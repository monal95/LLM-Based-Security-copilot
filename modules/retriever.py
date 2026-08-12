"""Convenience retrieval wrapper for Phase 5 consumers.

This module reuses the existing dense, sparse, hybrid-fusion, and reranking
pipeline to expose a simple ``retrieve`` helper that returns ranked chunks
as dictionaries.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Dict, List

from modules.Retrieval import dense_retriever, hybrid_fusion, reranker, sparse_retriever

LOGGER = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Configure default logging when the host application has not set handlers."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


def _to_dict(item: Any, rank: int) -> Dict[str, Any]:
    """Normalize a reranked item into a plain dictionary."""
    metadata = getattr(item, "metadata", {})
    if not isinstance(metadata, dict):
        metadata = {"raw_metadata": str(metadata)}

    return {
        "rank": rank,
        "score": float(getattr(item, "rerank_score", 0.0) or 0.0),
        "retrieval_score": float(getattr(item, "retrieval_score", 0.0) or 0.0),
        "text": str(getattr(item, "text", "")),
        "metadata": metadata,
        "chunk_id": getattr(item, "chunk_id", None),
        "fused_rank": getattr(item, "fused_rank", None),
    }


def retrieve(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Run the existing retrieval pipeline and return the top chunks.

    Args:
        query: Analyst query used to retrieve relevant incident-response evidence.
        top_k: Number of top chunks to return.

    Returns:
        A list of dictionaries containing text, metadata, and ranking scores.
    """
    _configure_logging()
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query cannot be empty")
    if top_k <= 0:
        raise ValueError("top_k must be greater than 0")

    LOGGER.info("Running retrieval wrapper | top_k=%d", top_k)
    dense = dense_retriever.run(normalized_query, dense_retriever.DenseRetrieverConfig(top_k=max(10, top_k * 5)))
    sparse = sparse_retriever.run(normalized_query, sparse_retriever.SparseRetrieverConfig(top_k=max(10, top_k * 5)))
    fused = hybrid_fusion.run(
        normalized_query,
        dense,
        sparse,
        hybrid_fusion.HybridFusionConfig(top_k=max(10, top_k * 5)),
    )
    reranked = reranker.run(
        normalized_query,
        fused,
        reranker.RerankerConfig(top_k=top_k, input_limit=max(10, top_k * 5)),
    )

    results: List[Dict[str, Any]] = []
    for index, item in enumerate(reranked.results[:top_k], start=1):
        results.append(_to_dict(item, index))
    return results


def main() -> int:
    """Manual smoke-test entrypoint."""
    for item in retrieve("ransomware containment and recovery", top_k=5):
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())