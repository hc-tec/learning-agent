from __future__ import annotations

from typing import Any

from flask import Flask, has_app_context

from flaskr.api.langfuse import (
    create_trace_with_root_span,
    finalize_langfuse_trace,
    get_langfuse_client,
)
from flaskr.api.llm import chat_llm, invoke_llm
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
    extract_json_object,
    json_dumps,
    json_loads,
    normalize_interaction_points,
    normalize_material_refs,
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
        "teacher_media_refs",
        "learning_progress",
        "prior_learning_summary",
        "tokui_responses",
        "course_profile_variables",
    ]
}

TOKUI_E2E_CONTROLLED_MODEL = "tokui-e2e-controlled"

TOKUI_UI_PATTERN_DECISION_GUIDE = """
TokUI UI pattern decision guide:
- First classify each teaching segment by learning job, then choose the UI.
  Do not choose tags because they look decorative.
- Category comparison / type taxonomy / parameter contrast:
  use a reference comparison board. Prefer `[row]` with 3-5 `[col]` cards
  containing `[badge]` titles and short labeled `[p]` facts, or a valid
  `[table]` when strict alignment matters. Each card/row must expose field
  labels such as 速度, 功能, 特点, 适用场景, 数智化侧重.
- Process / sequence / cause-effect / route / schedule:
  use `[steps]` or `[timeline]`; each step should have a concise title and
  one action/decision, not a paragraph dump.
- Candidate selection / POI list / option filtering / preference collection:
  use `[tag]`, `[badge]`, `[btngroup]`, `[input-tag]`, `[radio]`, or
  `[checkbox]` so the learner can scan and choose. Do not turn choices into
  plain prose.
- Confirmation / summary before proceeding:
  use a focused `[card]` or `[callout]` plus a real submit/choice control.
- Feedback after a learner answer:
  use a feedback card first, with a visible label such as 回答正确, 存在误区,
  回答不够具体, or 答非所问, then continue or ask a retry question.
- Media placeholders:
  render them as muted resource/status rows near the insertion point, not as
  random body text.
- A good learner block should feel like a small teaching tool: clear current
  task, scannable reference panel, explicit choices, and one obvious next
  action. A bad learner block is a prose article with decorative cards.
""".strip()

TOKUI_DSL_BEST_PRACTICES = """
TokUI DSL best practices from the parser/docs:
- Put "dsl" as the first JSON property so learner streaming can start while the
  JSON response is still being generated.
- Containers need matching closing tags. Leaf tags must not pretend to contain
  children.
- A `card` that has child blocks must not use `tx:`. Write
  `[card tt:"标题"][p 正文][btn tx:"继续" act:submit][/card]`, not
  `[card tt:"标题" tx:"正文"][btn ...][/card]`; otherwise later children become
  orphan top-level nodes.
- Variants always use `v:`. Write `[p v:muted 提示]`, not `[p muted 提示]`;
  bare variant words become visible body text.
- Paragraph `p` is dual-mode. Use leaf mode for plain text:
  `[p 一段文字]`. Use container mode only when it contains block children:
  `[p][btn tx:"按钮"][/p]`.
- Text containing literal `[` or `]`, or an ASCII `Q:` / `A:` prefix, must be
  protected. Prefer full-width `Q：` / `A：`, or quote the whole text body.
- Attribute values containing spaces, commas, pipes, semicolons, brackets, or
  colons must be double-quoted, especially `opt:"value:label;value2:label2"`.
- For streaming readability, long text blocks should use container forms such as
  `[callout t:info]...[/callout]`, `[md]...[/md]`, or `[code lang:js]...[/code]`
  rather than a giant `tx:` value.
- Use supported media tags directly: `[img s:"provided_url" tt:"title"]` and
  `[video s:"provided_url" controls]`; never invent `[media]`.
- Use supported teaching layout intentionally: `[row]`/`[col]` for comparisons,
  `[table]`/`[thead]`/`[tbody]`/`[tr]` for aligned facts, `[steps]`/`[step]`
  for sequences, `[callout]` for key judgments, and `[card]` for a focused
  teaching block. Use `[timeline]` for route/time arrangements, `[tabs]` for
  day/module switching, `[collapse]` for optional details, and `[input-tag]`
  when the learner edits a selected list. Do not invent unknown visual tags.
- TokUI tables do not use HTML-style `[td]` or `[th]` tags. Write table headers
  as `[thead cols:"类型,速度,功能,数智化侧重"]` and rows as comma-separated
  `[tr "高速铁路,250-350 km/h,长途纯客运,智能运维"]`. If any cell contains
  spaces, commas, pipes, or punctuation-heavy text, quote the entire row body.
- For comparison teaching that should look like a reference image or A2UI panel,
  prefer `[row]` with several `[col]` cards containing `[badge]`, `[tag]`, short
  `[p]` lines, and one clear visual hierarchy. Use `[table]` only when a real
  aligned grid is more readable than cards.
- Text is allowed and often necessary, but do not confuse structured tags with
  good visual teaching. When the concept benefits from a reference-picture-like
  UI, compose one from supported TokUI primitives: comparison cards, candidate
  lists, timeline cards, parameter tables, selected chips/tags, or decision
  panels. The result should feel like a small teaching app embedded in the
  lesson, not only an article with controls.
- For learner questions, use supported form controls:
  `[textarea n:field_id l:"问题" ph:"写下你的理解"][/textarea]`,
  `[radio n:field_id l:"问题" v:vertical opt:"a:选项A;b:选项B"]`,
  `[checkbox n:field_id l:"问题" v:vertical opt:"a:选项A;b:选项B"]`, and
  `[radio n:field_id l:"判断题" v:vertical opt:"true:对;false:错"]`.
""".strip()


