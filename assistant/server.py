"""Flask HTTP server for nix-assistant.

POST /review
  Body: { "source": "<nix config string>" }
  Returns: { "comments": [{"line": int, "severity": str, "message": str}] }

GET /health
  Returns: { "status": "ok", "model": "<llm_model>" }

Usage:
  python server.py
  python server.py --host 0.0.0.0 --port 7860 --model qwen2.5-coder:3b
"""
from __future__ import annotations

import argparse
import os

from assistant.review import review


MAX_SOURCE_BYTES = 128 * 1024  # 128 KB — generous for any real config file


def create_app(model: str, ollama_url: str):
    from flask import Flask, jsonify, request

    app = Flask("nix-assistant")
    app.config["MAX_CONTENT_LENGTH"] = MAX_SOURCE_BYTES + 1024

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
        except Exception as e:
            import logging
            logging.getLogger("nix-assistant").exception("review failed")
            return jsonify({"error": "review failed — check server logs"}), 500

    @app.get("/health")
    def _health():
        return jsonify({"status": "ok", "model": model})

    return app


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--model", default=os.environ.get("NIX_ASSISTANT_MODEL", "llama3.2:1b"))
    ap.add_argument("--ollama", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    args = ap.parse_args(argv)

    app = create_app(args.model, args.ollama)
    print(f"nix-assistant listening on {args.host}:{args.port}  model={args.model}")
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
