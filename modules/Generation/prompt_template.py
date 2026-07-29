"""SecureRAG Module 4.1 - Prompt template builder.

Builds a constrained, evidence-grounded prompt for SOC analyst queries.
The template strictly instructs the model to avoid hallucinations and only use
retrieved cybersecurity evidence.

Public API:
    run(
        query: str,
        reranked_response: Any,
        config: PromptTemplateConfig | None = None,
    ) -> PromptBuildResponse

Sample usage:
    from modules.Generation.prompt_template import run

    prompt = run("How should we triage CVE-2021-44228?", reranked_response)
    print(prompt.system_prompt)
    print(prompt.user_prompt)

Expected output shape:
    PromptBuildResponse(
        query="...",
        system_prompt="...",
        user_prompt="...",
        context_chunks=[...],
        context_count=<int>,
    )
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_SYSTEM_PROMPT = (
    "You are SecureRAG.\n"
    "You are an AI Copilot for SOC Analysts.\n"
    "You MUST answer ONLY using the provided context.\n"
    "Never fabricate cybersecurity facts.\n"
    "Always cite CVE IDs exactly.\n"
    "Always include:\n"
    "CVSS\n"
    "EPSS\n"
    "KEV Status\n"
    "MITRE ATT&CK mapping\n"
    "Patch recommendation if available.\n"
    "If information is unavailable,\n"
    "say:\n"
    "'Not found in retrieved evidence.'\n"
    "Never use outside knowledge."
)


@dataclass(slots=True)
class PromptTemplateConfig:
    """Runtime configuration for prompt construction.

    Attributes:
        max_context_chunks: Maximum number of reranked chunks to include.
        max_chunk_chars: Per chunk truncation length.
        max_total_context_chars: Overall context budget for prompt stability.
        include_metadata_fields: Metadata keys to serialize in prompt context.
        system_prompt: Optional override for system prompt text.
    """

    max_context_chunks: int = 5
    max_chunk_chars: int = 1600
    max_total_context_chars: int = 7000
    include_metadata_fields: tuple[str, ...] = (
        "cve_id",
        "cvss",
        "cvss_score",
        "epss",
        "epss_score",
        "kev",
        "kev_flag",
        "technique_id",
        "tactics",
        "source",
    )
    system_prompt: str = DEFAULT_SYSTEM_PROMPT


@dataclass(slots=True)
class PromptContextChunk:
    """Single context chunk embedded into final prompt."""

    rank: int
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PromptBuildResponse:
    """Structured prompt build output for LLM chain."""

    query: str
    system_prompt: str
    user_prompt: str
    context_chunks: List[PromptContextChunk]
    context_count: int
    generated_at_utc: str


def _configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


def _validate_config(config: PromptTemplateConfig) -> None:
    if config.max_context_chunks <= 0:
        raise ValueError("max_context_chunks must be greater than 0")
    if config.max_chunk_chars <= 0:
        raise ValueError("max_chunk_chars must be greater than 0")
    if config.max_total_context_chars <= 0:
        raise ValueError("max_total_context_chars must be greater than 0")
    if not config.system_prompt.strip():
        raise ValueError("system_prompt cannot be empty")


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


def _extract_reranked_items(reranked_response: Any) -> List[PromptContextChunk]:
    raw_items = getattr(reranked_response, "results", None)
    if not isinstance(raw_items, list):
        return []

    chunks: List[PromptContextChunk] = []
    for item in raw_items:
        rank = int(getattr(item, "rank", 0) or 0)
        text = str(getattr(item, "text", ""))
        if not text.strip():
            continue

        chunks.append(
            PromptContextChunk(
                rank=rank if rank > 0 else len(chunks) + 1,
                text=text,
                metadata=_coerce_metadata(getattr(item, "metadata", {})),
            )
        )

    chunks.sort(key=lambda item: item.rank)
    return chunks


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _format_metadata(metadata: Dict[str, Any], fields: tuple[str, ...]) -> str:
    parts: List[str] = []
    for key in fields:
        if key in metadata and metadata.get(key) not in (None, "", [], {}):
            parts.append(f"{key}={metadata.get(key)}")
    return "; ".join(parts) if parts else "No key metadata fields"


def _build_context_section(chunks: List[PromptContextChunk], config: PromptTemplateConfig) -> List[PromptContextChunk]:
    selected = chunks[: config.max_context_chunks]
    final: List[PromptContextChunk] = []
    total_chars = 0

    for chunk in selected:
        truncated_text = _truncate(chunk.text, config.max_chunk_chars)
        metadata_text = _format_metadata(chunk.metadata, config.include_metadata_fields)

        decorated_text = (
            f"[Chunk Rank: {chunk.rank}]\n"
            f"Metadata: {metadata_text}\n"
            f"Content:\n{truncated_text}"
        )

        if total_chars + len(decorated_text) > config.max_total_context_chars:
            remaining = config.max_total_context_chars - total_chars
            if remaining <= 80:
                break
            decorated_text = _truncate(decorated_text, remaining)

        final.append(
            PromptContextChunk(
                rank=chunk.rank,
                text=decorated_text,
                metadata=chunk.metadata,
            )
        )
        total_chars += len(decorated_text)

    return final


def _assemble_user_prompt(query: str, context_chunks: List[PromptContextChunk]) -> str:
    if not context_chunks:
        return (
            "Retrieved Context:\n"
            "Not found in retrieved evidence.\n\n"
            f"Analyst Query:\n{query}\n\n"
            "Instruction:\n"
            "If required fields are unavailable, answer with 'Not found in retrieved evidence.'"
        )

    context_block = "\n\n".join(chunk.text for chunk in context_chunks)
    return (
        "Retrieved Context:\n"
        f"{context_block}\n\n"
        f"Analyst Query:\n{query}\n\n"
        "Required Output Fields:\n"
        "- CVE IDs\n"
        "- CVSS\n"
        "- EPSS\n"
        "- KEV Status\n"
        "- MITRE ATT&CK Mapping\n"
        "- Patch Recommendation\n"
        "If any field is missing from context, output: Not found in retrieved evidence."
    )


def run(
    query: str,
    reranked_response: Any,
    config: PromptTemplateConfig | None = None,
) -> PromptBuildResponse:
    """Build SecureRAG prompt from reranked evidence.

    Args:
        query: Analyst query text.
        reranked_response: Reranker output object.
        config: Optional prompt template settings.

    Returns:
        Structured prompt with system and user sections.
    """
    _configure_logging()
    runtime_config = config or PromptTemplateConfig()
    _validate_config(runtime_config)
    normalized_query = _normalize_query(query)

    raw_chunks = _extract_reranked_items(reranked_response)
    context_chunks = _build_context_section(raw_chunks, runtime_config)
    user_prompt = _assemble_user_prompt(normalized_query, context_chunks)

    response = PromptBuildResponse(
        query=normalized_query,
        system_prompt=runtime_config.system_prompt,
        user_prompt=user_prompt,
        context_chunks=context_chunks,
        context_count=len(context_chunks),
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
    )

    LOGGER.info(
        "Prompt template built | context_chunks=%d query_len=%d",
        response.context_count,
        len(response.query),
    )
    return response


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prompt template runtime validation")
    parser.add_argument("query", type=str, help="Analyst query")
    parser.add_argument("--max-context", type=int, default=5)
    return parser


def _main() -> int:
    parser = _build_cli_parser()
    args = parser.parse_args()

    try:
        from modules.Retrieval import dense_retriever, hybrid_fusion, reranker, sparse_retriever

        dense = dense_retriever.run(args.query)
        sparse = sparse_retriever.run(args.query)
        fused = hybrid_fusion.run(args.query, dense, sparse)
        reranked = reranker.run(args.query, fused)

        prompt = run(
            query=args.query,
            reranked_response=reranked,
            config=PromptTemplateConfig(max_context_chunks=args.max_context),
        )
    except Exception as exc:  # pragma: no cover - CLI surface
        LOGGER.exception("Prompt template build failed")
        print(f"ERROR: {exc}")
        return 1

    print("Prompt build successful")
    print(f"Context chunks included: {prompt.context_count}")
    print("--- SYSTEM ---")
    print(prompt.system_prompt)
    print("--- USER ---")
    print(prompt.user_prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
