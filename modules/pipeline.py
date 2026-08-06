"""SecureRAG Phase 4 Pipeline - End-to-end retrieval, generation, and verification.

Workflow:
    Query
      -> Dense Retrieval
      -> Sparse Retrieval
      -> Hybrid Fusion (RRF)
      -> Cross-Encoder Reranking
      -> Prompt Construction
      -> Mistral via Ollama
      -> Hallucination Guard
      -> Final Verified Answer

Public API:
    run(query: str, config: SecureRAGPipelineConfig | None = None) -> PipelineResponse

Sample usage:
    from modules.pipeline import run

    response = run("How should we prioritize CVE-2021-44228?")
    print(response.final_answer)

Expected output shape:
    PipelineResponse(
        query="...",
        final_answer="...",
        confidence_score=<float>,
        verification_report={...},
        ...
    )
"""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.Generation import llm_chain, prompt_template
from modules.Retrieval import dense_retriever, hybrid_fusion, query_expander, reranker, sparse_retriever
from modules.Verification import hallucination_guard

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(slots=True)
class SecureRAGPipelineConfig:
    """Runtime configuration for full SecureRAG orchestration."""

    dense_config: dense_retriever.DenseRetrieverConfig = field(
        default_factory=dense_retriever.DenseRetrieverConfig
    )
    sparse_config: sparse_retriever.SparseRetrieverConfig = field(
        default_factory=sparse_retriever.SparseRetrieverConfig
    )
    fusion_config: hybrid_fusion.HybridFusionConfig = field(
        default_factory=hybrid_fusion.HybridFusionConfig
    )
    reranker_config: reranker.RerankerConfig = field(default_factory=reranker.RerankerConfig)
    prompt_config: prompt_template.PromptTemplateConfig = field(
        default_factory=prompt_template.PromptTemplateConfig
    )
    llm_config: llm_chain.LLMChainConfig = field(default_factory=llm_chain.LLMChainConfig)
    guard_config: hallucination_guard.HallucinationGuardConfig = field(
        default_factory=hallucination_guard.HallucinationGuardConfig
    )
    require_retrieval_for_generation: bool = False


@dataclass(slots=True)
class PipelineResponse:
    """Structured output from the complete SecureRAG pipeline."""

    query: str
    final_answer: str
    confidence_score: float
    verification_report: Dict[str, Any] = field(default_factory=dict)
    claim_reports: List[Dict[str, Any]] = field(default_factory=list)
    dense_results_count: int = 0
    sparse_results_count: int = 0
    fused_results_count: int = 0
    reranked_results_count: int = 0
    llm_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    generated_at_utc: str = ""
    diagnostics: Dict[str, Any] = field(default_factory=dict)


def _configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


def _normalize_query(query: str) -> str:
    normalized = query.strip()
    if not normalized:
        raise ValueError("Query cannot be empty")
    return normalized


def _claim_report_to_dict(report: hallucination_guard.ClaimReport) -> Dict[str, Any]:
    return {
        "claim_id": report.claim_id,
        "claim_text": report.claim_text,
        "status": report.status,
        "support_score": report.support_score,
        "matched_evidence_indices": report.matched_evidence_indices,
        "rationale": report.rationale,
    }


def _safe_stage(stage_name: str, func: Any, diagnostics: Dict[str, Any], *args: Any, **kwargs: Any) -> Any:
    try:
        return func(*args, **kwargs)
    except Exception as exc:
        LOGGER.exception("Pipeline stage failed: %s", stage_name)
        diagnostics[stage_name] = str(exc)
        return None


def _fallback_answer_for_no_retrieval() -> str:
    return "Not found in retrieved evidence."


