/**
 * Console navigation.
 *
 * Every entry maps to a capability the FastAPI backend actually exposes;
 * no view is listed here without a corresponding endpoint in backend/main.py.
 */

import {
  BarChart3,
  FileSearch,
  LayoutDashboard,
  ListOrdered,
  MessageSquare,
  Search,
  Server,
  Target,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export type ViewId =
  | 'dashboard'
  | 'chat'
  | 'vuln'
  | 'priority'
  | 'mitre'
  | 'evidence'
  | 'evaluation'
  | 'system';

export interface NavItem {
  id: ViewId;
  label: string;
  icon: LucideIcon;
  /** Backend endpoint the view depends on, shown on the System page. */
  endpoint: string;
}

export const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, endpoint: 'GET /api/health' },
  { id: 'chat', label: 'Analyst Console', icon: MessageSquare, endpoint: 'POST /api/chat' },
  { id: 'vuln', label: 'Vulnerabilities', icon: FileSearch, endpoint: 'GET /api/cve/{id}' },
  { id: 'priority', label: 'Prioritization', icon: ListOrdered, endpoint: 'POST /api/priority' },
  { id: 'mitre', label: 'MITRE ATT&CK', icon: Target, endpoint: 'GET /api/mitre/{id}' },
  { id: 'evidence', label: 'Evidence Search', icon: Search, endpoint: 'POST /api/retrieve' },
  { id: 'evaluation', label: 'Evaluation', icon: BarChart3, endpoint: 'GET /api/evaluation' },
  { id: 'system', label: 'System', icon: Server, endpoint: 'GET /api/health' },
];

export const VIEW_TITLES: Record<ViewId, string> = {
  dashboard: 'Dashboard',
  chat: 'Analyst Console',
  vuln: 'Vulnerabilities',
  priority: 'Vulnerability Prioritization',
  mitre: 'MITRE ATT&CK',
  evidence: 'Evidence Search',
  evaluation: 'Evaluation',
  system: 'System',
};
