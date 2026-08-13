# SecureRAG: SOC Analyst Threat Intelligence Platform

SecureRAG is a full-stack cyber threat intelligence (CTI) retrieval and answer-generation system designed for SOC analysts. It ingests structured threat feeds, builds a searchable knowledge base, evaluates retrieval quality, and exposes a production-oriented API and frontend for analyst workflows.

This project spans the full lifecycle from raw CTI ingestion to retrieval benchmarking and deployment documentation:

- Phase I: CTI ingestion and normalization
- Phase II: knowledge base construction and indexing
- Phase III: retrieval and answer generation groundwork
- Phase IV: end-to-end secure RAG pipeline and verification
- Phase V: prioritization, runbooks, and analyst decision support
- Phase VI: evaluation, benchmarking, frontend integration, and reproducible reporting

---

## 1. Project Overview

The system combines four major CTI sources:

- NVD: CVE metadata and vulnerability descriptions
- MITRE ATT&CK: adversary tactics and techniques
- CISA KEV: actively exploited vulnerabilities
- EPSS: exploit prediction scores

These sources are normalized, chunked, embedded, indexed, and then queried through a retrieval pipeline. The project supports both analyst-facing API interaction and benchmark-based evaluation against a 300-query test set.

The architecture is organized around five functional layers:

1. Data ingestion
2. Knowledge base construction
3. Retrieval and fusion
4. Answer generation and validation
5. Evaluation and reporting

---

## 2. Complete Workflow Across Phases

## Phase I — CTI Data Ingestion

Goal: collect and normalize vulnerability and adversary intelligence from external sources.

### Components

- [modules/ingestion/ingest_nvd.py](modules/ingestion/ingest_nvd.py)
- [modules/ingestion/ingest_mitre.py](modules/ingestion/ingest_mitre.py)
- [modules/ingestion/ingest_kev.py](modules/ingestion/ingest_kev.py)
- [modules/ingestion/epss_fetcher.py](modules/ingestion/epss_fetcher.py)
- [modules/ingestion/verify_sources.py](modules/ingestion/verify_sources.py)

### What happens

- NVD CVE records are fetched and normalized into a local dataset
- MITRE ATT&CK techniques are ingested and mapped to tactic/technique metadata
- KEV data is imported to flag actively exploited vulnerabilities
- EPSS scores are downloaded and stored for exploit likelihood ranking
- Source verification checks the health and completeness of ingested data

### Output locations

- [data/raw](data/raw)
- [data/processed](data/processed)

Examples:

- [data/processed/nvd.json](data/processed/nvd.json)
- [data/processed/mitre.json](data/processed/mitre.json)
- [data/processed/kev.json](data/processed/kev.json)
- [data/processed/epss.json](data/processed/epss.json)

### Run commands

```bash
py -3 -m modules.ingestion
```

or manually:

```bash
py -3 modules/ingestion/ingest_nvd.py
py -3 modules/ingestion/ingest_mitre.py
py -3 modules/ingestion/ingest_kev.py
py -3 modules/ingestion/epss_fetcher.py
```

### Result

The project obtains a normalized CTI corpus for downstream retrieval and analyst workflows.

---

## Phase II — Knowledge Base Building and Indexing

Goal: convert raw CTI into searchable, retrievable knowledge artifacts.

### Components

- [modules/Chunking/chunker.py](modules/Chunking/chunker.py)
- [modules/Chunking/embedder.py](modules/Chunking/embedder.py)
- [modules/Chunking/vector_store.py](modules/Chunking/vector_store.py)
- [modules/Chunking/bm25_index.py](modules/Chunking/bm25_index.py)
- [modules/Chunking/verify_embeddings.py](modules/Chunking/verify_embeddings.py)
- [modules/Chunking/build_knowledge_base.py](modules/Chunking/build_knowledge_base.py)

### What happens

- CTI documents are chunked into manageable retrieval units
- Text chunks are embedded with sentence-transformers
- Dense embeddings are stored in ChromaDB
- BM25 indexes are created for keyword search
- Output files and index integrity are verified

### Key artifacts

- [data/chunks/chunks.json](data/chunks/chunks.json)
- [embeddings/chroma_db](embeddings/chroma_db)
- [data/embeddings](data/embeddings)

### Run command

```bash
py -3 modules/Chunking/build_knowledge_base.py
```

### Result

The project becomes a searchable evidence base for CVE, MITRE, and IR analyst queries.

---

## Phase III — Retrieval Foundation and Analyst Query Handling

Goal: support retrieval operations beyond static indexing and prepare the application for end-to-end answer generation.

### Retrieval modules

