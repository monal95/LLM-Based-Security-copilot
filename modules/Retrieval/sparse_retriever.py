"""SecureRAG Module 3.2 - Sparse BM25 retrieval for cybersecurity evidence.

This module performs deterministic keyword retrieval using a persisted BM25 index.
It maps ranked corpus indices back to original chunk text and metadata so downstream
hybrid fusion can merge sparse and dense evidence consistently.

Public API:
    run(query: str, config: SparseRetrieverConfig | None = None) -> SparseRetrievalResponse

Sample usage:
    from modules.Retrieval.sparse_retriever import run

    response = run("CVE-2021-44228 remote code execution")
    for item in response.results[:3]:
        print(item.rank, item.score, item.metadata.get("cve_id"))

Expected output shape:
    SparseRetrievalResponse(
        query="...",
        total_results=<int>,
        results=[
            SparseRetrievalItem(
                rank=1,
                score=<float>,
                document="...",
                metadata={...},
                corpus_index=<int>,
                chunk_id="...",
            ),
            ...
        ],
    )
"""

from __future__ import annotations

import argparse
import json
import logging
import pickle
import re
import time
from functools import lru_cache
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BM25_FILE = PROJECT_ROOT / "data" / "embeddings" / "bm25.pkl"
DEFAULT_CORPUS_FILE = PROJECT_ROOT / "data" / "embeddings" / "corpus.pkl"
DEFAULT_CHUNKS_FILE = PROJECT_ROOT / "data" / "chunks" / "chunks.json"


@dataclass(slots=True)
class SparseRetrieverConfig:
    """Runtime configuration for sparse BM25 retrieval.

    Attributes:
        bm25_file: Path to persisted BM25Okapi object.
        corpus_file: Path to tokenized corpus aligned to chunks.json by index.
        chunks_file: Path to chunk payload that contains text and metadata.
        top_k: Number of ranked sparse matches to return.
        min_score: Minimum score threshold to include a result.
        deduplicate_documents: If true, deduplicate by normalized document text.
    """

    bm25_file: Path = DEFAULT_BM25_FILE
    corpus_file: Path = DEFAULT_CORPUS_FILE
    chunks_file: Path = DEFAULT_CHUNKS_FILE
    top_k: int = 30
    min_score: float = 0.0
    deduplicate_documents: bool = True


@dataclass(slots=True)
class SparseRetrievalItem:
    """Single sparse retrieval match from BM25 ranking."""

    rank: int
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    document: str = ""
    corpus_index: int = -1
    chunk_id: Optional[str] = None


@dataclass(slots=True)
class SparseRetrievalResponse:
    """Structured sparse retrieval output."""

    query: str
    top_k_requested: int
    total_results: int
    latency_ms: float
    generated_at_utc: str
    results: List[SparseRetrievalItem] = field(default_factory=list)


