/**
 * SecureRAG shared UI primitives.
 *
 * Flat, neutral building blocks used by every view so spacing, typography,
 * borders and status colours stay consistent across the console.
 */

import type { CSSProperties, ReactNode } from 'react';
import { Loader2 } from 'lucide-react';
import { NA, fmtText, isMissing, severityTone } from '../lib/format';
import type { BadgeTone } from '../lib/format';

/* ------------------------------------------------------------------ */
/* Layout                                                              */
/* ------------------------------------------------------------------ */

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
      <div style={{ maxWidth: 680 }}>
        <h1 className="page-title">{title}</h1>
        {description && (
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.8125rem', marginTop: 4 }}>{description}</p>
        )}
      </div>
      {actions && <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>{actions}</div>}
    </div>
  );
}

export function Section({
  title,
  description,
  actions,
  children,
  bodyStyle,
  flush = false,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  bodyStyle?: CSSProperties;
  /** Remove body padding — use when the section contains a full-bleed table. */
  flush?: boolean;
}) {
  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2 className="section-title">{title}</h2>
          {description && <p className="meta" style={{ marginTop: 2 }}>{description}</p>}
        </div>
        {actions && <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>{actions}</div>}
      </div>
      <div className={flush ? undefined : 'card-body'} style={bodyStyle}>
        {children}
      </div>
    </section>
  );
}

