"""Pass A: enumerate every nixpkgs attribute via `nix-env -qaP --json --meta`.

Writes the nix-env JSON to a tmpfile, then loads and inserts in batches.
Resumable: skips attrs whose (attr_path, nixpkgs_commit) is already in SQLite
and updates scrape_runs with progress cursor every CHECKPOINT_EVERY rows.
"""
from __future__ import annotations

import json
import logging
import signal
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import db

log = logging.getLogger(__name__)

CHECKPOINT_EVERY = 500
PROGRESS_LOG_EVERY = 1000


def _run_nix_env(nixpkgs_path: Path, out_path: Path) -> None:
    """Run `nix-env -qaP --json --meta` pinned to x86_64-linux and write
    stdout to out_path. System is pinned so macOS hosts can evaluate the
    Linux package set the NixOS audience actually uses — and so we avoid
    macOS-specific stdenv bootstrap traps in variants.nix.
    """
    cmd = [
        "nix-env",
        "-f", str(nixpkgs_path),
        "-qaP",
        "--json",
        "--meta",
        "--argstr", "system", "x86_64-linux",
        "--arg", "config",
        "{ allowAliases = false; allowBroken = true; allowUnfree = true; }",
    ]
    log.info("launching: %s (this takes 20-60 min; log progress every %d rows)",
             " ".join(cmd), PROGRESS_LOG_EVERY)
    with out_path.open("wb") as f:
        proc = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"nix-env failed with rc={proc.returncode}: {err[:2000]}")
    log.info("nix-env finished, output size=%d bytes", out_path.stat().st_size)


def _position_to_relpath(position: str | None, nixpkgs_root: Path) -> str | None:
    if not position:
        return None
    # position is "<abs-path>:<line>" or just "<abs-path>"
    path_part = position.rsplit(":", 1)[0]
    try:
        return str(Path(path_part).resolve().relative_to(nixpkgs_root.resolve()))
    except ValueError:
        return path_part


def _row_from_entry(
    attr_path: str, entry: dict, commit: str, channel: str, nixpkgs_root: Path, now: str
) -> dict:
    meta = entry.get("meta") or {}
    name = entry.get("name", "") or ""
    pname = entry.get("pname")
    version = entry.get("version")
    if pname is None and name:
        # Fallback: split "<pname>-<version>" heuristically on last "-<digit>"
        import re
        m = re.match(r"^(.*?)-(\d[\w.\-+]*)$", name)
        if m:
            pname, version = m.group(1), m.group(2)
        else:
            pname = name
    return {
        "attr_path": attr_path,
        "pname": pname,
        "version": version,
        "nixpkgs_commit": commit,
        "nixpkgs_channel": channel,
        "source_file_path": _position_to_relpath(meta.get("position"), nixpkgs_root),
        "source_file_sha256": None,
        "source_file_contents": None,
        "description": meta.get("description"),
        "license_json": db.js(meta.get("license")),
        "maintainers_json": db.js(meta.get("maintainers")),
        "homepage": meta.get("homepage") if isinstance(meta.get("homepage"), str) else db.js(meta.get("homepage")),
        "platforms_json": db.js(meta.get("platforms")),
        "build_inputs_json": None,
        "native_build_inputs_json": None,
        "propagated_inputs_json": None,
        "scraped_at": now,
    }


class _Stopped(Exception):
    pass


def run(
    conn,
    nixpkgs_path: Path,
    commit: str,
    channel: str,
) -> tuple[int, int]:
    """Execute Pass A. Returns (rows_inserted, rows_skipped_resume)."""
    resumable = db.find_resumable_run(conn, commit, "A")
    if resumable:
        run_id, last_attr, rows_already = resumable
        log.info(
            "resuming Pass A run_id=%s, %d rows already processed, cursor=%s",
            run_id, rows_already, last_attr,
        )
    else:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        run_id = db.start_run(conn, commit, channel, "A", now)
        last_attr, rows_already = None, 0
        log.info("starting Pass A run_id=%s (commit=%s channel=%s)", run_id, commit[:12], channel)

    stop_requested = {"flag": False}

    def _on_sigint(signum, frame):
        log.warning("SIGINT received, will pause after next checkpoint")
        stop_requested["flag"] = True

    prior_handler = signal.signal(signal.SIGINT, _on_sigint)

    batch: list[dict] = []
    rows_inserted = 0
    rows_seen = rows_already
    current_attr: str | None = last_attr

    def _flush():
        nonlocal rows_inserted, current_attr
        if not batch:
            return
        inserted = db.insert_packages(conn, batch)
        rows_inserted += inserted
        if current_attr is not None:
            db.update_run_progress(conn, run_id, current_attr, rows_seen)
        batch.clear()

    try:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        # Pass A is a single `nix-env -qa` run that produces a big JSON blob;
        # we buffer to a tmpfile so memory usage is the dict we load (~500 MB),
        # not the dict-plus-stream that ijson would hold.
        with tempfile.NamedTemporaryFile(
            prefix="nix-env-", suffix=".json", delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
        try:
            _run_nix_env(nixpkgs_path, tmp_path)
            log.info("loading nix-env JSON into memory for iteration...")
            with tmp_path.open("r") as f:
                all_entries = json.load(f)
        finally:
            tmp_path.unlink(missing_ok=True)

        log.info("nix-env returned %d top-level attrs", len(all_entries))
        skipping = last_attr is not None

        for attr_path, entry in all_entries.items():
            if skipping:
                if attr_path == last_attr:
                    skipping = False
                continue

            if not isinstance(entry, dict):
                continue

            row = _row_from_entry(attr_path, entry, commit, channel, nixpkgs_path, now)
            batch.append(row)
            rows_seen += 1
            current_attr = attr_path

            if rows_seen % PROGRESS_LOG_EVERY == 0:
                log.info("progress: rows_seen=%d last_attr=%s", rows_seen, attr_path)

            if len(batch) >= CHECKPOINT_EVERY:
                _flush()
                if stop_requested["flag"]:
                    raise _Stopped()

        _flush()
        now_done = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db.finish_run(conn, run_id, "done", now_done)
        log.info("Pass A complete: rows_seen=%d rows_inserted=%d", rows_seen, rows_inserted)
        return rows_inserted, rows_already

    except _Stopped:
        _flush()
        db.pause_run(conn, run_id, current_attr)
        log.warning("Pass A paused at cursor=%s, rerun to resume", current_attr)
        raise KeyboardInterrupt()

    except Exception as exc:
        now_err = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db.finish_run(conn, run_id, "failed", now_err, error=str(exc)[:2000])
        raise

    finally:
        signal.signal(signal.SIGINT, prior_handler)
