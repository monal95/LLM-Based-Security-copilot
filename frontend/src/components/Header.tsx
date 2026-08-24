/** Top header: current page, backend connection state, runbook action. */

import { BookOpen } from 'lucide-react';
import { VIEW_TITLES } from '../navigation';
import type { ViewId } from '../navigation';
import type { WarmupState } from '../types';

interface HeaderProps {
  activeView: ViewId;
  backendOnline: boolean | null;
  warmup: WarmupState | null;
  onOpenRunbook: () => void;
}

/**
 * Status text reflects the backend's own reported state. While warmup is
 * running the first query will be slow, and saying so is more useful than
 * showing a generic "connected".
 */
function describeStatus(backendOnline: boolean | null, warmup: WarmupState | null): string {
  if (backendOnline === null) return 'Checking API…';
  if (!backendOnline) return 'API unreachable';
  if (warmup?.status === 'running') return 'API connected — loading models';
  if (warmup?.status === 'failed') return 'API connected — warmup failed';
  return 'API connected';
}

export function Header({ activeView, backendOnline, warmup, onOpenRunbook }: HeaderProps) {
  const statusText = describeStatus(backendOnline, warmup);
  const degraded = backendOnline === true && warmup?.status === 'failed';

  return (
    <header
      style={{
        height: 'var(--header-h)',
        flex: 'none',
        background: 'var(--surface)',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 16,
        padding: '0 20px',
        position: 'sticky',
        top: 0,
        zIndex: 20,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, minWidth: 0 }}>
        <span className="meta">SecureRAG</span>
        <span className="meta" aria-hidden="true">/</span>
        <span style={{ fontSize: '0.8125rem', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {VIEW_TITLES[activeView]}
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <p
          role="status"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            fontSize: '0.75rem',
            color: !backendOnline || degraded ? 'var(--critical)' : 'var(--text-secondary)',
          }}
        >
          <span className={`dot ${backendOnline && !degraded ? 'dot-ok' : 'dot-down'}`} aria-hidden="true" />
          {statusText}
        </p>

        <button type="button" className="btn btn-sm" onClick={onOpenRunbook}>
          <BookOpen size={14} aria-hidden="true" />
          IR Runbook
        </button>
      </div>
    </header>
  );
}
