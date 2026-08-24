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

export async function sendChatMessage(query: string): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  });
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
