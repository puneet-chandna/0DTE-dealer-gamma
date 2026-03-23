/**
 * React Query hooks for the new analytics/data endpoints.
 */

import { useQuery } from '@tanstack/react-query';
import { dataAPI, analyticsAPI } from '@/lib/api';
import { getAppDataMode } from '@/lib/appMode';
import { useUIStore } from '@/stores/uiStore';
import type {
  RiskFreeRateInfo,
  IVSurfaceResponse,
  TechnicalIndicatorResponse,
  VectorBTBacktestResult,
} from '@/types';

/**
 * Query key factory for analytics.
 */
export const analyticsQueryKeys = {
  riskFreeRate: ['risk-free-rate'] as const,
  ivSurface: (mode: 'live' | 'demo', provider: string, symbol: string) =>
    ['iv-surface', mode, provider, symbol] as const,
  technicalIndicators: (
    mode: 'live' | 'demo',
    provider: string,
    symbol: string,
    period: string,
    interval: string,
    indicators: string
  ) => ['technical-indicators', mode, provider, symbol, period, interval, indicators] as const,
  vectorbtBacktest: (mode: 'live' | 'demo', provider: string, params: Record<string, unknown>) =>
    ['vectorbt-backtest', mode, provider, params] as const,
};

/**
 * Fetch the current risk-free rate from FRED.
 * Auto-refreshes every 5 minutes.
 */
export function useRiskFreeRate() {
  return useQuery<RiskFreeRateInfo>({
    queryKey: analyticsQueryKeys.riskFreeRate,
    queryFn: dataAPI.getRiskFreeRate,
    refetchInterval: 5 * 60 * 1000, // 5 minutes
    staleTime: 4 * 60 * 1000,
    retry: 2,
  });
}

/**
 * Fetch IV surface and skew data.
 */
export function useIVSurface(symbol: string = 'SPY', enabled: boolean = true) {
  const { demoModeEnabled, selectedProvider } = useUIStore();
  const mode = getAppDataMode(demoModeEnabled);

  return useQuery<IVSurfaceResponse>({
    queryKey: analyticsQueryKeys.ivSurface(mode, selectedProvider, symbol),
    queryFn: () =>
      analyticsAPI.getIVSurface(symbol, {
        demo: demoModeEnabled,
        provider: selectedProvider,
      }),
    enabled,
    staleTime: 60 * 1000, // 1 minute
    retry: 1,
  });
}

/**
 * Fetch technical indicators.
 */
export function useTechnicalIndicators(
  symbol: string = 'SPY',
  period: string = '1mo',
  interval: string = '1d',
  indicators: string = 'ATR,RSI,BBANDS',
  enabled: boolean = true
) {
  const { demoModeEnabled, selectedProvider } = useUIStore();
  const mode = getAppDataMode(demoModeEnabled);

  return useQuery<TechnicalIndicatorResponse>({
    queryKey: analyticsQueryKeys.technicalIndicators(
      mode,
      selectedProvider,
      symbol,
      period,
      interval,
      indicators
    ),
    queryFn: () =>
      analyticsAPI.getTechnicalIndicators(symbol, period, interval, indicators, {
        demo: demoModeEnabled,
        provider: selectedProvider,
      }),
    enabled,
    staleTime: 60 * 1000,
    retry: 1,
  });
}

/**
 * Run a vectorbt backtest on demand.
 * Only fires when params are provided and `enabled` is true.
 */
export function useVectorbtBacktest(
  params: {
    start_date: string;
    end_date: string;
    entry_threshold?: number;
    exit_threshold?: number;
    initial_cash?: number;
  } | null,
  enabled: boolean = false
) {
  const { demoModeEnabled, selectedProvider } = useUIStore();
  const mode = getAppDataMode(demoModeEnabled);
  const requestParams = params ? { symbol: 'SPX', ...params } : null;

  return useQuery<VectorBTBacktestResult>({
    queryKey: analyticsQueryKeys.vectorbtBacktest(mode, selectedProvider, requestParams ?? {}),
    queryFn: () =>
      analyticsAPI.runVectorbtBacktest(requestParams!, {
        demo: demoModeEnabled,
        provider: selectedProvider,
      }),
    enabled: enabled && requestParams !== null,
    staleTime: Infinity, // Don't auto-refetch backtests
    retry: 0,
  });
}
