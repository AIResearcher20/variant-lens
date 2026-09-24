"""
Generate plots from the benchmark results.

Reads evaluation_results.json and produces two figures under
docs/images. The first compares the three retrieval strategies across
the four metrics. The second shows the size of the reference set for
each eligible variant. Both figures are written to disk and are meant
to be embedded in the README.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


DEFAULT_RESULTS = Path("evaluation_results.json")
DEFAULT_OUTPUT_DIR = Path("docs/images")

METRICS = ["recall@5", "recall@10", "mrr", "ndcg@10"]
METRIC_LABELS = ["Recall@5", "Recall@10", "MRR", "nDCG@10"]

STRATEGY_LABELS = {
    "bm25": "BM25",
    "dense": "Dense",
    "hybrid": "Hybrid",
}

STRATEGY_COLORS = {
    "bm25": "#7f8c8d",
    "dense": "#2980b9",
    "hybrid": "#27ae60",
}


def load_results(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def plot_benchmark_summary(data: dict, output: Path) -> None:
    """
    Draw a grouped bar chart comparing strategies across metrics.
    """
    strategies = list(data["strategies"].keys())
    n_metrics = len(METRICS)
    n_strategies = len(strategies)
    bar_width = 0.8 / n_strategies

    fig, ax = plt.subplots(figsize=(9, 5))

    for i, strategy in enumerate(strategies):
        summary = data["strategies"][strategy]["summary"]
        values = [summary.get(m, 0.0) for m in METRICS]
        positions = [
            j - 0.4 + bar_width / 2 + i * bar_width
            for j in range(n_metrics)
        ]
        bars = ax.bar(
            positions,
            values,
            bar_width,
            label=STRATEGY_LABELS.get(strategy, strategy),
            color=STRATEGY_COLORS.get(strategy, "#333333"),
        )
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.005,
                f"{value:.3f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )

    ax.set_xticks(range(n_metrics))
    ax.set_xticklabels(METRIC_LABELS)
    ax.set_ylabel("Score")
    ax.set_ylim(0, max(0.5, ax.get_ylim()[1]))
    ax.set_title("Retrieval performance by strategy")
    ax.legend(loc="upper right")
    ax.grid(axis="y", linestyle=":", alpha=0.4)

    fig.tight_layout()
    fig.savefig(output, dpi=150)
    plt.close(fig)


def plot_reference_sizes(data: dict, output: Path) -> None:
    """
    Draw a horizontal bar chart showing the reference set size per variant.

    The chart also reports the candidate count so that the reader can see
    how many distractors each variant brings into the corpus.
    """
    eligible = data.get("per_variant", [])
    if not eligible:
        return

    eligible = sorted(eligible, key=lambda e: e["reference_count"])

    variant_ids = [e["variant_id"] for e in eligible]
    references = [e["reference_count"] for e in eligible]
    candidates = [e["candidate_count"] for e in eligible]

    fig, ax = plt.subplots(figsize=(9, max(3, 0.5 * len(variant_ids) + 1.5)))
    y_positions = list(range(len(variant_ids)))

    ax.barh(
        y_positions,
        candidates,
        color="#d5dbdb",
        label="Candidates in corpus",
    )
    ax.barh(
        y_positions,
        references,
        color="#2980b9",
        label="Reference set",
    )

    for i, (ref, cand) in enumerate(zip(references, candidates)):
        ax.text(ref + 2, i, str(ref), va="center", fontsize=8)
        ax.text(cand + 2, i, str(cand), va="center", fontsize=8, color="#7f8c8d")

    ax.set_yticks(y_positions)
    ax.set_yticklabels(variant_ids, fontsize=9)
    ax.set_xlabel("Number of publications")
    ax.set_title("Reference set and corpus size per variant")
    ax.legend(loc="lower right")
    ax.grid(axis="x", linestyle=":", alpha=0.4)

    fig.tight_layout()
    fig.savefig(output, dpi=150)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate plots from evaluation results."
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=DEFAULT_RESULTS,
        help="Path to evaluation_results.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where plots are written.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.results.exists():
        raise SystemExit(f"missing {args.results}")

    data = load_results(args.results)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = args.output_dir / "benchmark_results.png"
    reference_path = args.output_dir / "reference_sizes.png"

    plot_benchmark_summary(data, summary_path)
    print(f"wrote {summary_path}")

    if data.get("per_variant"):
        plot_reference_sizes(data, reference_path)
        print(f"wrote {reference_path}")
    else:
        print("per_variant data not present; reference plot skipped")


if __name__ == "__main__":
    main()
