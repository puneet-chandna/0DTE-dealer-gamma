/**
 * 0DTE GEX Frontend - Hybrid Dashboard Data Hook
 *
 * Provides unified data access with:
 * - WebSocket-first approach for real-time data
 * - Automatic fallback to REST polling when WebSocket fails
 * - Syncs WebSocket updates to React Query cache for consistency
 * - Exposes real-time status for UI indicators
 */

import { useEffect, useMemo, useState, useCallback, useReducer } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useGEXStream } from './useWebSocket';
import { useCurrentGEX, useCurrentRegime, useGEXByStrikes, queryKeys } from './useGEXData';
import type { GEXSnapshot, RegimeData, GEXByStrike, ConnectionState } from '@/types';

// Stale data threshold (milliseconds)
const STALE_THRESHOLD = 60000; // 60 seconds
// Time update interval for staleness checks
const TIME_UPDATE_INTERVAL = 5000; // 5 seconds

interface DashboardData {
  // GEX Data
  gexData: GEXSnapshot | null;
  regimeData: RegimeData | null;
  strikesData: GEXByStrike | null;

  // Connection status
  isRealtime: boolean;
  connectionState: ConnectionState;
  isLoading: boolean;
  isStale: boolean;
  error: string | null;

  // Timing
  lastUpdateTime: number | null;
  retryCount: number;

  // Actions
  reconnect: () => void;
  disconnect: () => void;
}

interface TimeSeriesPoint {
  timestamp: number;
  netGex: number;
  spotPrice: number;
}

/**
 * Unified hook for dashboard data that prefers WebSocket when available
 * and falls back to REST polling when disconnected.
 */
export function useDashboardData(): DashboardData {
  const queryClient = useQueryClient();
  const [currentTime, setCurrentTime] = useState(Date.now);

  // WebSocket stream for real-time updates
  const wsStream = useGEXStream();

  // REST polling hooks (used as fallback and for initial data)
  const polledGEX = useCurrentGEX();
  const polledRegime = useCurrentRegime();
  const polledStrikes = useGEXByStrikes();

  // Update current time periodically for staleness checks
  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(Date.now());
    }, TIME_UPDATE_INTERVAL);
    return () => clearInterval(interval);
  }, []);

  // Sync WebSocket data to React Query cache for consistency
  useEffect(() => {
    if (wsStream.isConnected && wsStream.data) {
      // Create a GEXSnapshot-like object from WebSocket update
      const wsGexSnapshot: Partial<GEXSnapshot> = {
        net_gex: wsStream.data.net_gex,
        zero_gamma_level: wsStream.data.zero_gamma_level,
        spot_price: wsStream.data.spot_price,
        timestamp: wsStream.data.timestamp || new Date().toISOString(),
        // Preserve other fields from cached data if available
        ...(polledGEX.data && {
          total_call_gex: polledGEX.data.total_call_gex,
          total_put_gex: polledGEX.data.total_put_gex,
          gex_by_strike: polledGEX.data.gex_by_strike,
          dominant_strike: polledGEX.data.dominant_strike,
          metrics: polledGEX.data.metrics,
        }),
      };

      // Update React Query cache with WebSocket data
      queryClient.setQueryData(queryKeys.gex.current, (old: GEXSnapshot | undefined) => ({
        ...old,
        ...wsGexSnapshot,
      }));

      // Create regime data from WebSocket update
      if (wsStream.data.regime) {
        const wsRegimeData: Partial<RegimeData> = {
          regime: wsStream.data.regime,
          net_gex: wsStream.data.net_gex,
          net_gex_billions: wsStream.data.net_gex_billions,
          timestamp: wsStream.data.timestamp || new Date().toISOString(),
          // Preserve description and color from cached data
          ...(polledRegime.data && {
            description: polledRegime.data.description,
            color: polledRegime.data.color,
          }),
        };

        queryClient.setQueryData(queryKeys.gex.regime, (old: RegimeData | undefined) => ({
          ...old,
          ...wsRegimeData,
        }));
      }
    }
  }, [wsStream.data, wsStream.isConnected, queryClient, polledGEX.data, polledRegime.data]);

  // Determine effective GEX data
  const gexData = useMemo((): GEXSnapshot | null => {
    // Prefer WebSocket data when connected and available
    if (wsStream.isConnected && wsStream.data) {
      // Merge WebSocket update with polled data for complete snapshot
      return {
        timestamp: wsStream.data.timestamp || new Date().toISOString(),
        spot_price: wsStream.data.spot_price,
        net_gex: wsStream.data.net_gex,
        zero_gamma_level: wsStream.data.zero_gamma_level,
        total_call_gex: polledGEX.data?.total_call_gex ?? 0,
        total_put_gex: polledGEX.data?.total_put_gex ?? 0,
        gex_by_strike: polledGEX.data?.gex_by_strike ?? {},
        dominant_strike: polledGEX.data?.dominant_strike ?? 0,
        metrics: polledGEX.data?.metrics ?? {},
      };
    }
    // Fall back to polled data
    return polledGEX.data ?? null;
  }, [wsStream.isConnected, wsStream.data, polledGEX.data]);

  // Determine effective regime data
  const regimeData = useMemo((): RegimeData | null => {
    if (wsStream.isConnected && wsStream.data?.regime) {
      return {
        regime: wsStream.data.regime,
        net_gex: wsStream.data.net_gex,
        net_gex_billions: wsStream.data.net_gex_billions,
        timestamp: wsStream.data.timestamp || new Date().toISOString(),
        description: polledRegime.data?.description ?? '',
        color: polledRegime.data?.color ?? 'yellow',
      };
    }
    return polledRegime.data ?? null;
  }, [wsStream.isConnected, wsStream.data, polledRegime.data]);

  // Calculate staleness using state-based current time
  const isStale = useMemo(() => {
    const lastUpdate = wsStream.lastUpdateTime ?? polledGEX.dataUpdatedAt ?? null;
    if (!lastUpdate) return true;

    const timeSinceUpdate = currentTime - lastUpdate;
    return timeSinceUpdate > STALE_THRESHOLD;
  }, [wsStream.lastUpdateTime, polledGEX.dataUpdatedAt, currentTime]);

  // Calculate loading state
  const isLoading =
    (!wsStream.isConnected && polledGEX.isLoading) ||
    (!wsStream.isConnected && polledRegime.isLoading) ||
    (!wsStream.isConnected && polledStrikes.isLoading);

  // Determine error state
  const error =
    wsStream.error ||
    (polledGEX.error ? String(polledGEX.error) : null) ||
    (polledRegime.error ? String(polledRegime.error) : null) ||
    (polledStrikes.error ? String(polledStrikes.error) : null);

  return {
    gexData,
    regimeData,
    strikesData: polledStrikes.data ?? null,

    isRealtime: wsStream.isConnected,
    connectionState: wsStream.connectionState,
    isLoading,
    isStale,
    error,

    lastUpdateTime: wsStream.lastUpdateTime ?? polledGEX.dataUpdatedAt ?? null,
    retryCount: wsStream.retryCount,

    reconnect: wsStream.reconnect,
    disconnect: wsStream.disconnect,
  };
}

