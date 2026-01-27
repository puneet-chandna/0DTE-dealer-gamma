/**
 * 0DTE GEX Frontend - React Query Hooks for GEX Data
 *
 * RULE: Use React Query for SERVER STATE (API data).
 * Use Zustand for CLIENT STATE (UI settings).
 */

import { useQuery } from '@tanstack/react-query';
import { gexAPI, analyticsAPI, healthAPI } from '@/lib/api';
import { useUIStore } from '@/stores/uiStore';

/**
 * Query keys for cache management.
 */
export const queryKeys = {
  gex: {
    current: ['gex', 'current'] as const,
    strikes: ['gex', 'strikes'] as const,
    regime: ['gex', 'regime'] as const,
    historical: (startDate: string, endDate: string) =>
      ['gex', 'historical', startDate, endDate] as const,
  },
  analytics: {
    summary: (startDate?: string, endDate?: string) =>
      ['analytics', 'summary', startDate, endDate] as const,
    gexVolatility: (startDate: string, endDate: string) =>
      ['analytics', 'gex-volatility', startDate, endDate] as const,
  },
  health: ['health'] as const,
};

/**
 * Hook for current real-time GEX data.
 */
export function useCurrentGEX() {
  const { autoRefreshEnabled, refreshInterval } = useUIStore();

  return useQuery({
    queryKey: queryKeys.gex.current,
    queryFn: gexAPI.getCurrentGEX,
    refetchInterval: autoRefreshEnabled ? refreshInterval * 1000 : false,
    staleTime: 10000, // 10 seconds
  });
}

/**
 * Hook for GEX breakdown by strike.
 */
export function useGEXByStrikes(minStrike?: number, maxStrike?: number) {
  const { autoRefreshEnabled, refreshInterval } = useUIStore();

  return useQuery({
    queryKey: [...queryKeys.gex.strikes, minStrike, maxStrike],
    queryFn: () => gexAPI.getGEXByStrikes(minStrike, maxStrike),
    refetchInterval: autoRefreshEnabled ? refreshInterval * 1000 : false,
    staleTime: 10000,
  });
}

/**
 * Hook for current market regime.
 */
export function useCurrentRegime() {
  const { autoRefreshEnabled } = useUIStore();

  return useQuery({
    queryKey: queryKeys.gex.regime,
    queryFn: gexAPI.getCurrentRegime,
    refetchInterval: autoRefreshEnabled ? 10000 : false, // More frequent for regime
    staleTime: 5000,
  });
}

/**
 * Hook for historical GEX data.
 */
export function useHistoricalGEX(startDate: string, endDate: string, interval?: string) {
  return useQuery({
    queryKey: queryKeys.gex.historical(startDate, endDate),
    queryFn: () => gexAPI.getHistoricalGEX(startDate, endDate, interval),
    enabled: Boolean(startDate && endDate),
    staleTime: 60000, // 1 minute - historical data changes less
  });
}

/**
 * Hook for summary statistics.
 */
export function useSummaryStats(startDate?: string, endDate?: string) {
  return useQuery({
    queryKey: queryKeys.analytics.summary(startDate, endDate),
    queryFn: () => analyticsAPI.getSummaryStats(startDate, endDate),
    staleTime: 60000,
  });
}

/**
 * Hook for health check.
 */
export function useHealthCheck() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: healthAPI.check,
    refetchInterval: 30000, // Check every 30 seconds
    retry: 2,
  });
}
