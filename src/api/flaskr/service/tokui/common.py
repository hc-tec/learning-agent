from __future__ import annotations

import hashlib
import json
import re
from typing import Any


TOKUI_STATUS_IDLE = "idle"
TOKUI_STATUS_VALIDATED = "validated"
TOKUI_STATUS_FAILED = "failed"
TOKUI_STATUS_FALLBACK = "fallback"

_TOKUI_TEXT_NEEDS_QUOTES_RE = re.compile(r"[\[\]:]")

_FIELD_TYPE_ALIASES = {
    "text": "short_text",
    "textarea": "short_text",
    "short": "short_text",
    "short_text": "short_text",
    "choice": "single_choice",
    "radio": "single_choice",
    "single": "single_choice",
    "single_choice": "single_choice",
    "select": "single_choice",
    "checkbox": "multi_choice",
    "multi": "multi_choice",
    "multiple": "multi_choice",
    "multiple_choice": "multi_choice",
    "multi_choice": "multi_choice",
    "boolean": "true_false",
    "bool": "true_false",
    "truefalse": "true_false",
    "true_false": "true_false",
    "number": "number",
}

_DEFAULT_VALUE_SHAPES = {
    "short_text": "string",
    "single_choice": "string",
    "multi_choice": "string_array",
    "true_false": "boolean",
    "number": "number",
}

_TRUE_FALSE_OPTIONS = [
    {"value": "true", "label": "对"},
    {"value": "false", "label": "错"},
]


