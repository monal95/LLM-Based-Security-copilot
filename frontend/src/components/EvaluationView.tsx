import { useEffect, useState } from 'react';
import { fetchBaselineVsFinal, fetchEvaluationResults } from '../services/api';
import type { EvaluationResults } from '../types';
import {
  categoryLabel,
  hasUnnormalisedNdcg,
  headlineMode,
  isEmptyPayload,
  listModes,
  modeLabel,
} from '../lib/evaluation';
import type { ModeSummary, PrioritySummary } from '../lib/evaluation';
import {
  Badge,
  BarChart,
  ErrorNote,
  Grid,
  KeyValues,
  LoadingRow,
  NotAvailable,
  PageHeader,
  Section,
  StatCard,
} from './ui';
import {
  NA,
  fmtFixed,
  fmtInt,
  fmtMs,
  fmtPct,
  fmtText,
} from '../lib/format';

interface MetricDelta {
  baseline?: number;
  final?: number;
  absolute_improvement?: number;
  percentage_improvement?: number;
}

interface ModeComparison {
  status?: string;
  baseline_status?: string;
  final_status?: string;
  baseline_error?: string | null;
  final_error?: string | null;
  [metric: string]: unknown;
}

interface BaselineVsFinal {
  timestamp_utc?: string;
  query_count?: number;
  baseline_config?: Record<string, unknown>;
  final_config?: Record<string, unknown>;
  metrics_by_mode?: Record<string, ModeComparison>;
}

const COMPARISON_META_KEYS = new Set(['status', 'baseline_status', 'final_status', 'baseline_error', 'final_error']);

const METRIC_LABELS: Record<string, string> = {
  recall_5: 'Recall@5',
  recall_10: 'Recall@10',
  precision_5: 'Precision@5',
  precision_10: 'Precision@10',
  mrr: 'MRR',
  ndcg_5: 'NDCG@5',
  ndcg_10: 'NDCG@10',
  avg_latency_ms: 'Mean latency (ms)',
};

/** Quality metrics only — latency is excluded from the "no change" check. */
const QUALITY_METRICS = ['recall_5', 'recall_10', 'precision_5', 'precision_10', 'mrr', 'ndcg_5', 'ndcg_10'];

