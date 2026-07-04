from __future__ import annotations

from typing import Any

from flask import Flask

from flaskr.dao import db
from flaskr.i18n import _
from flaskr.service.common import raise_error, raise_param_error
from flaskr.service.learn.models import (
    LearnProgressRecord,
    LearnTokuiArtifact,
    LearnTokuiResponse,
)
from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS, LEARN_STATUS_RESET
from flaskr.service.shifu.models import PublishedOutlineItem, PublishedTokuiTemplate
from flaskr.service.shifu.shifu_tokui_funcs import _invoke_tokui_llm
from flaskr.service.tokui.common import (
    TOKUI_STATUS_FAILED,
    TOKUI_STATUS_FALLBACK,
    TOKUI_STATUS_VALIDATED,
    json_dumps,
    json_loads,
    schema_hash,
    stable_hash,
)
from flaskr.service.tokui.validator import validate_tokui_dsl
from flaskr.util import generate_id
from flaskr.util.datetime import now_utc


TOKUI_FALLBACK_KEY = "server.learn.tokuiFallback"


def _latest_published_template(
    shifu_bid: str, outline_bid: str
) -> PublishedTokuiTemplate | None:
    return (
        PublishedTokuiTemplate.query.filter(
            PublishedTokuiTemplate.shifu_bid == shifu_bid,
            PublishedTokuiTemplate.outline_item_bid == outline_bid,
            PublishedTokuiTemplate.deleted == 0,
        )
        .order_by(PublishedTokuiTemplate.id.desc())
        .first()
    )


def _latest_published_outline(
    shifu_bid: str, outline_bid: str
) -> PublishedOutlineItem | None:
    return (
        PublishedOutlineItem.query.filter(
            PublishedOutlineItem.shifu_bid == shifu_bid,
            PublishedOutlineItem.outline_item_bid == outline_bid,
            PublishedOutlineItem.deleted == 0,
        )
        .order_by(PublishedOutlineItem.id.desc())
        .first()
    )


def _ensure_progress_record(
    app: Flask, shifu_bid: str, outline_bid: str, user_bid: str
) -> LearnProgressRecord:
    record = (
        LearnProgressRecord.query.filter(
            LearnProgressRecord.user_bid == user_bid,
            LearnProgressRecord.shifu_bid == shifu_bid,
            LearnProgressRecord.outline_item_bid == outline_bid,
            LearnProgressRecord.deleted == 0,
            LearnProgressRecord.status != LEARN_STATUS_RESET,
        )
        .order_by(LearnProgressRecord.id.desc())
        .first()
    )
    if record:
        return record
    record = LearnProgressRecord()
    record.progress_record_bid = generate_id(app)
    record.user_bid = user_bid
    record.shifu_bid = shifu_bid
    record.outline_item_bid = outline_bid
    record.status = LEARN_STATUS_IN_PROGRESS
    record.block_position = 0
    db.session.add(record)
    db.session.commit()
    return record


def _template_to_generation_payload(template: PublishedTokuiTemplate) -> dict[str, Any]:
    return {
        "teacher_intent": template.teacher_intent or "",
        "prompt_template": template.prompt_template or "",
        "concept": template.concept or "",
        "audience": template.audience or "",
        "material_refs": json_loads(template.material_refs, []),
        "media_refs": json_loads(template.media_refs, []),
        "generation_options": json_loads(template.generation_options, {}),
        "context_policy": json_loads(template.context_policy, {}),
    }


def _load_existing_responses(
    user_bid: str, shifu_bid: str, outline_bid: str
) -> list[dict[str, Any]]:
    rows = (
        LearnTokuiResponse.query.filter(
            LearnTokuiResponse.user_bid == user_bid,
            LearnTokuiResponse.shifu_bid == shifu_bid,
            LearnTokuiResponse.outline_item_bid == outline_bid,
            LearnTokuiResponse.deleted == 0,
        )
        .order_by(LearnTokuiResponse.id.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "field_id": row.field_id,
            "field_type": row.field_type,
            "field_label": row.field_label,
            "value": json_loads(row.value_json, {}),
        }
        for row in rows
    ]


def _build_learner_context(
    *,
    user_bid: str,
    shifu_bid: str,
    outline: PublishedOutlineItem,
    progress_record: LearnProgressRecord,
    template: PublishedTokuiTemplate,
) -> dict[str, Any]:
    return {
        "mode": "learner_runtime",
        "user": {"user_bid": user_bid},
        "course": {"shifu_bid": shifu_bid},
        "outline": {
            "outline_item_bid": outline.outline_item_bid,
            "title": outline.title,
            "position": outline.position,
        },
        "learning_progress": {
            "progress_record_bid": progress_record.progress_record_bid,
            "status": progress_record.status,
            "block_position": progress_record.block_position,
        },
        "teacher_material_refs": json_loads(template.material_refs, []),
        "teacher_media_refs": json_loads(template.media_refs, []),
        "tokui_responses": _load_existing_responses(
            user_bid, shifu_bid, outline.outline_item_bid
        ),
    }


