import { useEffect, useMemo, useState } from 'react';
import { Info, RefreshCw } from 'lucide-react';
import { fetchPriorityRankings } from '../services/api';
import type { PriorityItem } from '../types';
import { Modal } from './Modal';
import {
  Badge,
  BarChart,
  EmptyState,
  ErrorNote,
  Grid,
  KevBadge,
  LoadingRow,
  PageHeader,
  Section,
  SeverityBadge,
  StatCard,
  Spinner,
} from './ui';
import {
  NA,
  fmtFixed,
  fmtInt,
  fmtPct,
  severityFromCvss,
} from '../lib/format';

/** Starting watchlist. Every score shown is computed by the backend for these IDs. */
const DEFAULT_WATCHLIST = [
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

/**
 * Remediation window suggested by the console from the returned signals.
 * This is a presentation rule, not a value produced by the scoring model.
 */
function suggestedWindow(item: PriorityItem): string {
  if (item.kev_flag === 1) return 'Emergency — KEV, per CISA BOD 22-01';
  if (item.cvss_score >= 9.0) return 'Within 7 days';
  if (item.cvss_score >= 7.0) return 'Next patch cycle';
  return 'Scheduled maintenance';
}

export function PatchPriorityView() {
  const [watchlist, setWatchlist] = useState(DEFAULT_WATCHLIST);
  const [draft, setDraft] = useState(DEFAULT_WATCHLIST.join('\n'));
  const [items, setItems] = useState<PriorityItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  const [kevOnly, setKevOnly] = useState(false);
  const [editing, setEditing] = useState(false);
  const [explaining, setExplaining] = useState<PriorityItem | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchPriorityRankings(watchlist)
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setError(err.message);
          setItems([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [watchlist]);

  const filtered = useMemo(
    () =>
      items.filter((item) => {
        const matchesText = item.cve_id.toLowerCase().includes(filter.trim().toLowerCase());
        return matchesText && (kevOnly ? item.kev_flag === 1 : true);
      }),
    [items, filter, kevOnly],
  );

  const kevCount = items.filter((item) => item.kev_flag === 1).length;
  const criticalCount = items.filter((item) => item.cvss_score >= 9.0).length;
  const topScore = items.length ? Math.max(...items.map((item) => item.priority_score)) : null;

  const applyWatchlist = () => {
    const parsed = Array.from(
      new Set(
        draft
          .split(/[\s,]+/)
          .map((token) => token.trim().toUpperCase())
          .filter((token) => token.startsWith('CVE-')),
      ),
    );
    if (parsed.length) {
      setWatchlist(parsed);
      setEditing(false);
    }
  };

  return (
    <div className="view-stack">
      <PageHeader
        title="Vulnerability prioritization"
        description="Priority = (CVSS / 10 x 0.3) + (EPSS x 0.5) + (KEV flag x 0.2). Scores are computed by the backend for the CVEs on the watchlist."
        actions={
          <>
            <button type="button" className="btn" onClick={() => setEditing(true)}>
              Edit watchlist
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => setWatchlist([...watchlist])}
              disabled={loading}
            >
              {loading ? <Spinner /> : <RefreshCw size={14} aria-hidden="true" />}
              Re-score
            </button>
          </>
        }
      />

      {error && <ErrorNote message={error} />}

      <Grid min={200}>
        <StatCard label="CVEs scored" value={fmtInt(items.length)} sub="Current watchlist" />
        <StatCard label="Known exploited" value={fmtInt(kevCount)} sub="Present in the CISA KEV catalogue" />
        <StatCard label="CVSS critical" value={fmtInt(criticalCount)} sub="Base score at or above 9.0" />
        <StatCard label="Highest priority score" value={fmtFixed(topScore, 3)} sub="Top of the ranked list" />
      </Grid>

      <Section
        title="Ranked vulnerabilities"
        description="Ordered by priority score, highest first."
        actions={
          <>
            <label className="sr-only" htmlFor="priority-filter">
              Filter by CVE identifier
            </label>
            <input
              id="priority-filter"
              className="input input-mono"
              style={{ width: 190 }}
              type="search"
              placeholder="Filter CVE ID"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
            />
            <label className="checkbox-row">
              <input type="checkbox" checked={kevOnly} onChange={(event) => setKevOnly(event.target.checked)} />
              KEV only
            </label>
          </>
        }
        flush
      >
        {loading ? (
          <LoadingRow message="Scoring vulnerabilities…" />
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No vulnerabilities match"
            message={items.length ? 'Adjust the filter to see scored results.' : 'No scores were returned for this watchlist.'}
          />
        ) : (
          <div className="table-scroll">
            <table className="table">
              <caption className="sr-only">Vulnerabilities ranked by priority score</caption>
              <thead>
                <tr>
                  <th scope="col" className="align-right" style={{ width: 52 }}>Rank</th>
                  <th scope="col">CVE</th>
                  <th scope="col" className="align-right">Priority</th>
                  <th scope="col" className="align-right">CVSS</th>
                  <th scope="col">Severity</th>
                  <th scope="col" className="align-right">EPSS</th>
                  <th scope="col">KEV</th>
                  <th scope="col">Suggested window</th>
                  <th scope="col" style={{ width: 96 }}>Rationale</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => (
                  <tr key={item.cve_id}>
                    <td className="align-right num" style={{ color: 'var(--text-muted)' }}>{item.rank}</td>
                    <td className="mono" style={{ fontWeight: 500 }}>{item.cve_id}</td>
                    <td className="align-right num" style={{ fontWeight: 600 }}>{fmtFixed(item.priority_score, 3)}</td>
                    <td className="align-right num">{fmtFixed(item.cvss_score, 1)}</td>
                    <td><SeverityBadge severity={severityFromCvss(item.cvss_score)} /></td>
                    <td className="align-right num">{fmtPct(item.epss_score, 2)}</td>
                    <td><KevBadge kev={item.kev_flag === 1} /></td>
                    <td style={{ color: 'var(--text-secondary)' }}>{suggestedWindow(item)}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-sm"
                        onClick={() => setExplaining(item)}
                        disabled={!item.explanation}
                        title={item.explanation ? 'View the generated rationale' : 'No rationale returned for this CVE'}
                      >
                        <Info size={13} aria-hidden="true" />
                        Explain
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {!loading && items.length > 0 && (
        <Section title="Priority score distribution" description="Top ten CVEs on the watchlist.">
          <BarChart
            data={items.slice(0, 10).map((item) => ({ label: item.cve_id, value: item.priority_score }))}
            max={1}
            formatValue={(value) => value.toFixed(3)}
            labelWidth={138}
          />
        </Section>
      )}

      <Section title="Scoring signals" description="Signals used by the deployed scoring model.">
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <Badge tone="info">CVSS — weight 0.3</Badge>
          <Badge tone="info">EPSS — weight 0.5</Badge>
          <Badge tone="info">KEV — weight 0.2</Badge>
        </div>
        <p className="meta" style={{ marginTop: 8 }}>
          The suggested remediation window is derived in this console from KEV status and the CVSS band. It is not part of
          the score returned by POST /api/priority.
        </p>
      </Section>

      <Modal
        open={editing}
        title="Edit watchlist"
        description="One CVE identifier per line. Non-CVE tokens are ignored."
        onClose={() => setEditing(false)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setEditing(false)}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary" onClick={applyWatchlist}>
              Score watchlist
            </button>
          </>
        }
      >
        <label className="sr-only" htmlFor="watchlist-input">
          CVE identifiers
        </label>
        <textarea
          id="watchlist-input"
          className="input input-mono"
          rows={12}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
      </Modal>

      <Modal
        open={explaining !== null}
        title={explaining ? `Rationale — ${explaining.cve_id}` : ''}
        description="Generated from the retrieved evidence for this CVE."
        onClose={() => setExplaining(null)}
        footer={
          <button type="button" className="btn" onClick={() => setExplaining(null)}>
            Close
          </button>
        }
      >
        <p style={{ fontSize: '0.8125rem', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
          {explaining?.explanation ?? `${NA} — no rationale was returned for this CVE.`}
        </p>
      </Modal>
    </div>
  );
}
