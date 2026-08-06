"""Targeted Reciprocal Rank Fusion tuning helper."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from evaluation.evaluation_engine import DEFAULT_QUERIES_FILE, EvaluationConfig, load_queries, run_evaluation_suite


def main() -> int:
    parser = argparse.ArgumentParser(description="Tune the RRF k-constant")
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES_FILE)
    parser.add_argument("--k-values", type=int, nargs="+", default=[30, 40, 50, 60, 80])
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "evaluation" / "rrf_tuning_results.json")
    args = parser.parse_args()

    queries = load_queries(args.queries)
    results: List[Dict[str, Any]] = []
    best_k = None
    best_score = float("-inf")

    for k in args.k_values:
        config = EvaluationConfig.from_mapping({"rrf_k": k, "dense_top_k": 30, "sparse_top_k": 30, "fusion_top_k": 30})
        summary = run_evaluation_suite(queries=queries, config=config, mode="hybrid", experiment_name=f"rrf_k_{k}")
        mode_summary = summary.mode_summaries["hybrid"]
        metrics = mode_summary["metrics"]
        score = metrics["recall_10"] + metrics["mrr"] + metrics["ndcg_10"]

        results.append({"rrf_k": k, **mode_summary, "score": score})
        if score > best_score:
            best_score = score
            best_k = k

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump({"best_rrf_k": best_k, "results": results}, handle, indent=2)

    print(json.dumps({"best_rrf_k": best_k}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
