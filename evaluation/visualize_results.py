"""Generate plots for SecureRAG retrieval experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import matplotlib.pyplot as plt
import pandas as pd

from evaluation.evaluation_engine import EXPERIMENTS_ROOT


def _load_summary(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _collect_rows(experiments_root: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for summary_file in sorted(experiments_root.glob("*/evaluation_summary.json")):
        summary = _load_summary(summary_file)
        for mode, mode_summary in summary.get("mode_summaries", {}).items():
            metrics = mode_summary.get("metrics", {})
            rows.append(
                {
                    "experiment": summary.get("experiment_name", summary_file.parent.name),
                    "mode": mode,
                    "recall_10": metrics.get("recall_10", 0.0),
                    "precision_10": metrics.get("precision_10", 0.0),
                    "mrr": metrics.get("mrr", 0.0),
                    "ndcg_10": metrics.get("ndcg_10", 0.0),
                    "avg_latency_ms": mode_summary.get("avg_latency_ms", 0.0),
                }
            )
    return rows


def _plot_metric(frame: pd.DataFrame, metric: str, title: str, output_path: Path) -> None:
    pivot = frame.pivot(index="experiment", columns="mode", values=metric).fillna(0.0)
    ax = pivot.plot(kind="bar", figsize=(12, 6), width=0.85)
    ax.set_title(title)
    ax.set_xlabel("Experiment")
    ax.set_ylabel(metric.replace("_", " ").title())
    ax.legend(title="Mode", bbox_to_anchor=(1.02, 1), loc="upper left")
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=200)
    plt.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Visualize SecureRAG experiments")
    parser.add_argument("--experiments-root", type=Path, default=EXPERIMENTS_ROOT)
    parser.add_argument("--output-dir", type=Path, default=EXPERIMENTS_ROOT / "plots")
    args = parser.parse_args()

    rows = _collect_rows(args.experiments_root)
    if not rows:
        print("No experiments found.")
        return 0

    frame = pd.DataFrame(rows)
    _plot_metric(frame, "recall_10", "SecureRAG Recall@10 by Experiment", args.output_dir / "recall.png")
    _plot_metric(frame, "precision_10", "SecureRAG Precision@10 by Experiment", args.output_dir / "precision.png")
    _plot_metric(frame, "mrr", "SecureRAG MRR by Experiment", args.output_dir / "mrr.png")
    _plot_metric(frame, "ndcg_10", "SecureRAG nDCG@10 by Experiment", args.output_dir / "ndcg.png")
    _plot_metric(frame, "avg_latency_ms", "SecureRAG Latency by Experiment", args.output_dir / "latency.png")

    print(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())