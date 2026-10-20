'use client';

import { memo } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { Activity, BarChart3, LineChart, Waves, FlaskConical, RefreshCw, Radio } from 'lucide-react';
import { useMarketStatus } from '@/hooks/useMarketStatus';
import { useUIStore } from '@/stores/uiStore';
import { ProviderSelector } from './ProviderSelector';
import type { ConnectionState } from '@/types';

const navItems = [
  { href: '/dashboard', label: 'Dashboard', icon: BarChart3 },
  { href: '/analytics', label: 'Analytics', icon: LineChart },
  { href: '/dealer-flows', label: 'Dealer Flows', icon: Waves },
  { href: '/backtest', label: 'Backtest', icon: FlaskConical },
];

interface NavBarProps {
  isConnected?: boolean;
  isRealtime?: boolean;
  connectionState?: ConnectionState;
  retryCount?: number;
  isLoading?: boolean;
  lastUpdate?: string;
  captureTimestampLabel?: string;
  onRefresh?: () => void;
}

function NavBarComponent({ isRealtime, connectionState, retryCount = 0, isLoading, lastUpdate, captureTimestampLabel, onRefresh }: NavBarProps) {
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { demoModeEnabled, toggleDemoMode, autoRefreshEnabled, setAutoRefresh } = useUIStore();
  const { data: marketStatus } = useMarketStatus();
  const refresh = onRefresh ?? (() => {
    void queryClient.invalidateQueries({ predicate: query => ['gex', 'analytics', 'iv-surface', 'technical-indicators'].includes(String(query.queryKey[0])) });
  });
  const transport = connectionState === 'connecting'
    ? `Connecting${retryCount ? ` (${retryCount})` : ''}`
    : isRealtime ? 'Stream connected' : connectionState === 'connected' ? 'Polling connected' : 'REST fallback';

  return <header className="research-nav">
    <a className="sr-only focus:not-sr-only" href="#research-content">Skip to research content</a>
    <div className="nav-row">
      <Link href="/dashboard" className="research-brand" aria-label="0DTE Research home"><Activity size={21} aria-hidden="true" /><span>0DTE Research</span></Link>
      <nav className="page-links" aria-label="Research pages">
        {navItems.map(({ href, label, icon: Icon }) => <Link key={href} href={href} aria-current={pathname === href ? 'page' : undefined}><Icon size={16} aria-hidden="true" />{label}</Link>)}
      </nav>
      <div className="nav-controls">
        <ProviderSelector />
        <button type="button" className={`control-button ${demoModeEnabled ? 'demo-active' : ''}`} aria-pressed={demoModeEnabled} onClick={toggleDemoMode} title="Explore captured replay or synthetic examples; each panel identifies its data">Demo</button>
        {pathname !== '/backtest' && <button type="button" className="control-button" aria-label="Auto poll" aria-pressed={autoRefreshEnabled} onClick={() => setAutoRefresh(!autoRefreshEnabled)} title="Automatically refresh displayed market captures; backend collection continues">Auto poll</button>}
        <button type="button" className="control-button" aria-label="Refresh data" title="Fetch the latest available data" disabled={isLoading} onClick={refresh}><RefreshCw size={16} aria-hidden="true" /></button>
        <span className="session-state" title={marketStatus?.next_open ? `Next open: ${marketStatus.next_open}` : undefined}>{marketStatus ? marketStatus.is_open ? 'US session open' : 'US session closed' : 'Checking session'}</span>
      </div>
    </div>
    {(connectionState || captureTimestampLabel) && <div className="transport-line"><span className="inline-flex items-center gap-2"><Radio size={13} aria-hidden="true" />{transport}</span>{captureTimestampLabel && <span>{captureTimestampLabel}</span>}{!captureTimestampLabel && lastUpdate && <span>Capture time: {lastUpdate}</span>}<span>Connection status does not establish quote freshness.</span></div>}
  </header>;
}

export const NavBar = memo(NavBarComponent);
