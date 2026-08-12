"""Phase 6 Retrieval Evaluation Script.

Evaluates all 4 retrieval modes independently:
  1. dense
  2. sparse
  3. hybrid
  4. full

For each mode, calculates:
  - Recall@5, Recall@10
  - Precision@5, Precision@10
  - MRR
  - NDCG@5, NDCG@10
  - Hit@1, Hit@3, Hit@5, Hit@10
  - Average latency (ms)

Also computes metrics separately per query category:
  - cve_explanation (100 queries)
  - mitre_mapping (100 queries)
  - incident_response (100 queries)

Outputs:
  - evaluation/results/phase6_retrieval_results.json
  - evaluation/results/phase6_retrieval_results.csv
  - evaluation/results/retrieval_failures.json
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List

from evaluation.evaluation_engine import (
    DEFAULT_BASELINE_CONFIG,
    EvaluationConfig,
    load_config,
    _compute_metrics,
    _extract_identifiers,
)
from modules.Retrieval import dense_retriever, hybrid_fusion, reranker, sparse_retriever, query_expander

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUERIES_FILE = PROJECT_ROOT / "evaluation" / "phase6_queries.json"
RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"

LOGGER = logging.getLogger(__name__)


def load_phase6_queries() -> List[Dict[str, Any]]:
    if not QUERIES_FILE.exists():
        raise FileNotFoundError(f"Queries dataset not found: {QUERIES_FILE}")
    with open(QUERIES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def execute_mode_retrieval(query_text: str, mode: str, config: EvaluationConfig) -> tuple[List[Any], float]:
    """Execute single query retrieval for given mode and measure latency."""
    start = time.perf_counter()

    expanded_queries = query_expander.expand_query(query_text) if config.query_expansion else [query_text]
    retrieval_query = " ".join(expanded_queries)

    if mode == "dense":
        dense_cfg = dense_retriever.DenseRetrieverConfig(top_k=config.dense_top_k)
        response = dense_retriever.run(retrieval_query, config=dense_cfg)
        results = response.results
    elif mode == "sparse":
        sparse_cfg = sparse_retriever.SparseRetrieverConfig(top_k=config.sparse_top_k)
        response = sparse_retriever.run(retrieval_query, config=sparse_cfg)
        results = response.results
    elif mode == "hybrid":
        dense_cfg = dense_retriever.DenseRetrieverConfig(top_k=config.dense_top_k)
        sparse_cfg = sparse_retriever.SparseRetrieverConfig(top_k=config.sparse_top_k)
        d_resp = dense_retriever.run(retrieval_query, config=dense_cfg)
        s_resp = sparse_retriever.run(retrieval_query, config=sparse_cfg)
        fusion_cfg = hybrid_fusion.HybridFusionConfig(
            top_k=config.fusion_top_k,
            rrf_k=config.rrf_k,
            dense_weight=config.dense_weight,
            sparse_weight=config.sparse_weight,
        )
        f_resp = hybrid_fusion.run(query_text, d_resp, s_resp, config=fusion_cfg)
        results = f_resp.results
    elif mode == "full":
        dense_cfg = dense_retriever.DenseRetrieverConfig(top_k=config.dense_top_k)
        sparse_cfg = sparse_retriever.SparseRetrieverConfig(top_k=config.sparse_top_k)
        d_resp = dense_retriever.run(retrieval_query, config=dense_cfg)
        s_resp = sparse_retriever.run(retrieval_query, config=sparse_cfg)
        fusion_cfg = hybrid_fusion.HybridFusionConfig(
            top_k=config.fusion_top_k,
            rrf_k=config.rrf_k,
            dense_weight=config.dense_weight,
            sparse_weight=config.sparse_weight,
        )
        f_resp = hybrid_fusion.run(query_text, d_resp, s_resp, config=fusion_cfg)
        rerank_cfg = reranker.RerankerConfig(
            top_k=config.reranker_top_k,
            input_limit=config.reranker_input_limit,
            score_fusion_alpha=config.reranker_alpha,
        )
        r_resp = reranker.run(query_text, f_resp, config=rerank_cfg)
        results = r_resp.results
    else:
        raise ValueError(f"Unknown retrieval mode: {mode}")

    latency_ms = (time.perf_counter() - start) * 1000.0
    return results, latency_ms


def evaluate_mode(queries: List[Dict[str, Any]], mode: str, config: EvaluationConfig) -> Dict[str, Any]:
    LOGGER.info("Evaluating retrieval mode: %s across %d queries...", mode, len(queries))

    latencies: List[float] = []
    all_metrics: List[Dict[str, float]] = []
    category_results: Dict[str, List[Dict[str, float]]] = {}
    failed_queries: List[Dict[str, Any]] = []

    for q in queries:
        q_id = q["id"]
        cat = q["category"]
        q_text = q["query"]
        expected = [str(x).upper() for x in q.get("expected_documents", [])]

        results, latency = execute_mode_retrieval(q_text, mode, config)
        latencies.append(latency)

        # Extract predicted entity IDs per ranked chunk
        ranked_identifiers = [_extract_identifiers(item) for item in results]

        # Deduplicate entity hits across chunks so entity-level relevance is evaluated
        metrics = _compute_metrics(expected, ranked_identifiers)
        all_metrics.append(metrics)

        if cat not in category_results:
            category_results[cat] = []
        category_results[cat].append(metrics)

        # Record failures (hit@5 == 0 or recall@5 == 0)
        if metrics.get("hit_5", 0) == 0:
            top_5_items = [str(getattr(item, "document", getattr(item, "text", "")))[:150] for item in results[:5]]
            top_10_items = [str(getattr(item, "document", getattr(item, "text", "")))[:150] for item in results[:10]]

            # Determine rank of correct document
            correct_rank = None
            for r_idx, ids in enumerate(ranked_identifiers, start=1):
                if any(exp in ids for exp in expected):
                    correct_rank = r_idx
                    break

            failed_queries.append({
                "id": q_id,
                "category": cat,
                "query": q_text,
                "expected": expected,
                "retrieved_top_5": top_5_items,
                "retrieved_top_10": top_10_items,
                "rank_of_correct": correct_rank,
                "retrieval_mode": mode,
                "recall_5": metrics.get("recall_5", 0.0),
                "mrr": metrics.get("mrr", 0.0),
                "ndcg_5": metrics.get("ndcg_5", 0.0),
            })

    def avg(key: str, metric_list: List[Dict[str, float]]) -> float:
        return round(sum(m.get(key, 0.0) for m in metric_list) / max(1, len(metric_list)), 4)

    mode_summary = {
        "mode": mode,
        "total_queries": len(queries),
        "recall_5": avg("recall_5", all_metrics),
        "recall_10": avg("recall_10", all_metrics),
        "precision_5": avg("precision_5", all_metrics),
        "precision_10": avg("precision_10", all_metrics),
        "mrr": avg("mrr", all_metrics),
        "ndcg_5": avg("ndcg_5", all_metrics),
        "ndcg_10": avg("ndcg_10", all_metrics),
        "hit_1": avg("hit_1", all_metrics),
        "hit_3": avg("hit_3", all_metrics),
        "hit_5": avg("hit_5", all_metrics),
        "hit_10": avg("hit_10", all_metrics),
        "avg_latency_ms": round(sum(latencies) / max(1, len(latencies)), 2),
        "category_breakdown": {
            cat: {
                "count": len(items),
                "recall_5": avg("recall_5", items),
                "recall_10": avg("recall_10", items),
                "precision_5": avg("precision_5", items),
                "precision_10": avg("precision_10", items),
                "mrr": avg("mrr", items),
                "ndcg_5": avg("ndcg_5", items),
                "ndcg_10": avg("ndcg_10", items),
            }
            for cat, items in category_results.items()
        },
    }

    return mode_summary, failed_queries


def main():
    parser = argparse.ArgumentParser(description="Phase 6 Retrieval Evaluation")
    parser.add_argument("--mode", choices=["dense", "sparse", "hybrid", "full", "all"], default="all")
    parser.add_argument("--config", type=Path, default=DEFAULT_BASELINE_CONFIG)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    queries = load_phase6_queries()
    config = load_config(args.config)

    modes = ["dense", "sparse", "hybrid", "full"] if args.mode == "all" else [args.mode]

    all_mode_results = {}
    all_failures = {}

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    for mode in modes:
        mode_res, failures = evaluate_mode(queries, mode, config)
        all_mode_results[mode] = mode_res
        all_failures[mode] = failures

    # Write results JSON
    json_path = RESULTS_DIR / "phase6_retrieval_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_mode_results, f, indent=2)
    LOGGER.info("Saved retrieval evaluation results -> %s", json_path)

    # Write failures JSON
    failures_path = RESULTS_DIR / "retrieval_failures.json"
    with open(failures_path, "w", encoding="utf-8") as f:
        json.dump(all_failures, f, indent=2)
    LOGGER.info("Saved retrieval failures -> %s", failures_path)

    # Write CSV summary
    csv_path = RESULTS_DIR / "phase6_retrieval_results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Mode", "Recall@5", "Recall@10", "Precision@5", "Precision@10",
            "MRR", "NDCG@5", "NDCG@10", "Hit@1", "Hit@3", "Hit@5", "Hit@10", "Avg Latency (ms)"
        ])
        for mode, data in all_mode_results.items():
            writer.writerow([
                mode, data["recall_5"], data["recall_10"], data["precision_5"], data["precision_10"],
                data["mrr"], data["ndcg_5"], data["ndcg_10"], data["hit_1"], data["hit_3"],
                data["hit_5"], data["hit_10"], data["avg_latency_ms"]
            ])
    LOGGER.info("Saved CSV summary -> %s", csv_path)

    # Print summary table
    print("\n" + "=" * 90)
    print("PHASE 6 RETRIEVAL EVALUATION RESULTS (300 QUERIES)")
    print("=" * 90)
    print(f"{'Mode':<10} | {'R@5':<7} | {'R@10':<7} | {'P@5':<7} | {'P@10':<7} | {'MRR':<7} | {'NDCG@5':<8} | {'NDCG@10':<8} | {'Latency':<8}")
    print("-" * 90)
    for mode, data in all_mode_results.items():
        print(f"{mode:<10} | {data['recall_5']:<7.4f} | {data['recall_10']:<7.4f} | {data['precision_5']:<7.4f} | {data['precision_10']:<7.4f} | {data['mrr']:<7.4f} | {data['ndcg_5']:<8.4f} | {data['ndcg_10']:<8.4f} | {data['avg_latency_ms']:<8.1f}ms")
    print("=" * 90)


if __name__ == "__main__":
    main()
