"""Module 2.4 - Sparse BM25 index for SecureRAG.

This module builds a BM25 retrieval index over the chunk corpus generated in
Module 2.1. It persists both the tokenized corpus and the BM25 object for fast
loading during hybrid retrieval in Phase 4.
"""

from __future__ import annotations

import json
import logging
import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from tqdm import tqdm


LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHUNKS_FILE = PROJECT_ROOT / "data" / "chunks" / "chunks.json"
DEFAULT_BM25_FILE = PROJECT_ROOT / "data" / "embeddings" / "bm25.pkl"
DEFAULT_CORPUS_FILE = PROJECT_ROOT / "data" / "embeddings" / "corpus.pkl"


@dataclass(slots=True)
class BM25Config:
    """Runtime configuration for BM25 index generation."""

    chunks_file: Path = DEFAULT_CHUNKS_FILE
    bm25_file: Path = DEFAULT_BM25_FILE
    corpus_file: Path = DEFAULT_CORPUS_FILE


def _configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


def _load_chunks(chunks_file: Path) -> List[Dict[str, Any]]:
    if not chunks_file.exists():
        raise FileNotFoundError(f"Chunk file not found: {chunks_file}")

    with chunks_file.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, list):
        raise ValueError(f"Expected a list in {chunks_file}, got {type(data).__name__}")

    return data


def _tokenize(text: str) -> List[str]:
    """Tokenize text for sparse retrieval using a deterministic regex-based tokenizer."""
    normalized = text.lower()
    tokens = re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", normalized)
    return tokens


def _prepare_corpus(chunks: Sequence[Dict[str, Any]]) -> List[List[str]]:
    corpus: List[List[str]] = []
    progress = tqdm(total=len(chunks), desc="Tokenizing corpus", unit="chunk", ncols=100)

    try:
        for chunk in chunks:
            text = str(chunk.get("text", ""))
            corpus.append(_tokenize(text))
            progress.update(1)
    finally:
        progress.close()

    return corpus


def _save_pickle(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)


def build_index(config: Optional[BM25Config] = None) -> Path:
    """Build and persist the BM25 index and tokenized corpus."""
    _configure_logging()
    runtime_config = config or BM25Config()

    try:
        from rank_bm25 import BM25Okapi
    except ImportError as exc:
        raise ImportError(
            "rank-bm25 is required for Module 2.4. Install the project dependencies first."
        ) from exc

    LOGGER.info("Starting BM25 index build")
    LOGGER.info("Chunks file: %s", runtime_config.chunks_file)
    LOGGER.info("BM25 file: %s", runtime_config.bm25_file)
    LOGGER.info("Corpus file: %s", runtime_config.corpus_file)

    chunks = _load_chunks(runtime_config.chunks_file)
    LOGGER.info("Loaded %d chunks", len(chunks))

    corpus = _prepare_corpus(chunks)
    LOGGER.info("Prepared tokenized corpus with %d documents", len(corpus))

    bm25 = BM25Okapi(corpus)

    _save_pickle(runtime_config.bm25_file, bm25)
    _save_pickle(runtime_config.corpus_file, corpus)

    LOGGER.info("Saved BM25 index to %s", runtime_config.bm25_file)
    LOGGER.info("Saved tokenized corpus to %s", runtime_config.corpus_file)

    return runtime_config.bm25_file


def run(config: Optional[BM25Config] = None) -> Path:
    """Compatibility wrapper for pipeline orchestration."""
    return build_index(config=config)


if __name__ == "__main__":
    build_index()