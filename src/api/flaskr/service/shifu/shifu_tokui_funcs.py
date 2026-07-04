from __future__ import annotations

from typing import Any

from flask import Flask, has_app_context

from flaskr.api.langfuse import (
    create_trace_with_root_span,
    finalize_langfuse_trace,
    get_langfuse_client,
)
from flaskr.api.llm import invoke_llm
from flaskr.dao import db
from flaskr.service.check_risk.funcs import check_text_with_risk_control
from flaskr.service.common import raise_error, raise_param_error
from flaskr.service.metering import UsageContext
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftTokuiTemplate,
    PublishedTokuiTemplate,
)
from flaskr.service.tokui.common import (
    TOKUI_STATUS_FAILED,
    TOKUI_STATUS_IDLE,
    TOKUI_STATUS_VALIDATED,
    build_generation_payload,
    json_dumps,
    json_loads,
    normalize_media_refs,
    template_hash,
)
from flaskr.service.tokui.validator import validate_tokui_dsl
from flaskr.util import generate_id
from flaskr.util.datetime import now_utc


TOKUI_DEFAULT_CONTEXT_POLICY = {
    "allowed_context": [
        "course_title",
        "chapter_title",
        "outline_title",
        "teacher_material_refs",
        "learning_progress",
        "prior_learning_summary",
        "tokui_responses",
        "course_profile_variables",
    ]
}


def _as_json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            parsed = json_loads(value, default)
            return parsed
        except Exception:
            return default
    return value


def _latest_draft_outline(shifu_bid: str, outline_bid: str) -> DraftOutlineItem:
    outline = (
        DraftOutlineItem.query.filter(
            DraftOutlineItem.shifu_bid == shifu_bid,
            DraftOutlineItem.outline_item_bid == outline_bid,
            DraftOutlineItem.deleted == 0,
        )
        .order_by(DraftOutlineItem.id.desc())
        .first()
    )
    if not outline:
        raise_error("server.shifu.outlineItemNotFound")
    return outline


def _active_draft_template(
    shifu_bid: str, outline_bid: str
) -> DraftTokuiTemplate | None:
    return (
        DraftTokuiTemplate.query.filter(
            DraftTokuiTemplate.shifu_bid == shifu_bid,
            DraftTokuiTemplate.outline_item_bid == outline_bid,
            DraftTokuiTemplate.deleted == 0,
        )
        .order_by(DraftTokuiTemplate.id.desc())
        .first()
    )


def _serialize_template(template: DraftTokuiTemplate | PublishedTokuiTemplate | None) -> dict[str, Any]:
    if not template:
        return {}
    return {
        "tokui_template_bid": getattr(template, "tokui_template_bid", "")
        or getattr(template, "published_template_bid", ""),
        "published_template_bid": getattr(template, "published_template_bid", ""),
        "source_draft_template_bid": getattr(template, "source_draft_template_bid", ""),
        "shifu_bid": template.shifu_bid,
        "outline_item_bid": template.outline_item_bid,
        "teacher_intent": template.teacher_intent or "",
        "prompt_template": template.prompt_template or "",
        "concept": template.concept or "",
        "audience": template.audience or "",
        "material_refs": json_loads(template.material_refs, []),
        "media_refs": json_loads(template.media_refs, []),
        "generation_options": json_loads(template.generation_options, {}),
        "context_policy": json_loads(template.context_policy, TOKUI_DEFAULT_CONTEXT_POLICY),
        "preview_dsl": getattr(template, "preview_dsl", "") or "",
        "preview_interaction_schema": json_loads(
            getattr(template, "preview_interaction_schema", "[]"), []
        ),
        "preview_generation_status": getattr(template, "preview_generation_status", ""),
        "preview_validation_status": getattr(template, "preview_validation_status", ""),
        "preview_validation_error": json_loads(
            getattr(template, "preview_validation_error", ""), []
        ),
        "preview_parser_version": getattr(template, "preview_parser_version", ""),
        "template_hash": template.template_hash or "",
        "template_version": getattr(template, "template_version", 0),
    }


