import React, { useState } from 'react';
import {
  Send,
  ShieldCheck,
  AlertTriangle,
  FileText,
  Clock,
  Sparkles,
  Database,
  CheckCircle,
  HelpCircle,
} from 'lucide-react';
import { sendChatMessage } from '../services/api';
import type { ChatResponse } from '../types';

export const CopilotChatView: React.FC = () => {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [chatResponse, setChatResponse] = useState<ChatResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sampleQueries = [
    'What is CVE-2021-44228?',
    'How should we prioritize Log4Shell vs Zerologon?',
    'Explain MITRE ATT&CK technique T1190.',
    'What containment steps should a SOC analyst execute during a ransomware attack?',
  ];

  const handleSend = async (textToSend?: string) => {
    const qText = (textToSend || query).trim();
    if (!qText) return;

    setLoading(true);
    setError(null);
    try {
      const res = await sendChatMessage(qText);
      setChatResponse(res);
    } catch (err: any) {
      setError(err.message || 'Failed to communicate with SecureRAG pipeline');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto', padding: '32px 24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header & Quick Chips */}
      <div>
        <h2 style={{ fontSize: '1.8rem', fontWeight: 800, marginBottom: '6px' }}>
          SOC Copilot Chat
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.92rem', marginBottom: '16px' }}>
          Ask vulnerability, threat intelligence, or incident response questions with automated hallucination verification.
        </p>

        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Sparkles size={14} color="var(--accent-cyan)" /> Try:
          </span>
          {sampleQueries.map((sample, idx) => (
            <button
              key={idx}
              onClick={() => {
                setQuery(sample);
                handleSend(sample);
              }}
              style={{
                background: 'rgba(255, 255, 255, 0.04)',
                border: '1px solid var(--border-color)',
                borderRadius: '20px',
                padding: '4px 12px',
                fontSize: '0.78rem',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              {sample}
            </button>
          ))}
        </div>
      </div>

      {/* Main Input Box */}
      <div className="glass-panel" style={{ padding: '20px' }}>
        <div style={{ display: 'flex', gap: '12px' }}>
          <input
            type="text"
            className="input-field"
            placeholder="Ask SecureRAG (e.g., 'What is CVE-2021-44228 and how to patch it?')..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            disabled={loading}
          />
          <button className="btn-primary" onClick={() => handleSend()} disabled={loading}>
            {loading ? <Clock size={18} className="spin" /> : <Send size={18} />}
            {loading ? 'Analyzing...' : 'Query Copilot'}
          </button>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div style={{ padding: '16px', borderRadius: '10px', background: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', color: 'var(--accent-red)', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <AlertTriangle size={20} />
          <span>{error}</span>
        </div>
      )}

      {/* Response Panel */}
      {chatResponse && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '24px' }}>
          {/* Main Answer Column */}
          <div className="glass-panel" style={{ padding: '28px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* Header / Query Bar */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)', paddingBottom: '16px' }}>
              <div>
                <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Analyst Query
                </span>
                <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#fff' }}>
                  "{chatResponse.query}"
                </h3>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span className="badge badge-green">
                  <ShieldCheck size={14} /> {(chatResponse.confidence_score * 100).toFixed(1)}% Confidence
                </span>
                <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  {chatResponse.total_latency_ms.toFixed(0)} ms
                </span>
              </div>
            </div>

            {/* Answer Content */}
            <div style={{ background: 'rgba(10, 13, 20, 0.5)', padding: '20px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
              <h4 style={{ fontSize: '0.85rem', color: 'var(--accent-cyan)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <FileText size={16} /> Verified Technical Answer
              </h4>

              <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6, fontSize: '0.95rem', color: 'var(--text-primary)' }}>
                {chatResponse.final_answer}
              </div>
            </div>

            {/* Claim Verification Reports */}
            {chatResponse.claim_reports.length > 0 && (
              <div>
                <h4 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px' }}>
                  Claim-Level Grounding Verification
                </h4>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {chatResponse.claim_reports.map((claim) => (
                    <div
                      key={claim.claim_id}
                      style={{
                        padding: '12px 16px',
                        borderRadius: '8px',
                        background: 'rgba(255, 255, 255, 0.02)',
                        border: '1px solid var(--border-color)',
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: '12px',
                      }}
                    >
                      {claim.status === 'Verified' ? (
                        <CheckCircle size={18} color="var(--accent-green)" style={{ marginTop: '2px' }} />
                      ) : claim.status === 'Partially Verified' ? (
                        <AlertTriangle size={18} color="var(--accent-amber)" style={{ marginTop: '2px' }} />
                      ) : (
                        <HelpCircle size={18} color="var(--accent-red)" style={{ marginTop: '2px' }} />
                      )}

                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: '0.88rem', fontWeight: 500, color: '#fff', marginBottom: '4px' }}>
                          {claim.claim_text}
                        </div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                          Status: <strong style={{ color: claim.status === 'Verified' ? 'var(--accent-green)' : 'var(--accent-amber)' }}>{claim.status}</strong> | Support Score: {(claim.support_score * 100).toFixed(0)}%
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Diagnostics Side Drawer */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* Counts Panel */}
            <div className="glass-panel" style={{ padding: '20px' }}>
              <h4 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Database size={16} color="var(--accent-cyan)" /> Evidence Pipeline Counts
              </h4>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {[
                  { label: 'Dense Chunks (ChromaDB)', count: chatResponse.counts.dense },
                  { label: 'Sparse Chunks (BM25)', count: chatResponse.counts.sparse },
                  { label: 'Fused Chunks (RRF)', count: chatResponse.counts.fused },
                  { label: 'Reranked Chunks (Cross-Encoder)', count: chatResponse.counts.reranked },
                ].map((item, idx) => (
                  <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                    <span style={{ color: 'var(--text-muted)' }}>{item.label}</span>
                    <span className="font-mono" style={{ fontWeight: 600, color: 'var(--accent-cyan)' }}>{item.count}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Verification Summary Panel */}
            <div className="glass-panel" style={{ padding: '20px' }}>
              <h4 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '16px' }}>
                Verification Summary
              </h4>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <div style={{ background: 'rgba(16, 185, 129, 0.1)', padding: '12px', borderRadius: '8px', textAlign: 'center' }}>
                  <div style={{ fontSize: '1.2rem', fontWeight: 800, color: 'var(--accent-green)' }}>
                    {chatResponse.verification_report.verified}
                  </div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Verified Claims</div>
                </div>

                <div style={{ background: 'rgba(239, 68, 68, 0.1)', padding: '12px', borderRadius: '8px', textAlign: 'center' }}>
                  <div style={{ fontSize: '1.2rem', fontWeight: 800, color: 'var(--accent-red)' }}>
                    {chatResponse.verification_report.unsupported}
                  </div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Unsupported</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
