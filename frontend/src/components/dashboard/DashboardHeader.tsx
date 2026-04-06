/**
 * DashboardHeader - Header with title, connection status, and controls
 */

'use client';

import { memo, useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Moon,
  Sun,
  RefreshCw,
  Wifi,
  WifiOff,
  Radio,
  BarChart3,
  LineChart,
  Waves,
  FlaskConical,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { Badge, ConnectionStatus, ProviderSelector } from '@/components/ui';
import type { ConnectionState } from '@/types';

const pageLinks = [
  { href: '/dashboard', label: 'Dashboard', icon: BarChart3 },
  { href: '/analytics', label: 'Analytics', icon: LineChart },
  { href: '/dealer-flows', label: 'Dealer Flows', icon: Waves },
  { href: '/backtest', label: 'Backtest', icon: FlaskConical },
] as const;

interface DashboardHeaderProps {
  isConnected?: boolean;
  isRealtime?: boolean;
  connectionState?: ConnectionState;
  retryCount?: number;
  isLoading?: boolean;
  lastUpdate?: string;
  captureTimestampLabel?: string;
  onRefresh?: () => void;
}

function DashboardHeaderComponent({
  isRealtime = false,
  connectionState = 'idle',
  retryCount = 0,
  isLoading = false,
  lastUpdate,
  captureTimestampLabel,
  onRefresh,
}: DashboardHeaderProps) {
  const pathname = usePathname();
  const {
    isDarkMode,
    toggleDarkMode,
    autoRefreshEnabled,
    setAutoRefresh,
    demoModeEnabled,
    toggleDemoMode,
  } =
    useUIStore();
  const [hasMounted, setHasMounted] = useState(false);

  const isConnected = connectionState === 'connected';
  const showDarkModeEnabled = hasMounted && isDarkMode;

  useEffect(() => {
    setHasMounted(true);
  }, []);

  return (
    <header className="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-sm">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-start justify-between gap-4 px-4 py-4 sm:px-6 xl:flex-nowrap xl:items-center xl:px-8">
        {/* Left: Logo and Title */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3">
            {/* Logo */}
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500">
              <span className="text-sm font-bold text-white">Γ</span>
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-tight text-zinc-50">
                0DTE GEX Monitor
              </h1>
              <p className="text-xs text-zinc-500">Dealer Gamma Exposure</p>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1">
          {pageLinks.map(({ href, label, icon: Icon }) => {
            const isActive = pathname === href || pathname?.startsWith(`${href}/`);

            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  'flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200',
                  isActive
                    ? 'bg-violet-500/15 text-violet-300 ring-1 ring-violet-500/20'
                    : 'text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200'
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </div>

        {/* Center: Connection Status */}
        <div className="flex flex-wrap items-center gap-3 sm:gap-4 xl:ml-auto">
          {/* Real-time vs Polling indicator */}
          {isRealtime ? (
            <Badge variant="live" pulse>
              <Radio className="h-3 w-3" />
              Real-time
            </Badge>
          ) : isConnected ? (
            <Badge variant="success">
              <Wifi className="h-3 w-3" />
              Connected
            </Badge>
          ) : connectionState === 'connecting' ? (
            <Badge variant="warning">
              <RefreshCw className="h-3 w-3 animate-spin" />
              Connecting{retryCount > 0 ? ` (${retryCount})` : ''}
            </Badge>
          ) : connectionState === 'error' ? (
            <Badge variant="danger">
              <WifiOff className="h-3 w-3" />
              Error
            </Badge>
          ) : (
            <Badge variant="neutral">
              <WifiOff className="h-3 w-3" />
              Polling
            </Badge>
          )}

          <ConnectionStatus
            connectionState={connectionState}
            isRealtime={isRealtime}
            retryCount={retryCount}
          />

          {(lastUpdate || captureTimestampLabel) && (
            <div className="flex flex-col items-start gap-0.5 text-xs">
              {lastUpdate && (
                <span className="text-zinc-500">
                  Updated: {lastUpdate}
                </span>
              )}
              {captureTimestampLabel && (
                <span className="text-zinc-400">
                  {captureTimestampLabel}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Right: Controls */}
        <div className="flex flex-wrap items-center gap-2 xl:justify-end">
          <ProviderSelector />

          <button
            type="button"
            onClick={toggleDemoMode}
            className={cn(
              'rounded-md px-2.5 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] transition-colors',
              demoModeEnabled
                ? 'border border-amber-500/30 bg-amber-500/15 text-amber-300'
                : 'border border-zinc-700 bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200'
            )}
            title="Toggle coherent demo mode across the app"
          >
            Demo
          </button>

          <button
            onClick={() => setAutoRefresh(!autoRefreshEnabled)}
            className={cn(
              'flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors',
              autoRefreshEnabled
                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                : 'bg-zinc-800 text-zinc-400 border border-zinc-700 hover:bg-zinc-700'
            )}
            title={
              autoRefreshEnabled
                ? 'Auto REST polling is enabled. Backend capture keeps running either way.'
                : 'Manual REST polling only. Use the refresh button to fetch a new snapshot.'
            }
          >
            <RefreshCw
              className={cn('h-3.5 w-3.5', isLoading && 'animate-spin')}
            />
            {autoRefreshEnabled ? 'Auto Poll' : 'Manual Poll'}
          </button>

          {onRefresh && (
            <button
              onClick={onRefresh}
              disabled={isLoading}
              className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-300 disabled:opacity-50"
              title="Fetch the latest REST snapshot now"
            >
              <RefreshCw
                className={cn('h-4 w-4', isLoading && 'animate-spin')}
              />
            </button>
          )}

          <button
            onClick={toggleDarkMode}
            className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-300"
            title={
              hasMounted
                ? showDarkModeEnabled
                  ? 'Switch to light mode'
                  : 'Switch to dark mode'
                : 'Toggle theme'
            }
          >
            {showDarkModeEnabled ? (
              <Sun className="h-4 w-4" />
            ) : (
              <Moon className="h-4 w-4" />
            )}
          </button>
        </div>
      </div>
    </header>
  );
}

export const DashboardHeader = memo(DashboardHeaderComponent);
