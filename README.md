# SecureRAG CTI Processing Pipeline

## Project Status

- Phase 1 (CTI Ingestion): Completed
- Phase 2 (Knowledge Base and Indexing): Completed
- Phase 4 (Retrieval, Generation, Verification Pipeline): Completed

This repository implements a comprehensive pipeline for ingesting, processing, and indexing cyber threat intelligence (CTI) data for retrieval-augmented generation (RAG) applications. The pipeline consists of two main modules:

## Modules Overview

### Module 1: CTI Ingestion

Ingests and normalizes threat intelligence from four sources:

- NVD CVEs (National Vulnerability Database Common Vulnerabilities and Exposures)
- MITRE ATT&CK (Adversarial Tactics, Techniques, and Common Knowledge)
- CISA KEV (Cybersecurity and Infrastructure Security Agency Known Exploited Vulnerabilities)
- EPSS (Exploit Prediction Scoring System)

### Module 2: CTI Processing & Indexing

Processes the ingested CTI data through a pipeline that:

1. **Chunks** the CTI documents into retrievable passages
2. **Embeds** the chunks using sentence transformers for semantic search
3. **Indexes** the embeddings in a vector database (ChromaDB) for similarity search
4. **Indexes** the chunks in a BM25 index for keyword search
5. **Verifies** the quality and completeness of the generated artifacts

### Phase 4: Secure Retrieval and Verified Generation

Implements the complete secure answer pipeline for SOC analysts:

1. **Dense Retrieval** from ChromaDB using semantic embeddings
2. **Sparse Retrieval** from BM25 index using keyword matching
3. **Hybrid Fusion** using Reciprocal Rank Fusion (RRF)
4. **Cross-Encoder Reranking** for final evidence prioritization
5. **Prompt Construction** with strict grounding policy
6. **Mistral via Ollama** for grounded response generation
7. **Hallucination Guard** to verify claims against retrieved evidence

## Retrieval Evaluation Workflow

The evaluation framework writes reproducible experiment outputs under `evaluation/experiments/`.

Run the main evaluation suite:

```bash
py -3 evaluation/evaluate_retrieval.py --mode all --print-table
```

Compare saved experiments:

```bash
py -3 evaluation/compare_results.py
```

Generate plots for recall, precision, MRR, nDCG, and latency:

```bash
py -3 evaluation/visualize_results.py
```

Run hyperparameter tuning and save the best configuration:

```bash
py -3 evaluation/hyperparameter_search.py
```

The compatibility entrypoints `evaluation/run_full_evaluation.py` and `evaluation/tune_rrf.py` are still available if you prefer the older scripts.

## Project Layout

```
├── data/
│   ├── chunks/                   # Chunked CTI documents (JSON)
│   ├── embeddings/               # Embedded chunks and BM25 index (pickle files)
│   ├── processed/                # Normalized JSON output from ingestion
│   └── raw/                      # Raw downloaded source data
├── embeddings/
│   └── chroma_db/                # Persistent ChromaDB vector store
├── modules/
│   ├── Chunking/                 # Module 2: Processing and indexing
│   │   ├── chunker.py            # CTI chunking (Module 2.1)
│   │   ├── embedder.py           # Dense embedding generation (Module 2.2)
│   │   ├── vector_store.py       # ChromaDB vector storage (Module 2.3)
│   │   ├── bm25_index.py         # BM25 keyword indexing (Module 2.4)
│   │   ├── verify_embeddings.py  # Verification of outputs (Module 2.5)
│   │   └── build_knowledge_base.py # Module 2 pipeline orchestration
│   ├── Retrieval/                # Module 3: Retrieval
│   │   ├── dense_retriever.py    # Module 3.1
│   │   ├── sparse_retriever.py   # Module 3.2
│   │   ├── hybrid_fusion.py      # Module 3.3
│   │   └── reranker.py           # Module 3.4
│   ├── Generation/               # Module 4: Generation
│   │   ├── prompt_template.py    # Module 4.1
│   │   └── llm_chain.py          # Module 4.2
│   ├── Verification/             # Module 4: Verification
│   │   └── hallucination_guard.py # Module 4.3
│   ├── pipeline.py               # End-to-end SecureRAG orchestration
│   └── ingestion/                # Module 1: CTI ingestion
│       ├── __init__.py
│       ├── __main__.py           # Entry point for `python -m modules.ingestion`
│       ├── epss_fetcher.py       # EPSS ingestion
│       ├── ingest_kev.py         # CISA KEV ingestion
│       ├── ingest_mitre.py       # MITRE ATT&CK ingestion
│       ├── ingest_nvd.py         # NVD CVE ingestion
│       └── verify_sources.py     # Ingestion validation
├── tests/                        # Test files
└── eval/                         # Evaluation scripts
```

