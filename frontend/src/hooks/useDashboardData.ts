/**
 * 0DTE GEX Frontend - Hybrid Dashboard Data Hook
 *
 * Provides unified data access with:
 * - WebSocket-first approach for real-time data
 * - Automatic fallback to REST polling when WebSocket fails
 * - Syncs WebSocket updates to React Query cache for consistency
 * - Exposes real-time status for UI indicators
 */

import { useEffect, useMemo, useState, useCallback, useReducer, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useGEXStream } from './useWebSocket';
import { useCurrentGEX, useCurrentRegime, useGEXByStrikes, useHistoricalGEX, queryKeys } from './useGEXData';
import { useMarketStatus } from './useMarketStatus';
import { getAppDataMode } from '@/lib/appMode';
import { useUIStore } from '@/stores/uiStore';
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
  const [currentTime, setCurrentTime] = useState(() => Date.now());
  const { demoModeEnabled, selectedProvider } = useUIStore();
  const mode = getAppDataMode(demoModeEnabled);

  // WebSocket stream for real-time updates
  const wsStream = useGEXStream(demoModeEnabled, selectedProvider);
  const hasUsableRealtimeData = Boolean(
    wsStream.isConnected && wsStream.data && !wsStream.data.is_mock && !wsStream.data.is_stale
  );

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
      const currentGexCache = queryClient.getQueryData<GEXSnapshot>(
        queryKeys.gex.current(mode, selectedProvider)
      );
      const currentRegimeCache = queryClient.getQueryData<RegimeData>(
        queryKeys.gex.regime(mode, selectedProvider)
      );

      // Create a GEXSnapshot-like object from WebSocket update
      const wsGexSnapshot: Partial<GEXSnapshot> = {
        net_gex: wsStream.data.net_gex,
        zero_gamma_level: wsStream.data.zero_gamma_level,
        spot_price: wsStream.data.spot_price,
        timestamp: wsStream.data.timestamp || new Date().toISOString(),
        // Preserve other fields from cached data if available
        ...(currentGexCache && {
          total_call_gex: currentGexCache.total_call_gex,
          total_put_gex: currentGexCache.total_put_gex,
          gex_by_strike: currentGexCache.gex_by_strike,
          dominant_strike: currentGexCache.dominant_strike,
          metrics: currentGexCache.metrics,
        }),
      };

      // Update React Query cache with WebSocket data
      queryClient.setQueryData(queryKeys.gex.current(mode, selectedProvider), (old: GEXSnapshot | undefined) => ({
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
          ...(currentRegimeCache && {
            description: currentRegimeCache.description,
            color: currentRegimeCache.color,
          }),
        };

        queryClient.setQueryData(queryKeys.gex.regime(mode, selectedProvider), (old: RegimeData | undefined) => ({
          ...old,
          ...wsRegimeData,
        }));
      }
    }
  }, [wsStream.data, wsStream.isConnected, queryClient, mode, selectedProvider]);

  // Determine effective GEX data
  const gexData = useMemo((): GEXSnapshot | null => {
    // Prefer WebSocket data when connected and available
    if (hasUsableRealtimeData && wsStream.data) {
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
  }, [hasUsableRealtimeData, wsStream.data, polledGEX.data]);

  // Determine effective regime data
  const regimeData = useMemo((): RegimeData | null => {
    if (hasUsableRealtimeData && wsStream.data?.regime) {
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
  }, [hasUsableRealtimeData, wsStream.data, polledRegime.data]);

  const effectiveLastUpdateTime = useMemo(() => {
    if (wsStream.data?.timestamp) {
      const parsedTimestamp = Date.parse(wsStream.data.timestamp);
      if (!Number.isNaN(parsedTimestamp)) {
        return parsedTimestamp;
      }
    }

    return wsStream.lastUpdateTime ?? polledGEX.dataUpdatedAt ?? null;
  }, [wsStream.data, wsStream.lastUpdateTime, polledGEX.dataUpdatedAt]);

  // Calculate staleness using state-based current time
  const isStale = useMemo(() => {
    if (wsStream.isConnected && wsStream.data?.is_stale) {
      return true;
    }

    if (!effectiveLastUpdateTime) return true;

    const timeSinceUpdate = currentTime - effectiveLastUpdateTime;
    return timeSinceUpdate > STALE_THRESHOLD;
  }, [wsStream.isConnected, wsStream.data, effectiveLastUpdateTime, currentTime]);

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

    isRealtime: hasUsableRealtimeData,
    connectionState: wsStream.connectionState,
    isLoading,
    isStale,
    error,

    lastUpdateTime: effectiveLastUpdateTime,
    retryCount: wsStream.retryCount,

    reconnect: wsStream.reconnect,
    disconnect: wsStream.disconnect,
  };
}

