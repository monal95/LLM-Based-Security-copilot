import React, { useEffect, useState } from 'react';
import {
  ListOrdered,
  Flame,
  ShieldAlert,
  Search,
  Filter,
  Info,
  Clock,
  CheckCircle,
} from 'lucide-react';
import { fetchPriorityRankings } from '../services/api';
import { PriorityItem } from '../types';

export const PatchPriorityView: React.FC = () => {
  const [items, setItems] = useState<PriorityItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [kevOnly, setKevOnly] = useState(false);
  const [selectedExplanation, setSelectedExplanation] = useState<PriorityItem | null>(null);

  const defaultCveList = [
    'CVE-2021-44228',
    'CVE-2017-0144',
    'CVE-2020-1472',
    'CVE-2023-34362',
    'CVE-2021-34527',
    'CVE-2014-0160',
    'CVE-2021-26855',
    'CVE-2019-0708',
    'CVE-2022-30190',
    'CVE-2018-13379',
    'CVE-2019-11510',
    'CVE-2019-19781',
  ];

  useEffect(() => {
    loadRankings(defaultCveList);
  }, []);

  const loadRankings = async (cves: string[]) => {
    setLoading(true);
    try {
      const data = await fetchPriorityRankings(cves);
      setItems(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const filteredItems = items.filter((item) => {
    const matchesSearch = item.cve_id.toLowerCase().includes(search.toLowerCase());
    const matchesKev = kevOnly ? item.kev_flag === 1 : true;
    return matchesSearch && matchesKev;
  });

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto', padding: '32px 24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header */}
      <div>
        <h2 style={{ fontSize: '1.8rem', fontWeight: 800, marginBottom: '6px' }}>
          Patch Priority Ranking Table
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.92rem' }}>
          Vulnerability prioritization formula: Priority = (CVSS/10 × 0.3) + (EPSS × 0.5) + (KEV Flag × 0.2)
        </p>
      </div>

      {/* Controls Bar */}
      <div className="glass-panel" style={{ padding: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1, minWidth: '280px' }}>
          <Search size={18} color="var(--text-muted)" />
          <input
            type="text"
            className="input-field"
            placeholder="Filter by CVE ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ padding: '8px 12px' }}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            <input
              type="checkbox"
              checked={kevOnly}
              onChange={(e) => setKevOnly(e.target.checked)}
            />
            Show CISA KEV Only
          </label>

          <button className="btn-secondary" onClick={() => loadRankings(defaultCveList)}>
            <Clock size={16} /> Re-score All
          </button>
        </div>
      </div>

      {/* Priority Table */}
      <div className="glass-panel" style={{ overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
            Calculating weighted priority scores and generating LLM explanations...
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Rank</th>
                <th>CVE ID</th>
                <th>CVSS Score</th>
                <th>EPSS Prob (30d)</th>
                <th>KEV Status</th>
                <th>Priority Score</th>
                <th>Recommended Action</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {filteredItems.map((item) => (
                <tr key={item.cve_id}>
                  <td className="font-mono" style={{ fontWeight: 700, color: 'var(--accent-cyan)' }}>
                    #{item.rank}
                  </td>
                  <td className="font-mono" style={{ fontWeight: 600, color: '#fff' }}>
                    {item.cve_id}
                  </td>
                  <td>
                    <span style={{ fontWeight: 600, color: item.cvss_score >= 9.0 ? 'var(--accent-red)' : 'var(--accent-amber)' }}>
                      {item.cvss_score.toFixed(1)}
                    </span>
                  </td>
                  <td>
                    <span className="font-mono">{(item.epss_score * 100).toFixed(1)}%</span>
                  </td>
                  <td>
                    {item.kev_flag === 1 ? (
                      <span className="badge badge-red">
                        <Flame size={12} /> CONFIRMED EXPLOITED
                      </span>
                    ) : (
                      <span className="badge" style={{ background: 'rgba(255,255,255,0.05)', color: 'var(--text-muted)' }}>
                        Not in KEV
                      </span>
                    )}
                  </td>
                  <td>
                    <div style={{ fontWeight: 800, color: 'var(--accent-cyan)', fontSize: '1rem' }}>
                      {item.priority_score.toFixed(3)}
                    </div>
                  </td>
                  <td style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    {item.kev_flag === 1
                      ? 'Emergency 24-hr remediation (CISA BOD)'
                      : item.cvss_score >= 9.0
                      ? 'Priority patch cycle within 7 days'
                      : 'Standard scheduled maintenance patch'}
                  </td>
                  <td>
                    <button
                      className="btn-secondary"
                      style={{ padding: '4px 10px', fontSize: '0.75rem' }}
                      onClick={() => setSelectedExplanation(item)}
                    >
                      <Info size={14} /> Explain
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Explanation Modal */}
      {selectedExplanation && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '20px' }}>
          <div className="glass-panel-glow" style={{ maxWidth: '600px', width: '100%', padding: '28px', background: 'var(--bg-surface)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#fff' }}>
                Priority Rationale: {selectedExplanation.cve_id}
              </h3>
              <button
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: '1.4rem', cursor: 'pointer' }}
                onClick={() => setSelectedExplanation(null)}
              >
                &times;
              </button>
            </div>

            <div style={{ background: 'rgba(10,13,20,0.6)', padding: '16px', borderRadius: '8px', border: '1px solid var(--border-color)', marginBottom: '20px', lineHeight: 1.6, fontSize: '0.92rem' }}>
              {selectedExplanation.explanation || 'No explanation generated.'}
            </div>

            <div style={{ textAlign: 'right' }}>
              <button className="btn-primary" onClick={() => setSelectedExplanation(null)}>
                Close Rationale
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