- [modules/Retrieval/dense_retriever.py](modules/Retrieval/dense_retriever.py)
- [modules/Retrieval/sparse_retriever.py](modules/Retrieval/sparse_retriever.py)
- [modules/Retrieval/hybrid_fusion.py](modules/Retrieval/hybrid_fusion.py)
- [modules/Retrieval/reranker.py](modules/Retrieval/reranker.py)

### Retrieval stack

- Dense retrieval: semantic search over ChromaDB embeddings
- Sparse retrieval: BM25 keyword matching
- Hybrid fusion: reciprocal rank fusion to combine signals
- Reranking: cross-encoder prioritization of evidence

### Result

The system can take analyst questions and retrieve relevant CTI evidence with ranked ordering.

---

## Phase IV — SecureRAG End-to-End Pipeline

Goal: transform retrieval results into grounded, verified responses with hallucination checks.

### Main orchestration

- [modules/pipeline.py](modules/pipeline.py)
- [modules/Generation/prompt_template.py](modules/Generation/prompt_template.py)
- [modules/Generation/llm_chain.py](modules/Generation/llm_chain.py)
- [modules/Verification/hallucination_guard.py](modules/Verification/hallucination_guard.py)

### End-to-end flow

```text
User query
  -> Dense retrieval
  -> Sparse retrieval
  -> Hybrid fusion
  -> Cross-encoder reranking
  -> Prompt construction
  -> Ollama LLM generation
  -> Hallucination guard
  -> Final verified answer
```

### Run command

```bash
py -3 modules/pipeline.py "How should we prioritize CVE-2021-44228?"
```

### Safety model

- Retrieved evidence is used as grounding context
- Unsupported claims are filtered or rejected
- The system falls back cleanly if retrieval fails
- Final output includes diagnostics and verification metadata

---

## Phase V — CVE Prioritization and Analyst Support

Goal: move from generic retrieval to SOC decision support.

### Analyst support modules

- [modules/priority_scorer.py](modules/priority_scorer.py)
- [modules/runbook_generator.py](modules/runbook_generator.py)
- [modules/patch_explainer.py](modules/patch_explainer.py)
- [modules/retriever.py](modules/retriever.py)

### Capabilities

- Score and rank CVEs using CVSS, EPSS, KEV and exploit context
- Explain prioritization logic
- Generate IR response runbooks
- Surface relevant evidence and remediation guidance

### Backend endpoints

The live API is defined in [backend/main.py](backend/main.py), with endpoints for:

- /api/health
- /api/chat
- /api/retrieve
- /api/cve/{cve_id}
- /api/mitre/{technique_id}
- /api/priority
- /api/evaluation
- /api/evaluation/baseline-vs-final
- /api/runbook/{incident_type}

### Example health check

