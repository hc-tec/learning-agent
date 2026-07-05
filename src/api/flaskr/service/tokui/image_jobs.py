from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from flask import Flask

from flaskr.api.langfuse import (
    create_trace_with_root_span,
    finalize_langfuse_trace,
    get_langfuse_client,
)
from flaskr.api.llm import invoke_llm
from flaskr.dao import db
from flaskr.service.check_risk.funcs import check_text_with_risk_control
from flaskr.service.common import raise_error, raise_param_error
from flaskr.service.config import get_config
from flaskr.service.config.funcs import add_config
from flaskr.service.metering import UsageContext
from flaskr.service.metering.consts import BILL_USAGE_SCENE_DEBUG
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftTokuiTemplate,
    TokuiImageGenerationCandidate,
    TokuiImageGenerationJob,
)
from flaskr.service.tokui.common import (
    extract_json_object,
    json_dumps,
    normalize_media_refs,
)
from flaskr.service.tokui.image_generation import (
    TokuiImageProviderConfig,
    _store_generated_image,
    get_tokui_image_provider_config,
    request_generated_image,
)
from flaskr.util import generate_id


JOB_STATUS_QUEUED = "queued"
JOB_STATUS_OPTIMIZING_PROMPT = "optimizing_prompt"
JOB_STATUS_GENERATING_IMAGES = "generating_images"
JOB_STATUS_AWAITING_SELECTION = "awaiting_selection"
JOB_STATUS_SELECTED = "selected"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_CANCELED = "canceled"

CANDIDATE_STATUS_QUEUED = "queued"
CANDIDATE_STATUS_GENERATING = "generating"
CANDIDATE_STATUS_SUCCEEDED = "succeeded"
CANDIDATE_STATUS_FAILED = "failed"

PROMPT_STATUS_PENDING = "pending"
PROMPT_STATUS_OPTIMIZING = "optimizing"
PROMPT_STATUS_SUCCEEDED = "succeeded"
PROMPT_STATUS_FAILED = "failed"

TOKUI_IMAGE_CONFIG_KEYS = {
    "api_base_url": "TOKUI_IMAGE_API_BASE_URL",
    "api_key": "TOKUI_IMAGE_API_KEY",
    "model": "TOKUI_IMAGE_MODEL",
    "timeout_seconds": "TOKUI_IMAGE_TIMEOUT_SECONDS",
    "size": "TOKUI_IMAGE_SIZE",
    "default_candidate_count": "TOKUI_IMAGE_DEFAULT_CANDIDATE_COUNT",
    "prompt_optimizer_enabled": "TOKUI_IMAGE_PROMPT_OPTIMIZER_ENABLED",
    "prompt_optimizer_model": "TOKUI_IMAGE_PROMPT_OPTIMIZER_MODEL",
    "prompt_optimizer_temperature": "TOKUI_IMAGE_PROMPT_OPTIMIZER_TEMPERATURE",
    "prompt_optimizer_system_prompt": "TOKUI_IMAGE_PROMPT_OPTIMIZER_SYSTEM_PROMPT",
}

DEFAULT_PROMPT_OPTIMIZER_SYSTEM_PROMPT = """
你是教学产品里的图像提示词优化器。你的任务是把老师输入的教学图像意图，
优化成适合图像生成模型的清晰提示词。

要求：
- 保持老师输入的主要语言，不要强制翻译。
- 面向课堂教学示意图，而不是风景图、装饰图或营销海报。
- 明确图像主体、结构关系、箭头、标签、背景、风格和禁忌。
- 如果老师描述专业概念，优先生成白底、清晰标签、流程/结构/关系示意图。
- 不要编造老师没有要求的品牌、人物或无关场景。

只返回 JSON：
{
  "optimized_prompt": "优化后的图像生成提示词"
}
""".strip()

_JOB_EXECUTOR = ThreadPoolExecutor(max_workers=4)


@dataclass(frozen=True)
class TokuiImageJobConfig:
    provider: TokuiImageProviderConfig
    candidate_count: int
    prompt_optimizer_enabled: bool
    prompt_optimizer_model: str
    prompt_optimizer_temperature: float
    prompt_optimizer_system_prompt: str