def _quote_tokui_text_content(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if _TOKUI_TEXT_NEEDS_QUOTES_RE.search(text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def _repair_card_tx_container(match: re.Match[str]) -> str:
    attrs = match.group("attrs") or ""
    body = match.group("body") or ""
    tx_match = re.search(
        r'(?:^|\s)tx:(?:"(?P<quoted>(?:[^"\\]|\\.)*)"|(?P<bare>[^\s\]]+))',
        attrs,
    )
    if not tx_match or not body.strip():
        return match.group(0)
    tx_value = tx_match.group("quoted")
    if tx_value is None:
        tx_value = tx_match.group("bare") or ""
    tx_value = tx_value.replace('\\"', '"')
    cleaned_attrs = (attrs[: tx_match.start()] + attrs[tx_match.end() :]).strip()
    open_tag = f"[card {cleaned_attrs}]" if cleaned_attrs else "[card]"
    text_node = _quote_tokui_text_content(tx_value)
    injected = f"[p {text_node}]" if text_node else ""
    return f"{open_tag}{injected}{body}[/card]"


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


def normalize_material_refs(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        resource_id = str(
            item.get("resource_id")
            or item.get("resource_bid")
            or item.get("id")
            or ""
        ).strip()
        url = str(item.get("url") or item.get("src") or "").strip()
        media_type = str(item.get("media_type") or item.get("type") or "image").strip()
        if media_type not in {"image", "video"}:
            media_type = "image"
        normalized.append(
            {
                "placement_id": str(
                    item.get("placement_id") or item.get("bid") or f"material_{index + 1}"
                ).strip(),
                "position": str(item.get("position") or index + 1).strip(),
                "insertion_point": str(item.get("insertion_point") or "").strip(),
                "media_type": media_type,
                "title": str(item.get("title") or item.get("name") or "").strip(),
                "description": str(
                    item.get("description")
                    or item.get("generation_prompt")
                    or item.get("prompt")
                    or ""
                ).strip(),
                "purpose": str(item.get("purpose") or "").strip(),
                "resource_id": resource_id,
                "url": url,
            }
        )
    return [
        item
        for item in normalized
        if item["title"]
        or item["description"]
        or item["insertion_point"]
        or item["purpose"]
        or item["resource_id"]
        or item["url"]
    ]


def normalize_interaction_points(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        response_schema = item.get("response_schema")
        if not isinstance(response_schema, dict):
            response_schema = {}
        response_schema = normalize_response_schema(response_schema) if response_schema else {}
        blocking = bool(item.get("blocking", item.get("blocking_behavior", False)))
        continue_on_submit_value = item.get("continue_on_submit")
        continue_on_submit = (
            bool(continue_on_submit_value)
            if continue_on_submit_value is not None
            else blocking
        )
        normalized.append(
            {
                "interaction_id": str(
                    item.get("interaction_id")
                    or item.get("field_id")
                    or item.get("id")
                    or f"interaction_{index + 1}"
                ).strip(),
                "position": str(item.get("position") or index + 1).strip(),
                "insertion_point": str(
                    item.get("insertion_point") or item.get("trigger_after") or ""
                ).strip(),
                "kind": str(item.get("kind") or "checkpoint").strip(),
                "prompt": str(item.get("prompt") or item.get("question") or "").strip(),
                "response_schema": response_schema,
                "blocking": blocking,
                "continue_on_submit": continue_on_submit,
                "downstream_context_policy": str(
                    item.get("downstream_context_policy") or ""
                ).strip(),
                "continuation_hint": str(item.get("continuation_hint") or "").strip(),
            }
        )
    return [
        item
        for item in normalized
        if item["prompt"]
        or item["downstream_context_policy"]
        or item["continuation_hint"]
        or item["response_schema"]
    ]


def schema_hash(interaction_schema: Any) -> str:
    return stable_hash(interaction_schema if isinstance(interaction_schema, list) else [])


def normalize_field_type(value: Any) -> str:
    raw = str(value or "short_text").strip().lower().replace("-", "_")
    return _FIELD_TYPE_ALIASES.get(raw, raw or "short_text")


def normalize_schema_options(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            option_value = item.strip()
            option_label = option_value
        elif isinstance(item, dict):
            option_value = str(
                item.get("value")
                or item.get("v")
                or item.get("id")
                or item.get("key")
                or f"option_{index + 1}"
            ).strip()
            option_label = str(
                item.get("label")
                or item.get("tx")
                or item.get("text")
                or item.get("name")
                or option_value
            ).strip()
        else:
            continue
        if not option_value and not option_label:
            continue
        if not option_value:
            option_value = option_label
        if not option_label:
            option_label = option_value
        normalized.append({"value": option_value, "label": option_label})
    return normalized


def normalize_response_schema(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    field_type = normalize_field_type(raw.get("field_type") or raw.get("type"))
    options = normalize_schema_options(raw.get("options") or raw.get("choices"))
    if field_type == "true_false" and not options:
        options = list(_TRUE_FALSE_OPTIONS)
    normalized: dict[str, Any] = {
        "field_type": field_type,
        "value_shape": str(
            raw.get("value_shape") or _DEFAULT_VALUE_SHAPES.get(field_type, "string")
        ),
    }
    if options:
        normalized["options"] = options
    return normalized


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
        response_schema = normalize_response_schema(item)
        normalized_item = {
            "field_id": field_id,
            "field_type": response_schema["field_type"],
            "label": str(item.get("label") or item.get("field_label") or ""),
            "required": bool(item.get("required", False)),
            "semantic_role": str(item.get("semantic_role") or ""),
            "value_shape": response_schema["value_shape"],
            "blocking": blocking,
            "continue_on_submit": continue_on_submit,
            "continuation_hint": str(item.get("continuation_hint") or ""),
        }
        if response_schema.get("options"):
            normalized_item["options"] = response_schema["options"]
        normalized.append(normalized_item)
    return normalized


def normalize_generated_tokui_dsl(dsl: str) -> str:
    normalized = str(dsl or "").strip()

    def replace_heading_container(match: re.Match[str]) -> str:
        content = (match.group(2) or "").strip()
        if not content:
            return ""
        return f"[h2 {content}]"

    normalized = re.sub(
        r"\[heading([^\]]*)\](.*?)\[/heading\]",
        replace_heading_container,
        normalized,
        flags=re.IGNORECASE | re.DOTALL,
    )
    normalized = re.sub(
        r"\[heading\s+([^\]]+)\]",
        lambda match: f"[h2 {match.group(1).strip()}]",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\[card(?P<attrs>[^\]]*\btx:(?:\"(?:[^\"\\]|\\.)*\"|[^\s\]]+)[^\]]*)\]"
        r"(?P<body>[\s\S]*?)\[/card\]",
        _repair_card_tx_container,
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\[p\s+(muted|bold|sm|lg|left|center|right)\s+([^\]]+)\]",
        lambda match: f"[p v:{match.group(1)} {match.group(2).strip()}]",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\[(p|item|h[1-6])(\s+v:[^\s\]]+)?\s+([QA]):",
        lambda match: f"[{match.group(1)}{match.group(2) or ''} {match.group(3)}：",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"(\[p[^\]]+\])\s*\[/p\]",
        r"\1",
        normalized,
        flags=re.IGNORECASE,
    )
    return normalized


def build_generation_payload(raw_text: str) -> dict[str, Any]:
    parsed = extract_json_object(raw_text)
    dsl = normalize_generated_tokui_dsl(
        str(parsed.get("dsl") or parsed.get("tokui_dsl") or "")
    )
    interaction_schema = normalize_interaction_schema(parsed.get("interaction_schema"))
    media_refs = parsed.get("media_refs")
    if not isinstance(media_refs, list):
        media_refs = []
    return {
        "dsl": dsl,
        "interaction_schema": interaction_schema,
        "media_refs": media_refs,
    }
