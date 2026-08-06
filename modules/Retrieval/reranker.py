"""SecureRAG Module 3.4 - Cross-encoder reranking.

This module reranks hybrid-fused retrieval candidates using
cross-encoder/ms-marco-MiniLM-L-6-v2 to improve relevance precision.

Public API:
    run(
        query: str,
        fused_response: Any,
        config: RerankerConfig | None = None,
    ) -> RerankerResponse

Sample usage:
    from modules.Retrieval import dense_retriever, sparse_retriever, hybrid_fusion, reranker

    q = "How severe is CVE-2021-44228 and what should be patched first?"
    dense = dense_retriever.run(q)
    sparse = sparse_retriever.run(q)
    fused = hybrid_fusion.run(q, dense, sparse)
    reranked = reranker.run(q, fused)

Expected output shape:
    RerankerResponse(
        query="...",
        total_results=<int>,
        results=[
            RerankItem(
                rank=1,
                rerank_score=<float>,
                retrieval_score=<float>,
                text="...",
                metadata={...},
            )
        ],
    )
"""

from __future__ import annotations

import argparse
import logging
import math
import time
import re
from functools import lru_cache
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_CVE_PATTERN = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
_TECHNIQUE_PATTERN = re.compile(r"\bT\d{4}(?:\.\d{3})?\b", re.IGNORECASE)


@dataclass(slots=True)
class RerankerConfig:
    """Runtime configuration for cross-encoder reranking.

    Attributes:
        model_name: Cross-encoder model to use for query-doc scoring.
        top_k: Number of final reranked items to return.
        input_limit: Max number of fused items to score.
        device: Inference device for model loading.
        score_fusion_alpha: Blend factor between rerank and retrieval scores.
    """

    model_name: str = DEFAULT_CROSS_ENCODER_MODEL
    top_k: int = 10
    input_limit: int = 50
    device: str = "cpu"
    score_fusion_alpha: float = 0.85


@dataclass(slots=True)
class RerankItem:
    """Single reranked item with cross-encoder evidence score."""

    rank: int
    rerank_score: float
    retrieval_score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    text: str = ""
    chunk_id: Optional[str] = None
    fused_rank: Optional[int] = None


@dataclass(slots=True)
class RerankerResponse:
    """Structured output of the reranking stage."""

    query: str
    model_name: str
    top_k_requested: int
    total_results: int
    latency_ms: float
    generated_at_utc: str
    results: List[RerankItem] = field(default_factory=list)


@dataclass(slots=True)
class _FusedInputItem:
    rank: int
    retrieval_score: float
    text: str
    metadata: Dict[str, Any]
    chunk_id: Optional[str]


def _configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


def _validate_config(config: RerankerConfig) -> None:
    if config.top_k <= 0:
        raise ValueError("top_k must be greater than 0")
    if config.input_limit <= 0:
        raise ValueError("input_limit must be greater than 0")
    if not config.model_name.strip():
        raise ValueError("model_name cannot be empty")
    if not (0.0 <= config.score_fusion_alpha <= 1.0):
        raise ValueError("score_fusion_alpha must be within [0.0, 1.0]")


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


def _extract_fused_items(fused_response: Any, input_limit: int) -> List[_FusedInputItem]:
    results = getattr(fused_response, "results", None)
    if not isinstance(results, list):
        return []

    extracted: List[_FusedInputItem] = []
    for item in results:
        text = str(getattr(item, "document", ""))
        if not text.strip():
            continue

        extracted.append(
            _FusedInputItem(
                rank=int(getattr(item, "rank", 0) or 0),
                retrieval_score=float(getattr(item, "fusion_score", 0.0) or 0.0),
                text=text,
                metadata=_coerce_metadata(getattr(item, "metadata", {})),
                chunk_id=(
                    str(getattr(item, "chunk_id"))
                    if getattr(item, "chunk_id", None) is not None
                    else None
                ),
            )
        )

    extracted.sort(key=lambda x: x.rank if x.rank > 0 else 10**9)
    return extracted[:input_limit]


