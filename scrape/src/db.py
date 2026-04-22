"""SQLite persistence for the nix-corpus scrape."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS packages (
  id                        INTEGER PRIMARY KEY,
  attr_path                 TEXT NOT NULL,
  pname                     TEXT,
  version                   TEXT,
  nixpkgs_commit            TEXT NOT NULL,
  nixpkgs_channel           TEXT NOT NULL,
  source_file_path          TEXT,
  source_file_sha256        TEXT,
  source_file_contents      TEXT,
  description               TEXT,
  license_json              TEXT,
  maintainers_json          TEXT,
  homepage                  TEXT,
  platforms_json            TEXT,
  build_inputs_json         TEXT,
  native_build_inputs_json  TEXT,
  propagated_inputs_json    TEXT,
  build_status              TEXT,
  closure_size_bytes        INTEGER,
  reverse_deps_count        INTEGER,
  last_commit_touching      TEXT,
  scraped_at                TEXT NOT NULL,
  UNIQUE(attr_path, nixpkgs_commit)
);

CREATE INDEX IF NOT EXISTS idx_packages_commit ON packages(nixpkgs_commit);
CREATE INDEX IF NOT EXISTS idx_packages_attr   ON packages(attr_path);
CREATE INDEX IF NOT EXISTS idx_packages_file   ON packages(source_file_path);

CREATE TABLE IF NOT EXISTS scrape_runs (
  id               INTEGER PRIMARY KEY,
  nixpkgs_commit   TEXT NOT NULL,
  nixpkgs_channel  TEXT NOT NULL,
  started_at       TEXT NOT NULL,
  completed_at     TEXT,
  pass             TEXT NOT NULL,
  status           TEXT NOT NULL,
  last_attr        TEXT,
  rows_processed   INTEGER NOT NULL DEFAULT 0,
  error            TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_current
  ON scrape_runs(nixpkgs_commit, pass, status);

CREATE TABLE IF NOT EXISTS nixos_options (
  id                     INTEGER PRIMARY KEY,
  option_path            TEXT NOT NULL,
  nixpkgs_commit         TEXT NOT NULL,
  nixpkgs_channel        TEXT NOT NULL,
  type                   TEXT,
  default_json           TEXT,
  example_json           TEXT,
  description            TEXT,
  declarations_json      TEXT,
  related_packages_json  TEXT,
  read_only              INTEGER,
  visible                INTEGER,
  internal               INTEGER,
  scraped_at             TEXT NOT NULL,
  UNIQUE(option_path, nixpkgs_commit)
);

CREATE INDEX IF NOT EXISTS idx_options_commit ON nixos_options(nixpkgs_commit);
CREATE INDEX IF NOT EXISTS idx_options_path   ON nixos_options(option_path);
"""

PACKAGE_COLS = (
    "attr_path", "pname", "version", "nixpkgs_commit", "nixpkgs_channel",
    "source_file_path", "source_file_sha256", "source_file_contents",
    "description", "license_json", "maintainers_json", "homepage",
    "platforms_json", "build_inputs_json", "native_build_inputs_json",
    "propagated_inputs_json", "scraped_at",
)


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Cursor]:
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def find_resumable_run(
    conn: sqlite3.Connection, commit: str, pass_name: str
) -> tuple[int, str | None, int] | None:
    """Return (run_id, last_attr, rows_processed) if a resumable run exists."""
    row = conn.execute(
        """
        SELECT id, last_attr, rows_processed FROM scrape_runs
        WHERE nixpkgs_commit = ? AND pass = ? AND status IN ('running', 'paused')
        ORDER BY id DESC LIMIT 1
        """,
        (commit, pass_name),
    ).fetchone()
    return row if row else None


def start_run(
    conn: sqlite3.Connection, commit: str, channel: str, pass_name: str, started_at: str
) -> int:
    cur = conn.execute(
        """
        INSERT INTO scrape_runs
          (nixpkgs_commit, nixpkgs_channel, started_at, pass, status)
        VALUES (?, ?, ?, ?, 'running')
        """,
        (commit, channel, started_at, pass_name),
    )
    conn.commit()
    return cur.lastrowid


def update_run_progress(
    conn: sqlite3.Connection, run_id: int, last_attr: str, rows_processed: int
) -> None:
    conn.execute(
        "UPDATE scrape_runs SET last_attr = ?, rows_processed = ? WHERE id = ?",
        (last_attr, rows_processed, run_id),
    )
    conn.commit()


def finish_run(
    conn: sqlite3.Connection, run_id: int, status: str, completed_at: str,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE scrape_runs
        SET status = ?, completed_at = ?, error = ?
        WHERE id = ?
        """,
        (status, completed_at, error, run_id),
    )
    conn.commit()


def pause_run(conn: sqlite3.Connection, run_id: int, last_attr: str | None) -> None:
    conn.execute(
        "UPDATE scrape_runs SET status = 'paused', last_attr = ? WHERE id = ?",
        (last_attr, run_id),
    )
    conn.commit()


def insert_packages(
    conn: sqlite3.Connection, rows: Iterable[dict]
) -> int:
    placeholders = ", ".join(["?"] * len(PACKAGE_COLS))
    col_list = ", ".join(PACKAGE_COLS)
    sql = (
        f"INSERT OR IGNORE INTO packages ({col_list}) VALUES ({placeholders})"
    )
    tuples = [tuple(r.get(c) for c in PACKAGE_COLS) for r in rows]
    cur = conn.executemany(sql, tuples)
    conn.commit()
    return cur.rowcount


OPTION_COLS = (
    "option_path", "nixpkgs_commit", "nixpkgs_channel", "type",
    "default_json", "example_json", "description", "declarations_json",
    "related_packages_json", "read_only", "visible", "internal", "scraped_at",
)


def insert_options(
    conn: sqlite3.Connection, rows: Iterable[dict]
) -> int:
    placeholders = ", ".join(["?"] * len(OPTION_COLS))
    col_list = ", ".join(OPTION_COLS)
    sql = (
        f"INSERT OR IGNORE INTO nixos_options ({col_list}) VALUES ({placeholders})"
    )
    tuples = [tuple(r.get(c) for c in OPTION_COLS) for r in rows]
    cur = conn.executemany(sql, tuples)
    conn.commit()
    return cur.rowcount


def js(value) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, ensure_ascii=False)
