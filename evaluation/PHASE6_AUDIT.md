# Phase VI — Full Codebase Audit

**Audit Date**: 2026-08-12
**Auditor**: SecureRAG Phase VI Implementation

---

## Current Architecture

```
SecureRAG Pipeline
├── Data Ingestion (modules/ingestion/)
│   ├── NVD CVEs → data/raw/nvd_raw.json (1.8GB) → data/processed/nvd.json (243MB)
│   ├── MITRE ATT&CK → data/raw/mitre_raw.json (40MB) → data/processed/mitre.json (1.4MB)
│   ├── CISA KEV → data/raw/kev_raw.json (1.2MB) → data/processed/kev.json (1.3MB)
│   └── EPSS → data/raw/epss_raw.json (30MB) → data/processed/epss.json (38MB)
├── Knowledge Base (modules/Chunking/)
│   ├── chunker.py → data/chunks/chunks.json (806MB)
│   ├── embedder.py → data/embeddings/embedded_chunks.pkl
│   ├── vector_store.py → embeddings/chroma_db/ (ChromaDB)
│   ├── bm25_index.py → data/embeddings/bm25.pkl + corpus.pkl
│   └── verify_embeddings.py
├── Retrieval (modules/Retrieval/)
│   ├── query_expander.py (cybersecurity synonym expansion)
│   ├── dense_retriever.py (ChromaDB + all-MiniLM-L6-v2, metadata fast-path)
│   ├── sparse_retriever.py (BM25Okapi, cybersecurity tokenizer)
│   ├── hybrid_fusion.py (RRF with weighted dense/sparse)
│   └── reranker.py (cross-encoder/ms-marco-MiniLM-L-6-v2, metadata boost)
├── Generation (modules/Generation/)
│   ├── prompt_template.py (evidence-grounded prompt builder)
│   └── llm_chain.py (Mistral via Ollama)
├── Verification (modules/Verification/)
│   └── hallucination_guard.py (claim-level token overlap verification)
├── Prioritization
│   ├── priority_scorer.py (CVSS/EPSS/KEV weighted scoring)
│   ├── patch_explainer.py (LLM ranking explanations)
│   └── runbook_generator.py (NIST CSF 2.0 aligned IR runbooks)
├── Pipeline Orchestration
│   ├── pipeline.py (end-to-end: query → verified answer)
│   └── retriever.py (convenience wrapper for retrieval only)
└── Evaluation (evaluation/)
    ├── evaluation_engine.py (1087-line research-grade evaluation)
    ├── retrieval_queries.json (100 queries, 12 categories)
    ├── baseline_config.json
    ├── experiments/best_config.json
    ├── hyperparameter_results.json (12 trials)
    └── experiments/ (18 experiment directories)
```

---

## Component Inventory

### A. Dense Retrieval ✅
- **File**: `modules/Retrieval/dense_retriever.py` (569 lines)
- **Model**: sentence-transformers/all-MiniLM-L6-v2
- **Storage**: ChromaDB persistent client
- **Features**: CVE/technique metadata fast-path, cosine similarity, LRU-cached model/client

### B. Sparse/BM25 Retrieval ✅
- **File**: `modules/Retrieval/sparse_retriever.py` (449 lines)
- **Index**: BM25Okapi via rank-bm25
- **Features**: Cybersecurity-aware tokenizer, deduplication, corpus alignment validation

### C. Hybrid Retrieval ✅
- **File**: `modules/Retrieval/hybrid_fusion.py` (407 lines)
- **Method**: Reciprocal Rank Fusion with configurable weights
- **Features**: chunk_id/document dedup, weighted dense/sparse contributions

### D. Cross-encoder Reranking ✅
- **File**: `modules/Retrieval/reranker.py` (418 lines)
- **Model**: cross-encoder/ms-marco-MiniLM-L-6-v2
- **Features**: Score fusion (alpha blend), metadata-aware CVE/technique boosting, fallback sort

### E. Query Expansion ✅
- **File**: `modules/Retrieval/query_expander.py` (55 lines)
- **Method**: Static cybersecurity synonym map (12 vulnerability nicknames)

### F. Metadata Lookup ✅
- **Integrated into**: dense_retriever.py (CVE/technique metadata fast-path)
- **Integrated into**: reranker.py (metadata-aware boosting)

### G. Prompt Generation ✅
- **File**: `modules/Generation/prompt_template.py` (326 lines)
- **Features**: Evidence-grounded, metadata serialization, context budget, required output fields

