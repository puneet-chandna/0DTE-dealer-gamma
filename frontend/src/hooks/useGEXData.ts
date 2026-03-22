/**
 * 0DTE GEX Frontend - React Query Hooks for GEX Data
 *
 * RULE: Use React Query for SERVER STATE (API data).
 * Use Zustand for CLIENT STATE (UI settings).
 */

import { useQuery } from '@tanstack/react-query';
import { gexAPI, analyticsAPI, healthAPI } from '@/lib/api';
import { getAppDataMode } from '@/lib/appMode';
import { useUIStore } from '@/stores/uiStore';

/**
 * Query keys for cache management.
 */
export const queryKeys = {
  gex: {
    current: (mode: 'live' | 'demo') => ['gex', mode, 'current'] as const,
    strikes: (mode: 'live' | 'demo') => ['gex', mode, 'strikes'] as const,
    regime: (mode: 'live' | 'demo') => ['gex', mode, 'regime'] as const,
    historical: (mode: 'live' | 'demo', startDate: string, endDate: string) =>
      ['gex', mode, 'historical', startDate, endDate] as const,
  },
  analytics: {
    summary: (mode: 'live' | 'demo', startDate?: string, endDate?: string) =>
      ['analytics', mode, 'summary', startDate, endDate] as const,
    gexVolatility: (startDate: string, endDate: string) =>
      ['analytics', 'gex-volatility', startDate, endDate] as const,
  },
  health: ['health'] as const,
  marketStatus: ['market-status'] as const,
};

/**
 * Hook for current real-time GEX data.
 */
export function useCurrentGEX() {
  const { autoRefreshEnabled, refreshInterval, demoModeEnabled } = useUIStore();
  const mode = getAppDataMode(demoModeEnabled);

  return useQuery({
    queryKey: queryKeys.gex.current(mode),
    queryFn: () => gexAPI.getCurrentGEX({ demo: demoModeEnabled }),
    refetchInterval: autoRefreshEnabled ? refreshInterval * 1000 : false,
    staleTime: 10000, // 10 seconds
  });
}

/**
 * Hook for GEX breakdown by strike.
 */
export function useGEXByStrikes(minStrike?: number, maxStrike?: number) {
  const { autoRefreshEnabled, refreshInterval, demoModeEnabled } = useUIStore();
  const mode = getAppDataMode(demoModeEnabled);

  return useQuery({
    queryKey: [...queryKeys.gex.strikes(mode), minStrike, maxStrike],
    queryFn: () => gexAPI.getGEXByStrikes(minStrike, maxStrike, { demo: demoModeEnabled }),
    refetchInterval: autoRefreshEnabled ? refreshInterval * 1000 : false,
    staleTime: 10000,
  });
}

/**
 * Hook for current market regime.
 */
export function useCurrentRegime() {
  const { autoRefreshEnabled, demoModeEnabled } = useUIStore();
  const mode = getAppDataMode(demoModeEnabled);

  return useQuery({
    queryKey: queryKeys.gex.regime(mode),
    queryFn: () => gexAPI.getCurrentRegime({ demo: demoModeEnabled }),
    refetchInterval: autoRefreshEnabled ? 10000 : false, // More frequent for regime
    staleTime: 5000,
  });
}

/**
 * Hook for historical GEX data.
 */
export function useHistoricalGEX(startDate: string, endDate: string, interval?: string) {
  const { demoModeEnabled } = useUIStore();
  const mode = getAppDataMode(demoModeEnabled);

  return useQuery({
    queryKey: queryKeys.gex.historical(mode, startDate, endDate),
    queryFn: () => gexAPI.getHistoricalGEX(startDate, endDate, interval, { demo: demoModeEnabled }),
    enabled: Boolean(startDate && endDate),
    staleTime: 60000, // 1 minute - historical data changes less
  });
}

/**
 * Hook for summary statistics.
 */
export function useSummaryStats(startDate?: string, endDate?: string) {
  const { demoModeEnabled } = useUIStore();
  const mode = getAppDataMode(demoModeEnabled);

  return useQuery({
    queryKey: queryKeys.analytics.summary(mode, startDate, endDate),
    queryFn: () => analyticsAPI.getSummaryStats(startDate, endDate, { demo: demoModeEnabled }),
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
