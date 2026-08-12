"""SecureRAG Phase 5 incident response runbook generator.

This module retrieves incident-specific evidence chunks and asks the local
Mistral model to synthesize a structured, NIST CSF 2.0 aligned runbook.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence

from modules.retriever import retrieve

LOGGER = logging.getLogger(__name__)
INCIDENT_TYPES = ["ransomware", "phishing", "data_breach", "supply_chain"]
DEFAULT_MODEL = "mistral"


def _configure_logging() -> None:
    """Configure default logging when the host application has not set handlers."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


def _validate_incident_type(incident_type: str) -> str:
    """Validate incident type input against the supported list."""
    normalized = incident_type.strip().lower()
    if not normalized:
        raise ValueError("incident_type cannot be empty")
    if normalized not in INCIDENT_TYPES:
        raise ValueError(f"incident_type must be one of: {', '.join(INCIDENT_TYPES)}")
    return normalized


def _call_ollama(model: str, system_prompt: str, user_prompt: str) -> str:
    """Call Ollama and return the assistant response text."""
    try:
        import ollama  # type: ignore
    except ImportError as exc:
        raise ImportError("ollama package is required for runbook generation") from exc

    try:
        payload = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as exc:
        raise RuntimeError(f"Ollama chat failed for model '{model}'") from exc

    if not isinstance(payload, dict):
        return str(payload).strip()

    message = payload.get("message", {})
    if isinstance(message, dict):
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip()
    return ""


def _collect_context_chunks(incident_type: str) -> List[Dict[str, Any]]:
    """Retrieve the top chunks relevant to the incident type."""
    query = f"{incident_type} incident response containment eradication recovery evidence notification"
    results = retrieve(query, top_k=5)
    normalized: List[Dict[str, Any]] = []
    for item in results:
        if isinstance(item, dict):
            normalized.append(item)
    return normalized[:5]


def _format_chunks_for_prompt(chunks: Sequence[Dict[str, Any]]) -> str:
    """Convert retrieved chunks into a prompt-ready context block."""
    lines: List[str] = []
    for index, chunk in enumerate(chunks, start=1):
        text = str(chunk.get("text", chunk.get("document", ""))).strip()
        metadata = chunk.get("metadata", {})
        source_name = "unknown"
        if isinstance(metadata, dict):
            source_name = str(metadata.get("source", metadata.get("document_type", source_name)))
        lines.append(f"[{index}] Source: {source_name}\n{text}")
    return "\n\n".join(lines)


def _extract_phase_items(text: str) -> Dict[str, List[str]]:
    """Parse the LLM response into the five required runbook phases."""
    phase_map = {
        "containment": [],
        "eradication": [],
        "recovery": [],
        "evidence": [],
        "notification": [],
    }
    current_phase: str | None = None

    phase_aliases = {
        "containment": "containment",
        "eradication": "eradication",
        "recovery": "recovery",
        "evidence preservation": "evidence",
        "evidence": "evidence",
        "notification": "notification",
    }

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        heading = re.sub(r"^[0-9]+[.)]\s*", "", line).strip().lower()
        heading = heading.rstrip(":")
        if heading in phase_aliases:
            current_phase = phase_aliases[heading]
            continue

        if current_phase is None:
            continue

        cleaned = re.sub(r"^[-*•]\s*", "", line).strip()
        cleaned = re.sub(r"^[0-9]+[.)]\s*", "", cleaned).strip()
        if cleaned:
            phase_map[current_phase].append(cleaned)

    for key, items in phase_map.items():
        if not items:
            phase_map[key] = [f"No structured {key} steps were returned by the model."]
    return phase_map


def generate_runbook(incident_type: str) -> dict:
    """Generate a structured incident response runbook for one incident type.

    Args:
        incident_type: One of the supported incident categories.

    Returns:
        A dictionary containing the incident type, five structured phases, context sources,
        and a generation timestamp.
    """
    _configure_logging()
    normalized_type = _validate_incident_type(incident_type)
    LOGGER.info("Generating runbook for incident type: %s", normalized_type)
    print(f"Retrieving context for {normalized_type}...")

    chunks = _collect_context_chunks(normalized_type)
    context_block = _format_chunks_for_prompt(chunks)
    context_sources = []
    for index, chunk in enumerate(chunks, start=1):
        context_sources.append(
            {
                "rank": index,
                "chunk_id": chunk.get("chunk_id") or chunk.get("id"),
                "source": (chunk.get("metadata") or {}).get("source") if isinstance(chunk.get("metadata"), dict) else None,
            }
        )

    system_prompt = (
        "You are a NIST CSF 2.0 aligned incident response specialist. "
        "Generate a structured playbook using ONLY the provided context. Structure your response in exactly 5 phases."
    )
    user_prompt = (
        f"Incident type: {normalized_type}\n\n"
        f"Context:\n{context_block}\n\n"
        "Generate a complete incident response runbook with these 5 phases:\n"
        "1. CONTAINMENT — Immediate actions to stop spread\n"
        "2. ERADICATION — Remove threat from all affected systems\n"
        "3. RECOVERY — Restore systems to normal operation\n"
        "4. EVIDENCE PRESERVATION — Preserve forensic artifacts\n"
        "5. NOTIFICATION — Who to notify and in what order (NIST CSF 2.0 aligned)\n\n"
        "For each phase, provide 4-6 specific, actionable steps."
    )

    print("Calling Mistral via Ollama for runbook generation...")
    response_text = _call_ollama(DEFAULT_MODEL, system_prompt, user_prompt)
    phases = _extract_phase_items(response_text)

    return {
        "incident_type": normalized_type,
        "phases": phases,
        "context_sources": context_sources,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    """Manual smoke-test entrypoint."""
    runbook = generate_runbook("ransomware")
    print(runbook)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())