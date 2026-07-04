from __future__ import annotations

import hashlib
import json
import re
from typing import Any


TOKUI_STATUS_IDLE = "idle"
TOKUI_STATUS_VALIDATED = "validated"
TOKUI_STATUS_FAILED = "failed"
TOKUI_STATUS_FALLBACK = "fallback"


def json_dumps(value: Any, default: Any) -> str:
    if value is None:
        value = default
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def stable_hash(value: Any) -> str:
    normalized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def template_hash(payload: dict[str, Any]) -> str:
    return stable_hash(
        {
            "teacher_intent": payload.get("teacher_intent") or "",
            "prompt_template": payload.get("prompt_template") or "",
            "concept": payload.get("concept") or "",
            "audience": payload.get("audience") or "",
            "material_refs": payload.get("material_refs") or [],
            "media_refs": payload.get("media_refs") or [],
            "generation_options": payload.get("generation_options") or {},
            "context_policy": payload.get("context_policy") or {},
        }
    )


def normalize_media_refs(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, str):
            ref = item.strip()
            if ref:
                normalized.append(
                    {
                        "resource_id": ref,
                        "url": "",
                        "type": "image",
                        "title": "",
                        "description": "",
                    }
                )
            continue
        if not isinstance(item, dict):
            continue
        resource_id = str(
            item.get("resource_id")
            or item.get("resource_bid")
            or item.get("id")
            or ""
        ).strip()
        url = str(item.get("url") or item.get("src") or "").strip()
        if not resource_id and not url:
            continue
        media_type = str(item.get("type") or item.get("media_type") or "image").strip()
        if media_type not in {"image", "video"}:
            media_type = "image"
        normalized.append(
            {
                "resource_id": resource_id,
                "url": url,
                "type": media_type,
                "title": str(item.get("title") or item.get("name") or "").strip(),
                "description": str(item.get("description") or "").strip(),
            }
        )
    return normalized


def schema_hash(interaction_schema: Any) -> str:
    return stable_hash(interaction_schema if isinstance(interaction_schema, list) else [])


def extract_json_object(text: str) -> dict[str, Any]:
    normalized = str(text or "").strip()
    if not normalized:
        return {}

    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", normalized, re.IGNORECASE)
    if fence_match:
        normalized = fence_match.group(1).strip()

    try:
        parsed = json.loads(normalized)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass

    first = normalized.find("{")
    last = normalized.rfind("}")
    if first >= 0 and last > first:
        try:
            parsed = json.loads(normalized[first : last + 1])
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def normalize_interaction_schema(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        field_id = str(item.get("field_id") or item.get("id") or f"field_{index + 1}")
        blocking = bool(item.get("blocking", False))
        continue_on_submit_value = item.get("continue_on_submit")
        continue_on_submit = (
            bool(continue_on_submit_value)
            if continue_on_submit_value is not None
            else blocking
        )
        normalized.append(
            {
                "field_id": field_id,
                "field_type": str(item.get("field_type") or item.get("type") or "text"),
                "label": str(item.get("label") or item.get("field_label") or ""),
                "required": bool(item.get("required", False)),
                "semantic_role": str(item.get("semantic_role") or ""),
                "value_shape": str(item.get("value_shape") or ""),
                "blocking": blocking,
                "continue_on_submit": continue_on_submit,
                "continuation_hint": str(item.get("continuation_hint") or ""),
            }
        )
    return normalized


def build_generation_payload(raw_text: str) -> dict[str, Any]:
    parsed = extract_json_object(raw_text)
    dsl = str(parsed.get("dsl") or parsed.get("tokui_dsl") or "").strip()
    interaction_schema = normalize_interaction_schema(parsed.get("interaction_schema"))
    media_refs = parsed.get("media_refs")
    if not isinstance(media_refs, list):
        media_refs = []
    return {
        "dsl": dsl,
        "interaction_schema": interaction_schema,
        "media_refs": media_refs,
    }
