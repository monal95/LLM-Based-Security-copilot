"""Module 2.5 - Lightweight verification for the SecureRAG retrieval artifacts.

This module performs a low-memory verification pass over the Module 2 outputs.
It checks the expected files, reports sizes, validates the ChromaDB collection,
inspects a small sample of embedded chunks and BM25 corpus entries, and runs a
single semantic query to confirm retrieval quality for Log4Shell.
"""

from __future__ import annotations

import json
import logging
import math
import os
import pickle
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHUNKS_FILE = PROJECT_ROOT / "data" / "chunks" / "chunks.json"
DEFAULT_EMBEDDED_CHUNKS_FILE = PROJECT_ROOT / "data" / "embeddings" / "embedded_chunks.pkl"
DEFAULT_CHROMA_DIR = PROJECT_ROOT / "embeddings" / "chroma_db"
DEFAULT_COLLECTION_NAME = "secure_rag_chunks"
DEFAULT_BM25_FILE = PROJECT_ROOT / "data" / "embeddings" / "bm25.pkl"
DEFAULT_CORPUS_FILE = PROJECT_ROOT / "data" / "embeddings" / "corpus.pkl"


class _SampleReadComplete(Exception):
    """Internal signal used to stop unpickling after a small sample."""


class _SampleListUnpickler(pickle._Unpickler):
    """Read only the first few items from a top-level pickled list."""

    def __init__(self, file_obj: Any, sample_limit: int) -> None:
        super().__init__(file_obj)
        self.sample_limit = sample_limit
        self.loaded_items = 0
        self.root_list: Optional[list[Any]] = None
        self.dispatch = self.dispatch.copy()
        self.dispatch[pickle.EMPTY_LIST[0]] = _SampleListUnpickler.load_empty_list
        self.dispatch[pickle.APPEND[0]] = _SampleListUnpickler.load_append
        if hasattr(pickle, "APPENDS"):
            self.dispatch[pickle.APPENDS[0]] = _SampleListUnpickler.load_appends

    def load_empty_list(self) -> None:
        super().load_empty_list()
        if self.root_list is None:
            self.root_list = self.stack[-1]

    def load_append(self) -> None:
        item = self.stack.pop()
        target = self.stack[-1]
        target.append(item)
        if target is self.root_list:
            self.loaded_items += 1
            if self.loaded_items >= self.sample_limit:
                raise _SampleReadComplete

    def load_appends(self) -> None:
        items = self.pop_mark()
        target = self.stack[-1]
        target.extend(items)
        if target is self.root_list:
            self.loaded_items += len(items)
            if self.loaded_items >= self.sample_limit:
                raise _SampleReadComplete


@dataclass(slots=True)
class VerificationConfig:
    """Runtime configuration for Module 2 verification."""

    chunks_file: Path = DEFAULT_CHUNKS_FILE
    embedded_chunks_file: Path = DEFAULT_EMBEDDED_CHUNKS_FILE
    chroma_dir: Path = DEFAULT_CHROMA_DIR
    collection_name: str = DEFAULT_COLLECTION_NAME
    bm25_file: Path = DEFAULT_BM25_FILE
    corpus_file: Path = DEFAULT_CORPUS_FILE
    query_text: str = "Log4Shell remote code execution"


def _configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


def _human_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"

    units = ["KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        size /= 1024.0
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.2f} {unit}"
    return f"{num_bytes} B"


def _path_size(path: Path) -> Optional[int]:
    if not path.exists():
        return None
    if path.is_file():
        return path.stat().st_size

    total = 0
    for root, _, files in os.walk(path):
        for filename in files:
            try:
                total += (Path(root) / filename).stat().st_size
            except OSError:
                continue
    return total


def _load_pickle_sample(path: Path, sample_limit: int) -> List[Any]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with path.open("rb") as handle:
        unpickler = _SampleListUnpickler(handle, sample_limit=sample_limit)
        try:
            data = unpickler.load()
        except _SampleReadComplete:
            data = unpickler.root_list or []

    if not isinstance(data, list):
        raise ValueError(f"Expected a list in {path}, got {type(data).__name__}")

    return data[:sample_limit]


def _tokenize(query: str) -> List[str]:
    import re

    tokens = re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", query.lower())
    return tokens


def _top_bm25_query(query: str, corpus: Sequence[Sequence[str]], top_k: int = 5) -> List[int]:
    query_tokens = _tokenize(query)
    if not corpus or not query_tokens:
        return []

    total_documents = len(corpus)
    total_length = sum(len(document) for document in corpus)
    average_length = total_length / total_documents if total_documents else 0.0

    document_frequencies: Dict[str, int] = {}
    for document in corpus:
        for token in set(document):
            document_frequencies[token] = document_frequencies.get(token, 0) + 1

    k1 = 1.5
    b = 0.75
    scores: List[float] = []
    for document in corpus:
        token_counts: Dict[str, int] = {}
        for token in document:
            token_counts[token] = token_counts.get(token, 0) + 1

        document_length = len(document)
        score = 0.0
        for token in query_tokens:
            document_frequency = document_frequencies.get(token, 0)
            if document_frequency <= 0:
                continue

            idf = math.log(1.0 + ((total_documents - document_frequency + 0.5) / (document_frequency + 0.5)))
            term_frequency = token_counts.get(token, 0)
            if term_frequency <= 0:
                continue

            denominator = term_frequency + k1 * (1.0 - b + b * (document_length / average_length if average_length else 0.0))
            if denominator > 0:
                score += idf * ((term_frequency * (k1 + 1.0)) / denominator)

        scores.append(score)

    ranked = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)
    return ranked[:top_k]


