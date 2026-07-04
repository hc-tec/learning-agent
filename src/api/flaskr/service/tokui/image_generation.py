from __future__ import annotations

import base64
import binascii
import re
import uuid
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import requests
from flask import Flask

from flaskr.dao import db
from flaskr.service.check_risk.funcs import check_text_with_risk_control
from flaskr.service.common import raise_error, raise_param_error
from flaskr.service.common.oss_utils import OSS_PROFILE_COURSES
from flaskr.service.common.storage import upload_to_storage
from flaskr.service.config import get_config
from flaskr.service.resource.models import Resource


_DEFAULT_IMAGE_SIZE = "1024x1024"
_PROVIDER_ERROR_SNIPPET_LIMIT = 500


@dataclass(frozen=True)
class TokuiImageProviderConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int
    default_size: str


@dataclass(frozen=True)
class GeneratedImage:
    content: bytes
    content_type: str
    provider_payload: dict[str, Any]


def _get_positive_int_config(name: str, default: int) -> int:
    value = get_config(name, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def get_tokui_image_provider_config() -> TokuiImageProviderConfig:
    base_url = str(get_config("TOKUI_IMAGE_API_BASE_URL", "") or "").strip().rstrip("/")
    api_key = str(get_config("TOKUI_IMAGE_API_KEY", "") or "").strip()
    model = str(get_config("TOKUI_IMAGE_MODEL", "gpt-image-2") or "").strip()
    default_size = str(
        get_config("TOKUI_IMAGE_SIZE", _DEFAULT_IMAGE_SIZE) or _DEFAULT_IMAGE_SIZE
    ).strip()
    timeout_seconds = _get_positive_int_config("TOKUI_IMAGE_TIMEOUT_SECONDS", 120)

    if not base_url or not api_key:
        raise_error("server.shifu.tokuiImageNotConfigured")
    if not model:
        raise_param_error("model")
    if not default_size:
        default_size = _DEFAULT_IMAGE_SIZE

    return TokuiImageProviderConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
        default_size=default_size,
    )


def _build_provider_request(
    *,
    config: TokuiImageProviderConfig,
    prompt: str,
    size: str,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    endpoint = f"{config.base_url}/images/generations"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
        "User-Agent": "AI-Shifu TokUI Image Generator/1.0",
    }
    payload = {
        "model": config.model,
        "prompt": prompt,
        "size": size or config.default_size,
        "n": 1,
        "response_format": "b64_json",
    }
    return endpoint, headers, payload


def _provider_error_message(response: requests.Response) -> str:
    text = (response.text or "").strip()
    if len(text) > _PROVIDER_ERROR_SNIPPET_LIMIT:
        text = f"{text[:_PROVIDER_ERROR_SNIPPET_LIMIT]}..."
    return text


def _decode_data_url(value: str) -> tuple[bytes, str]:
    header, encoded = value.split(",", 1)
    content_type = "image/png"
    match = re.match(r"data:(image/[-+\w.]+);base64", header)
    if match:
        content_type = match.group(1)
    return base64.b64decode(encoded), content_type


def _download_generated_image(url: str, timeout_seconds: int) -> tuple[bytes, str]:
    try:
        response = requests.get(url, timeout=timeout_seconds)
        response.raise_for_status()
    except requests.RequestException:
        raise_error("server.shifu.tokuiImageGenerationFailed")

    content_type = str(response.headers.get("Content-Type") or "image/png").split(";")[
        0
    ]
    if not content_type.startswith("image/"):
        content_type = "image/png"
    return response.content, content_type


