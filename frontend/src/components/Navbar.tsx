import React from 'react';
import {
  ShieldAlert,
  MessageSquare,
  FileSearch,
  ListOrdered,
  Grid,
  BarChart3,
  BookOpen,
} from 'lucide-react';

interface NavbarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  backendOnline: boolean;
  onOpenRunbook: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  backendOnline,
  onOpenRunbook,
}) => {
  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: Grid },
    { id: 'chat', label: 'SOC Copilot', icon: MessageSquare },
    { id: 'vuln', label: 'Vulnerability Triage', icon: FileSearch },
    { id: 'priority', label: 'Patch Priority', icon: ListOrdered },
    { id: 'mitre', label: 'MITRE ATT&CK', icon: ShieldAlert },
    { id: 'evaluation', label: 'Evaluation Metrics', icon: BarChart3 },
  ];

  return (
    <header className="glass-panel" style={{ borderRadius: 0, borderTop: 0, borderLeft: 0, borderRight: 0, padding: '12px 24px', position: 'sticky', top: 0, zIndex: 50 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', maxWidth: '1400px', margin: '0 auto' }}>
        {/* Brand Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ width: '38px', height: '38px', borderRadius: '10px', background: 'linear-gradient(135deg, #00f2fe, #7928ca)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 0 15px rgba(0, 242, 254, 0.4)' }}>
            <ShieldAlert size={22} color="#fff" />
          </div>
          <div>
            <h1 style={{ fontSize: '1.2rem', fontWeight: 800, background: 'linear-gradient(90deg, #fff, #94a3b8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', letterSpacing: '-0.02em' }}>
              SecureRAG
            </h1>
            <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600 }}>
              Hallucination-Safe Cyber Copilot
            </p>
          </div>
        </div>

        {/* Nav Tabs */}
        <nav style={{ display: 'flex', gap: '6px', background: 'rgba(10, 13, 20, 0.6)', padding: '4px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '8px 14px',
                  borderRadius: '8px',
                  fontSize: '0.85rem',
                  fontWeight: isActive ? 600 : 400,
                  color: isActive ? 'var(--accent-cyan)' : 'var(--text-secondary)',
                  background: isActive ? 'rgba(0, 242, 254, 0.12)' : 'transparent',
                  border: isActive ? '1px solid rgba(0, 242, 254, 0.3)' : '1px solid transparent',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                <Icon size={16} />
                {item.label}
              </button>
            );
          })}
        </nav>

        {/* Right Status Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <button
            onClick={onOpenRunbook}
            className="btn-secondary"
            style={{ fontSize: '0.82rem', padding: '7px 14px' }}
          >
            <BookOpen size={15} color="var(--accent-cyan)" />
            IR Runbook
          </button>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(255, 255, 255, 0.04)', padding: '6px 12px', borderRadius: '20px', border: '1px solid var(--border-color)' }}>
            <div className={backendOnline ? 'pulse-live' : ''} style={!backendOnline ? { width: 8, height: 8, borderRadius: '50%', backgroundColor: 'var(--accent-red)' } : {}} />
            <span style={{ fontSize: '0.78rem', color: backendOnline ? 'var(--accent-green)' : 'var(--accent-red)', fontWeight: 600 }}>
              {backendOnline ? 'API Connected' : 'API Offline'}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
};
