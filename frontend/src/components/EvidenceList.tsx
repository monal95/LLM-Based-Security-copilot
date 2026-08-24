/**
 * Renders retrieved chunks as a citation list.
 *
 * Source labels come from chunk metadata only; nothing is inferred when the
 * metadata is absent.
 */

import type { RetrievalItem } from '../types';
import {
  Badge,
  EmptyState,
} from './ui';
import {
  fmtFixed,
} from '../lib/format';

function sourceLabels(item: RetrievalItem): string[] {
  const metadata = item.metadata ?? {};
  const labels: string[] = [];

  const source = metadata.source ?? metadata.dataset ?? metadata.origin;
  if (typeof source === 'string' && source.trim()) labels.push(source.trim().toUpperCase());

  if (typeof metadata.cve_id === 'string' && metadata.cve_id.trim()) labels.push(metadata.cve_id.toUpperCase());
  if (typeof metadata.technique_id === 'string' && metadata.technique_id.trim()) {
    labels.push(metadata.technique_id.toUpperCase());
  }

  return Array.from(new Set(labels));
}

export function EvidenceList({ items, emptyMessage }: { items: RetrievalItem[]; emptyMessage?: string }) {
  if (!items.length) {
    return <EmptyState title="No evidence returned" message={emptyMessage ?? 'The retriever returned no chunks for this query.'} />;
  }

  return (
    <ol style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
      {items.map((item, index) => {
        const labels = sourceLabels(item);
        return (
          <li
            key={item.chunk_id ?? `${item.rank}-${index}`}
            style={{
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              padding: '10px 12px',
              background: 'var(--surface-sunken)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
              <span className="num" style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                [{item.rank ?? index + 1}]
              </span>
              {labels.map((label) => (
                <Badge key={label} tone="info">
                  {label}
                </Badge>
              ))}
              <span className="meta" style={{ marginLeft: 'auto' }}>
                score {fmtFixed(item.score, 4)}
              </span>
            </div>
            <p style={{ fontSize: '0.8125rem', lineHeight: 1.55, color: 'var(--text)' }}>{item.text}</p>
            {item.chunk_id && (
              <p className="meta mono" style={{ marginTop: 6 }}>
                {item.chunk_id}
              </p>
            )}
          </li>
        );
      })}
    </ol>
  );
}