def run(query: str, config: SecureRAGPipelineConfig | None = None) -> PipelineResponse:
    """Run end-to-end SecureRAG pipeline.

    Args:
        query: Analyst query.
        config: Optional configuration for each stage.

    Returns:
        Fully verified answer with stage diagnostics.
    """
    _configure_logging()
    runtime_config = config or SecureRAGPipelineConfig()
    normalized_query = _normalize_query(query)
    started = time.perf_counter()

    diagnostics: Dict[str, Any] = {}

    expanded_queries = query_expander.expand_query(normalized_query)
    retrieval_query_text = " ".join(expanded_queries)
    if len(expanded_queries) > 1:
        LOGGER.info("Query expanded from '%s' to: %s", normalized_query, expanded_queries)
        diagnostics["expanded_queries"] = expanded_queries

    dense_response = _safe_stage(
        "dense_retrieval",
        dense_retriever.run,
        diagnostics,
        retrieval_query_text,
        runtime_config.dense_config,
    )

    sparse_response = _safe_stage(
        "sparse_retrieval",
        sparse_retriever.run,
        diagnostics,
        retrieval_query_text,
        runtime_config.sparse_config,
    )

    if dense_response is None and sparse_response is None:
        final_answer = _fallback_answer_for_no_retrieval()
        total_latency_ms = (time.perf_counter() - started) * 1000.0
        return PipelineResponse(
            query=normalized_query,
            final_answer=final_answer,
            confidence_score=0.0,
            verification_report={
                "total_claims": 1,
                "verified": 0,
                "partially_verified": 0,
                "unsupported": 1,
                "confidence_score": 0.0,
            },
            claim_reports=[],
            total_latency_ms=total_latency_ms,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            diagnostics=diagnostics,
        )

    if dense_response is None:
        dense_response = dense_retriever.DenseRetrievalResponse(
            query=normalized_query,
            collection_name=runtime_config.dense_config.collection_name,
            embedding_model=runtime_config.dense_config.embedding_model,
            top_k_requested=runtime_config.dense_config.top_k,
            total_results=0,
            latency_ms=0.0,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            results=[],
        )

    if sparse_response is None:
        sparse_response = sparse_retriever.SparseRetrievalResponse(
            query=normalized_query,
            top_k_requested=runtime_config.sparse_config.top_k,
            total_results=0,
            latency_ms=0.0,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            results=[],
        )

    fused_response = _safe_stage(
        "hybrid_fusion",
        hybrid_fusion.run,
        diagnostics,
        normalized_query,
        dense_response,
        sparse_response,
        runtime_config.fusion_config,
    )

    if fused_response is None:
        fused_response = hybrid_fusion.HybridFusionResponse(
            query=normalized_query,
            rrf_k=runtime_config.fusion_config.rrf_k,
            top_k_requested=runtime_config.fusion_config.top_k,
            total_results=0,
            latency_ms=0.0,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            results=[],
        )

    reranked_response = _safe_stage(
        "reranker",
        reranker.run,
        diagnostics,
        normalized_query,
        fused_response,
        runtime_config.reranker_config,
    )

    if reranked_response is None:
        reranked_response = reranker.RerankerResponse(
            query=normalized_query,
            model_name=runtime_config.reranker_config.model_name,
            top_k_requested=runtime_config.reranker_config.top_k,
            total_results=0,
            latency_ms=0.0,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            results=[],
        )

    if runtime_config.require_retrieval_for_generation and reranked_response.total_results == 0:
        guarded_answer = _fallback_answer_for_no_retrieval()
        total_latency_ms = (time.perf_counter() - started) * 1000.0
        return PipelineResponse(
            query=normalized_query,
            final_answer=guarded_answer,
            confidence_score=0.0,
            verification_report={
                "total_claims": 1,
                "verified": 0,
                "partially_verified": 0,
                "unsupported": 1,
                "confidence_score": 0.0,
            },
            claim_reports=[],
            dense_results_count=dense_response.total_results,
            sparse_results_count=sparse_response.total_results,
            fused_results_count=fused_response.total_results,
            reranked_results_count=reranked_response.total_results,
            total_latency_ms=total_latency_ms,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            diagnostics={**diagnostics, "generation_skipped": "no_retrieval_results"},
        )

    prompt_response = _safe_stage(
        "prompt_template",
        prompt_template.run,
        diagnostics,
        normalized_query,
        reranked_response,
        runtime_config.prompt_config,
    )

    if prompt_response is None:
        prompt_response = prompt_template.PromptBuildResponse(
            query=normalized_query,
            system_prompt=runtime_config.prompt_config.system_prompt,
            user_prompt=(
                "Retrieved Context:\nNot found in retrieved evidence.\n\n"
                f"Analyst Query:\n{normalized_query}"
            ),
            context_chunks=[],
            context_count=0,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
        )

    llm_response = _safe_stage(
        "llm_chain",
        llm_chain.run,
        diagnostics,
        prompt_response,
        runtime_config.llm_config,
    )

    if llm_response is None:
        llm_response = llm_chain.LLMChainResponse(
            model=runtime_config.llm_config.model,
            answer=(
                "Not found in retrieved evidence. "
                "LLM generation failed and fallback answer was applied."
            ),
            token_usage={},
            latency_ms=0.0,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            raw_response={"error": "llm_chain stage failed"},
        )

    guard_response = _safe_stage(
        "hallucination_guard",
        hallucination_guard.run,
        diagnostics,
        llm_response.answer,
        reranked_response,
        runtime_config.guard_config,
    )

    if guard_response is None:
        guard_response = hallucination_guard.HallucinationGuardResponse(
            original_answer=llm_response.answer,
            verified_answer="Not found in retrieved evidence.",
            confidence_score=0.0,
            claim_reports=[],
            verification_summary={
                "total_claims": 0,
                "verified": 0,
                "partially_verified": 0,
                "unsupported": 0,
                "confidence_score": 0.0,
            },
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
        )

    total_latency_ms = (time.perf_counter() - started) * 1000.0
    response = PipelineResponse(
        query=normalized_query,
        final_answer=guard_response.verified_answer,
        confidence_score=guard_response.confidence_score,
        verification_report=guard_response.verification_summary,
        claim_reports=[_claim_report_to_dict(report) for report in guard_response.claim_reports],
        dense_results_count=dense_response.total_results,
        sparse_results_count=sparse_response.total_results,
        fused_results_count=fused_response.total_results,
        reranked_results_count=reranked_response.total_results,
        llm_latency_ms=llm_response.latency_ms,
        total_latency_ms=total_latency_ms,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        diagnostics=diagnostics,
    )

    LOGGER.info(
        "SecureRAG pipeline completed | dense=%d sparse=%d fused=%d reranked=%d confidence=%.4f total_latency_ms=%.2f",
        response.dense_results_count,
        response.sparse_results_count,
        response.fused_results_count,
        response.reranked_results_count,
        response.confidence_score,
        response.total_latency_ms,
    )
    return response


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SecureRAG end-to-end pipeline")
    parser.add_argument("query", type=str, help="SOC analyst query")
    parser.add_argument("--top-k-dense", type=int, default=10)
    parser.add_argument("--top-k-sparse", type=int, default=10)
    parser.add_argument("--top-k-fused", type=int, default=15)
    parser.add_argument("--top-k-rerank", type=int, default=5)
    parser.add_argument("--llm-model", type=str, default="mistral")
    return parser


def _main() -> int:
    parser = _build_cli_parser()
    args = parser.parse_args()

    config = SecureRAGPipelineConfig(
        dense_config=dense_retriever.DenseRetrieverConfig(top_k=args.top_k_dense),
        sparse_config=sparse_retriever.SparseRetrieverConfig(top_k=args.top_k_sparse),
        fusion_config=hybrid_fusion.HybridFusionConfig(top_k=args.top_k_fused),
        reranker_config=reranker.RerankerConfig(top_k=args.top_k_rerank),
        llm_config=llm_chain.LLMChainConfig(model=args.llm_model),
    )

    try:
        response = run(args.query, config=config)
    except Exception as exc:  # pragma: no cover - CLI surface
        LOGGER.exception("Pipeline execution failed")
        print(f"ERROR: {exc}")
        return 1

    print("SecureRAG pipeline successful")
    print(f"Query: {response.query}")
    print(f"Final confidence: {response.confidence_score}")
    print(f"Total latency (ms): {response.total_latency_ms:.2f}")
    print("Final verified answer:")
    print(response.final_answer)
    print("Verification summary:")
    print(response.verification_report)

    if response.diagnostics:
        print("Diagnostics:")
        print(response.diagnostics)

    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