def _extract_generated_image(
    provider_payload: dict[str, Any],
    *,
    timeout_seconds: int,
) -> GeneratedImage:
    data = provider_payload.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise_error("server.shifu.tokuiImageProviderInvalidResponse")

    first = data[0]
    b64_json = str(first.get("b64_json") or "").strip()
    data_url = str(first.get("data_url") or "").strip()
    url = str(first.get("url") or "").strip()

    try:
        if b64_json:
            return GeneratedImage(
                content=base64.b64decode(b64_json),
                content_type="image/png",
                provider_payload=first,
            )
        if data_url.startswith("data:image/"):
            content, content_type = _decode_data_url(data_url)
            return GeneratedImage(
                content=content,
                content_type=content_type,
                provider_payload=first,
            )
    except (binascii.Error, ValueError):
        raise_error("server.shifu.tokuiImageProviderInvalidResponse")

    if url:
        content, content_type = _download_generated_image(url, timeout_seconds)
        return GeneratedImage(
            content=content,
            content_type=content_type,
            provider_payload=first,
        )

    raise_error("server.shifu.tokuiImageProviderInvalidResponse")


def _extension_for_content_type(content_type: str) -> str:
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized == "image/jpeg":
        return "jpg"
    if normalized == "image/webp":
        return "webp"
    if normalized == "image/gif":
        return "gif"
    return "png"


def _clean_title(value: str) -> str:
    title = re.sub(r"\s+", " ", str(value or "").strip())
    if not title:
        return "TokUI generated image"
    return title[:120]


def _store_generated_image(
    app: Flask,
    *,
    user_bid: str,
    prompt: str,
    title: str,
    generated_image: GeneratedImage,
) -> dict[str, str]:
    resource_id = uuid.uuid4().hex
    content_type = generated_image.content_type or "image/png"
    extension = _extension_for_content_type(content_type)
    object_key = f"tokui/generated-images/{resource_id}.{extension}"
    filename = f"{_clean_title(title)}.{extension}"

    result = upload_to_storage(
        app,
        file_content=BytesIO(generated_image.content),
        object_key=object_key,
        content_type=content_type,
        profile=OSS_PROFILE_COURSES,
    )

    resource = Resource(
        resource_id=resource_id,
        name=filename[:255],
        type=0,
        oss_bucket=result.bucket,
        oss_name=result.object_key,
        url=result.url,
        status=0,
        is_deleted=0,
        created_by=user_bid,
        updated_by=user_bid,
    )
    db.session.add(resource)
    db.session.commit()

    return {
        "resource_id": resource_id,
        "url": result.url,
        "type": "image",
        "title": _clean_title(title),
        "description": prompt,
    }


def generate_tokui_image_media_ref(
    app: Flask,
    *,
    user_bid: str,
    prompt: str,
    outline_bid: str = "",
    title: str = "",
    size: str = "",
) -> dict[str, Any]:
    normalized_prompt = str(prompt or "").strip()
    if not normalized_prompt:
        raise_param_error("prompt")
    if outline_bid:
        check_text_with_risk_control(app, outline_bid, user_bid, normalized_prompt)

    config = get_tokui_image_provider_config()
    image_size = str(size or config.default_size).strip() or config.default_size
    endpoint, headers, payload = _build_provider_request(
        config=config,
        prompt=normalized_prompt,
        size=image_size,
    )

    try:
        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=config.timeout_seconds,
        )
    except requests.RequestException:
        raise_error("server.shifu.tokuiImageGenerationFailed")

    if response.status_code >= 400:
        app.logger.warning(
            "TokUI image provider request failed status=%s body=%s",
            response.status_code,
            _provider_error_message(response),
        )
        raise_error("server.shifu.tokuiImageGenerationFailed")

    try:
        provider_payload = response.json()
    except ValueError:
        raise_error("server.shifu.tokuiImageProviderInvalidResponse")
    if not isinstance(provider_payload, dict):
        raise_error("server.shifu.tokuiImageProviderInvalidResponse")

    generated_image = _extract_generated_image(
        provider_payload,
        timeout_seconds=config.timeout_seconds,
    )
    with app.app_context():
        media_ref = _store_generated_image(
            app,
            user_bid=user_bid,
            prompt=normalized_prompt,
            title=title or normalized_prompt,
            generated_image=generated_image,
        )

    return {
        "media_ref": media_ref,
        "resource": media_ref,
        "provider": {
            "model": config.model,
            "size": image_size,
        },
    }
