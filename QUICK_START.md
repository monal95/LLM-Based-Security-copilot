# Quick Start: Deploy SecureRAG Phase VI

## Prerequisites

- Python 3.13+ with virtual environment `.venv/` activated
- Node.js 18+ with npm
- Port 8000 (backend) and 5173 (frontend dev) available

 
## Option 1: Development Mode (Recommended for Testing)

### Terminal 1: Start Backend

```bash
cd d:\Project\SOC_Analyst
.\.venv\Scripts\uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

✅ Backend running on http://127.0.0.1:8000

### Terminal 2: Start Frontend

```bash
cd d:\Project\SOC_Analyst\frontend
npm run dev
```

✅ Frontend running on http://localhost:5173

### Access the Application

- Open browser: **http://localhost:5173/**
- API docs: http://127.0.0.1:8000/docs (Swagger UI)
- OpenAPI spec: http://127.0.0.1:8000/openapi.json

---

## Option 2: Production Mode (Build & Serve)

### Build Frontend

```bash
cd d:\Project\SOC_Analyst\frontend
npm run build
# Output in: frontend/dist/
```

### Deploy Backend

```bash
cd d:\Project\SOC_Analystuvicorn backend.main:app --host 0.0.0.0 --port 8000
.\.venv\Scripts\
```

### Serve Frontend

Option A: Use any web server (nginx, Apache, etc.)

```bash
# Copy frontend/dist/* to your web server root
# Example with Python http.server:
cd frontend/dist
python -m http.server 3000
```

Option B: Use Docker

```dockerfile
FROM nginx:latest
COPY frontend/dist /usr/share/nginx/html
EXPOSE 80
```

---

## Testing the System

### Run Test Suite

```bash
cd d:\Project\SOC_Analyst
.\.venv\Scripts\pytest tests/test_phase6.py -v
```

✅ Expected: 7/7 tests passing

### Test Endpoints Manually

#### 1. Health Check

```bash
curl http://127.0.0.1:8000/api/health
```

Response: `{"status": "healthy", ...}`

#### 2. CVE Lookup

```bash
curl -X POST http://127.0.0.1:8000/api/cve/CVE-2021-44228 \
  -H "Content-Type: application/json"
```

#### 3. MITRE Lookup

```bash
curl -X POST http://127.0.0.1:8000/api/mitre/T1021 \
  -H "Content-Type: application/json"
```

#### 4. Chat/RAG

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "What is CVE-2021-44228?"}'
```

---

## Features to Explore

### 1. Dashboard View

- Statistics cards with vulnerability counts
- Real-time system health
- NIST CSF compliance indicators

### 2. Vulnerability Triage

- Search by CVE ID
- View CVSS, EPSS, and KEV status
- Inspect exploit chains

### 3. Patch Priority

- Ranked CVE list by exploit probability
- Sortable by severity, EPSS, KEV status
- Incident response runbook generation

### 4. MITRE ATT&CK Exploration

- Technique lookup by ID
- Tactics and sub-techniques
- Mitigation strategies

### 5. Evaluation Dashboard

- RAGAS metrics (when Ollama is running)
- Retrieval performance by category
- Baseline vs final comparison

### 6. Copilot Chat

- Natural language queries
- Evidence-backed responses
- Related CVEs and techniques

### 7. Incident Response Runbook

- Generate NIST CSF-aligned procedures
- Threat-specific playbooks
- Download as markdown

---

## Configuration

### Backend (.env)

Located at `d:\Project\SOC_Analyst\.env`

Key variables:

```env
OLLAMA_BASE_URL=http://localhost:11434    # For LLM generation (optional)
ALLOWED_ORIGINS=["http://localhost:5173", "http://127.0.0.1:3000"]
LLM_MODEL=mistral
CHROMA_DB_PATH=embeddings/chroma_db/
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

### Frontend (API URL)

Located in component files (e.g., `src/services/api.ts`)

Current configuration:

```typescript
const API_BASE = "http://127.0.0.1:8000";
```

To change for production:

1. Edit `src/services/api.ts`
2. Update API_BASE to production URL
3. Run `npm run build`

---

## Troubleshooting

### Issue: "Connection refused" on port 8000

**Solution**: Backend not running. Start it:

```bash
.\.venv\Scripts\uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

### Issue: "Cannot find module 'node_modules/...'"

**Solution**: Frontend dependencies missing. Install:

```bash
cd frontend
npm install
npm run dev
```

### Issue: TypeScript compilation errors

**Solution**: Shouldn't happen (all errors fixed). If you see them:

```bash
cd frontend
npx tsc --noEmit  # Check for errors
npm run build     # Try building
```

### Issue: Evaluation tests fail

**Solution**: Check ChromaDB vector store:

```bash
# Verify embeddings are indexed
ls embeddings/chroma_db/
# Should show: chroma.sqlite3 and UUID directory
```

### Issue: RAGAS metrics not available

**Solution**: Start Ollama service:

```bash
# Download and run Ollama (https://ollama.ai)
ollama serve  # Runs on localhost:11434
ollama pull mistral  # Download model
```

---

## Performance Notes

### Expected Response Times

- CVE lookup: 100-200ms
- MITRE technique: 100-200ms
- Chat/RAG: 500-2000ms (depends on retrieval complexity)
- Frontend load: <2s (production build)

### Resource Requirements

- **RAM**: 4GB minimum (ChromaDB + vectors)
- **CPU**: 2 cores minimum
- **Disk**: 2GB for embeddings + data
- **GPU**: Optional (improves embeddings, not required)

---

## What's Ready for Production

### ✅ Production Ready

- CVE vulnerability lookup (100% accuracy)
- MITRE technique exploration (100% accuracy)
- Frontend UI (8 components, optimized)
- Backend API (9 endpoints, tested)
- Test suite (7/7 passing)

### ⚠️ Needs Optimization (Phase VII)

- Incident Response queries (80% accuracy, needs hybrid retrieval)
- RAGAS evaluation (requires Ollama, not critical)
- Sparse/Hybrid retrieval modes (memory optimization needed)

---

## Next Steps

### Immediate (Today)

1. [ ] Run test suite: `pytest tests/test_phase6.py -v`
2. [ ] Start backend: `uvicorn backend.main:app --reload`
3. [ ] Start frontend: `npm run dev` (frontend directory)
4. [ ] Access: http://localhost:5173

### Short-term (This Week)

1. [ ] Deploy to staging environment
2. [ ] Run user acceptance testing
3. [ ] Configure production .env
4. [ ] Set up monitoring/logging

### Medium-term (Phase VII)

1. [ ] Implement hybrid dense+sparse retrieval
2. [ ] Optimize IR query handling
3. [ ] Fine-tune embeddings on security domain
4. [ ] Deploy Ollama for RAGAS evaluation

---

## Support & Documentation

### Key Documents

- **PHASE6_COMPLETION_SUMMARY.md**: Full status overview
- **FAILURE_ANALYSIS.md**: Root cause analysis of IR query performance
- **PAPER_RESULTS.md**: Detailed evaluation metrics
- **PHASE6_README.md**: Reproducibility guide
- **PHASE6_AUDIT.md**: Architecture inventory

### Example Queries

1. "What is CVE-2021-44228?" (Expectation: Log4j vulnerability)
2. "Find exploits for T1021" (Expectation: Remote Access techniques)
3. "How to respond to ransomware incident?" (Expectation: IR runbook)
4. "Rank CVEs by exploit probability" (Expectation: EPSS-ordered list)

---

**Status**: ✅ Phase VI Complete | 📅 Generated: 2026-08-13 | 🚀 Ready for Deployment