### H. LLM Generation ✅
- **File**: `modules/Generation/llm_chain.py` (247 lines)
- **Model**: Mistral via Ollama
- **Features**: Configurable temperature/top_p/max_tokens, fallback answer

### I. Hallucination Verification ✅
- **File**: `modules/Verification/hallucination_guard.py` (360 lines)
- **Method**: Claim splitting → token overlap scoring → verified/partial/unsupported classification

### J. CVE Prioritization ✅
- **File**: `modules/priority_scorer.py` (350 lines)
- **Formula**: priority = (cvss/10 × cvss_w) + (epss × epss_w) + (kev × kev_w)
- **Presets**: WEIGHTS_MAIN (0.3/0.5/0.2), ABLATION1 (0.5/0.3/0.2), ABLATION2 (0.33/0.33/0.34)

### K. Existing Evaluation Framework ✅
- **File**: `evaluation/evaluation_engine.py` (1087 lines)
- **Capabilities**: Multi-mode evaluation, parallel retrieval, NDCG/MRR/Recall/Precision, category-level, experiment artifacts
- **Existing benchmark**: 100 queries across 12 categories

### L. Existing Frontend/Backend ❌
- **Frontend**: None (empty `app/` directory, no `frontend/` directory)
- **Backend API**: None (no FastAPI, no REST endpoints)
- **Streamlit**: Listed in requirements.txt but no Streamlit app exists

---

## Reusable Components

| Component | Location | Phase VI Usage |
|-----------|----------|----------------|
| `pipeline.run()` | `modules/pipeline.py` | Backend /api/chat endpoint |
| `retriever.retrieve()` | `modules/retriever.py` | Backend /api/retrieve endpoint |
| `priority_scorer.score_cve()` | `modules/priority_scorer.py` | Backend /api/cve/{id}, priority eval |
| `priority_scorer.rank_cves()` | `modules/priority_scorer.py` | Backend /api/priority, priority eval |
| `runbook_generator.generate_runbook()` | `modules/runbook_generator.py` | Backend /api/runbook/{type} |
| `patch_explainer.explain_rankings()` | `modules/patch_explainer.py` | Backend priority details |
| `evaluation_engine` | `evaluation/evaluation_engine.py` | Retrieval evaluation (reuse metrics) |
| Dense/Sparse/Hybrid/Reranker | `modules/Retrieval/*` | Retrieval evaluation per-mode |
| `baseline_config.json` | `evaluation/` | Baseline comparison |
| `best_config.json` | `evaluation/experiments/` | Final comparison |

---

## Missing Components (To Be Built)

1. **300-query evaluation dataset** with structured ground truth
2. **Phase 6 retrieval evaluation** script (4 modes, entity-level metrics)
3. **RAGAS evaluation** pipeline
4. **Priority evaluation** with Spearman correlation vs KEV dates
5. **Baseline vs Final comparison** with visualization
6. **Failure analysis** report
7. **React + Vite frontend** (6 pages)
8. **FastAPI backend** (9 endpoints)
9. **Security hardening** (.env, CORS, input validation)
10. **Test suite** for Phase 6
11. **Paper-ready results** table
12. **Reproducibility documentation**

---

## Files That Will Be Modified

| File | Modification |
|------|-------------|
| `requirements.txt` | Add fastapi, uvicorn, python-dotenv, python-multipart |
| `.gitignore` | Add frontend/node_modules, frontend/dist, .env |

---

## Files That Should NOT Be Modified

All existing module files, data files, evaluation configs, and experiment artifacts.
See implementation plan for complete list.

---

## Risks

1. **Large dataset evaluation time**: 300 queries × 4 modes = long runtime
2. **Ollama availability**: RAGAS and runbook generation need Mistral
3. **Retrieval quality**: Baseline metrics (Recall@5=0.39) are modest — honest reporting critical
4. **RAGAS API version**: Must detect installed version and adapt
5. **ChromaDB state**: Evaluation assumes existing ChromaDB is populated

---

## Recommended Implementation Order

1. Audit document (this file) ✅
2. 300-query dataset + validation
3. Retrieval evaluation script
4. RAGAS evaluation script
5. Priority evaluation script
6. FastAPI backend (needed before frontend)
7. React frontend
8. Security hardening
9. Tests
10. Run evaluations → generate results
11. Baseline vs final comparison
12. Failure analysis
13. Paper results
14. Reproducibility docs
15. Quality gate
