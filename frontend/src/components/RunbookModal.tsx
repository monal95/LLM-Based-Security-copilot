import React, { useState } from 'react';
import {
  BookOpen,
  Download,
  Shield,
  Clock,
  CheckCircle2,
  X,
} from 'lucide-react';
import { generateRunbook } from '../services/api';
import { RunbookResponse } from '../types';

interface RunbookModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const RunbookModal: React.FC<RunbookModalProps> = ({ isOpen, onClose }) => {
  const [incidentType, setIncidentType] = useState('ransomware');
  const [runbook, setRunbook] = useState<RunbookResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activePhase, setActivePhase] = useState<'containment' | 'eradication' | 'recovery' | 'evidence' | 'notification'>('containment');

  if (!isOpen) return null;

  const handleGenerate = async (typeToGen?: string) => {
    const targetType = typeToGen || incidentType;
    setLoading(true);
    setError(null);
    try {
      const data = await generateRunbook(targetType);
      setRunbook(data);
    } catch (err: any) {
      setError(err.message || 'Runbook generation failed');
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadMarkdown = () => {
    if (!runbook) return;
    const content = `# Incident Response Playbook: ${runbook.incident_type.toUpperCase()}
Generated: ${runbook.timestamp}
Framework: NIST CSF 2.0 Aligned

## 1. CONTAINMENT
${runbook.phases.containment.map((s, i) => `${i + 1}. ${s}`).join('\n')}

## 2. ERADICATION
${runbook.phases.eradication.map((s, i) => `${i + 1}. ${s}`).join('\n')}

## 3. RECOVERY
${runbook.phases.recovery.map((s, i) => `${i + 1}. ${s}`).join('\n')}

## 4. EVIDENCE PRESERVATION
${runbook.phases.evidence.map((s, i) => `${i + 1}. ${s}`).join('\n')}

## 5. NOTIFICATION
${runbook.phases.notification.map((s, i) => `${i + 1}. ${s}`).join('\n')}
`;

    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `IR_Runbook_${runbook.incident_type}_NIST_CSF2.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(6px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200, padding: '20px' }}>
      <div className="glass-panel-glow" style={{ maxWidth: '850px', width: '100%', maxHeight: '90vh', overflowY: 'auto', padding: '32px', background: 'var(--bg-surface)' }}>
        {/* Modal Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', paddingBottom: '16px', marginBottom: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <BookOpen size={24} color="var(--accent-cyan)" />
            <div>
              <h3 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#fff' }}>
                Incident Response Runbook Generator
              </h3>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                NIST CSF 2.0 Aligned Playbook Synthesized from Retrieved Evidence
              </p>
            </div>
          </div>

          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
            <X size={24} />
          </button>
        </div>

        {/* Type selector bar */}
        <div style={{ display: 'flex', gap: '10px', marginBottom: '24px', flexWrap: 'wrap' }}>
          {['ransomware', 'phishing', 'data_breach', 'supply_chain'].map((type) => (
            <button
              key={type}
              onClick={() => {
                setIncidentType(type);
                handleGenerate(type);
              }}
              style={{
                padding: '8px 16px',
                borderRadius: '8px',
                border: incidentType === type ? '1px solid var(--accent-cyan)' : '1px solid var(--border-color)',
                background: incidentType === type ? 'rgba(0, 242, 254, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                color: incidentType === type ? 'var(--accent-cyan)' : 'var(--text-secondary)',
                fontWeight: incidentType === type ? 600 : 400,
                cursor: 'pointer',
                textTransform: 'capitalize',
              }}
            >
              {type.replace('_', ' ')}
            </button>
          ))}
        </div>

        {loading && (
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
            <Clock size={24} className="spin" style={{ marginBottom: '12px' }} />
            <div>Synthesizing NIST CSF 2.0 Runbook via Ollama Mistral...</div>
          </div>
        )}

        {error && (
          <div style={{ padding: '16px', borderRadius: '8px', background: 'rgba(239, 68, 68, 0.15)', color: 'var(--accent-red)', marginBottom: '20px' }}>
            {error}
          </div>
        )}

        {/* Runbook Output */}
        {runbook && !loading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* Action Bar */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="badge badge-green">
                <CheckCircle2 size={14} /> NIST CSF 2.0 Compliant
              </span>

              <button className="btn-primary" onClick={handleDownloadMarkdown}>
                <Download size={16} /> Download IR Runbook (.md)
              </button>
            </div>

            {/* Phase Tabs */}
            <div style={{ display: 'flex', gap: '6px', borderBottom: '1px solid var(--border-color)' }}>
              {(['containment', 'eradication', 'recovery', 'evidence', 'notification'] as const).map((phase) => (
                <button
                  key={phase}
                  onClick={() => setActivePhase(phase)}
                  style={{
                    padding: '8px 12px',
                    borderBottom: activePhase === phase ? '2px solid var(--accent-cyan)' : '2px solid transparent',
                    color: activePhase === phase ? 'var(--accent-cyan)' : 'var(--text-muted)',
                    background: 'none',
                    borderLeft: 'none',
                    borderRight: 'none',
                    borderTop: 'none',
                    fontWeight: activePhase === phase ? 600 : 400,
                    fontSize: '0.85rem',
                    cursor: 'pointer',
                    textTransform: 'capitalize',
                  }}
                >
                  {phase}
                </button>
              ))}
            </div>

            {/* Phase Content */}
            <div style={{ background: 'rgba(10, 13, 20, 0.6)', padding: '20px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
              <ul style={{ display: 'flex', flexDirection: 'column', gap: '12px', listStyle: 'none' }}>
                {runbook.phases[activePhase].map((step, i) => (
                  <li key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', fontSize: '0.92rem', color: 'var(--text-primary)' }}>
                    <span className="font-mono" style={{ color: 'var(--accent-cyan)', fontWeight: 700 }}>
                      {i + 1}.
                    </span>
                    <span>{step}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
