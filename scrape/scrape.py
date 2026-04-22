#!/usr/bin/env python3
"""CLI entrypoint for the nix-corpus scraper.

Usage:
  python scrape.py --pass A [--nixpkgs <path>] [--channel unstable]
  python scrape.py --status

Passes A/B/C operate on a SQLite DB (data/corpus.db) and are independently
resumable: kill the process, rerun with the same --pass, it picks up from
the last checkpoint.
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from src import db
from src import pass_a_enumerate
from src import pass_o_options

ROOT = Path(__file__).resolve().parent
DEFAULT_NIXPKGS = ROOT / "data" / "nixpkgs"
DEFAULT_DB = ROOT / "data" / "corpus.db"
LOG_DIR = ROOT / "logs"


def _setup_logging(pass_name: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"pass_{pass_name.lower()}.log"
    handlers = [
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


def _nixpkgs_commit(nixpkgs_path: Path) -> str:
    r = subprocess.run(
        ["git", "-C", str(nixpkgs_path), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    return r.stdout.strip()


def _status(db_path: Path) -> int:
    if not db_path.exists():
        print(f"no corpus.db at {db_path}")
        return 0
    conn = db.connect(db_path)
    print("=== scrape_runs ===")
    rows = conn.execute(
        """
        SELECT id, substr(nixpkgs_commit,1,12), nixpkgs_channel, pass, status,
               rows_processed, substr(started_at,1,19), substr(completed_at,1,19), last_attr
        FROM scrape_runs ORDER BY id DESC LIMIT 10
        """
    ).fetchall()
    if not rows:
        print("(no runs yet)")
    for r in rows:
        print(f"  id={r[0]} commit={r[1]} ch={r[2]} pass={r[3]} status={r[4]} "
              f"rows={r[5]} started={r[6]} done={r[7] or '—'} cursor={r[8]}")

    for table in ("packages", "nixos_options"):
        print(f"=== {table} ===")
        total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  total rows: {total}")
        rows = conn.execute(
            f"""
            SELECT substr(nixpkgs_commit,1,12), nixpkgs_channel, COUNT(*)
            FROM {table} GROUP BY nixpkgs_commit, nixpkgs_channel ORDER BY 3 DESC
            """
        ).fetchall()
        for c, ch, n in rows:
            print(f"    {c} ({ch}): {n}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pass", dest="pass_name", choices=["A", "B", "C", "O"],
                    help="which pass to run (A=packages, O=NixOS options, B=sources, C=deps)")
    ap.add_argument("--status", action="store_true",
                    help="print scrape status and exit")
    ap.add_argument("--nixpkgs", type=Path, default=DEFAULT_NIXPKGS,
                    help=f"path to nixpkgs clone (default: {DEFAULT_NIXPKGS})")
    ap.add_argument("--channel", default="unstable",
                    help="nixpkgs channel label (default: unstable)")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB,
                    help=f"sqlite db path (default: {DEFAULT_DB})")
    args = ap.parse_args(argv)

    if args.status:
        return _status(args.db)

    if not args.pass_name:
        ap.error("must specify --pass A|B|C or --status")

    _setup_logging(args.pass_name)
    log = logging.getLogger("scrape")

    if not args.nixpkgs.exists():
        log.error("nixpkgs path does not exist: %s", args.nixpkgs)
        return 2

    commit = _nixpkgs_commit(args.nixpkgs)
    log.info("nixpkgs=%s commit=%s channel=%s db=%s",
             args.nixpkgs, commit, args.channel, args.db)

    conn = db.connect(args.db)

    try:
        if args.pass_name == "A":
            inserted, prior = pass_a_enumerate.run(
                conn, args.nixpkgs, commit, args.channel,
            )
            log.info("done: inserted=%d prior=%d", inserted, prior)
        elif args.pass_name == "O":
            inserted, seen = pass_o_options.run(
                conn, args.nixpkgs, commit, args.channel,
            )
            log.info("done: inserted=%d seen=%d", inserted, seen)
        else:
            log.error("pass %s not yet implemented", args.pass_name)
            return 3
    except KeyboardInterrupt:
        log.warning("interrupted; state persisted, rerun to resume")
        return 130

    return 0


if __name__ == "__main__":
    sys.exit(main())
