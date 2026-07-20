"""Module 2 orchestration for SecureRAG.

This script runs the full Module 2 pipeline in order:
chunker -> embedder -> vector_store -> bm25_index -> verify_embeddings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from modules.Chunking import bm25_index, chunker, embedder, vector_store, verify_embeddings


LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class KnowledgeBaseBuildConfig:
    """Runtime configuration for the Module 2 pipeline."""

    chunker_config: Optional[chunker.ChunkerConfig] = None
    embedder_config: Optional[embedder.EmbedderConfig] = None
    vector_store_config: Optional[vector_store.VectorStoreConfig] = None
    bm25_config: Optional[bm25_index.BM25Config] = None
    verification_config: Optional[verify_embeddings.VerificationConfig] = None


def _configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


def run(config: Optional[KnowledgeBaseBuildConfig] = None) -> dict:
    """Execute the entire Module 2 pipeline."""
    _configure_logging()
    runtime_config = config or KnowledgeBaseBuildConfig()

    LOGGER.info("Starting SecureRAG Module 2 pipeline")

    try:
        LOGGER.info("Step 1/5: Chunking")
        chunker_output = chunker.run(runtime_config.chunker_config)

        LOGGER.info("Step 2/5: Dense embedding")
        embedded_output = embedder.run(runtime_config.embedder_config)

        LOGGER.info("Step 3/5: Vector store")
        vector_store_output = vector_store.run(runtime_config.vector_store_config)

        LOGGER.info("Step 4/5: BM25 indexing")
        bm25_output = bm25_index.run(runtime_config.bm25_config)

        LOGGER.info("Step 5/5: Verification")
        verification_report = verify_embeddings.run(runtime_config.verification_config)

    except Exception:
        LOGGER.exception("Module 2 pipeline failed")
        raise

    LOGGER.info("Module 2 pipeline completed successfully")
    return {
        "chunker_output": str(chunker_output),
        "embedded_output": str(embedded_output),
        "vector_store_output": str(vector_store_output),
        "bm25_output": str(bm25_output),
        "verification_report": verification_report,
    }


if __name__ == "__main__":
    run()