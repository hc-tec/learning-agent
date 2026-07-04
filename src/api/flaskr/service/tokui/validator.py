from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
from flask import Flask


TOKUI_VALIDATION_TIMEOUT_SECONDS = 8
TOKUI_MAX_DSL_BYTES = 512 * 1024


@dataclass
class TokuiValidationError:
    message: str
    code: str = "TOKUI_VALIDATION_ERROR"
    path: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"message": self.message, "code": self.code, "path": self.path}


@dataclass
class TokuiValidationResult:
    ok: bool
    parser_version: str = ""
    errors: list[TokuiValidationError] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "parser_version": self.parser_version,
            "errors": [error.to_dict() for error in self.errors],
        }


def _default_validator_script_path() -> Path:
    api_root = Path(__file__).resolve().parents[4]
    api_script_path = api_root / "scripts" / "validate-tokui.mjs"
    if api_script_path.exists():
        return api_script_path
    return api_root.parent / "cook-web" / "scripts" / "validate-tokui.mjs"


def _normalize_errors(raw_errors: Any) -> list[TokuiValidationError]:
    if not isinstance(raw_errors, list):
        return []
    errors: list[TokuiValidationError] = []
    for item in raw_errors:
        if isinstance(item, dict):
            errors.append(
                TokuiValidationError(
                    message=str(item.get("message") or "TokUI validation failed"),
                    code=str(item.get("code") or "TOKUI_VALIDATION_ERROR"),
                    path=str(item.get("path") or ""),
                )
            )
        else:
            errors.append(TokuiValidationError(message=str(item)))
    return errors


def validate_tokui_dsl(
    app: Flask,
    dsl: str,
    *,
    locale: str = "zh-CN",
    theme: str = "default",
) -> TokuiValidationResult:
    normalized_dsl = str(dsl or "")
    if not normalized_dsl.strip():
        return TokuiValidationResult(
            ok=False,
            errors=[
                TokuiValidationError(
                    message="TokUI DSL is empty",
                    code="TOKUI_EMPTY_DSL",
                )
            ],
        )
    if len(normalized_dsl.encode("utf-8")) > TOKUI_MAX_DSL_BYTES:
        return TokuiValidationResult(
            ok=False,
            errors=[
                TokuiValidationError(
                    message="TokUI DSL is too large",
                    code="TOKUI_DSL_TOO_LARGE",
                )
            ],
        )

    validator_url = str(app.config.get("TOKUI_VALIDATOR_URL") or "").strip()
    if validator_url:
        return _validate_tokui_dsl_via_http(
            app,
            validator_url,
            normalized_dsl,
            locale=locale,
            theme=theme,
        )

    script_path = Path(
        app.config.get("TOKUI_VALIDATOR_SCRIPT")
        or str(_default_validator_script_path())
    )
    if not script_path.exists():
        return TokuiValidationResult(
            ok=False,
            errors=[
                TokuiValidationError(
                    message=f"TokUI validator script not found: {script_path}",
                    code="TOKUI_VALIDATOR_NOT_FOUND",
                )
            ],
        )

    payload = json.dumps(
        {"dsl": normalized_dsl, "locale": locale, "theme": theme},
        ensure_ascii=False,
    )
    try:
        completed = subprocess.run(
            ["node", str(script_path)],
            input=payload,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=int(app.config.get("TOKUI_VALIDATION_TIMEOUT", TOKUI_VALIDATION_TIMEOUT_SECONDS)),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return TokuiValidationResult(
            ok=False,
            errors=[
                TokuiValidationError(
                    message="TokUI validation timed out",
                    code="TOKUI_VALIDATION_TIMEOUT",
                )
            ],
        )
    except Exception as exc:
        app.logger.exception("TokUI validation subprocess failed")
        return TokuiValidationResult(
            ok=False,
            errors=[
                TokuiValidationError(
                    message=str(exc),
                    code="TOKUI_VALIDATION_SUBPROCESS_ERROR",
                )
            ],
        )

    if completed.returncode != 0:
        return TokuiValidationResult(
            ok=False,
            errors=[
                TokuiValidationError(
                    message=(completed.stderr or "TokUI validator failed").strip(),
                    code="TOKUI_VALIDATOR_RUNTIME_ERROR",
                )
            ],
        )

    try:
        result = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return TokuiValidationResult(
            ok=False,
            errors=[
                TokuiValidationError(
                    message="TokUI validator returned invalid JSON",
                    code="TOKUI_VALIDATOR_INVALID_JSON",
                )
            ],
        )

    return TokuiValidationResult(
        ok=bool(result.get("ok")),
        parser_version=str(result.get("parser_version") or ""),
        errors=_normalize_errors(result.get("errors")),
    )


def _validate_tokui_dsl_via_http(
    app: Flask,
    validator_url: str,
    dsl: str,
    *,
    locale: str,
    theme: str,
) -> TokuiValidationResult:
    try:
        response = requests.post(
            validator_url,
            json={"dsl": dsl, "locale": locale, "theme": theme},
            timeout=int(app.config.get("TOKUI_VALIDATION_TIMEOUT", TOKUI_VALIDATION_TIMEOUT_SECONDS)),
        )
        response.raise_for_status()
        result = response.json()
    except requests.Timeout:
        return TokuiValidationResult(
            ok=False,
            errors=[
                TokuiValidationError(
                    message="TokUI validation timed out",
                    code="TOKUI_VALIDATION_TIMEOUT",
                )
            ],
        )
    except Exception as exc:
        app.logger.exception("TokUI validation HTTP service failed")
        return TokuiValidationResult(
            ok=False,
            errors=[
                TokuiValidationError(
                    message=str(exc),
                    code="TOKUI_VALIDATOR_HTTP_ERROR",
                )
            ],
        )

    return TokuiValidationResult(
        ok=bool(result.get("ok")),
        parser_version=str(result.get("parser_version") or ""),
        errors=_normalize_errors(result.get("errors")),
    )
