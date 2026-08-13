import React from 'react';
import {
  Database,
  ShieldCheck,
  Zap,
  Activity,
  Layers,
  Cpu,
  ArrowUpRight,
  Lock,
} from 'lucide-react';

interface DashboardViewProps {
  onNavigate: (tab: string) => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({ onNavigate }) => {
  const statCards = [
    {
      title: 'Vulnerabilities Indexed',
      value: '366,669',
      sub: 'NVD CVEs ingested & embedded',
      icon: Database,
      color: 'var(--accent-cyan)',
    },
    {
      title: 'CISA KEV Exploited',
      value: '1,647',
      sub: 'Active exploited vulnerabilities',
      icon: ShieldCheck,
      color: 'var(--accent-amber)',
    },
    {
      title: 'MITRE ATT&CK Techniques',
      value: '697',
      sub: 'Enterprise tactics & mitigations',
      icon: Layers,
      color: 'var(--accent-purple)',
    },
    {
      title: 'Hallucination Guard',
      value: '100% Active',
      sub: 'Claim-level verification engine',
      icon: Lock,
      color: 'var(--accent-green)',
    },
  ];

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto', padding: '32px 24px', display: 'flex', flexDirection: 'column', gap: '32px' }}>
      {/* Hero Banner */}
      <div className="glass-panel" style={{ padding: '36px', background: 'linear-gradient(135deg, rgba(17,22,34,0.9), rgba(121,40,202,0.15))', border: '1px solid rgba(0, 242, 254, 0.25)', position: 'relative', overflow: 'hidden' }}>
        <div style={{ position: 'absolute', right: '-40px', top: '-40px', width: '300px', height: '300px', background: 'radial-gradient(circle, rgba(0,242,254,0.15) 0%, rgba(0,0,0,0) 70%)', pointerEvents: 'none' }} />
        
        <div style={{ maxWidth: '800px' }}>
          <span className="badge badge-cyan" style={{ marginBottom: '12px' }}>
            <Zap size={13} /> SecureRAG Phase VI Production Engine
          </span>
          <h2 style={{ fontSize: '2.2rem', fontWeight: 800, marginBottom: '12px', letterSpacing: '-0.03em', lineHeight: 1.2 }}>
            Hallucination-Safe AI Copilot for Cybersecurity Operations
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '1.05rem', marginBottom: '24px', maxWidth: '750px' }}>
            Grounding SOC analyst queries with NVD vulnerability data, CISA KEV real-time exploitation flags, EPSS probabilities, and MITRE ATT&CK technique mappings using hybrid dense/sparse retrieval and claim-level verification.
          </p>

          <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap' }}>
            <button className="btn-primary" onClick={() => onNavigate('chat')}>
              Launch SOC Copilot <ArrowUpRight size={18} />
            </button>
            <button className="btn-secondary" onClick={() => onNavigate('priority')}>
              View Patch Priority Table
            </button>
            <button className="btn-secondary" onClick={() => onNavigate('evaluation')}>
              Inspect Evaluation Benchmark
            </button>
          </div>
        </div>
      </div>

      {/* Stat Cards Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '20px' }}>
        {statCards.map((card, idx) => {
          const Icon = card.icon;
          return (
            <div key={idx} className="glass-panel" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 500 }}>{card.title}</span>
                <div style={{ width: '36px', height: '36px', borderRadius: '8px', background: 'rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Icon size={20} color={card.color} />
                </div>
              </div>
              <div style={{ fontSize: '2rem', fontWeight: 800, color: '#fff', letterSpacing: '-0.02em' }}>
                {card.value}
              </div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                {card.sub}
              </div>
            </div>
          );
        })}
      </div>

      {/* Architecture Flow Diagram */}
      <div className="glass-panel" style={{ padding: '28px' }}>
        <h3 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Cpu size={20} color="var(--accent-cyan)" /> SecureRAG Pipeline Architecture
        </h3>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px' }}>
          {[
            { step: '01. Analyst Query', desc: 'Query expansion & ID detection (CVE / Technique)', color: '#00f2fe' },
            { step: '02. Hybrid Retrieval', desc: 'ChromaDB Dense + BM25 Sparse RRF Fusion', color: '#4facfe' },
            { step: '03. Cross-Encoder', desc: 'ms-marco Reranking + Metadata Boosting', color: '#7928ca' },
            { step: '04. LLM Generation', desc: 'Grounded Mistral Prompt Construction', color: '#ff0080' },
            { step: '05. Hallucination Guard', desc: 'Token overlap verification & Claim reporting', color: '#10b981' },
          ].map((item, index) => (
            <div
              key={index}
              style={{
                background: 'rgba(10, 13, 20, 0.6)',
                border: '1px solid var(--border-color)',
                borderRadius: '10px',
                padding: '16px',
                position: 'relative',
              }}
            >
              <div style={{ fontSize: '0.8rem', fontWeight: 700, color: item.color, marginBottom: '6px' }}>
                {item.step}
              </div>
              <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                {item.desc}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
