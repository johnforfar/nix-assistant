"""Generate (broken_config, review) training pairs.

Flow:
  synthesizer  ─→  SynthesizedCase (Nix source + metadata)
       │
       ▼
  oracle.eval_source (Docker Nix)  ─→  real error + location
       │
       ▼
  emit JSONL row:
    { prompt: <Nix source>, completion: <review JSON>, pattern_id, strategy }

This is the v0 spec from 2.md, with one key change: training-data *inputs*
are synthesized by us (no scraping from forums), but the *ground-truth errors*
still come from `nix eval` — the Nix compiler stays the oracle.

Usage:
  python -m scrape.generate_pairs \\
    --patterns package_attr_path_drift \\
    --count 500 \\
    --out data/train_pairs.jsonl

Resumable: the output file is appended to. If it exists on startup, we count
existing lines and continue from there.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from .oracle import eval_source
from .synthesizers import SYNTHESIZERS, SynthesizedCase


def _verify_expected_error(case: SynthesizedCase, stderr: str) -> bool:
    """Sanity-check: does Nix's real error match what the synthesizer expected?

    If not, the mutation didn't produce the error class we intended — drop the
    case rather than emit a mislabeled training pair.
    """
    return all(kw in stderr for kw in case.expected_error_contains)


def _build_review(case: SynthesizedCase, err: dict) -> list[dict]:
    """Compose the ideal review comment from the oracle's real error + pattern label.

    Uses the pattern's hint text and the oracle's real line number. Severity is
    always "error" for hard eval failures; soft linter findings get "warning"
    (future: when we add those patterns).
    """
    label = case.label
    hint = label.get("hint") or err["message"]
    return [
        {
            "line": err["line"],
            "severity": "error",
            "message": hint,
        }
    ]


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--patterns", nargs="+", default=list(SYNTHESIZERS.keys()),
                    help="pattern ids to generate from")
    ap.add_argument("--count", type=int, default=50,
                    help="target total pair count across all patterns")
    ap.add_argument("--out", type=Path, default=Path("data/train_pairs.jsonl"))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    args.out.parent.mkdir(parents=True, exist_ok=True)

    # Resumability: if file exists, count existing rows and target the difference.
    already_written = 0
    seen_hashes: set[str] = set()
    if args.out.exists():
        with args.out.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    seen_hashes.add(row.get("id", ""))
                    already_written += 1
                except json.JSONDecodeError:
                    continue
    remaining = max(0, args.count - already_written)
    print(f"[gen] target={args.count} already_written={already_written} remaining={remaining}",
          file=sys.stderr)

    if remaining == 0:
        print("[gen] done, nothing to do", file=sys.stderr)
        return 0

    # Distribute remaining count across selected patterns, round-robin-ish.
    per_pattern = max(1, remaining // len(args.patterns))
    overage_needed = remaining - per_pattern * len(args.patterns)
    plan = [(pid, per_pattern + (1 if i < overage_needed else 0))
            for i, pid in enumerate(args.patterns)]
    print(f"[gen] plan: {plan}", file=sys.stderr)

    # Generate all the synthesized candidates up front (cheap), then run oracle
    # on each (expensive — ~600 ms/call).
    candidates: list[SynthesizedCase] = []
    for pid, n in plan:
        synth = SYNTHESIZERS[pid]
        candidates.extend(synth(n, seed=args.seed))
    print(f"[gen] synthesized {len(candidates)} candidates", file=sys.stderr)

    written = 0
    dropped_unexpected = 0
    dropped_no_error = 0
    dropped_dup = 0
    t_start = time.monotonic()

    with args.out.open("a", encoding="utf-8") as fout:
        for i, case in enumerate(candidates, 1):
            case_id = _hash(case.source)
            if case_id in seen_hashes:
                dropped_dup += 1
                continue

            t0 = time.monotonic()
            result = eval_source(case.source, strategy=case.strategy)
            elapsed_ms = (time.monotonic() - t0) * 1000

            if result.ok:
                # We expected the mutation to break eval; it didn't. Skip.
                dropped_no_error += 1
                if args.verbose:
                    print(f"[gen] {i}/{len(candidates)} {case.pattern_id} "
                          f"NO-ERROR ({elapsed_ms:.0f}ms) — dropped",
                          file=sys.stderr)
                continue
            if result.error is None:
                dropped_no_error += 1
                if args.verbose:
                    print(f"[gen] {i}/{len(candidates)} {case.pattern_id} "
                          f"UNPARSEABLE ({elapsed_ms:.0f}ms) — dropped",
                          file=sys.stderr)
                continue
            if not _verify_expected_error(case, result.stderr):
                dropped_unexpected += 1
                if args.verbose:
                    print(f"[gen] {i}/{len(candidates)} {case.pattern_id} "
                          f"UNEXPECTED-ERROR ({elapsed_ms:.0f}ms) — dropped",
                          file=sys.stderr)
                continue

            review = _build_review(case, result.error)
            row = {
                "id": case_id,
                "pattern_id": case.pattern_id,
                "strategy": case.strategy,
                "prompt": case.source,
                "completion": json.dumps(review),
                "oracle_line": result.error["line"],
                "oracle_message": result.error["message"],
                "label": case.label,
            }
            fout.write(json.dumps(row) + "\n")
            fout.flush()
            seen_hashes.add(case_id)
            written += 1
            if args.verbose or i % 10 == 0:
                print(f"[gen] {i}/{len(candidates)} {case.pattern_id} "
                      f"OK line={result.error['line']} ({elapsed_ms:.0f}ms)",
                      file=sys.stderr)

    t_total = time.monotonic() - t_start
    print(f"\n[gen] === SUMMARY ===", file=sys.stderr)
    print(f"  written       : {written}", file=sys.stderr)
    print(f"  dropped (dup) : {dropped_dup}", file=sys.stderr)
    print(f"  dropped (no error produced) : {dropped_no_error}", file=sys.stderr)
    print(f"  dropped (wrong error class) : {dropped_unexpected}", file=sys.stderr)
    print(f"  wall time     : {t_total:.1f}s ({t_total/max(1,written):.2f}s/pair)",
          file=sys.stderr)
    print(f"  out           : {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