def _configure_logging() -> None:
    """Configure default logger if parent application did not configure one."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


def _validate_config(config: SparseRetrieverConfig) -> None:
    """Validate runtime configuration."""
    if config.top_k <= 0:
        raise ValueError("top_k must be greater than 0")
    if config.min_score < 0:
        raise ValueError("min_score must be >= 0")


def _normalize_query(query: str) -> str:
    """Normalize query and guard against empty inputs."""
    normalized = query.strip()
    if not normalized:
        raise ValueError("Query cannot be empty")
    return normalized


def _tokenize(text: str) -> List[str]:
    """Deterministic cybersecurity-aware tokenizer."""
    raw_tokens = re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", text.lower())
    expanded_tokens: List[str] = []
    for tok in raw_tokens:
        expanded_tokens.append(tok)
        if "-" in tok or "_" in tok:
            sub_parts = re.split(r"[-_]", tok)
            for part in sub_parts:
                if part and part not in expanded_tokens:
                    expanded_tokens.append(part)
    return expanded_tokens


def _load_pickle(path: Path, expected_description: str) -> Any:
    """Load pickle payload with explicit diagnostics."""
    if not path.exists():
        raise FileNotFoundError(f"{expected_description} not found: {path}")

    try:
        with path.open("rb") as handle:
            payload = pickle.load(handle)
    except Exception as exc:
        raise RuntimeError(f"Failed to load {expected_description} from {path}") from exc

    return payload


@lru_cache(maxsize=8)
def _get_bm25_index(bm25_file: str) -> Any:
    """Cache the BM25 index so repeated evaluations avoid re-unpickling it."""
    return _load_pickle(Path(bm25_file), "BM25 index")


@lru_cache(maxsize=8)
def _get_tokenized_corpus(corpus_file: str) -> Any:
    """Cache the tokenized corpus because it is read-only during evaluation."""
    return _load_pickle(Path(corpus_file), "tokenized corpus")


@lru_cache(maxsize=8)
def _get_chunks(chunks_file: str) -> List[Dict[str, Any]]:
    """Cache the chunk payload so sparse evaluation can reuse the evidence text."""
    return _load_chunks(Path(chunks_file))


def _load_chunks(chunks_file: Path) -> List[Dict[str, Any]]:
    """Load chunk records that hold evidence text and metadata."""
    if not chunks_file.exists():
        raise FileNotFoundError(f"chunks.json not found: {chunks_file}")

    try:
        with chunks_file.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        raise RuntimeError(f"Failed to parse chunks file: {chunks_file}") from exc

    if not isinstance(payload, list):
        raise ValueError(
            f"Expected list in {chunks_file}, got {type(payload).__name__}"
        )

    normalized: List[Dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            normalized.append(item)
        else:
            normalized.append({"text": str(item), "metadata": {}, "id": None})
    return normalized


def _coerce_metadata(metadata: Any) -> Dict[str, Any]:
    """Normalize potentially corrupted metadata into dictionary form."""
    if isinstance(metadata, dict):
        return metadata
    if metadata is None:
        return {}
    return {"raw_metadata": str(metadata)}


def _safe_chunk(chunks: Sequence[Dict[str, Any]], index: int) -> Dict[str, Any]:
    """Return chunk object for index or synthetic placeholder if out of bounds."""
    if 0 <= index < len(chunks):
        value = chunks[index]
        if isinstance(value, dict):
            return value
    return {
        "id": None,
        "text": "",
        "metadata": {"retrieval_warning": "corpus index has no matching chunk"},
    }


def _dedup_key(text: str) -> str:
    """Create deterministic key for duplicate elimination."""
    return " ".join(text.split()).lower()


def _validate_alignment(corpus: Any, chunks: Sequence[Dict[str, Any]]) -> None:
    """Validate that corpus and chunk arrays are index-aligned."""
    if not isinstance(corpus, list):
        raise ValueError(f"Expected tokenized corpus as list, got {type(corpus).__name__}")
    if len(corpus) == 0:
        raise ValueError("Tokenized corpus is empty")
    if len(chunks) == 0:
        raise ValueError("chunks.json is empty")

    if len(corpus) != len(chunks):
        LOGGER.warning(
            "Corpus and chunk counts differ (corpus=%d, chunks=%d); retrieval will continue with min length mapping",
            len(corpus),
            len(chunks),
        )


def _rank_indices(scores: np.ndarray, top_k: int) -> List[int]:
    """Return top-k indices sorted by descending BM25 score."""
    if scores.size == 0:
        return []
    descending_indices = np.argsort(-scores)
    return [int(idx) for idx in descending_indices[:top_k]]


def _validate_response(response: SparseRetrievalResponse) -> None:
    """Runtime schema and ordering checks for sparse retrieval output."""
    if response.total_results != len(response.results):
        raise RuntimeError("Sparse retrieval validation failed: total_results mismatch")

    expected_rank = 1
    for item in response.results:
        if item.rank != expected_rank:
            raise RuntimeError("Sparse retrieval validation failed: rank ordering mismatch")
        if not isinstance(item.metadata, dict):
            raise RuntimeError("Sparse retrieval validation failed: metadata must be dict")
        if not isinstance(item.document, str):
            raise RuntimeError("Sparse retrieval validation failed: document must be string")
        expected_rank += 1


def run(query: str, config: SparseRetrieverConfig | None = None) -> SparseRetrievalResponse:
    """Run sparse BM25 retrieval for analyst query.

    Args:
        query: Analyst input query text.
        config: Optional runtime configuration.

    Returns:
        Structured sparse retrieval results.

    Raises:
        ValueError: For invalid inputs.
        FileNotFoundError: If required artifacts are missing.
        RuntimeError: If loading or scoring fails.
    """
    _configure_logging()
    runtime_config = config or SparseRetrieverConfig()
    _validate_config(runtime_config)
    normalized_query = _normalize_query(query)

    LOGGER.info(
        "Sparse retrieval started | top_k=%d | bm25_file=%s",
        runtime_config.top_k,
        runtime_config.bm25_file,
    )

    # Cache the heavy sparse artifacts so the hot path only performs scoring and ranking.
    bm25 = _get_bm25_index(str(runtime_config.bm25_file))
    corpus = _get_tokenized_corpus(str(runtime_config.corpus_file))
    chunks = _get_chunks(str(runtime_config.chunks_file))

    _validate_alignment(corpus=corpus, chunks=chunks)

    query_tokens = _tokenize(normalized_query)
    if not query_tokens:
        LOGGER.warning("Sparse retrieval query produced no tokens after normalization")
        response = SparseRetrievalResponse(
            query=normalized_query,
            top_k_requested=runtime_config.top_k,
            total_results=0,
            latency_ms=0.0,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            results=[],
        )
        _validate_response(response)
        return response

    started = time.perf_counter()
    try:
        score_vector = bm25.get_scores(query_tokens)
    except Exception as exc:
        raise RuntimeError("BM25 scoring failed") from exc
    latency_ms = (time.perf_counter() - started) * 1000.0

    scores = np.asarray(score_vector, dtype=np.float32)
    ranked_indices = _rank_indices(scores=scores, top_k=max(runtime_config.top_k * 3, runtime_config.top_k))

    seen_documents: set[str] = set()
    items: List[SparseRetrievalItem] = []

    for corpus_index in ranked_indices:
        if corpus_index < 0 or corpus_index >= scores.size:
            continue

        score = float(scores[corpus_index])
        if score < runtime_config.min_score:
            continue

        chunk = _safe_chunk(chunks, corpus_index)
        document = str(chunk.get("text", ""))

        if runtime_config.deduplicate_documents:
            key = _dedup_key(document)
            if key in seen_documents:
                continue
            seen_documents.add(key)

        metadata = _coerce_metadata(chunk.get("metadata", {}))
        chunk_id = chunk.get("id")

        items.append(
            SparseRetrievalItem(
                rank=len(items) + 1,
                score=score,
                metadata=metadata,
                document=document,
                corpus_index=corpus_index,
                chunk_id=str(chunk_id) if chunk_id is not None else None,
            )
        )

        if len(items) >= runtime_config.top_k:
            break

    response = SparseRetrievalResponse(
        query=normalized_query,
        top_k_requested=runtime_config.top_k,
        total_results=len(items),
        latency_ms=latency_ms,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        results=items,
    )

    _validate_response(response)

    LOGGER.info(
        "Sparse retrieval completed | results=%d | latency_ms=%.2f",
        response.total_results,
        response.latency_ms,
    )
    return response


def _build_cli_parser() -> argparse.ArgumentParser:
    """Build CLI parser for local runtime validation."""
    parser = argparse.ArgumentParser(description="Run SecureRAG sparse retriever")
    parser.add_argument("query", type=str, help="Analyst query text")
    parser.add_argument("--top-k", type=int, default=10, help="Number of sparse results")
    parser.add_argument(
        "--bm25-file",
        type=Path,
        default=DEFAULT_BM25_FILE,
        help="Path to BM25 pickle artifact",
    )
    parser.add_argument(
        "--corpus-file",
        type=Path,
        default=DEFAULT_CORPUS_FILE,
        help="Path to tokenized corpus pickle artifact",
    )
    parser.add_argument(
        "--chunks-file",
        type=Path,
        default=DEFAULT_CHUNKS_FILE,
        help="Path to chunks.json",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Minimum BM25 score required to include a result",
    )
    return parser


def _main() -> int:
    """CLI entrypoint for sparse retriever validation."""
    parser = _build_cli_parser()
    args = parser.parse_args()

    config = SparseRetrieverConfig(
        bm25_file=args.bm25_file,
        corpus_file=args.corpus_file,
        chunks_file=args.chunks_file,
        top_k=args.top_k,
        min_score=args.min_score,
    )

    try:
        response = run(query=args.query, config=config)
    except Exception as exc:  # pragma: no cover - CLI surface
        LOGGER.exception("Sparse retrieval failed")
        print(f"ERROR: {exc}")
        return 1

    print("Sparse retrieval successful")
    print(f"Query: {response.query}")
    print(f"Total results: {response.total_results}")
    print(f"Latency (ms): {response.latency_ms:.2f}")

    for item in response.results:
        print(
            f"[{item.rank}] score={item.score:.4f} "
            f"index={item.corpus_index} chunk_id={item.chunk_id}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
