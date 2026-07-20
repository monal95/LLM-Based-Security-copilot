"""Module 2.2 - Dense embedding generation for SecureRAG.

This module loads chunked CTI documents from ``data/chunks/chunks.json``,
generates a 384-dimensional embedding for each chunk using
``sentence-transformers/all-MiniLM-L6-v2``, and persists the enriched chunk
records to ``data/embeddings/embedded_chunks.pkl``.
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, TYPE_CHECKING

import numpy as np
from tqdm import tqdm

if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from sentence_transformers import SentenceTransformer


LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHUNKS_FILE = PROJECT_ROOT / "data" / "chunks" / "chunks.json"
DEFAULT_OUTPUT_FILE = PROJECT_ROOT / "data" / "embeddings" / "embedded_chunks.pkl"
DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass(slots=True)
class EmbedderConfig:
    """Runtime configuration for dense embedding generation."""

    chunks_file: Path = DEFAULT_CHUNKS_FILE
    output_file: Path = DEFAULT_OUTPUT_FILE
    model_name: str = DEFAULT_MODEL_NAME
    batch_size: int = 64


def _configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


def _load_chunks(chunks_file: Path) -> List[Dict[str, Any]]:
    if not chunks_file.exists():
        raise FileNotFoundError(f"Chunk file not found: {chunks_file}")

    import json

    with chunks_file.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, list):
        raise ValueError(f"Expected a list in {chunks_file}, got {type(data).__name__}")

    return data


def _load_model(model_name: str) -> "SentenceTransformer":
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "sentence-transformers is required for Module 2.2. Install the project dependencies first."
        ) from exc

    LOGGER.info("Loading embedding model '%s' on CPU", model_name)
    model = SentenceTransformer(model_name, device="cpu")
    return model


def _prepare_texts(chunks: Sequence[Dict[str, Any]]) -> List[str]:
    texts: List[str] = []
    for chunk in chunks:
        text = str(chunk.get("text", "")).strip()
        texts.append(text)
    return texts


def _encode_batch(model: SentenceTransformer, batch_texts: Sequence[str]) -> np.ndarray:
    embeddings = model.encode(
        list(batch_texts),
        batch_size=len(batch_texts) if batch_texts else 1,
        convert_to_numpy=True,
        normalize_embeddings=False,
        show_progress_bar=False,
        device="cpu",
    )
    if embeddings.ndim == 1:
        embeddings = np.expand_dims(embeddings, axis=0)
    return embeddings


def _embed_chunks(
    chunks: List[Dict[str, Any]],
    model: SentenceTransformer,
    batch_size: int,
) -> List[Dict[str, Any]]:
    embedded_chunks: List[Dict[str, Any]] = []
    total_batches = max(1, (len(chunks) + batch_size - 1) // batch_size)

    progress = tqdm(total=len(chunks), desc="Embedding chunks", unit="chunk", ncols=100)

    try:
        for start_index in range(0, len(chunks), batch_size):
            batch = chunks[start_index : start_index + batch_size]
            batch_texts = _prepare_texts(batch)

            try:
                embeddings = _encode_batch(model, batch_texts)
            except Exception as exc:
                LOGGER.exception(
                    "Batch embedding failed for items %d-%d of %d; retrying individually",
                    start_index,
                    min(start_index + batch_size, len(chunks)) - 1,
                    len(chunks),
                )
                embeddings = []
                for text in batch_texts:
                    try:
                        single_embedding = _encode_batch(model, [text])[0]
                        embeddings.append(single_embedding)
                    except Exception:
                        LOGGER.exception("Failed to embed chunk text during fallback path")
                        embeddings.append(np.zeros(384, dtype=np.float32))
                embeddings = np.asarray(embeddings)

            for original_chunk, embedding in zip(batch, embeddings):
                enriched_chunk = dict(original_chunk)
                enriched_chunk["embedding"] = embedding.astype(np.float32).tolist()
                embedded_chunks.append(enriched_chunk)

            progress.update(len(batch))
    finally:
        progress.close()

    if len(embedded_chunks) != len(chunks):
        raise RuntimeError(
            f"Embedding count mismatch: expected {len(chunks)}, got {len(embedded_chunks)}"
        )

    LOGGER.info("Embedded %d chunks across %d batches", len(embedded_chunks), total_batches)
    return embedded_chunks


def _save_embeddings(output_file: Path, embedded_chunks: List[Dict[str, Any]]) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("wb") as handle:
        pickle.dump(embedded_chunks, handle, protocol=pickle.HIGHEST_PROTOCOL)


def run(config: EmbedderConfig | None = None) -> Path:
    """Run Module 2.2 and persist the embedded chunk collection."""
    _configure_logging()
    runtime_config = config or EmbedderConfig()

    LOGGER.info("Starting embedding pipeline")
    LOGGER.info("Chunks file: %s", runtime_config.chunks_file)
    LOGGER.info("Output file: %s", runtime_config.output_file)
    LOGGER.info("Batch size: %d", runtime_config.batch_size)

    chunks = _load_chunks(runtime_config.chunks_file)
    LOGGER.info("Loaded %d chunks", len(chunks))

    model = _load_model(runtime_config.model_name)
    embedded_chunks = _embed_chunks(chunks, model, runtime_config.batch_size)
    _save_embeddings(runtime_config.output_file, embedded_chunks)

    LOGGER.info("Saved %d embedded chunks to %s", len(embedded_chunks), runtime_config.output_file)
    return runtime_config.output_file


if __name__ == "__main__":
    run()