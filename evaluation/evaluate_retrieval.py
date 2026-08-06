"""Backward-compatible wrapper for the research-grade evaluation engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from evaluation.evaluation_engine import (
    DEFAULT_BASELINE_CONFIG,
    DEFAULT_QUERIES_FILE,
    EvaluationConfig,
    build_experiment_report,
    load_config,
    load_queries,
    run_evaluation_suite,
)


def _load_queries(queries_file: Path) -> List[Dict[str, Any]]:
    return load_queries(queries_file)


def _load_config(config_file: Path) -> Dict[str, Any]:
    return load_config(config_file).to_dict()


def run_evaluation(
    queries: List[Dict[str, Any]],
    mode: str = "dense",
    config_dict: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    summary = run_evaluation_suite(
        queries=queries,
        config=EvaluationConfig.from_mapping(config_dict or {}),
        mode=mode,
        experiment_name="compatibility_run",
    )
    if mode == "all":
        return {
            "mode": "all",
            "modes": summary.mode_summaries,
            "comparison_table": summary.comparison_table,
        }
    mode_summary = summary.mode_summaries[mode]
    flat_result = {
        "mode": mode,
        "total_queries": mode_summary["query_count"],
        "avg_latency_ms": mode_summary["avg_latency_ms"],
        "per_stage_latency_ms": mode_summary["per_stage_latency_ms"],
    }
    flat_result.update(mode_summary["metrics"])
    return flat_result


def main() -> int:
    summary = build_experiment_report(
        queries_file=DEFAULT_QUERIES_FILE,
        config_file=DEFAULT_BASELINE_CONFIG,
        mode="all",
        experiment_name="secure_rag_evaluation",
    )
    print(summary.experiment_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
