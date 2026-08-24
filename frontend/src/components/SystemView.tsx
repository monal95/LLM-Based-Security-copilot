import { RefreshCw } from 'lucide-react';
import { API_BASE } from '../services/api';
import { NAV_ITEMS } from '../navigation';
import type { HealthResponse } from '../types';
import {
  Badge,
  ErrorNote,
  KeyValues,
  NotAvailable,
  PageHeader,
  Section,
} from './ui';
import {
  NA,
  fmtMs,
  fmtText,
} from '../lib/format';

interface SystemViewProps {
  health: HealthResponse | null;
  backendOnline: boolean | null;
  onRefresh: () => void;
}

const WARMUP_TONE = {
  ready: 'low',
  running: 'medium',
  failed: 'critical',
  not_started: 'neutral',
} as const;

export function SystemView({ health, backendOnline, onRefresh }: SystemViewProps) {
  const models = (health?.models ?? {}) as Record<string, string>;
  const warmupState = health?.warmup ?? null;
  const warmupStages = Object.entries(warmupState?.stages ?? {});

  return (
    <div className="view-stack">
      <PageHeader
        title="System"
        description="Backend connection, model configuration and the API surface this console depends on."
        actions={
          <button type="button" className="btn" onClick={onRefresh}>
            <RefreshCw size={14} aria-hidden="true" />
            Check connection
          </button>
        }
      />

      {backendOnline === false && (
        <ErrorNote message="The backend API did not respond. Start it with: uvicorn backend.main:app --host 0.0.0.0 --port 8000" />
      )}

      <div className="two-col">
        <Section title="Connection" description="Configured through the VITE_API_BASE_URL environment variable.">
          <KeyValues
            rows={[
              { key: 'API base URL', value: API_BASE, mono: true },
              {
                key: 'Status',
                value: backendOnline === null ? 'Checking' : backendOnline ? 'Connected' : 'Unreachable',
              },
              { key: 'Reported status', value: fmtText(health?.status) },
              { key: 'Service', value: fmtText(health?.service) },
              { key: 'Version', value: fmtText(health?.version), mono: true },
            ]}
          />
        </Section>

        <Section title="Models and indexes" description="Reported by GET /api/health.">
          <KeyValues
            rows={[
              { key: 'Embedding model', value: fmtText(models.embedding), mono: true },
              { key: 'Reranker', value: fmtText(models.reranker), mono: true },
              { key: 'Generator', value: fmtText(models.llm), mono: true },
              { key: 'Index', value: fmtText(health?.database) },
            ]}
          />
        </Section>
      </div>

      <Section
        title="Startup warmup"
        description="Models and indexes are loaded once at startup so analyst queries do not pay for it."
        actions={
          warmupState ? (
            <Badge tone={WARMUP_TONE[warmupState.status] ?? 'neutral'}>{warmupState.status.replace(/_/g, ' ').toUpperCase()}</Badge>
          ) : undefined
        }
      >
        {!warmupState ? (
          <NotAvailable
            what="the backend did not report warmup state"
            reason="Warmup reporting requires a backend build that includes backend/warmup.py."
          />
        ) : (
          <>
            <KeyValues
              rows={[
                { key: 'Status', value: warmupState.status.replace(/_/g, ' ') },
                { key: 'Total warmup time', value: fmtMs(warmupState.elapsed_ms), mono: true },
                { key: 'Components loaded', value: String(warmupStages.length), mono: true },
              ]}
            />

            {warmupState.error && (
              <div style={{ marginTop: 12 }}>
                <ErrorNote message={warmupState.error} />
              </div>
            )}

            {warmupStages.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <p className="label" style={{ marginBottom: 6 }}>Measured load times</p>
                <KeyValues
                  rows={warmupStages.map(([stage, ms]) => ({
                    key: stage.replace(/_ms$/, '').replace(/_/g, ' '),
                    value: fmtMs(ms),
                    mono: true,
                  }))}
                />
              </div>
            )}
          </>
        )}
      </Section>

      <Section title="API surface" description="Each console view and the endpoint it calls." flush>
        <div className="table-scroll">
          <table className="table">
            <caption className="sr-only">Console views and their backend endpoints</caption>
            <thead>
              <tr>
                <th scope="col">View</th>
                <th scope="col">Endpoint</th>
              </tr>
            </thead>
            <tbody>
              {NAV_ITEMS.map((item) => (
                <tr key={item.id}>
                  <td>{item.label}</td>
                  <td className="mono">{item.endpoint}</td>
                </tr>
              ))}
              <tr>
                <td>IR runbook</td>
                <td className="mono">GET /api/runbook/{'{incident_type}'}</td>
              </tr>
              <tr>
                <td>Baseline comparison</td>
                <td className="mono">GET /api/evaluation/baseline-vs-final</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Raw health response" description="Unmodified payload from the backend.">
        {health ? (
          <pre
            className="mono"
            style={{
              fontSize: '0.75rem',
              lineHeight: 1.6,
              background: 'var(--surface-sunken)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              padding: 12,
              overflowX: 'auto',
            }}
          >
            {JSON.stringify(health, null, 2)}
          </pre>
        ) : (
          <p className="meta">{NA} — no health payload has been received.</p>
        )}
      </Section>
    </div>
  );
}
