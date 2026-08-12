# Phase VI — SecureRAG Evaluation & Deployment Guide

This directory contains the reproducible benchmark artifacts, evaluation scripts, and paper-ready results for **Phase VI: SecureRAG Evaluation, React UI, Deployment, and Paper Results**.

---

## 1. System Environment & Specifications

- **Evaluation Date**: 2026-08-12
- **Operating System**: Windows / Linux compatible
- **Python Version**: Python 3.13+ (Virtual Environment `.venv`)
- **Node.js Version**: Node.js v22.14.0, npm 11.1.0
- **Primary Models**:
  - **Embedding Model**: `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)
  - **Cross-Encoder Reranker**: `cross-encoder/ms-marco-MiniLM-L-6-v2`
  - **LLM Generator**: `mistral` via Ollama (`http://localhost:11434`)
- **Evaluation Dataset**: `evaluation/phase6_queries.json` (300 queries: 100 CVE, 100 ATT&CK, 100 IR)

---

## 2. Reproducibility Workflow & Execution Commands

### Step 1: Validate 300-Query Benchmark Dataset
```bash
.\.venv\Scripts\python.exe evaluation/validate_phase6_dataset.py
```
*Output*: Validates exactly 300 queries (100 CVE explanation, 100 ATT&CK mapping, 100 incident response), verifies non-empty ground truth, and checks entity existence in NVD/KEV/MITRE datasets.

---

### Step 2: Execute Retrieval Evaluation (4 Modes)
```bash
.\.venv\Scripts\python.exe -m evaluation.phase6_retrieval_evaluation --mode all
```
*Output*:
- `evaluation/results/phase6_retrieval_results.json`
- `evaluation/results/phase6_retrieval_results.csv`
- `evaluation/results/retrieval_failures.json`

---

### Step 3: Execute RAGAS Evaluation
```bash
.\.venv\Scripts\python.exe evaluation/phase6_ragas.py
```
*Output*:
- `evaluation/results/phase6_ragas_results.json`
- `evaluation/results/phase6_ragas_results.csv`

---

### Step 4: Execute Priority Scoring Evaluation
```bash
.\.venv\Scripts\python.exe eval/phase6_priority_evaluation.py
```
*Output*:
- `evaluation/results/phase6_priority_results.json`

---

### Step 5: Generate Baseline vs Final Comparison
```bash
.\.venv\Scripts\python.exe evaluation/phase6_baseline_vs_final.py
```
*Output*:
- `evaluation/results/baseline_vs_final.json`
- `evaluation/results/baseline_vs_final.csv`
- `evaluation/results/baseline_vs_final.png`

---

### Step 6: Generate Failure Analysis & Paper Results
```bash
.\.venv\Scripts\python.exe evaluation/phase6_failure_analysis.py
.\.venv\Scripts\python.exe evaluation/generate_paper_results.py
```
*Output*:
- `evaluation/FAILURE_ANALYSIS.md`
- `evaluation/results/PAPER_RESULTS.md`

---

### Step 7: Run Test Suite
```bash
.\.venv\Scripts\pytest.exe tests/test_phase6.py -v
```

---

## 3. Production Deployment Commands

### Backend API (FastAPI)
```bash
.\.venv\Scripts\uvicorn.exe backend.main:app --host 0.0.0.0 --port 8000 --reload
```
API Documentation available at: `http://localhost:8000/docs`

### Frontend Application (React + Vite)
```bash
cd frontend
npm install
npm run dev
```
Frontend Web UI available at: `http://localhost:5173`

---

## 4. Key Artifact Locations

- **Paper Results Table**: [PAPER_RESULTS.md](file:///d:/Project/SOC_Analyst/evaluation/results/PAPER_RESULTS.md)
- **Failure Analysis Report**: [FAILURE_ANALYSIS.md](file:///d:/Project/SOC_Analyst/evaluation/FAILURE_ANALYSIS.md)
- **Baseline vs Final Plot**: [baseline_vs_final.png](file:///d:/Project/SOC_Analyst/evaluation/results/baseline_vs_final.png)
- **Phase 6 Audit**: [PHASE6_AUDIT.md](file:///d:/Project/SOC_Analyst/evaluation/PHASE6_AUDIT.md)
