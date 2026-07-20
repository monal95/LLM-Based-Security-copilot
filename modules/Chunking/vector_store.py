"""Module 2.3 - Persistent ChromaDB vector store for SecureRAG.

This module loads the dense embedded chunk payload from
``data/embeddings/embedded_chunks.pkl`` and stores the records in a persistent
local ChromaDB collection under ``embeddings/chroma_db/``.
"""

from __future__ import annotations

import json
import logging
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from tqdm import tqdm


LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EMBEDDED_CHUNKS_FILE = PROJECT_ROOT / "data" / "embeddings" / "embedded_chunks.pkl"
DEFAULT_CHROMA_DIR = PROJECT_ROOT / "embeddings" / "chroma_db"
DEFAULT_COLLECTION_NAME = "secure_rag_chunks"
DEFAULT_BATCH_SIZE = 256


@dataclass(slots=True)
class VectorStoreConfig:
	"""Runtime configuration for the persistent vector store."""

	embedded_chunks_file: Path = DEFAULT_EMBEDDED_CHUNKS_FILE
	chroma_dir: Path = DEFAULT_CHROMA_DIR
	collection_name: str = DEFAULT_COLLECTION_NAME
	batch_size: int = DEFAULT_BATCH_SIZE


def _configure_logging() -> None:
	if not logging.getLogger().handlers:
		logging.basicConfig(
			level=logging.INFO,
			format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
		)


def _load_embedded_chunks(embedded_chunks_file: Path) -> List[Dict[str, Any]]:
	if not embedded_chunks_file.exists():
		raise FileNotFoundError(f"Embedded chunks file not found: {embedded_chunks_file}")

	with embedded_chunks_file.open("rb") as handle:
		data = pickle.load(handle)

	if not isinstance(data, list):
		raise ValueError(
			f"Expected a list in {embedded_chunks_file}, got {type(data).__name__}"
		)

	return data


def _normalize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
	normalized: Dict[str, Any] = {}
	for key, value in metadata.items():
		if value is None or isinstance(value, (str, int, float, bool)):
			normalized[key] = value
		elif isinstance(value, (list, tuple, set, dict)):
			normalized[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
		else:
			normalized[key] = str(value)
	return normalized


def _existing_ids(collection: Any) -> set[str]:
	ids: set[str] = set()
	offset = 0
	page_size = 5000

	while True:
		result = collection.get(limit=page_size, offset=offset, include=[])
		batch_ids = result.get("ids", []) if isinstance(result, dict) else []
		if not batch_ids:
			break
		ids.update(str(item) for item in batch_ids)
		offset += page_size

	return ids


def _chunk_batches(items: Sequence[Dict[str, Any]], batch_size: int) -> Iterable[List[Dict[str, Any]]]:
	for start in range(0, len(items), batch_size):
		yield list(items[start : start + batch_size])


def _prepare_records(records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
	prepared: List[Dict[str, Any]] = []
	for record in records:
		chunk_id = str(record.get("id", "")).strip()
		text = str(record.get("text", ""))
		metadata = record.get("metadata", {})
		embedding = record.get("embedding")

		if not chunk_id:
			raise ValueError("Encountered an embedded chunk without an id")
		if not isinstance(metadata, dict):
			raise ValueError(f"Chunk {chunk_id} has invalid metadata type: {type(metadata).__name__}")
		if embedding is None:
			raise ValueError(f"Chunk {chunk_id} is missing an embedding")

		prepared.append(
			{
				"id": chunk_id,
				"text": text,
				"metadata": _normalize_metadata(metadata),
				"embedding": embedding,
			}
		)
	return prepared


def build_vector_store(config: Optional[VectorStoreConfig] = None) -> Path:
	"""Build or update the persistent ChromaDB vector store."""
	_configure_logging()
	runtime_config = config or VectorStoreConfig()

	try:
		import chromadb  # type: ignore
	except ImportError as exc:
		raise ImportError(
			"chromadb is required for Module 2.3. Install the project dependencies first."
		) from exc

	LOGGER.info("Starting ChromaDB vector store build")
	LOGGER.info("Embedded chunks file: %s", runtime_config.embedded_chunks_file)
	LOGGER.info("Chroma directory: %s", runtime_config.chroma_dir)
	LOGGER.info("Collection name: %s", runtime_config.collection_name)
	LOGGER.info("Batch size: %d", runtime_config.batch_size)

	records = _prepare_records(_load_embedded_chunks(runtime_config.embedded_chunks_file))
	LOGGER.info("Loaded %d embedded chunks", len(records))

	runtime_config.chroma_dir.mkdir(parents=True, exist_ok=True)
	client = chromadb.PersistentClient(path=str(runtime_config.chroma_dir))
	collection = client.get_or_create_collection(name=runtime_config.collection_name)

	existing_id_set = _existing_ids(collection)
	if existing_id_set:
		LOGGER.info("Detected %d existing chunk ids in collection", len(existing_id_set))

	records_to_write = [record for record in records if record["id"] not in existing_id_set]
	skipped = len(records) - len(records_to_write)
	if skipped:
		LOGGER.info("Skipping %d already-indexed chunks", skipped)

	if not records_to_write:
		LOGGER.info("No new records to index; vector store is already up to date")
		return runtime_config.chroma_dir

	progress = tqdm(total=len(records_to_write), desc="Indexing ChromaDB", unit="chunk", ncols=100)

	try:
		for batch in _chunk_batches(records_to_write, runtime_config.batch_size):
			ids = [item["id"] for item in batch]
			documents = [item["text"] for item in batch]
			metadatas = [item["metadata"] for item in batch]
			embeddings = [item["embedding"] for item in batch]

			try:
				collection.upsert(
					ids=ids,
					documents=documents,
					metadatas=metadatas,
					embeddings=embeddings,
				)
			except Exception as exc:
				LOGGER.exception("Failed to upsert a batch into ChromaDB")
				raise RuntimeError("ChromaDB upsert failed") from exc

			progress.update(len(batch))
	finally:
		progress.close()

	final_count = collection.count()
	LOGGER.info("ChromaDB collection '%s' now contains %d records", runtime_config.collection_name, final_count)
	return runtime_config.chroma_dir


def run(config: Optional[VectorStoreConfig] = None) -> Path:
	"""Compatibility wrapper for pipeline orchestration."""
	return build_vector_store(config=config)


if __name__ == "__main__":
	build_vector_store()
