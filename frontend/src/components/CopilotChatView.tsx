import { useState } from 'react';
import { CheckCircle2, CircleSlash, TriangleAlert } from 'lucide-react';
import { fetchEvidence, sendChatMessage } from '../services/api';
import type { ChatResponse, ClaimReport, RetrievalItem } from '../types';
import { EvidenceList } from './EvidenceList';
import {
  Badge,
  EmptyState,
  ErrorNote,
  Grid,
  KeyValues,
  LoadingRow,
  PageHeader,
  QuickPicks,
  SearchBar,
  Section,
  Spinner,
  StatCard,
} from './ui';
import {
  NA,
  fmtInt,
  fmtMs,
  fmtPct,
} from '../lib/format';
import type { BadgeTone } from '../lib/format';

const EXAMPLE_QUERIES = [
  'What is CVE-2021-44228?',
  'Explain MITRE ATT&CK technique T1190.',
  'How should Log4Shell be prioritised against Zerologon?',
];

const CLAIM_STYLES: Record<ClaimReport['status'], { tone: BadgeTone; icon: typeof CheckCircle2 }> = {
  Verified: { tone: 'low', icon: CheckCircle2 },
  'Partially Verified': { tone: 'medium', icon: TriangleAlert },
  Unsupported: { tone: 'critical', icon: CircleSlash },
};

