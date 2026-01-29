/**
 * Connection Status Component
 *
 * Visual indicator for WebSocket/polling connection state.
 * Shows:
 * - 🟢 Real-time (WebSocket connected)
 * - 🟡 Polling (WebSocket disconnected, using REST)
 * - 🔴 Offline/Error (no data available)
 */

'use client';

import { memo } from 'react';
import type { ConnectionState } from '@/types';

interface ConnectionStatusProps {
  connectionState: ConnectionState;
  isRealtime: boolean;
  retryCount?: number;
  className?: string;
}

const statusConfig: Record<
  ConnectionState,
  { color: string; bgColor: string; label: string; pulse?: boolean }
> = {
  idle: {
    color: 'text-zinc-400',
    bgColor: 'bg-zinc-600',
    label: 'Initializing',
  },
  connecting: {
    color: 'text-amber-400',
    bgColor: 'bg-amber-500',
    label: 'Connecting',
    pulse: true,
  },
  connected: {
    color: 'text-emerald-400',
    bgColor: 'bg-emerald-500',
    label: 'Real-time',
  },
  disconnected: {
    color: 'text-amber-400',
    bgColor: 'bg-amber-500',
    label: 'Polling',
  },
  error: {
    color: 'text-red-400',
    bgColor: 'bg-red-500',
    label: 'Error',
  },
};

/**
 * ConnectionStatus displays the current data connection state.
 */
export const ConnectionStatus = memo(function ConnectionStatus({
  connectionState,
  isRealtime,
  retryCount = 0,
  className = '',
}: ConnectionStatusProps) {
  // Determine display state
  const displayState = isRealtime ? 'connected' : connectionState;
  const config = statusConfig[displayState];

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {/* Status indicator dot */}
      <span className="relative flex h-2.5 w-2.5">
        {config.pulse && (
          <span
            className={`absolute inline-flex h-full w-full animate-ping rounded-full ${config.bgColor} opacity-75`}
          />
        )}
        <span
          className={`relative inline-flex h-2.5 w-2.5 rounded-full ${config.bgColor}`}
        />
      </span>

      {/* Status label */}
      <span className={`text-xs font-medium ${config.color}`}>
        {config.label}
        {connectionState === 'connecting' && retryCount > 0 && (
          <span className="ml-1 text-zinc-500">
            (retry {retryCount})
          </span>
        )}
      </span>
    </div>
  );
});

/**
 * Compact version for tight spaces (just the dot with tooltip).
 */
export const ConnectionStatusDot = memo(function ConnectionStatusDot({
  connectionState,
  isRealtime,
  className = '',
}: Omit<ConnectionStatusProps, 'retryCount'>) {
  const displayState = isRealtime ? 'connected' : connectionState;
  const config = statusConfig[displayState];

  return (
    <span
      className={`relative flex h-2 w-2 ${className}`}
      title={config.label}
    >
      {config.pulse && (
        <span
          className={`absolute inline-flex h-full w-full animate-ping rounded-full ${config.bgColor} opacity-75`}
        />
      )}
      <span
        className={`relative inline-flex h-2 w-2 rounded-full ${config.bgColor}`}
      />
    </span>
  );
});