def _load_model(model_name: str, device: str) -> Any:
    try:
        from sentence_transformers import CrossEncoder  # type: ignore
    except ImportError as exc:
        raise ImportError("sentence-transformers is required for reranking") from exc

    try:
        return CrossEncoder(model_name, device=device)
    except Exception as exc:
        raise RuntimeError(f"Failed to load cross-encoder model '{model_name}'") from exc


@lru_cache(maxsize=8)
def _get_cross_encoder(model_name: str, device: str) -> Any:
    """Cache the cross-encoder so repeated reranking trials reuse one model instance."""
    return _load_model(model_name, device)


def _predict_scores(model: Any, query: str, items: List[_FusedInputItem]) -> np.ndarray:
    pairs = [(query, item.text) for item in items]
    try:
        raw_scores = model.predict(pairs, show_progress_bar=False)
    except Exception as exc:
        raise RuntimeError("Cross-encoder scoring failed") from exc

    scores = np.asarray(raw_scores, dtype=np.float32)
    if scores.ndim != 1 or scores.shape[0] != len(items):
        raise RuntimeError("Unexpected cross-encoder score shape")
    return scores


def _fallback_sort(items: List[_FusedInputItem], top_k: int, model_name: str, latency_ms: float, query: str) -> RerankerResponse:
    ordered = sorted(items, key=lambda item: item.retrieval_score, reverse=True)[:top_k]
    output = [
        RerankItem(
            rank=index,
            rerank_score=float(item.retrieval_score),
            retrieval_score=float(item.retrieval_score),
            metadata=item.metadata,
            text=item.text,
            chunk_id=item.chunk_id,
            fused_rank=item.rank,
        )
        for index, item in enumerate(ordered, start=1)
    ]

    return RerankerResponse(
        query=query,
        model_name=model_name,
        top_k_requested=top_k,
        total_results=len(output),
        latency_ms=latency_ms,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        results=output,
    )


def _validate_response(response: RerankerResponse) -> None:
    if response.total_results != len(response.results):
        raise RuntimeError("Reranker validation failed: total_results mismatch")

    expected_rank = 1
    for item in response.results:
        if item.rank != expected_rank:
            raise RuntimeError("Reranker validation failed: rank ordering mismatch")
        if not isinstance(item.metadata, dict):
            raise RuntimeError("Reranker validation failed: metadata must be dict")
        if not isinstance(item.text, str):
            raise RuntimeError("Reranker validation failed: text must be string")
        if math.isnan(item.rerank_score) or math.isinf(item.rerank_score):
            raise RuntimeError("Reranker validation failed: invalid rerank score")
        expected_rank += 1