def _template_payload_from_request(payload: dict[str, Any]) -> dict[str, Any]:
    material_refs = _as_json_value(payload.get("material_refs"), [])
    media_refs = _as_json_value(payload.get("media_refs"), [])
    generation_options = _as_json_value(payload.get("generation_options"), {})
    context_policy = _as_json_value(
        payload.get("context_policy"), TOKUI_DEFAULT_CONTEXT_POLICY
    )
    if not isinstance(material_refs, list):
        raise_param_error("material_refs")
    if not isinstance(media_refs, list):
        raise_param_error("media_refs")
    if not isinstance(generation_options, dict):
        raise_param_error("generation_options")
    if not isinstance(context_policy, dict):
        raise_param_error("context_policy")
    return {
        "teacher_intent": str(payload.get("teacher_intent") or "").strip(),
        "prompt_template": str(payload.get("prompt_template") or "").strip(),
        "concept": str(payload.get("concept") or "").strip(),
        "audience": str(payload.get("audience") or "").strip(),
        "material_refs": material_refs,
        "media_refs": normalize_media_refs(media_refs),
        "generation_options": generation_options,
        "context_policy": context_policy,
    }


def get_draft_tokui_template(
    app: Flask, shifu_bid: str, outline_bid: str
) -> dict[str, Any]:
    with app.app_context():
        _latest_draft_outline(shifu_bid, outline_bid)
        return _serialize_template(_active_draft_template(shifu_bid, outline_bid))


def save_draft_tokui_template(
    app: Flask, user_bid: str, shifu_bid: str, outline_bid: str, payload: dict[str, Any]
) -> dict[str, Any]:
    with app.app_context():
        _latest_draft_outline(shifu_bid, outline_bid)
        template_payload = _template_payload_from_request(payload)
        if not template_payload["prompt_template"] and not template_payload["teacher_intent"]:
            raise_param_error("prompt_template")
        check_text_with_risk_control(
            app,
            outline_bid,
            user_bid,
            f"{template_payload['teacher_intent']}\n{template_payload['prompt_template']}",
        )
        hash_value = template_hash(template_payload)
        template = _active_draft_template(shifu_bid, outline_bid)
        if template is None:
            template = DraftTokuiTemplate()
            template.tokui_template_bid = generate_id(app)
            template.shifu_bid = shifu_bid
            template.outline_item_bid = outline_bid
            template.created_user_bid = user_bid
            db.session.add(template)

        template.teacher_intent = template_payload["teacher_intent"]
        template.prompt_template = template_payload["prompt_template"]
        template.concept = template_payload["concept"]
        template.audience = template_payload["audience"]
        template.material_refs = json_dumps(template_payload["material_refs"], [])
        template.media_refs = json_dumps(template_payload["media_refs"], [])
        template.generation_options = json_dumps(template_payload["generation_options"], {})
        template.context_policy = json_dumps(template_payload["context_policy"], TOKUI_DEFAULT_CONTEXT_POLICY)
        template.template_hash = hash_value
        template.updated_user_bid = user_bid
        template.updated_at = now_utc()
        if template.preview_generation_status == "":
            template.preview_generation_status = TOKUI_STATUS_IDLE
        db.session.commit()
        return _serialize_template(template)


