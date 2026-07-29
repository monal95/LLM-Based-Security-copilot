"""SecureRAG Module 3.1 - Dense semantic retrieval over ChromaDB.

This module performs semantic retrieval for SOC analyst queries using:
- sentence-transformers/all-MiniLM-L6-v2 for query embedding
- Persistent ChromaDB collection for nearest-neighbor search

Public API:
    run(query: str, config: DenseRetrieverConfig | None = None) -> DenseRetrievalResponse

Sample usage:
    from modules.Retrieval.dense_retriever import run

    response = run("How should I prioritize CVE-2021-44228?")
    print(response.results[0].document)

Expected output shape:
    DenseRetrievalResponse(
        query="...",
        total_results=<int>,
        results=[
            DenseRetrievalItem(
                rank=1,
                distance=<float | None>,
                similarity_score=<float>,
                document="...",
                metadata={...},
                chunk_id="...",
            ),
            ...
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
from typing import Any, Dict, List, Optional, Sequence, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - imported only for static typing
    from sentence_transformers import SentenceTransformer

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHROMA_DIR = PROJECT_ROOT / "embeddings" / "chroma_db"
DEFAULT_COLLECTION_NAME = "secure_rag_chunks"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

_CVE_PATTERN = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)


@dataclass(slots=True)
class DenseRetrieverConfig:
    """Runtime configuration for dense semantic retrieval.

    Attributes:
        chroma_dir: Path to persistent ChromaDB directory.
        collection_name: Chroma collection containing CTI chunks.
        embedding_model: SentenceTransformer model used for query embeddings.
        top_k: Number of top matches to return.
        device: Inference device for sentence-transformers model.
        include_embeddings: If true, requests embeddings from Chroma for direct
            cosine similarity computation.
        query_timeout_seconds: Soft timeout target (for telemetry/logging).
    """

    chroma_dir: Path = DEFAULT_CHROMA_DIR
    collection_name: str = DEFAULT_COLLECTION_NAME
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    top_k: int = 10
    device: str = "cpu"
    include_embeddings: bool = True
    query_timeout_seconds: float = 20.0


@dataclass(slots=True)
class DenseRetrievalItem:
    """Single dense retrieval match for analyst evidence grounding."""

    rank: int
    distance: Optional[float]
    similarity_score: float
    document: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    chunk_id: Optional[str] = None


@dataclass(slots=True)
class DenseRetrievalResponse:
    """Structured output for dense retrieval module."""

    query: str
    collection_name: str
    embedding_model: str
    top_k_requested: int
    total_results: int
    latency_ms: float
    generated_at_utc: str
    results: List[DenseRetrievalItem] = field(default_factory=list)


def _configure_logging() -> None:
    """Configure default logging when host app has not configured handlers."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


def _validate_config(config: DenseRetrieverConfig) -> None:
    """Validate runtime configuration before retrieval begins."""
    if config.top_k <= 0:
        raise ValueError("top_k must be greater than 0")
    if not config.collection_name.strip():
        raise ValueError("collection_name cannot be empty")
    if not config.embedding_model.strip():
        raise ValueError("embedding_model cannot be empty")


def _normalize_query(query: str) -> str:
    """Normalize and validate analyst query text."""
    normalized = query.strip()
    if not normalized:
        raise ValueError("Query cannot be empty")
    return normalized


def _extract_cve_ids(text: str) -> List[str]:
    """Extract unique, uppercased CVE identifiers from *text*."""
    return list(dict.fromkeys(m.upper() for m in _CVE_PATTERN.findall(text)))


