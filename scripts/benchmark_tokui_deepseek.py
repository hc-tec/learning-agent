#!/usr/bin/env python3
"""Benchmark DeepSeek streaming speed for TokUI DSL generation.

The script intentionally uses only Python's standard library so it can run from
the repository root without installing extra packages.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


TOKUI_SYSTEM_PROMPT = """You generate TokUI DSL for a learning application.
Return only TokUI DSL. No markdown fences, no prose, no HTML, no XML.

Core syntax:
- Use bracket tags: [card tt:"Title"]...[/card], [p Plain text], [btn tx:Continue v:primary].
- Attributes use key:value, never key="value". Quote values that contain spaces, colons, brackets, semicolons, or commas.
- Containers must close: card, ft, row, col, table, tbody, code, md, callout, steps, bubble, think, suggestions.
- Leaf tags do not close: h1-h6, btn, input, source, suggestion, step, chart with inline d, thead with cols, tr.
- Paragraph has two modes: plain text uses leaf [p Text] with no [/p]; block children use [p]...[/p].
- Use callout as [callout t:info tt:"Tip"]...[/callout] or [callout t:info tx:"Tip text"]. Do not invent attrs like tip:Text.
- Use table shorthand: [table][thead cols:"Name,Score"][tbody][tr Alice,90][/tbody][/table]. Never use th or td.
- Use form choice shorthand: [radio n:q1 l:"Question" opt:"a:Option A;b:Option B"]. Do not output [opt]...[/opt].
- Use chart shorthand: [chart t:scatter l:"1h,2h,3h" d:"55,65,80"].
- Avoid literal [ or ] in normal text. Use parentheses for arrays, e.g. (1, 3, 5). Brackets are allowed inside code/md raw containers.
- Avoid ASCII Q: or A: prefixes in body text; use full-width Q： or quote the body.
- If using think, write a brief visible reasoning summary only. Do not reveal hidden chain-of-thought.
"""


PROMPTS = [
    {
        "name": "short_card",
        "prompt": (
            "Create one compact learning card that explains Python variables "
            "to a beginner. Required tags: card, h3, p, code, callout. "
            "Canonical shape: [card tt:\"Python Variables\"][h3 Title]"
            "[p Text][code lang:python]x = 1[/code]"
            "[callout t:info tx:\"Tip text\"][/card]"
        ),
    },
    {
        "name": "quiz_card",
        "prompt": (
            "Create one interactive quiz card about HTTP status codes. "
            "Required tags: card, p, radio, ft, btn. Use exactly this radio "
            "style: [radio n:status l:\"Which status means success?\" "
            "opt:\"200:OK;404:Not Found;500:Server Error\"]. Put buttons "
            "inside [ft]...[/ft]."
        ),
    },
    {
        "name": "lesson_steps",
        "prompt": (
            "Create a three-step mini lesson about binary search. Required "
            "tags: card, steps, step, p, callout, code, quick-reply. Step "
            "shape: [steps v:2][step tt:\"Step 1\" desc:\"Find middle\"]"
            "[step tt:\"Step 2\" desc:\"Choose half\"][/steps]. "
            "Important: step is a leaf tag; never write [/step], and never "
            "put p/callout/code inside a step. Put explanations after the "
            "closed steps block. "
            "Quick reply shape: [quick-reply items:\"Trace it|Show code|Quiz me\"]. "
            "In paragraph text, write arrays with parentheses like (1, 3, 5), "
            "not square brackets. Keep it under 900 characters."
        ),
    },
    {
        "name": "data_chart",
        "prompt": (
            "Create a data explanation about study time versus quiz score. "
            "Required tags: card, p, chart, table, thead, tbody, tr. Use "
            "chart shape [chart t:scatter l:\"1h,2h,3h\" d:\"55,65,80\"] "
            "and table shape [table][thead cols:\"Hours,Score\"][tbody]"
            "[tr 1,55][tr 2,65][/tbody][/table]."
        ),
    },
    {
        "name": "tutor_bubble",
        "prompt": (
            "Create one AI tutor chat response about recursion. Required tags: "
            "bubble, think, p, source, suggestions, suggestion. Use bubble "
            "shape [bubble role:ai]...[/bubble]. The think block must be a "
            "short learner-facing plan summary, not hidden chain-of-thought. "
            "Do not use md or markdown code fences. "
            "Use source leaf shape "
            "[source n:1 tt:\"SICP\" sn:\"Classic CS text\" u:#]. Use "
            "suggestions shape [suggestions][suggestion tt:Trace tx:\"Try "
            "factorial(3)\" clk:trace][/suggestions]."
        ),
    },
]


def load_env_file(path: Path) -> bool:
    """Load simple KEY=VALUE lines without overwriting existing environment."""

    if not path.exists() or not path.is_file():
      return False

    loaded = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in ("'", '"')
        ):
            value = value[1:-1]
        os.environ[key] = value
        loaded = True
    return loaded


def load_default_env_files(repo_root: Path) -> list[str]:
    """Load likely local env files and return paths loaded."""

    candidates = [
        repo_root / ".env",
        repo_root.parent / ".env",
        repo_root / "docker" / ".env",
    ]
    loaded_paths = []
    for candidate in candidates:
        if load_env_file(candidate):
            loaded_paths.append(str(candidate))
    return loaded_paths


@dataclass
class BenchmarkResult:
    prompt_name: str
    run_index: int
    model: str
    ok: bool
    status: int | None
    error: str | None
    ttfb_ms: float | None
    first_content_ms: float | None
    first_tokui_tag_ms: float | None
    total_ms: float | None
    output_chars: int
    chunks: int
    chars_per_second: float | None
    contains_code_fence: bool
    bracket_balance: int
    starts_with_tokui_tag: bool
    contains_equals_attrs: bool
    contains_html_table_tags: bool
    invalid_leaf_closing_count: int
    output_preview: str
    output_text: str


def _build_payload(model: str, prompt: str, max_tokens: int) -> dict[str, Any]:
    return {
        "model": model,
        "stream": True,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": TOKUI_SYSTEM_PROMPT,
            },
            {"role": "user", "content": prompt},
        ],
        # DeepSeek exposes thinking-mode controls through OpenAI-compatible
        # request bodies. If a model ignores this field, it should be harmless.
        "thinking": {"type": "disabled"},
    }


def _extract_delta_content(event_payload: dict[str, Any]) -> str:
    choices = event_payload.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    return content if isinstance(content, str) else ""


def run_one(
    *,
    api_key: str,
    base_url: str,
    model: str,
    prompt_name: str,
    prompt: str,
    run_index: int,
    timeout: int,
    max_tokens: int,
) -> BenchmarkResult:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    payload = _build_payload(model, prompt, max_tokens)
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )

    started_at = time.perf_counter()
    ttfb_ms: float | None = None
    first_content_ms: float | None = None
    first_tokui_tag_ms: float | None = None
    output_parts: list[str] = []
    chunks = 0
    status: int | None = None

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            for raw_line in response:
                now = time.perf_counter()
                if ttfb_ms is None:
                    ttfb_ms = (now - started_at) * 1000

                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue

                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    break

                try:
                    event_payload = json.loads(data)
                except json.JSONDecodeError:
                    continue

                content = _extract_delta_content(event_payload)
                if not content:
                    continue

                chunks += 1
                if first_content_ms is None:
                    first_content_ms = (now - started_at) * 1000
                output_parts.append(content)
                if first_tokui_tag_ms is None and "[" in "".join(output_parts):
                    first_tokui_tag_ms = (now - started_at) * 1000

        total_ms = (time.perf_counter() - started_at) * 1000
        output = "".join(output_parts)
        chars_per_second = (
            len(output) / (total_ms / 1000) if total_ms and total_ms > 0 else None
        )
        return BenchmarkResult(
            prompt_name=prompt_name,
            run_index=run_index,
            model=model,
            ok=True,
            status=status,
            error=None,
            ttfb_ms=ttfb_ms,
            first_content_ms=first_content_ms,
            first_tokui_tag_ms=first_tokui_tag_ms,
            total_ms=total_ms,
            output_chars=len(output),
            chunks=chunks,
            chars_per_second=chars_per_second,
            contains_code_fence="```" in output,
            bracket_balance=output.count("[") - output.count("]"),
            starts_with_tokui_tag=output.lstrip().startswith("["),
            contains_equals_attrs=bool(
                re.search(
                    r"\[[a-z][a-z0-9-]*(?:\s+[a-z][\w-]*:(?:\"[^\"]*\"|[^\s\]]+))*\s+[a-z][\w-]*=",
                    output,
                )
            ),
            contains_html_table_tags=bool(re.search(r"\[/?(?:th|td)\b", output)),
            invalid_leaf_closing_count=len(
                re.findall(
                    r"\[/(?:h[1-6]|btn|input|pwd|source|suggestion|chart|thead|tr|opt)\]",
                    output,
                )
            ),
            output_preview=output[:500],
            output_text=output,
        )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        total_ms = (time.perf_counter() - started_at) * 1000
        return BenchmarkResult(
            prompt_name=prompt_name,
            run_index=run_index,
            model=model,
            ok=False,
            status=exc.code,
            error=body[:1000],
            ttfb_ms=ttfb_ms,
            first_content_ms=first_content_ms,
            first_tokui_tag_ms=first_tokui_tag_ms,
            total_ms=total_ms,
            output_chars=0,
            chunks=chunks,
            chars_per_second=None,
            contains_code_fence=False,
            bracket_balance=0,
            starts_with_tokui_tag=False,
            contains_equals_attrs=False,
            contains_html_table_tags=False,
            invalid_leaf_closing_count=0,
            output_preview="",
            output_text="",
        )
    except Exception as exc:  # noqa: BLE001 - benchmark should report failures.
        total_ms = (time.perf_counter() - started_at) * 1000
        return BenchmarkResult(
            prompt_name=prompt_name,
            run_index=run_index,
            model=model,
            ok=False,
            status=status,
            error=str(exc),
            ttfb_ms=ttfb_ms,
            first_content_ms=first_content_ms,
            first_tokui_tag_ms=first_tokui_tag_ms,
            total_ms=total_ms,
            output_chars=0,
            chunks=chunks,
            chars_per_second=None,
            contains_code_fence=False,
            bracket_balance=0,
            starts_with_tokui_tag=False,
            contains_equals_attrs=False,
            contains_html_table_tags=False,
            invalid_leaf_closing_count=0,
            output_preview="",
            output_text="",
        )


def _avg(values: list[float | None]) -> float | None:
    numeric = [value for value in values if value is not None]
    if not numeric:
        return None
    return sum(numeric) / len(numeric)


def summarize(results: list[BenchmarkResult]) -> dict[str, Any]:
    successful = [result for result in results if result.ok]
    return {
        "total_runs": len(results),
        "successful_runs": len(successful),
        "failed_runs": len(results) - len(successful),
        "avg_ttfb_ms": _avg([result.ttfb_ms for result in successful]),
        "avg_first_content_ms": _avg(
            [result.first_content_ms for result in successful]
        ),
        "avg_first_tokui_tag_ms": _avg(
            [result.first_tokui_tag_ms for result in successful]
        ),
        "avg_total_ms": _avg([result.total_ms for result in successful]),
        "avg_chars_per_second": _avg(
            [result.chars_per_second for result in successful]
        ),
        "code_fence_runs": sum(1 for result in successful if result.contains_code_fence),
        "unbalanced_bracket_runs": sum(
            1 for result in successful if result.bracket_balance != 0
        ),
        "non_tokui_prefix_runs": sum(
            1 for result in successful if not result.starts_with_tokui_tag
        ),
        "equals_attr_runs": sum(
            1 for result in successful if result.contains_equals_attrs
        ),
        "html_table_tag_runs": sum(
            1 for result in successful if result.contains_html_table_tags
        ),
        "invalid_leaf_closing_runs": sum(
            1 for result in successful if result.invalid_leaf_closing_count > 0
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark DeepSeek streaming speed for TokUI DSL generation."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument(
        "--out",
        default="docs/generated/tokui-deepseek-benchmark.json",
        help="Output JSON path, relative to repository root by default.",
    )
    parser.add_argument(
        "--prompt",
        choices=[item["name"] for item in PROMPTS],
        help="Run only one prompt class.",
    )
    parser.add_argument(
        "--env-file",
        action="append",
        help=(
            "Optional .env file to load before reading DEEPSEEK_API_KEY. "
            "Can be passed multiple times."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    loaded_env_files = load_default_env_files(repo_root)
    for env_file in args.env_file or []:
        if load_env_file(Path(env_file)):
            loaded_env_files.append(env_file)

    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print(
            "DEEPSEEK_API_KEY is not set. Set it before running the benchmark "
            "or pass --env-file.",
            file=sys.stderr,
        )
        return 2

    selected_prompts = PROMPTS
    if args.prompt:
        selected_prompts = [item for item in PROMPTS if item["name"] == args.prompt]

    results: list[BenchmarkResult] = []
    for prompt_item in selected_prompts:
        for run_index in range(1, args.runs + 1):
            print(
                f"Running {prompt_item['name']} #{run_index} with {args.model}...",
                flush=True,
            )
            result = run_one(
                api_key=api_key,
                base_url=args.base_url,
                model=args.model,
                prompt_name=prompt_item["name"],
                prompt=prompt_item["prompt"],
                run_index=run_index,
                timeout=args.timeout,
                max_tokens=args.max_tokens,
            )
            results.append(result)
            print(
                json.dumps(
                    {
                        "prompt": result.prompt_name,
                        "ok": result.ok,
                        "ttfb_ms": result.ttfb_ms,
                        "first_content_ms": result.first_content_ms,
                        "total_ms": result.total_ms,
                        "output_chars": result.output_chars,
                        "chars_per_second": result.chars_per_second,
                        "status": result.status,
                        "error": result.error,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    payload = {
        "model": args.model,
        "base_url": args.base_url,
        "loaded_env_files": loaded_env_files,
        "created_at_unix": int(time.time()),
        "summary": summarize(results),
        "results": [asdict(result) for result in results],
    }

    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote benchmark results to {output_path}")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