/**
 * Hook that tracks intraday time series data by accumulating WebSocket updates.
 * Uses useReducer pattern to avoid setState-in-effect lint warnings.
 */
export function useIntradayTimeSeries() {
  const { gexData, isRealtime, lastUpdateTime } = useDashboardData();

  // Use reducer for accumulating time series to avoid setState in effect
  const [timeSeries, dispatch] = useReducer(
    (state: TimeSeriesPoint[], action: { type: 'add'; point: TimeSeriesPoint } | { type: 'clear' }) => {
      if (action.type === 'clear') {
        return [];
      }

      if (action.type === 'add') {
        // Only add new data points (deduplicate by timestamp)
        const exists = state.some(
          (point) => Math.abs(point.timestamp - action.point.timestamp) < 1000
        );

        if (exists) return state;

        const updated = [...state, action.point];

        // Keep only last 2 hours of data (assuming 5s updates = 1440 points)
        if (updated.length > 1500) {
          return updated.slice(-1440);
        }

        return updated;
      }

      return state;
    },
    []
  );

  // Accumulate data points from WebSocket updates
  useEffect(() => {
    if (isRealtime && gexData && lastUpdateTime) {
      dispatch({
        type: 'add',
        point: {
          timestamp: lastUpdateTime,
          netGex: gexData.net_gex ?? 0,
          spotPrice: gexData.spot_price ?? 0,
        },
      });
    }
  }, [gexData, isRealtime, lastUpdateTime]);

  // Clear time series (e.g., on market close)
  const clearTimeSeries = useCallback(() => {
    dispatch({ type: 'clear' });
  }, []);

  return {
    timeSeries,
    dataPointCount: timeSeries.length,
    clearTimeSeries,
  };
}
