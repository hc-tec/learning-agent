"""
Complex TokUI course E2E matrix for AI-Shifu.

The default matrix uses a deterministic local image provider and the
tokui-e2e-controlled model hook. It proves multi-image, multi-input,
multi-round continuation, partial/all image failure, refresh reuse, republish
cache invalidation, and learner browser rendering without calling paid LLM or
image providers.

Usage:
    python ./e2e/run_tokui_complex_course_e2e.py

For browser rendering against a local Cook Web dev server, prefer a same-origin
proxy host such as AI_SHIFU_URL=http://localtest.me:3008 and start Next with
NEXT_PUBLIC_API_BASE_URL=http://api.localtest.me:8080. That keeps browser API
calls on /api/* while the Next dev server proxies them to the Docker backend.

Optional environment:
    AI_SHIFU_URL=http://127.0.0.1:8080
    HEADLESS=false
    E2E_IMAGE_PROVIDER_PORT=5824
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import subprocess
import struct
import sys
import threading
import time
import traceback
import zlib
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import requests
from browser_use import BrowserProfile
from browser_use.browser.session import BrowserSession


TARGET_URL = os.getenv("AI_SHIFU_URL", "http://127.0.0.1:8080").rstrip("/")
HEADLESS = os.getenv("HEADLESS", "true").lower() != "false"
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
RESULT_PATH = Path(__file__).resolve().parent / "tokui_complex_course_e2e_result.json"
SCREENSHOT_PATH = (
    Path(__file__).resolve().parent / "tokui_complex_course_learner.png"
)
FAKE_IMAGE_PROVIDER_PORT = int(os.getenv("E2E_IMAGE_PROVIDER_PORT", "5824"))
FAKE_IMAGE_PROVIDER_PUBLIC_URL = os.getenv(
    "E2E_IMAGE_PROVIDER_PUBLIC_URL",
    f"http://host.docker.internal:{FAKE_IMAGE_PROVIDER_PORT}/v1",
).rstrip("/")
TOKUI_VALIDATOR_PORT = int(os.getenv("E2E_TOKUI_VALIDATOR_PORT", "5811"))
TOKUI_VALIDATOR_HEALTH_URL = os.getenv(
    "E2E_TOKUI_VALIDATOR_HEALTH_URL",
    f"http://127.0.0.1:{TOKUI_VALIDATOR_PORT}/health",
)
CONTROLLED_MODEL = "tokui-e2e-controlled"

def solid_png_b64(width: int, height: int, rgb: tuple[int, int, int]) -> str:
    raw_scanlines = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", checksum)
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw_scanlines))
        + chunk(b"IEND", b"")
    )
    return base64.b64encode(png).decode("ascii")


SAMPLE_PNGS_B64 = [
    solid_png_b64(100, 200, (220, 38, 38)),
    solid_png_b64(100, 200, (22, 163, 74)),
    solid_png_b64(100, 200, (37, 99, 235)),
]


class CheckFailed(AssertionError):
    pass


class ScenarioRecorder:
    def __init__(self, name: str) -> None:
        self.name = name
        self.checks: list[dict[str, Any]] = []
        self.evidence: dict[str, Any] = {}

    def check(self, name: str, passed: bool, detail: str, extra: Any = None) -> None:
        item: dict[str, Any] = {
            "name": name,
            "passed": bool(passed),
            "detail": detail,
        }
        if extra is not None:
            item["extra"] = extra
        self.checks.append(item)
        if not passed:
            raise CheckFailed(f"{self.name}.{name}: {detail}")

    def to_result(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": all(item["passed"] for item in self.checks),
            "checks": self.checks,
            "evidence": self.evidence,
        }


class FakeImageProviderHandler(BaseHTTPRequestHandler):
    request_count = 0
    mode_counts: dict[str, int] = {}
    requests: list[dict[str, Any]] = []
    lock = threading.Lock()

    def do_POST(self) -> None:
        if self.path != "/v1/images/generations":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("content-length") or "0")
        raw_body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            payload = {}
        prompt = str(payload.get("prompt") or "")
        if "E2E_ALL_FAIL" in prompt:
            mode = "all_fail"
        elif "E2E_PARTIAL_FAIL" in prompt:
            mode = "partial"
        elif "E2E_TIMEOUT" in prompt:
            mode = "timeout"
        else:
            mode = "success"

        with FakeImageProviderHandler.lock:
            FakeImageProviderHandler.request_count += 1
            FakeImageProviderHandler.mode_counts[mode] = (
                FakeImageProviderHandler.mode_counts.get(mode, 0) + 1
            )
            mode_index = FakeImageProviderHandler.mode_counts[mode]
            FakeImageProviderHandler.requests.append(
                {"mode": mode, "mode_index": mode_index, "payload": payload}
            )

        if mode == "timeout":
            time.sleep(120)
            return
        if mode == "all_fail" or (mode == "partial" and mode_index % 3 != 1):
            body = json.dumps(
                {"error": {"message": f"E2E fake provider {mode} failure"}}
            ).encode("utf-8")
            self.send_response(500)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        sample_index = (mode_index - 1) % len(SAMPLE_PNGS_B64)
        if "first" in prompt.lower():
            sample_index = 0
        elif "second" in prompt.lower():
            sample_index = 1
        elif "partial" in prompt.lower() or "retry" in prompt.lower():
            sample_index = 2
        response = {
            "data": [
                {
                    "b64_json": SAMPLE_PNGS_B64[sample_index],
                    "revised_prompt": f"{prompt} #{mode_index}",
                }
            ]
        }
        body = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def start_fake_image_provider() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", FAKE_IMAGE_PROVIDER_PORT), FakeImageProviderHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _tokui_validator_is_healthy() -> bool:
    try:
        response = requests.get(TOKUI_VALIDATOR_HEALTH_URL, timeout=3)
        return response.ok
    except Exception:
        return False


def start_tokui_validator_if_needed() -> subprocess.Popen[bytes] | None:
    if _tokui_validator_is_healthy():
        return None

    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "src" / "cook-web" / "scripts" / "validate-tokui-server.mjs"
    if not script_path.exists():
        raise CheckFailed(f"TokUI validator server script not found: {script_path}")

    node_bin = os.getenv("E2E_NODE_BIN") or shutil.which("node")
    fallback_node = Path("D:/apps/nodejs/node.exe")
    if not node_bin and fallback_node.exists():
        node_bin = str(fallback_node)
    if not node_bin:
        raise CheckFailed("node executable not found for TokUI validator server")

    env = os.environ.copy()
    env["TOKUI_VALIDATOR_HOST"] = "0.0.0.0"
    env["TOKUI_VALIDATOR_PORT"] = str(TOKUI_VALIDATOR_PORT)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [node_bin, str(script_path)],
        cwd=str(repo_root / "src" / "cook-web"),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    for _ in range(30):
        if process.poll() is not None:
            raise CheckFailed(
                f"TokUI validator server exited early with code {process.returncode}"
            )
        if _tokui_validator_is_healthy():
            return process
        time.sleep(0.5)
    process.terminate()
    raise CheckFailed("TokUI validator server did not become healthy")


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.session = requests.Session()
        self.token = ""

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        token: bool = False,
        timeout: int = 60,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if token:
            headers["Token"] = self.token
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            json=json_body,
            headers=headers,
            timeout=timeout,
        )
        try:
            parsed = response.json()
        except Exception:
            parsed = None
        return {
            "path": path,
            "status": response.status_code,
            "ok": response.ok,
            "text": response.text[:1200],
            "json": parsed,
        }

    def login(self) -> dict[str, Any]:
        captcha = self.request("GET", "/api/user/captcha")
        captcha_id = data(captcha).get("captcha_id")
        captcha_verify = self.request(
            "POST",
            "/api/user/captcha/verify",
            json_body={"captcha_id": captcha_id, "captcha_code": "0000"},
        )
        captcha_ticket = data(captcha_verify).get("captcha_ticket")
        sms = self.request(
            "POST",
            "/api/user/send_sms_code",
            json_body={"mobile": "13800000001", "captcha_ticket": captcha_ticket},
        )
        login = self.request(
            "POST",
            "/api/user/login_sms",
            json_body={
                "mobile": "13800000001",
                "sms_code": "1024",
                "login_context": "admin",
            },
        )
        self.token = str(data(login).get("token") or "")
        return {"captcha": captcha, "captchaVerify": captcha_verify, "sms": sms, "login": login}


def resolve_api_base_url(site_url: str) -> str:
    try:
        response = requests.get(f"{site_url}/api/config", timeout=10)
        if response.ok:
            api_base = str((response.json() or {}).get("apiBaseUrl") or "").rstrip("/")
            if api_base:
                return api_base
    except Exception:
        pass
    return site_url


def code(item: dict[str, Any]) -> Any:
    return (item.get("json") or {}).get("code")


def data(item: dict[str, Any]) -> dict[str, Any]:
    value = (item.get("json") or {}).get("data")
    return value if isinstance(value, dict) else {}


def require_api_ok(item: dict[str, Any], label: str) -> dict[str, Any]:
    if code(item) != 0:
        raise CheckFailed(f"{label} failed: {item}")
    return data(item)


def build_image_config_restore_payload(previous: dict[str, Any]) -> dict[str, Any]:
    return {
        "api_base_url": previous.get("api_base_url", ""),
        "model": previous.get("model", "gpt-image-2"),
        "timeout_seconds": previous.get("timeout_seconds", 120),
        "size": previous.get("size", "1024x1024"),
        "default_candidate_count": previous.get("default_candidate_count", 3),
        "prompt_optimizer_enabled": previous.get("prompt_optimizer_enabled", True),
        "prompt_optimizer_model": previous.get("prompt_optimizer_model", ""),
        "prompt_optimizer_temperature": previous.get("prompt_optimizer_temperature", 0.2),
        "prompt_optimizer_system_prompt": previous.get("prompt_optimizer_system_prompt", ""),
    }


def base_template(media_refs: list[dict[str, Any]] | None = None, *, version: str) -> dict[str, Any]:
    return {
        "teacher_intent": (
            f"E2E_VERSION_{version}: learner can explain China's four railway "
            "types in plain language and map business requests to the right type."
        ),
        "prompt_template": (
            f"E2E_VERSION_{version}: Use a detailed railway industry lesson. "
            "First explain why railways are classified by speed and freight/passenger "
            "function, then teach high-speed, intercity, mixed passenger/freight, "
            "and heavy-haul railways with concrete business examples. Insert multiple "
            "materials at their specified positions. Ask Feynman-style checks, then "
            "use learner answers to continue with targeted correction instead of "
            "repeating the same question."
        ),
        "concept": "铁路行业基本格局与分类",
        "audience": "铁路数智化部门新人",
        "material_refs": [
            {
                "placement_id": "railway_scene_video",
                "position": "1",
                "insertion_point": "讲完四类铁路的文字讲解后，立即插入",
                "media_type": "video",
                "title": "四类铁路实景对比短片",
                "description": "高铁、城际、客货共线、重载四段实景分屏对比，带速度、功能和特点字幕。",
                "purpose": "用直观视觉差异替代抽象文字，避免死记硬背。",
            },
            {
                "placement_id": "railway_compare_chart",
                "position": "2",
                "insertion_point": "视频播放结束后立即插入",
                "media_type": "image",
                "title": "中国四类铁路核心参数对比图",
                "description": "横向四栏对比高铁、城际、客货共线、重载铁路的速度、功能、特点和数智化侧重。",
                "purpose": "把零散知识点结构化，方便回顾记忆。",
            },
            {
                "placement_id": "eight_vertical_eight_horizontal_map",
                "position": "3",
                "insertion_point": "讲完八纵八横概念后立即插入",
                "media_type": "image",
                "title": "中国高铁八纵八横主通道示意图",
                "description": "简化中国地图，突出八纵八横和武汉、沿江通道。",
                "purpose": "建立空间认知，让新人理解全国路网和本院业务区域。",
            },
        ],
        "media_refs": media_refs or [],
        "generation_options": {
            "model": CONTROLLED_MODEL,
            "temperature": 0.1,
            "interaction_mode": "checkpoint",
            "blocking_checkpoint": True,
            "e2e_controlled_llm": True,
            "interaction_points": [
                {
                    "interaction_id": "railway_business_mapping_check",
                    "position": "1",
                    "kind": "feynman_check",
                    "prompt": "客户说要做万吨列车制动系统健康预测，这属于哪类铁路？",
                    "response_schema": {"field_type": "text"},
                    "blocking": True,
                    "continue_on_submit": True,
                    "continuation_hint": "根据答案判断学生是否理解重载铁路的业务诉求。",
                },
                {
                    "interaction_id": "intercity_flow_check",
                    "position": "2",
                    "kind": "scenario_mapping",
                    "prompt": "市域内通勤客流预测系统大概率对应哪类铁路？",
                    "response_schema": {"field_type": "choice"},
                    "blocking": False,
                    "continue_on_submit": False,
                    "continuation_hint": "用答案补强城际铁路和高铁的区别。",
                },
                {
                    "interaction_id": "high_speed_freight_reasoning",
                    "position": "3",
                    "kind": "explain_in_own_words",
                    "prompt": "用自己的话解释为什么高铁一般不跑货运列车。",
                    "response_schema": {"field_type": "text"},
                    "blocking": True,
                    "continue_on_submit": True,
                    "continuation_hint": "针对学生的原因解释补充线路平顺度、安全和运营规则差异。",
                },
            ],
        },
        "context_policy": {
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
        },
    }


def create_course_tree(client: ApiClient, stamp: str) -> dict[str, str]:
    course = require_api_ok(
        client.request(
            "PUT",
            "/api/shifu/shifus",
            json_body={
                "name": f"E2E TokUI Complex {stamp}",
                "description": "Complex TokUI E2E course",
                "avatar": "",
            },
            token=True,
        ),
        "create course",
    )
    shifu_bid = str(course.get("bid") or "")
    chapter = require_api_ok(
        client.request(
            "PUT",
            f"/api/shifu/shifus/{shifu_bid}/outlines",
            json_body={
                "parent_bid": "",
                "name": "E2E complex chapter",
                "description": "",
                "type": "guest",
                "index": 1,
                "is_hidden": False,
            },
            token=True,
        ),
        "create chapter",
    )
    lesson = require_api_ok(
        client.request(
            "PUT",
            f"/api/shifu/shifus/{shifu_bid}/outlines",
            json_body={
                "parent_bid": chapter.get("bid"),
                "name": "E2E complex TokUI lesson",
                "description": "",
                "type": "trial",
                "index": 1,
                "is_hidden": False,
            },
            token=True,
        ),
        "create lesson",
    )
    return {
        "shifu_bid": shifu_bid,
        "chapter_bid": str(chapter.get("bid") or ""),
        "outline_bid": str(lesson.get("bid") or ""),
    }


def configure_image_provider(client: ApiClient, recorder: ScenarioRecorder) -> dict[str, Any]:
    previous = require_api_ok(
        client.request("GET", "/api/shifu/admin/operations/tokui-image/config", token=True),
        "get image config",
    )
    payload: dict[str, Any] = {
        "api_base_url": FAKE_IMAGE_PROVIDER_PUBLIC_URL,
        "model": "e2e-image-model",
        "timeout_seconds": 20,
        "size": "1024x1024",
        "default_candidate_count": 3,
        "prompt_optimizer_enabled": False,
        "prompt_optimizer_model": "",
        "prompt_optimizer_temperature": 0.2,
        "prompt_optimizer_system_prompt": "E2E disables image prompt optimization.",
    }
    if not previous.get("api_key_configured"):
        payload["api_key"] = "e2e-fake-image-key"
    updated = require_api_ok(
        client.request(
            "POST",
            "/api/shifu/admin/operations/tokui-image/config",
            json_body=payload,
            token=True,
        ),
        "update image config",
    )
    recorder.evidence["imageConfigBefore"] = previous
    recorder.evidence["imageConfigUpdate"] = updated
    return build_image_config_restore_payload(previous)


def poll_image_job(
    client: ApiClient,
    shifu_bid: str,
    outline_bid: str,
    job_bid: str,
    *,
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    latest: dict[str, Any] = {}
    while time.time() < deadline:
        response = client.request(
            "GET",
            f"/api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/tokui-template/image-jobs/{job_bid}",
            token=True,
            timeout=10,
        )
        latest = require_api_ok(response, "poll image job")
        if latest.get("status") in {"awaiting_selection", "selected", "failed", "canceled"}:
            return latest
        time.sleep(1)
    raise CheckFailed(f"image job did not finish: {latest}")


def create_and_select_image(
    client: ApiClient,
    shifu_bid: str,
    outline_bid: str,
    prompt: str,
    recorder: ScenarioRecorder,
    label: str,
    select_index: int = 0,
) -> dict[str, Any]:
    job = require_api_ok(
        client.request(
            "POST",
            f"/api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/tokui-template/image-jobs",
            json_body={
                "teacher_prompt": prompt,
                "title": label,
                "size": "1024x1024",
                "candidate_count": 3,
            },
            token=True,
            timeout=20,
        ),
        f"create image job {label}",
    )
    polled = poll_image_job(client, shifu_bid, outline_bid, str(job.get("job_bid") or ""))
    candidates = polled.get("candidates") or []
    succeeded = [
        candidate
        for candidate in candidates
        if candidate.get("status") == "succeeded" and candidate.get("candidate_bid")
    ]
    recorder.check(
        f"{label}_has_successful_candidates",
        polled.get("status") == "awaiting_selection" and len(succeeded) >= 1,
        "image job reached awaiting_selection with at least one successful candidate",
        polled,
    )
    selected_candidate = succeeded[min(max(select_index, 0), len(succeeded) - 1)]
    selected = require_api_ok(
        client.request(
            "POST",
            f"/api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/tokui-template/image-jobs/{job.get('job_bid')}/select",
            json_body={"candidate_bid": selected_candidate.get("candidate_bid")},
            token=True,
            timeout=30,
        ),
        f"select image candidate {label}",
    )
    recorder.evidence[label] = {"job": polled, "selected": selected}
    return selected.get("media_ref") or {}


def run_failure_and_retry_scenario(
    client: ApiClient,
    shifu_bid: str,
    outline_bid: str,
    recorder: ScenarioRecorder,
) -> None:
    partial_job = require_api_ok(
        client.request(
            "POST",
            f"/api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/tokui-template/image-jobs",
            json_body={
                "teacher_prompt": "E2E_PARTIAL_FAIL generate three candidates",
                "title": "partial failure",
                "candidate_count": 3,
            },
            token=True,
            timeout=20,
        ),
        "create partial failure job",
    )
    partial = poll_image_job(client, shifu_bid, outline_bid, partial_job["job_bid"])
    partial_candidates = partial.get("candidates") or []
    partial_success = [
        item for item in partial_candidates if item.get("status") == "succeeded"
    ]
    partial_failed = [
        item for item in partial_candidates if item.get("status") == "failed"
    ]
    recorder.check(
        "partial_image_failure_keeps_selectable_success",
        partial.get("status") == "awaiting_selection"
        and partial_success
        and partial_failed,
        "partial fake provider failure kept successful candidates selectable",
        partial,
    )
    before_template = require_api_ok(
        client.request(
            "GET",
            f"/api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/tokui-template",
            token=True,
        ),
        "get template before partial select",
    )
    selected = require_api_ok(
        client.request(
            "POST",
            f"/api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/tokui-template/image-jobs/{partial_job['job_bid']}/select",
            json_body={"candidate_bid": partial_success[0]["candidate_bid"]},
            token=True,
            timeout=30,
        ),
        "select partial success candidate",
    )
    after_template = selected.get("template") or {}
    recorder.check(
        "failed_candidates_do_not_pollute_media_refs",
        len(after_template.get("media_refs") or [])
        == len(before_template.get("media_refs") or []) + 1,
        "only the selected successful candidate was appended to media_refs",
        selected,
    )

    all_fail_job = require_api_ok(
        client.request(
            "POST",
            f"/api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/tokui-template/image-jobs",
            json_body={
                "teacher_prompt": "E2E_ALL_FAIL generate no usable candidates",
                "title": "all failure",
                "candidate_count": 3,
            },
            token=True,
            timeout=20,
        ),
        "create all-fail job",
    )
    all_fail = poll_image_job(client, shifu_bid, outline_bid, all_fail_job["job_bid"])
    recorder.check(
        "all_image_candidates_failed_is_clear",
        all_fail.get("status") == "failed" and all_fail.get("error_message"),
        "all-fail fake provider job reached failed with a clear error",
        all_fail,
    )
    retry_job = require_api_ok(
        client.request(
            "POST",
            f"/api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/tokui-template/image-jobs",
            json_body={
                "teacher_prompt": "retry after all-fail succeeds",
                "title": "retry success",
                "candidate_count": 3,
                "retry_of_job_bid": all_fail_job["job_bid"],
            },
            token=True,
            timeout=20,
        ),
        "create retry job",
    )
    retry = poll_image_job(client, shifu_bid, outline_bid, retry_job["job_bid"])
    recorder.check(
        "image_retry_links_old_job_and_succeeds",
        retry.get("retry_of_job_bid") == all_fail_job["job_bid"]
        and retry.get("status") == "awaiting_selection",
        "retry job linked retry_of_job_bid and reached awaiting_selection",
        retry,
    )
    recorder.evidence["failureAndRetry"] = {
        "partial": partial,
        "allFail": all_fail,
        "retry": retry,
    }


def extract_urls_from_dsl(dsl: str) -> list[str]:
    urls: list[str] = []
    for part in dsl.split('"'):
        if part.startswith("/api/storage/courses/") and part not in urls:
            urls.append(part)
    return urls


def run_course_matrix(client: ApiClient) -> dict[str, Any]:
    recorder = ScenarioRecorder("complex_tokui_course_matrix")
    stamp = str(int(time.time() * 1000))
    ids = create_course_tree(client, stamp)
    shifu_bid = ids["shifu_bid"]
    outline_bid = ids["outline_bid"]
    recorder.evidence["ids"] = ids

    restore_payload = configure_image_provider(client, recorder)
    require_api_ok(
        client.request(
            "POST",
            f"/api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/tokui-template",
            json_body=base_template(version="1"),
            token=True,
        ),
        "save base template",
    )

    first_media = create_and_select_image(
        client,
        shifu_bid,
        outline_bid,
        "E2E_SUCCESS first process diagram",
        recorder,
        "imageJobOne",
    )
    second_media = create_and_select_image(
        client,
        shifu_bid,
        outline_bid,
        "E2E_SUCCESS second misconception diagram",
        recorder,
        "imageJobTwo",
        select_index=1,
    )
    media_refs = [first_media, second_media]
    template_v1 = base_template(media_refs=media_refs, version="1")
    guidance = require_api_ok(
        client.request(
            "POST",
            f"/api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/tokui-template/guidance",
            json_body=template_v1,
            token=True,
            timeout=60,
        ),
        "generate controlled guidance",
    )
    template_v1["prompt_template"] = guidance.get("prompt_template") or template_v1["prompt_template"]
    saved_v1 = require_api_ok(
        client.request(
            "POST",
            f"/api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/tokui-template",
            json_body=template_v1,
            token=True,
        ),
        "save template v1",
    )
    recorder.check(
        "teacher_template_has_multiple_media_refs",
        len(saved_v1.get("media_refs") or []) >= 2,
        "teacher template saved at least two media refs",
        saved_v1.get("media_refs"),
    )
    recorder.check(
        "teacher_design_has_multiple_material_placements",
        len(saved_v1.get("material_refs") or []) >= 3
        and any(
            "四类铁路实景对比短片" in str(item.get("title") or "")
            for item in saved_v1.get("material_refs") or []
            if isinstance(item, dict)
        ),
        "teacher course design persisted multiple material insertion points",
        saved_v1.get("material_refs"),
    )
    recorder.check(
        "teacher_design_has_multiple_interaction_points",
        len(saved_v1.get("interaction_points") or []) >= 3
        and any(
            item.get("blocking") is True
            for item in saved_v1.get("interaction_points") or []
            if isinstance(item, dict)
        ),
        "teacher course design persisted multiple answer-dependent checkpoints",
        saved_v1.get("interaction_points"),
    )
    recorder.check(
        "controlled_guidance_is_detailed_and_staged",
        "Stage 1" in str(guidance.get("prompt_template") or "")
        and "Stage 2" in str(guidance.get("prompt_template") or "")
        and "Stage 3" in str(guidance.get("prompt_template") or ""),
        "controlled guidance keeps multi-stage teaching structure",
        guidance,
    )
    publish_v1 = require_api_ok(
        client.request(
            "POST",
            f"/api/shifu/shifus/{shifu_bid}/publish",
            json_body={},
            token=True,
            timeout=120,
        ),
        "publish v1",
    )

    learner_1 = require_api_ok(
        client.request(
            "GET",
            f"/api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/tokui",
            token=True,
            timeout=60,
        ),
        "learner artifact one",
    )
    schema_1 = learner_1.get("interaction_schema") or []
    dsl_1 = str(learner_1.get("dsl") or "")
    dsl_urls_1 = extract_urls_from_dsl(dsl_1)
    recorder.check(
        "learner_round_one_uses_two_provided_images",
        learner_1.get("validation_status") == "validated"
        and len(schema_1) >= 3
        and len(dsl_urls_1) >= 2
        and all(url in {item.get("url") for item in media_refs} for url in dsl_urls_1),
        "round one DSL references at least two provided stored media URLs and no invented URL",
        {"dsl": dsl_1, "urls": dsl_urls_1, "schema": schema_1},
    )
    recorder.check(
        "interaction_schema_has_three_fields_and_two_types",
        len(schema_1) >= 3
        and {"text", "choice", "number"}.intersection(
            {item.get("field_type") for item in schema_1}
        )
        and len({item.get("field_type") for item in schema_1}) >= 2,
        "round one schema includes multiple fields and multiple field types",
        schema_1,
    )
    learner_1_again = require_api_ok(
        client.request(
            "GET",
            f"/api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/tokui",
            token=True,
            timeout=60,
        ),
        "learner artifact one refresh",
    )
    recorder.check(
        "refresh_reuses_same_validated_artifact",
        learner_1_again.get("reused") is True
        and learner_1_again.get("tokui_artifact_bid") == learner_1.get("tokui_artifact_bid"),
        "same template version and progress record reused the validated artifact",
        learner_1_again,
    )

    response_1 = require_api_ok(
        client.request(
            "POST",
            f"/api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/tokui/responses",
            json_body={
                "tokui_artifact_bid": learner_1.get("tokui_artifact_bid"),
                "responses": [
                    {
                        "field_id": "prior_experience",
                        "field_type": "choice",
                        "value": "worked_with_it",
                    },
                    {
                        "field_id": "concept_explanation",
                        "field_type": "text",
                        "value": "E2E_ANSWER_ONE pressure moves through the pipe first",
                    },
                    {
                        "field_id": "confidence_score",
                        "field_type": "number",
                        "value": 4,
                    },
                ],
            },
            token=True,
        ),
        "save round one responses",
    )
    recorder.check(
        "multi_input_submit_saved_all_responses",
        response_1.get("saved") == 3 and response_1.get("continue_required") is True,
        "one submit saved all three fields and requested continuation",
        response_1,
    )

    learner_2 = require_api_ok(
        client.request(
            "GET",
            f"/api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/tokui",
            token=True,
            timeout=60,
        ),
        "learner artifact two",
    )
    dsl_2 = str(learner_2.get("dsl") or "")
    recorder.check(
        "round_two_uses_round_one_answers",
        learner_2.get("tokui_artifact_bid") != learner_1.get("tokui_artifact_bid")
        and "E2E_ASSERT_ROUND_TWO" in dsl_2
        and "E2E_ANSWER_ONE" in dsl_2,
        "round two artifact changed and included first-round answer context",
        learner_2,
    )
    response_2 = require_api_ok(
        client.request(
            "POST",
            f"/api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/tokui/responses",
            json_body={
                "tokui_artifact_bid": learner_2.get("tokui_artifact_bid"),
                "responses": [
                    {
                        "field_id": "refinement_plan",
                        "field_type": "text",
                        "value": "E2E_ANSWER_TWO compare the two diagrams before giving feedback",
                    }
                ],
            },
            token=True,
        ),
        "save round two response",
    )
    recorder.check(
        "second_blocking_response_requests_continuation",
        response_2.get("saved") == 1 and response_2.get("continue_required") is True,
        "second blocking response saved and requested the third artifact",
        response_2,
    )
    learner_3 = require_api_ok(
        client.request(
            "GET",
            f"/api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/tokui",
            token=True,
            timeout=60,
        ),
        "learner artifact three",
    )
    dsl_3 = str(learner_3.get("dsl") or "")
    recorder.check(
        "round_three_uses_previous_two_rounds",
        learner_3.get("tokui_artifact_bid") != learner_2.get("tokui_artifact_bid")
        and "E2E_ASSERT_ROUND_THREE" in dsl_3
        and "E2E_ANSWER_ONE" in dsl_3
        and "E2E_ANSWER_TWO" in dsl_3,
        "third artifact included answers from both previous learner turns",
        learner_3,
    )

    template_v2 = base_template(media_refs=media_refs, version="2")
    require_api_ok(
        client.request(
            "POST",
            f"/api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/tokui-template",
            json_body=template_v2,
            token=True,
        ),
        "save template v2",
    )
    require_api_ok(
        client.request(
            "POST",
            f"/api/shifu/shifus/{shifu_bid}/publish",
            json_body={},
            token=True,
            timeout=120,
        ),
        "publish v2",
    )
    learner_v2 = require_api_ok(
        client.request(
            "GET",
            f"/api/learn/shifu/{shifu_bid}/outlines/{outline_bid}/tokui",
            token=True,
            timeout=60,
        ),
        "learner artifact after republish",
    )
    recorder.check(
        "republish_invalidates_old_artifact_cache",
        learner_v2.get("tokui_artifact_bid") != learner_3.get("tokui_artifact_bid")
        and learner_v2.get("template_hash") != learner_3.get("template_hash")
        and "E2E_TEMPLATE_MARKER:E2E_VERSION_2" in str(learner_v2.get("dsl") or ""),
        "new template hash generated a fresh artifact with v2 marker",
        learner_v2,
    )

    run_failure_and_retry_scenario(client, shifu_bid, outline_bid, recorder)

    recorder.evidence["publishV1"] = publish_v1
    recorder.evidence["learnerArtifacts"] = {
        "round1": learner_1,
        "round1Refresh": learner_1_again,
        "round2": learner_2,
        "round3": learner_3,
        "afterRepublish": learner_v2,
    }
    recorder.evidence["imageConfigRestorePayload"] = restore_payload
    return {
        "scenario": recorder.to_result(),
        "restore_payload": restore_payload,
        "ids": ids,
        "token": client.token,
    }


def make_profile() -> BrowserProfile:
    kwargs: dict[str, Any] = {
        "headless": HEADLESS,
        "allowed_domains": ["localhost", "127.0.0.1", "*"],
    }
    if Path(EDGE_PATH).exists():
        kwargs["executable_path"] = EDGE_PATH
    return BrowserProfile(**kwargs)


async def maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


async def verify_learner_browser_rendering(ids: dict[str, str], token: str) -> dict[str, Any]:
    session = BrowserSession(browser_profile=make_profile())
    learner_url = (
        f"{TARGET_URL}/e2e/tokui-render"
        f"?shifu_bid={ids['shifu_bid']}&outline_bid={ids['outline_bid']}"
    )
    try:
        await maybe_await(session.start())
        page = await maybe_await(session.get_current_page())
        await maybe_await(page.goto(TARGET_URL))
        await page.evaluate(
            """
            (...args) => {
              const token = args[0];
              try {
                localStorage.setItem('token', JSON.stringify(token));
                localStorage.setItem('token_faked', JSON.stringify(0));
                document.cookie = `token=${token}; path=/`;
              } catch {}
            }
            """,
            token,
        )
        await maybe_await(page.goto(learner_url))
        await asyncio.sleep(8)
        dom = await page.evaluate(
            """
            (...args) => {
              const shifuBid = args[0];
              const outlineBid = args[1];
              const root = document.querySelector('[data-testid="learner-tokui-block"]');
              const renderer = document.querySelector('[data-testid="tokui-renderer-root"]');
              const images = Array.from(document.querySelectorAll('[data-testid="learner-tokui-block"] img, [data-testid="learner-tokui-block"] [role="img"]'));
              const collect = async () => {
                const token = localStorage.getItem('token') || '';
                const result = {
                  href: location.href,
                  title: document.title,
                  tokenLength: token.length,
                  tokenFaked: localStorage.getItem('token_faked') || '',
                  hasLearnerTokuiBlock: Boolean(root),
                  hasRenderer: Boolean(renderer),
                  bodyText: document.body ? document.body.innerText.slice(0, 3000) : '',
                  imageCount: images.length,
                  imageSources: images.map((el) => el.getAttribute('src') || el.getAttribute('style') || '')
                };
                try {
                  result.apiConfig = await (await fetch('/api/config')).json();
                } catch (error) {
                  result.apiConfigError = String(error);
                }
                try {
                  const response = await fetch(`/api/learn/shifu/${shifuBid}/outlines/${outlineBid}/tokui`, {
                    headers: {
                      Token: token,
                      Authorization: `Bearer ${token}`,
                    },
                  });
                  result.learnerFetchStatus = response.status;
                  result.learnerFetchText = (await response.text()).slice(0, 1200);
                } catch (error) {
                  result.learnerFetchError = String(error);
                }
                return result;
              };
              return collect();
            }
            """,
            ids["shifu_bid"],
            ids["outline_bid"],
        )
        if isinstance(dom, str):
            dom = json.loads(dom)
        await maybe_await(session.take_screenshot(str(SCREENSHOT_PATH), full_page=True))
        dom["screenshot_path"] = str(SCREENSHOT_PATH)
        return dom
    finally:
        await maybe_await(session.stop())


async def main() -> int:
    validator_process = start_tokui_validator_if_needed()
    fake_provider = start_fake_image_provider()
    result: dict[str, Any] = {
        "passed": False,
        "target_url": TARGET_URL,
        "headless": HEADLESS,
        "fake_image_provider_public_url": FAKE_IMAGE_PROVIDER_PUBLIC_URL,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "scenarios": [],
    }
    restore_payload: dict[str, Any] | None = None
    client: ApiClient | None = None
    try:
        api_base_url = resolve_api_base_url(TARGET_URL)
        result["api_base_url"] = api_base_url
        client = ApiClient(api_base_url)
        login = client.login()
        if not client.token:
            raise CheckFailed(f"login failed: {login}")

        matrix = run_course_matrix(client)
        restore_payload = matrix["restore_payload"]
        result["scenarios"].append(matrix["scenario"])

        browser = await verify_learner_browser_rendering(matrix["ids"], matrix["token"])
        browser_scenario = ScenarioRecorder("learner_browser_rendering")
        browser_scenario.evidence["browser"] = browser
        try:
            browser_scenario.check(
                "learner_page_rendered_tokui_block",
                browser.get("hasLearnerTokuiBlock") and browser.get("hasRenderer"),
                "browser rendered learner TokUI block and renderer root",
                browser,
            )
            browser_scenario.check(
                "learner_browser_has_tokui_images",
                int(browser.get("imageCount") or 0) >= 2,
                "browser DOM exposes at least two TokUI-rendered media nodes",
                browser.get("imageSources"),
            )
        finally:
            result["scenarios"].append(browser_scenario.to_result())
        result["fake_image_provider_requests"] = FakeImageProviderHandler.request_count
        result["fake_image_provider_mode_counts"] = FakeImageProviderHandler.mode_counts
        result["passed"] = all(scenario.get("passed") for scenario in result["scenarios"])
    except Exception as exc:
        result.update(
            {
                "passed": False,
                "error": f"{exc.__class__.__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        if validator_process is not None:
            validator_process.terminate()
            try:
                validator_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                validator_process.kill()
        if client is not None and restore_payload is not None:
            try:
                result["imageConfigRestore"] = client.request(
                    "POST",
                    "/api/shifu/admin/operations/tokui-image/config",
                    json_body=restore_payload,
                    token=True,
                )
            except Exception as restore_exc:
                result["imageConfigRestoreError"] = str(restore_exc)
        fake_provider.shutdown()

    RESULT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "passed": result.get("passed"),
                "result_path": str(RESULT_PATH),
                "scenarios": [
                    {
                        "name": scenario.get("name"),
                        "passed": scenario.get("passed"),
                        "failed_checks": [
                            check
                            for check in scenario.get("checks", [])
                            if not check.get("passed")
                        ],
                    }
                    for scenario in result.get("scenarios", [])
                ],
                "error": result.get("error"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130)