export function EvaluationView() {
  const [evaluation, setEvaluation] = useState<EvaluationResults | null>(null);
  const [comparison, setComparison] = useState<BaselineVsFinal | null>(null);
  const [evalError, setEvalError] = useState<string | null>(null);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    Promise.allSettled([fetchEvaluationResults(), fetchBaselineVsFinal()]).then(([evalResult, bvfResult]) => {
      if (cancelled) return;

      if (evalResult.status === 'fulfilled') setEvaluation(evalResult.value);
      else setEvalError(evalResult.reason instanceof Error ? evalResult.reason.message : 'Evaluation results unavailable');

      if (bvfResult.status === 'fulfilled') setComparison(bvfResult.value);
      else
        setComparisonError(
          bvfResult.reason instanceof Error ? bvfResult.reason.message : 'Baseline comparison unavailable',
        );

      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  const modes = listModes(evaluation?.retrieval as Record<string, unknown> | undefined);
  const headline = headlineMode(modes);
  const priority = (evaluation?.priority ?? {}) as PrioritySummary;
  const ragas = evaluation?.ragas as Record<string, number> | undefined;
  const ndcgSuspect = hasUnnormalisedNdcg(modes);

  if (loading) {
    return (
      <div className="view-stack">
        <PageHeader title="Evaluation" description="Benchmark results served from the evaluation result files." />
        <div className="card">
          <LoadingRow message="Loading evaluation results…" />
        </div>
      </div>
    );
  }

  return (
    <div className="view-stack">
      <PageHeader
        title="Evaluation"
        description="Retrieval, generation and prioritization results as produced by the evaluation scripts. Every figure is read from a result file; nothing on this page is estimated."
      />

      {evalError && <ErrorNote message={`Evaluation results: ${evalError}`} />}

      <Grid min={200}>
        <StatCard label="Queries evaluated" value={fmtInt(headline?.total_queries)} sub={headline ? modeLabel(headline.mode) : undefined} />
        <StatCard label="Recall@5" value={fmtPct(headline?.recall_5, 2)} sub="Top-5 retrieval" />
        <StatCard label="MRR" value={fmtFixed(headline?.mrr, 4)} sub="Mean reciprocal rank" />
        <StatCard label="Mean latency" value={fmtMs(headline?.avg_latency_ms)} sub="Per query" />
      </Grid>

      {/* -------------------- Retrieval -------------------- */}

      <Section
        title="Retrieval performance"
        description={
          modes.length
            ? `${modes.length} of 4 retrieval modes present in the results file.`
            : 'No retrieval results were returned by the API.'
        }
        flush
      >
        {modes.length ? (
          <div className="table-scroll">
            <table className="table">
              <caption className="sr-only">Retrieval metrics by mode</caption>
              <thead>
                <tr>
                  <th scope="col">Mode</th>
                  <th scope="col" className="align-right">Queries</th>
                  <th scope="col" className="align-right">Recall@5</th>
                  <th scope="col" className="align-right">Recall@10</th>
                  <th scope="col" className="align-right">P@5</th>
                  <th scope="col" className="align-right">P@10</th>
                  <th scope="col" className="align-right">MRR</th>
                  <th scope="col" className="align-right">NDCG@5</th>
                  <th scope="col" className="align-right">NDCG@10</th>
                  <th scope="col" className="align-right">Hit@1</th>
                  <th scope="col" className="align-right">Latency</th>
                </tr>
              </thead>
              <tbody>
                {modes.map((mode: ModeSummary) => (
                  <tr key={mode.mode}>
                    <td style={{ fontWeight: 500 }}>
                      {modeLabel(mode.mode)}
                      {mode.status && mode.status !== 'SUCCESS' && (
                        <span style={{ marginLeft: 6 }}>
                          <Badge tone="medium">{mode.status}</Badge>
                        </span>
                      )}
                    </td>
                    <td className="align-right num">{fmtInt(mode.total_queries)}</td>
                    <td className="align-right num">{fmtFixed(mode.recall_5, 4)}</td>
                    <td className="align-right num">{fmtFixed(mode.recall_10, 4)}</td>
                    <td className="align-right num">{fmtFixed(mode.precision_5, 4)}</td>
                    <td className="align-right num">{fmtFixed(mode.precision_10, 4)}</td>
                    <td className="align-right num">{fmtFixed(mode.mrr, 4)}</td>
                    <td className="align-right num">{fmtFixed(mode.ndcg_5, 4)}</td>
                    <td className="align-right num">{fmtFixed(mode.ndcg_10, 4)}</td>
                    <td className="align-right num">{fmtFixed(mode.hit_1, 4)}</td>
                    <td className="align-right num">{fmtMs(mode.avg_latency_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="card-body">
            <NotAvailable what="no retrieval evaluation results are present" reason="Run evaluation/phase6_retrieval_evaluation.py to produce phase6_retrieval_results.json." />
          </div>
        )}
      </Section>

      {ndcgSuspect && (
        <div
          role="note"
          style={{
            border: '1px solid var(--medium-border)',
            background: 'var(--medium-bg)',
            borderRadius: 'var(--radius-sm)',
            padding: '10px 12px',
            fontSize: '0.8125rem',
          }}
        >
          <strong style={{ color: 'var(--medium)' }}>NDCG values exceed 1.0.</strong>{' '}
          <span>
            NDCG is bounded by 1 by definition. In the current results the ideal DCG is computed from the single expected
            document while DCG counts every matching chunk, so these figures are unnormalised DCG. Treat them as DCG until
            the normalisation in evaluation/evaluation_engine.py is corrected.
          </span>
        </div>
      )}

      {modes.length > 0 && (
        <Section title="Recall@5 by retrieval mode">
          <BarChart
            data={modes.map((mode) => ({ label: modeLabel(mode.mode), value: mode.recall_5 }))}
            max={1}
            formatValue={(value) => value.toFixed(4)}
          />
        </Section>
      )}

      {headline?.category_breakdown && (
        <Section title="Performance by query category" description={`${modeLabel(headline.mode)} retrieval.`} flush>
          <div className="table-scroll">
            <table className="table">
              <caption className="sr-only">Retrieval metrics by benchmark query category</caption>
              <thead>
                <tr>
                  <th scope="col">Category</th>
                  <th scope="col" className="align-right">Queries</th>
                  <th scope="col" className="align-right">Recall@5</th>
                  <th scope="col" className="align-right">Recall@10</th>
                  <th scope="col" className="align-right">P@5</th>
                  <th scope="col" className="align-right">MRR</th>
                  <th scope="col" className="align-right">NDCG@5</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(headline.category_breakdown).map(([category, metrics]) => (
                  <tr key={category}>
                    <td>{categoryLabel(category)}</td>
                    <td className="align-right num">{fmtInt(metrics.count)}</td>
                    <td className="align-right num">{fmtFixed(metrics.recall_5, 4)}</td>
                    <td className="align-right num">{fmtFixed(metrics.recall_10, 4)}</td>
                    <td className="align-right num">{fmtFixed(metrics.precision_5, 4)}</td>
                    <td className="align-right num">{fmtFixed(metrics.mrr, 4)}</td>
                    <td className="align-right num">{fmtFixed(metrics.ndcg_5, 4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {/* -------------------- RAGAS -------------------- */}

      <Section title="RAG generation quality (RAGAS)" description="Faithfulness, relevancy and context metrics.">
        {isEmptyPayload(ragas) ? (
          <NotAvailable
            what="no RAGAS results are available from the API"
            reason="GET /api/evaluation reads evaluation/results/phase6_ragas_results.json; that file is not present, so no generation-quality figures are shown."
          />
        ) : (
          <Grid min={200}>
            <StatCard label="Faithfulness" value={fmtFixed(ragas?.faithfulness, 4)} sub="Answer grounded in context" />
            <StatCard label="Answer relevancy" value={fmtFixed(ragas?.answer_relevancy, 4)} sub="Answer addresses the query" />
            <StatCard label="Context precision" value={fmtFixed(ragas?.context_precision, 4)} sub="Signal in retrieved context" />
            <StatCard label="Context recall" value={fmtFixed(ragas?.context_recall, 4)} sub="Ground truth covered" />
          </Grid>
        )}
      </Section>

      {/* -------------------- Prioritization -------------------- */}

      <Section
        title="Prioritization performance"
        description={fmtText(priority.evaluation_name) !== NA ? String(priority.evaluation_name) : 'Priority scoring validation.'}
      >
        {isEmptyPayload(priority) ? (
          <NotAvailable
            what="no prioritization validation results are available"
            reason="Run eval/phase6_priority_evaluation.py to produce phase6_priority_results.json."
          />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
            <KeyValues
              rows={[
                { key: 'Spearman rho', value: fmtFixed(priority.spearman_rho, 4), mono: true },
                { key: 'Spearman p-value', value: priority.spearman_pvalue?.toExponential(3) ?? NA, mono: true },
                { key: 'Kendall tau', value: fmtFixed(priority.kendall_tau, 4), mono: true },
                { key: 'Kendall p-value', value: priority.kendall_pvalue?.toExponential(3) ?? NA, mono: true },
              ]}
            />
            <KeyValues
              rows={[
                { key: 'Sample size', value: fmtInt(priority.sample_size), mono: true },
                { key: 'Top-5 overlap', value: fmtFixed(priority.top5_overlap, 4), mono: true },
                { key: 'Top-10 overlap', value: fmtFixed(priority.top10_overlap, 4), mono: true },
                { key: 'Category ordering accuracy', value: fmtPct(priority.category_ordering_accuracy, 1), mono: true },
              ]}
            />
          </div>
        )}

        {!isEmptyPayload(priority) && (
          <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
            <p className="meta">
              Ground truth: {fmtText(priority.ground_truth_metric)}
              {priority.category_ordering_notes ? ` — ${priority.category_ordering_notes}` : ''}
            </p>
            {priority.weights_used && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
                {Object.entries(priority.weights_used).map(([weight, value]) => (
                  <Badge key={weight} tone="info">
                    {weight.replace('_weight', '').toUpperCase()} {value}
                  </Badge>
                ))}
              </div>
            )}
            <p className="meta" style={{ marginTop: 8 }}>
              The deployed scoring model combines CVSS, EPSS and KEV only. No other signal contributed to these figures.
            </p>
          </div>
        )}
      </Section>

      {/* -------------------- Baseline vs final -------------------- */}

      <BaselineComparison comparison={comparison} error={comparisonError} />

      {/* -------------------- Failure analysis -------------------- */}

      <Section title="Failure analysis" description="Queries whose expected document was not retrieved.">
        <NotAvailable
          what="per-query failure records are not exposed by the API"
          reason="evaluation/results/retrieval_failures.json is written by the evaluation script but no endpoint serves it. Inspect that file directly, or add an endpoint to backend/main.py."
        />
      </Section>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function BaselineComparison({ comparison, error }: { comparison: BaselineVsFinal | null; error: string | null }) {
  if (error || !comparison?.metrics_by_mode) {
    return (
      <Section title="Baseline vs final configuration">
        <NotAvailable
          what="no baseline comparison is available"
          reason={error ?? 'Run evaluation/phase6_baseline_vs_final.py to produce baseline_vs_final.json.'}
        />
      </Section>
    );
  }

  const entries = Object.entries(comparison.metrics_by_mode);

  return (
    <Section
      title="Baseline vs final configuration"
      description={`${fmtInt(comparison.query_count)} queries — generated ${fmtText(comparison.timestamp_utc)}`}
    >
      {entries.map(([mode, metrics]) => {
        const metricRows = Object.entries(metrics).filter(
          (entry): entry is [string, MetricDelta] =>
            !COMPARISON_META_KEYS.has(entry[0]) && !!entry[1] && typeof entry[1] === 'object',
        );

        const qualityUnchanged =
          metricRows.length > 0 &&
          metricRows
            .filter(([key]) => QUALITY_METRICS.includes(key))
            .every(([, value]) => value.absolute_improvement === 0);

        if (metrics.status !== 'completed') {
          return (
            <div key={mode} style={{ marginBottom: 12 }}>
              <p className="section-title" style={{ marginBottom: 4 }}>{modeLabel(mode)}</p>
              <p className="meta">
                {NA} — comparison status: {fmtText(metrics.status)}
                {metrics.baseline_error ? ` (baseline: ${metrics.baseline_error})` : ''}
                {metrics.final_error ? ` (final: ${metrics.final_error})` : ''}
              </p>
            </div>
          );
        }

        return (
          <div key={mode} style={{ marginBottom: 16 }}>
            <p className="section-title" style={{ marginBottom: 8 }}>{modeLabel(mode)}</p>

            <div className="table-scroll">
              <table className="table">
                <caption className="sr-only">Baseline versus final metrics for {modeLabel(mode)}</caption>
                <thead>
                  <tr>
                    <th scope="col">Metric</th>
                    <th scope="col" className="align-right">Baseline</th>
                    <th scope="col" className="align-right">Final</th>
                    <th scope="col" className="align-right">Absolute change</th>
                    <th scope="col" className="align-right">Change</th>
                  </tr>
                </thead>
                <tbody>
                  {metricRows.map(([metric, values]) => (
                    <tr key={metric}>
                      <td>{METRIC_LABELS[metric] ?? metric}</td>
                      <td className="align-right num">{fmtFixed(values.baseline, 4)}</td>
                      <td className="align-right num">{fmtFixed(values.final, 4)}</td>
                      <td className="align-right num">{fmtFixed(values.absolute_improvement, 4)}</td>
                      <td className="align-right num">
                        {values.percentage_improvement === undefined
                          ? NA
                          : `${values.percentage_improvement > 0 ? '+' : ''}${values.percentage_improvement.toFixed(2)}%`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {qualityUnchanged && (
              <p
                className="meta"
                style={{
                  marginTop: 8,
                  padding: '8px 10px',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                  background: 'var(--surface-sunken)',
                }}
              >
                Every quality metric is identical between the two configurations for this mode; only latency differs.
                Confirm which configuration was used as the baseline before citing this comparison as an optimisation
                result.
              </p>
            )}
          </div>
        );
      })}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 16, marginTop: 8 }}>
        <ConfigList title="Baseline configuration" config={comparison.baseline_config} />
        <ConfigList title="Final configuration" config={comparison.final_config} />
      </div>
    </Section>
  );
}

function ConfigList({ title, config }: { title: string; config?: Record<string, unknown> }) {
  if (!config || isEmptyPayload(config)) {
    return (
      <div>
        <p className="section-title" style={{ marginBottom: 6 }}>{title}</p>
        <p className="meta">{NA}</p>
      </div>
    );
  }

  return (
    <div>
      <p className="section-title" style={{ marginBottom: 6 }}>{title}</p>
      <KeyValues
        rows={Object.entries(config).map(([key, value]) => ({
          key: key.replace(/_/g, ' '),
          value: typeof value === 'boolean' ? (value ? 'true' : 'false') : String(value),
          mono: true,
        }))}
      />
    </div>
  );
}
