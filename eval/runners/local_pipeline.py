"""Run the nix-assistant pipeline locally via `assistant.review`.

Imports the live-site pipeline directly from `../../repo/assistant/` so we're
benchmarking the same code path the xnode runs, with a swappable model.
This avoids network round-trips (local is ~5-15s per call vs. ~20s+ for
the live xnode) and lets us benchmark any Ollama-hosted model against the
same test set.

Requires:
  - Ollama running at OLLAMA_URL (default http://localhost:11434)
  - The chosen LLM pulled: e.g. `ollama pull qwen2.5-coder:1.5b`
  - `nomic-embed-text` (or `nomic-embed-text:v1.5`) pulled for RAG
  - `data/embeddings/` present at the project root

Configuration via env vars:
  - NIX_ASSISTANT_MODEL  (default: "qwen2.5-coder:1.5b")
  - OLLAMA_URL           (default: "http://localhost:11434")
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Ensure retrieve.py finds our embeddings before we import the package
_PROJ_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("NIX_ASSISTANT_DATA", str(_PROJ_ROOT / "data"))

_REPO_PATH = _PROJ_ROOT / "repo"
if str(_REPO_PATH) not in sys.path:
    sys.path.insert(0, str(_REPO_PATH))

try:
    from assistant import review as _assistant_review  # noqa: E402
    _IMPORT_ERROR: str | None = None
except Exception as e:
    _assistant_review = None
    _IMPORT_ERROR = f"{type(e).__name__}: {e}"


DEFAULT_MODEL = os.environ.get("NIX_ASSISTANT_MODEL", "qwen2.5-coder:1.5b")
DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")


@dataclass
class RunResult:
    ok: bool
    http_status: int | None
    raw_response: str
    parsed_comments: list[dict] | None
    latency_ms: float
    error: str | None


def run_one(source: str) -> RunResult:
    if _assistant_review is None:
        return RunResult(False, None, "", None, 0.0,
                         f"import failed: {_IMPORT_ERROR}")
    t0 = time.monotonic()
    try:
        comments = _assistant_review.review(
            source,
            ollama_url=DEFAULT_OLLAMA_URL,
            llm_model=DEFAULT_MODEL,
        )
    except Exception as e:
        latency_ms = (time.monotonic() - t0) * 1000
        return RunResult(False, None, "", None, latency_ms,
                         f"{type(e).__name__}: {e}")
    latency_ms = (time.monotonic() - t0) * 1000

    parsed = [
        {"line": c.line, "severity": c.severity, "message": c.message}
        for c in comments
    ]
    raw = json.dumps({"comments": parsed})
    return RunResult(True, 200, raw, parsed, latency_ms, None)
