"""Pass O: enumerate NixOS module options via `nix eval` on optionsNix.

Produces one row per NixOS option (e.g. `services.nginx.enable`), with
type / default / example / description / declarations. This complements
Pass A which covers package derivations.

Monolithic eval: we ask nix for the full options tree as JSON in one call.
Idempotent via UNIQUE(option_path, nixpkgs_commit) — rerunning is safe.
"""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import db

log = logging.getLogger(__name__)

CHECKPOINT_EVERY = 1000
PROGRESS_LOG_EVERY = 2000


def _run_nix_eval(nixpkgs_path: Path, options_nix: Path) -> dict:
    cmd = [
        "nix-instantiate",
        "--eval",
        "--strict",
        "--json",
        "-I", f"nixpkgs={nixpkgs_path.resolve()}",
        str(options_nix),
    ]
    log.info("launching: %s", " ".join(cmd))
    proc = subprocess.run(
        cmd, capture_output=True, text=False, check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"nix-instantiate failed with rc={proc.returncode}: {err[:4000]}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        head = proc.stdout[:500].decode("utf-8", errors="replace")
        raise RuntimeError(f"nix-instantiate stdout not valid JSON: {exc}; head={head!r}")


def _row_from_option(
    path: str, meta: dict, commit: str, channel: str, now: str
) -> dict:
    # optionsNix shape varies slightly per nixpkgs version; tolerate missing keys.
    return {
        "option_path": path,
        "nixpkgs_commit": commit,
        "nixpkgs_channel": channel,
        "type": meta.get("type"),
        "default_json": db.js(meta.get("default")),
        "example_json": db.js(meta.get("example")),
        "description": meta.get("description"),
        "declarations_json": db.js(meta.get("declarations")),
        "related_packages_json": db.js(meta.get("relatedPackages")),
        "read_only": 1 if meta.get("readOnly") else 0,
        "visible": 0 if meta.get("visible") is False else 1,
        "internal": 1 if meta.get("internal") else 0,
        "scraped_at": now,
    }


def run(conn, nixpkgs_path: Path, commit: str, channel: str) -> tuple[int, int]:
    """Execute Pass O. Returns (rows_inserted, total_options_seen)."""
    resumable = db.find_resumable_run(conn, commit, "O")
    if resumable:
        run_id, _, _ = resumable
        log.info("resuming Pass O run_id=%s (idempotent — re-evaluating)", run_id)
    else:
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        run_id = db.start_run(conn, commit, channel, "O", started_at)
        log.info(
            "starting Pass O run_id=%s (commit=%s channel=%s)",
            run_id, commit[:12], channel,
        )

    try:
        options_nix = Path(__file__).resolve().parent / "options.nix"
        log.info("evaluating NixOS options tree — this takes 2–10 minutes...")
        tree = _run_nix_eval(nixpkgs_path, options_nix)
        total = len(tree)
        log.info("nix eval returned %d options", total)

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        batch: list[dict] = []
        rows_inserted = 0
        rows_seen = 0

        for path, meta in tree.items():
            if not isinstance(meta, dict):
                continue
            batch.append(_row_from_option(path, meta, commit, channel, now))
            rows_seen += 1

            if rows_seen % PROGRESS_LOG_EVERY == 0:
                log.info("progress: rows_seen=%d last=%s", rows_seen, path)

            if len(batch) >= CHECKPOINT_EVERY:
                rows_inserted += db.insert_options(conn, batch)
                db.update_run_progress(conn, run_id, path, rows_seen)
                batch.clear()

        if batch:
            rows_inserted += db.insert_options(conn, batch)

        completed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db.finish_run(conn, run_id, "done", completed_at)
        log.info("Pass O complete: rows_seen=%d rows_inserted=%d", rows_seen, rows_inserted)
        return rows_inserted, rows_seen

    except Exception as exc:
        err_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db.finish_run(conn, run_id, "failed", err_at, error=str(exc)[:2000])
        raise
