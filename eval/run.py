"""Run a benchmark: iterate a dataset, call a runner, compute metrics, save JSON.

Usage:
  python -m eval.run --runner live_xnode --dataset eval/dataset/v0_seed.jsonl --out eval/results/v0_live.json

Resumable: writes one raw line per case to <out>.raw.jsonl as it goes, so you can
ctrl-C mid-run and not lose progress. The final <out>.json is the aggregate.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path

from . import metrics


def load_dataset(path: Path) -> list[dict]:
    cases = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def score_case(case: dict, parsed_comments: list[dict] | None) -> dict[str, bool]:
    gt = case["ground_truth"]
    is_negative = case.get("is_negative", False)
    scored = {"schema_valid": metrics.schema_valid(parsed_comments)}
    if is_negative:
        scored["empty_on_negative"] = metrics.empty_on_negative(parsed_comments)
    else:
        scored["line_exact"] = metrics.line_exact(parsed_comments, gt["line"])
        scored["severity_match"] = metrics.severity_match(parsed_comments, gt["severity"])
        scored["message_keywords_hit"] = metrics.message_keywords_hit(
            parsed_comments, gt.get("message_keywords", [])
        )
    scored["looks_like_escape_hatch"] = metrics.looks_like_escape_hatch(parsed_comments)
    return scored


def aggregate(per_case: list[dict]) -> dict[str, float]:
    """Compute pass rates across all cases for each metric."""
    totals: dict[str, int] = {}
    counts: dict[str, int] = {}
    for pc in per_case:
        for k, v in pc["metrics"].items():
            totals[k] = totals.get(k, 0) + (1 if v else 0)
            counts[k] = counts.get(k, 0) + 1
    return {k: (totals[k] / counts[k]) if counts[k] else 0.0 for k in totals}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runner", required=True,
                    help="runner module name under eval.runners (e.g. live_xnode)")
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--version", default=None,
                    help="Version label for this run (defaults to out filename stem)")
    ap.add_argument("--system", default=None,
                    help="Human-readable system description for the leaderboard")
    ap.add_argument("--limit", type=int, default=None,
                    help="Only run first N cases (for smoke testing)")
    args = ap.parse_args(argv)

    runner = importlib.import_module(f"eval.runners.{args.runner}")
    cases = load_dataset(args.dataset)
    if args.limit:
        cases = cases[: args.limit]

    version = args.version or args.out.stem
    system = args.system or args.runner

    args.out.parent.mkdir(parents=True, exist_ok=True)
    raw_log = args.out.with_suffix(".raw.jsonl")
    raw_log.unlink(missing_ok=True)

    print(f"[run] version={version} system={system} cases={len(cases)} out={args.out}", flush=True)
    per_case = []
    run_start = time.monotonic()
    for i, case in enumerate(cases, 1):
        cid = case["id"]
        src = case["broken_source"]
        print(f"[run] {i}/{len(cases)} {cid} ({case.get('mutation_type', 'neg')}) ...",
              end="", flush=True)
        result = runner.run_one(src)
        scored = score_case(case, result.parsed_comments) if result.ok else {
            "schema_valid": False, "line_exact": False, "severity_match": False,
            "message_keywords_hit": False, "empty_on_negative": False,
            "looks_like_escape_hatch": False,
        }
        record = {
            "id": cid,
            "mutation_type": case.get("mutation_type"),
            "is_negative": case.get("is_negative", False),
            "ok": result.ok,
            "http_status": result.http_status,
            "latency_ms": result.latency_ms,
            "error": result.error,
            "raw_response": result.raw_response[:8000],
            "parsed_comments": result.parsed_comments,
            "metrics": scored,
        }
        per_case.append(record)
        with raw_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        passed = sum(1 for v in scored.values() if v)
        total = len(scored)
        print(f" {'OK' if result.ok else 'FAIL'}  {result.latency_ms:.0f}ms  {passed}/{total}",
              flush=True)

    run_secs = time.monotonic() - run_start
    agg = aggregate(per_case)
    avg_latency = sum(r["latency_ms"] for r in per_case) / len(per_case) if per_case else 0

    summary = {
        "version": version,
        "system": system,
        "dataset": str(args.dataset),
        "n_cases": len(cases),
        "run_seconds": run_secs,
        "avg_latency_ms": avg_latency,
        "metrics": agg,
        "per_case": per_case,
    }
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\n[run] === SUMMARY ===", flush=True)
    print(f"       version        : {version}")
    print(f"       system         : {system}")
    print(f"       cases          : {len(cases)}")
    print(f"       wall time      : {run_secs:.1f}s")
    print(f"       avg latency    : {avg_latency:.0f}ms")
    for k in sorted(agg):
        print(f"       {k:24s} : {100*agg[k]:5.1f}%")
    print(f"\n       saved -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
