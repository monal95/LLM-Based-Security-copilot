"""
Compare SecureRAG retrieval experiments.

Displays ALL retrieval modes (dense, sparse, hybrid, full)
for every experiment instead of only the best mode.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from evaluation.evaluation_engine import EXPERIMENTS_ROOT


def load_summary(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def collect_experiments(experiments_root: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    if not experiments_root.exists():
        return rows

    summaries = sorted(
        experiments_root.glob("*/evaluation_summary.json"),
        reverse=True,
    )

    for summary_file in summaries:

        summary = load_summary(summary_file)

        experiment = summary.get(
            "experiment_name",
            summary_file.parent.name,
        )

        timestamp = summary.get(
            "timestamp_utc",
            "",
        )

        for row in summary.get("comparison_table", []):

            rows.append(
                {
                    "experiment": experiment,
                    "timestamp_utc": timestamp,
                    "mode": row.get("mode", ""),
                    "queries": row.get("queries", 0),

                    "recall_5": row.get("recall_5", 0),
                    "recall_10": row.get("recall_10", 0),
                    "precision_5": row.get("precision_5", 0),
                    "precision_10": row.get("precision_10", 0),

                    "hit_1": row.get("hit_1", 0),
                    "hit_5": row.get("hit_5", 0),
                    "hit_10": row.get("hit_10", 0),

                    "mrr": row.get("mrr", 0),
                    "ndcg_5": row.get("ndcg_5", 0),
                    "ndcg_10": row.get("ndcg_10", 0),

                    "latency_ms": row.get("avg_latency_ms", 0),

                    "dense_ms": row.get("dense_ms", 0),
                    "sparse_ms": row.get("sparse_ms", 0),
                    "fusion_ms": row.get("fusion_ms", 0),
                    "reranker_ms": row.get("reranker_ms", 0),

                    "path": str(summary_file.parent),
                }
            )

    return rows


def main() -> int:

    parser = argparse.ArgumentParser(
        description="Compare SecureRAG experiments"
    )

    parser.add_argument(
        "--experiments-root",
        type=Path,
        default=EXPERIMENTS_ROOT,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )

    args = parser.parse_args()

    rows = collect_experiments(args.experiments_root)

    if not rows:
        print("No experiments found.")
        return 0

    frame = pd.DataFrame(rows)

    mode_order = {
        "dense": 0,
        "sparse": 1,
        "hybrid": 2,
        "full": 3,
    }

    frame["mode_order"] = frame["mode"].map(mode_order)

    frame = frame.sort_values(
        ["timestamp_utc", "experiment", "mode_order"],
        ascending=[False, True, True],
    )

    frame = frame.drop(columns=["mode_order"])

    display = frame[
        [
            "experiment",
            "timestamp_utc",
            "mode",
            "queries",
            "recall_10",
            "precision_10",
            "hit_10",
            "mrr",
            "ndcg_10",
            "latency_ms",
        ]
    ].copy()

    metric_columns = [
        "recall_10",
        "precision_10",
        "hit_10",
        "mrr",
        "ndcg_10",
    ]

    for col in metric_columns:
        display[col] = display[col].map(lambda x: f"{x:.4f}")

    display["latency_ms"] = display["latency_ms"].map(
        lambda x: f"{x:.2f}"
    )

    print("\n================ SECURERAG EXPERIMENT COMPARISON ================\n")

    print(display.to_string(index=False))

    if args.output:

        args.output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        frame.to_csv(args.output, index=False)

        print(f"\nCSV saved to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())