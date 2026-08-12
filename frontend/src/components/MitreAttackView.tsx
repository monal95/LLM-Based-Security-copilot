import React, { useState } from 'react';
import {
  ShieldAlert,
  Search,
  ExternalLink,
  Layers,
  CheckSquare,
  Globe,
  Clock,
} from 'lucide-react';
import { fetchMitreTechnique } from '../services/api';
import { MitreTechnique } from '../types';

export const MitreAttackView: React.FC = () => {
  const [techId, setTechId] = useState('T1190');
  const [technique, setTechnique] = useState<MitreTechnique | null>({
    technique_id: 'T1190',
    name: 'Exploit Public-Facing Application',
    description: 'Adversaries may attempt to take advantage of a weakness in an Internet-facing computer or program using software, data, or commands in order to cause unintended or unanticipated behavior. Weaknesses can include a vulnerability, a bug, or an insecurity.',
    tactics: ['Initial Access'],
    sub_techniques: [],
    platforms: ['Linux', 'Windows', 'macOS', 'Containers'],
    url: 'https://attack.mitre.org/techniques/T1190',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sampleTechniques = [
    'T1190',
    'T1003',
    'T1059',
    'T1566',
    'T1055',
    'T1053',
    'T1110',
    'T1021',
  ];

  const handleSearch = async (targetId?: string) => {
    const idToSearch = (targetId || techId).trim().toUpperCase();
    if (!idToSearch) return;

    setLoading(true);
    setError(null);
    try {
      const data = await fetchMitreTechnique(idToSearch);
      setTechnique(data);
    } catch (err: any) {
      setError(err.message || `Technique ${idToSearch} not found`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto', padding: '32px 24px', display: 'flex', flexDirection: 'column', gap: '28px' }}>
      {/* Header */}
      <div>
        <h2 style={{ fontSize: '1.8rem', fontWeight: 800, marginBottom: '6px' }}>
          MITRE ATT&CK Technique Explorer
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.92rem', marginBottom: '16px' }}>
          Browse adversary tactics, sub-techniques, platform targets, and NIST mitigations derived from MITRE ATT&CK v14.
        </p>

        {/* Quick Technique Chips */}
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '16px' }}>
          {sampleTechniques.map((t) => (
            <button
              key={t}
              onClick={() => {
                setTechId(t);
                handleSearch(t);
              }}
              style={{
                background: 'rgba(255, 255, 255, 0.04)',
                border: '1px solid var(--border-color)',
                borderRadius: '20px',
                padding: '4px 12px',
                fontSize: '0.78rem',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
              }}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="glass-panel" style={{ padding: '16px', maxWidth: '600px', display: 'flex', gap: '12px' }}>
          <input
            type="text"
            className="input-field"
            placeholder="Enter Technique ID (e.g., T1190 or T1003.001)..."
            value={techId}
            onChange={(e) => setTechId(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          />
          <button className="btn-primary" onClick={() => handleSearch()} disabled={loading}>
            {loading ? <Clock size={16} className="spin" /> : <Search size={16} />}
            Search
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: '16px', borderRadius: '10px', background: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', color: 'var(--accent-red)' }}>
          {error}
        </div>
      )}

      {/* Technique Card */}
      {technique && (
        <div className="glass-panel" style={{ padding: '32px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px', borderBottom: '1px solid var(--border-color)', paddingBottom: '20px' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                <span className="font-mono" style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--accent-cyan)' }}>
                  {technique.technique_id}
                </span>
                <h3 style={{ fontSize: '1.4rem', fontWeight: 700, color: '#fff' }}>
                  {technique.name}
                </h3>
              </div>

              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {technique.tactics?.map((tactic, idx) => (
                  <span key={idx} className="badge badge-purple">
                    <ShieldAlert size={12} /> {tactic}
                  </span>
                ))}
              </div>
            </div>

            {technique.url && (
              <a
                href={technique.url}
                target="_blank"
                rel="noreferrer"
                className="btn-secondary"
                style={{ fontSize: '0.82rem' }}
              >
                View on ATT&CK <Globe size={14} />
              </a>
            )}
          </div>

          {/* Description */}
          <div>
            <h4 style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '10px' }}>
              Description & Operational Context
            </h4>
            <p style={{ color: 'var(--text-primary)', lineHeight: 1.6, fontSize: '0.95rem', background: 'rgba(10, 13, 20, 0.4)', padding: '16px', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
              {technique.description}
            </p>
          </div>

          {/* Platforms & Sub-techniques Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px' }}>
            {/* Target Platforms */}
            {technique.platforms && technique.platforms.length > 0 && (
              <div style={{ background: 'rgba(10, 13, 20, 0.6)', padding: '18px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
                <h5 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '10px' }}>
                  Target Platforms
                </h5>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  {technique.platforms.map((p, i) => (
                    <span key={i} className="badge badge-cyan">
                      <Layers size={12} /> {p}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Sub-techniques */}
            {technique.sub_techniques && technique.sub_techniques.length > 0 && (
              <div style={{ background: 'rgba(10, 13, 20, 0.6)', padding: '18px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
                <h5 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '10px' }}>
                  Associated Sub-Techniques
                </h5>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  {technique.sub_techniques.map((sub, i) => (
                    <span key={i} className="badge badge-purple" style={{ fontFamily: 'var(--font-mono)' }}>
                      {sub}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