## Requirements

- Python 3.13 (recommended)
- pip
- See `requirements.txt` for Python package dependencies

## Installation

Create and activate a virtual environment, then install the package requirements:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

If `python` is not available on your PATH, use the Python Launcher:

```bash
py -3 -m venv .venv
.venv\Scripts\activate
py -3 -m pip install -r requirements.txt
```

## Module 1: CTI Ingestion

### How To Ingest Data

Run each ingestion script from the repository root:

```bash
py -3 modules/ingestion/ingest_nvd.py
py -3 modules/ingestion/ingest_mitre.py
py -3 modules/ingestion/ingest_kev.py
py -3 modules/ingestion/epss_fetcher.py
```

**Recommended order:**

1. NVD
2. MITRE
3. KEV
4. EPSS

You can also run all ingestions sequentially using the module entry point:

```bash
py -3 -m modules.ingestion
```

This will run all ingestions and then verify the generated datasets.

### Importing as a Package

```python
from modules.ingestion import fetch_all_cves, ingest_mitre, ingest_kev, fetch_epss, verify_sources

fetch_all_cves()
ingest_mitre()
ingest_kev()
fetch_epss()
verify_sources()
```

### Source Behavior

- **NVD**: Uses the NVD API 2.0 with pagination and local page caching
- **MITRE**: Downloads the ATT&CK Enterprise STIX 2.1 JSON bundle from GitHub
- **CISA KEV**: Downloads the official KEV JSON feed
- **EPSS**: Uses the bulk gzipped CSV download as primary source, falls back to FIRST.org API

### NVD API Key

The NVD ingester reads `NVD_API_KEY` from the environment:

```bash
set NVD_API_KEY=your_api_key_here
```

If the key is not set, the script still works but runs more slowly due to stricter rate limiting.

### Outputs

Each script writes two files:

- `data/raw/<source>_raw.json` - raw downloaded data
- `data/processed/<source>.json` - normalized JSON output

The NVD ingester also uses temporary page cache files under `data/raw/nvd_pages/`.

## Module 2: CTI Processing & Indexing

Module 2 processes the output from Module 1 to create a searchable knowledge base.

### Running the Full Module 2 Pipeline

To run the complete processing pipeline (chunking → embedding → vector storage → BM25 indexing → verification):

```bash
py -3 modules/Chunking/build_knowledge_base.py
```

### Individual Module Steps

You can also run each step independently:

#### Step 1: Chunking (Module 2.1)

```bash
py -3 modules/Chunking/chunker.py
```

Creates `data/chunks/chunks.json` with chunked CTI documents.

#### Step 2: Embedding Generation (Module 2.2)

```bash
py -3 modules/Chunking/embedder.py
```

Generates embeddings and saves to `data/embeddings/embedded_chunks.pkl`.

#### Step 3: Vector Storage (Module 2.3)

```bash
py -3 modules/Chunking/vector_store.py
```

Builds persistent ChromaDB vector store in `embeddings/chroma_db/`.

