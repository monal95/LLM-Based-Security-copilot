"""FastAPI Backend entrypoint for SecureRAG.

Orchestrates existing SecureRAG core modules:
  - modules.pipeline (End-to-end RAG answer generation & verification)
  - modules.retriever (Evidence retrieval wrapper)
  - modules.priority_scorer (CVE CVSS/EPSS/KEV priority ranking)
  - modules.runbook_generator (NIST CSF 2.0 IR runbooks)
  - modules.patch_explainer (Patch priority explanations)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from backend import warmup
from modules import patch_explainer, pipeline, priority_scorer, retriever, runbook_generator

LOGGER = logging.getLogger("secure_rag.backend")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

app = FastAPI(
    title="SecureRAG API Backend",
    description="Hallucination-Safe AI Copilot for Threat Intelligence and Vulnerability Prioritization",
    version="1.0.0",
)

# Phase 10 - CORS Security Configuration
origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Set SECURERAG_SKIP_WARMUP=1 to keep startup lazy (useful for CLI-style runs
# that only touch the metadata endpoints).
SKIP_WARMUP = os.getenv("SECURERAG_SKIP_WARMUP", "").strip().lower() in {"1", "true", "yes"}


@app.on_event("startup")
def preload_retrieval_stack() -> None:
    """Load models and indexes once, off the request path.

    Runs on a background thread so the server accepts connections immediately;
    /api/health reports progress while it completes.
    """
    if SKIP_WARMUP:
        LOGGER.info("Warmup skipped (SECURERAG_SKIP_WARMUP set); components load on first query")
        return
    warmup.start_background_warmup()


# Request Models
class ChatRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000, example="What is CVE-2021-44228?")
    top_k_dense: int = Field(10, ge=1, le=50)
    top_k_sparse: int = Field(10, ge=1, le=50)
    top_k_fused: int = Field(15, ge=1, le=50)
    top_k_rerank: int = Field(5, ge=1, le=20)


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000, example="ransomware containment and recovery")
    top_k: int = Field(5, ge=1, le=30)


class PriorityRequest(BaseModel):
    cve_ids: List[str] = Field(..., min_items=1, max_items=100, example=["CVE-2021-44228", "CVE-2022-26134", "CVE-2023-44487"])
    explain: bool = Field(True)


@app.get("/api/health")
def get_health() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "service": "SecureRAG API",
        "version": "1.0.0",
        "models": {
            "embedding": "sentence-transformers/all-MiniLM-L6-v2",
            "reranker": "cross-encoder/ms-marco-MiniLM-L-6-v2",
            "llm": "mistral (via Ollama)",
        },
        "database": "ChromaDB + BM25",
        # Real measurements recorded during startup warmup, not estimates.
        "warmup": warmup.get_state(),
    }


@app.post("/api/chat")
def post_chat(req: ChatRequest) -> Dict[str, Any]:
    try:
        cfg = pipeline.SecureRAGPipelineConfig(
            dense_config=pipeline.dense_retriever.DenseRetrieverConfig(top_k=req.top_k_dense),
            sparse_config=pipeline.sparse_retriever.SparseRetrieverConfig(top_k=req.top_k_sparse),
            fusion_config=pipeline.hybrid_fusion.HybridFusionConfig(top_k=req.top_k_fused),
            reranker_config=pipeline.reranker.RerankerConfig(top_k=req.top_k_rerank),
        )
        res = pipeline.run(req.query, config=cfg)
        return {
            "query": res.query,
            "final_answer": res.final_answer,
            "confidence_score": res.confidence_score,
            "verification_report": res.verification_report,
            "claim_reports": res.claim_reports,
            "counts": {
                "dense": res.dense_results_count,
                "sparse": res.sparse_results_count,
                "fused": res.fused_results_count,
                "reranked": res.reranked_results_count,
            },
            "total_latency_ms": res.total_latency_ms,
            "stage_timings_ms": res.diagnostics.get("stage_timings_ms", {}),
            "warm": warmup.is_ready(),
            "generated_at_utc": res.generated_at_utc,
        }
    except Exception as exc:
        LOGGER.exception("Chat API execution failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/retrieve")
def post_retrieve(req: RetrieveRequest) -> Dict[str, Any]:
    try:
        started = time.perf_counter()
        results = retriever.retrieve(req.query, top_k=req.top_k)
        latency_ms = round((time.perf_counter() - started) * 1000.0, 2)

        LOGGER.info(
            "Retrieve completed | top_k=%d results=%d latency_ms=%.2f warm=%s",
            req.top_k,
            len(results),
            latency_ms,
            warmup.is_ready(),
        )
        return {
            "query": req.query,
            "top_k": req.top_k,
            "total_results": len(results),
            "latency_ms": latency_ms,
            "warm": warmup.is_ready(),
            "results": results,
        }
    except Exception as exc:
        LOGGER.exception("Retrieve API execution failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/cve/{cve_id}")
def get_cve_details(cve_id: str) -> Dict[str, Any]:
    clean_id = cve_id.strip().upper()
    if not clean_id.startswith("CVE-"):
        raise HTTPException(status_code=400, detail="Invalid CVE ID format. Must start with 'CVE-'")

    scored = priority_scorer.score_cve(clean_id, priority_scorer.WEIGHTS_MAIN)

    # Enrich with description from NVD/KEV if available
    nvd_rec = priority_scorer._get_nvd_index().get(clean_id, {})
    epss_rec = priority_scorer._get_epss_index().get(clean_id, {})
    kev_set = priority_scorer._get_kev_index()

    return {
        "cve_id": clean_id,
        "cvss_score": scored["cvss_score"],
        "epss_score": scored["epss_score"],
        "epss_percentile": float(epss_rec.get("percentile", 0.0) or 0.0) if epss_rec else 0.0,
        "kev_flag": scored["kev_flag"] == 1,
        "priority_score": scored["priority_score"],
        "description": nvd_rec.get("description", "No description available in local database."),
        "published_date": nvd_rec.get("published_date", "Unknown"),
        "severity": nvd_rec.get("severity", "MEDIUM"),
        "affected_products": nvd_rec.get("affected_products", []),
    }


@app.get("/api/mitre/{technique_id}")
def get_mitre_details(technique_id: str) -> Dict[str, Any]:
    clean_id = technique_id.strip().upper()
    mitre_path = PROJECT_ROOT / "data" / "processed" / "mitre.json"
    if not mitre_path.exists():
        raise HTTPException(status_code=500, detail="MITRE dataset not found.")

    with open(mitre_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in data:
        if isinstance(item, dict) and item.get("technique_id", "").upper() == clean_id:
            return item

    raise HTTPException(status_code=404, detail=f"MITRE technique '{clean_id}' not found.")


@app.post("/api/priority")
def post_priority(req: PriorityRequest) -> Dict[str, Any]:
    try:
        if req.explain:
            report = patch_explainer.generate_priority_report(req.cve_ids, priority_scorer.WEIGHTS_MAIN)
            return report
        else:
            ranked = priority_scorer.rank_cves(req.cve_ids, priority_scorer.WEIGHTS_MAIN)
            return {"ranked_cves": ranked, "weights_used": priority_scorer.WEIGHTS_MAIN}
    except Exception as exc:
        LOGGER.exception("Priority ranking failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/evaluation")
def get_evaluation_results() -> Dict[str, Any]:
    ret_path = PROJECT_ROOT / "evaluation" / "results" / "phase6_retrieval_results.json"
    ragas_path = PROJECT_ROOT / "evaluation" / "results" / "phase6_ragas_results.json"
    prio_path = PROJECT_ROOT / "evaluation" / "results" / "phase6_priority_results.json"

    ret_data = json.load(open(ret_path, "r", encoding="utf-8")) if ret_path.exists() else {}
    ragas_data = json.load(open(ragas_path, "r", encoding="utf-8")) if ragas_path.exists() else {}
    prio_data = json.load(open(prio_path, "r", encoding="utf-8")) if prio_path.exists() else {}

    return {
        "retrieval": ret_data,
        "ragas": ragas_data,
        "priority": prio_data,
    }


@app.get("/api/evaluation/baseline-vs-final")
def get_baseline_vs_final() -> Dict[str, Any]:
    bvf_path = PROJECT_ROOT / "evaluation" / "results" / "baseline_vs_final.json"
    if not bvf_path.exists():
        raise HTTPException(status_code=404, detail="Baseline vs Final comparison results not found.")
    with open(bvf_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/runbook/{incident_type}")
def get_runbook(incident_type: str) -> Dict[str, Any]:
    try:
        runbook = runbook_generator.generate_runbook(incident_type)
        return runbook
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as exc:
        LOGGER.exception("Runbook generation failed")
        raise HTTPException(status_code=500, detail=str(exc))
