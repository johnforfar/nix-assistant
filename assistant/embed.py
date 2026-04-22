#!/usr/bin/env python3
"""Build the vector index from corpus.db using nomic-embed-text via Ollama.

Usage:
  python embed.py                         # embed both tables
  python embed.py --table packages        # packages only
  python embed.py --table nixos-options   # options only
  python embed.py --status               # show index status

Output:
  data/embeddings/packages.npy           float32 [N, 768]
  data/embeddings/packages_meta.json     [{"id": attr_path, "text": "..."}]
  data/embeddings/nixos_options.npy
  data/embeddings/nixos_options_meta.json

Resumable: reads existing meta to determine which rows already embedded,
appends new rows, rewrites both files atomically.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT.parent / "scrape" / "data" / "corpus.db"
EMB_DIR = ROOT / "data" / "embeddings"
OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"
BATCH_SIZE = 32
CHECKPOINT_EVERY = 500


def _ollama_embed(texts: list[str]) -> list[list[float]]:
    body = json.dumps({"model": EMBED_MODEL, "input": texts}).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embed",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    return data["embeddings"]


def _embed_table(
    conn: sqlite3.Connection,
    table: str,
    id_col: str,
    npy_path: Path,
    meta_path: Path,
) -> int:
    EMB_DIR.mkdir(parents=True, exist_ok=True)

    # Load already-embedded ids from existing meta
    done_ids: set[str] = set()
    existing_vecs: list[list[float]] = []
    existing_meta: list[dict] = []
    if meta_path.exists() and npy_path.exists():
        with meta_path.open() as f:
            existing_meta = json.load(f)
        existing_vecs = np.load(str(npy_path)).tolist()
        done_ids = {m["id"] for m in existing_meta}
        print(f"  {table}: {len(done_ids)} rows already embedded, resuming")

    # Fetch rows not yet embedded
    if table == "packages":
        rows = conn.execute(
            "SELECT attr_path, pname, description FROM packages ORDER BY attr_path"
        ).fetchall()
        pending = [
            (r[0], f"{r[1] or r[0]}: {r[2] or ''}".strip())
            for r in rows if r[0] not in done_ids
        ]
    else:
        rows = conn.execute(
            "SELECT option_path, type, description FROM nixos_options ORDER BY option_path"
        ).fetchall()
        pending = [
            (r[0], f"{r[0]} ({r[1] or 'unknown'}): {r[2] or ''}".strip())
            for r in rows if r[0] not in done_ids
        ]

    if not pending:
        print(f"  {table}: nothing new to embed")
        return 0

    print(f"  {table}: {len(pending)} rows to embed via {EMBED_MODEL}")

    new_vecs: list[list[float]] = []
    new_meta: list[dict] = []
    total = len(pending)
    t0 = time.time()

    for i in range(0, total, BATCH_SIZE):
        batch = pending[i : i + BATCH_SIZE]
        ids = [b[0] for b in batch]
        texts = [b[1] for b in batch]

        for attempt in range(3):
            try:
                vecs = _ollama_embed(texts)
                break
            except Exception as e:
                if attempt == 2:
                    raise
                print(f"    retry {attempt+1} after error: {e}", file=sys.stderr)
                time.sleep(2 ** attempt)

        new_vecs.extend(vecs)
        new_meta.extend({"id": id_, "text": txt} for id_, txt in zip(ids, texts))

        done = i + len(batch)
        if done % CHECKPOINT_EVERY < BATCH_SIZE or done == total:
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate if rate > 0 else 0
            print(f"    {done}/{total}  {rate:.0f} rows/s  ETA {eta:.0f}s")
            _save(npy_path, meta_path, existing_vecs + new_vecs, existing_meta + new_meta)

    _save(npy_path, meta_path, existing_vecs + new_vecs, existing_meta + new_meta)
    print(f"  {table}: done — {len(new_vecs)} new rows embedded")
    return len(new_vecs)


def _save(npy_path: Path, meta_path: Path, vecs: list, meta: list) -> None:
    arr = np.array(vecs, dtype=np.float32)
    tmp_npy = npy_path.with_suffix(".tmp.npy")
    tmp_meta = meta_path.with_suffix(".tmp.json")
    np.save(str(tmp_npy), arr)
    with tmp_meta.open("w") as f:
        json.dump(meta, f)
    tmp_npy.replace(npy_path)
    tmp_meta.replace(meta_path)


def _status() -> None:
    for name, npy, meta in [
        ("packages", EMB_DIR / "packages.npy", EMB_DIR / "packages_meta.json"),
        ("nixos-options", EMB_DIR / "nixos_options.npy", EMB_DIR / "nixos_options_meta.json"),
    ]:
        if npy.exists() and meta.exists():
            arr = np.load(str(npy))
            print(f"{name}: {arr.shape[0]} vectors, dim={arr.shape[1]}, "
                  f"size={npy.stat().st_size // 1024}KB")
        else:
            print(f"{name}: not built")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--table", choices=["packages", "nixos-options"],
                    help="embed one table only (default: both)")
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--ollama", default=OLLAMA_URL)
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args(argv)

    if args.ollama != OLLAMA_URL:
        globals()["OLLAMA_URL"] = args.ollama

    if args.status:
        _status()
        return 0

    if not args.db.exists():
        print(f"error: corpus.db not found at {args.db}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(args.db))

    if args.table in (None, "packages"):
        _embed_table(conn, "packages", "attr_path",
                     EMB_DIR / "packages.npy",
                     EMB_DIR / "packages_meta.json")

    if args.table in (None, "nixos-options"):
        _embed_table(conn, "nixos_options", "option_path",
                     EMB_DIR / "nixos_options.npy",
                     EMB_DIR / "nixos_options_meta.json")

    return 0


if __name__ == "__main__":
    sys.exit(main())
