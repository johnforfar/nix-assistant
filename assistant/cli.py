#!/usr/bin/env python3
"""nix-assistant CLI — review a Nix config file.

Usage:
  python cli.py configuration.nix
  python cli.py flake.nix --model qwen2.5-coder:3b
  cat config.nix | python cli.py -
  python cli.py --embed            # build/update the vector index first
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file", nargs="?", default="-",
                    help="path to .nix file or - for stdin")
    ap.add_argument("--model", default=os.environ.get("NIX_ASSISTANT_MODEL", "qwen2.5-coder:3b"))
    ap.add_argument("--ollama", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    ap.add_argument("--json", dest="as_json", action="store_true",
                    help="output raw JSON instead of formatted text")
    ap.add_argument("--embed", action="store_true",
                    help="build/update embedding index and exit")
    args = ap.parse_args(argv)

    if args.embed:
        from assistant.embed import main as embed_main
        return embed_main([])

    if args.file == "-":
        source = sys.stdin.read()
    else:
        p = Path(args.file)
        if not p.exists():
            print(f"error: file not found: {p}", file=sys.stderr)
            return 2
        source = p.read_text(encoding="utf-8")

    from assistant.review import review

    try:
        comments = review(source, ollama_url=args.ollama, llm_model=args.model)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.as_json:
        import json
        print(json.dumps([
            {"line": c.line, "severity": c.severity, "message": c.message}
            for c in comments
        ], indent=2))
        return 0

    if not comments:
        print("No issues found.")
        return 0

    fname = args.file if args.file != "-" else "<stdin>"
    for c in comments:
        loc = f"{fname}:{c.line}" if c.line else fname
        icon = {"error": "✗", "warning": "⚠", "hint": "ℹ"}.get(c.severity, "·")
        print(f"{icon}  {loc}  [{c.severity}]  {c.message}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
