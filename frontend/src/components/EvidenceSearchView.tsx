import { useState } from 'react';
import { fetchEvidence } from '../services/api';
import type { RetrievalItem } from '../types';
import { EvidenceList } from './EvidenceList';
import {
  EmptyState,
  ErrorNote,
  Grid,
  LoadingRow,
  PageHeader,
  QuickPicks,
  SearchBar,
  Section,
  StatCard,
} from './ui';
import {
  fmtFixed,
  fmtInt,
} from '../lib/format';

const EXAMPLE_QUERIES = [
  'Log4Shell JNDI exploitation',
  'ransomware containment and recovery',
  'credential dumping from LSASS',
];

const TOP_K_OPTIONS = [5, 10, 15, 20];

export function EvidenceSearchView() {
  const [query, setQuery] = useState('');
  const [topK, setTopK] = useState(5);
  const [items, setItems] = useState<RetrievalItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runSearch = async (text?: string) => {
    const value = (text ?? query).trim();
    if (!value) return;

    setQuery(value);
    setLoading(true);
    setError(null);

    try {
      setItems(await fetchEvidence(value, topK));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Evidence retrieval failed');
      setItems(null);
    } finally {
      setLoading(false);
    }
  };

  const topScore = items?.length ? Math.max(...items.map((item) => item.score ?? 0)) : null;

  return (
    <div className="view-stack">
      <PageHeader
        title="Evidence search"
        description="Query the indexed knowledge base directly and inspect the chunks the retriever returns, without generating an answer."
      />

      <Section
        title="Retrieval query"
        actions={
          <>
            <label className="sr-only" htmlFor="top-k">
              Number of chunks to retrieve
            </label>
            <select
              id="top-k"
              className="input"
              style={{ width: 120 }}
              value={topK}
              onChange={(event) => setTopK(Number(event.target.value))}
            >
              {TOP_K_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  Top {option}
                </option>
              ))}
            </select>
          </>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <SearchBar
            id="evidence-search"
            label="Retrieval query"
            placeholder="Describe the threat, technique or vulnerability…"
            value={query}
            onChange={setQuery}
            onSubmit={() => runSearch()}
            busy={loading}
            submitLabel="Retrieve"
            maxWidth={720}
          />
          <QuickPicks label="Examples" items={EXAMPLE_QUERIES} onPick={(text) => runSearch(text)} />
        </div>
      </Section>

      {error && <ErrorNote message={error} />}

      {loading && (
        <div className="card">
          <LoadingRow message="Retrieving chunks…" />
        </div>
      )}

      {!loading && items === null && !error && (
        <div className="card">
          <EmptyState title="No search run yet" message="Submit a query to inspect the retrieved evidence." />
        </div>
      )}

      {!loading && items !== null && (
        <>
          <Grid min={200}>
            <StatCard label="Chunks returned" value={fmtInt(items.length)} sub={`Requested top ${topK}`} />
            <StatCard label="Highest score" value={fmtFixed(topScore, 4)} sub="Rank 1 retrieval score" />
          </Grid>

          <Section title="Retrieved evidence" description="Ordered by retrieval score.">
            <EvidenceList items={items} emptyMessage="No chunks matched this query." />
          </Section>
        </>
      )}
    </div>
  );
}
