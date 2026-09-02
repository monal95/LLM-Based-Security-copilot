"""SecureRAG Module 4.2 - Ollama LLM chain for grounded generation.

This module invokes Mistral via Ollama chat API using the prompt package
built by prompt_template.py.

Public API:
    run(
        prompt_response: Any,
        config: LLMChainConfig | None = None,
    ) -> LLMChainResponse

Sample usage:
    from modules.Generation.llm_chain import run

    llm = run(prompt_response)
    print(llm.answer)

Expected output shape:
    LLMChainResponse(
        answer="...",
        token_usage={...},
        latency_ms=<float>,
    )
"""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class LLMChainConfig:
    """Runtime configuration for Ollama generation.

    Attributes:
        model: Ollama model name.
        temperature: Sampling temperature.
        top_p: Nucleus sampling parameter.
        max_tokens: Max generated tokens.
        timeout_seconds: Request timeout passed to Ollama client.
        host: Optional Ollama host override.
    """

    model: str = "mistral"
    temperature: float = 0.1
    top_p: float = 0.9
    max_tokens: int = 900
    timeout_seconds: float = 60.0
    host: Optional[str] = None


@dataclass(slots=True)
class LLMChainResponse:
    """Structured output for the LLM generation stage."""

    model: str
    answer: str
    token_usage: Dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    generated_at_utc: str = ""
    raw_response: Dict[str, Any] = field(default_factory=dict)


def _configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


def _validate_config(config: LLMChainConfig) -> None:
    if not config.model.strip():
        raise ValueError("model cannot be empty")
    if not (0.0 <= config.temperature <= 2.0):
        raise ValueError("temperature must be within [0.0, 2.0]")
    if not (0.0 < config.top_p <= 1.0):
        raise ValueError("top_p must be within (0.0, 1.0]")
    if config.max_tokens <= 0:
        raise ValueError("max_tokens must be greater than 0")
    if config.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than 0")


def _extract_prompt(prompt_response: Any) -> tuple[str, str]:
    system_prompt = str(getattr(prompt_response, "system_prompt", "")).strip()
    user_prompt = str(getattr(prompt_response, "user_prompt", "")).strip()
    if not system_prompt:
        raise ValueError("Missing system_prompt in prompt response")
    if not user_prompt:
        raise ValueError("Missing user_prompt in prompt response")
    return system_prompt, user_prompt


def _extract_usage(payload: Dict[str, Any]) -> Dict[str, int]:
    usage: Dict[str, int] = {}
    for key in ("prompt_eval_count", "eval_count", "total_duration", "load_duration"):
        value = payload.get(key)
        if isinstance(value, (int, float)):
            usage[key] = int(value)
    return usage


def _fallback_answer() -> str:
    return (
        "Not found in retrieved evidence. "
        "LLM generation is temporarily unavailable; please verify retrieved context and retry."
    )


def _fallback_response(model: str, reason: str) -> LLMChainResponse:
    return LLMChainResponse(
        model=model,
        answer=_fallback_answer(),
        token_usage={},
        latency_ms=0.0,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        raw_response={"error": reason},
    )


def run(prompt_response: Any, config: LLMChainConfig | None = None) -> LLMChainResponse:
    """Generate a grounded response via Ollama chat.

    Args:
        prompt_response: Output from prompt_template.run().
        config: Optional LLM runtime settings.

    Returns:
        Generated answer with usage and latency metadata.
    """
    _configure_logging()
    runtime_config = config or LLMChainConfig()
    _validate_config(runtime_config)

    system_prompt, user_prompt = _extract_prompt(prompt_response)

    try:
        import ollama  # type: ignore
    except ImportError as exc:
        LOGGER.warning("Ollama package unavailable; returning fallback answer")
        return _fallback_response(runtime_config.model, f"ollama import failed: {exc}")

    options: Dict[str, Any] = {
        "temperature": runtime_config.temperature,
        "top_p": runtime_config.top_p,
        "num_predict": runtime_config.max_tokens,
    }

    client_kwargs: Dict[str, Any] = {
        "timeout": runtime_config.timeout_seconds,
    }
    if runtime_config.host:
        client_kwargs["host"] = runtime_config.host

    started = time.perf_counter()
    try:
        client = ollama.Client(**client_kwargs)
        LOGGER.info(
            "Calling Ollama | model=%s timeout=%.0fs",
            runtime_config.model,
            runtime_config.timeout_seconds,
        )
        payload = client.chat(
            model=runtime_config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            options=options,
            keep_alive="10m",
        )
        latency_ms = (time.perf_counter() - started) * 1000.0

        message = payload.get("message", {}) if isinstance(payload, dict) else {}
        answer = str(message.get("content", "")).strip()
        if not answer:
            answer = _fallback_answer()

        response = LLMChainResponse(
            model=runtime_config.model,
            answer=answer,
            token_usage=_extract_usage(payload if isinstance(payload, dict) else {}),
            latency_ms=latency_ms,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            raw_response=payload if isinstance(payload, dict) else {"raw": str(payload)},
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        LOGGER.exception("Ollama generation failed; returning guarded fallback answer")
        response = LLMChainResponse(
            model=runtime_config.model,
            answer=_fallback_answer(),
            token_usage={},
            latency_ms=latency_ms,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            raw_response={"error": str(exc)},
        )

    LOGGER.info(
        "LLM chain completed | model=%s latency_ms=%.2f answer_chars=%d",
        response.model,
        response.latency_ms,
        len(response.answer),
    )
    return response


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LLM chain runtime validation")
    parser.add_argument("query", type=str, help="Analyst query")
    parser.add_argument("--model", type=str, default="mistral")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--max-tokens", type=int, default=900)
    return parser


def _main() -> int:
    parser = _build_cli_parser()
    args = parser.parse_args()

    try:
        from modules.Generation import prompt_template
        from modules.Retrieval import dense_retriever, hybrid_fusion, reranker, sparse_retriever

        dense = dense_retriever.run(args.query)
        sparse = sparse_retriever.run(args.query)
        fused = hybrid_fusion.run(args.query, dense, sparse)
        reranked = reranker.run(args.query, fused)
        prompt = prompt_template.run(args.query, reranked)

        response = run(
            prompt,
            config=LLMChainConfig(
                model=args.model,
                temperature=args.temperature,
                top_p=args.top_p,
                max_tokens=args.max_tokens,
            ),
        )
    except Exception as exc:  # pragma: no cover - CLI surface
        LOGGER.exception("LLM chain failed")
        print(f"ERROR: {exc}")
        return 1

    print("LLM chain successful")
    print(f"Model: {response.model}")
    print(f"Latency (ms): {response.latency_ms:.2f}")
    print("Answer:")
    print(response.answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