def _build_generation_prompt(
    *,
    template_payload: dict[str, Any],
    context_payload: dict[str, Any],
    validation_errors: list[dict[str, Any]] | None = None,
) -> str:
    repair_section = ""
    if validation_errors:
        repair_section = (
            "\n\nThe previous TokUI DSL failed validation. Fix only the DSL while preserving intent.\n"
            f"Validation errors JSON:\n{json_dumps(validation_errors, [])}\n"
        )
    return f"""
You generate TokUI teaching UI. Return one JSON object only.

Required JSON shape:
{{
  "dsl": "[card tt:\\"...\\"]...[/card]",
  "interaction_schema": [
    {{
      "field_id": "stable_semantic_id",
      "field_type": "choice|text|number|boolean|submit",
      "label": "field label",
      "required": false,
      "semantic_role": "check_understanding",
      "value_shape": "string",
      "blocking": false,
      "continue_on_submit": false,
      "continuation_hint": ""
    }}
  ],
  "media_refs": []
}}

Rules:
- Do not explain outside JSON.
- Use TokUI DSL only in the dsl field.
- Include interaction_schema for every learner-fillable control.
- Reuse stable field_id names derived from the learning task.
- Reference only provided media/material URLs or IDs.
- If teacher media refs are provided, use them where they help explain the
  concept. For images, render an image/media element using the provided stable
  URL or resource_id. For videos, render a video/player/media element using the
  provided stable URL or resource_id. Never invent media URLs.
- The output media_refs list must contain only the provided media refs that are
  actually used in the DSL.
- Keep the output concise enough for one lesson node.
- Treat learner-fillable input as a teaching checkpoint when later lesson content
  depends on the learner answer.
- For a checkpoint, generate only the content before the question plus the
  learner input/submit UI. Do not generate answer-dependent follow-up content in
  the same DSL before the learner submits.
- Mark checkpoint fields with "blocking": true and "continue_on_submit": true.
  Use "continuation_hint" to explain what the next generation should do after
  the answer is saved.
- When Runtime context JSON contains tokui_responses, use those answers to
  generate the next appropriate teaching content instead of asking the same
  checkpoint again.

Teacher template JSON:
{json_dumps(template_payload, {})}

Runtime context JSON:
{json_dumps(context_payload, {})}
{repair_section}
""".strip()


def _invoke_tokui_llm(
    app: Flask,
    *,
    user_bid: str,
    outline: Any,
    template_payload: dict[str, Any],
    context_payload: dict[str, Any],
    validation_errors: list[dict[str, Any]] | None = None,
    generation_name: str,
) -> dict[str, Any]:
    model = str(
        (template_payload.get("generation_options") or {}).get("model")
        or outline.ask_llm
        or outline.llm
        or ""
    ).strip()
    if not model:
        raise_param_error("model")
    temperature = float(
        (template_payload.get("generation_options") or {}).get("temperature")
        or outline.ask_llm_temperature
        or outline.llm_temperature
        or 0.3
    )
    prompt = _build_generation_prompt(
        template_payload=template_payload,
        context_payload=context_payload,
        validation_errors=validation_errors,
    )
    trace = None
    span = None
    try:
        trace, span = create_trace_with_root_span(
            client=get_langfuse_client(),
            trace_payload={
                "name": generation_name,
                "user_id": user_bid,
                "metadata": {
                    "shifu_bid": outline.shifu_bid,
                    "outline_item_bid": outline.outline_item_bid,
                },
            },
            root_span_payload={"name": generation_name, "input": context_payload},
        )
        chunks = invoke_llm(
            app,
            user_bid,
            span,
            model=model,
            message=prompt,
            json=True,
            stream=True,
            generation_name=generation_name,
            usage_context=UsageContext(
                user_bid=user_bid,
                shifu_bid=outline.shifu_bid,
                outline_item_bid=outline.outline_item_bid,
                usage_scene=BILL_USAGE_SCENE_DEBUG,
            ),
            usage_scene=BILL_USAGE_SCENE_DEBUG,
            temperature=temperature,
        )
        response_text = "".join(chunk.result for chunk in chunks if chunk.result)
        return build_generation_payload(response_text)
    finally:
        if trace is not None:
            finalize_langfuse_trace(
                trace=trace,
                root_span=span,
                root_span_payload={"output": generation_name},
            )


