/** Compact application sidebar: product mark plus primary navigation. */

import { Shield } from 'lucide-react';
import { NAV_ITEMS } from '../navigation';
import type { ViewId } from '../navigation';

interface SidebarProps {
  activeView: ViewId;
  onNavigate: (view: ViewId) => void;
}

export function Sidebar({ activeView, onNavigate }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <Shield size={17} color="var(--accent)" aria-hidden="true" />
        <div className="collapse-hide" style={{ lineHeight: 1.2 }}>
          <div style={{ fontSize: '0.875rem', fontWeight: 600, letterSpacing: '-0.01em' }}>SecureRAG</div>
          <div style={{ fontSize: '0.625rem', color: 'var(--text-muted)' }}>Threat Intelligence Console</div>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Primary">
        <ul>
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activeView === item.id;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  className="nav-btn"
                  onClick={() => onNavigate(item.id)}
                  aria-current={isActive ? 'page' : undefined}
                  title={item.label}
                >
                  <Icon size={15} aria-hidden="true" />
                  <span className="collapse-hide">{item.label}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="sidebar-foot">
        <p className="meta">Evidence-grounded retrieval with claim-level verification.</p>
      </div>
    </aside>
  );
}
