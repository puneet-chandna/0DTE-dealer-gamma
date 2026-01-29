/**
 * DashboardHeader - Header with title, connection status, and controls
 */

'use client';

import { memo } from 'react';
import { Moon, Sun, RefreshCw, Wifi, WifiOff, Radio } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useUIStore } from '@/stores/uiStore';
import { Badge, ConnectionStatus } from '@/components/ui';
import type { ConnectionState } from '@/types';

interface DashboardHeaderProps {
  isConnected?: boolean;
  isRealtime?: boolean;
  connectionState?: ConnectionState;
  retryCount?: number;
  isLoading?: boolean;
  lastUpdate?: string;
  onRefresh?: () => void;
}

function DashboardHeaderComponent({
  isConnected = false,
  isRealtime = false,
  connectionState = 'idle',
  retryCount = 0,
  isLoading = false,
  lastUpdate,
  onRefresh,
}: DashboardHeaderProps) {
  const { isDarkMode, toggleDarkMode, autoRefreshEnabled, setAutoRefresh } =
    useUIStore();

  return (
    <header className="flex items-center justify-between border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-sm px-6 py-4">
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

      {/* Center: Connection Status */}
      <div className="flex items-center gap-4">
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

        {/* Detailed connection status */}
        <ConnectionStatus
          connectionState={connectionState}
          isRealtime={isRealtime}
          retryCount={retryCount}
        />

        {/* Last update time */}
        {lastUpdate && (
          <span className="text-xs text-zinc-500">
            Updated: {lastUpdate}
          </span>
        )}
      </div>

      {/* Right: Controls */}
      <div className="flex items-center gap-2">
        {/* Auto-refresh toggle */}
        <button
          onClick={() => setAutoRefresh(!autoRefreshEnabled)}
          className={cn(
            'flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors',
            autoRefreshEnabled
              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
              : 'bg-zinc-800 text-zinc-400 border border-zinc-700 hover:bg-zinc-700'
          )}
          title={autoRefreshEnabled ? 'Auto-refresh enabled' : 'Auto-refresh disabled'}
        >
          <RefreshCw
            className={cn('h-3.5 w-3.5', isLoading && 'animate-spin')}
          />
          {autoRefreshEnabled ? 'Auto' : 'Manual'}
        </button>

        {/* Manual refresh */}
        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-300 disabled:opacity-50"
            title="Refresh data"
          >
            <RefreshCw
              className={cn('h-4 w-4', isLoading && 'animate-spin')}
            />
          </button>
        )}

        {/* Theme toggle */}
        <button
          onClick={toggleDarkMode}
          className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-300"
          title={isDarkMode ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {isDarkMode ? (
            <Sun className="h-4 w-4" />
          ) : (
            <Moon className="h-4 w-4" />
          )}
        </button>
      </div>
    </header>
  );
}

export const DashboardHeader = memo(DashboardHeaderComponent);