def _artifact_to_dict(artifact: LearnTokuiArtifact) -> dict[str, Any]:
    return {
        "tokui_artifact_bid": artifact.tokui_artifact_bid,
        "published_template_bid": artifact.published_template_bid,
        "template_hash": artifact.template_hash,
        "schema_hash": schema_hash(json_loads(artifact.interaction_schema, [])),
        "shifu_bid": artifact.shifu_bid,
        "outline_item_bid": artifact.outline_item_bid,
        "progress_record_bid": artifact.progress_record_bid,
        "dsl": artifact.dsl,
        "interaction_schema": json_loads(artifact.interaction_schema, []),
        "generation_status": artifact.generation_status,
        "validation_status": artifact.validation_status,
        "validation_error": json_loads(artifact.validation_error, []),
        "parser_version": artifact.parser_version,
        "fallback_text": artifact.fallback_text,
    }


def _find_reusable_artifact(
    *,
    user_bid: str,
    progress_record_bid: str,
    template_hash_value: str,
) -> LearnTokuiArtifact | None:
    return (
        LearnTokuiArtifact.query.filter(
            LearnTokuiArtifact.user_bid == user_bid,
            LearnTokuiArtifact.progress_record_bid == progress_record_bid,
            LearnTokuiArtifact.template_hash == template_hash_value,
            LearnTokuiArtifact.deleted == 0,
            LearnTokuiArtifact.validation_status == TOKUI_STATUS_VALIDATED,
        )
        .order_by(LearnTokuiArtifact.id.desc())
        .first()
    )


def get_or_generate_tokui_artifact(
    app: Flask,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    *,
    force_regenerate: bool = False,
) -> dict[str, Any]:
    with app.app_context():
        template = _latest_published_template(shifu_bid, outline_bid)
        if not template:
            return {"enabled": False}
        outline = _latest_published_outline(shifu_bid, outline_bid)
        if not outline:
            raise_error("server.shifu.outlineItemNotFound")
        progress_record = _ensure_progress_record(app, shifu_bid, outline_bid, user_bid)
        if not force_regenerate:
            reusable = _find_reusable_artifact(
                user_bid=user_bid,
                progress_record_bid=progress_record.progress_record_bid,
                template_hash_value=template.template_hash,
            )
            if reusable:
                result = _artifact_to_dict(reusable)
                result["enabled"] = True
                result["reused"] = True
                return result

        context_payload = _build_learner_context(
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline=outline,
            progress_record=progress_record,
            template=template,
        )
        context_hash = stable_hash(context_payload)
        generation_payload = _template_to_generation_payload(template)
        repair_attempted = False
        generated: dict[str, Any] = {"dsl": "", "interaction_schema": []}
        validation_errors: list[dict[str, Any]] = []
        parser_version = ""
        validation_ok = False
        try:
            generated = _invoke_tokui_llm(
                app,
                user_bid=user_bid,
                outline=outline,
                template_payload=generation_payload,
                context_payload=context_payload,
                generation_name="tokui_learner_runtime",
            )
            validation = validate_tokui_dsl(app, generated["dsl"])
            parser_version = validation.parser_version
            validation_ok = validation.ok
            validation_errors = [error.to_dict() for error in validation.errors]
            if not validation.ok:
                repair_attempted = True
                generated = _invoke_tokui_llm(
                    app,
                    user_bid=user_bid,
                    outline=outline,
                    template_payload=generation_payload,
                    context_payload=context_payload,
                    validation_errors=validation_errors,
                    generation_name="tokui_learner_runtime_repair",
                )
                validation = validate_tokui_dsl(app, generated["dsl"])
                parser_version = validation.parser_version
                validation_ok = validation.ok
                validation_errors = [error.to_dict() for error in validation.errors]
        except Exception as exc:
            app.logger.exception("TokUI learner runtime generation failed")
            validation_errors = [
                {
                    "message": str(exc) or exc.__class__.__name__,
                    "code": exc.__class__.__name__,
                }
            ]

        artifact = LearnTokuiArtifact()
        artifact.tokui_artifact_bid = generate_id(app)
        artifact.published_template_bid = template.published_template_bid
        artifact.template_hash = template.template_hash
        artifact.shifu_bid = shifu_bid
        artifact.outline_item_bid = outline_bid
        artifact.progress_record_bid = progress_record.progress_record_bid
        artifact.user_bid = user_bid
        artifact.context_hash = context_hash
        artifact.dsl = generated["dsl"] if validation_ok else ""
        artifact.interaction_schema = json_dumps(
            generated["interaction_schema"] if validation_ok else [], []
        )
        artifact.generation_status = (
            TOKUI_STATUS_VALIDATED if validation_ok else TOKUI_STATUS_FALLBACK
        )
        artifact.validation_status = (
            TOKUI_STATUS_VALIDATED if validation_ok else TOKUI_STATUS_FAILED
        )
        artifact.validation_error = json_dumps(validation_errors, [])
        artifact.parser_version = parser_version
        artifact.repair_attempted = 1 if repair_attempted else 0
        artifact.fallback_text = "" if validation_ok else _(TOKUI_FALLBACK_KEY)
        db.session.add(artifact)
        db.session.commit()
        result = _artifact_to_dict(artifact)
        result["enabled"] = True
        result["reused"] = False
        result["repair_attempted"] = repair_attempted
        return result