```bash
.
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

---

## Phase VI — Evaluation, Benchmarking, Frontend, and Reporting

Goal: validate the system rigorously and package the project for reproducible evaluation and deployment.

### Core evaluation files

- [evaluation/validate_phase6_dataset.py](evaluation/validate_phase6_dataset.py)
- [evaluation/phase6_retrieval_evaluation.py](evaluation/phase6_retrieval_evaluation.py)
- [evaluation/phase6_ragas.py](evaluation/phase6_ragas.py)
- [evaluation/phase6_priority_evaluation.py](eval/phase6_priority_evaluation.py)
- [evaluation/phase6_baseline_vs_final.py](evaluation/phase6_baseline_vs_final.py)
- [evaluation/generate_paper_results.py](evaluation/generate_paper_results.py)
- [evaluation/phase6_failure_analysis.py](evaluation/phase6_failure_analysis.py)

### Evaluation dataset

The benchmark uses a 300-query dataset built from:

- 100 CVE explanation queries
- 100 MITRE ATT&CK mapping queries
- 100 IR / incident-response queries

Validation includes:

- dataset size and split checks
- ground truth completeness checks
- source coverage checks for CVE, KEV, and MITRE entities

### Evaluation workflow

Run the full benchmark suite:

```bash
.
.venv\Scripts\python.exe evaluation/validate_phase6_dataset.py
.
.venv\Scripts\python.exe -m evaluation.phase6_retrieval_evaluation --mode all
.
.venv\Scripts\python.exe evaluation/phase6_ragas.py
.
.venv\Scripts\python.exe eval/phase6_priority_evaluation.py
.
.venv\Scripts\python.exe evaluation/phase6_baseline_vs_final.py
.
.venv\Scripts\python.exe evaluation/phase6_failure_analysis.py
.
.venv\Scripts\python.exe evaluation/generate_paper_results.py
```

### Verification and test coverage

The regression test suite is in [tests/test_phase6.py](tests/test_phase6.py). It checks:

- dataset integrity
- MRR and NDCG calculations
- priority scoring behavior
- backend endpoints

Verified result from the project run:

- 7/7 tests passed

### Frontend

The frontend is in [frontend](frontend). It uses Vite and provides the analyst UI for browsing CVEs, MITRE mappings, priorities, evaluations, and runbooks.

Run it with:

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

### Production-relevant result

The final dense comparison script produced a reproducible benchmark artifact showing strong retrieval quality with much lower latency:

- recall@5: 0.9333 -> 0.9333
- MRR: 0.9333 -> 0.9333
- NDCG@5: 1.4033 -> 1.4033
- average latency: 631.01 ms -> 166.54 ms
- improvement: ~73.61% latency reduction

The final comparison artifacts are in:

- [evaluation/results/baseline_vs_final.json](evaluation/results/baseline_vs_final.json)
- [evaluation/results/baseline_vs_final.csv](evaluation/results/baseline_vs_final.csv)
- [evaluation/results/baseline_vs_final.png](evaluation/results/baseline_vs_final.png)

### Phase VI summary documents

- [PHASE6_FINAL_SUMMARY.md](PHASE6_FINAL_SUMMARY.md)
- [PHASE6_COMPLETION_SUMMARY.md](PHASE6_COMPLETION_SUMMARY.md)
- [evaluation/PHASE6_README.md](evaluation/PHASE6_README.md)
- [evaluation/PHASE6_AUDIT.md](evaluation/PHASE6_AUDIT.md)
- [evaluation/results/PAPER_RESULTS.md](evaluation/results/PAPER_RESULTS.md)
- [evaluation/FAILURE_ANALYSIS.md](evaluation/FAILURE_ANALYSIS.md)

---

## 3. Project Structure

```text
SOC_Analyst/
├── README.md
├── LICENSE
├── requirements.txt
├── backend/
│   └── main.py
├── data/
│   ├── chunks/
│   ├── embeddings/
│   ├── processed/
│   └── raw/
├── embeddings/
│   └── chroma_db/
├── eval/
│   ├── phase6_priority_evaluation.py
│   ├── validate_prioritizer.py
│   └── ...
├── evaluation/
│   ├── phase6_baseline_vs_final.py
│   ├── phase6_failure_analysis.py
│   ├── phase6_retrieval_evaluation.py
│   ├── phase6_ragas.py
│   ├── validate_phase6_dataset.py
│   ├── PHASE6_README.md
│   ├── PHASE6_AUDIT.md
│   └── results/
├── frontend/
│   ├── package.json
│   ├── src/
│   ├── public/
│   └── vite.config.ts
├── modules/
│   ├── Chunking/
│   ├── Generation/
│   ├── Retrieval/
│   ├── Verification/
│   ├── ingestion/
│   ├── pipeline.py
│   ├── priority_scorer.py
│   ├── patch_explainer.py
│   ├── retriever.py
│   ├── runbook_generator.py
│   └── ...
├── tests/
│   └── test_phase6.py
└── ...
```

---

## 4. Setup and Local Development

### Requirements

- Python 3.13 recommended
- Node.js 18+ or newer
- pip
- access to Ollama for LLM generation if running the full pipeline

### Environment setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Backend startup

```bash
.
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### Frontend startup

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

### API docs

Open:

- http://127.0.0.1:8000/docs
- http://127.0.0.1:5173

---

## 5. What the Project Delivers

This project provides a complete CTI intelligence workflow for analyst use cases:

- ingest vulnerability and ATT&CK data
- build a persistent retrieval index from that data
- answer security questions with grounded evidence
- rank vulnerabilities by strategic priority
- generate runbooks for incident response scenarios
- benchmark retrieval quality across a reproducible 300-query dataset
- expose the work through both an API and a frontend interface

---

## 6. Realistic Assessment of Current Status

The project is functionally complete for the core secure SOC analytics workflow:

- ingestion pipeline works
- knowledge base indexing works
- end-to-end retrieval and generation pipeline works
- priority scoring and responder support work
- Phase VI evaluation is reproducible
- tests pass
- benchmarking artifacts have been generated

The honest limitation recognized in the evaluation reports is that some IR / cross-domain queries still benefit from further optimization, especially around chunking and hybrid retrieval strategies. This is documented in the Phase VI analysis files rather than hidden.

---

## 7. Final Summary

SecureRAG is a complete CTI retrieval and analyst decision-support system that starts from raw threat intelligence feeds and ends with a working secure retrieval pipeline, API, frontend, evaluation framework, and final reporting artifacts.

Its full lifecycle can be understood as follows:

1. Ingest and normalize CTI data
2. Build the searchable knowledge base
3. Retrieve semantically relevant evidence
4. Fuse retrieval signals and rerank the best results
5. Generate grounded analyst answers
6. Score and prioritize vulnerabilities for triage
7. Validate with reproducible benchmarks and tests
8. Package everything into a usable product and report

This README now reflects that complete workflow from Phase I through Phase VI using the real project structure and verified execution state.