#### Step 4: BM25 Indexing (Module 2.4)

```bash
py -3 modules/Chunking/bm25_index.py
```

Creates BM25 index (`data/embeddings/bm25.pkl`) and tokenized corpus (`data/embeddings/corpus.pkl`).

#### Step 5: Verification (Module 2.5)

```bash
py -3 modules/Chunking/verify_embeddings.py
```

Verifies the generated artifacts and reports on their quality.

### Accessing the Processed Data

#### Vector Store (ChromaDB)

```python
import chromadb
from sentence_transformers import SentenceTransformer

# Load the persistent client and collection
client = chromadb.PersistentClient(path="embeddings/chroma_db")
collection = client.get_collection(name="secure_rag_chunks")

# Example query
query_text = "Log4Shell remote code execution vulnerability"
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
query_embedding = model.encode([query_text])

results = collection.query(
    query_embeddings=query_embedding,
    n_results=5,
    include=["documents", "metadatas", "distances"]
)
```

#### BM25 Index

```python
import pickle
from rank_bm25 import BM25Okapi

# Load the BM25 index and tokenized corpus
with open("data/embeddings/bm25.pkl", "rb") as f:
    bm25 = pickle.load(f)

with open("data/embeddings/corpus.pkl", "rb") as f:
    corpus = pickle.load(f)

# Example query
query = "Log4Shell RCE"
tokenized_query = query.lower().split()
scores = bm25.get_scores(tokenized_query)
top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:5]
```

## Verification

After running the pipeline, you can verify the outputs using:

```bash
py -3 modules/Chunking/verify_embeddings.py
```

This will check:

- File existence and sizes
- Embedding dimension (should be 384)
- ChromaDB collection count and sample data
- Semantic search capability (testing for Log4Shell CVE-2021-44228)
- BM25 index functionality

## Pipeline Orchestration

For end-to-end execution of both modules:

```bash
# Step 1: Ingest all CTI data
py -3 -m modules.ingestion

# Step 2: Process and index the ingested data
py -3 modules/Chunking/build_knowledge_base.py
```

Or run the individual steps as needed based on your workflow requirements.

## Phase 4: Retrieval and Verified Generation

### End-to-End SecureRAG Flow

```
User Query
    -> Dense Retrieval (ChromaDB)
    -> Sparse Retrieval (BM25)
    -> Hybrid Fusion (RRF)
    -> Cross-Encoder Reranking
    -> Prompt Builder
    -> Mistral (Ollama)
    -> Hallucination Guard
    -> Final Verified Answer
```

### Run Complete SecureRAG Pipeline

```bash
py -3 modules/pipeline.py "How should we prioritize CVE-2021-44228?"
```

### Run Phase 4 Modules Individually

Dense retrieval:

```bash
py -3 modules/Retrieval/dense_retriever.py "CVE-2021-44228"
```

Sparse retrieval:

```bash
py -3 modules/Retrieval/sparse_retriever.py "CVE-2021-44228"
```

Hybrid fusion:

```bash
py -3 modules/Retrieval/hybrid_fusion.py "CVE-2021-44228"
```

Cross-encoder reranking:

```bash
py -3 modules/Retrieval/reranker.py "CVE-2021-44228"
```

Prompt construction:

```bash
py -3 modules/Generation/prompt_template.py "CVE-2021-44228"
```

LLM chain (Ollama Mistral):

```bash
py -3 modules/Generation/llm_chain.py "CVE-2021-44228"
```

Hallucination guard:

```bash
py -3 modules/Verification/hallucination_guard.py "CVE-2021-44228"
```

### Security and Reliability Notes

- The generated answer is always post-processed by the hallucination guard.
- Unsupported claims are removed or replaced with explicit non-verified text.
- If context is insufficient, the system returns: `Not found in retrieved evidence.`
- Retrieval and generation stages implement failure-safe fallbacks and structured diagnostics.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details
