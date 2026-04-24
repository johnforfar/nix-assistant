"""Flask HTTP server for nix-assistant.

POST /api/review
  Body: { "source": "<nix config string>" }
  Returns: { "comments": [{"line": int, "severity": str, "message": str}] }

GET /api/feedback/challenge
  Returns: { "id": "<uuid>", "prompt": "<word arithmetic question>" }

POST /api/feedback
  Body: { "challenge_id": str, "answer": int, "name": str?, "message": str }
  Returns: { "ok": true } | { "error": str }

GET /health
  Returns: { "status": "ok", "model": "<llm_model>" }

Usage:
  python server.py
  python server.py --host 0.0.0.0 --port 7860 --model qwen2.5-coder:3b
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import time
import unicodedata
import uuid
from pathlib import Path
from random import randint
from threading import Lock

from assistant.review import review


MAX_SOURCE_BYTES = 128 * 1024  # 128 KB — generous for any real config file
MAX_MSG_BYTES    = 2000        # feedback message cap
MAX_NAME_BYTES   = 80
CHALLENGE_TTL_S  = 600
FEEDBACK_HOURLY  = 3           # per-IP rate limit

# Input hardening: strip C0/C1 control chars (except \t \n), strip bidi/ZW,
# reject obvious web-vector strings. Everything is stored as plain text and
# JSON-escaped by Flask's jsonify on read — storage is inert.
_BAD_CTRL = re.compile(r"[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]")
_BAD_BIDI = re.compile(r"[​-‍‪-‮⁦-⁩﻿]")
_XSS_LIKE = re.compile(
    r"<\s*(?:script|iframe|object|embed|meta|style|link|svg|img|on\w+\s*=)"
    r"|javascript\s*:|data\s*:\s*text|vbscript\s*:|expression\s*\(",
    re.IGNORECASE,
)

_NUM_WORDS = {1:"one",2:"two",3:"three",4:"four",5:"five",6:"six",7:"seven",8:"eight",9:"nine"}

# Challenge + rate-limit state (single-process Flask, so in-memory is fine).
_CHALLENGES: dict[str, tuple[int, float]] = {}  # id -> (answer, expires_ts)
_CHALLENGE_LOCK = Lock()
_DB_LOCK = Lock()


def _sanitize_text(s, max_bytes: int) -> str:
    if not isinstance(s, str):
        return ""
    s = _BAD_CTRL.sub("", s)
    s = _BAD_BIDI.sub("", s)
    s = unicodedata.normalize("NFKC", s).strip()
    # cap at bytes, not chars (multi-byte UTF-8 honored)
    b = s.encode("utf-8")[:max_bytes]
    # avoid leaving a dangling partial codepoint at the trim boundary
    return b.decode("utf-8", errors="ignore")


def _looks_malicious(s: str) -> bool:
    return bool(_XSS_LIKE.search(s))


def _client_ip(request) -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return (request.remote_addr or "unknown")[:64]


def _feedback_db_path() -> Path:
    base = os.environ.get("NIX_ASSISTANT_DATA", ".")
    return Path(base) / "feedback.db"


def _init_feedback_db() -> None:
    db = _feedback_db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    with _DB_LOCK, sqlite3.connect(db) as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT DEFAULT (datetime('now')),
                ip TEXT NOT NULL,
                user_agent TEXT,
                name TEXT,
                message TEXT NOT NULL
            )"""
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_feedback_ip_time ON feedback(ip, created_at)")