def generate_teacher_tokui_preview(
    app: Flask, user_bid: str, shifu_bid: str, outline_bid: str, payload: dict[str, Any]
) -> dict[str, Any]:
    with app.app_context():
        template = save_draft_tokui_template(app, user_bid, shifu_bid, outline_bid, payload)
        outline = _latest_draft_outline(shifu_bid, outline_bid)
        template_row = _active_draft_template(shifu_bid, outline_bid)
        if template_row is None:
            raise_error("server.shifu.outlineItemNotFound")

        context_payload = {
            "mode": "teacher_preview",
            "course": {"shifu_bid": shifu_bid},
            "outline": {"outline_item_bid": outline_bid, "title": outline.title},
            "sample_learner_context": payload.get("sample_context") or {},
            "teacher_media_refs": template.get("media_refs") or [],
        }
        generated = _invoke_tokui_llm(
            app,
            user_bid=user_bid,
            outline=outline,
            template_payload=template,
            context_payload=context_payload,
            generation_name="tokui_teacher_preview",
        )
        validation = validate_tokui_dsl(app, generated["dsl"])
        repair_attempted = False
        if not validation.ok:
            repair_attempted = True
            generated = _invoke_tokui_llm(
                app,
                user_bid=user_bid,
                outline=outline,
                template_payload=template,
                context_payload=context_payload,
                validation_errors=[error.to_dict() for error in validation.errors],
                generation_name="tokui_teacher_preview_repair",
            )
            validation = validate_tokui_dsl(app, generated["dsl"])

        template_row.preview_dsl = generated["dsl"]
        template_row.preview_interaction_schema = json_dumps(
            generated["interaction_schema"], []
        )
        template_row.media_refs = json_dumps(template.get("media_refs") or [], [])
        template_row.preview_generation_status = (
            TOKUI_STATUS_VALIDATED if validation.ok else TOKUI_STATUS_FAILED
        )
        template_row.preview_validation_status = (
            TOKUI_STATUS_VALIDATED if validation.ok else TOKUI_STATUS_FAILED
        )
        template_row.preview_validation_error = json_dumps(
            [error.to_dict() for error in validation.errors], []
        )
        template_row.preview_parser_version = validation.parser_version
        template_row.updated_user_bid = user_bid
        template_row.updated_at = now_utc()
        db.session.commit()
        result = _serialize_template(template_row)
        result["repair_attempted"] = repair_attempted
        return result


def validate_tokui_preview(app: Flask, dsl: str) -> dict[str, Any]:
    with app.app_context():
        return validate_tokui_dsl(app, dsl).to_dict()


def _publish_tokui_templates_in_current_context(
    app: Flask, user_bid: str, shifu_bid: str
) -> None:
    PublishedTokuiTemplate.query.filter(
        PublishedTokuiTemplate.shifu_bid == shifu_bid,
        PublishedTokuiTemplate.deleted == 0,
    ).update({"deleted": 1}, synchronize_session=False)
    draft_templates = DraftTokuiTemplate.query.filter(
        DraftTokuiTemplate.shifu_bid == shifu_bid,
        DraftTokuiTemplate.deleted == 0,
    ).all()
    now = now_utc()
    for draft in draft_templates:
        existing_latest = (
            PublishedTokuiTemplate.query.filter(
                PublishedTokuiTemplate.source_draft_template_bid
                == draft.tokui_template_bid,
                PublishedTokuiTemplate.deleted == 1,
            )
            .order_by(PublishedTokuiTemplate.template_version.desc())
            .first()
        )
        published = PublishedTokuiTemplate()
        published.published_template_bid = generate_id(app)
        published.source_draft_template_bid = draft.tokui_template_bid
        published.shifu_bid = draft.shifu_bid
        published.outline_item_bid = draft.outline_item_bid
        published.teacher_intent = draft.teacher_intent
        published.prompt_template = draft.prompt_template
        published.concept = draft.concept
        published.audience = draft.audience
        published.material_refs = draft.material_refs
        published.media_refs = draft.media_refs
        published.generation_options = draft.generation_options
        published.context_policy = draft.context_policy
        published.preview_dsl = draft.preview_dsl
        published.preview_interaction_schema = draft.preview_interaction_schema
        published.template_hash = draft.template_hash
        published.template_version = int(
            getattr(existing_latest, "template_version", 0) or 0
        ) + 1
        published.published_at = now
        published.published_user_bid = user_bid
        published.created_at = now
        published.updated_at = now
        db.session.add(published)


def publish_tokui_templates(app: Flask, user_bid: str, shifu_bid: str) -> None:
    if has_app_context():
        _publish_tokui_templates_in_current_context(app, user_bid, shifu_bid)
        return

    with app.app_context():
        _publish_tokui_templates_in_current_context(app, user_bid, shifu_bid)
        db.session.commit()