export function Grid({ min = 220, gap = 12, children }: { min?: number; gap?: number; children: ReactNode }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(auto-fit, minmax(${min}px, 1fr))`, gap }}>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Stat card                                                           */
/* ------------------------------------------------------------------ */

export function StatCard({
  label,
  value,
  sub,
  icon,
}: {
  label: string;
  value: string;
  sub?: string;
  icon?: ReactNode;
}) {
  const unavailable = value === NA;
  return (
    <div className="card" style={{ padding: '14px 16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <span className="label">{label}</span>
        {icon && <span style={{ color: 'var(--text-muted)', display: 'flex' }}>{icon}</span>}
      </div>
      <div
        className="num"
        style={{
          fontSize: '1.5rem',
          fontWeight: 600,
          letterSpacing: '-0.02em',
          marginTop: 8,
          color: unavailable ? 'var(--text-muted)' : 'var(--text)',
        }}
      >
        {value}
      </div>
      {sub && <div className="meta" style={{ marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Badges                                                              */
/* ------------------------------------------------------------------ */

export function Badge({ tone = 'neutral', children }: { tone?: BadgeTone; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

/** Severity badge. Text always carries the rating, so colour is never the only signal. */
export function SeverityBadge({ severity }: { severity: string | null | undefined }) {
  const text = fmtText(severity).toUpperCase();
  return <Badge tone={severityTone(text)}>{text}</Badge>;
}

export function KevBadge({ kev }: { kev: boolean | null | undefined }) {
  if (kev === null || kev === undefined) return <span className="meta">{NA}</span>;
  return kev ? <Badge tone="critical">KEV</Badge> : <Badge tone="neutral">NOT KEV</Badge>;
}

/* ------------------------------------------------------------------ */
/* States                                                              */
/* ------------------------------------------------------------------ */

export function Spinner({ size = 14 }: { size?: number }) {
  return <Loader2 size={size} className="spin" aria-hidden="true" />;
}

export function LoadingRow({ message = 'Loading…' }: { message?: string }) {
  return (
    <div
      role="status"
      style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '28px 16px', justifyContent: 'center', color: 'var(--text-secondary)', fontSize: '0.8125rem' }}
    >
      <Spinner />
      {message}
    </div>
  );
}

export function SkeletonBlock({ height = 64 }: { height?: number }) {
  return <div className="skeleton" style={{ height }} aria-hidden="true" />;
}

export function EmptyState({ title, message, action }: { title: string; message?: string; action?: ReactNode }) {
  return (
    <div style={{ padding: '32px 16px', textAlign: 'center' }}>
      <p style={{ fontSize: '0.8125rem', fontWeight: 500 }}>{title}</p>
      {message && <p className="meta" style={{ marginTop: 4, maxWidth: 440, marginInline: 'auto' }}>{message}</p>}
      {action && <div style={{ marginTop: 12 }}>{action}</div>}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div
      role="alert"
      style={{
        display: 'flex',
        gap: 8,
        alignItems: 'flex-start',
        padding: '10px 12px',
        border: '1px solid var(--critical-border)',
        background: 'var(--critical-bg)',
        color: 'var(--critical)',
        borderRadius: 'var(--radius-sm)',
        fontSize: '0.8125rem',
      }}
    >
      <span style={{ fontWeight: 600 }}>Error</span>
      <span style={{ color: 'var(--text)' }}>{message}</span>
    </div>
  );
}

/**
 * Rendered wherever the backend exposes no value for a panel. Keeps the
 * absence explicit rather than filling the space with an invented figure.
 */
export function NotAvailable({ what, reason }: { what: string; reason?: string }) {
  return (
    <div style={{ padding: '20px 4px' }}>
      <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
        <span className="num" style={{ color: 'var(--text-muted)', fontWeight: 600 }}>{NA}</span>
        {' — '}
        {what}
      </p>
      {reason && <p className="meta" style={{ marginTop: 4 }}>{reason}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Key/value list                                                      */
/* ------------------------------------------------------------------ */

export function KeyValues({ rows }: { rows: Array<{ key: string; value: ReactNode; mono?: boolean }> }) {
  return (
    <dl>
      {rows.map((row) => (
        <div className="kv" key={row.key}>
          <dt>{row.key}</dt>
          <dd className={row.mono ? 'num' : undefined}>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/* ------------------------------------------------------------------ */
/* Chart — flat horizontal bars, single accent colour                  */
/* ------------------------------------------------------------------ */

export function BarChart({
  data,
  max,
  formatValue = (v: number) => v.toFixed(3),
  labelWidth = 150,
}: {
  data: Array<{ label: string; value: number | null | undefined; note?: string }>;
  /** Upper bound of the value axis. Defaults to the largest value present. */
  max?: number;
  formatValue?: (value: number) => string;
  labelWidth?: number;
}) {
  const present = data.filter((d) => !isMissing(d.value)).map((d) => Number(d.value));
  const upper = max ?? (present.length ? Math.max(...present) : 1);
  const safeUpper = upper > 0 ? upper : 1;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {data.map((row) => {
        const missing = isMissing(row.value);
        const value = Number(row.value);
        const pct = missing ? 0 : Math.max(0, Math.min(100, (value / safeUpper) * 100));
        return (
          <div key={row.label} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span
              className="label"
              style={{ width: labelWidth, flex: 'none', color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
              title={row.label}
            >
              {row.label}
            </span>
            <div style={{ flex: 1, minWidth: 60, height: 14, background: 'var(--surface-sunken)', border: '1px solid var(--border)', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{ width: `${pct}%`, height: '100%', background: 'var(--accent)' }} />
            </div>
            <span className="num" style={{ width: 78, textAlign: 'right', flex: 'none', fontSize: '0.75rem', color: missing ? 'var(--text-muted)' : 'var(--text)' }}>
              {missing ? NA : formatValue(value)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Search bar                                                          */
/* ------------------------------------------------------------------ */

export function SearchBar({
  id,
  label,
  placeholder,
  value,
  onChange,
  onSubmit,
  busy = false,
  submitLabel = 'Search',
  mono = false,
  maxWidth = 460,
}: {
  id: string;
  label: string;
  placeholder?: string;
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  busy?: boolean;
  submitLabel?: string;
  mono?: boolean;
  maxWidth?: number;
}) {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
      style={{ display: 'flex', gap: 8, maxWidth, width: '100%' }}
      role="search"
    >
      <label className="sr-only" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        className={mono ? 'input input-mono' : 'input'}
        type="search"
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={busy}
      />
      <button className="btn btn-primary" type="submit" disabled={busy}>
        {busy ? <Spinner /> : null}
        {busy ? 'Working…' : submitLabel}
      </button>
    </form>
  );
}

/** Compact row of clickable example identifiers. */
export function QuickPicks({
  items,
  onPick,
  label,
}: {
  items: string[];
  onPick: (item: string) => void;
  label: string;
}) {
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
      <span className="meta" style={{ marginRight: 2 }}>{label}</span>
      {items.map((item) => (
        <button key={item} type="button" className="btn btn-sm mono" onClick={() => onPick(item)}>
          {item}
        </button>
      ))}
    </div>
  );
}
