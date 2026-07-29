"""SecureRAG Module 4.3 - Hallucination guard and factual claim verification.

This module verifies LLM-generated claims against retrieved evidence and produces
an evidence-constrained final answer.

Public API:
    run(
        llm_answer: str,
        retrieval_context: Any,
        config: HallucinationGuardConfig | None = None,
    ) -> HallucinationGuardResponse

Sample usage:
    from modules.Verification.hallucination_guard import run

    verified = run(llm_answer, reranker_response)
    print(verified.verified_answer)

Expected output shape:
    HallucinationGuardResponse(
        verified_answer="...",
        confidence_score=<float>,
        claim_reports=[...],
        verification_summary={...},
    )
"""

from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

UNSUPPORTED_SENTENCE = "Not verified by retrieved evidence."


@dataclass(slots=True)
class HallucinationGuardConfig:
    """Runtime configuration for claim verification.

    Attributes:
        unsupported_policy: Action for unsupported claims: "replace" or "remove".
        min_tokens_per_claim: Minimum token count to treat segment as claim.
        verified_threshold: Overlap threshold for "Verified".
        partial_threshold: Overlap threshold for "Partially Verified".
        max_claims: Safety cap on number of claims processed.
    """

    unsupported_policy: str = "replace"
    min_tokens_per_claim: int = 4
    verified_threshold: float = 0.55
    partial_threshold: float = 0.30
    max_claims: int = 40


@dataclass(slots=True)
class ClaimReport:
    """Per-claim verification report."""

    claim_id: int
    claim_text: str
    status: str
    support_score: float
    matched_evidence_indices: List[int] = field(default_factory=list)
    rationale: str = ""


@dataclass(slots=True)
class HallucinationGuardResponse:
    """Final verified output and claim-level diagnostics."""

    original_answer: str
    verified_answer: str
    confidence_score: float
    claim_reports: List[ClaimReport]
    verification_summary: Dict[str, Any] = field(default_factory=dict)
    generated_at_utc: str = ""


def _configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )


def _validate_config(config: HallucinationGuardConfig) -> None:
    if config.unsupported_policy not in {"replace", "remove"}:
        raise ValueError("unsupported_policy must be 'replace' or 'remove'")
    if config.min_tokens_per_claim <= 0:
        raise ValueError("min_tokens_per_claim must be > 0")
    if not (0.0 <= config.partial_threshold <= config.verified_threshold <= 1.0):
        raise ValueError("Thresholds must satisfy 0 <= partial <= verified <= 1")
    if config.max_claims <= 0:
        raise ValueError("max_claims must be > 0")


def _normalize_answer(answer: str) -> str:
    normalized = answer.strip()
    if not normalized:
        raise ValueError("LLM answer cannot be empty")
    return normalized


def _extract_evidence_texts(retrieval_context: Any) -> List[str]:
    raw_results = getattr(retrieval_context, "results", None)
    if not isinstance(raw_results, list):
        return []

    evidence: List[str] = []
    for item in raw_results:
        candidate = getattr(item, "text", None)
        if candidate is None:
            candidate = getattr(item, "document", "")
        text = str(candidate)
        if text.strip():
            evidence.append(text)
    return evidence


def _split_claims(answer: str, min_tokens: int, max_claims: int) -> List[str]:
    rough_segments = re.split(r"(?<=[.!?])\s+|\n+", answer)
    claims: List[str] = []

    for segment in rough_segments:
        normalized = segment.strip(" -\t\r\n")
        if not normalized:
            continue

        token_count = len(re.findall(r"[A-Za-z0-9_-]+", normalized))
        if token_count >= min_tokens:
            claims.append(normalized)

        if len(claims) >= max_claims:
            break

    if not claims:
        claims = [answer.strip()]
    return claims


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", text.lower()))


def _extract_cve_ids(text: str) -> set[str]:
    return {match.upper() for match in re.findall(r"CVE-\d{4}-\d{4,7}", text, flags=re.IGNORECASE)}


def _claim_support_score(claim: str, evidence: str) -> float:
    claim_tokens = _tokenize(claim)
    if not claim_tokens:
        return 0.0

    evidence_tokens = _tokenize(evidence)
    overlap = len(claim_tokens & evidence_tokens) / max(1, len(claim_tokens))

    claim_cves = _extract_cve_ids(claim)
    evidence_cves = _extract_cve_ids(evidence)
    cve_bonus = 0.20 if claim_cves and (claim_cves & evidence_cves) else 0.0

    return min(1.0, overlap + cve_bonus)


