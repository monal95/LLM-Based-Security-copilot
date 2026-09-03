import type {
  ChatResponse,
  CveDetails,
  EvaluationResults,
  MitreTechnique,
  PriorityItem,
  RetrievalItem,
  RunbookResponse,
} from '../types';

export const API_BASE = (import.meta.env.VITE_API_BASE_URL?.trim() || 'http://127.0.0.1:8000/api').replace(/\/$/, '');

async function safeErrorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const data = await res.json();
    if (data && typeof data.detail === 'string' && data.detail.trim()) {
      return data.detail;
    }
  } catch {
    // Response body may not be JSON; fall back to generic message.
  }
  return fallback;
}

export async function checkHealth(): Promise<any> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error('Backend offline');
  return res.json();
}

/**
 * Client abort ceiling for /api/chat.
 *
 * This must cover the WHOLE request - retrieval, fusion, reranking AND
 * generation - not just the backend's LLM_TIMEOUT_SECONDS. On a
 * memory-constrained host the retrieval stages alone have been measured at
 * over 400s (paging the BM25 index back in while a 5 GB model is resident),
 * so a ceiling sized only to the generation timeout aborts a request the
 * backend would still have completed.
 *
 * Override with VITE_CHAT_TIMEOUT_MS when the default does not fit the host.
 */
const CHAT_TIMEOUT_MS = Number(import.meta.env.VITE_CHAT_TIMEOUT_MS) || 600_000;

export async function sendChatMessage(query: string): Promise<ChatResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timeoutId);
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new Error(
        `Request timed out after ${CHAT_TIMEOUT_MS / 1000} seconds. ` +
          'CPU-only generation is slow — close memory-heavy apps and retry, ' +
          'or set a smaller OLLAMA_MODEL in .env.',
      );
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
  if (!res.ok) {
    throw new Error(await safeErrorMessage(res, 'Chat execution failed'));
  }
  return res.json();
}

export async function fetchEvidence(query: string, top_k = 5): Promise<RetrievalItem[]> {
  const res = await fetch(`${API_BASE}/retrieve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, top_k }),
  });
  if (!res.ok) throw new Error('Evidence retrieval failed');
  const data = await res.json();
  return data.results || [];
}

export async function fetchCveDetails(cveId: string): Promise<CveDetails> {
  const res = await fetch(`${API_BASE}/cve/${encodeURIComponent(cveId)}`);
  if (!res.ok) {
    throw new Error(await safeErrorMessage(res, `CVE ${cveId} not found`));
  }
  return res.json();
}

export async function fetchMitreTechnique(techniqueId: string): Promise<MitreTechnique> {
  const res = await fetch(`${API_BASE}/mitre/${encodeURIComponent(techniqueId)}`);
  if (!res.ok) {
    throw new Error(await safeErrorMessage(res, `Technique ${techniqueId} not found`));
  }
  return res.json();
}

export async function fetchPriorityRankings(cveList: string[]): Promise<PriorityItem[]> {
  const res = await fetch(`${API_BASE}/priority`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cve_ids: cveList, explain: true }),
  });
  if (!res.ok) throw new Error('Priority ranking failed');
  const data = await res.json();
  return data.ranked_cves || [];
}

export async function fetchEvaluationResults(): Promise<EvaluationResults> {
  const res = await fetch(`${API_BASE}/evaluation`);
  if (!res.ok) throw new Error('Evaluation results fetch failed');
  return res.json();
}

export async function fetchBaselineVsFinal(): Promise<any> {
  const res = await fetch(`${API_BASE}/evaluation/baseline-vs-final`);
  if (!res.ok) throw new Error('Baseline vs Final comparison fetch failed');
  return res.json();
}

export async function generateRunbook(incidentType: string): Promise<RunbookResponse> {
  const res = await fetch(`${API_BASE}/runbook/${encodeURIComponent(incidentType)}`);
  if (!res.ok) {
    throw new Error(await safeErrorMessage(res, 'Runbook generation failed'));
  }
  return res.json();
}