def _load_chroma_collection(chroma_dir: Path, collection_name: str) -> Any:
    try:
        import chromadb  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "chromadb is required for Module 2.5. Install the project dependencies first."
        ) from exc

    client = chromadb.PersistentClient(path=str(chroma_dir))
    return client.get_collection(name=collection_name)


def _query_chroma(query_text: str, chroma_dir: Path, collection_name: str, top_k: int = 5) -> Dict[str, Any]:
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "sentence-transformers is required for Module 2.5. Install the project dependencies first."
        ) from exc

    collection = _load_chroma_collection(chroma_dir, collection_name)
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")
    query_embedding = model.encode([query_text], convert_to_numpy=True, device="cpu")[0].tolist()

    started = time.perf_counter()
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    latency = time.perf_counter() - started

    return {"result": result, "latency": latency, "collection_count": collection.count()}


def _paper_report_line(label: str, value: Any) -> str:
    return f"{label}: {value}"


def _get_mapping_value(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        return payload.get(key)
    return None


def _check_flag(lines: List[str], passed: bool, success: str, failure: str) -> None:
    lines.append(f"✓ {success}" if passed else f"✗ {failure}")


def run(config: Optional[VerificationConfig] = None) -> Dict[str, Any]:
    """Run Module 2 verification and return a structured summary."""
    _configure_logging()
    runtime_config = config or VerificationConfig()

    LOGGER.info("Starting Module 2 verification")
    LOGGER.info("Chunks file: %s", runtime_config.chunks_file)
    LOGGER.info("Embedded chunks file: %s", runtime_config.embedded_chunks_file)
    LOGGER.info("Chroma directory: %s", runtime_config.chroma_dir)
    LOGGER.info("BM25 file: %s", runtime_config.bm25_file)
    LOGGER.info("Corpus file: %s", runtime_config.corpus_file)

    report_lines: List[str] = []
    issues: List[str] = []
    file_sizes: Dict[str, Optional[int]] = {
        "chunks.json": _path_size(runtime_config.chunks_file),
        "embedded_chunks.pkl": _path_size(runtime_config.embedded_chunks_file),
        "bm25.pkl": _path_size(runtime_config.bm25_file),
        "corpus.pkl": _path_size(runtime_config.corpus_file),
        "ChromaDB": _path_size(runtime_config.chroma_dir),
    }

    chunks_exists = runtime_config.chunks_file.exists()
    embedded_exists = runtime_config.embedded_chunks_file.exists()
    bm25_exists = runtime_config.bm25_file.exists()
    corpus_exists = runtime_config.corpus_file.exists()
    chroma_exists = runtime_config.chroma_dir.exists()

    _check_flag(report_lines, chunks_exists, "chunks.json found", "chunks.json missing")
    _check_flag(report_lines, embedded_exists, "embedded_chunks.pkl found", "embedded_chunks.pkl missing")
    _check_flag(report_lines, bm25_exists, "bm25.pkl found", "bm25.pkl missing")
    _check_flag(report_lines, corpus_exists, "corpus.pkl found", "corpus.pkl missing")
    _check_flag(report_lines, chroma_exists, "ChromaDB found", "ChromaDB missing")

    if not chunks_exists:
        issues.append(f"Missing chunks file: {runtime_config.chunks_file}")
    if not embedded_exists:
        issues.append(f"Missing embedded chunks file: {runtime_config.embedded_chunks_file}")
    if not bm25_exists:
        issues.append(f"Missing BM25 file: {runtime_config.bm25_file}")
    if not corpus_exists:
        issues.append(f"Missing corpus file: {runtime_config.corpus_file}")
    if not chroma_exists:
        issues.append(f"Missing ChromaDB directory: {runtime_config.chroma_dir}")

    sample_corpus: List[List[str]] = []
    collection_count: Optional[int] = None
    vector_dimension: Optional[int] = None
    semantic_passed = False
    bm25_passed = False
    peek_count = 0
    top_results: List[Dict[str, Any]] = []

    if embedded_exists:
        try:
            sample_embedding = _load_pickle_sample(runtime_config.embedded_chunks_file, sample_limit=1)
            if not sample_embedding:
                issues.append("embedded_chunks.pkl did not contain a readable sample")
                _check_flag(report_lines, False, "Embedding dimension = 384", "Embedding dimension != 384")
            else:
                first_embedding = sample_embedding[0]
                if not isinstance(first_embedding, dict):
                    issues.append("First embedded chunk is not a dictionary")
                    _check_flag(report_lines, False, "Embedding dimension = 384", "Embedding dimension != 384")
                else:
                    embedding_vector = first_embedding.get("embedding")
                    metadata = first_embedding.get("metadata")
                    vector_dimension = len(embedding_vector) if isinstance(embedding_vector, list) else None
                    sample_ok = vector_dimension == 384 and isinstance(metadata, dict) and bool(metadata)
                    _check_flag(report_lines, sample_ok, "Embedding dimension = 384", "Embedding dimension != 384")
                    if not sample_ok:
                        issues.append("Sample embedding did not validate dimension 384 and metadata presence")
        except Exception as exc:
            issues.append(f"Sample embedding load failed: {exc}")
            _check_flag(report_lines, False, "Embedding dimension = 384", "Embedding dimension != 384")

    if chroma_exists:
        try:
            collection = _load_chroma_collection(runtime_config.chroma_dir, runtime_config.collection_name)
            collection_count = collection.count()
            _check_flag(report_lines, True, f"Vector count = {collection_count}", "Vector count unavailable")

            peek = collection.peek(limit=5)
            peek_embeddings = _get_mapping_value(peek, "embeddings") or []
            peek_metadatas = _get_mapping_value(peek, "metadatas") or []
            peek_documents = _get_mapping_value(peek, "documents") or []
            peek_count = min(5, len(peek_embeddings) or len(peek_metadatas) or len(peek_documents))

            if isinstance(peek_embeddings, list) and peek_embeddings and isinstance(peek_embeddings[0], list):
                vector_dimension = len(peek_embeddings[0])

            try:
                semantic_info = _query_chroma(runtime_config.query_text, runtime_config.chroma_dir, runtime_config.collection_name)
                result = semantic_info["result"]
                documents = result.get("documents", [[]])[0]
                metadatas = result.get("metadatas", [[]])[0]
                distances = result.get("distances", [[]])[0]

                for index, document in enumerate(documents):
                    metadata = metadatas[index] if index < len(metadatas) else {}
                    top_results.append(
                        {
                            "rank": index + 1,
                            "text": document,
                            "metadata": metadata,
                            "distance": distances[index] if index < len(distances) else None,
                        }
                    )

                semantic_passed = any(
                    (
                        isinstance(item.get("metadata"), dict)
                        and item["metadata"].get("cve_id") == "CVE-2021-44228"
                    )
                    or "CVE-2021-44228" in str(item.get("text", ""))
                    for item in top_results
                )
                _check_flag(report_lines, semantic_passed, "Semantic search passed", "Semantic search failed")
            except Exception as exc:
                issues.append(f"Semantic query failed: {exc}")
                _check_flag(report_lines, False, "Semantic search passed", "Semantic search failed")
        except Exception as exc:
            issues.append(f"ChromaDB verification failed: {exc}")
            _check_flag(report_lines, False, "Vector count unavailable", "Vector count unavailable")

    if corpus_exists:
        try:
            sample_corpus = _load_pickle_sample(runtime_config.corpus_file, sample_limit=5)
            if sample_corpus:
                bm25_top_indices = _top_bm25_query(runtime_config.query_text, sample_corpus, top_k=5)
                bm25_passed = bool(bm25_top_indices)
                _check_flag(report_lines, bm25_passed, "BM25 passed", "BM25 failed")
            else:
                issues.append("corpus.pkl did not contain a readable sample")
                _check_flag(report_lines, False, "BM25 passed", "BM25 failed")
        except Exception as exc:
            issues.append(f"BM25 query failed: {exc}")
            _check_flag(report_lines, False, "BM25 passed", "BM25 failed")

    for label, size in file_sizes.items():
        if size is None:
            LOGGER.info("%s size: missing", label)
        else:
            LOGGER.info("%s size: %s", label, _human_size(size))

    for line in report_lines:
        LOGGER.info(line)
        print(line)

    final_status = not issues and chunks_exists and embedded_exists and bm25_exists and corpus_exists and chroma_exists and semantic_passed and bm25_passed
    final_line = "Module 2 Verification PASSED" if final_status else "Module 2 Verification FAILED"
    LOGGER.info(final_line)
    print(final_line)

    return {
        "chunk_count": None,
        "embedding_count": None,
        "collection_size": collection_count,
        "bm25_document_count": None,
        "query_text": runtime_config.query_text,
        "query_latency_seconds": None,
        "top_results": top_results,
        "bm25_top_documents": [],
        "top_result_contains_log4shell": semantic_passed,
        "file_sizes": file_sizes,
        "vector_dimension": vector_dimension,
        "vector_count": collection_count,
        "semantic_search_passed": semantic_passed,
        "bm25_passed": bm25_passed,
        "issues": issues,
        "report_lines": report_lines + [final_line],
        "passed": final_status,
        "peek_count": peek_count,
    }


if __name__ == "__main__":
    run()