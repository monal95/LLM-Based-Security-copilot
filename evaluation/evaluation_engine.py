"""Research-grade retrieval evaluation engine for SecureRAG.

This module orchestrates retrieval experiments across the supported retrieval
modes, computes ranking metrics, aggregates category-level results, and writes
experiment artifacts suitable for reproducible reporting.

Public entry points:
    - load_queries(path)
    - load_config(path)
    - run_evaluation_suite(...)
    - build_experiment_report(...)
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from threading import Lock
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUERIES_FILE = PROJECT_ROOT / "evaluation" / "retrieval_queries.json"
DEFAULT_BASELINE_CONFIG = PROJECT_ROOT / "evaluation" / "baseline_config.json"
EXPERIMENTS_ROOT = PROJECT_ROOT / "evaluation" / "experiments"

LOGGER = logging.getLogger(__name__)

SUPPORTED_MODES = ("dense", "sparse", "hybrid", "full", "all")
METRIC_KS = (1, 3, 5, 10, 20, 30)
RECALL_KS = (5, 10, 20, 30)
PRECISION_KS = (5, 10)
NDCG_KS = (5, 10)

_CVE_PATTERN = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
_TECHNIQUE_PATTERN = re.compile(r"\bT\d{4}(?:\.\d{3})?\b", re.IGNORECASE)
_IOC_PATTERN = re.compile(
    r"\b(?:[a-f0-9]{32}|[a-f0-9]{40}|[a-f0-9]{64}|(?:\d{1,3}\.){3}\d{1,3}|[a-z0-9.-]+\.[a-z]{2,})\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class EvaluationConfig:
    """Evaluation and retrieval controls loaded from baseline_config.json."""

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    dense_top_k: int = 10
    sparse_top_k: int = 10
    fusion_top_k: int = 15
    rrf_k: int = 60
    dense_weight: float = 0.5
    sparse_weight: float = 0.5
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranker_input_limit: int = 25
    reranker_top_k: int = 5
    reranker_alpha: float = 0.85
    metadata_boost: float = 0.0
    query_expansion: bool = True
    cve_metadata_lookup: bool = True
    mitre_metadata_lookup: bool = True

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "EvaluationConfig":
        data = dict(payload or {})
        defaults = cls()

        return cls(
            embedding_model=str(data.get("embedding_model", defaults.embedding_model)),
            dense_top_k=int(data.get("dense_top_k", defaults.dense_top_k)),
            sparse_top_k=int(data.get("sparse_top_k", defaults.sparse_top_k)),
            fusion_top_k=int(data.get("fusion_top_k", defaults.fusion_top_k)),
            rrf_k=int(data.get("rrf_k", defaults.rrf_k)),
            dense_weight=float(data.get("dense_weight", defaults.dense_weight)),
            sparse_weight=float(data.get("sparse_weight", defaults.sparse_weight)),
            reranker_model=str(data.get("reranker_model", defaults.reranker_model)),
            reranker_input_limit=int(data.get("reranker_input_limit", defaults.reranker_input_limit)),
            reranker_top_k=int(data.get("reranker_top_k", defaults.reranker_top_k)),
            reranker_alpha=float(data.get("reranker_alpha", defaults.reranker_alpha)),
            metadata_boost=float(data.get("metadata_boost", defaults.metadata_boost)),
            query_expansion=bool(data.get("query_expansion", defaults.query_expansion)),
            cve_metadata_lookup=bool(data.get("cve_metadata_lookup", defaults.cve_metadata_lookup)),
            mitre_metadata_lookup=bool(data.get("mitre_metadata_lookup", defaults.mitre_metadata_lookup)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "embedding_model": self.embedding_model,
            "dense_top_k": self.dense_top_k,
            "sparse_top_k": self.sparse_top_k,
            "fusion_top_k": self.fusion_top_k,
            "rrf_k": self.rrf_k,
            "dense_weight": self.dense_weight,
            "sparse_weight": self.sparse_weight,
            "reranker_model": self.reranker_model,
            "reranker_input_limit": self.reranker_input_limit,
            "reranker_top_k": self.reranker_top_k,
            "reranker_alpha": self.reranker_alpha,
            "metadata_boost": self.metadata_boost,
            "query_expansion": self.query_expansion,
            "cve_metadata_lookup": self.cve_metadata_lookup,
            "mitre_metadata_lookup": self.mitre_metadata_lookup,
        }


@dataclass(slots=True)
class StageLatency:
    dense_ms: float = 0.0
    sparse_ms: float = 0.0
    fusion_ms: float = 0.0
    reranker_ms: float = 0.0
    total_ms: float = 0.0


@dataclass(slots=True)
class QueryResult:
    experiment_mode: str
    query: str
    category: str
    normalized_category: str
    expected: List[str]
    predicted: List[str]
    per_stage_latency_ms: StageLatency
    metrics: Dict[str, float]
    hit_at_30: int
    failure_reason: Optional[str] = None
    retrieval_diagnostics: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExperimentSummary:
    experiment_name: str
    experiment_dir: Path
    timestamp_utc: str
    config: EvaluationConfig
    mode_summaries: Dict[str, Dict[str, Any]]
    category_summaries: Dict[str, Dict[str, Any]]
    comparison_table: List[Dict[str, Any]]
    per_query_results: List[Dict[str, Any]]
    failed_queries: List[Dict[str, Any]]
    artifacts: Dict[str, str]


@dataclass(slots=True)
class _ParallelRetrievalResult:
    dense_response: Any | None = None
    sparse_response: Any | None = None
    dense_error: Exception | None = None
    sparse_error: Exception | None = None
    wall_ms: float = 0.0


@dataclass(slots=True)
class _PipelineArtifacts:
    retrieval_query: str
    expanded_queries: List[str]
    dense_response: Any | None = None
    sparse_response: Any | None = None
    fused_response: Any | None = None
    reranked_response: Any | None = None
    dense_error: Exception | None = None
    sparse_error: Exception | None = None
    fusion_error: Exception | None = None
    rerank_error: Exception | None = None
    dense_ms: float = 0.0
    sparse_ms: float = 0.0
    retrieval_wall_ms: float = 0.0
    fusion_ms: float = 0.0
    reranker_ms: float = 0.0


_RETRIEVAL_PAIR_CACHE: Dict[Tuple[Any, ...], _ParallelRetrievalResult] = {}
_RETRIEVAL_PAIR_CACHE_LOCK = Lock()


def _configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")


def _load_json(path: Path, *, required: bool = True, default: Any = None) -> Any:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"File not found: {path}")
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_queries(path: Path = DEFAULT_QUERIES_FILE) -> List[Dict[str, Any]]:
    payload = _load_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Expected an array in {path}")
    queries: List[Dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        query = str(item.get("query", "")).strip()
        if not query:
            continue
        queries.append(
            {
                "query": query,
                "category": str(item.get("category", "Uncategorized")).strip() or "Uncategorized",
                "expected": [str(value).upper() for value in item.get("expected", []) if str(value).strip()],
            }
        )
    return queries


def load_config(path: Path = DEFAULT_BASELINE_CONFIG) -> EvaluationConfig:
    payload = _load_json(path, required=False, default={})
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected mapping in {path}")
    return EvaluationConfig.from_mapping(payload)


def _ensure_experiment_dir(base_dir: Path = EXPERIMENTS_ROOT, experiment_name: Optional[str] = None) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_name = _slugify(experiment_name or "evaluation")
    experiment_dir = base_dir / f"{timestamp}_{safe_name}"
    suffix = 1
    while experiment_dir.exists():
        experiment_dir = base_dir / f"{timestamp}_{safe_name}_{suffix}"
        suffix += 1
    experiment_dir.mkdir(parents=True, exist_ok=False)
    return experiment_dir


def _slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return value or "evaluation"


def _coerce_metadata(metadata: Any) -> Dict[str, Any]:
    if isinstance(metadata, dict):
        return metadata
    if metadata is None:
        return {}
    return {"raw_metadata": str(metadata)}


def _extract_identifiers(item: Any) -> List[str]:
    identifiers: List[str] = []
    metadata = _coerce_metadata(getattr(item, "metadata", {}) or {})
    for key in ("cve_id", "technique_id", "id", "chunk_id"):
        value = metadata.get(key)
        if value:
            identifiers.append(str(value).upper())

    text = str(getattr(item, "document", None) or getattr(item, "text", None) or "")
    identifiers.extend(match.upper() for match in _CVE_PATTERN.findall(text))
    identifiers.extend(match.upper() for match in _TECHNIQUE_PATTERN.findall(text))
    return list(dict.fromkeys(identifiers))


def _extract_query_entities(query: str) -> Dict[str, List[str]]:
    return {
        "cves": list(dict.fromkeys(match.upper() for match in _CVE_PATTERN.findall(query))),
        "techniques": list(dict.fromkeys(match.upper() for match in _TECHNIQUE_PATTERN.findall(query))),
        "iocs": list(dict.fromkeys(match.lower() for match in _IOC_PATTERN.findall(query))),
    }


def _compute_dcg(relevances: Sequence[int], k: int) -> float:
    score = 0.0
    for index, relevance in enumerate(relevances[:k]):
        if relevance > 0:
            score += (2**relevance - 1) / math.log2(index + 2)
    return score


def _compute_metrics(expected: Sequence[str], ranked_identifiers: Sequence[Sequence[str]]) -> Dict[str, float]:
    expected_set = {str(value).upper() for value in expected if str(value).strip()}
    if not expected_set:
        return {metric: 0.0 for metric in [
            *(f"recall_{k}" for k in RECALL_KS),
            *(f"precision_{k}" for k in PRECISION_KS),
            *(f"hit_{k}" for k in METRIC_KS),
            "mrr",
            *(f"ndcg_{k}" for k in NDCG_KS),
        ]}

    per_rank_hits = [1 if expected_set.intersection({identifier.upper() for identifier in identifiers}) else 0 for identifiers in ranked_identifiers]

    metrics: Dict[str, float] = {}
    for k in RECALL_KS:
        found = set()
        for identifiers in ranked_identifiers[:k]:
            found.update(identifier.upper() for identifier in identifiers)
        metrics[f"recall_{k}"] = len(found.intersection(expected_set)) / float(len(expected_set))

    for k in PRECISION_KS:
        metrics[f"precision_{k}"] = sum(per_rank_hits[:k]) / float(k)

    for k in METRIC_KS:
        metrics[f"hit_{k}"] = 1.0 if any(per_rank_hits[:k]) else 0.0

    mrr = 0.0
    for index, relevance in enumerate(per_rank_hits):
        if relevance:
            mrr = 1.0 / float(index + 1)
            break
    metrics["mrr"] = mrr

    ideal_length = max(len(expected_set), len(per_rank_hits))
    ideal_relevances = [1] * len(expected_set) + [0] * max(0, ideal_length - len(expected_set))
    for k in NDCG_KS:
        dcg = _compute_dcg(per_rank_hits, k)
        idcg = _compute_dcg(ideal_relevances, k)
        metrics[f"ndcg_{k}"] = dcg / idcg if idcg > 0 else 0.0

    return metrics


def _extract_result_payload(response: Any, *, preferred_score_attr: str) -> List[Dict[str, Any]]:
    results = getattr(response, "results", None)
    if not isinstance(results, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for item in results:
        metadata = _coerce_metadata(getattr(item, "metadata", {}) or {})
        identifiers = _extract_identifiers(item)
        score = getattr(item, preferred_score_attr, None)
        if score is None:
            score = getattr(item, "similarity_score", None)
        if score is None:
            score = getattr(item, "fusion_score", None)
        if score is None:
            score = getattr(item, "score", 0.0)
        normalized.append(
            {
                "rank": int(getattr(item, "rank", len(normalized) + 1) or len(normalized) + 1),
                "score": float(score or 0.0),
                "document": str(getattr(item, "document", None) or getattr(item, "text", None) or ""),
                "metadata": metadata,
                "chunk_id": getattr(item, "chunk_id", None),
                "identifiers": identifiers,
            }
        )
    return normalized


def _boost_ranked_items(
    items: List[Dict[str, Any]],
    query: str,
    config: EvaluationConfig,
) -> List[Dict[str, Any]]:
    if config.metadata_boost <= 0:
        return items

    query_entities = _extract_query_entities(query)
    boosted: List[Dict[str, Any]] = []
    for item in items:
        score = float(item["score"])
        metadata = item["metadata"]

        boosts = 0.0
        cve_id = str(metadata.get("cve_id", "")).upper()
        technique_id = str(metadata.get("technique_id", "")).upper()

        if config.cve_metadata_lookup and cve_id and cve_id in query_entities["cves"]:
            boosts += config.metadata_boost
        if config.mitre_metadata_lookup and technique_id and technique_id in query_entities["techniques"]:
            boosts += config.metadata_boost

        if boosts:
            score += boosts

        boosted.append({**item, "score": score})

    boosted.sort(key=lambda payload: (payload["score"], payload["rank"]), reverse=True)
    for index, item in enumerate(boosted, start=1):
        item["rank"] = index
    return boosted


def _primary_category(raw_category: str, query: str, expected: Sequence[str]) -> str:
    category = (raw_category or "").strip().lower()
    text = f"{raw_category} {query}".lower()
    expected_text = " ".join(str(value).upper() for value in expected)

    if _CVE_PATTERN.search(expected_text) or any(token in category for token in ["cve", "vulnerability", "exploit", "cwe"]):
        return "CVE"
    if _TECHNIQUE_PATTERN.search(expected_text) or "attack" in category:
        return "MITRE ATT&CK"
    if "ransomware" in text:
        return "Ransomware"
    if "malware" in text:
        return "Malware"
    if any(keyword in text for keyword in ["threat actor", "apt", "unc", "fin ", "lazarus", "actor"]):
        return "Threat Actor"
    if any(keyword in text for keyword in ["patch", "mitigation", "remediat", "update", "hotfix"]):
        return "Patch"
    if any(keyword in text for keyword in ["ioc", "indicator", "hash", "domain", "ip address", "url"]):
        return "IOC"
    if any(keyword in text for keyword in ["triage", "prioritize", "investigate", "contain", "respond", "workflow", "incident"]):
        return "SOC Workflow"
    if any(keyword in category for keyword in ["vendor", "product"]):
        return "Vendor"
    if "natural language" in category:
        return "Natural Language"
    return "Natural Language"


def _build_mode_query(
    query: str,
    config: EvaluationConfig,
) -> Tuple[str, List[str]]:
    if not config.query_expansion:
        return query, [query]

    from modules.Retrieval import query_expander

    expanded = query_expander.expand_query(query)
    if len(expanded) == 1:
        return query, expanded
    return " ".join(expanded), expanded


def _build_dense_config(config: EvaluationConfig):
    from modules.Retrieval import dense_retriever

    return dense_retriever.DenseRetrieverConfig(
        embedding_model=config.embedding_model,
        top_k=config.dense_top_k,
    )


@lru_cache(maxsize=32)
def _cached_dense_config(
    embedding_model: str,
    dense_top_k: int,
):
    from modules.Retrieval import dense_retriever

    return dense_retriever.DenseRetrieverConfig(
        embedding_model=embedding_model,
        top_k=dense_top_k,
    )


def _build_sparse_config(config: EvaluationConfig):
    from modules.Retrieval import sparse_retriever

    return sparse_retriever.SparseRetrieverConfig(top_k=config.sparse_top_k)


@lru_cache(maxsize=32)
def _cached_sparse_config(sparse_top_k: int):
    from modules.Retrieval import sparse_retriever

    return sparse_retriever.SparseRetrieverConfig(top_k=sparse_top_k)


def _build_fusion_config(config: EvaluationConfig):
    from modules.Retrieval import hybrid_fusion

    return hybrid_fusion.HybridFusionConfig(
        top_k=config.fusion_top_k,
        rrf_k=config.rrf_k,
        dense_weight=config.dense_weight,
        sparse_weight=config.sparse_weight,
    )


@lru_cache(maxsize=32)
def _cached_fusion_config(
    fusion_top_k: int,
    rrf_k: int,
    dense_weight: float,
    sparse_weight: float,
):
    from modules.Retrieval import hybrid_fusion

    return hybrid_fusion.HybridFusionConfig(
        top_k=fusion_top_k,
        rrf_k=rrf_k,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
    )


def _build_reranker_config(config: EvaluationConfig):
    from modules.Retrieval import reranker

    return reranker.RerankerConfig(
        model_name=config.reranker_model,
        top_k=config.reranker_top_k,
        input_limit=config.reranker_input_limit,
        score_fusion_alpha=config.reranker_alpha,
    )


@lru_cache(maxsize=32)
def _cached_reranker_config(
    reranker_model: str,
    reranker_top_k: int,
    reranker_input_limit: int,
    reranker_alpha: float,
):
    from modules.Retrieval import reranker

    return reranker.RerankerConfig(
        model_name=reranker_model,
        top_k=reranker_top_k,
        input_limit=reranker_input_limit,
        score_fusion_alpha=reranker_alpha,
    )


def _mode_order(mode: str) -> Tuple[str, ...]:
    if mode == "all":
        return ("dense", "sparse", "hybrid", "full")
    return (mode,)


def _empty_stage_result() -> StageLatency:
    return StageLatency()


def _run_retrieval_pair(query: str, config: EvaluationConfig) -> _ParallelRetrievalResult:
    from modules.Retrieval import dense_retriever, sparse_retriever

    cache_key = (
        query,
        config.embedding_model,
        config.dense_top_k,
        config.sparse_top_k,
        config.query_expansion,
    )
    with _RETRIEVAL_PAIR_CACHE_LOCK:
        cached_result = _RETRIEVAL_PAIR_CACHE.get(cache_key)
    if cached_result is not None:
        return cached_result

    dense_config = _cached_dense_config(config.embedding_model, config.dense_top_k)
    sparse_config = _cached_sparse_config(config.sparse_top_k)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as executor:
        dense_future = executor.submit(dense_retriever.run, query, dense_config)
        sparse_future = executor.submit(sparse_retriever.run, query, sparse_config)

        dense_response = None
        sparse_response = None
        dense_error: Exception | None = None
        sparse_error: Exception | None = None

        try:
            dense_response = dense_future.result()
        except Exception as exc:  # pragma: no cover - propagated to caller logic
            dense_error = exc

        try:
            sparse_response = sparse_future.result()
        except Exception as exc:  # pragma: no cover - propagated to caller logic
            sparse_error = exc

    wall_ms = (time.perf_counter() - started) * 1000.0
    result = _ParallelRetrievalResult(
        dense_response=dense_response,
        sparse_response=sparse_response,
        dense_error=dense_error,
        sparse_error=sparse_error,
        wall_ms=wall_ms,
    )
    with _RETRIEVAL_PAIR_CACHE_LOCK:
        _RETRIEVAL_PAIR_CACHE[cache_key] = result
    return result


def _execute_query_pipeline(query: str, config: EvaluationConfig) -> _PipelineArtifacts:
    from modules.Retrieval import hybrid_fusion, reranker

    retrieval_query, expanded = _build_mode_query(query, config)
    artifacts = _PipelineArtifacts(retrieval_query=retrieval_query, expanded_queries=expanded)

    retrieval_pair = _run_retrieval_pair(retrieval_query, config)
    artifacts.dense_response = retrieval_pair.dense_response
    artifacts.sparse_response = retrieval_pair.sparse_response
    artifacts.dense_error = retrieval_pair.dense_error
    artifacts.sparse_error = retrieval_pair.sparse_error
    artifacts.retrieval_wall_ms = retrieval_pair.wall_ms

    if retrieval_pair.dense_response is not None:
        artifacts.dense_ms = float(getattr(retrieval_pair.dense_response, "latency_ms", retrieval_pair.wall_ms))
    if retrieval_pair.sparse_response is not None:
        artifacts.sparse_ms = float(getattr(retrieval_pair.sparse_response, "latency_ms", retrieval_pair.wall_ms))

    if artifacts.dense_error is None and artifacts.sparse_error is None:
        start = time.perf_counter()
        try:
            artifacts.fused_response = hybrid_fusion.run(
                retrieval_query,
                artifacts.dense_response,
                artifacts.sparse_response,
                config=_cached_fusion_config(
                    config.fusion_top_k,
                    config.rrf_k,
                    config.dense_weight,
                    config.sparse_weight,
                ),
            )
            artifacts.fusion_ms = float(getattr(artifacts.fused_response, "latency_ms", (time.perf_counter() - start) * 1000.0))
        except Exception as exc:
            artifacts.fusion_error = exc
            artifacts.fusion_ms = (time.perf_counter() - start) * 1000.0

    if artifacts.fusion_error is None and artifacts.fused_response is not None:
        start = time.perf_counter()
        try:
            artifacts.reranked_response = reranker.run(
                retrieval_query,
                artifacts.fused_response,
                config=_cached_reranker_config(
                    config.reranker_model,
                    config.reranker_top_k,
                    config.reranker_input_limit,
                    config.reranker_alpha,
                ),
            )
            artifacts.reranker_ms = float(getattr(artifacts.reranked_response, "latency_ms", (time.perf_counter() - start) * 1000.0))
        except Exception as exc:
            artifacts.rerank_error = exc
            artifacts.reranker_ms = (time.perf_counter() - start) * 1000.0

    return artifacts


def _empty_metrics() -> Dict[str, float]:
    return {
        **{f"recall_{k}": 0.0 for k in RECALL_KS},
        **{f"precision_{k}": 0.0 for k in PRECISION_KS},
        **{f"hit_{k}": 0.0 for k in METRIC_KS},
        "mrr": 0.0,
        **{f"ndcg_{k}": 0.0 for k in NDCG_KS},
    }


def _materialize_query_result(
    *,
    current_mode: str,
    query_text: str,
    category: str,
    expected: List[str],
    normalized_category: str,
    config: EvaluationConfig,
    artifacts: _PipelineArtifacts,
    total_ms: float,
) -> Tuple[QueryResult, Dict[str, Any], bool]:
    diagnostics: Dict[str, Any] = {
        "retrieval_query": artifacts.retrieval_query,
        "expanded_queries": artifacts.expanded_queries,
        "retrieval_wall_ms": artifacts.retrieval_wall_ms,
    }

    stage_latency = StageLatency(
        dense_ms=artifacts.dense_ms,
        sparse_ms=artifacts.sparse_ms,
        fusion_ms=artifacts.fusion_ms,
        reranker_ms=artifacts.reranker_ms,
        total_ms=total_ms,
    )

    if current_mode == "dense":
        response = artifacts.dense_response
        preferred_score_attr = "similarity_score"
        failure = artifacts.dense_error
    elif current_mode == "sparse":
        response = artifacts.sparse_response
        preferred_score_attr = "score"
        failure = artifacts.sparse_error
    elif current_mode == "hybrid":
        response = artifacts.fused_response
        preferred_score_attr = "fusion_score"
        failure = artifacts.dense_error or artifacts.sparse_error or artifacts.fusion_error
    elif current_mode == "full":
        response = artifacts.reranked_response
        preferred_score_attr = "rerank_score"
        failure = artifacts.dense_error or artifacts.sparse_error or artifacts.fusion_error or artifacts.rerank_error
    else:
        raise ValueError(f"Unsupported mode: {current_mode}")

    if failure is None:
        ranked_items = _extract_result_payload(response, preferred_score_attr=preferred_score_attr)
        metrics = _compute_metrics(expected, [row["identifiers"] for row in ranked_items])
        hit_at_30 = 1 if metrics.get("recall_30", 0.0) > 0 else 0
        ranked_items = _boost_ranked_items(ranked_items, artifacts.retrieval_query, config)
        diagnostics["result_count"] = len(ranked_items)
        result = QueryResult(
            experiment_mode=current_mode,
            query=query_text,
            category=category,
            normalized_category=normalized_category,
            expected=expected,
            predicted=[identifier for row in ranked_items for identifier in row["identifiers"]],
            per_stage_latency_ms=stage_latency,
            metrics=metrics,
            hit_at_30=hit_at_30,
            retrieval_diagnostics={
                **diagnostics,
                "ranked_items": [
                    {
                        "rank": row["rank"],
                        "score": row["score"],
                        "document": row["document"],
                        "metadata": row["metadata"],
                        "chunk_id": row["chunk_id"],
                        "identifiers": row["identifiers"],
                    }
                    for row in ranked_items[: config.reranker_top_k if current_mode == "full" else config.fusion_top_k if current_mode == "hybrid" else config.sparse_top_k if current_mode == "sparse" else config.dense_top_k]
                ],
            },
        )
        return result, diagnostics, bool(hit_at_30 == 0)

    metrics = _empty_metrics()
    result = QueryResult(
        experiment_mode=current_mode,
        query=query_text,
        category=category,
        normalized_category=normalized_category,
        expected=expected,
        predicted=[],
        per_stage_latency_ms=stage_latency,
        metrics=metrics,
        hit_at_30=0,
        failure_reason=str(failure),
        retrieval_diagnostics={"error": str(failure), **diagnostics},
    )
    return result, diagnostics, False


def _run_single_mode(query: str, mode: str, config: EvaluationConfig) -> Tuple[List[Dict[str, Any]], StageLatency, Dict[str, Any]]:
    artifacts = _execute_query_pipeline(query, config)
    diagnostics: Dict[str, Any] = {
        "retrieval_query": artifacts.retrieval_query,
        "expanded_queries": artifacts.expanded_queries,
        "retrieval_wall_ms": artifacts.retrieval_wall_ms,
    }
    stage_latency = StageLatency(
        dense_ms=artifacts.dense_ms,
        sparse_ms=artifacts.sparse_ms,
        fusion_ms=artifacts.fusion_ms,
        reranker_ms=artifacts.reranker_ms,
    )

    if mode == "dense":
        items = _extract_result_payload(artifacts.dense_response, preferred_score_attr="similarity_score")
    elif mode == "sparse":
        items = _extract_result_payload(artifacts.sparse_response, preferred_score_attr="score")
    elif mode == "hybrid":
        items = _extract_result_payload(artifacts.fused_response, preferred_score_attr="fusion_score")
    elif mode == "full":
        items = _extract_result_payload(artifacts.reranked_response, preferred_score_attr="rerank_score")
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    items = _boost_ranked_items(items, artifacts.retrieval_query, config)
    diagnostics["result_count"] = len(items)
    return items, stage_latency, diagnostics


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _build_mode_summary(rows: List[QueryResult], mode: str) -> Dict[str, Any]:
    if not rows:
        return {
            "mode": mode,
            "query_count": 0,
            "metrics": {metric: 0.0 for metric in [
                *(f"recall_{k}" for k in RECALL_KS),
                *(f"precision_{k}" for k in PRECISION_KS),
                *(f"hit_{k}" for k in METRIC_KS),
                "mrr",
                *(f"ndcg_{k}" for k in NDCG_KS),
            ]},
            "avg_latency_ms": 0.0,
            "per_stage_latency_ms": {"dense_ms": 0.0, "sparse_ms": 0.0, "fusion_ms": 0.0, "reranker_ms": 0.0, "total_ms": 0.0},
        }

    metric_keys = rows[0].metrics.keys()
    metrics = {key: sum(row.metrics.get(key, 0.0) for row in rows) / len(rows) for key in metric_keys}
    stage_latency = {
        "dense_ms": sum(row.per_stage_latency_ms.dense_ms for row in rows) / len(rows),
        "sparse_ms": sum(row.per_stage_latency_ms.sparse_ms for row in rows) / len(rows),
        "fusion_ms": sum(row.per_stage_latency_ms.fusion_ms for row in rows) / len(rows),
        "reranker_ms": sum(row.per_stage_latency_ms.reranker_ms for row in rows) / len(rows),
        "total_ms": sum(row.per_stage_latency_ms.total_ms for row in rows) / len(rows),
    }
    return {
        "mode": mode,
        "query_count": len(rows),
        "metrics": metrics,
        "avg_latency_ms": stage_latency["total_ms"],
        "per_stage_latency_ms": stage_latency,
    }


def _build_category_summary(rows: List[QueryResult], mode: str, all_groups: Sequence[str]) -> Dict[str, Any]:
    grouped: Dict[str, List[QueryResult]] = {group: [] for group in all_groups}
    for row in rows:
        grouped.setdefault(row.normalized_category, []).append(row)

    summary: Dict[str, Any] = {}
    for group in all_groups:
        group_rows = grouped.get(group, [])
        summary[group] = _build_mode_summary(group_rows, mode) if group_rows else {
            "mode": mode,
            "query_count": 0,
            "metrics": {metric: 0.0 for metric in [
                *(f"recall_{k}" for k in RECALL_KS),
                *(f"precision_{k}" for k in PRECISION_KS),
                *(f"hit_{k}" for k in METRIC_KS),
                "mrr",
                *(f"ndcg_{k}" for k in NDCG_KS),
            ]},
            "avg_latency_ms": 0.0,
            "per_stage_latency_ms": {"dense_ms": 0.0, "sparse_ms": 0.0, "fusion_ms": 0.0, "reranker_ms": 0.0, "total_ms": 0.0},
        }
    return summary


def run_evaluation_suite(
    *,
    queries: Sequence[Mapping[str, Any]],
    config: EvaluationConfig,
    mode: str = "all",
    experiment_name: Optional[str] = None,
    experiment_dir: Optional[Path] = None,
) -> ExperimentSummary:
    _configure_logging()

    if mode not in SUPPORTED_MODES:
        raise ValueError(f"Unsupported mode '{mode}'. Expected one of: {', '.join(SUPPORTED_MODES)}")

    modes = _mode_order(mode)
    timestamp_utc = datetime.now(timezone.utc).isoformat()
    experiment_dir = experiment_dir or _ensure_experiment_dir(experiment_name=experiment_name)
    experiment_name = experiment_name or experiment_dir.name

    query_rows: List[QueryResult] = []
    failed_queries: List[Dict[str, Any]] = []
    mode_summaries: Dict[str, Dict[str, Any]] = {}
    mode_rows_map: Dict[str, List[QueryResult]] = {mode_name: [] for mode_name in modes}

    for item in queries:
        query_text = str(item.get("query", "")).strip()
        if not query_text:
            continue

        category = str(item.get("category", "Uncategorized")).strip() or "Uncategorized"
        expected = [str(value).upper() for value in item.get("expected", []) if str(value).strip()]
        normalized_category = _primary_category(category, query_text, expected)

        LOGGER.info("Running evaluation query='%s'", query_text)
        start = time.perf_counter()
        artifacts = _execute_query_pipeline(query_text, config)
        total_ms = (time.perf_counter() - start) * 1000.0

        for current_mode in modes:
            result, diagnostics, is_failure_hit = _materialize_query_result(
                current_mode=current_mode,
                query_text=query_text,
                category=category,
                expected=expected,
                normalized_category=normalized_category,
                config=config,
                artifacts=artifacts,
                total_ms=total_ms,
            )
            mode_rows_map[current_mode].append(result)
            query_rows.append(result)

            if result.failure_reason is not None:
                failed_queries.append(
                    {
                        "mode": current_mode,
                        "query": query_text,
                        "category": category,
                        "normalized_category": normalized_category,
                        "expected": expected,
                        "failure_reason": result.failure_reason,
                        "per_stage_latency_ms": asdict(result.per_stage_latency_ms),
                        "retrieval_diagnostics": result.retrieval_diagnostics,
                    }
                )
            elif is_failure_hit:
                failed_queries.append(
                    {
                        "mode": current_mode,
                        "query": query_text,
                        "category": category,
                        "normalized_category": normalized_category,
                        "expected": expected,
                        "metrics": result.metrics,
                        "per_stage_latency_ms": asdict(result.per_stage_latency_ms),
                        "retrieval_diagnostics": diagnostics,
                    }
                )

    for current_mode, rows in mode_rows_map.items():
        mode_summaries[current_mode] = _build_mode_summary(rows, current_mode)

    all_groups = ["CVE", "MITRE ATT&CK", "Malware", "Threat Actor", "Vendor", "Patch", "IOC", "Ransomware", "SOC Workflow", "Natural Language"]
    category_summaries = {
        current_mode: _build_category_summary(rows, current_mode, all_groups)
        for current_mode, rows in mode_rows_map.items()
    }

    comparison_table: List[Dict[str, Any]] = []
    for current_mode, summary in mode_summaries.items():
        metrics = summary["metrics"]
        comparison_table.append(
            {
                "mode": current_mode,
                "queries": summary["query_count"],
                **{key: metrics.get(key, 0.0) for key in [
                    "recall_5",
                    "recall_10",
                    "recall_20",
                    "recall_30",
                    "precision_5",
                    "precision_10",
                    "hit_1",
                    "hit_3",
                    "hit_5",
                    "hit_10",
                    "mrr",
                    "ndcg_5",
                    "ndcg_10",
                ]},
                "avg_latency_ms": summary["avg_latency_ms"],
                "dense_ms": summary["per_stage_latency_ms"]["dense_ms"],
                "sparse_ms": summary["per_stage_latency_ms"]["sparse_ms"],
                "fusion_ms": summary["per_stage_latency_ms"]["fusion_ms"],
                "reranker_ms": summary["per_stage_latency_ms"]["reranker_ms"],
            }
        )

    artifacts = {
        "per_query_results": str(experiment_dir / "per_query_results.json"),
        "failed_queries": str(experiment_dir / "failed_queries.json"),
        "category_results": str(experiment_dir / "category_results.json"),
        "evaluation_summary": str(experiment_dir / "evaluation_summary.json"),
        "evaluation_csv": str(experiment_dir / "evaluation.csv"),
        "best_config": str(EXPERIMENTS_ROOT / "best_config.json"),
    }

    _write_json(Path(artifacts["per_query_results"]), [asdict(row) for row in query_rows])
    _write_json(Path(artifacts["failed_queries"]), failed_queries)
    _write_json(
        Path(artifacts["category_results"]),
        {
            "categories": category_summaries,
            "groups": all_groups,
        },
    )

    evaluation_summary = {
        "experiment_name": experiment_name,
        "experiment_dir": str(experiment_dir),
        "timestamp_utc": timestamp_utc,
        "config": config.to_dict(),
        "mode_summaries": mode_summaries,
        "comparison_table": comparison_table,
        "category_summaries": category_summaries,
        "failed_query_count": len(failed_queries),
        "query_count": len(query_rows),
    }
    _write_json(Path(artifacts["evaluation_summary"]), evaluation_summary)

    frame = pd.DataFrame(comparison_table)
    frame.to_csv(artifacts["evaluation_csv"], index=False)

    return ExperimentSummary(
        experiment_name=experiment_name,
        experiment_dir=experiment_dir,
        timestamp_utc=timestamp_utc,
        config=config,
        mode_summaries=mode_summaries,
        category_summaries=category_summaries,
        comparison_table=comparison_table,
        per_query_results=[asdict(row) for row in query_rows],
        failed_queries=failed_queries,
        artifacts=artifacts,
    )


def build_experiment_report(
    *,
    queries_file: Path = DEFAULT_QUERIES_FILE,
    config_file: Path = DEFAULT_BASELINE_CONFIG,
    mode: str = "all",
    experiment_name: Optional[str] = None,
    experiment_dir: Optional[Path] = None,
) -> ExperimentSummary:
    return run_evaluation_suite(
        queries=load_queries(queries_file),
        config=load_config(config_file),
        mode=mode,
        experiment_name=experiment_name,
        experiment_dir=experiment_dir,
    )


def _print_comparison_table(summary: ExperimentSummary) -> None:
    rows = summary.comparison_table
    if not rows:
        print("No evaluation results available.")
        return

    headers = ["mode", "queries", "recall_5", "recall_10", "recall_20", "recall_30", "precision_5", "precision_10", "hit_1", "hit_3", "hit_5", "hit_10", "mrr", "ndcg_5", "ndcg_10", "avg_latency_ms", "dense_ms", "sparse_ms", "fusion_ms", "reranker_ms"]
    print("\nEVALUATION COMPARISON TABLE")
    print("=" * 120)
    print(" | ".join(headers))
    print("-" * 120)
    for row in rows:
        print(" | ".join(
            str(row.get(column, "")) if column not in {"avg_latency_ms", "dense_ms", "sparse_ms", "fusion_ms", "reranker_ms", "mrr", "ndcg_5", "ndcg_10", "precision_5", "precision_10", "recall_5", "recall_10", "recall_20", "recall_30", "hit_1", "hit_3", "hit_5", "hit_10"}
            else f"{float(row.get(column, 0.0)):.4f}"
            for column in headers
        ))


def _write_best_config(summary: ExperimentSummary) -> None:
    best_row = max(summary.comparison_table, key=lambda row: (row.get("recall_10", 0.0), row.get("mrr", 0.0), row.get("ndcg_10", 0.0), -row.get("avg_latency_ms", 0.0)), default=None)
    if not best_row:
        return

    best_config = {
        **summary.config.to_dict(),
        "best_mode": best_row.get("mode"),
        "selection_metrics": {
            "recall_10": best_row.get("recall_10", 0.0),
            "mrr": best_row.get("mrr", 0.0),
            "ndcg_10": best_row.get("ndcg_10", 0.0),
        },
    }
    _write_json(EXPERIMENTS_ROOT / "best_config.json", best_config)


def main() -> int:
    parser = argparse.ArgumentParser(description="SecureRAG retrieval evaluation engine")
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES_FILE)
    parser.add_argument("--config", type=Path, default=DEFAULT_BASELINE_CONFIG)
    parser.add_argument("--mode", choices=SUPPORTED_MODES, default="all")
    parser.add_argument("--experiment-name", type=str, default="secure_rag_evaluation")
    parser.add_argument("--experiment-dir", type=Path, default=None)
    parser.add_argument("--print-table", action="store_true")
    args = parser.parse_args()

    summary = run_evaluation_suite(
        queries=load_queries(args.queries),
        config=load_config(args.config),
        mode=args.mode,
        experiment_name=args.experiment_name,
        experiment_dir=args.experiment_dir,
    )
    _write_best_config(summary)
    if args.print_table:
        _print_comparison_table(summary)
    print(json.dumps({"experiment_dir": str(summary.experiment_dir), "artifacts": summary.artifacts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())