def _is_e2e_controlled_tokui(template_payload: dict[str, Any]) -> bool:
    generation_options = template_payload.get("generation_options") or {}
    if not isinstance(generation_options, dict):
        return False
    return (
        generation_options.get("e2e_controlled_llm") is True
        and str(generation_options.get("model") or "").strip()
        == TOKUI_E2E_CONTROLLED_MODEL
    )


def _tokui_attr(value: Any) -> str:
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace('"', "'")
        .replace("[", "(")
        .replace("]", ")")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _controlled_media_urls(context_payload: dict[str, Any]) -> list[str]:
    media_refs = context_payload.get("teacher_media_refs") or []
    if not isinstance(media_refs, list):
        return []
    urls: list[str] = []
    for item in media_refs:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("src") or "").strip()
        if url and url not in urls:
            urls.append(url)
    return urls


def _controlled_response_value(
    responses: list[dict[str, Any]], field_id: str, default: str = ""
) -> str:
    for response in responses:
        if not isinstance(response, dict):
            continue
        if str(response.get("field_id") or "") != field_id:
            continue
        value = response.get("value")
        if isinstance(value, dict):
            return str(value.get("value") or value.get("text") or default)
        return str(value if value is not None else default)
    return default


def _controlled_image_block(urls: list[str]) -> str:
    if not urls:
        return ""
    images = "".join(
        f'[img s:"{_tokui_attr(url)}" tt:"E2E teaching image {index + 1}"]'
        for index, url in enumerate(urls[:2])
    )
    return f"[imgs]{images}[/imgs]"


def _controlled_template_marker(template_payload: dict[str, Any]) -> str:
    source = (
        f"{template_payload.get('teacher_intent') or ''}\n"
        f"{template_payload.get('prompt_template') or ''}"
    )
    if "E2E_VERSION_2" in source:
        return '[p E2E_TEMPLATE_MARKER:E2E_VERSION_2]'
    if "E2E_VERSION_1" in source:
        return '[p E2E_TEMPLATE_MARKER:E2E_VERSION_1]'
    return ""


