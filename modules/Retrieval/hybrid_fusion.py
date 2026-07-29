"""SecureRAG Module 3.3 - Hybrid fusion via Reciprocal Rank Fusion (RRF).

This module merges dense and sparse retrieval outputs into a unified evidence list
using Reciprocal Rank Fusion:
    score = sum(1 / (k + rank))

Public API:
    run(
        query: str,
        dense_response: Any,
        sparse_response: Any,
        config: HybridFusionConfig | None = None,
    ) -> HybridFusionResponse

Sample usage:
    from modules.Retrieval import dense_retriever, sparse_retriever, hybrid_fusion

    dense = dense_retriever.run("Prioritize CVE-2021-44228")
    sparse = sparse_retriever.run("Prioritize CVE-2021-44228")
    fused = hybrid_fusion.run("Prioritize CVE-2021-44228", dense, sparse)

Expected output shape:
    HybridFusionResponse(
        query="...",
        total_results=<int>,
        results=[
            HybridFusionItem(
                rank=1,
                fusion_score=<float>,
                retrieval_score=<float>,
                document="...",
                metadata={...},
            )
        ],
    )
"""

from __future__ import annotations

import argparse
import logging
import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class HybridFusionConfig:
    """Runtime configuration for hybrid reciprocal-rank fusion.

    Attributes:
        rrf_k: Constant in RRF denominator, commonly 60.
        top_k: Number of fused results to return.
        dedup_strategy: Deduplication strategy: "chunk_id" or "document".
        min_fusion_score: Drop fused items below this threshold.
    """

    rrf_k: int = 60
    top_k: int = 15
    dedup_strategy: str = "chunk_id"
    min_fusion_score: float = 0.0


@dataclass(slots=True)
class HybridFusionItem:
    """Unified evidence item after dense+sparse fusion."""

    rank: int
    fusion_score: float
    retrieval_score: float
    document: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    chunk_id: Optional[str] = None
    dense_rank: Optional[int] = None
    sparse_rank: Optional[int] = None
    dense_similarity: Optional[float] = None
    sparse_score: Optional[float] = None


@dataclass(slots=True)
class HybridFusionResponse:
    """Structured output for hybrid fusion stage."""

    query: str
    rrf_k: int
    top_k_requested: int
    total_results: int
    latency_ms: float
    generated_at_utc: str
    results: List[HybridFusionItem] = field(default_factory=list)


@dataclass(slots=True)
class _Candidate:
    """Internal normalized candidate representation."""

    source: str
    rank: int
    score: float
    document: str
    metadata: Dict[str, Any]
    chunk_id: Optional[str]


def _configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


def _validate_config(config: HybridFusionConfig) -> None:
    if config.rrf_k <= 0:
        raise ValueError("rrf_k must be greater than 0")
    if config.top_k <= 0:
        raise ValueError("top_k must be greater than 0")
    if config.dedup_strategy not in {"chunk_id", "document"}:
        raise ValueError("dedup_strategy must be either 'chunk_id' or 'document'")
    if config.min_fusion_score < 0:
        raise ValueError("min_fusion_score must be >= 0")


def _normalize_query(query: str) -> str:
    normalized = query.strip()
    if not normalized:
        raise ValueError("Query cannot be empty")
    return normalized


def _coerce_metadata(metadata: Any) -> Dict[str, Any]:
    if isinstance(metadata, dict):
        return metadata
    if metadata is None:
        return {}
    return {"raw_metadata": str(metadata)}


def _normalize_doc_key(document: str) -> str:
    return re.sub(r"\s+", " ", document).strip().lower()


def _to_candidates_dense(response: Any) -> List[_Candidate]:
    results = getattr(response, "results", None)
    if not isinstance(results, list):
        return []

    candidates: List[_Candidate] = []
    for item in results:
        rank = int(getattr(item, "rank", 0) or 0)
        if rank <= 0:
            continue
        document = str(getattr(item, "document", ""))
        if not document.strip():
            continue

        score = float(getattr(item, "similarity_score", 0.0) or 0.0)
        metadata = _coerce_metadata(getattr(item, "metadata", {}))
        chunk_id_value = getattr(item, "chunk_id", None)

        candidates.append(
            _Candidate(
                source="dense",
                rank=rank,
                score=score,
                document=document,
                metadata=metadata,
                chunk_id=str(chunk_id_value) if chunk_id_value is not None else None,
            )
        )
    return candidates


def _to_candidates_sparse(response: Any) -> List[_Candidate]:
    results = getattr(response, "results", None)
    if not isinstance(results, list):
        return []

    candidates: List[_Candidate] = []
    for item in results:
        rank = int(getattr(item, "rank", 0) or 0)
        if rank <= 0:
            continue
        document = str(getattr(item, "document", ""))
        if not document.strip():
            continue

        score = float(getattr(item, "score", 0.0) or 0.0)
        metadata = _coerce_metadata(getattr(item, "metadata", {}))
        chunk_id_value = getattr(item, "chunk_id", None)

        candidates.append(
            _Candidate(
                source="sparse",
                rank=rank,
                score=score,
                document=document,
                metadata=metadata,
                chunk_id=str(chunk_id_value) if chunk_id_value is not None else None,
            )
        )
    return candidates


def _candidate_key(candidate: _Candidate, strategy: str) -> str:
    if strategy == "chunk_id" and candidate.chunk_id:
        return f"id:{candidate.chunk_id}"
    return f"doc:{_normalize_doc_key(candidate.document)}"


def _rrf(rank: int, k_constant: int) -> float:
    return 1.0 / float(k_constant + rank)