def create_app(model: str, ollama_url: str):
    from flask import Flask, jsonify, request

    app = Flask("nix-assistant")
    app.config["MAX_CONTENT_LENGTH"] = MAX_SOURCE_BYTES + 1024

    try:
        _init_feedback_db()
    except Exception:
        # Don't crash the app if feedback DB can't initialize; review endpoint
        # still needs to work.
        import logging
        logging.getLogger("nix-assistant").exception("feedback DB init failed")

    @app.post("/api/review")
    def _review():
        body = request.get_json(silent=True) or {}
        source = body.get("source", "")
        if not source.strip():
            return jsonify({"error": "source is required"}), 400
        if len(source.encode()) > MAX_SOURCE_BYTES:
            return jsonify({"error": "source too large (max 128 KB)"}), 413
        try:
            comments = review(source, ollama_url=ollama_url, llm_model=model)
            return jsonify({"comments": [
                {"line": c.line, "severity": c.severity, "message": c.message}
                for c in comments
            ]})
        except Exception:
            import logging
            logging.getLogger("nix-assistant").exception("review failed")
            return jsonify({"error": "review failed — check server logs"}), 500

    @app.get("/api/feedback/challenge")
    def _feedback_challenge():
        # Random arithmetic challenge; answer lives server-side only.
        a, b = randint(1, 9), randint(1, 9)
        if randint(0, 1):
            prompt = f"what is {_NUM_WORDS[a]} plus {_NUM_WORDS[b]}?"
            answer = a + b
        else:
            if a < b: a, b = b, a
            prompt = f"what is {_NUM_WORDS[a]} minus {_NUM_WORDS[b]}?"
            answer = a - b
        cid = uuid.uuid4().hex
        with _CHALLENGE_LOCK:
            # Purge expired challenges to keep the map small
            now = time.time()
            for k in [k for k, v in _CHALLENGES.items() if v[1] < now]:
                _CHALLENGES.pop(k, None)
            _CHALLENGES[cid] = (answer, now + CHALLENGE_TTL_S)
        return jsonify({"id": cid, "prompt": prompt})

    @app.post("/api/feedback")
    def _feedback():
        body = request.get_json(silent=True) or {}
        cid  = body.get("challenge_id", "")
        ans  = body.get("answer", None)
        name = _sanitize_text(body.get("name") or "", MAX_NAME_BYTES)
        msg  = _sanitize_text(body.get("message") or "", MAX_MSG_BYTES)

        if not msg:
            return jsonify({"error": "message is required"}), 400
        if _looks_malicious(msg) or _looks_malicious(name):
            return jsonify({"error": "message contains disallowed content"}), 400

        # Verify challenge (use up — one shot).
        with _CHALLENGE_LOCK:
            c = _CHALLENGES.pop(cid, None)
        if not c or c[1] < time.time():
            return jsonify({"error": "challenge expired — reload the page"}), 400
        try:
            if int(ans) != c[0]:
                return jsonify({"error": "challenge answer wrong"}), 400
        except (TypeError, ValueError):
            return jsonify({"error": "invalid answer"}), 400

        ip = _client_ip(request)
        ua = (request.headers.get("User-Agent") or "")[:200]

        # Rate limit + insert in one transaction.
        try:
            with _DB_LOCK, sqlite3.connect(_feedback_db_path()) as c:
                n = c.execute(
                    "SELECT COUNT(*) FROM feedback WHERE ip = ? AND created_at > datetime('now', '-1 hour')",
                    (ip,),
                ).fetchone()[0]
                if n >= FEEDBACK_HOURLY:
                    return jsonify({"error": f"rate limited ({FEEDBACK_HOURLY}/hour per ip)"}), 429
                c.execute(
                    "INSERT INTO feedback (ip, user_agent, name, message) VALUES (?, ?, ?, ?)",
                    (ip, ua, name, msg),
                )
        except Exception:
            import logging
            logging.getLogger("nix-assistant").exception("feedback store failed")
            return jsonify({"error": "could not save feedback"}), 500

        return jsonify({"ok": True})

    @app.get("/health")
    def _health():
        return jsonify({"status": "ok", "model": model})

    return app


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default=os.environ.get("BIND_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "7860")))
    ap.add_argument("--model", default=os.environ.get("NIX_ASSISTANT_MODEL", "llama3.2:1b"))
    ap.add_argument("--ollama", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    args = ap.parse_args(argv)

    app = create_app(args.model, args.ollama)
    print(f"nix-assistant listening on {args.host}:{args.port}  model={args.model}")
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