def _build_metadata_items(
    get_payload: Dict[str, Any],
) -> List[DenseRetrievalItem]:
    """Convert a ChromaDB ``get()`` payload into ranked retrieval items.

    Metadata-only lookups have no embedding vectors and no distance values,
    so ``distance`` is ``None`` and ``similarity_score`` is ``1.0`` (exact
    match).
    """
    documents: List[str] = get_payload.get("documents") or []
    metadatas: List[Dict[str, Any]] = get_payload.get("metadatas") or []
    ids: List[str] = get_payload.get("ids") or []

    items: List[DenseRetrievalItem] = []
    for idx in range(len(documents)):
        items.append(
            DenseRetrievalItem(
                rank=idx + 1,
                distance=None,
                similarity_score=1.0,
                document=str(documents[idx]) if idx < len(documents) else "",
                metadata=_coerce_metadata(metadatas[idx] if idx < len(metadatas) else {}),
                chunk_id=str(ids[idx]) if idx < len(ids) else None,
            )
        )
    return items


def _load_sentence_transformer(model_name: str, device: str) -> "SentenceTransformer":
    """Load sentence-transformers model for query embedding."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "sentence-transformers is required for dense retrieval. Install project dependencies."
        ) from exc

    LOGGER.info("Loading embedding model: %s (device=%s)", model_name, device)
    return SentenceTransformer(model_name, device=device)


def _load_chroma_collection(chroma_dir: Path, collection_name: str) -> Any:
    """Load persistent Chroma collection and fail fast if missing."""
    if not chroma_dir.exists():
        raise FileNotFoundError(f"ChromaDB directory not found: {chroma_dir}")

    try:
        import chromadb  # type: ignore
    except ImportError as exc:
        raise ImportError("chromadb is required for dense retrieval.") from exc

    client = chromadb.PersistentClient(path=str(chroma_dir))
    try:
        collection = client.get_collection(name=collection_name)
    except Exception as exc:
        raise RuntimeError(
            f"Unable to load Chroma collection '{collection_name}' from {chroma_dir}"
        ) from exc

    return collection


def _to_float_list(vector: Sequence[float] | np.ndarray) -> List[float]:
    """Convert embedding vector to a plain Python float list."""
    if isinstance(vector, np.ndarray):
        return vector.astype(np.float32).tolist()
    return [float(item) for item in vector]


def _cosine_similarity(query_vec: Sequence[float], doc_vec: Sequence[float]) -> float:
    """Compute cosine similarity with robust numerical safeguards."""
    q = np.asarray(query_vec, dtype=np.float32)
    d = np.asarray(doc_vec, dtype=np.float32)

    if q.ndim != 1 or d.ndim != 1 or q.shape[0] != d.shape[0]:
        raise ValueError("Embedding dimension mismatch during cosine similarity computation")

    q_norm = float(np.linalg.norm(q))
    d_norm = float(np.linalg.norm(d))
    if q_norm == 0.0 or d_norm == 0.0:
        return 0.0

    similarity = float(np.dot(q, d) / (q_norm * d_norm))
    if math.isnan(similarity) or math.isinf(similarity):
        return 0.0

    return max(-1.0, min(1.0, similarity))


def _coerce_metadata(metadata: Any) -> Dict[str, Any]:
    """Normalize potentially corrupted metadata into dictionary form."""
    if isinstance(metadata, dict):
        return metadata
    if metadata is None:
        return {}
    return {"raw_metadata": str(metadata)}


def _safe_extract_first(payload: Dict[str, Any], key: str) -> List[Any]:
    """Extract first result list from Chroma query payload."""
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    if isinstance(first, list):
        return first
    return []


def _build_items(
    query_embedding: Sequence[float],
    result_payload: Dict[str, Any],
) -> List[DenseRetrievalItem]:
    """Convert raw Chroma payload into ranked retrieval records."""
    documents = _safe_extract_first(result_payload, "documents")
    metadatas = _safe_extract_first(result_payload, "metadatas")
    distances = _safe_extract_first(result_payload, "distances")
    ids = _safe_extract_first(result_payload, "ids")
    embeddings = _safe_extract_first(result_payload, "embeddings")

    items: List[DenseRetrievalItem] = []
    total = len(documents)

    for idx in range(total):
        rank = idx + 1
        document = str(documents[idx]) if idx < len(documents) else ""
        metadata = _coerce_metadata(metadatas[idx] if idx < len(metadatas) else {})

        distance_value: Optional[float] = None
        if idx < len(distances):
            try:
                distance_value = float(distances[idx])
            except (TypeError, ValueError):
                distance_value = None

        similarity_score = 0.0
        if idx < len(embeddings) and isinstance(embeddings[idx], (list, tuple)):
            try:
                similarity_score = _cosine_similarity(query_embedding, embeddings[idx])
            except Exception:
                LOGGER.warning(
                    "Failed to compute cosine similarity for rank=%d; falling back to distance transform",
                    rank,
                )
                similarity_score = 1.0 - distance_value if distance_value is not None else 0.0
        else:
            similarity_score = 1.0 - distance_value if distance_value is not None else 0.0

        chunk_id = str(ids[idx]) if idx < len(ids) else None

        items.append(
            DenseRetrievalItem(
                rank=rank,
                distance=distance_value,
                similarity_score=float(similarity_score),
                document=document,
                metadata=metadata,
                chunk_id=chunk_id,
            )
        )

    return items


def _validate_response(response: DenseRetrievalResponse) -> None:
    """Runtime validation to ensure retrieval output integrity."""
    if response.total_results != len(response.results):
        raise RuntimeError(
            "Dense retrieval response validation failed: total_results mismatch"
        )

    expected_rank = 1
    for item in response.results:
        if item.rank != expected_rank:
            raise RuntimeError(
                f"Dense retrieval response validation failed: unexpected rank {item.rank}"
            )
        if not isinstance(item.document, str):
            raise RuntimeError("Dense retrieval response validation failed: document is not a string")
        if not isinstance(item.metadata, dict):
            raise RuntimeError("Dense retrieval response validation failed: metadata is not a dictionary")
        expected_rank += 1


def run(query: str, config: DenseRetrieverConfig | None = None) -> DenseRetrievalResponse:
    """Run dense semantic retrieval for a SOC analyst query.

    Args:
        query: Analyst question, indicator, or vulnerability query.
        config: Optional runtime configuration override.

    Returns:
        Structured retrieval response with ranked evidence chunks.

    Raises:
        ValueError: If query or config is invalid.
        FileNotFoundError: If ChromaDB path does not exist.
        RuntimeError: If retrieval execution fails.
        ImportError: If required runtime dependencies are unavailable.
    """
    _configure_logging()
    runtime_config = config or DenseRetrieverConfig()
    _validate_config(runtime_config)

    normalized_query = _normalize_query(query)
    LOGGER.info(
        "Dense retrieval started | collection=%s | top_k=%d",
        runtime_config.collection_name,
        runtime_config.top_k,
    )

    # ------------------------------------------------------------------
    # CVE-ID fast-path: exact metadata lookup before loading the model
    # ------------------------------------------------------------------
    detected_cves = _extract_cve_ids(normalized_query)
    collection = _load_chroma_collection(runtime_config.chroma_dir, runtime_config.collection_name)

    if detected_cves:
        LOGGER.info("CVE IDs detected in query: %s – attempting metadata lookup", detected_cves)
        started = time.perf_counter()

        if len(detected_cves) == 1:
            where_filter: Dict[str, Any] = {"cve_id": {"$eq": detected_cves[0]}}
        else:
            where_filter = {"cve_id": {"$in": detected_cves}}

        try:
            meta_payload = collection.get(
                where=where_filter,
                include=["documents", "metadatas"],
            )
        except Exception:  # noqa: BLE001
            LOGGER.warning(
                "Metadata lookup for %s failed; falling back to semantic search",
                detected_cves,
                exc_info=True,
            )
            meta_payload = None

        if meta_payload and meta_payload.get("ids"):
            items = _build_metadata_items(meta_payload)
            latency_ms = (time.perf_counter() - started) * 1000.0

            response = DenseRetrievalResponse(
                query=normalized_query,
                collection_name=runtime_config.collection_name,
                embedding_model=runtime_config.embedding_model,
                top_k_requested=runtime_config.top_k,
                total_results=len(items),
                latency_ms=latency_ms,
                generated_at_utc=datetime.now(timezone.utc).isoformat(),
                results=items,
            )
            _validate_response(response)
            LOGGER.info(
                "CVE metadata lookup succeeded | results=%d | latency_ms=%.2f",
                response.total_results,
                response.latency_ms,
            )
            return response

        LOGGER.info(
            "No metadata match for %s; falling back to semantic retrieval",
            detected_cves,
        )

    # ------------------------------------------------------------------
    # Standard semantic retrieval pipeline
    # ------------------------------------------------------------------
    model = _load_sentence_transformer(runtime_config.embedding_model, runtime_config.device)

    started = time.perf_counter()
    query_embedding_array = model.encode(
        [normalized_query],
        convert_to_numpy=True,
        normalize_embeddings=False,
        show_progress_bar=False,
        device=runtime_config.device,
    )
    query_embedding = _to_float_list(query_embedding_array[0])

    includes = ["documents", "metadatas", "distances"]
    if runtime_config.include_embeddings:
        includes.append("embeddings")

    try:
        payload = collection.query(
            query_embeddings=[query_embedding],
            n_results=runtime_config.top_k,
            include=includes,
        )
    except Exception as exc:
        raise RuntimeError("Chroma dense retrieval query failed") from exc

    latency_ms = (time.perf_counter() - started) * 1000.0
    if latency_ms > (runtime_config.query_timeout_seconds * 1000.0):
        LOGGER.warning(
            "Dense retrieval exceeded soft timeout target: %.2f ms > %.2f ms",
            latency_ms,
            runtime_config.query_timeout_seconds * 1000.0,
        )

    items = _build_items(query_embedding=query_embedding, result_payload=payload)

    response = DenseRetrievalResponse(
        query=normalized_query,
        collection_name=runtime_config.collection_name,
        embedding_model=runtime_config.embedding_model,
        top_k_requested=runtime_config.top_k,
        total_results=len(items),
        latency_ms=latency_ms,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        results=items,
    )

    _validate_response(response)

    LOGGER.info(
        "Dense retrieval completed | results=%d | latency_ms=%.2f",
        response.total_results,
        response.latency_ms,
    )
    return response


def _build_cli_parser() -> argparse.ArgumentParser:
    """Create CLI parser for lightweight runtime validation."""
    parser = argparse.ArgumentParser(description="Run SecureRAG dense retrieval module")
    parser.add_argument("query", type=str, help="Analyst query text")
    parser.add_argument("--top-k", type=int, default=10, help="Top-k results to retrieve")
    parser.add_argument(
        "--collection",
        type=str,
        default=DEFAULT_COLLECTION_NAME,
        help="Chroma collection name",
    )
    parser.add_argument(
        "--chroma-dir",
        type=Path,
        default=DEFAULT_CHROMA_DIR,
        help="Path to persistent ChromaDB directory",
    )
    parser.add_argument(
        "--embedding-model",
        type=str,
        default=DEFAULT_EMBEDDING_MODEL,
        help="SentenceTransformer embedding model name",
    )
    parser.add_argument("--device", type=str, default="cpu", help="Embedding inference device")
    return parser


def _main() -> int:
    """CLI entrypoint for manual testing and runtime validation."""
    parser = _build_cli_parser()
    args = parser.parse_args()

    config = DenseRetrieverConfig(
        chroma_dir=args.chroma_dir,
        collection_name=args.collection,
        embedding_model=args.embedding_model,
        top_k=args.top_k,
        device=args.device,
    )

    try:
        response = run(query=args.query, config=config)
    except Exception as exc:  # pragma: no cover - CLI surface
        LOGGER.exception("Dense retrieval failed")
        print(f"ERROR: {exc}")
        return 1

    print("Dense retrieval successful")
    print(f"Query: {response.query}")
    print(f"Total results: {response.total_results}")
    print(f"Latency (ms): {response.latency_ms:.2f}")

    for item in response.results:
        print(
            f"[{item.rank}] similarity={item.similarity_score:.4f} "
            f"distance={item.distance} chunk_id={item.chunk_id}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
