# SecureRAG — Hallucination-Safe AI Copilot for SOC Analysts

SecureRAG is a retrieval-augmented generation (RAG) system for security operations. It ingests
public cyber threat intelligence (CTI), indexes it for hybrid dense + sparse retrieval, generates
answers with a locally hosted Mistral model, and then **verifies every claim against the retrieved
evidence** before showing it to an analyst. Anything the evidence does not support is stripped or
explicitly marked as unverified.

The system ships as three layers:

| Layer      | Stack                                       | Entry point           |
| ---------- | ------------------------------------------- | --------------------- |
| Core RAG   | Python 3.13, ChromaDB, BM25, Ollama/Mistral | `modules/pipeline.py` |
| REST API   | FastAPI + Uvicorn                           | `backend/main.py`     |
| Analyst UI | React 19 + TypeScript + Vite                | `frontend/`           |

**License:** MIT · **Repository:** https://github.com/monal95/LLM-Based-Security-copilot

---

## Table of Contents

1. [Why SecureRAG](#why-securerag)
2. [Architecture](#architecture)
3. [Knowledge Base](#knowledge-base)
4. [Project Layout](#project-layout)
5. [Installation](#installation)
6. [Building the Knowledge Base](#building-the-knowledge-base)
7. [Running the Application](#running-the-application)
8. [API Reference](#api-reference)
9. [Configuration](#configuration)
10. [Python Usage](#python-usage)
11. [Evaluation](#evaluation)
12. [Testing](#testing)
13. [Troubleshooting](#troubleshooting)
14. [Roadmap](#roadmap)
15. [License](#license)

---

## Why SecureRAG

A generic LLM asked "how bad is CVE-2021-44228?" will answer confidently whether or not it actually
knows. In a SOC that is unacceptable — a fabricated CVSS score or an invented mitigation step turns
into a wrong patch decision.

SecureRAG addresses that with four design commitments:

- **Grounded by construction.** The generator only sees reranked chunks retrieved from real NVD,
  MITRE ATT&CK, CISA KEV, and EPSS records. The prompt carries a strict grounding policy.
- **Verified after generation.** `modules/Verification/hallucination_guard.py` splits the answer
  into claims and scores each against the retrieved context. Claims below the support threshold are
  replaced or removed, and a per-claim report plus a confidence score is returned with every answer.
- **Fails closed.** When evidence is insufficient the system returns
  `Not found in retrieved evidence.` rather than guessing.
- **Fully local.** Embeddings, reranking, vector store, and the LLM all run on the host machine. No
  CTI data or analyst query leaves the box.

---

## Architecture

```
                        ┌──────────────────────────────────────────┐
   NVD  ─┐              │            Ingestion (Module 1)          │
 MITRE  ─┤              │   normalize → data/processed/*.json      │
  KEV   ─┼──────────────▶                                          │
  EPSS  ─┘              └────────────────────┬─────────────────────┘
                                             │
                        ┌────────────────────▼─────────────────────┐
                        │        Knowledge Base (Module 2)         │
                        │   chunk (512 tok / 50 overlap)           │
                        │   embed (all-MiniLM-L6-v2, 384-dim)      │
                        │   → ChromaDB   +   → BM25 index          │
                        └────────────────────┬─────────────────────┘
                                             │
  Analyst query ─────────────────────────────▼──────────────────────
                                             │
       ┌─────────────────┬───────────────────┴─────────────┐
       │ Query Expansion │  (CVE aliases: Log4Shell, ...)   │
       └────────┬────────┴────────────────┬────────────────┘
                │                         │
      ┌─────────▼────────┐      ┌─────────▼─────────┐
      │ Dense Retrieval  │      │ Sparse Retrieval  │
      │    (ChromaDB)    │      │      (BM25)       │
      └─────────┬────────┘      └─────────┬─────────┘
                └────────────┬────────────┘
                  ┌──────────▼──────────┐
                  │ Hybrid Fusion (RRF) │  score = Σ 1/(k + rank)
                  └──────────┬──────────┘
                  ┌──────────▼─────────────────────────┐
                  │ Cross-Encoder Rerank               │
                  │ (ms-marco-MiniLM-L-6-v2)           │
                  └──────────┬─────────────────────────┘
                  ┌──────────▼──────────┐
                  │ Prompt Construction │  strict grounding policy
                  └──────────┬──────────┘
                  ┌──────────▼──────────┐
                  │ Mistral via Ollama  │
                  └──────────┬──────────┘
                  ┌──────────▼──────────┐
                  │ Hallucination Guard │  per-claim verification
                  └──────────┬──────────┘
                             ▼
              Verified answer + confidence + claim reports
```

### Pipeline stages

| Stage           | Module                                    | Model / method                                                                                            | Default                          |
| --------------- | ----------------------------------------- | --------------------------------------------------------------------------------------------------------- | -------------------------------- |
| Query expansion | `modules/Retrieval/query_expander.py`     | Static CTI synonym map (Log4Shell, EternalBlue, Zerologon, PrintNightmare, ProxyShell, Heartbleed, Follina, BlueKeep, …) | enabled                          |
| Dense retrieval | `modules/Retrieval/dense_retriever.py`    | `sentence-transformers/all-MiniLM-L6-v2` over ChromaDB                                                    | `top_k=30`                       |
| Sparse retrieval| `modules/Retrieval/sparse_retriever.py`   | `rank_bm25.BM25Okapi` over the tokenized corpus                                                           | configurable `top_k`             |
| Hybrid fusion   | `modules/Retrieval/hybrid_fusion.py`      | Reciprocal Rank Fusion                                                                                    | `rrf_k=60`                       |
| Reranking       | `modules/Retrieval/reranker.py`           | `cross-encoder/ms-marco-MiniLM-L-6-v2`                                                                    | `top_k=10`                       |
| Prompting       | `modules/Generation/prompt_template.py`   | Evidence-constrained prompt package                                                                       | —                                |
| Generation      | `modules/Generation/llm_chain.py`         | Mistral via Ollama (env-configurable)                                                                     | `temperature=0.1`, `max_tokens=300`, `timeout=420s` |
| Verification    | `modules/Verification/hallucination_guard.py` | Claim/evidence overlap scoring                                                                        | verified ≥ 0.55, partial ≥ 0.30  |

### Analyst services built on the pipeline

- **`modules/priority_scorer.py`** — CVE patch triage.
  `priority = (cvss/10 × w_cvss) + (epss × w_epss) + (kev_flag × w_kev)`
  Default weights `WEIGHTS_MAIN = {cvss: 0.3, epss: 0.5, kev: 0.2}`, with two ablation presets
  (`WEIGHTS_ABLATION1`, `WEIGHTS_ABLATION2`) used in the evaluation studies.
- **`modules/patch_explainer.py`** — turns a ranking into short, analyst-facing rationales.
- **`modules/runbook_generator.py`** — NIST CSF 2.0 aligned incident-response runbooks for
  `ransomware`, `phishing`, `data_breach`, and `supply_chain`.
- **`modules/retriever.py`** — thin `retrieve(query, top_k)` wrapper returning ranked chunks as dicts.
- **`backend/warmup.py`** — loads torch, both transformer models, ChromaDB, and the BM25 pickles on a
  background thread at startup so the first analyst query does not pay that cost. `/api/health`
  reports real measured warmup timings, not estimates.

---

## Knowledge Base

Built from four public CTI sources, refreshed by the ingestion module:

| Source       | Feed                                       | Processed records     |
| ------------ | ------------------------------------------ | --------------------- |
| NVD CVE      | NVD API 2.0 (paginated, checkpointed)      | **366,669**           |
| EPSS         | FIRST.org bulk gzipped CSV (API fallback)  | **348,900**           |
| MITRE ATT&CK | Enterprise STIX 2.1 bundle                 | **697** techniques    |
| CISA KEV     | Official KEV JSON feed                     | **1,647**             |

Indexed artifacts:

- **414,854** chunks in `data/chunks/chunks.json`
- ChromaDB collection `secure_rag_chunks` — 414,854 vectors, 384 dimensions
- BM25 index `data/embeddings/bm25.pkl` + tokenized corpus `data/embeddings/corpus.pkl`

> Datasets and indexes are **not** committed — `.gitignore` excludes `data/*` and `embeddings/*`.
> Expect roughly **8 GB** on disk after a full build. Build them locally with the steps below.

---

## Project Layout

```
SOC_Analyst/
├── backend/
│   ├── main.py                       # FastAPI app — 9 endpoints
│   └── warmup.py                     # Background model/index preloading
├── modules/
│   ├── ingestion/                    # Module 1 — CTI ingestion
│   │   ├── __main__.py               # `python -m modules.ingestion`
│   │   ├── ingest_nvd.py             # 1.1 NVD CVEs
│   │   ├── ingest_mitre.py           # 1.2 MITRE ATT&CK
│   │   ├── ingest_kev.py             # 1.3 CISA KEV
│   │   ├── epss_fetcher.py           # 1.4 EPSS scores
│   │   └── verify_sources.py         # Ingestion validation
│   ├── Chunking/                     # Module 2 — knowledge base
│   │   ├── chunker.py                # 2.1 512-token chunks, 50 overlap
│   │   ├── embedder.py               # 2.2 all-MiniLM-L6-v2
│   │   ├── vector_store.py           # 2.3 ChromaDB persistence
│   │   ├── bm25_index.py             # 2.4 BM25 index
│   │   ├── verify_embeddings.py      # 2.5 artifact verification
│   │   └── build_knowledge_base.py   # Module 2 orchestration
│   ├── Retrieval/                    # Module 3 — retrieval
│   │   ├── dense_retriever.py        # 3.1
│   │   ├── sparse_retriever.py       # 3.2
│   │   ├── hybrid_fusion.py          # 3.3 RRF
│   │   ├── reranker.py               # 3.4 cross-encoder
│   │   └── query_expander.py         # 3.5 CTI synonym expansion
│   ├── Generation/                   # Module 4 — generation
│   │   ├── prompt_template.py        # 4.1
│   │   └── llm_chain.py              # 4.2 Ollama/Mistral
│   ├── Verification/
│   │   └── hallucination_guard.py    # 4.3 claim verification
│   ├── pipeline.py                   # End-to-end orchestration
│   ├── retriever.py                  # Simple retrieve() wrapper
│   ├── priority_scorer.py            # CVSS/EPSS/KEV patch triage
│   ├── patch_explainer.py            # Ranking explanations
│   └── runbook_generator.py          # NIST CSF 2.0 IR runbooks
├── frontend/
│   └── src/
│       ├── App.tsx, navigation.ts, types.ts
│       ├── components/               # 8 console views + shared UI
│       ├── services/api.ts           # Typed backend client
│       └── lib/                      # Formatting + evaluation helpers
├── evaluation/                       # Research evaluation harness
│   ├── evaluation_engine.py          # Metric computation core
│   ├── phase6_queries.json           # 300-query benchmark
│   ├── phase6_retrieval_evaluation.py
│   ├── phase6_ragas.py               # RAGAS faithfulness / relevancy
│   ├── phase6_baseline_vs_final.py
│   ├── phase6_failure_analysis.py
│   ├── hyperparameter_search.py, tune_rrf.py
│   ├── benchmark_runtime.py          # Wall-clock API latency
│   ├── experiments/                  # Timestamped experiment artifacts
│   └── results/                      # Metrics, plots, PAPER_RESULTS.md
├── eval/                             # Prioritization validation studies
├── tests/test_phase6.py              # 7-test suite
├── data/, embeddings/                # Generated artifacts (gitignored)
├── requirements.txt, .env.example, QUICK_START.md, LICENSE
```

---

## Installation

### Prerequisites

- **Python 3.13+**
- **Node.js 18+** with npm
- **Ollama** with the `mistral` model — required for generation, runbooks, patch explanations, and
  RAGAS evaluation. Retrieval, CVE lookup, MITRE lookup, and prioritization work without it.
- ~8 GB free disk, 4 GB RAM minimum. GPU optional.
- Ports **8000** (backend) and **5173** (frontend dev) free.

### 1. Python environment

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

### 2. Ollama

```bash
ollama serve            # listens on http://localhost:11434
ollama pull mistral
```

### 3. Frontend dependencies

```bash
cd frontend
npm install
```

### 4. Environment file

```bash
cp .env.example .env    # Windows: copy .env.example .env
```

Optionally set an NVD API key before ingesting — without it the NVD crawl still works but is
rate-limited heavily:

```bash
set NVD_API_KEY=your_api_key_here       # Windows
export NVD_API_KEY=your_api_key_here    # macOS / Linux
```

---

## Building the Knowledge Base

Both steps are long-running. The full NVD crawl is the slowest part and is checkpointed, so an
interrupted run resumes.

### Step 1 — Ingest CTI sources

```bash
python -m modules.ingestion
```

Runs NVD → MITRE → KEV → EPSS in order, then validates the output. Each source writes
`data/raw/<source>_raw.json` and `data/processed/<source>.json`.

Individual sources:

```bash
python modules/ingestion/ingest_nvd.py
python modules/ingestion/ingest_mitre.py
python modules/ingestion/ingest_kev.py
python modules/ingestion/epss_fetcher.py
python modules/ingestion/verify_sources.py
```

### Step 2 — Chunk, embed, and index

```bash
python modules/Chunking/build_knowledge_base.py
```

Runs `chunker → embedder → vector_store → bm25_index → verify_embeddings`. Individual steps:

```bash
python modules/Chunking/chunker.py            # → data/chunks/chunks.json
python modules/Chunking/embedder.py           # → data/embeddings/embedded_chunks.pkl
python modules/Chunking/vector_store.py       # → embeddings/chroma_db/
python modules/Chunking/bm25_index.py         # → data/embeddings/bm25.pkl + corpus.pkl
python modules/Chunking/verify_embeddings.py  # sanity checks
```

`verify_embeddings.py` confirms file existence and sizes, a 384-dim embedding space, the ChromaDB
collection count, semantic search for Log4Shell / CVE-2021-44228, and BM25 functionality.

---

## Running the Application

### Development

**Terminal 1 — backend**

```bash
.\.venv\Scripts\uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — frontend**

```bash
cd frontend
npm run dev
```

| Surface         | URL                             |
| --------------- | ------------------------------- |
| Analyst console | http://localhost:5173/          |
| API             | http://127.0.0.1:8000           |
| Swagger UI      | http://127.0.0.1:8000/docs      |
| OpenAPI spec    | http://127.0.0.1:8000/openapi.json |

Startup warmup runs on a background thread — the server accepts connections immediately and
`GET /api/health` reports warmup progress (`not_started` → `running` → `ready`). Set
`SECURERAG_SKIP_WARMUP=1` for lazy loading when you only need the metadata endpoints.

### Production

```bash
cd frontend && npm run build          # → frontend/dist/
.\.venv\Scripts\uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Serve `frontend/dist/` from any static web server, and set `VITE_API_BASE_URL` at build time to
point the bundle at your production API. Set `ALLOWED_ORIGINS` on the backend to match.

### Console views

| View            | Purpose                                        | Backend endpoint       |
| --------------- | ---------------------------------------------- | ---------------------- |
| Dashboard       | System health, warmup state, model inventory   | `GET /api/health`      |
| Analyst Console | Grounded chat with confidence and claim reports| `POST /api/chat`       |
| Vulnerabilities | CVE lookup — CVSS, EPSS, KEV, priority score   | `GET /api/cve/{id}`    |
| Prioritization  | Ranked patch queue with explanations           | `POST /api/priority`   |
| MITRE ATT&CK    | Technique, tactics, sub-techniques, mitigations| `GET /api/mitre/{id}`  |
| Evidence Search | Raw reranked retrieval, no generation          | `POST /api/retrieve`   |
| Evaluation      | Retrieval / RAGAS / prioritization metrics     | `GET /api/evaluation`  |
| System          | Endpoint inventory and diagnostics             | `GET /api/health`      |

Incident-response runbooks are generated from a modal on top of these views via
`GET /api/runbook/{incident_type}` and can be downloaded as Markdown.

---

## API Reference

Base URL: `http://127.0.0.1:8000`. CORS methods are limited to `GET`, `POST`, `OPTIONS`.

### `GET /api/health`

Service status, model inventory, and measured warmup timings.

```bash
curl http://127.0.0.1:8000/api/health
```

### `POST /api/chat`

Full RAG pipeline: retrieval → fusion → rerank → generation → verification.

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"What is CVE-2021-44228?\"}"
```

| Field           | Type   | Default | Range        |
| --------------- | ------ | ------- | ------------ |
| `query`         | string | —       | 2–1000 chars |
| `top_k_dense`   | int    | 10      | 1–50         |
| `top_k_sparse`  | int    | 10      | 1–50         |
| `top_k_fused`   | int    | 15      | 1–50         |
| `top_k_rerank`  | int    | 5       | 1–20         |

Returns `final_answer`, `confidence_score`, `verification_report`, `claim_reports`, per-stage
retrieval `counts`, `total_latency_ms`, `stage_timings_ms`, a `warm` flag, and
`generation_status` / `llm_error`.

`generation_status` separates a model failure from a genuine "the evidence does not support this"
result:

| `generation_status` | `final_answer` | `confidence_score` | `claim_reports` | Meaning |
| ------------------- | -------------- | ------------------ | --------------- | ------- |
| `"ok"` | verified answer | 0.0–1.0 | one per claim | Model answered; claims scored against evidence |
| `"failed"` | `""` | `null` | `[]` | Ollama call errored — see `llm_error`. No claims are scored, because verifying an error message would report it as a low-confidence answer |

Retrieval counts are populated in both cases, so the evidence remains usable when generation fails.

### `POST /api/retrieve`

Evidence retrieval only — no LLM, so it works without Ollama.

```bash
curl -X POST http://127.0.0.1:8000/api/retrieve \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"ransomware containment and recovery\", \"top_k\": 5}"
```

`top_k` accepts 1–30 (default 5).

### `GET /api/cve/{cve_id}`

CVSS, EPSS score and percentile, KEV flag, computed priority score, description, severity,
publication date, and affected products. Rejects IDs that do not start with `CVE-`.

```bash
curl http://127.0.0.1:8000/api/cve/CVE-2021-44228
```

### `GET /api/mitre/{technique_id}`

Full technique record — name, description, tactics, sub-techniques, mitigations, platforms, data
sources, and the ATT&CK URL.

```bash
curl http://127.0.0.1:8000/api/mitre/T1021
```

### `POST /api/priority`

Ranks 1–100 CVEs by the weighted CVSS/EPSS/KEV score. With `explain: true` (default) each entry
carries an LLM-written rationale; with `explain: false` you get the raw ranking and the weights used.

```bash
curl -X POST http://127.0.0.1:8000/api/priority \
  -H "Content-Type: application/json" \
  -d "{\"cve_ids\": [\"CVE-2021-44228\", \"CVE-2022-26134\"], \"explain\": true}"
```

### `GET /api/evaluation`

Combined retrieval, RAGAS, and prioritization metrics read from `evaluation/results/`. Missing
result files come back as empty objects rather than errors.

### `GET /api/evaluation/baseline-vs-final`

Baseline vs tuned-configuration comparison over the same 300-query benchmark. `404` if the
comparison has not been run.

### `GET /api/runbook/{incident_type}`

NIST CSF 2.0 aligned runbook. Valid types: `ransomware`, `phishing`, `data_breach`, `supply_chain`.

```bash
curl http://127.0.0.1:8000/api/runbook/ransomware
```

---


## Configuration

### Backend — `.env`

```env
HOST=0.0.0.0
PORT=8000

# Comma-separated CORS origins
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173

OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=mistral

# Generation limits — see the note on CPU-only inference below
LLM_TIMEOUT_SECONDS=420
LLM_MAX_TOKENS=300

# Optional: OpenAI-backed RAGAS evaluator instead of the local model
# OPENAI_API_KEY=your_openai_api_key_here

DATA_DIR=data
EMBEDDINGS_DIR=embeddings
```

| Variable | Effect | Default |
| -------- | ------ | ------- |
| `OLLAMA_MODEL` | Model used for generation, runbooks and patch explanations | `mistral` |
| `OLLAMA_HOST` | Ollama endpoint | `http://localhost:11434` |
| `LLM_TIMEOUT_SECONDS` | Client timeout for a single generation call | `420` |
| `LLM_MAX_TOKENS` | Cap on generated tokens (`num_predict`) | `300` |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins | localhost 5173/3000 |
| `SECURERAG_SKIP_WARMUP=1` | Skip startup preloading; components load lazily on first query | unset |
| `NVD_API_KEY` | Raises NVD ingestion rate limits | unset |

### Generation timeouts on CPU-only hardware

Generation runs on the CPU unless Ollama can offload to a GPU (`curl
http://localhost:11434/api/ps` — `size_vram: 0` means CPU-only). A 7B model such as `mistral`
(~5 GB) can need **several minutes** per answer there, and it competes for RAM with torch, both
transformer models, ChromaDB and the BM25 index.

Two settings must stay in step, or a slow-but-successful generation is reported as a timeout:

- `LLM_TIMEOUT_SECONDS` in `.env` — the backend's ceiling for **the Ollama call only**.
- `VITE_CHAT_TIMEOUT_MS` (default 600000) — the browser's abort, which covers the **whole request**:
  retrieval + fusion + reranking + generation.

The second must exceed the first by more than the retrieval time, and retrieval is not free when
memory is tight. Measured on an 8 GB laptop with a 5 GB model resident, one `/api/chat` call spent
**408 s in retrieval before generation even started**:

| Stage | Measured (starved) | Healthy machine |
| ----- | ------------------ | --------------- |
| Dense retrieval (with CVE metadata lookup) | 78.8 s | ~0.2 s |
| Sparse retrieval (BM25 paged back from disk) | 317.8 s | ~0.2 s |
| Hybrid fusion | 0.04 s | 0.04 s |
| Reranking | 6.6 s | ~1 s |

An already-warmed BM25 index taking five minutes means it was evicted to the pagefile — the clearest
signal that the model and the retrieval stack do not fit in RAM together.

**Ollama and the retrieval stack compete for the same RAM.** Ollama keeps a model resident after a
query (`keep_alive`), so on a memory-tight machine a loaded 5 GB model can starve the backend's own
startup — the BM25 and ChromaDB loads slow to a crawl or stall. Symptoms are a warmup that never
reaches `ready` and a large pagefile. Check with:

```bash
curl http://localhost:11434/api/ps          # is a model resident, and how big?
```

To free it without stopping Ollama:

```bash
curl http://localhost:11434/api/generate -d '{"model":"mistral","keep_alive":0}'
```

Budget roughly: ~2 GB for the retrieval stack (torch, both transformer models, ChromaDB, BM25) plus
the model size. Under about 8 GB total, a 7B model leaves no headroom.

A smaller model helps far more than a longer timeout. Measured on an 8 GB laptop (i5-1235U,
CPU-only, no GPU offload), same query, same 3500-char prompt budget and `LLM_MAX_TOKENS=300`:

| Model | Size | Result |
| ----- | ---- | ------ |
| `mistral` (7.2B) | 5.0 GB | **Failed** — `ReadTimeout` at 423 s, 0 tokens generated |
| `qwen2.5:3b` (3.1B) | 1.9 GB | **106 s** — correct grounded answer (load 8.8 s, prompt eval 895 tok / 62.6 s, generate 98 tok / 32.9 s) |

The 7B model is not slow so much as *absent*: it does not fit alongside the retrieval stack, so the
machine swaps instead of computing. Switching models needs no code change:

```bash
ollama pull qwen2.5:3b        # ~1.9 GB instead of ~5 GB
# then set OLLAMA_MODEL=qwen2.5:3b in .env and restart the backend
```

When generation fails, `/api/chat` returns `generation_status: "failed"` with an `llm_error`, and
the console shows a generation-failure notice with the retrieved evidence still listed — rather than
scoring the fallback text as an unsupported claim.

### Frontend — API base URL

`frontend/src/services/api.ts` reads `VITE_API_BASE_URL` and falls back to
`http://127.0.0.1:8000/api`. Note the value must include the `/api` path segment.

```bash
# frontend/.env
VITE_API_BASE_URL=https://securerag.example.com/api
VITE_CHAT_TIMEOUT_MS=600000
```

| Variable | Effect | Default |
| -------- | ------ | ------- |
| `VITE_API_BASE_URL` | Backend base URL — must include the `/api` segment | `http://127.0.0.1:8000/api` |
| `VITE_CHAT_TIMEOUT_MS` | Browser abort for the whole `/api/chat` request | `600000` (10 min) |

Vite inlines these at build time, so change them before `npm run build`, not after.

### Tuning retrieval

Every stage takes a dataclass config, so behavior can be changed per call without touching module
code:

```python
from modules import pipeline
from modules.Retrieval import dense_retriever, hybrid_fusion, reranker, sparse_retriever

cfg = pipeline.SecureRAGPipelineConfig(
    dense_config=dense_retriever.DenseRetrieverConfig(top_k=20),
    sparse_config=sparse_retriever.SparseRetrieverConfig(top_k=10),
    fusion_config=hybrid_fusion.HybridFusionConfig(rrf_k=40, top_k=15),
    reranker_config=reranker.RerankerConfig(top_k=10),
)
response = pipeline.run("How should we prioritize CVE-2021-44228?", config=cfg)
```

---

## Python Usage

### End-to-end pipeline

```bash
python modules/pipeline.py "How should we prioritize CVE-2021-44228?"
```

```python
from modules.pipeline import run

response = run("How should we prioritize CVE-2021-44228?")
print(response.final_answer)
print(response.confidence_score)
print(response.verification_report)
```

### Individual stages from the CLI

```bash
python modules/Retrieval/dense_retriever.py "CVE-2021-44228"
python modules/Retrieval/sparse_retriever.py "CVE-2021-44228"
python modules/Retrieval/hybrid_fusion.py "CVE-2021-44228"
python modules/Retrieval/reranker.py "CVE-2021-44228"
python modules/Generation/prompt_template.py "CVE-2021-44228"
python modules/Generation/llm_chain.py "CVE-2021-44228"
python modules/Verification/hallucination_guard.py "CVE-2021-44228"
```

### Prioritization and runbooks

```python
from modules.priority_scorer import WEIGHTS_MAIN, rank_cves, score_cve
from modules.patch_explainer import generate_priority_report
from modules.runbook_generator import generate_runbook

score_cve("CVE-2021-44228", WEIGHTS_MAIN)
rank_cves(["CVE-2021-44228", "CVE-2022-26134", "CVE-2023-44487"], WEIGHTS_MAIN)
generate_priority_report(["CVE-2021-44228"], WEIGHTS_MAIN)
generate_runbook("ransomware")
```

### Querying the indexes directly

```python
import chromadb
from sentence_transformers import SentenceTransformer

client = chromadb.PersistentClient(path="embeddings/chroma_db")
collection = client.get_collection(name="secure_rag_chunks")

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
results = collection.query(
    query_embeddings=model.encode(["Log4Shell remote code execution"]),
    n_results=5,
    include=["documents", "metadatas", "distances"],
)
```

```python
import pickle

with open("data/embeddings/bm25.pkl", "rb") as f:
    bm25 = pickle.load(f)
with open("data/embeddings/corpus.pkl", "rb") as f:
    corpus = pickle.load(f)

scores = bm25.get_scores("Log4Shell RCE".lower().split())
```

---

## Evaluation

The benchmark is `evaluation/phase6_queries.json` — **300 queries**, evenly split across 100
`cve_explanation`, 100 `mitre_mapping`, and 100 `incident_response` items.

### Retrieval quality (dense mode, 300 queries)

| Metric       | Value     |
| ------------ | --------- |
| Recall@5     | 93.33%    |
| Recall@10    | 93.33%    |
| MRR          | 0.9333    |
| Precision@5  | 34.53%    |
| Precision@10 | 18.03%    |
| NDCG@5       | 1.4033    |
| NDCG@10      | 1.4287    |
| Hit@1        | 93.33%    |
| Avg latency  | 162.32 ms |

### By category

| Category                | Recall@5 | MRR  | NDCG@5 | Status              |
| ----------------------- | -------- | ---- | ------ | ------------------- |
| CVE explanation (100)   | 100%     | 1.00 | 1.7259 | Production ready    |
| MITRE mapping (100)     | 100%     | 1.00 | 1.1375 | Production ready    |
| Incident response (100) | 80%      | 0.80 | 1.3465 | Needs optimization  |

**Known failure mode.** All 20 IR failures (IR_021–IR_040) share one root cause: cross-domain
mismatch. A query like *"IR procedure for MITRE T1012 exploitation"* expects the CVE that exploits
T1012, but chunking keeps MITRE and CVE records separate, so dense similarity returns the technique
chunk instead. This is an index/query mismatch, not a retriever defect — hybrid dense+sparse
retrieval and explicit CVE↔technique relationship chunks are the planned fixes. Full write-up:
[evaluation/results/PAPER_RESULTS.md](evaluation/results/PAPER_RESULTS.md).

### Prioritization scoring (60-CVE sample, ground truth = CISA KEV `date_added`)

| Metric                     | Value                    |
| -------------------------- | ------------------------ |
| Weights                    | cvss 0.3 / epss 0.5 / kev 0.2 |
| Spearman ρ                 | −0.3923 (p = 0.0019)     |
| Kendall τ                  | −0.2780 (p = 0.0017)     |
| Category ordering accuracy | 100%                     |

Every KEV-listed CVE outranked every non-KEV CVE. The negative rank correlation is expected — KEV
addition date measures *when CISA catalogued* a vulnerability, not how urgent it is today, so it is
a weak proxy for patch priority.

### Running evaluations

```bash
# Validate the benchmark dataset (strict: 300 queries, 100 per category)
python evaluation/validate_phase6_dataset.py

# Retrieval evaluation — modes: dense | sparse | hybrid | full | all
python evaluation/phase6_retrieval_evaluation.py --mode all
python evaluation/run_full_evaluation.py --mode all --experiment-name my_run

# RAGAS: faithfulness, answer relevancy, context precision (requires Ollama)
python evaluation/phase6_ragas.py --limit 50

# Prioritization evaluation and validation studies
python eval/phase6_priority_evaluation.py
python eval/validate_prioritizer.py

# Hyperparameter search and targeted RRF tuning
python evaluation/hyperparameter_search.py --max-trials 12
python evaluation/tune_rrf.py

# Baseline vs tuned config on the identical benchmark
python evaluation/phase6_baseline_vs_final.py

# Reporting
python evaluation/phase6_failure_analysis.py     # → evaluation/FAILURE_ANALYSIS.md
python evaluation/generate_paper_results.py      # → evaluation/results/PAPER_RESULTS.md
python evaluation/compare_results.py
python evaluation/visualize_results.py

# Wall-clock API latency (independent of the research metrics)
python evaluation/benchmark_runtime.py --endpoint retrieve --runs 5 --top-k 10
```

Experiment artifacts land in timestamped directories under `evaluation/experiments/`; aggregate
metrics, CSVs, and plots in `evaluation/results/`.

### Baseline vs tuned configuration

| Parameter             | Baseline  | Tuned     |
| --------------------- | --------- | --------- |
| Dense top-k           | 10        | 20        |
| Sparse top-k          | 10        | 10        |
| Fusion top-k          | 15        | 15        |
| RRF k                 | 60        | 40        |
| Dense / sparse weight | 0.5 / 0.5 | 0.6 / 0.6 |
| Reranker top-k        | 5         | 10        |
| Reranker alpha        | 0.85      | 0.75      |
| Metadata boost        | 0.15      | 0.0       |

---

## Testing

```bash
.\.venv\Scripts\pytest tests/test_phase6.py -v
```

Seven tests, all passing: benchmark dataset validation, MRR/NDCG computation on controlled inputs,
priority-scorer correlation output, and the `/api/health`, `/api/cve/{id}`, `/api/mitre/{id}`, and
`/api/priority` endpoints.

Frontend checks:

```bash
cd frontend
npm run lint          # oxlint
npx tsc --noEmit      # type check
npm run build
```

---

## Troubleshooting

**`Connection refused` on port 8000** — the backend is not running:

```bash
.\.venv\Scripts\uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

**First query is very slow** — warmup has not finished. Check `GET /api/health` and wait for
`warmup.status: "ready"`. If you set `SECURERAG_SKIP_WARMUP=1`, the cost moves to the first query
instead.

Warmup loads the chunk payload, the BM25 index, the tokenized corpus, ChromaDB and both transformer
models. On a memory-constrained machine this is slow — measured on an 8 GB laptop with almost no
free RAM, a cold warmup took **16 minutes**:

| Stage | Measured |
| ----- | -------- |
| `chunks_ms` (chunks.json, ~770 MB) | 520 s |
| `tokenized_corpus_ms` | 208 s |
| `bm25_index_ms` | 131 s |
| `embedding_model_ms` | 114 s |
| `cross_encoder_ms` | 6 s |
| `chroma_collection_ms` | 5 s |

With adequate free RAM these are seconds, not minutes. A warmup measured in minutes is a memory
signal — see the Ollama contention note under [Configuration](#configuration).

**The answer is "Not found in retrieved evidence." even though the evidence panel shows the right
chunks** — this is a *generation* failure, not a retrieval or verification one. Check
`generation_status` in the `/api/chat` response: `"failed"` means the Ollama call errored and
`llm_error` says why. The usual cause is the generation timeout being too short for CPU-only
inference — see [Generation timeouts on CPU-only hardware](#generation-timeouts-on-cpu-only-hardware).

If you see the literal text *"LLM generation is temporarily unavailable"* inside a claim, you are
running a build from before this was fixed: the guarded fallback string was being scored against the
evidence and reported as an unsupported claim.

**Generation, runbooks, or patch explanations fail** — Ollama is not reachable:

```bash
ollama serve
ollama pull mistral
curl http://localhost:11434/api/tags     # confirm the model in OLLAMA_MODEL is listed
```

Retrieval, CVE lookup, MITRE lookup, and prioritization still work without it.

**Chat requests time out** — CPU-only generation is slow and the machine may be swapping. Check free
RAM; a 7B model needs ~5 GB on top of the ~2 GB the retrieval stack holds. Close memory-heavy apps,
or switch to a smaller `OLLAMA_MODEL`. Raise `LLM_TIMEOUT_SECONDS` *and* `CHAT_TIMEOUT_MS` together —
raising only the backend value lets the browser abort first.

**Empty retrieval results** — the knowledge base has not been built. Verify:

```bash
ls embeddings/chroma_db/      # expect chroma.sqlite3 and a UUID directory
python modules/Chunking/verify_embeddings.py
```

**`MITRE dataset not found`** — `data/processed/mitre.json` is missing; run
`python modules/ingestion/ingest_mitre.py`.

**Evaluation endpoints return empty objects** — no results files yet. Run the evaluation scripts
above to populate `evaluation/results/`.

**CORS errors in the browser** — add the frontend origin to `ALLOWED_ORIGINS` in `.env` and restart
the backend.

**Frontend cannot reach the API** — confirm `VITE_API_BASE_URL` includes the `/api` suffix, and
rebuild (Vite inlines env values at build time).

### Expected performance

| Operation                        | Latency     |
| -------------------------------- | ----------- |
| CVE lookup                       | 100–200 ms  |
| MITRE technique lookup           | 100–200 ms  |
| Evidence retrieval               | ~160 ms     |
| Chat / full RAG                  | 500–2000 ms |
| Frontend load (production build) | < 2 s       |

---

## Roadmap

Delivered:

- CTI ingestion across NVD, MITRE ATT&CK, CISA KEV, and EPSS
- Chunking, embedding, ChromaDB vector store, and BM25 index over 414,854 chunks
- Hybrid retrieval with RRF and cross-encoder reranking
- Grounded generation with post-hoc hallucination verification
- CVE prioritization, patch explanations, and NIST CSF 2.0 runbooks
- FastAPI backend (9 endpoints) and React analyst console (8 views)
- 300-query evaluation harness with RAGAS, hyperparameter search, and failure analysis

Planned:

- Hybrid dense + sparse retrieval as the default serving mode — expected to recover ~90% of the
  IR-query failures
- CVE↔technique relationship chunks to close the cross-domain mismatch
- Memory optimization for sparse and hybrid modes at full corpus scale
- Domain-adapted embeddings fine-tuned on security text

---

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Monal Prashanth.

CTI data is sourced from NVD, MITRE ATT&CK, CISA KEV, and FIRST.org EPSS; each remains subject to
its own terms of use.