def save_tokui_responses(
    app: Flask,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    with app.app_context():
        artifact_bid = str(payload.get("tokui_artifact_bid") or "").strip()
        if not artifact_bid:
            raise_param_error("tokui_artifact_bid")
        responses = payload.get("responses")
        if not isinstance(responses, list):
            raise_param_error("responses")
        artifact = (
            LearnTokuiArtifact.query.filter(
                LearnTokuiArtifact.tokui_artifact_bid == artifact_bid,
                LearnTokuiArtifact.shifu_bid == shifu_bid,
                LearnTokuiArtifact.outline_item_bid == outline_bid,
                LearnTokuiArtifact.user_bid == user_bid,
                LearnTokuiArtifact.deleted == 0,
            )
            .order_by(LearnTokuiArtifact.id.desc())
            .first()
        )
        if not artifact:
            raise_param_error("tokui_artifact_bid")
        interaction_schema = json_loads(artifact.interaction_schema, [])
        schema_by_id = {
            str(item.get("field_id") or ""): item
            for item in interaction_schema
            if isinstance(item, dict)
        }
        current_schema_hash = schema_hash(interaction_schema)
        saved = 0
        continue_fields: list[str] = []
        for response in responses:
            if not isinstance(response, dict):
                continue
            field_id = str(response.get("field_id") or "").strip()
            if not field_id:
                continue
            field_schema = schema_by_id.get(field_id, {})
            if field_schema.get("blocking") or field_schema.get("continue_on_submit"):
                continue_fields.append(field_id)
            LearnTokuiResponse.query.filter(
                LearnTokuiResponse.tokui_artifact_bid == artifact.tokui_artifact_bid,
                LearnTokuiResponse.field_id == field_id,
                LearnTokuiResponse.user_bid == user_bid,
                LearnTokuiResponse.deleted == 0,
            ).update({"deleted": 1}, synchronize_session=False)
            row = LearnTokuiResponse()
            row.tokui_response_bid = generate_id(app)
            row.tokui_artifact_bid = artifact.tokui_artifact_bid
            row.published_template_bid = artifact.published_template_bid
            row.template_hash = artifact.template_hash
            row.schema_hash = current_schema_hash
            row.shifu_bid = shifu_bid
            row.outline_item_bid = outline_bid
            row.progress_record_bid = artifact.progress_record_bid
            row.user_bid = user_bid
            row.field_id = field_id
            row.field_type = str(
                response.get("field_type") or field_schema.get("field_type") or ""
            )
            row.field_label = str(field_schema.get("label") or response.get("label") or "")
            row.value_json = json_dumps(response.get("value"), {})
            row.submitted_at = now_utc()
            db.session.add(row)
            saved += 1
        continue_required = bool(continue_fields)
        if continue_required:
            LearnTokuiArtifact.query.filter(
                LearnTokuiArtifact.user_bid == user_bid,
                LearnTokuiArtifact.progress_record_bid == artifact.progress_record_bid,
                LearnTokuiArtifact.template_hash == artifact.template_hash,
                LearnTokuiArtifact.deleted == 0,
                LearnTokuiArtifact.validation_status == TOKUI_STATUS_VALIDATED,
            ).update(
                {"deleted": 1, "updated_at": now_utc()},
                synchronize_session=False,
            )
        db.session.commit()
        return {
            "saved": saved,
            "schema_hash": current_schema_hash,
            "continue_required": continue_required,
            "continue_fields": continue_fields,
        }