def _build_e2e_controlled_tokui_generation(
    *,
    template_payload: dict[str, Any],
    context_payload: dict[str, Any],
    generation_name: str,
) -> dict[str, Any]:
    responses = context_payload.get("tokui_responses") or []
    if not isinstance(responses, list):
        responses = []
    urls = _controlled_media_urls(context_payload)
    image_block = _controlled_image_block(urls)
    template_marker = _controlled_template_marker(template_payload)
    prior = _controlled_response_value(responses, "prior_experience", "none")
    explanation = _controlled_response_value(
        responses, "concept_explanation", "missing explanation"
    )
    confidence = _controlled_response_value(responses, "confidence_score", "0")
    refinement = _controlled_response_value(
        responses, "refinement_plan", "missing refinement"
    )

    if any(
        str(item.get("field_id") or "") == "refinement_plan"
        for item in responses
        if isinstance(item, dict)
    ):
        dsl = (
            '[card tt:"E2E stage 3 - targeted feedback"]'
            f"{template_marker}"
            f"{image_block}"
            f'[p The learner first chose "{_tokui_attr(prior)}", explained '
            f'"{_tokui_attr(explanation)}", rated confidence as '
            f'"{_tokui_attr(confidence)}", then refined with '
            f'"{_tokui_attr(refinement)}".]'
            "[p E2E_ASSERT_ROUND_THREE sees both prior rounds and now gives "
            "answer-dependent feedback instead of asking the same checkpoint.]"
            "[/card]"
        )
        return {"dsl": dsl, "interaction_schema": [], "media_refs": []}

    if any(
        str(item.get("field_id") or "") == "concept_explanation"
        for item in responses
        if isinstance(item, dict)
    ):
        dsl = (
            '[card tt:"E2E stage 2 - follow-up checkpoint"]'
            f"{template_marker}"
            f"{image_block}"
            f'[p E2E_ASSERT_ROUND_TWO uses prior_experience="{_tokui_attr(prior)}" '
            f'and concept_explanation="{_tokui_attr(explanation)}".]'
            "[p Now ask for a repair plan before continuing.]"
            "[form]"
            '[textarea n:refinement_plan l:"Repair plan"]Describe the next teaching move[/textarea]'
            '[btn act:submit tx:"Continue"]'
            "[/form]"
            "[/card]"
        )
        return {
            "dsl": dsl,
            "interaction_schema": [
                {
                    "field_id": "refinement_plan",
                    "field_type": "text",
                    "label": "Repair plan",
                    "required": True,
                    "semantic_role": "follow_up_checkpoint",
                    "value_shape": "string",
                    "blocking": True,
                    "continue_on_submit": True,
                    "continuation_hint": "Use the first and second round answers.",
                }
            ],
            "media_refs": [],
        }

    dsl = (
        '[card tt:"E2E stage 1 - multi-input checkpoint"]'
        f"{template_marker}"
        f"{image_block}"
        "[p E2E_ASSERT_ROUND_ONE introduces the concept with two teaching images, "
        "then stops at a blocking checkpoint.]"
        "[form]"
        '[select n:prior_experience l:"Prior experience" opt:"new,worked_with_it,expert"]'
        '[textarea n:concept_explanation l:"Concept explanation"]Explain the pressure path[/textarea]'
        '[input n:confidence_score l:"Confidence score" type:number ph:"1-5"]'
        '[btn act:submit tx:"Submit"]'
        "[/form]"
        "[/card]"
    )
    return {
        "dsl": dsl,
        "interaction_schema": [
            {
                "field_id": "prior_experience",
                "field_type": "choice",
                "label": "Prior experience",
                "required": True,
                "semantic_role": "learner_background",
                "value_shape": "string",
                "blocking": False,
                "continue_on_submit": False,
                "continuation_hint": "",
            },
            {
                "field_id": "concept_explanation",
                "field_type": "text",
                "label": "Concept explanation",
                "required": True,
                "semantic_role": "check_understanding",
                "value_shape": "string",
                "blocking": True,
                "continue_on_submit": True,
                "continuation_hint": "Use this answer to generate the follow-up.",
            },
            {
                "field_id": "confidence_score",
                "field_type": "number",
                "label": "Confidence score",
                "required": True,
                "semantic_role": "confidence",
                "value_shape": "number",
                "blocking": False,
                "continue_on_submit": False,
                "continuation_hint": "",
            },
        ],
        "media_refs": [],
    }


