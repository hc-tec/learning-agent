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
    normalize_interaction_points,
    normalize_material_refs,
    schema_hash,
    stable_hash,
)
from flaskr.service.tokui.validator import validate_tokui_dsl
from flaskr.util import generate_id
from flaskr.util.datetime import now_utc


TOKUI_FALLBACK_KEY = "server.learn.tokuiFallback"

CONTINUATION_FEEDBACK_TERMS = (
    "回答正确",
    "判断正确",
    "答得对",
    "很准确",
    "理解得很到位",
    "存在误区",
    "这里有误区",
    "不属于",
    "不是高铁",
    "回答不够具体",
    "还不够具体",
    "含糊",
    "太笼统",
    "比较笼统",
    "答非所问",
    "先回到问题",
    "回到原问题",
    "有点跑题",
    "与问题无关",
    "和问题无关",
    "问题无关",
    "correct",
    "incorrect",
    "vague",
    "incomplete",
    "off-topic",
)


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
    generation_options = json_loads(template.generation_options, {})
    interaction_points = normalize_interaction_points(
        generation_options.get("interaction_points")
    )
    return {
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
        "context_policy": json_loads(template.context_policy, {}),
    }


def _response_to_dict(row: LearnTokuiResponse) -> dict[str, Any]:
    return {
        "tokui_response_bid": row.tokui_response_bid,
        "tokui_artifact_bid": row.tokui_artifact_bid,
        "field_id": row.field_id,
        "field_type": row.field_type,
        "field_label": row.field_label,
        "value": json_loads(row.value_json, {}),
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
    return [_response_to_dict(row) for row in rows]


def _load_responses_by_artifact(
    *, user_bid: str, artifact_bids: list[str]
) -> dict[str, list[dict[str, Any]]]:
    if not artifact_bids:
        return {}
    rows = (
        LearnTokuiResponse.query.filter(
            LearnTokuiResponse.user_bid == user_bid,
            LearnTokuiResponse.tokui_artifact_bid.in_(artifact_bids),
            LearnTokuiResponse.deleted == 0,
        )
        .order_by(LearnTokuiResponse.id.asc())
        .all()
    )
    responses_by_artifact: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        responses_by_artifact.setdefault(row.tokui_artifact_bid, []).append(
            _response_to_dict(row)
        )
    return responses_by_artifact


def _continue_field_ids(interaction_schema: list[Any]) -> set[str]:
    return {
        str(item.get("field_id") or "").strip()
        for item in interaction_schema
        if isinstance(item, dict)
        and (item.get("blocking") or item.get("continue_on_submit"))
        and str(item.get("field_id") or "").strip()
    }


def _response_field_ids(responses: list[Any]) -> set[str]:
    return {
        str(response.get("field_id") or "").strip()
        for response in responses
        if isinstance(response, dict) and str(response.get("field_id") or "").strip()
    }


def _has_continue_response_values(
    interaction_schema: list[Any], responses: list[Any]
) -> bool:
    continue_field_ids = _continue_field_ids(interaction_schema)
    if not continue_field_ids:
        return False
    return bool(continue_field_ids & _response_field_ids(responses))


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
        "teacher_material_refs": normalize_material_refs(
            json_loads(template.material_refs, [])
        ),
        "teacher_media_refs": json_loads(template.media_refs, []),
        "teacher_interaction_points": normalize_interaction_points(
            json_loads(template.generation_options, {}).get("interaction_points")
        ),
        "tokui_responses": _load_existing_responses(
            user_bid, shifu_bid, outline.outline_item_bid
        ),
    }


def _continuation_contract_errors(
    generated: dict[str, Any], context_payload: dict[str, Any]
) -> list[dict[str, Any]]:
    responses = context_payload.get("tokui_responses") or []
    if not isinstance(responses, list) or not responses:
        return []
    answered_field_ids = {
        str(response.get("field_id") or "").strip()
        for response in responses
        if isinstance(response, dict)
    }
    answered_field_ids.discard("")
    if not answered_field_ids:
        return []
    interaction_schema = generated.get("interaction_schema") or []
    if not isinstance(interaction_schema, list):
        return []
    errors: list[dict[str, Any]] = []
    dsl = str(generated.get("dsl") or "")
    feedback_prefix = dsl[:600]
    if not any(term in feedback_prefix for term in CONTINUATION_FEEDBACK_TERMS):
        errors.append(
            {
                "message": (
                    "Continuation output did not provide explicit answer-quality "
                    "feedback. Start the continuation with a feedback block using "
                    "回答正确, 存在误区, 回答不够具体, or 答非所问 before any new teaching."
                ),
                "code": "TokuiContinuationMissingAnswerFeedback",
            }
        )
    repeated_field_ids = sorted(
        {
            str(field.get("field_id") or "").strip()
            for field in interaction_schema
            if isinstance(field, dict)
            and str(field.get("field_id") or "").strip() in answered_field_ids
        }
    )
    if repeated_field_ids:
        errors.append(
            {
                "message": (
                    "Continuation output repeated already answered learner fields. "
                    "Generate only the next feedback/continuation block and do not "
                    "ask the same checkpoint again."
                ),
                "code": "TokuiContinuationRepeatedAnsweredFields",
                "field_ids": repeated_field_ids,
            }
        )
    return errors


