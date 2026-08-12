import {
  ChatResponse,
  CveDetails,
  EvaluationResults,
  MitreTechnique,
  PriorityItem,
  RetrievalItem,
  RunbookResponse,
} from '../types';

const API_BASE = 'http://localhost:8000/api';

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
    const err = await res.json();
    throw new Error(err.detail || 'Chat execution failed');
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
    const err = await res.json();
    throw new Error(err.detail || `CVE ${cveId} not found`);
  }
  return res.json();
}

export async function fetchMitreTechnique(techniqueId: string): Promise<MitreTechnique> {
  const res = await fetch(`${API_BASE}/mitre/${encodeURIComponent(techniqueId)}`);
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || `Technique ${techniqueId} not found`);
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
    const err = await res.json();
    throw new Error(err.detail || 'Runbook generation failed');
  }
  return res.json();
}
