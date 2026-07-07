import json
from types import SimpleNamespace

import requests
from flask import Flask

from flaskr.service.tokui import validator


def _app_with_http_validator(script_path):
    app = Flask(__name__)
    app.config["TOKUI_VALIDATOR_URL"] = "http://validator.test/validate"
    app.config["TOKUI_VALIDATOR_SCRIPT"] = str(script_path)
    app.config["TOKUI_VALIDATION_TIMEOUT"] = 3
    return app


def test_http_validator_connection_error_falls_back_to_local_script(
    monkeypatch, tmp_path
):
    script_path = tmp_path / "validate-tokui.mjs"
    script_path.write_text("// fake validator", encoding="utf-8")
    app = _app_with_http_validator(script_path)
    captured = {}

    def fake_post(*args, **kwargs):
        raise requests.ConnectionError("validator is down")

    def fake_run(args, input, text, stdout, stderr, timeout, check):
        captured["args"] = args
        captured["payload"] = json.loads(input)
        captured["timeout"] = timeout
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"ok": True, "parser_version": "test-parser"}),
            stderr="",
        )

    monkeypatch.setattr(validator.requests, "post", fake_post)
    monkeypatch.setattr(validator.subprocess, "run", fake_run)

    result = validator.validate_tokui_dsl(app, "[card][p hello]")

    assert result.ok is True
    assert result.parser_version == "test-parser"
    assert captured["args"] == ["node", str(script_path)]
    assert captured["payload"]["dsl"] == "[card][p hello]"
    assert captured["payload"]["locale"] == "zh-CN"
    assert captured["timeout"] == 3


def test_http_validator_timeout_falls_back_to_local_script(monkeypatch, tmp_path):
    script_path = tmp_path / "validate-tokui.mjs"
    script_path.write_text("// fake validator", encoding="utf-8")
    app = _app_with_http_validator(script_path)

    def fake_post(*args, **kwargs):
        raise requests.Timeout()

    def fake_run(*args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"ok": True, "parser_version": "timeout-fallback"}),
            stderr="",
        )

    monkeypatch.setattr(validator.requests, "post", fake_post)
    monkeypatch.setattr(validator.subprocess, "run", fake_run)

    result = validator.validate_tokui_dsl(app, "[card][p after timeout]")

    assert result.ok is True
    assert result.parser_version == "timeout-fallback"


def test_http_validator_semantic_errors_do_not_use_local_fallback(
    monkeypatch, tmp_path
):
    script_path = tmp_path / "validate-tokui.mjs"
    script_path.write_text("// fake validator", encoding="utf-8")
    app = _app_with_http_validator(script_path)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "ok": False,
                "parser_version": "http-parser",
                "errors": [
                    {
                        "message": "Unknown TokUI node",
                        "code": "TOKUI_VALIDATION_ERROR",
                        "path": "root.0",
                    }
                ],
            }

    def fake_post(*args, **kwargs):
        return FakeResponse()

    def fake_run(*args, **kwargs):
        raise AssertionError("local fallback should not run for parser errors")

    monkeypatch.setattr(validator.requests, "post", fake_post)
    monkeypatch.setattr(validator.subprocess, "run", fake_run)

    result = validator.validate_tokui_dsl(app, "[unknown]")

    assert result.ok is False
    assert result.parser_version == "http-parser"
    assert result.errors[0].code == "TOKUI_VALIDATION_ERROR"
    assert result.errors[0].message == "Unknown TokUI node"


def test_http_validator_connection_error_without_local_script_keeps_http_error(
    monkeypatch, tmp_path
):
    app = _app_with_http_validator(tmp_path / "missing-validator.mjs")

    def fake_post(*args, **kwargs):
        raise requests.ConnectionError("validator is down")

    def fake_run(*args, **kwargs):
        raise AssertionError("missing local script must not run")

    monkeypatch.setattr(validator.requests, "post", fake_post)
    monkeypatch.setattr(validator.subprocess, "run", fake_run)

    result = validator.validate_tokui_dsl(app, "[card][p hello]")

    assert result.ok is False
    assert result.errors[0].code == "TOKUI_VALIDATOR_HTTP_ERROR"
