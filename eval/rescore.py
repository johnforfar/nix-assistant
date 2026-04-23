"""Re-score an existing benchmark run against the current metrics module.

Reads a `*.raw.jsonl` log from an earlier run, re-computes all metrics
(including any added since the run happened), and writes a fresh aggregate
JSON. Does NOT call the model again.

Usage:
  python -m eval.rescore \
    --in eval/results/v0_live.raw.jsonl \
    --dataset eval/dataset/v0_seed.jsonl \
    --out eval/results/v0_live.json \
    --corpus-db data/corpus.db \
    --nixpkgs-root data/nixpkgs
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import metrics as M


def load_raw(raw_path: Path) -> list[dict]:
    out: list[dict] = []
    with raw_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_dataset_by_id(path: Path) -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                c = json.loads(line)
                by_id[c["id"]] = c
    return by_id


def score(case_raw: dict, case_def: dict, ctx: dict) -> dict:
    parsed = case_raw.get("parsed_comments")
    is_neg = bool(case_def.get("is_negative", False))
    gt = case_def.get("ground_truth") or {}

    out: dict = {"schema_valid": M.schema_valid(parsed)}
    if is_neg:
        out["empty_on_negative"] = M.empty_on_negative(parsed)
    else:
        out["line_exact"] = M.line_exact(parsed, gt.get("line", 0))
        out["severity_match"] = M.severity_match(parsed, gt.get("severity", ""))
        out["message_keywords_hit"] = M.message_keywords_hit(
            parsed, gt.get("message_keywords", [])
        )
    out["looks_like_escape_hatch"] = M.looks_like_escape_hatch(parsed)

    # non-slop metrics
    out["no_hallucinated_options"] = M.no_hallucinated_options(
        parsed, ctx["valid_prefix_set"]
    )
    out["receipts_available"] = M.receipts_available(
        parsed, ctx["option_source_map"], ctx["nixpkgs_root"]
    )
    dialect = None if is_neg else M.detect_dialect(case_def.get("broken_source", ""))
    out["dialect_awareness"] = M.dialect_awareness(parsed, dialect)
    return out


def aggregate(per_case: list[dict]) -> dict[str, dict]:
    """Per-metric {pass_rate, n_applicable, n_total}."""
    totals: dict[str, int] = {}
    counts: dict[str, int] = {}
    n_total = len(per_case)
    for pc in per_case:
        for k, v in pc["metrics"].items():
            if v is None:
                continue
            counts[k] = counts.get(k, 0) + 1
            totals[k] = totals.get(k, 0) + (1 if v else 0)
    return {
        k: {
            "pass_rate": (totals[k] / counts[k]) if counts[k] else 0.0,
            "n_applicable": counts[k],
            "n_total": n_total,
        }
        for k in counts
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="in_raw", required=True, type=Path)
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--corpus-db", default=Path("data/corpus.db"), type=Path)
    ap.add_argument("--nixpkgs-root", default=Path("data/nixpkgs"), type=Path)
    ap.add_argument("--version", default=None)
    ap.add_argument("--system", default=None)
    args = ap.parse_args(argv)

    print(f"[rescore] loading context from {args.corpus_db} ...")
    ctx = {
        "valid_prefix_set": M.load_option_prefix_set(args.corpus_db),
        "option_source_map": M.load_option_source_map(args.corpus_db),
        "nixpkgs_root": args.nixpkgs_root,
    }
    print(f"[rescore]   {len(ctx['valid_prefix_set']):,} option prefixes")
    print(f"[rescore]   {len(ctx['option_source_map']):,} options with declaration paths")

    raw = load_raw(args.in_raw)
    defs = load_dataset_by_id(args.dataset)
    print(f"[rescore] scoring {len(raw)} cases ...")

    per_case: list[dict] = []
    for rc in raw:
        cid = rc["id"]
        if cid not in defs:
            print(f"[warn] case {cid} missing from dataset; skipping")
            continue
        scored = score(rc, defs[cid], ctx)
        per_case.append(
            {
                "id": cid,
                "mutation_type": defs[cid].get("mutation_type"),
                "is_negative": defs[cid].get("is_negative", False),
                "ok": rc.get("ok", True),
                "latency_ms": rc.get("latency_ms", 0),
                "parsed_comments": rc.get("parsed_comments"),
                "metrics": scored,
            }
        )

    agg = aggregate(per_case)

    # Preserve existing metadata if the output file exists already
    existing: dict = {}
    if args.out.exists():
        try:
            existing = json.loads(args.out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    n_total = len(per_case)
    avg_latency = (
        sum(pc["latency_ms"] for pc in per_case) / n_total if n_total else 0.0
    )

    summary = {
        "version": args.version or existing.get("version") or args.in_raw.stem.replace(".raw", ""),
        "system": args.system or existing.get("system", "(rescored)"),
        "dataset": str(args.dataset),
        "n_cases": n_total,
        "avg_latency_ms": avg_latency,
        "metrics": {k: v["pass_rate"] for k, v in agg.items()},
        "metrics_detail": agg,
        "per_case": per_case,
    }
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n[rescore] === SUMMARY ===")
    for k in sorted(agg):
        d = agg[k]
        print(f"  {k:28s} : {100*d['pass_rate']:5.1f}%   "
              f"({d['n_applicable']}/{d['n_total']} applicable)")
    print(f"\nsaved -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