def _coerce_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    return default


def _coerce_positive_int(value: Any, default: int, *, minimum: int = 1, maximum: int = 6) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_tokui_image_job_config() -> TokuiImageJobConfig:
    provider = get_tokui_image_provider_config()
    candidate_count = _coerce_positive_int(
        get_config("TOKUI_IMAGE_DEFAULT_CANDIDATE_COUNT", 3),
        3,
        minimum=1,
        maximum=6,
    )
    optimizer_enabled = _coerce_bool(
        get_config("TOKUI_IMAGE_PROMPT_OPTIMIZER_ENABLED", True),
        True,
    )
    optimizer_model = str(
        get_config("TOKUI_IMAGE_PROMPT_OPTIMIZER_MODEL", "") or ""
    ).strip()
    optimizer_temperature = _coerce_float(
        get_config("TOKUI_IMAGE_PROMPT_OPTIMIZER_TEMPERATURE", 0.2),
        0.2,
    )
    optimizer_prompt = str(
        get_config(
            "TOKUI_IMAGE_PROMPT_OPTIMIZER_SYSTEM_PROMPT",
            DEFAULT_PROMPT_OPTIMIZER_SYSTEM_PROMPT,
        )
        or DEFAULT_PROMPT_OPTIMIZER_SYSTEM_PROMPT
    ).strip()
    return TokuiImageJobConfig(
        provider=provider,
        candidate_count=candidate_count,
        prompt_optimizer_enabled=optimizer_enabled,
        prompt_optimizer_model=optimizer_model,
        prompt_optimizer_temperature=optimizer_temperature,
        prompt_optimizer_system_prompt=optimizer_prompt
        or DEFAULT_PROMPT_OPTIMIZER_SYSTEM_PROMPT,
    )


def get_operator_tokui_image_config() -> dict[str, Any]:
    return {
        "api_base_url": str(get_config("TOKUI_IMAGE_API_BASE_URL", "") or ""),
        "api_key_configured": bool(str(get_config("TOKUI_IMAGE_API_KEY", "") or "")),
        "model": str(get_config("TOKUI_IMAGE_MODEL", "gpt-image-2") or ""),
        "timeout_seconds": _coerce_positive_int(
            get_config("TOKUI_IMAGE_TIMEOUT_SECONDS", 120),
            120,
            minimum=1,
            maximum=900,
        ),
        "size": str(get_config("TOKUI_IMAGE_SIZE", "1024x1024") or "1024x1024"),
        "default_candidate_count": _coerce_positive_int(
            get_config("TOKUI_IMAGE_DEFAULT_CANDIDATE_COUNT", 3),
            3,
            minimum=1,
            maximum=6,
        ),
        "prompt_optimizer_enabled": _coerce_bool(
            get_config("TOKUI_IMAGE_PROMPT_OPTIMIZER_ENABLED", True),
            True,
        ),
        "prompt_optimizer_model": str(
            get_config("TOKUI_IMAGE_PROMPT_OPTIMIZER_MODEL", "") or ""
        ),
        "prompt_optimizer_temperature": _coerce_float(
            get_config("TOKUI_IMAGE_PROMPT_OPTIMIZER_TEMPERATURE", 0.2),
            0.2,
        ),
        "prompt_optimizer_system_prompt": str(
            get_config(
                "TOKUI_IMAGE_PROMPT_OPTIMIZER_SYSTEM_PROMPT",
                DEFAULT_PROMPT_OPTIMIZER_SYSTEM_PROMPT,
            )
            or DEFAULT_PROMPT_OPTIMIZER_SYSTEM_PROMPT
        ),
    }


def update_operator_tokui_image_config(
    app: Flask, user_bid: str, payload: dict[str, Any]
) -> dict[str, Any]:
    for field, key in TOKUI_IMAGE_CONFIG_KEYS.items():
        if field not in payload:
            continue
        if field == "api_key":
            raw_value = str(payload.get(field) or "").strip()
            if not raw_value:
                continue
            add_config(app, key, raw_value, is_secret=True, updated_by=user_bid)
            continue
        raw_value = payload.get(field)
        if isinstance(raw_value, bool):
            value = "true" if raw_value else "false"
        else:
            value = str(raw_value if raw_value is not None else "").strip()
        add_config(app, key, value, is_secret=False, updated_by=user_bid)
    return get_operator_tokui_image_config()


