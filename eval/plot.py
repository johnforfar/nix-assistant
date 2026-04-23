"""Produce the leaderboard chart.

Reads all eval/results/*.json files, plots each metric as a line across versions.
The version order comes from the 'version' field in each JSON (alphanumerically sorted
unless --order is given).

Usage:
  python -m eval.plot --results eval/results --out eval/chart/leaderboard.png
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


METRICS_TO_PLOT = [
    "schema_valid",
    "no_hallucinated_options",
    "line_exact",
    "severity_match",
    "message_keywords_hit",
    "receipts_available",
    "empty_on_negative",
    "dialect_awareness",
]


def load_runs(results_dir: Path) -> list[dict]:
    runs = []
    for p in sorted(results_dir.glob("*.json")):
        if p.name.endswith(".raw.jsonl"):
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        runs.append(data)
    return runs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", type=Path, default=Path("eval/results"))
    ap.add_argument("--out", type=Path, default=Path("eval/chart/leaderboard.png"))
    ap.add_argument("--order", nargs="+", default=None,
                    help="explicit version order (defaults to alphanumeric)")
    args = ap.parse_args(argv)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed. pip install matplotlib")
        return 2

    runs = load_runs(args.results)
    if not runs:
        print(f"no result files in {args.results}")
        return 1

    if args.order:
        order = args.order
        runs.sort(key=lambda r: order.index(r["version"]) if r["version"] in order else 999)
    else:
        runs.sort(key=lambda r: r["version"])

    versions = [r["version"] for r in runs]
    xs = list(range(len(versions)))

    fig, ax = plt.subplots(figsize=(11, 6), dpi=130)
    fig.patch.set_facecolor("#0a0f1a")
    ax.set_facecolor("#0a0f1a")

    colors = {
        "schema_valid":            "#00e5ff",
        "no_hallucinated_options": "#ff3860",
        "line_exact":              "#ff8c42",
        "severity_match":          "#ffe566",
        "message_keywords_hit":    "#7ebae4",
        "receipts_available":      "#c589e8",
        "empty_on_negative":       "#00ffb3",
        "dialect_awareness":       "#9ae79e",
    }

    for metric in METRICS_TO_PLOT:
        # Skip metric entirely if every run reports 0 applicable cases.
        any_applicable = any(
            r.get("metrics_detail", {}).get(metric, {}).get("n_applicable", 0) > 0
            or metric in r.get("metrics", {})
            for r in runs
        )
        if not any_applicable:
            continue
        ys = [100 * r["metrics"].get(metric, 0) for r in runs]
        ax.plot(xs, ys, marker="o", linewidth=2.2, markersize=8,
                color=colors.get(metric, "#ffffff"), label=metric)

    ax.set_xticks(xs)
    ax.set_xticklabels(versions, fontsize=10, color="#a0c0d8")
    ax.set_ylim(0, 105)
    ax.set_yticks(range(0, 101, 20))
    ax.set_ylabel("pass rate (%)", color="#a0c0d8", fontsize=11)
    ax.set_title("nix-assistant benchmark — metric performance across versions",
                 color="#00e5ff", fontsize=13, fontweight="bold", pad=18)
    ax.grid(True, alpha=0.15, color="#00e5ff")
    ax.tick_params(colors="#a0c0d8")
    for spine in ax.spines.values():
        spine.set_color("#1a3040")

    legend = ax.legend(loc="lower right", facecolor="#0a0f1a", edgecolor="#1a3040",
                       fontsize=9, labelcolor="#a0c0d8")
    for text in legend.get_texts():
        text.set_color("#a0c0d8")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(args.out, facecolor=fig.get_facecolor())
    print(f"saved -> {args.out}")
    print(f"\nversions: {versions}")
    for r in runs:
        print(f"  {r['version']:20s} " + "  ".join(
            f"{m}={100*r['metrics'].get(m, 0):5.1f}%" for m in METRICS_TO_PLOT
        ))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
