'use client';

/**
 * 0DTE GEX Frontend - Hybrid Dashboard Data Hook
 *
 * Provides unified data access with:
 * - WebSocket-first approach for real-time data
 * - Automatic fallback to REST polling when WebSocket fails
 * - Syncs WebSocket updates to React Query cache for consistency
 * - Exposes real-time status for UI indicators
 */

import {
  createElement,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useState,
  type ReactNode,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useGEXStream } from './useWebSocket';
import { useCurrentGEX, useCurrentRegime, useGEXByStrikes, useHistoricalGEX, queryKeys } from './useGEXData';
import { useMarketStatus } from './useMarketStatus';
import { getAppDataMode } from '@/lib/appMode';
import { canReplaceSnapshot, retainLatestSnapshot } from '@/lib/snapshots';
import { getCurrentMarketDateString } from '@/lib/utils';
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

const DashboardDataContext = createContext<DashboardData | null>(null);

/**
 * Unified hook for dashboard data that prefers WebSocket when available
 * and falls back to REST polling when disconnected.
 */
function useDashboardDataState(): DashboardData {
  const queryClient = useQueryClient();
  const [currentTime, setCurrentTime] = useState(() => Date.now());
  const { demoModeEnabled, selectedProvider } = useUIStore();
  const mode = getAppDataMode(demoModeEnabled);

  // WebSocket stream for real-time updates
  const wsStream = useGEXStream(demoModeEnabled, selectedProvider);
  const hasUsableRealtimeData = Boolean(
    wsStream.isConnected &&
      wsStream.data &&
      Number.isFinite(Date.parse(wsStream.data.timestamp ?? '')) &&
      wsStream.data.provider === selectedProvider &&
      Boolean(wsStream.data.is_demo) === demoModeEnabled &&
      typeof wsStream.data.total_call_gex === 'number' &&
      typeof wsStream.data.total_put_gex === 'number' &&
      wsStream.data.gex_by_strike && wsStream.data.metrics &&
      !wsStream.data.is_stale &&
      (
        !wsStream.data.is_mock ||
        (demoModeEnabled && wsStream.data.is_demo)
      )
  );

  // REST polling hooks (used as fallback and for initial data)
  const polledGEX = useCurrentGEX();
  const polledRegime = useCurrentRegime();
  const polledStrikes = useGEXByStrikes();
  const hasRealtimeGEX = hasUsableRealtimeData && (
    demoModeEnabled || canReplaceSnapshot(polledGEX.data?.timestamp, wsStream.data?.timestamp)
  );
  const hasRealtimeRegime = hasUsableRealtimeData && (
    demoModeEnabled || canReplaceSnapshot(polledRegime.data?.timestamp, wsStream.data?.timestamp)
  );

  const parseSnapshotTimestamp = useCallback((timestamp?: string | null) => {
    if (!timestamp) return null;
    const parsedTimestamp = Date.parse(timestamp);
    return Number.isNaN(parsedTimestamp) ? null : parsedTimestamp;
  }, []);

  // Update current time periodically for staleness checks
  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(Date.now());
    }, TIME_UPDATE_INTERVAL);
    return () => clearInterval(interval);
  }, []);

  // Sync WebSocket data to React Query cache for consistency
  useEffect(() => {
    if (hasUsableRealtimeData && wsStream.data) {
      const wsGexSnapshot: GEXSnapshot = {
        net_gex: wsStream.data.net_gex,
        zero_gamma_level: wsStream.data.zero_gamma_level,
        spot_price: wsStream.data.spot_price,
        timestamp: wsStream.data.timestamp || new Date().toISOString(),
        advanced_analytics: wsStream.data.advanced_analytics ?? null,
        total_call_gex: wsStream.data.total_call_gex!,
        total_put_gex: wsStream.data.total_put_gex!,
        gex_by_strike: wsStream.data.gex_by_strike!,
        dominant_strike: wsStream.data.dominant_strike ?? 0,
        metrics: wsStream.data.metrics!,
        provider: wsStream.data.provider,
      };

      // Update React Query cache with WebSocket data
      queryClient.setQueryData<GEXSnapshot>(queryKeys.gex.current(mode, selectedProvider), (previous) =>
        demoModeEnabled ? wsGexSnapshot : retainLatestSnapshot(previous, wsGexSnapshot)
      );

      // Create regime data from WebSocket update
      if (wsStream.data.regime) {
        const wsRegimeData: RegimeData = {
          regime: wsStream.data.regime,
          net_gex: wsStream.data.net_gex,
          net_gex_billions: wsStream.data.net_gex_billions,
          timestamp: wsStream.data.timestamp || new Date().toISOString(),
          description: wsStream.data.description ?? '',
          color: wsStream.data.color ?? 'yellow',
        };

        queryClient.setQueryData<RegimeData>(queryKeys.gex.regime(mode, selectedProvider), (previous) =>
          demoModeEnabled ? wsRegimeData : retainLatestSnapshot(previous, wsRegimeData)
        );
      }
    }
  }, [wsStream.data, hasUsableRealtimeData, queryClient, mode, selectedProvider, demoModeEnabled]);

  // Determine effective GEX data
  const gexData = useMemo((): GEXSnapshot | null => {
    // Prefer WebSocket data when connected and available
    if (hasRealtimeGEX && wsStream.data) {
      // Merge WebSocket update with polled data for complete snapshot
      return {
        timestamp: wsStream.data.timestamp || new Date().toISOString(),
        spot_price: wsStream.data.spot_price,
        net_gex: wsStream.data.net_gex,
        zero_gamma_level: wsStream.data.zero_gamma_level,
        total_call_gex: wsStream.data.total_call_gex!,
        total_put_gex: wsStream.data.total_put_gex!,
        gex_by_strike: wsStream.data.gex_by_strike!,
        dominant_strike: wsStream.data.dominant_strike ?? 0,
        metrics: wsStream.data.metrics!,
        provider: wsStream.data.provider,
        // Prefer WebSocket advanced analytics, fall back to polled
        advanced_analytics: wsStream.data.advanced_analytics ?? null,
      };
    }
    // Fall back to polled data
    return polledGEX.data ?? null;
  }, [hasRealtimeGEX, wsStream.data, polledGEX.data]);

  // Determine effective regime data
  const regimeData = useMemo((): RegimeData | null => {
    if (hasRealtimeRegime && wsStream.data?.regime) {
      return {
        regime: wsStream.data.regime,
        net_gex: wsStream.data.net_gex,
        net_gex_billions: wsStream.data.net_gex_billions,
        timestamp: wsStream.data.timestamp || new Date().toISOString(),
        description: wsStream.data.description ?? '',
        color: wsStream.data.color ?? 'yellow',
      };
    }
    return polledRegime.data ?? null;
  }, [hasRealtimeRegime, wsStream.data, polledRegime.data]);

  const websocketTimestamp = useMemo(
    () => parseSnapshotTimestamp(wsStream.data?.timestamp) ?? wsStream.lastUpdateTime ?? null,
    [parseSnapshotTimestamp, wsStream.data?.timestamp, wsStream.lastUpdateTime]
  );

  const polledTimestamp = useMemo(
    () =>
      parseSnapshotTimestamp(polledGEX.data?.timestamp) ??
      (polledGEX.dataUpdatedAt > 0 ? polledGEX.dataUpdatedAt : null),
    [parseSnapshotTimestamp, polledGEX.data?.timestamp, polledGEX.dataUpdatedAt]
  );

  const effectiveLastUpdateTime = useMemo(() => {
    if (hasRealtimeGEX) {
      return websocketTimestamp;
    }

    return polledTimestamp ?? websocketTimestamp;
  }, [hasRealtimeGEX, polledTimestamp, websocketTimestamp]);

  // Calculate staleness using state-based current time
  const isStale = useMemo(() => {
    const hasFresherPolledSnapshot =
      polledTimestamp !== null &&
      websocketTimestamp !== null &&
      polledTimestamp > websocketTimestamp;

    if (wsStream.isConnected && wsStream.data?.is_stale && !hasFresherPolledSnapshot) {
      return true;
    }

    if (!effectiveLastUpdateTime) return true;

    const timeSinceUpdate = currentTime - effectiveLastUpdateTime;
    return timeSinceUpdate > STALE_THRESHOLD;
  }, [
    wsStream.isConnected,
    wsStream.data,
    polledTimestamp,
    websocketTimestamp,
    effectiveLastUpdateTime,
    currentTime,
  ]);

  // Calculate loading state
  const isLoading =
    !hasRealtimeGEX && (polledGEX.isLoading || polledRegime.isLoading || polledStrikes.isLoading);

  // Determine error state
  const error =
    wsStream.error ||
    (polledGEX.error ? String(polledGEX.error) : null) ||
    (polledRegime.error ? String(polledRegime.error) : null) ||
    (polledStrikes.error ? String(polledStrikes.error) : null);

  return {
    gexData,
    regimeData,
    strikesData: hasRealtimeGEX && gexData ? {
      strikes: Object.keys(gexData.gex_by_strike).map(Number),
      gex_values: Object.values(gexData.gex_by_strike),
      spot_price: gexData.spot_price, zero_gamma_level: gexData.zero_gamma_level,
    } : polledStrikes.data ?? null,

    isRealtime: hasRealtimeGEX,
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

interface DashboardDataProviderProps {
  children: ReactNode;
}

export function DashboardDataProvider({ children }: DashboardDataProviderProps) {
  const value = useDashboardDataState();

  return createElement(DashboardDataContext.Provider, { value }, children);
}

export function useDashboardData(): DashboardData {
  const value = useContext(DashboardDataContext);

  if (value === null) {
    throw new Error('useDashboardData must be used within DashboardDataProvider');
  }

  return value;
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
  const sourceKey = JSON.stringify(timeSeriesKey);

  const [series, dispatch] = useReducer(
    (
      state: { key: string; points: TimeSeriesPoint[] },
      action:
        | { type: 'seed' | 'replace'; key: string; points: TimeSeriesPoint[] }
        | { type: 'add'; key: string; point: TimeSeriesPoint }
        | { type: 'clear'; key: string }
    ) => {
      if (action.type === 'replace') {
        return { key: action.key, points: action.points };
      }
      if (state.key !== action.key) return state;
      if (action.type === 'clear') {
        return { ...state, points: [] };
      }

      if (action.type === 'seed') {
        const seen = new Set<number>();
        const points = [...state.points, ...action.points]
          .sort((left, right) => left.timestamp - right.timestamp)
          .filter((point) => {
            if (seen.has(point.timestamp)) return false;
            seen.add(point.timestamp);
            return true;
          });
        return { ...state, points: points.slice(-1500) };
      }

      if (action.type === 'add') {
        const exists = state.points.some(
          (point) => Math.abs(point.timestamp - action.point.timestamp) < 1000
        );
        if (exists) return state;

        const points = [...state.points, action.point];
        return { ...state, points: points.length > 1500 ? points.slice(-1440) : points };
      }
      return state;
    },
    {
      key: sourceKey,
      points: queryClient.getQueryData<TimeSeriesPoint[]>(timeSeriesKey) ?? [],
    }
  );
  const timeSeries = series.key === sourceKey ? series.points : [];

  useEffect(() => {
    dispatch({
      type: 'replace',
      key: sourceKey,
      points: queryClient.getQueryData<TimeSeriesPoint[]>(timeSeriesKey) ?? [],
    });
  }, [queryClient, sourceKey, timeSeriesKey]);

  useEffect(() => {
    if (!persistedHistory.data?.data?.length) {
      return;
    }

    dispatch({
      type: 'seed',
      key: sourceKey,
      points: persistedHistory.data.data.map((snapshot: GEXSnapshot) => ({
        timestamp: Date.parse(snapshot.timestamp),
        netGex: snapshot.net_gex ?? 0,
        spotPrice: snapshot.spot_price ?? 0,
      })),
    });
  }, [persistedHistory.data, sourceKey]);

  // Accumulate data points from WebSocket OR REST updates for this source.
  useEffect(() => {
    if (gexData && lastUpdateTime) {
      const captureTime = new Date(gexData.timestamp);
      if (!demoModeEnabled && (
        !Number.isFinite(captureTime.getTime()) ||
        getCurrentMarketDateString(captureTime) !== tradingDateEt
      )) return;

      dispatch({
        type: 'add',
        key: sourceKey,
        point: {
          timestamp: lastUpdateTime,
          netGex: gexData.net_gex ?? 0,
          spotPrice: gexData.spot_price ?? 0,
        },
      });
    }
  }, [gexData, lastUpdateTime, sourceKey, demoModeEnabled, tradingDateEt]);

  useEffect(() => {
    if (series.key === sourceKey) {
      queryClient.setQueryData(timeSeriesKey, series.points);
    }
  }, [queryClient, series, sourceKey, timeSeriesKey]);

  const clearTimeSeries = useCallback(() => {
    dispatch({ type: 'clear', key: sourceKey });
  }, [sourceKey]);

  return {
    timeSeries,
    dataPointCount: timeSeries.length,
    clearTimeSeries,
  };
}
