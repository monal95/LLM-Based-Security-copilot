"""Automatic hyperparameter tuning for SecureRAG retrieval evaluation."""

from __future__ import annotations

import argparse
import itertools
import json
import random
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from evaluation.evaluation_engine import DEFAULT_QUERIES_FILE, EvaluationConfig, EXPERIMENTS_ROOT, load_queries, run_evaluation_suite


SEARCH_SPACE = {
    "dense_top_k": [10, 20, 30, 50],
    "sparse_top_k": [10, 20, 30, 50],
    "fusion_top_k": [10, 15, 20, 30],
    "rrf_k": [40, 50, 60, 80],
    "dense_weight": [0.4, 0.5, 0.6, 0.7, 0.8],
    "sparse_weight": [0.2, 0.3, 0.4, 0.5, 0.6],
    "reranker_input_limit": [10, 20, 25, 40, 60],
    "reranker_top_k": [3, 5, 10],
    "reranker_alpha": [0.75, 0.85, 0.9],
}


def _sample_configs(max_trials: int, seed: int) -> List[Dict[str, Any]]:
    keys = list(SEARCH_SPACE.keys())
    product = list(itertools.product(*(SEARCH_SPACE[key] for key in keys)))
    rng = random.Random(seed)
    if max_trials >= len(product):
        chosen = product
    else:
        chosen = rng.sample(product, max_trials)
    return [dict(zip(keys, values)) for values in chosen]


def _score_mode(summary: Dict[str, Any]) -> float:
    metrics = summary.get("metrics", {})
    latency_penalty = min(summary.get("avg_latency_ms", 0.0) / 1000.0, 1.0) * 0.05
    return (
        0.35 * metrics.get("recall_10", 0.0)
        + 0.15 * metrics.get("precision_10", 0.0)
        + 0.20 * metrics.get("mrr", 0.0)
        + 0.20 * metrics.get("ndcg_10", 0.0)
        + 0.10 * metrics.get("hit_10", 0.0)
        - latency_penalty
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Hyperparameter search for SecureRAG retrieval")
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES_FILE)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "evaluation" / "hyperparameter_results.json")
    parser.add_argument("--max-trials", type=int, default=12)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--experiment-name", type=str, default="hyperparameter_search")
    args = parser.parse_args()

    queries = load_queries(args.queries)
    configs = _sample_configs(args.max_trials, args.seed)

    trials: List[Dict[str, Any]] = []
    best_config: Dict[str, Any] | None = None
    best_score = float("-inf")

    for index, candidate in enumerate(configs, start=1):
        runtime_config = EvaluationConfig.from_mapping(candidate)
        summary = run_evaluation_suite(
            queries=queries,
            config=runtime_config,
            mode="all",
            experiment_name=f"{args.experiment_name}_{index}",
        )

        mode_scores = {mode: _score_mode(mode_summary) for mode, mode_summary in summary.mode_summaries.items()}
        score = sum(mode_scores.values()) / max(len(mode_scores), 1)
        trial = {
            "trial": index,
            "config": runtime_config.to_dict(),
            "mode_scores": mode_scores,
            "score": score,
            "comparison_table": summary.comparison_table,
            "experiment_dir": str(summary.experiment_dir),
        }
        trials.append(trial)

        if score > best_score:
            best_score = score
            best_config = {
                **runtime_config.to_dict(),
                "selected_score": score,
                "selected_by": "average_mode_score",
                "experiment_dir": str(summary.experiment_dir),
            }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump({"best_config": best_config, "trials": trials}, handle, indent=2)

    best_path = EXPERIMENTS_ROOT / "best_config.json"
    best_path.parent.mkdir(parents=True, exist_ok=True)
    with best_path.open("w", encoding="utf-8") as handle:
        json.dump(best_config, handle, indent=2)

    print(json.dumps({"best_config": best_config}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