def _artifact_to_dict(
    artifact: LearnTokuiArtifact,
    responses_by_artifact: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    submitted_responses = (
        responses_by_artifact or {}
    ).get(artifact.tokui_artifact_bid, [])
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
        "submitted_responses": submitted_responses,
        "submitted": bool(submitted_responses),
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


def _has_newer_artifact(artifact: LearnTokuiArtifact) -> bool:
    return (
        LearnTokuiArtifact.query.filter(
            LearnTokuiArtifact.user_bid == artifact.user_bid,
            LearnTokuiArtifact.progress_record_bid == artifact.progress_record_bid,
            LearnTokuiArtifact.template_hash == artifact.template_hash,
            LearnTokuiArtifact.deleted == 0,
            LearnTokuiArtifact.id > artifact.id,
        )
        .order_by(LearnTokuiArtifact.id.asc())
        .first()
        is not None
    )


def _artifact_has_saved_continue_response(artifact: LearnTokuiArtifact) -> bool:
    continue_field_ids = _continue_field_ids(json_loads(artifact.interaction_schema, []))
    if not continue_field_ids:
        return False
    return (
        LearnTokuiResponse.query.filter(
            LearnTokuiResponse.user_bid == artifact.user_bid,
            LearnTokuiResponse.tokui_artifact_bid == artifact.tokui_artifact_bid,
            LearnTokuiResponse.field_id.in_(continue_field_ids),
            LearnTokuiResponse.deleted == 0,
        )
        .order_by(LearnTokuiResponse.id.desc())
        .first()
        is not None
    )


def _should_reuse_artifact(artifact: LearnTokuiArtifact) -> bool:
    if not _artifact_has_saved_continue_response(artifact):
        return True
    return _has_newer_artifact(artifact)


def _filter_artifacts_for_chain(
    artifacts: list[LearnTokuiArtifact],
) -> list[LearnTokuiArtifact]:
    if not artifacts:
        return []
    last_artifact_bid = artifacts[-1].tokui_artifact_bid
    return [
        artifact
        for artifact in artifacts
        if artifact.validation_status == TOKUI_STATUS_VALIDATED
        or artifact.tokui_artifact_bid == last_artifact_bid
    ]


def _load_artifact_chain(
    *,
    user_bid: str,
    progress_record_bid: str,
    template_hash_value: str,
    include_failed_artifact: LearnTokuiArtifact | None = None,
) -> list[dict[str, Any]]:
    artifacts = (
        LearnTokuiArtifact.query.filter(
            LearnTokuiArtifact.user_bid == user_bid,
            LearnTokuiArtifact.progress_record_bid == progress_record_bid,
            LearnTokuiArtifact.template_hash == template_hash_value,
            LearnTokuiArtifact.deleted == 0,
        )
        .order_by(LearnTokuiArtifact.id.asc())
        .all()
    )
    if include_failed_artifact and all(
        item.tokui_artifact_bid != include_failed_artifact.tokui_artifact_bid
        for item in artifacts
    ):
        artifacts.append(include_failed_artifact)
    artifacts = _filter_artifacts_for_chain(artifacts)
    artifact_bids = [artifact.tokui_artifact_bid for artifact in artifacts]
    responses_by_artifact = _load_responses_by_artifact(
        user_bid=user_bid, artifact_bids=artifact_bids
    )
    return [_artifact_to_dict(artifact, responses_by_artifact) for artifact in artifacts]


def _attach_artifact_chain(
    result: dict[str, Any],
    *,
    user_bid: str,
    progress_record_bid: str,
    template_hash_value: str,
    include_failed_artifact: LearnTokuiArtifact | None = None,
) -> dict[str, Any]:
    result["artifact_chain"] = _load_artifact_chain(
        user_bid=user_bid,
        progress_record_bid=progress_record_bid,
        template_hash_value=template_hash_value,
        include_failed_artifact=include_failed_artifact,
    )
    return result


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
                if _should_reuse_artifact(reusable):
                    result = _artifact_to_dict(reusable)
                    result["enabled"] = True
                    result["reused"] = True
                    return _attach_artifact_chain(
                        result,
                        user_bid=user_bid,
                        progress_record_bid=progress_record.progress_record_bid,
                        template_hash_value=template.template_hash,
                    )

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
            validation_errors = [error.to_dict() for error in validation.errors]
            contract_errors = _continuation_contract_errors(
                generated, context_payload
            )
            validation_errors.extend(contract_errors)
            validation_ok = validation.ok and not contract_errors
            if not validation_ok:
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
                validation_errors = [error.to_dict() for error in validation.errors]
                contract_errors = _continuation_contract_errors(
                    generated, context_payload
                )
                validation_errors.extend(contract_errors)
                validation_ok = validation.ok and not contract_errors
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
        return _attach_artifact_chain(
            result,
            user_bid=user_bid,
            progress_record_bid=progress_record.progress_record_bid,
            template_hash_value=template.template_hash,
            include_failed_artifact=artifact
            if artifact.validation_status != TOKUI_STATUS_VALIDATED
            else None,
        )


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
        db.session.commit()
        return {
            "saved": saved,
            "schema_hash": current_schema_hash,
            "continue_required": continue_required,
            "continue_fields": continue_fields,
        }