def _serialize_candidate(candidate: TokuiImageGenerationCandidate) -> dict[str, Any]:
    return {
        "candidate_bid": candidate.candidate_bid or "",
        "job_bid": candidate.job_bid or "",
        "candidate_index": int(candidate.candidate_index or 0),
        "status": candidate.status or CANDIDATE_STATUS_QUEUED,
        "resource_id": candidate.resource_id or "",
        "url": candidate.resource_url or "",
        "type": "image",
        "title": candidate.title or "",
        "description": candidate.description or "",
        "selected": bool(candidate.selected),
        "error_message": candidate.error_message or "",
        "created_at": candidate.created_at.isoformat() if candidate.created_at else "",
        "updated_at": candidate.updated_at.isoformat() if candidate.updated_at else "",
    }


def _serialize_job(job: TokuiImageGenerationJob) -> dict[str, Any]:
    candidates = (
        TokuiImageGenerationCandidate.query.filter(
            TokuiImageGenerationCandidate.job_bid == job.job_bid,
            TokuiImageGenerationCandidate.deleted == 0,
        )
        .order_by(TokuiImageGenerationCandidate.candidate_index.asc())
        .all()
    )
    return {
        "job_bid": job.job_bid or "",
        "retry_of_job_bid": job.retry_of_job_bid or "",
        "shifu_bid": job.shifu_bid or "",
        "outline_item_bid": job.outline_item_bid or "",
        "tokui_template_bid": job.tokui_template_bid or "",
        "status": job.status or JOB_STATUS_QUEUED,
        "teacher_prompt": job.teacher_prompt or "",
        "optimized_prompt": job.optimized_prompt or "",
        "final_provider_prompt": job.final_provider_prompt or "",
        "prompt_optimization_status": job.prompt_optimization_status or PROMPT_STATUS_PENDING,
        "prompt_optimization_error": job.prompt_optimization_error or "",
        "prompt_optimizer_enabled": bool(job.prompt_optimizer_enabled),
        "provider_model": job.provider_model or "",
        "provider_size": job.provider_size or "",
        "candidate_count": int(job.candidate_count or 0),
        "selected_candidate_bid": job.selected_candidate_bid or "",
        "error_message": job.error_message or "",
        "candidates": [_serialize_candidate(candidate) for candidate in candidates],
        "created_at": job.created_at.isoformat() if job.created_at else "",
        "updated_at": job.updated_at.isoformat() if job.updated_at else "",
    }


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


def _load_job(
    shifu_bid: str, outline_bid: str, job_bid: str
) -> TokuiImageGenerationJob:
    job = (
        TokuiImageGenerationJob.query.filter(
            TokuiImageGenerationJob.job_bid == job_bid,
            TokuiImageGenerationJob.shifu_bid == shifu_bid,
            TokuiImageGenerationJob.outline_item_bid == outline_bid,
            TokuiImageGenerationJob.deleted == 0,
        )
        .order_by(TokuiImageGenerationJob.id.desc())
        .first()
    )
    if not job:
        raise_param_error("job_bid")
    return job


