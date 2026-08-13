export interface ClaimReport {
  claim_id: number;
  claim_text: string;
  status: 'Verified' | 'Partially Verified' | 'Unsupported';
  support_score: number;
  matched_evidence_indices: number[];
  rationale: string;
}

export interface VerificationReport {
  total_claims: number;
  verified: number;
  partially_verified: number;
  unsupported: number;
  confidence_score: number;
}

export interface ChatResponse {
  query: string;
  final_answer: string;
  confidence_score: number;
  verification_report: VerificationReport;
  claim_reports: ClaimReport[];
  counts: {
    dense: number;
    sparse: number;
    fused: number;
    reranked: number;
  };
  total_latency_ms: number;
  generated_at_utc: string;
}

export interface RetrievalItem {
  rank: number;
  score: number;
  retrieval_score: number;
  text: string;
  metadata: Record<string, any>;
  chunk_id?: string;
  fused_rank?: number;
}

export interface CveDetails {
  cve_id: string;
  cvss_score: number;
  epss_score: number;
  epss_percentile?: number;
  kev_flag: boolean;
  priority_score: number;
  description: string;
  published_date: string;
  severity: string;
  affected_products: string[];
}

export interface PriorityItem {
  rank: number;
  cve_id: string;
  cvss_score: number;
  epss_score: number;
  kev_flag: number;
  priority_score: number;
  explanation?: string;
  rank_signals?: Record<string, any>;
}

export interface MitreTechnique {
  technique_id: string;
  name: string;
  description: string;
  tactics: string[];
  sub_techniques?: string[];
  mitigations?: Array<{ mitigation_id: string; name: string }>;
  platforms?: string[];
  url?: string;
}

export interface RunbookPhase {
  containment: string[];
  eradication: string[];
  recovery: string[];
  evidence: string[];
  notification: string[];
}

export interface RunbookResponse {
  incident_type: string;
  phases: RunbookPhase;
  context_sources: Array<{ rank: number; chunk_id: string; source?: string }>;
  timestamp: string;
}

export interface EvaluationResults {
  retrieval: Record<string, any>;
  ragas: {
    faithfulness: number;
    answer_relevancy: number;
    context_precision: number;
    context_recall: number;
  };
  priority: {
    spearman_rho: number;
    spearman_pvalue: number;
    sample_size: number;
    top5_overlap: number;
    category_ordering_accuracy: number;
  };
}
