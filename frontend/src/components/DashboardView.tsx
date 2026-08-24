import { useEffect, useState } from 'react';
import { Activity, AlertTriangle, Crosshair, Database, Gauge, Timer } from 'lucide-react';
import { fetchEvaluationResults } from '../services/api';
import type { EvaluationResults } from '../types';
import type { ViewId } from '../navigation';
import type { HealthResponse } from '../types';
import { headlineMode, listModes, modeLabel } from '../lib/evaluation';
import type { PrioritySummary } from '../lib/evaluation';
import {
  ErrorNote,
  Grid,
  KeyValues,
  NotAvailable,
  PageHeader,
  Section,
  StatCard,
} from './ui';
import {
  NA,
  fmtFixed,
  fmtInt,
  fmtMs,
  fmtPct,
  fmtText,
} from '../lib/format';

interface DashboardViewProps {
  health: HealthResponse | null;
  backendOnline: boolean | null;
  onNavigate: (view: ViewId) => void;
}

/** Stages of the implemented retrieval pipeline, in execution order. */
const PIPELINE_STAGES = [
  { step: '1', name: 'Query analysis', detail: 'Expansion, CVE and technique ID detection' },
  { step: '2', name: 'Hybrid retrieval', detail: 'ChromaDB dense vectors and BM25 sparse, fused with RRF' },
  { step: '3', name: 'Reranking', detail: 'Cross-encoder ms-marco-MiniLM-L-6-v2' },
  { step: '4', name: 'Generation', detail: 'Evidence-grounded prompt, Mistral via Ollama' },
  { step: '5', name: 'Verification', detail: 'Claim-level grounding check before the answer is shown' },
];

export function DashboardView({ health, backendOnline, onNavigate }: DashboardViewProps) {
  const [evaluation, setEvaluation] = useState<EvaluationResults | null>(null);
  const [evalError, setEvalError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchEvaluationResults()
      .then((data) => {
        if (!cancelled) {
          setEvaluation(data);
          setEvalError(null);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setEvalError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const modes = listModes(evaluation?.retrieval as Record<string, unknown> | undefined);
  const headline = headlineMode(modes);
  const priority = (evaluation?.priority ?? {}) as PrioritySummary;
  const models = (health?.models ?? {}) as Record<string, string>;

  return (
    <div className="view-stack">
      <PageHeader
        title="Dashboard"
        description="Operational state of the SecureRAG retrieval and verification pipeline, with the most recent benchmark results served by the backend."
        actions={
          <>
            <button type="button" className="btn" onClick={() => onNavigate('chat')}>
              Open analyst console
            </button>
            <button type="button" className="btn" onClick={() => onNavigate('evaluation')}>
              View evaluation
            </button>
          </>
        }
      />

      {backendOnline === false && (
        <ErrorNote message="The backend API is unreachable. Start it with: uvicorn backend.main:app --host 0.0.0.0 --port 8000" />
      )}

      <Grid min={210}>
        <StatCard
          label="Pipeline status"
          value={backendOnline === null ? 'Checking' : backendOnline ? 'Operational' : 'Offline'}
          sub={fmtText(health?.service)}
          icon={<Activity size={14} />}
        />
        <StatCard
          label="Queries benchmarked"
          value={fmtInt(headline?.total_queries)}
          sub={headline ? `${modeLabel(headline.mode)} retrieval` : 'No evaluation run loaded'}
          icon={<Database size={14} />}
        />
        <StatCard
          label="Recall@5"
          value={fmtPct(headline?.recall_5, 2)}
          sub="Expected document within top 5"
          icon={<Crosshair size={14} />}
        />
        <StatCard
          label="MRR"
          value={fmtFixed(headline?.mrr, 4)}
          sub="Mean reciprocal rank"
          icon={<Gauge size={14} />}
        />
        <StatCard
          label="Retrieval latency"
          value={fmtMs(headline?.avg_latency_ms)}
          sub="Mean per query"
          icon={<Timer size={14} />}
        />
        <StatCard
          label="Prioritization correlation"
          value={fmtFixed(priority.spearman_rho, 4)}
          sub={priority.sample_size ? `Spearman rho, n = ${priority.sample_size}` : 'Spearman rho'}
          icon={<AlertTriangle size={14} />}
        />
      </Grid>

      {evalError && <ErrorNote message={`Evaluation results unavailable: ${evalError}`} />}

      <div className="two-col">
        <Section title="Runtime configuration" description="Reported by GET /api/health.">
          <KeyValues
            rows={[
              { key: 'Service', value: fmtText(health?.service) },
              { key: 'Version', value: fmtText(health?.version), mono: true },
              { key: 'Embedding model', value: fmtText(models.embedding), mono: true },
              { key: 'Reranker', value: fmtText(models.reranker), mono: true },
              { key: 'Generator', value: fmtText(models.llm), mono: true },
              { key: 'Index', value: fmtText(health?.database) },
            ]}
          />
        </Section>

        <Section
          title="Knowledge base coverage"
          description="Corpus counts for NVD, CISA KEV and MITRE ATT&CK."
        >
          <NotAvailable
            what="corpus record counts are not exposed by the API"
            reason="No backend endpoint reports ingested record totals, so no count is shown here. Add a stats endpoint to backend/main.py if these figures are needed on the dashboard."
          />
        </Section>
      </div>

      <Section title="Retrieval pipeline" description="Stages executed for every analyst query.">
        <ol style={{ listStyle: 'none', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 8 }}>
          {PIPELINE_STAGES.map((stage) => (
            <li
              key={stage.step}
              style={{
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                padding: '10px 12px',
                background: 'var(--surface-sunken)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                <span className="num" style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>{stage.step}</span>
                <span style={{ fontSize: '0.8125rem', fontWeight: 600 }}>{stage.name}</span>
              </div>
              <p className="meta" style={{ marginTop: 4 }}>{stage.detail}</p>
            </li>
          ))}
        </ol>
      </Section>

      {headline?.category_breakdown && (
        <Section title="Recall by query category" description={`${modeLabel(headline.mode)} retrieval, Recall@5.`} flush>
          <div className="table-scroll">
            <table className="table">
              <caption className="sr-only">Recall at 5 broken down by benchmark query category</caption>
              <thead>
                <tr>
                  <th scope="col">Category</th>
                  <th scope="col" className="align-right">Queries</th>
                  <th scope="col" className="align-right">Recall@5</th>
                  <th scope="col" className="align-right">MRR</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(headline.category_breakdown).map(([category, metrics]) => (
                  <tr key={category}>
                    <td>{category.replace(/_/g, ' ')}</td>
                    <td className="align-right num">{fmtInt(metrics.count)}</td>
                    <td className="align-right num">{fmtPct(metrics.recall_5, 2)}</td>
                    <td className="align-right num">{fmtFixed(metrics.mrr, 4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {!headline && !evalError && (
        <Section title="Benchmark results">
          <p className="meta">
            {NA} — no evaluation run has been loaded from the backend yet.
          </p>
        </Section>
      )}
    </div>
  );
}