def create_tokui_image_generation_job(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    teacher_prompt = str(payload.get("teacher_prompt") or payload.get("prompt") or "").strip()
    if not teacher_prompt:
        raise_param_error("teacher_prompt")

    outline = _latest_draft_outline(shifu_bid, outline_bid)
    check_text_with_risk_control(app, outline_bid, user_bid, teacher_prompt)
    config = get_tokui_image_job_config()
    template = _active_draft_template(shifu_bid, outline_bid)
    requested_count = payload.get("candidate_count")
    candidate_count = (
        _coerce_positive_int(requested_count, config.candidate_count, minimum=1, maximum=6)
        if requested_count is not None
        else config.candidate_count
    )
    size = str(payload.get("size") or config.provider.default_size).strip()
    if not size:
        size = config.provider.default_size
    job = TokuiImageGenerationJob(
        job_bid=generate_id(app),
        retry_of_job_bid=str(payload.get("retry_of_job_bid") or "").strip(),
        shifu_bid=shifu_bid,
        outline_item_bid=outline.outline_item_bid,
        tokui_template_bid=getattr(template, "tokui_template_bid", "") or "",
        created_user_bid=user_bid,
        status=JOB_STATUS_QUEUED,
        teacher_prompt=teacher_prompt,
        prompt_optimization_status=PROMPT_STATUS_PENDING,
        prompt_optimizer_enabled=1 if config.prompt_optimizer_enabled else 0,
        prompt_optimizer_model=config.prompt_optimizer_model,
        prompt_optimizer_temperature=Decimal(str(config.prompt_optimizer_temperature)),
        prompt_optimizer_template_snapshot=config.prompt_optimizer_system_prompt,
        provider_base_url=config.provider.base_url,
        provider_model=config.provider.model,
        provider_size=size,
        provider_timeout_seconds=config.provider.timeout_seconds,
        candidate_count=candidate_count,
    )
    db.session.add(job)
    db.session.commit()
    _JOB_EXECUTOR.submit(_process_job_safely, app, job.job_bid)
    return _serialize_job(job)


def get_tokui_image_generation_job(
    shifu_bid: str, outline_bid: str, job_bid: str
) -> dict[str, Any]:
    return _serialize_job(_load_job(shifu_bid, outline_bid, job_bid))


def get_latest_tokui_image_generation_job(
    shifu_bid: str, outline_bid: str
) -> dict[str, Any]:
    job = (
        TokuiImageGenerationJob.query.filter(
            TokuiImageGenerationJob.shifu_bid == shifu_bid,
            TokuiImageGenerationJob.outline_item_bid == outline_bid,
            TokuiImageGenerationJob.deleted == 0,
        )
        .order_by(TokuiImageGenerationJob.id.desc())
        .first()
    )
    return _serialize_job(job) if job else {}


def _build_optimizer_user_prompt(job: TokuiImageGenerationJob) -> str:
    return json_dumps(
        {
            "teacher_prompt": job.teacher_prompt or "",
            "course_context": {
                "shifu_bid": job.shifu_bid or "",
                "outline_item_bid": job.outline_item_bid or "",
            },
            "output_contract": {
                "optimized_prompt": "string, required",
            },
        },
        {},
    )


def _optimize_prompt(app: Flask, job: TokuiImageGenerationJob) -> str:
    if not str(job.prompt_optimizer_model or "").strip():
        raise_error("server.shifu.tokuiImagePromptOptimizerNotConfigured")
    trace = None
    span = None
    try:
        trace, span = create_trace_with_root_span(
            client=get_langfuse_client(),
            trace_payload={
                "name": "tokui_image_prompt_optimizer",
                "user_id": job.created_user_bid,
                "metadata": {
                    "shifu_bid": job.shifu_bid,
                    "outline_item_bid": job.outline_item_bid,
                    "job_bid": job.job_bid,
                },
            },
            root_span_payload={
                "name": "tokui_image_prompt_optimizer",
                "input": job.teacher_prompt,
            },
        )
        chunks = invoke_llm(
            app,
            job.created_user_bid,
            span,
            model=job.prompt_optimizer_model,
            message=_build_optimizer_user_prompt(job),
            system=job.prompt_optimizer_template_snapshot
            or DEFAULT_PROMPT_OPTIMIZER_SYSTEM_PROMPT,
            json=True,
            stream=True,
            generation_name="tokui_image_prompt_optimizer",
            usage_context=UsageContext(
                user_bid=job.created_user_bid,
                shifu_bid=job.shifu_bid,
                outline_item_bid=job.outline_item_bid,
                usage_scene=BILL_USAGE_SCENE_DEBUG,
            ),
            usage_scene=BILL_USAGE_SCENE_DEBUG,
            temperature=float(job.prompt_optimizer_temperature or 0.2),
        )
        response_text = "".join(chunk.result for chunk in chunks if chunk.result)
        parsed = extract_json_object(response_text)
        optimized_prompt = str(parsed.get("optimized_prompt") or "").strip()
        if not optimized_prompt:
            raise_error("server.shifu.tokuiImagePromptOptimizationFailed")
        return optimized_prompt
    finally:
        if trace is not None:
            finalize_langfuse_trace(
                trace=trace,
                root_span=span,
                root_span_payload={"output": "tokui_image_prompt_optimizer"},
            )


def _mark_job_failed(job_bid: str, message: str) -> None:
    job = TokuiImageGenerationJob.query.filter(
        TokuiImageGenerationJob.job_bid == job_bid,
        TokuiImageGenerationJob.deleted == 0,
    ).first()
    if not job:
        return
    job.status = JOB_STATUS_FAILED
    job.error_message = str(message or "")[:2000]
    db.session.commit()


def _safe_provider_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, list):
        safe_data: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            safe_item = {
                key: value
                for key, value in item.items()
                if key not in {"b64_json", "data_url"}
            }
            if "url" in safe_item:
                safe_item["url"] = str(safe_item["url"])[:500]
            safe_data.append(safe_item)
        return {"data": safe_data}
    return {}