def _merge_candidates(
    dense_candidates: Sequence[_Candidate],
    sparse_candidates: Sequence[_Candidate],
    config: HybridFusionConfig,
) -> List[HybridFusionItem]:
    accumulator: Dict[str, HybridFusionItem] = {}

    for candidate in list(dense_candidates) + list(sparse_candidates):
        key = _candidate_key(candidate, config.dedup_strategy)
        rrf_score = _rrf(candidate.rank, config.rrf_k)

        if key not in accumulator:
            accumulator[key] = HybridFusionItem(
                rank=0,
                fusion_score=0.0,
                retrieval_score=candidate.score,
                document=candidate.document,
                metadata=candidate.metadata,
                chunk_id=candidate.chunk_id,
            )

        target = accumulator[key]
        target.fusion_score += rrf_score

        if candidate.score > target.retrieval_score:
            target.retrieval_score = candidate.score

        if candidate.source == "dense":
            target.dense_rank = candidate.rank
            target.dense_similarity = candidate.score
        elif candidate.source == "sparse":
            target.sparse_rank = candidate.rank
            target.sparse_score = candidate.score

        # Keep richer metadata if one side has additional fields.
        if len(candidate.metadata) > len(target.metadata):
            target.metadata = candidate.metadata

        if not target.chunk_id and candidate.chunk_id:
            target.chunk_id = candidate.chunk_id

    fused = [item for item in accumulator.values() if item.fusion_score >= config.min_fusion_score]
    fused.sort(key=lambda item: (item.fusion_score, item.retrieval_score), reverse=True)

    for index, item in enumerate(fused[: config.top_k], start=1):
        item.rank = index

    return fused[: config.top_k]


def _validate_response(response: HybridFusionResponse) -> None:
    if response.total_results != len(response.results):
        raise RuntimeError("Hybrid fusion validation failed: total_results mismatch")

    expected_rank = 1
    for item in response.results:
        if item.rank != expected_rank:
            raise RuntimeError("Hybrid fusion validation failed: non-contiguous rank sequence")
        if not isinstance(item.metadata, dict):
            raise RuntimeError("Hybrid fusion validation failed: metadata is not a dict")
        if not isinstance(item.document, str):
            raise RuntimeError("Hybrid fusion validation failed: document is not a string")
        if math.isnan(item.fusion_score) or math.isinf(item.fusion_score):
            raise RuntimeError("Hybrid fusion validation failed: invalid fusion score")
        expected_rank += 1


def run(
    query: str,
    dense_response: Any,
    sparse_response: Any,
    config: HybridFusionConfig | None = None,
) -> HybridFusionResponse:
    """Fuse dense and sparse retrieval outputs using reciprocal rank fusion.

    Args:
        query: Analyst query.
        dense_response: Output object from dense retriever.
        sparse_response: Output object from sparse retriever.
        config: Optional fusion settings.

    Returns:
        Fused and deduplicated ranked list of evidence chunks.

    Raises:
        ValueError: If query/config is invalid.
        RuntimeError: If response integrity checks fail.
    """
    _configure_logging()
    runtime_config = config or HybridFusionConfig()
    _validate_config(runtime_config)
    normalized_query = _normalize_query(query)

    started = time.perf_counter()

    dense_candidates = _to_candidates_dense(dense_response)
    sparse_candidates = _to_candidates_sparse(sparse_response)

    merged = _merge_candidates(
        dense_candidates=dense_candidates,
        sparse_candidates=sparse_candidates,
        config=runtime_config,
    )

    latency_ms = (time.perf_counter() - started) * 1000.0

    response = HybridFusionResponse(
        query=normalized_query,
        rrf_k=runtime_config.rrf_k,
        top_k_requested=runtime_config.top_k,
        total_results=len(merged),
        latency_ms=latency_ms,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        results=merged,
    )

    _validate_response(response)

    LOGGER.info(
        "Hybrid fusion completed | dense=%d sparse=%d fused=%d latency_ms=%.2f",
        len(dense_candidates),
        len(sparse_candidates),
        response.total_results,
        response.latency_ms,
    )
    return response


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hybrid fusion runtime validation")
    parser.add_argument("query", type=str, help="Analyst query text")
    parser.add_argument("--dense-top-k", type=int, default=10)
    parser.add_argument("--sparse-top-k", type=int, default=10)
    parser.add_argument("--fused-top-k", type=int, default=15)
    parser.add_argument("--rrf-k", type=int, default=60)
    return parser


def _main() -> int:
    parser = _build_cli_parser()
    args = parser.parse_args()

    try:
        from modules.Retrieval import dense_retriever, sparse_retriever

        dense = dense_retriever.run(
            query=args.query,
            config=dense_retriever.DenseRetrieverConfig(top_k=args.dense_top_k),
        )
        sparse = sparse_retriever.run(
            query=args.query,
            config=sparse_retriever.SparseRetrieverConfig(top_k=args.sparse_top_k),
        )

        fused = run(
            query=args.query,
            dense_response=dense,
            sparse_response=sparse,
            config=HybridFusionConfig(top_k=args.fused_top_k, rrf_k=args.rrf_k),
        )
    except Exception as exc:  # pragma: no cover - CLI surface
        LOGGER.exception("Hybrid fusion failed")
        print(f"ERROR: {exc}")
        return 1

    print("Hybrid fusion successful")
    print(f"Query: {fused.query}")
    print(f"Total fused results: {fused.total_results}")
    print(f"Latency (ms): {fused.latency_ms:.2f}")
    for item in fused.results:
        print(
            f"[{item.rank}] fusion={item.fusion_score:.6f} "
            f"dense_rank={item.dense_rank} sparse_rank={item.sparse_rank}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
