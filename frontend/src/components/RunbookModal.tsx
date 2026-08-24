import { useState } from 'react';
import { Download } from 'lucide-react';
import { generateRunbook } from '../services/api';
import type { RunbookPhase, RunbookResponse } from '../types';
import { Modal } from './Modal';
import {
  EmptyState,
  ErrorNote,
  LoadingRow,
  Spinner,
} from './ui';
import {
  NA,
  fmtText,
} from '../lib/format';

interface RunbookModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const INCIDENT_TYPES = ['ransomware', 'phishing', 'data_breach', 'supply_chain'];

const PHASES: Array<{ id: keyof RunbookPhase; label: string }> = [
  { id: 'containment', label: 'Containment' },
  { id: 'eradication', label: 'Eradication' },
  { id: 'recovery', label: 'Recovery' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'notification', label: 'Notification' },
];

export function RunbookModal({ isOpen, onClose }: RunbookModalProps) {
  const [incidentType, setIncidentType] = useState('ransomware');
  const [runbook, setRunbook] = useState<RunbookResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activePhase, setActivePhase] = useState<keyof RunbookPhase>('containment');

  const handleGenerate = async (type?: string) => {
    const target = type ?? incidentType;
    setIncidentType(target);
    setLoading(true);
    setError(null);

    try {
      setRunbook(await generateRunbook(target));
      setActivePhase('containment');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Runbook generation failed');
      setRunbook(null);
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = () => {
    if (!runbook) return;

    const section = (title: string, steps: string[]) =>
      `## ${title}\n${steps.map((step, index) => `${index + 1}. ${step}`).join('\n')}\n`;

    const content = [
      `# Incident Response Runbook: ${runbook.incident_type.toUpperCase()}`,
      `Generated: ${runbook.timestamp}`,
      'Framework: NIST CSF 2.0',
      '',
      ...PHASES.map((phase) => section(phase.label, runbook.phases[phase.id] ?? [])),
    ].join('\n');

    const url = URL.createObjectURL(new Blob([content], { type: 'text/markdown' }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `IR_Runbook_${runbook.incident_type}.md`;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  };

  const steps = runbook?.phases?.[activePhase] ?? [];

  return (
    <Modal
      open={isOpen}
      title="Incident response runbook"
      description="NIST CSF 2.0 aligned procedure generated from retrieved evidence."
      onClose={onClose}
      width={760}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            Close
          </button>
          <button type="button" className="btn btn-primary" onClick={handleDownload} disabled={!runbook}>
            <Download size={14} aria-hidden="true" />
            Download Markdown
          </button>
        </>
      }
    >
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
        {INCIDENT_TYPES.map((type) => (
          <button
            key={type}
            type="button"
            className={type === incidentType ? 'btn btn-sm btn-primary' : 'btn btn-sm'}
            onClick={() => handleGenerate(type)}
            disabled={loading}
          >
            {type.replace(/_/g, ' ')}
          </button>
        ))}
      </div>

      {error && <ErrorNote message={error} />}

      {loading && <LoadingRow message="Generating runbook…" />}

      {!loading && !runbook && !error && (
        <EmptyState
          title="No runbook generated"
          message="Select an incident type to generate a procedure from the retrieved evidence."
          action={
            <button type="button" className="btn" onClick={() => handleGenerate()} disabled={loading}>
              {loading ? <Spinner /> : null}
              Generate {incidentType.replace(/_/g, ' ')} runbook
            </button>
          }
        />
      )}

      {runbook && !loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div role="tablist" aria-label="Runbook phases" style={{ display: 'flex', gap: 2, borderBottom: '1px solid var(--border)', flexWrap: 'wrap' }}>
            {PHASES.map((phase) => {
              const isActive = phase.id === activePhase;
              return (
                <button
                  key={phase.id}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => setActivePhase(phase.id)}
                  style={{
                    padding: '7px 11px',
                    fontFamily: 'inherit',
                    fontSize: '0.8125rem',
                    fontWeight: isActive ? 600 : 400,
                    color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                    background: 'none',
                    border: 'none',
                    borderBottom: `2px solid ${isActive ? 'var(--accent)' : 'transparent'}`,
                    cursor: 'pointer',
                    marginBottom: -1,
                  }}
                >
                  {phase.label}
                </button>
              );
            })}
          </div>

          {steps.length ? (
            <ol style={{ paddingLeft: 20, display: 'flex', flexDirection: 'column', gap: 7 }}>
              {steps.map((step, index) => (
                <li key={index} style={{ fontSize: '0.8125rem', lineHeight: 1.6 }}>
                  {step}
                </li>
              ))}
            </ol>
          ) : (
            <p className="meta">{NA} — no steps were generated for this phase.</p>
          )}

          {runbook.context_sources?.length ? (
            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 10 }}>
              <p className="label" style={{ marginBottom: 6 }}>
                Evidence used ({runbook.context_sources.length} chunks)
              </p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {runbook.context_sources.map((source) => (
                  <span
                    key={source.chunk_id}
                    className="mono"
                    style={{
                      fontSize: '0.6875rem',
                      border: '1px solid var(--border)',
                      background: 'var(--surface-sunken)',
                      borderRadius: 3,
                      padding: '2px 6px',
                      color: 'var(--text-secondary)',
                    }}
                  >
                    [{source.rank}] {fmtText(source.source ?? source.chunk_id)}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          <p className="meta">Generated {fmtText(runbook.timestamp)}</p>
        </div>
      )}
    </Modal>
  );
}
