"""Runner that hits the live nix-assistant deployment.

Treats the xnode as a black box: we POST the source, get back {comments: [...]}.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_URL = "https://nix-assistant.build.openmesh.cloud/api/review"
DEFAULT_TIMEOUT_S = 240  # live site is CPU-only, cold starts can exceed 60s


@dataclass
class RunResult:
    ok: bool
    http_status: int | None
    raw_response: str
    parsed_comments: list[dict] | None
    latency_ms: float
    error: str | None


def run_one(source: str, url: str = DEFAULT_URL, timeout_s: int = DEFAULT_TIMEOUT_S) -> RunResult:
    body = json.dumps({"source": source}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        return RunResult(False, e.code, raw, None, (time.monotonic() - t0) * 1000, f"HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError) as e:
        return RunResult(False, None, "", None, (time.monotonic() - t0) * 1000, str(e))
    latency_ms = (time.monotonic() - t0) * 1000

    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError as e:
        return RunResult(False, status, raw, None, latency_ms, f"response not JSON: {e}")

    if isinstance(data, dict) and "error" in data:
        return RunResult(False, status, raw, None, latency_ms, f"api error: {data['error']}")

    comments = data.get("comments") if isinstance(data, dict) else None
    if not isinstance(comments, list):
        return RunResult(False, status, raw, None, latency_ms, "response missing 'comments' array")

    return RunResult(True, status, raw, comments, latency_ms, None)