/**
 * Hook that tracks intraday time series data by accumulating WebSocket updates.
 * Uses useReducer pattern to avoid setState-in-effect lint warnings.
 */
export function useIntradayTimeSeries(
  gexData: GEXSnapshot | null,
  lastUpdateTime: number | null
) {
  const queryClient = useQueryClient();
  const { demoModeEnabled, selectedProvider } = useUIStore();
  const mode = getAppDataMode(demoModeEnabled);
  const { data: marketStatus } = useMarketStatus();
  const tradingDateEt = useMemo(
    () => marketStatus?.current_time_et?.slice(0, 10) ?? '',
    [marketStatus?.current_time_et]
  );
  const timeSeriesKey = useMemo(
    () =>
      queryKeys.gex.intradaySeries(
        mode,
        selectedProvider,
        'SPX',
        tradingDateEt || 'pending-trading-day'
      ),
    [mode, selectedProvider, tradingDateEt]
  );
  const persistedHistory = useHistoricalGEX(tradingDateEt, tradingDateEt, '1m', 'SPX');
  const previousTimeSeriesKeyRef = useRef(timeSeriesKey);

  // Use reducer for accumulating time series to avoid setState in effect
  const [timeSeries, dispatch] = useReducer(
    (
      state: TimeSeriesPoint[],
      action:
        | { type: 'seed'; points: TimeSeriesPoint[] }
        | { type: 'add'; point: TimeSeriesPoint }
        | { type: 'clear' }
    ) => {
      if (action.type === 'clear') {
        return [];
      }

      if (action.type === 'seed') {
        const mergedPoints = [...state, ...action.points];
        const seen = new Set<number>();
        const deduped = mergedPoints
          .slice()
          .sort((left, right) => left.timestamp - right.timestamp)
          .filter((point) => {
            if (seen.has(point.timestamp)) {
              return false;
            }
            seen.add(point.timestamp);
            return true;
          });
        return deduped.slice(-1500);
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
    queryClient.getQueryData<TimeSeriesPoint[]>(timeSeriesKey) ?? []
  );

  useEffect(() => {
    const cachedSeries = queryClient.getQueryData<TimeSeriesPoint[]>(timeSeriesKey) ?? [];
    if (cachedSeries.length > 0) {
      dispatch({ type: 'seed', points: cachedSeries });
      return;
    }

    dispatch({ type: 'clear' });
  }, [queryClient, timeSeriesKey]);

  useEffect(() => {
    if (!persistedHistory.data?.data?.length) {
      return;
    }

    dispatch({
      type: 'seed',
      points: persistedHistory.data.data.map((snapshot: GEXSnapshot) => ({
        timestamp: Date.parse(snapshot.timestamp),
        netGex: snapshot.net_gex ?? 0,
        spotPrice: snapshot.spot_price ?? 0,
      })),
    });
  }, [persistedHistory.data]);

  // Accumulate data points from WebSocket OR REST updates
  useEffect(() => {
    if (gexData && lastUpdateTime) {
      dispatch({
        type: 'add',
        point: {
          timestamp: lastUpdateTime,
          netGex: gexData.net_gex ?? 0,
          spotPrice: gexData.spot_price ?? 0,
        },
      });
    }
  }, [gexData, lastUpdateTime]);

  useEffect(() => {
    if (previousTimeSeriesKeyRef.current !== timeSeriesKey) {
      previousTimeSeriesKeyRef.current = timeSeriesKey;
      return;
    }

    queryClient.setQueryData(timeSeriesKey, timeSeries);
    previousTimeSeriesKeyRef.current = timeSeriesKey;
  }, [queryClient, timeSeries, timeSeriesKey]);

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
