import base64
import pytest
from flask import Flask

from flaskr.service.common.models import AppException
from flaskr.service.tokui import image_generation


def test_tokui_image_provider_config_requires_base_url_and_api_key(monkeypatch):
    monkeypatch.setattr(image_generation, "get_config", lambda key, default=None: "")

    with pytest.raises(AppException):
        image_generation.get_tokui_image_provider_config()


def test_tokui_image_provider_request_uses_configured_base_url_and_model():
    config = image_generation.TokuiImageProviderConfig(
        base_url="https://image-provider.test/v1",
        api_key="test-key",
        model="custom-image-model",
        timeout_seconds=30,
        default_size="1024x1024",
    )

    endpoint, headers, payload = image_generation._build_provider_request(
        config=config,
        prompt="Draw a clear teaching diagram",
        size="768x768",
    )

    assert endpoint == "https://image-provider.test/v1/images/generations"
    assert headers["Authorization"] == "Bearer test-key"
    assert headers["User-Agent"] == "AI-Shifu TokUI Image Generator/1.0"
    assert payload["model"] == "custom-image-model"
    assert payload["prompt"] == "Draw a clear teaching diagram"
    assert payload["size"] == "768x768"
    assert payload["response_format"] == "b64_json"


def test_generate_tokui_image_media_ref_stores_b64_provider_image(monkeypatch):
    app = Flask(__name__)
    png_bytes = b"\x89PNG\r\n\x1a\nsample"
    encoded = base64.b64encode(png_bytes).decode("ascii")

    def fake_get_config(key, default=None):
        return {
            "TOKUI_IMAGE_API_BASE_URL": "https://image-provider.test/v1",
            "TOKUI_IMAGE_API_KEY": "test-key",
            "TOKUI_IMAGE_MODEL": "gpt-image-2",
            "TOKUI_IMAGE_TIMEOUT_SECONDS": 10,
            "TOKUI_IMAGE_SIZE": "1024x1024",
        }.get(key, default)

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"data": [{"b64_json": encoded}]}

    captured = {}

    def fake_post(endpoint, headers, json, timeout):
        captured["endpoint"] = endpoint
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    def fake_store(app, *, user_bid, prompt, title, generated_image):
        captured["stored"] = generated_image.content
        return {
            "resource_id": "resource-1",
            "url": "/api/storage/courses/tokui/generated-images/resource-1.png",
            "type": "image",
            "title": title,
            "description": prompt,
        }

    monkeypatch.setattr(image_generation, "get_config", fake_get_config)
    monkeypatch.setattr(image_generation, "check_text_with_risk_control", lambda *args: None)
    monkeypatch.setattr(image_generation.requests, "post", fake_post)
    monkeypatch.setattr(image_generation, "_store_generated_image", fake_store)

    result = image_generation.generate_tokui_image_media_ref(
        app,
        user_bid="teacher-1",
        outline_bid="outline-1",
        prompt="Draw a simple railway braking diagram",
        title="Brake diagram",
    )

    assert captured["endpoint"] == "https://image-provider.test/v1/images/generations"
    assert captured["json"]["model"] == "gpt-image-2"
    assert captured["json"]["prompt"] == "Draw a simple railway braking diagram"
    assert captured["stored"] == png_bytes
    assert result["media_ref"] == {
        "resource_id": "resource-1",
        "url": "/api/storage/courses/tokui/generated-images/resource-1.png",
        "type": "image",
        "title": "Brake diagram",
        "description": "Draw a simple railway braking diagram",
    }
    assert result["provider"] == {"model": "gpt-image-2", "size": "1024x1024"}