export function CopilotChatView() {
  const [query, setQuery] = useState('');
  const [submitted, setSubmitted] = useState('');
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [evidence, setEvidence] = useState<RetrievalItem[] | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);

  const runQuery = async (text?: string) => {
    const value = (text ?? query).trim();
    if (!value) return;

    setQuery(value);
    setSubmitted(value);
    setLoading(true);
    setError(null);
    setEvidence(null);
    setEvidenceError(null);

    try {
      setResponse(await sendChatMessage(value));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The SecureRAG pipeline did not return an answer');
      setResponse(null);
    } finally {
      setLoading(false);
    }
  };

  const loadEvidence = async () => {
    if (!submitted) return;
    setEvidenceLoading(true);
    setEvidenceError(null);
    try {
      setEvidence(await fetchEvidence(submitted, 5));
    } catch (err) {
      setEvidenceError(err instanceof Error ? err.message : 'Evidence retrieval failed');
    } finally {
      setEvidenceLoading(false);
    }
  };

  const verification = response?.verification_report;

  return (
    <div className="view-stack">
      <PageHeader
        title="Analyst console"
        description="Answers are generated only from retrieved threat intelligence and are checked claim by claim against that evidence before being shown."
      />

      <Section title="Query">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <SearchBar
            id="analyst-query"
            label="Analyst query"
            placeholder="Ask SecureRAG about a CVE, technique or response procedure…"
            value={query}
            onChange={setQuery}
            onSubmit={() => runQuery()}
            busy={loading}
            submitLabel="Run query"
            maxWidth={720}
          />
          <QuickPicks label="Examples" items={EXAMPLE_QUERIES} onPick={(text) => runQuery(text)} />
        </div>
      </Section>

      {error && <ErrorNote message={error} />}

      {loading && (
        <div className="card">
          <LoadingRow message="Running retrieval, generation and verification… (first query after startup is slower while models load)" />
        </div>
      )}

      {!loading && !response && !error && (
        <div className="card">
          <EmptyState
            title="No query run yet"
            message="Submit a question to retrieve grounded evidence and a verified answer."
          />
        </div>
      )}

      {response && !loading && (
        <>
          <Grid min={200}>
            <StatCard label="Confidence" value={fmtPct(response.confidence_score, 1)} sub="Share of claims supported by evidence" />
            <StatCard label="Claims checked" value={fmtInt(verification?.total_claims)} sub="Extracted from the generated answer" />
            <StatCard label="Unsupported claims" value={fmtInt(verification?.unsupported)} sub="Not matched to retrieved evidence" />
            <StatCard label="End-to-end latency" value={fmtMs(response.total_latency_ms)} sub="Retrieval, generation and verification" />
          </Grid>

          <Section
            title="Answer"
            description={`Query: ${response.query}`}
            actions={<span className="meta">{response.generated_at_utc}</span>}
          >
            <p style={{ whiteSpace: 'pre-wrap', fontSize: '0.8125rem', lineHeight: 1.65 }}>{response.final_answer}</p>
          </Section>

          <div className="main-side">
            <Section
              title="Claim verification"
              description="Each claim in the answer, checked against the retrieved evidence."
              flush
            >
              {response.claim_reports.length ? (
                <div className="table-scroll">
                  <table className="table">
                    <caption className="sr-only">Claim-level grounding verification results</caption>
                    <thead>
                      <tr>
                        <th scope="col" style={{ width: 40 }}>#</th>
                        <th scope="col">Claim</th>
                        <th scope="col">Status</th>
                        <th scope="col" className="align-right">Support</th>
                      </tr>
                    </thead>
                    <tbody>
                      {response.claim_reports.map((claim) => {
                        const style = CLAIM_STYLES[claim.status] ?? { tone: 'neutral' as BadgeTone, icon: TriangleAlert };
                        const Icon = style.icon;
                        return (
                          <tr key={claim.claim_id}>
                            <td className="num" style={{ color: 'var(--text-muted)' }}>{claim.claim_id}</td>
                            <td style={{ minWidth: 280 }}>
                              {claim.claim_text}
                              {claim.rationale && (
                                <div className="meta" style={{ marginTop: 3 }}>{claim.rationale}</div>
                              )}
                            </td>
                            <td>
                              <Badge tone={style.tone}>
                                <Icon size={11} aria-hidden="true" />
                                {claim.status}
                              </Badge>
                            </td>
                            <td className="align-right num">{fmtPct(claim.support_score, 0)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyState title="No claims extracted" message="The verifier found no individual claims in this answer." />
              )}
            </Section>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <Section title="Verification summary">
                <KeyValues
                  rows={[
                    { key: 'Verified', value: fmtInt(verification?.verified), mono: true },
                    { key: 'Partially verified', value: fmtInt(verification?.partially_verified), mono: true },
                    { key: 'Unsupported', value: fmtInt(verification?.unsupported), mono: true },
                    { key: 'Confidence', value: fmtPct(verification?.confidence_score, 1), mono: true },
                  ]}
                />
              </Section>

              <Section title="Retrieval counts" description="Chunks at each pipeline stage.">
                <KeyValues
                  rows={[
                    { key: 'Dense (ChromaDB)', value: fmtInt(response.counts?.dense), mono: true },
                    { key: 'Sparse (BM25)', value: fmtInt(response.counts?.sparse), mono: true },
                    { key: 'Fused (RRF)', value: fmtInt(response.counts?.fused), mono: true },
                    { key: 'Reranked', value: fmtInt(response.counts?.reranked), mono: true },
                  ]}
                />
              </Section>
            </div>
          </div>

          {response.stage_timings_ms && Object.keys(response.stage_timings_ms).length > 0 && (
            <Section
              title="Stage timings"
              description="Wall-clock milliseconds measured by the backend for this request."
              actions={
                response.warm === false ? (
                  <Badge tone="medium">COLD — startup warmup had not finished</Badge>
                ) : undefined
              }
              flush
            >
              <div className="table-scroll">
                <table className="table">
                  <caption className="sr-only">Per-stage latency for this query</caption>
                  <thead>
                    <tr>
                      <th scope="col">Stage</th>
                      <th scope="col" className="align-right">Latency</th>
                      <th scope="col" className="align-right">Share of total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(response.stage_timings_ms).map(([stage, ms]) => (
                      <tr key={stage}>
                        <td>{stage.replace(/_/g, ' ')}</td>
                        <td className="align-right num">{fmtMs(ms)}</td>
                        <td className="align-right num">
                          {response.total_latency_ms > 0 ? fmtPct(ms / response.total_latency_ms, 1) : NA}
                        </td>
                      </tr>
                    ))}
                    <tr>
                      <td style={{ fontWeight: 600 }}>total</td>
                      <td className="align-right num" style={{ fontWeight: 600 }}>{fmtMs(response.total_latency_ms)}</td>
                      <td className="align-right num">—</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </Section>
          )}

          <Section
            title="Evidence"
            description="Chunks retrieved for this query from the indexed knowledge base."
            actions={
              <button type="button" className="btn btn-sm" onClick={loadEvidence} disabled={evidenceLoading}>
                {evidenceLoading ? <Spinner /> : null}
                {evidence ? 'Reload evidence' : 'Retrieve evidence'}
              </button>
            }
          >
            {evidenceError && <ErrorNote message={evidenceError} />}
            {evidenceLoading && <LoadingRow message="Retrieving evidence…" />}
            {!evidenceLoading && evidence && <EvidenceList items={evidence} />}
            {!evidenceLoading && !evidence && !evidenceError && (
              <p className="meta">
                The chat endpoint reports evidence counts only. Retrieve the chunks themselves to inspect what the answer
                was grounded in.
              </p>
            )}
          </Section>
        </>
      )}
    </div>
  );
}