def _build_e2e_controlled_guidance() -> str:
    return "\n".join(
        [
            "E2E controlled teaching guide: teach in three stages.",
            "Stage 1: compare at least two provided media resources and ask a",
            "multi-field checkpoint before continuing.",
            "Stage 2: use the learner's first answer verbatim, diagnose the gap,",
            "and ask one blocking follow-up for a repair plan.",
            "Stage 3: use answers from both previous rounds and give targeted",
            "feedback. Never invent media URLs; only use teacher_media_refs.",
            "Feedback rule: incomplete answers should be acknowledged honestly",
            "and repaired with a concrete next explanation.",
        ]
    )


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
    generation_options = json_loads(template.generation_options, {})
    interaction_points = normalize_interaction_points(
        generation_options.get("interaction_points")
    )
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
        "material_refs": normalize_material_refs(json_loads(template.material_refs, [])),
        "media_refs": json_loads(template.media_refs, []),
        "interaction_points": interaction_points,
        "generation_options": {
            **generation_options,
            "interaction_points": interaction_points,
        },
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
    interaction_points = _as_json_value(
        payload.get("interaction_points"), generation_options.get("interaction_points", [])
    )
    if not isinstance(interaction_points, list):
        raise_param_error("interaction_points")
    normalized_interaction_points = normalize_interaction_points(interaction_points)
    generation_options = {
        **generation_options,
        "interaction_points": normalized_interaction_points,
    }
    return {
        "teacher_intent": str(payload.get("teacher_intent") or "").strip(),
        "prompt_template": str(payload.get("prompt_template") or "").strip(),
        "concept": str(payload.get("concept") or "").strip(),
        "audience": str(payload.get("audience") or "").strip(),
        "material_refs": normalize_material_refs(material_refs),
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
    generation_options = template_payload.get("generation_options") or {}
    interaction_mode = str(generation_options.get("interaction_mode") or "").strip()
    checkpoint_required = bool(generation_options.get("blocking_checkpoint"))
    interaction_points = normalize_interaction_points(
        generation_options.get("interaction_points")
    )
    material_refs = normalize_material_refs(template_payload.get("material_refs"))
    interaction_policy = (
        "- The teacher selected CHECKPOINT mode. You must include one meaningful "
        "learner-fillable checkpoint unless saved tokui_responses already answer "
        "it. Mark that field with \"blocking\": true and "
        "\"continue_on_submit\": true.\n"
        if checkpoint_required or interaction_mode == "checkpoint"
        else "- The teacher selected NORMAL interaction mode. Add learner input only "
        "when the teaching guide asks for it; do not mark fields as blocking "
        "unless later content truly depends on the answer.\n"
    )
    if interaction_points:
        interaction_policy += (
            "- The teacher provided explicit interaction/check points. Treat them "
            "as course design requirements, not suggestions. Each interaction point "
            "is a flow insertion point by default: teach the relevant section first, then render "
            "that checkpoint at its position/insertion_point. Do not dump all "
            "interaction points together as a form or end-of-lesson quiz unless the "
            "teacher explicitly asked for a quiz. Generate at most the next "
            "unanswered blocking point at this runtime step; after the answer is "
            "saved, continue with the next dependent explanation or checkpoint.\n"
        )
    feedback_policy = ""
    tokui_responses = context_payload.get("tokui_responses")
    if isinstance(tokui_responses, list) and tokui_responses:
        feedback_policy = (
            "- Runtime context includes saved learner answers. Before moving on, "
            "diagnose the answer quality and give differentiated feedback: if the "
            "answer is correct, confirm why and continue; if it is incorrect, name "
            "the misconception and reteach the relevant prerequisite; if it is vague "
            "or incomplete, ask for precision or give a contrastive example; if it is "
            "off-topic, explicitly bring the learner back to the original checkpoint. "
            "Choose the continuation strategy from that diagnosis: correct answers may "
            "advance, but incorrect, vague, incomplete, or off-topic answers must get "
            "remediation, a clarifying prompt, or a return-to-question step before the "
            "next dependent concept. If you ask the learner to try again, use a new "
            "field_id with a suffix such as _retry or _clarification; do not reuse an "
            "already answered field_id. Use an explicit Chinese feedback label such as "
            "\"回答正确\", \"存在误区\", \"回答不够具体\", or \"答非所问\" so the learner "
            "understands why the next step changed. Do not mechanically continue as if "
            "every answer were correct.\n"
        )
    prior_artifact_policy = ""
    prior_artifacts = context_payload.get("prior_tokui_artifacts")
    if isinstance(prior_artifacts, list) and prior_artifacts:
        prior_artifact_policy = (
            "- Runtime context includes prior_tokui_artifacts. These artifacts are "
            "already visible above the new output in the learner page. Treat them as "
            "the conversation history and do not re-teach, re-list, or re-render their "
            "lesson sections, media placeholders, or answered checkpoints. The new "
            "DSL must be an appended continuation after the latest submitted artifact: "
            "first give answer-quality feedback, then move only to the next genuinely "
            "uncovered teaching segment or a downstream checkpoint. If an interaction "
            "point's insertion content is already covered in prior_tokui_artifacts, do "
            "not repeat that content just to ask the question; either ask a concise "
            "downstream check without re-explaining, or skip to the next logical point "
            "when the question is no longer pedagogically appropriate.\n"
        )
    presentation_policy = (
        "- For an initial learner runtime block with complex teacher design "
        "(multiple material placements, multiple media refs, multiple interaction "
        "points, or a long teaching guide), the DSL may include normal explanatory "
        "text, but it MUST also include at least one reference-picture-like UI panel "
        "built from supported TokUI tags: `[table]`, `[row]`/`[col]`, `[steps]`, "
        "`[desc]`, `[tag]`, `[badge]`, `[btngroup]`, `[timeline]`, `[tabs]`, "
        "`[collapse]`, `[input-tag]`, `[radio]`, or `[checkbox]`. "
        "When the lesson compares 3 or more categories, use `[table]` or "
        "`[row]`/`[col]` before the first checkpoint. When the lesson has time/order "
        "or process structure, use `[steps]` or `[timeline]`. When the learner must choose among "
        "candidates, use chips/tags/badges and real choice controls. This is a "
        "runtime contract, not a style suggestion.\n"
        "- Apply the UI pattern decision guide before writing DSL. Match the UI "
        "to the teaching job: comparison board for taxonomies, steps/timeline for "
        "processes, option panels for choices, resource/status rows for materials, "
        "and feedback cards for answer diagnosis. If a lesson segment contains "
        "both explanation and a learner decision, render the reference panel first "
        "and the decision/checkpoint after it.\n"
    )
    material_policy = (
        "- The teacher provided structured material placements. Use their "
        "insertion_point, title, description, purpose, media_type, and stable "
        "resource URL/ID to decide where each image/video belongs. A lesson may "
        "have many materials; do not collapse them into one generic image.\n"
        if material_refs
        else ""
    )
    repair_section = ""
    if validation_errors:
        repair_section = (
            "\n\nThe previous TokUI output failed validation or a runtime continuation contract. "
            "Fix the output while preserving intent. If the error says an already answered "
            "field was repeated, remove that checkpoint and generate the next answer-dependent "
            "feedback/continuation block instead. If you still need the learner to retry "
            "the same concept, ask a new retry question with a fresh field_id suffix such as "
            "_retry or _clarification. If the error says the continuation is missing "
            "answer-quality feedback, make the first DSL block an explicit feedback card "
            "using \"回答正确\", \"存在误区\", \"回答不够具体\", or \"答非所问\" before any new teaching. "
            "If the error code is TokuiPresentationMissingStructure, keep useful "
            "text but add a reference-picture-like UI panel with supported tags "
            "such as `[table]`, `[row]`/`[col]`, `[steps]`, `[desc]`, `[tag]`, "
            "`[badge]`, `[btngroup]`, `[timeline]`, `[tabs]`, `[collapse]`, "
            "`[input-tag]`, `[radio]`, or `[checkbox]`. For comparison-heavy "
            "lessons, use a table or row/col comparison before the checkpoint. "
            "Also re-check the TokUI parser footguns below before returning the repaired JSON.\n"
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
      "field_type": "short_text|single_choice|multi_choice|true_false",
      "label": "field label",
      "required": false,
      "semantic_role": "check_understanding",
      "value_shape": "string",
      "options": [
        {{"value": "a", "label": "option label"}}
      ],
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
- Put the `dsl` property first in the returned JSON object, followed by
  `interaction_schema` and `media_refs`, so the runtime can stream the DSL field
  immediately.
- Use only supported TokUI teaching tags for common lesson structure:
  `[card]`, `[p]`, `[h1]` to `[h6]`, `[callout]`, `[list]`, `[item]`,
  `[row]`, `[col]`, `[table]`, `[thead]`, `[tbody]`, `[tr]`, `[desc]`,
  `[steps]`, `[step]`, `[timeline]`, `[tabs]`, `[tab]`, `[collapse]`,
  `[input-tag]`, `[tag]`, `[badge]`, `[img]`, `[video]`, `[form]`,
  `[input]`, `[textarea]`, `[radio]`, `[checkbox]`, `[select]`, `[opt]`,
  `[btngroup]`, and `[btn]`.
  Never generate `[heading]`, `[section]`, `[submit]`, `[media]`, `[td]`, or
  `[th]` tags.
  For section titles use self-closing headings such as `[h2 二、我国铁路四大核心类型]`.
  For muted placeholder text use leaf paragraph syntax such as
  `[p v:muted 素材待提供：四类铁路实景对比短片]`; do not append `[/p]`
  to a leaf paragraph.
- Use real TokUI form syntax for learner controls, where `n` exactly matches
  interaction_schema `field_id`:
  - short_text: `[textarea n:"field_id" l:"field label" ph:"写下你的理解" req][/textarea]`
  - single_choice: `[radio n:"field_id" l:"field label" v:vertical opt:"a:选项A;b:选项B"]`
  - multi_choice: `[checkbox n:"field_id" l:"field label" v:vertical opt:"a:选项A;b:选项B"]`
  - true_false: `[radio n:"field_id" l:"field label" v:vertical opt:"true:对;false:错"]`
  Use `[btn tx:"提交" v:primary act:submit]` for the submit button.
  Do not generate `[submit]`, `field_id=`, `field_type=`, `label=`, or
  `required=true` attributes in the DSL; those names belong only in JSON
  interaction_schema.
- Include interaction_schema for every learner-fillable control.
- Use canonical interaction_schema field_type values: `short_text`,
  `single_choice`, `multi_choice`, and `true_false`. `number` is only for
  legacy controlled E2E data, not new teaching questions.
- For single_choice and multi_choice, include an `options` array with stable
  string values and learner-readable labels. For true_false, use values
  `"true"` and `"false"` with labels matching the lesson language.
- Reuse stable field_id names derived from the learning task.
- Presentation quality matters. Do not output a wall of plain `[p]` nodes when
  the content has structure. Use callouts for key judgments, tables or
  row/col cards for comparisons, steps for sequences, short lists for criteria,
  and a clear question/feedback card around each checkpoint. Keep the layout
  readable on mobile and avoid decorative complexity.
- This presentation requirement is mandatory for complex lessons. If the
  teacher design contains several materials, media refs, interaction points, or
  a detailed guide, the initial learner DSL can still include explanatory text,
  but must also contain at least one reference UI pattern using `[table]`,
  `[row]`/`[col]`, `[steps]`, `[desc]`, `[tag]`, `[badge]`, `[btngroup]`,
  `[timeline]`, `[tabs]`, `[collapse]`, `[input-tag]`, `[radio]`, or
  `[checkbox]`. Think in terms of teaching reference panels:
  a route/comparison board, option cards, a parameter table, a timeline, a
  checklist, selected chips, or a decision panel. Avoid plain article output.
  Prefer `[row]`/`[col]` comparison cards for A2UI-style visual teaching. If
  you use `[table]`, use TokUI syntax: `[thead cols:"类型,速度,功能"]` and
  comma-separated `[tr "高速铁路,250-350 km/h,长途客运"]` rows; never put
  `[td]` or `[th]` inside a table.
- Treat teacher_intent as the learner outcome and prompt_template as the
  teacher's detailed teaching guide. The guide may contain teaching sequence,
  examples, misconceptions, checkpoint timing, feedback rules, and standards
  for whether the learner has actually understood. Use it as the source
  material for a student-facing teaching rewrite: restructure, paraphrase,
  stage, and adapt it into TokUI teaching, but preserve critical facts,
  examples, learner goals, and checkpoint logic. Do not reduce it to a short
  generic summary and do not merely copy the teacher script verbatim. The
  generated lesson should read like a teacher-facing guide has been rewritten
  into a clear learner-facing classroom flow, not pasted as raw instructions.
- Reference only provided media/material URLs or IDs.
- If teacher media refs are provided, use them where they help explain the
  concept. For images with a URL, render `[img s:"provided_url" tt:"title"
  alt:"title"]`. For videos with a URL, render `[video s:"provided_url"]`.
  Do not generate `[media]` tags. If a teacher material placement has no usable
  URL/resource yet, write a short learner-readable placeholder such as
  `[p v:muted 素材待提供：素材标题]` instead of exposing empty technical attributes.
  Never invent media URLs.
- The output media_refs list must contain only the provided media refs that are
  actually used in the DSL.
- Keep the output concise enough for one lesson node.
- Treat learner-fillable input as a teaching checkpoint when later lesson content
  depends on the learner answer.
- Treat teacher-provided interaction_points as in-flow teaching checkpoints.
  Explain the relevant section first, then place the checkpoint at its
  position/insertion_point. Do not collect multiple checkpoints as one
  continuous form or final quiz unless the teacher explicitly instructs that.
- For a checkpoint, generate only the content before the question plus the
  learner input/submit UI. Do not generate answer-dependent follow-up content in
  the same DSL before the learner submits.
- Mark checkpoint fields with "blocking": true and "continue_on_submit": true.
  Use "continuation_hint" to explain what the next generation should do after
  the answer is saved.
- When Runtime context JSON contains tokui_responses, use those answers to
  generate only the next appropriate continuation block. The first DSL block
  MUST be an answer-quality feedback block with an explicit label: "回答正确",
  "存在误区", "回答不够具体", or "答非所问". Do not repeat the lesson opening,
  do not restart the same explanation, and do not ask the same checkpoint again.
  If the answer is vague or off-topic and the learner must try again, ask a new
  clarification/retry control with a fresh field_id suffix such as _retry or
  _clarification instead of reusing an answered field_id.
  The learner UI will append this new block after the prior block, so the new
  DSL must read like "based on your answer, continue with..." rather than a
  fresh course entry.
- In continuation blocks, always provide answer-quality feedback before new
  teaching content. Decide whether the learner answer is correct, incorrect,
  vague/incomplete, or off-topic, then choose the follow-up strategy from that
  diagnosis. Do not treat every submitted answer as correct.

TokUI parser/source best practices:
{TOKUI_DSL_BEST_PRACTICES}

{TOKUI_UI_PATTERN_DECISION_GUIDE}
{presentation_policy}
{material_policy}
{interaction_policy}
{feedback_policy}
{prior_artifact_policy}

Teacher template JSON:
{json_dumps(template_payload, {})}

Runtime context JSON:
{json_dumps(context_payload, {})}
{repair_section}
""".strip()


def _build_guidance_prompt(
    *,
    template_payload: dict[str, Any],
    context_payload: dict[str, Any],
) -> str:
    generation_options = template_payload.get("generation_options") or {}
    interaction_mode = str(generation_options.get("interaction_mode") or "").strip()
    checkpoint_required = bool(generation_options.get("blocking_checkpoint"))
    interaction_points = normalize_interaction_points(
        generation_options.get("interaction_points")
    )
    material_refs = normalize_material_refs(template_payload.get("material_refs"))
    interaction_policy = (
        "The lesson must include one blocking checkpoint question. Explain what "
        "the checkpoint diagnoses, what counts as a good answer, what common "
        "misconceptions to watch for, and how the next explanation should depend "
        "on the learner answer."
        if checkpoint_required or interaction_mode == "checkpoint"
        else "Only ask for learner input when it improves the lesson. Do not make "
        "an interaction blocking unless later content truly depends on that answer."
    )
    material_policy = (
        "The teacher has listed structured material placements. Preserve each "
        "placement's insertion point, role, media type, title, and teaching purpose "
        "in the guide so generation can render multiple images/videos at the right "
        "moments."
        if material_refs
        else "If media would help, describe exactly what kind of image or video "
        "would be useful and where it should appear."
    )
    explicit_interaction_policy = (
        "The teacher has listed explicit interaction/check points. Preserve all of "
        "them, explain what each diagnoses, which ones block later content, and how "
        "later generation should use each learner answer."
        if interaction_points
        else "If the lesson needs checks, describe multiple possible checkpoints "
        "instead of assuming one lesson has only one learner input."
    )
    return f"""
You are helping a teacher write a detailed AI teaching guide for TokUI lesson generation.
Return one JSON object only:
{{
  "prompt_template": "the improved detailed teaching guide"
}}

What this guide is:
- It is instructions for the AI teacher, not final student-facing copy.
- It should describe teaching sequence, explanation style, examples, media usage,
  checkpoint timing, expected learner answer quality, feedback rules, follow-up
  strategy, and misconception handling.
- It should be concrete enough that another model can generate TokUI DSL and an
  interaction_schema without guessing the teacher's pedagogy.
- Keep it practical for one lesson node, but do not collapse it into a short prompt.

Language:
- Use Chinese when the teacher input is Chinese or mostly Chinese.
- Use English when the teacher input is English or mostly English.
- Do not introduce any third language.

Interaction policy:
{interaction_policy}

Material policy:
{material_policy}

Explicit interaction points policy:
{explicit_interaction_policy}

Teacher draft JSON:
{json_dumps(template_payload, {})}

Authoring context JSON:
{json_dumps(context_payload, {})}
""".strip()


def _resolve_generation_settings(
    template_payload: dict[str, Any], outline: Any
) -> tuple[str, float]:
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
    return model, temperature


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
    generated: dict[str, Any] | None = None
    for event in iter_tokui_llm_generation(
        app,
        user_bid=user_bid,
        outline=outline,
        template_payload=template_payload,
        context_payload=context_payload,
        validation_errors=validation_errors,
        generation_name=generation_name,
    ):
        if event.get("type") == "final":
            generated = event.get("generated")
    if generated is None:
        raise_error("server.shifu.tokuiGenerationFailed")
    return generated


def iter_tokui_llm_generation(
    app: Flask,
    *,
    user_bid: str,
    outline: Any,
    template_payload: dict[str, Any],
    context_payload: dict[str, Any],
    validation_errors: list[dict[str, Any]] | None = None,
    conversation_messages: list[dict[str, str]] | None = None,
    generation_name: str,
):
    if _is_e2e_controlled_tokui(template_payload):
        yield {
            "type": "final",
            "generated": _build_e2e_controlled_tokui_generation(
                template_payload=template_payload,
                context_payload=context_payload,
                generation_name=generation_name,
            ),
        }
        return

    model, temperature = _resolve_generation_settings(template_payload, outline)
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
        if conversation_messages:
            chunks = chat_llm(
                app,
                user_bid,
                span,
                model=model,
                messages=conversation_messages,
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
        else:
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
        response_chunks: list[str] = []
        for chunk in chunks:
            text = chunk.result or ""
            if not text:
                continue
            response_chunks.append(text)
            yield {"type": "text", "text": text}
        response_text = "".join(response_chunks)
        yield {"type": "final", "generated": build_generation_payload(response_text)}
    finally:
        if trace is not None:
            finalize_langfuse_trace(
                trace=trace,
                root_span=span,
                root_span_payload={"output": generation_name},
            )


def _invoke_guidance_llm(
    app: Flask,
    *,
    user_bid: str,
    outline: Any,
    template_payload: dict[str, Any],
    context_payload: dict[str, Any],
) -> str:
    if _is_e2e_controlled_tokui(template_payload):
        return _build_e2e_controlled_guidance()

    model, temperature = _resolve_generation_settings(template_payload, outline)
    prompt = _build_guidance_prompt(
        template_payload=template_payload,
        context_payload=context_payload,
    )
    trace = None
    span = None
    try:
        trace, span = create_trace_with_root_span(
            client=get_langfuse_client(),
            trace_payload={
                "name": "tokui_teacher_guidance",
                "user_id": user_bid,
                "metadata": {
                    "shifu_bid": outline.shifu_bid,
                    "outline_item_bid": outline.outline_item_bid,
                },
            },
            root_span_payload={
                "name": "tokui_teacher_guidance",
                "input": context_payload,
            },
        )
        chunks = invoke_llm(
            app,
            user_bid,
            span,
            model=model,
            message=prompt,
            json=True,
            stream=True,
            generation_name="tokui_teacher_guidance",
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
        parsed = extract_json_object(response_text)
        guidance = str(parsed.get("prompt_template") or "").strip()
        if not guidance:
            raise_error("server.shifu.tokuiGuidanceGenerationFailed")
        return guidance
    finally:
        if trace is not None:
            finalize_langfuse_trace(
                trace=trace,
                root_span=span,
                root_span_payload={"output": "tokui_teacher_guidance"},
            )


def generate_teacher_tokui_guidance(
    app: Flask, user_bid: str, shifu_bid: str, outline_bid: str, payload: dict[str, Any]
) -> dict[str, Any]:
    with app.app_context():
        template = save_draft_tokui_template(
            app, user_bid, shifu_bid, outline_bid, payload
        )
        outline = _latest_draft_outline(shifu_bid, outline_bid)
        template_row = _active_draft_template(shifu_bid, outline_bid)
        if template_row is None:
            raise_error("server.shifu.outlineItemNotFound")

        context_payload = {
            "mode": "teacher_guidance_authoring",
            "course": {"shifu_bid": shifu_bid},
            "outline": {"outline_item_bid": outline_bid, "title": outline.title},
            "teacher_material_refs": template.get("material_refs") or [],
            "teacher_media_refs": template.get("media_refs") or [],
            "teacher_interaction_points": template.get("interaction_points") or [],
        }
        guidance = _invoke_guidance_llm(
            app,
            user_bid=user_bid,
            outline=outline,
            template_payload=template,
            context_payload=context_payload,
        )

        template_row.prompt_template = guidance
        template_row.template_hash = template_hash(
            {
                **template,
                "prompt_template": guidance,
            }
        )
        template_row.updated_user_bid = user_bid
        template_row.updated_at = now_utc()
        db.session.commit()
        return _serialize_template(template_row)


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
            "teacher_material_refs": template.get("material_refs") or [],
            "teacher_media_refs": template.get("media_refs") or [],
            "teacher_interaction_points": template.get("interaction_points") or [],
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