def _generate_candidate(app: Flask, job_bid: str, candidate_bid: str) -> bool:
    with app.app_context():
        candidate = TokuiImageGenerationCandidate.query.filter(
            TokuiImageGenerationCandidate.candidate_bid == candidate_bid,
            TokuiImageGenerationCandidate.job_bid == job_bid,
            TokuiImageGenerationCandidate.deleted == 0,
        ).first()
        job = TokuiImageGenerationJob.query.filter(
            TokuiImageGenerationJob.job_bid == job_bid,
            TokuiImageGenerationJob.deleted == 0,
        ).first()
        if not candidate or not job:
            return False
        candidate.status = CANDIDATE_STATUS_GENERATING
        db.session.commit()
        config = TokuiImageProviderConfig(
            base_url=job.provider_base_url,
            api_key=str(get_config("TOKUI_IMAGE_API_KEY", "") or ""),
            model=job.provider_model,
            timeout_seconds=int(job.provider_timeout_seconds or 120),
            default_size=job.provider_size or "1024x1024",
        )
        try:
            generated_image, provider_payload = request_generated_image(
                app,
                config=config,
                prompt=job.final_provider_prompt,
                size=job.provider_size,
            )
            media_ref = _store_generated_image(
                app,
                user_bid=job.created_user_bid,
                prompt=job.final_provider_prompt,
                title=f"{candidate.title or 'TokUI generated image'} {candidate.candidate_index + 1}",
                generated_image=generated_image,
            )
            candidate.status = CANDIDATE_STATUS_SUCCEEDED
            candidate.resource_id = media_ref["resource_id"]
            candidate.resource_url = media_ref["url"]
            candidate.title = media_ref["title"]
            candidate.description = media_ref["description"]
            candidate.provider_payload_json = json_dumps(
                _safe_provider_payload(provider_payload),
                {},
            )
            candidate.error_message = ""
            db.session.commit()
            return True
        except Exception as exc:
            candidate.status = CANDIDATE_STATUS_FAILED
            candidate.error_message = str(exc)[:2000]
            db.session.commit()
            return False


def _process_job_safely(app: Flask, job_bid: str) -> None:
    try:
        _process_job(app, job_bid)
    except Exception as exc:
        with app.app_context():
            app.logger.exception("TokUI image job failed job_bid=%s", job_bid)
            _mark_job_failed(job_bid, str(exc))