def run(
    query: str,
    fused_response: Any,
    config: RerankerConfig | None = None,
) -> RerankerResponse:
    """Run cross-encoder reranking on fused retrieval candidates.

    Args:
        query: Analyst query.
        fused_response: Output from hybrid fusion module.
        config: Optional reranker settings.

    Returns:
        Top reranked evidence items.

    Raises:
        ValueError: If query/config is invalid.
        RuntimeError: If response validation fails.
    """
    _configure_logging()
    runtime_config = config or RerankerConfig()
    _validate_config(runtime_config)
    normalized_query = _normalize_query(query)

    candidates = _extract_fused_items(fused_response, runtime_config.input_limit)
    if not candidates:
        empty = RerankerResponse(
            query=normalized_query,
            model_name=runtime_config.model_name,
            top_k_requested=runtime_config.top_k,
            total_results=0,
            latency_ms=0.0,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            results=[],
        )
        _validate_response(empty)
        return empty

    start = time.perf_counter()
    try:
        # SentenceTransformers already batches query-document pairs; keep the full batch on one model call.
        model = _get_cross_encoder(runtime_config.model_name, runtime_config.device)
        rerank_scores = _predict_scores(model=model, query=normalized_query, items=candidates)
        latency_ms = (time.perf_counter() - start) * 1000.0

        query_cves = set(m.upper() for m in _CVE_PATTERN.findall(normalized_query))
        query_techs = set(m.upper() for m in _TECHNIQUE_PATTERN.findall(normalized_query))

        merged: List[tuple[float, _FusedInputItem, float]] = []
        alpha = runtime_config.score_fusion_alpha
        for idx, item in enumerate(candidates):
            rerank_score = float(rerank_scores[idx])
            blended = alpha * rerank_score + (1.0 - alpha) * float(item.retrieval_score)

            # Step 9 — Metadata-aware Reranking Boost
            meta_cve = str(item.metadata.get("cve_id", "")).upper()
            meta_tech = str(item.metadata.get("technique_id", "")).upper()

            if (query_cves and meta_cve in query_cves) or (query_techs and meta_tech in query_techs):
                blended += 100.0

            merged.append((blended, item, rerank_score))

        merged.sort(key=lambda row: row[0], reverse=True)
        trimmed = merged[: runtime_config.top_k]

        results = [
            RerankItem(
                rank=rank,
                rerank_score=float(raw_rerank_score),
                retrieval_score=float(item.retrieval_score),
                metadata=item.metadata,
                text=item.text,
                chunk_id=item.chunk_id,
                fused_rank=item.rank,
            )
            for rank, (_, item, raw_rerank_score) in enumerate(trimmed, start=1)
        ]

        response = RerankerResponse(
            query=normalized_query,
            model_name=runtime_config.model_name,
            top_k_requested=runtime_config.top_k,
            total_results=len(results),
            latency_ms=latency_ms,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            results=results,
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000.0
        LOGGER.exception("Cross-encoder reranking failed; applying retrieval-score fallback")
        response = _fallback_sort(
            items=candidates,
            top_k=runtime_config.top_k,
            model_name=runtime_config.model_name,
            latency_ms=latency_ms,
            query=normalized_query,
        )
        response.results = [
            RerankItem(
                rank=item.rank,
                rerank_score=item.rerank_score,
                retrieval_score=item.retrieval_score,
                metadata={**item.metadata, "reranker_fallback": str(exc)},
                text=item.text,
                chunk_id=item.chunk_id,
                fused_rank=item.fused_rank,
            )
            for item in response.results
        ]

    _validate_response(response)

    LOGGER.info(
        "Reranking completed | inputs=%d outputs=%d latency_ms=%.2f",
        len(candidates),
        response.total_results,
        response.latency_ms,
    )
    return response


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cross-encoder reranking runtime validation")
    parser.add_argument("query", type=str, help="Analyst query")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--input-limit", type=int, default=25)
    parser.add_argument("--device", type=str, default="cpu")
    return parser


def _main() -> int:
    parser = _build_cli_parser()
    args = parser.parse_args()

    try:
        from modules.Retrieval import dense_retriever, hybrid_fusion, sparse_retriever

        dense = dense_retriever.run(args.query)
        sparse = sparse_retriever.run(args.query)
        fused = hybrid_fusion.run(args.query, dense, sparse)

        response = run(
            query=args.query,
            fused_response=fused,
            config=RerankerConfig(top_k=args.top_k, input_limit=args.input_limit, device=args.device),
        )
    except Exception as exc:  # pragma: no cover - CLI surface
        LOGGER.exception("Reranker failed")
        print(f"ERROR: {exc}")
        return 1

    print("Reranker successful")
    print(f"Query: {response.query}")
    print(f"Total reranked results: {response.total_results}")
    print(f"Latency (ms): {response.latency_ms:.2f}")
    for item in response.results:
        print(
            f"[{item.rank}] rerank={item.rerank_score:.4f} "
            f"retrieval={item.retrieval_score:.4f} cve={item.metadata.get('cve_id')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
