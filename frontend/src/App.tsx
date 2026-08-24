import { useCallback, useEffect, useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { DashboardView } from './components/DashboardView';
import { CopilotChatView } from './components/CopilotChatView';
import { VulnerabilityView } from './components/VulnerabilityView';
import { PatchPriorityView } from './components/PatchPriorityView';
import { MitreAttackView } from './components/MitreAttackView';
import { EvidenceSearchView } from './components/EvidenceSearchView';
import { EvaluationView } from './components/EvaluationView';
import { SystemView } from './components/SystemView';
import { RunbookModal } from './components/RunbookModal';
import { checkHealth } from './services/api';
import type { ViewId } from './navigation';
import type { HealthResponse } from './types';

// Health is a cheap liveness probe, not a data source. Poll infrequently and
// only while the tab is visible so it never competes with a running query.
const HEALTH_POLL_MS = 30000;

export function App() {
  const [activeView, setActiveView] = useState<ViewId>('dashboard');
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [runbookOpen, setRunbookOpen] = useState(false);

  const verifyBackendHealth = useCallback(async () => {
    try {
      const payload = await checkHealth();
      setHealth(payload);
      setBackendOnline(true);
    } catch {
      setHealth(null);
      setBackendOnline(false);
    }
  }, []);

  useEffect(() => {
    verifyBackendHealth();

    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') {
        verifyBackendHealth();
      }
    }, HEALTH_POLL_MS);

    // Re-check immediately when the tab regains focus rather than polling harder.
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') verifyBackendHealth();
    };
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [verifyBackendHealth]);

  return (
    <div className="shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>

      <Sidebar activeView={activeView} onNavigate={setActiveView} />

      <div className="shell-main">
        <Header
          activeView={activeView}
          backendOnline={backendOnline}
          warmup={health?.warmup ?? null}
          onOpenRunbook={() => setRunbookOpen(true)}
        />

        <main id="main-content" className="shell-content">
          {activeView === 'dashboard' && (
            <DashboardView health={health} backendOnline={backendOnline} onNavigate={setActiveView} />
          )}
          {activeView === 'chat' && <CopilotChatView />}
          {activeView === 'vuln' && <VulnerabilityView />}
          {activeView === 'priority' && <PatchPriorityView />}
          {activeView === 'mitre' && <MitreAttackView />}
          {activeView === 'evidence' && <EvidenceSearchView />}
          {activeView === 'evaluation' && <EvaluationView />}
          {activeView === 'system' && (
            <SystemView health={health} backendOnline={backendOnline} onRefresh={verifyBackendHealth} />
          )}
        </main>
      </div>

      <RunbookModal isOpen={runbookOpen} onClose={() => setRunbookOpen(false)} />
    </div>
  );
}

export default App;