def _process_job(app: Flask, job_bid: str) -> None:
    with app.app_context():
        job = TokuiImageGenerationJob.query.filter(
            TokuiImageGenerationJob.job_bid == job_bid,
            TokuiImageGenerationJob.deleted == 0,
        ).first()
        if not job or job.status == JOB_STATUS_CANCELED:
            return
        job.status = JOB_STATUS_OPTIMIZING_PROMPT
        job.prompt_optimization_status = PROMPT_STATUS_OPTIMIZING
        db.session.commit()
        if bool(job.prompt_optimizer_enabled):
            try:
                optimized_prompt = _optimize_prompt(app, job)
            except Exception as exc:
                job.status = JOB_STATUS_FAILED
                job.prompt_optimization_status = PROMPT_STATUS_FAILED
                job.prompt_optimization_error = str(exc)[:2000]
                job.error_message = str(exc)[:2000]
                db.session.commit()
                return
        else:
            optimized_prompt = job.teacher_prompt or ""

        job.optimized_prompt = optimized_prompt
        job.final_provider_prompt = optimized_prompt
        job.prompt_optimization_status = PROMPT_STATUS_SUCCEEDED
        job.status = JOB_STATUS_GENERATING_IMAGES
        db.session.commit()

        candidates: list[TokuiImageGenerationCandidate] = []
        for index in range(int(job.candidate_count or 1)):
            candidate = TokuiImageGenerationCandidate(
                candidate_bid=generate_id(app),
                job_bid=job.job_bid,
                candidate_index=index,
                status=CANDIDATE_STATUS_QUEUED,
                title="TokUI generated image",
                description=job.final_provider_prompt,
            )
            db.session.add(candidate)
            candidates.append(candidate)
        db.session.commit()

    success_count = 0
    with ThreadPoolExecutor(max_workers=max(1, min(len(candidates), 6))) as executor:
        futures = [
            executor.submit(_generate_candidate, app, job_bid, candidate.candidate_bid)
            for candidate in candidates
        ]
        for future in as_completed(futures):
            if future.result():
                success_count += 1

    with app.app_context():
        job = TokuiImageGenerationJob.query.filter(
            TokuiImageGenerationJob.job_bid == job_bid,
            TokuiImageGenerationJob.deleted == 0,
        ).first()
        if not job:
            return
        if success_count > 0:
            job.status = JOB_STATUS_AWAITING_SELECTION
            job.error_message = ""
        else:
            job.status = JOB_STATUS_FAILED
            job.error_message = "All image candidates failed"
        db.session.commit()


def select_tokui_image_candidate(
    app: Flask,
    *,
    user_bid: str,
    shifu_bid: str,
    outline_bid: str,
    job_bid: str,
    candidate_bid: str,
) -> dict[str, Any]:
    job = _load_job(shifu_bid, outline_bid, job_bid)
    candidate = (
        TokuiImageGenerationCandidate.query.filter(
            TokuiImageGenerationCandidate.candidate_bid == candidate_bid,
            TokuiImageGenerationCandidate.job_bid == job.job_bid,
            TokuiImageGenerationCandidate.deleted == 0,
        )
        .order_by(TokuiImageGenerationCandidate.id.desc())
        .first()
    )
    if not candidate or candidate.status != CANDIDATE_STATUS_SUCCEEDED:
        raise_param_error("candidate_bid")

    media_ref = {
        "resource_id": candidate.resource_id or "",
        "url": candidate.resource_url or "",
        "type": "image",
        "title": candidate.title or "TokUI generated image",
        "description": candidate.description or job.final_provider_prompt or "",
    }
    from flaskr.service.shifu.shifu_tokui_funcs import (
        get_draft_tokui_template,
        save_draft_tokui_template,
    )

    current_template = get_draft_tokui_template(app, shifu_bid, outline_bid)
    media_refs = normalize_media_refs(current_template.get("media_refs") or [])
    media_refs.append(media_ref)
    payload = {
        **current_template,
        "media_refs": media_refs,
    }
    updated_template = save_draft_tokui_template(
        app,
        user_bid,
        shifu_bid,
        outline_bid,
        payload,
    )
    TokuiImageGenerationCandidate.query.filter(
        TokuiImageGenerationCandidate.job_bid == job.job_bid,
        TokuiImageGenerationCandidate.deleted == 0,
    ).update({"selected": 0})
    candidate.selected = 1
    job.selected_candidate_bid = candidate.candidate_bid
    job.status = JOB_STATUS_SELECTED
    db.session.commit()
    return {
        "job": _serialize_job(job),
        "media_ref": media_ref,
        "template": updated_template,
    }
