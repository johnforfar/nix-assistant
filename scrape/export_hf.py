#!/usr/bin/env python3
"""Export corpus.db → parquet shards for Hugging Face dataset upload.

Usage:
  python export_hf.py                          # export both splits to data/export/
  python export_hf.py --split packages         # packages only
  python export_hf.py --split nixos-options    # NixOS options only
  python export_hf.py --upload                 # export then push to HF Hub
  python export_hf.py --repo OpenxAILabs/nix-corpus --upload

Output layout (mirrors HF parquet convention):
  data/export/
    packages/
      train-00000-of-00001.parquet
    nixos-options/
      train-00000-of-00001.parquet

Requires: pip install pyarrow huggingface_hub   (or pip install .[export])
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "corpus.db"
DEFAULT_OUT = ROOT / "data" / "export"
DEFAULT_REPO = "OpenxAILabs/nix-corpus"
SHARD_ROWS = 50_000


def _export_packages(conn: sqlite3.Connection, out_dir: Path) -> Path:
    import pyarrow as pa
    import pyarrow.parquet as pq

    out_dir.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(
        """
        SELECT
          attr_path, pname, version,
          nixpkgs_commit, nixpkgs_channel,
          source_file_path,
          description, homepage,
          license_json, maintainers_json,
          platforms_json,
          build_inputs_json, native_build_inputs_json, propagated_inputs_json,
          scraped_at
        FROM packages
        ORDER BY attr_path
        """
    ).fetchall()

    cols = [
        "attr_path", "pname", "version",
        "nixpkgs_commit", "nixpkgs_channel",
        "source_file_path",
        "description", "homepage",
        "license_json", "maintainers_json",
        "platforms_json",
        "build_inputs_json", "native_build_inputs_json", "propagated_inputs_json",
        "scraped_at",
    ]
    table = pa.table({c: [r[i] for r in rows] for i, c in enumerate(cols)})

    total = len(rows)
    n_shards = max(1, (total + SHARD_ROWS - 1) // SHARD_ROWS)
    for shard in range(n_shards):
        shard_table = table.slice(shard * SHARD_ROWS, SHARD_ROWS)
        fname = out_dir / f"train-{shard:05d}-of-{n_shards:05d}.parquet"
        pq.write_table(shard_table, fname, compression="snappy")
        print(f"  wrote {fname.name}  ({len(shard_table)} rows)")

    print(f"packages: {total} rows → {n_shards} shard(s)")
    return out_dir


def _export_options(conn: sqlite3.Connection, out_dir: Path) -> Path:
    import pyarrow as pa
    import pyarrow.parquet as pq

    out_dir.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(
        """
        SELECT
          option_path,
          nixpkgs_commit, nixpkgs_channel,
          type,
          default_json, example_json,
          description,
          read_only, visible, internal,
          scraped_at
        FROM nixos_options
        ORDER BY option_path
        """
    ).fetchall()

    cols = [
        "option_path",
        "nixpkgs_commit", "nixpkgs_channel",
        "type",
        "default_json", "example_json",
        "description",
        "read_only", "visible", "internal",
        "scraped_at",
    ]
    table = pa.table({c: [r[i] for r in rows] for i, c in enumerate(cols)})

    total = len(rows)
    n_shards = max(1, (total + SHARD_ROWS - 1) // SHARD_ROWS)
    for shard in range(n_shards):
        shard_table = table.slice(shard * SHARD_ROWS, SHARD_ROWS)
        fname = out_dir / f"train-{shard:05d}-of-{n_shards:05d}.parquet"
        pq.write_table(shard_table, fname, compression="snappy")
        print(f"  wrote {fname.name}  ({len(shard_table)} rows)")

    print(f"nixos-options: {total} rows → {n_shards} shard(s)")
    return out_dir


def _upload(repo: str, export_root: Path) -> None:
    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(repo_id=repo, repo_type="dataset", exist_ok=True)

    for split_dir in sorted(export_root.iterdir()):
        if not split_dir.is_dir():
            continue
        for parquet_file in sorted(split_dir.glob("*.parquet")):
            path_in_repo = f"data/{split_dir.name}/{parquet_file.name}"
            print(f"  uploading {path_in_repo} ...")
            api.upload_file(
                path_or_fileobj=str(parquet_file),
                path_in_repo=path_in_repo,
                repo_id=repo,
                repo_type="dataset",
            )

    print(f"\nDataset live at: https://huggingface.co/datasets/{repo}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--split", choices=["packages", "nixos-options"],
                    help="export one split only (default: both)")
    ap.add_argument("--upload", action="store_true",
                    help="push parquet files to HF Hub after export")
    ap.add_argument("--repo", default=DEFAULT_REPO,
                    help=f"HF dataset repo (default: {DEFAULT_REPO})")
    args = ap.parse_args(argv)

    if not args.db.exists():
        print(f"error: corpus.db not found at {args.db}", file=sys.stderr)
        return 2

    try:
        import pyarrow  # noqa: F401
    except ImportError:
        print("error: pyarrow not installed — run: pip install pyarrow", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(args.db))

    if args.split in (None, "packages"):
        _export_packages(conn, args.out / "packages")

    if args.split in (None, "nixos-options"):
        _export_options(conn, args.out / "nixos-options")

    if args.upload:
        try:
            import huggingface_hub  # noqa: F401
        except ImportError:
            print("error: huggingface_hub not installed — run: pip install huggingface_hub",
                  file=sys.stderr)
            return 2
        _upload(args.repo, args.out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