def _classify_claim(
    claim: str,
    evidence_texts: Sequence[str],
    config: HallucinationGuardConfig,
) -> ClaimReport:
    best_score = 0.0
    matched_indices: List[int] = []

    for idx, evidence in enumerate(evidence_texts):
        score = _claim_support_score(claim, evidence)
        if score > best_score:
            best_score = score
            matched_indices = [idx]
        elif abs(score - best_score) <= 1e-9 and score > 0.0:
            matched_indices.append(idx)

    claim_cves = _extract_cve_ids(claim)
    cve_supported = False
    if claim_cves:
        evidence_cves_union: set[str] = set()
        for evidence in evidence_texts:
            evidence_cves_union.update(_extract_cve_ids(evidence))
        cve_supported = bool(claim_cves & evidence_cves_union)

    if best_score >= config.verified_threshold and (not claim_cves or cve_supported):
        status = "Verified"
        rationale = "Strong lexical/evidence overlap with retrieved context."
    elif best_score >= config.partial_threshold or cve_supported:
        status = "Partially Verified"
        rationale = "Partial overlap or partial entity support in retrieved context."
    else:
        status = "Unsupported"
        rationale = "No adequate evidence support found in retrieved context."

    return ClaimReport(
        claim_id=0,
        claim_text=claim,
        status=status,
        support_score=best_score,
        matched_evidence_indices=matched_indices,
        rationale=rationale,
    )


def _render_verified_answer(
    claims: Sequence[ClaimReport],
    policy: str,
) -> str:
    lines: List[str] = []
    for claim in claims:
        if claim.status == "Unsupported":
            if policy == "replace":
                lines.append(UNSUPPORTED_SENTENCE)
            continue
        lines.append(claim.claim_text)

    if not lines:
        return "Not found in retrieved evidence."

    return "\n".join(lines)


def _confidence(claims: Sequence[ClaimReport]) -> float:
    if not claims:
        return 0.0

    points = 0.0
    for claim in claims:
        if claim.status == "Verified":
            points += 1.0
        elif claim.status == "Partially Verified":
            points += 0.5

    return round(points / len(claims), 4)


def _summary(claims: Sequence[ClaimReport], confidence: float) -> Dict[str, Any]:
    verified = sum(1 for claim in claims if claim.status == "Verified")
    partial = sum(1 for claim in claims if claim.status == "Partially Verified")
    unsupported = sum(1 for claim in claims if claim.status == "Unsupported")

    return {
        "total_claims": len(claims),
        "verified": verified,
        "partially_verified": partial,
        "unsupported": unsupported,
        "confidence_score": confidence,
    }


def run(
    llm_answer: str,
    retrieval_context: Any,
    config: HallucinationGuardConfig | None = None,
) -> HallucinationGuardResponse:
    """Verify generated claims against retrieved evidence context.

    Args:
        llm_answer: Raw generated answer from LLM stage.
        retrieval_context: Typically reranker output containing top evidence texts.
        config: Optional guard settings.

    Returns:
        Evidence-verified final answer and claim-level diagnostics.
    """
    _configure_logging()
    runtime_config = config or HallucinationGuardConfig()
    _validate_config(runtime_config)
    normalized_answer = _normalize_answer(llm_answer)

    evidence_texts = _extract_evidence_texts(retrieval_context)
    claims_raw = _split_claims(
        normalized_answer,
        min_tokens=runtime_config.min_tokens_per_claim,
        max_claims=runtime_config.max_claims,
    )

    reports: List[ClaimReport] = []
    for idx, claim in enumerate(claims_raw, start=1):
        report = _classify_claim(claim=claim, evidence_texts=evidence_texts, config=runtime_config)
        report.claim_id = idx
        reports.append(report)

    verified_answer = _render_verified_answer(reports, runtime_config.unsupported_policy)
    confidence = _confidence(reports)

    response = HallucinationGuardResponse(
        original_answer=normalized_answer,
        verified_answer=verified_answer,
        confidence_score=confidence,
        claim_reports=reports,
        verification_summary=_summary(reports, confidence),
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
    )

    LOGGER.info(
        "Hallucination guard completed | claims=%d confidence=%.4f",
        len(reports),
        response.confidence_score,
    )
    return response


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hallucination guard runtime validation")
    parser.add_argument("query", type=str, help="Analyst query")
    parser.add_argument("--unsupported-policy", choices=["replace", "remove"], default="replace")
    return parser


def _main() -> int:
    parser = _build_cli_parser()
    args = parser.parse_args()

    try:
        from modules.Generation import llm_chain, prompt_template
        from modules.Retrieval import dense_retriever, hybrid_fusion, reranker, sparse_retriever

        dense = dense_retriever.run(args.query)
        sparse = sparse_retriever.run(args.query)
        fused = hybrid_fusion.run(args.query, dense, sparse)
        reranked = reranker.run(args.query, fused)
        prompt = prompt_template.run(args.query, reranked)
        generated = llm_chain.run(prompt)

        verified = run(
            llm_answer=generated.answer,
            retrieval_context=reranked,
            config=HallucinationGuardConfig(unsupported_policy=args.unsupported_policy),
        )
    except Exception as exc:  # pragma: no cover - CLI surface
        LOGGER.exception("Hallucination guard failed")
        print(f"ERROR: {exc}")
        return 1

    print("Hallucination guard successful")
    print(f"Confidence score: {verified.confidence_score}")
    print("Verified answer:")
    print(verified.verified_answer)
    print("Verification summary:")
    print(verified.verification_summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
