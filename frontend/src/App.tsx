import React, { useEffect, useState } from 'react';
import { Navbar } from './components/Navbar';
import { DashboardView } from './components/DashboardView';
import { CopilotChatView } from './components/CopilotChatView';
import { VulnerabilityView } from './components/VulnerabilityView';
import { PatchPriorityView } from './components/PatchPriorityView';
import { MitreAttackView } from './components/MitreAttackView';
import { EvaluationView } from './components/EvaluationView';
import { RunbookModal } from './components/RunbookModal';
import { checkHealth } from './services/api';

export function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [backendOnline, setBackendOnline] = useState(false);
  const [runbookOpen, setRunbookOpen] = useState(false);

  useEffect(() => {
    verifyBackendHealth();
    const interval = setInterval(verifyBackendHealth, 15000);
    return () => clearInterval(interval);
  }, []);

  const verifyBackendHealth = async () => {
    try {
      await checkHealth();
      setBackendOnline(true);
    } catch {
      setBackendOnline(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top Header Navbar */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        backendOnline={backendOnline}
        onOpenRunbook={() => setRunbookOpen(true)}
      />

      {/* Main Active Tab View */}
      <main style={{ flex: 1 }}>
        {activeTab === 'dashboard' && <DashboardView onNavigate={setActiveTab} />}
        {activeTab === 'chat' && <CopilotChatView />}
        {activeTab === 'vuln' && <VulnerabilityView />}
        {activeTab === 'priority' && <PatchPriorityView />}
        {activeTab === 'mitre' && <MitreAttackView />}
        {activeTab === 'evaluation' && <EvaluationView />}
      </main>

      {/* IR Runbook Modal */}
      <RunbookModal isOpen={runbookOpen} onClose={() => setRunbookOpen(false)} />
    </div>
  );
}

export default App;
