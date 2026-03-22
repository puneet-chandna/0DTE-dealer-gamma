/**
 * React Query Hooks Tests
 *
 * Tests for useGEXData hooks with mocked API and React Query wrapper.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import type { ReactNode } from 'react';

import {
  useCurrentGEX,
  useGEXByStrikes,
  useCurrentRegime,
  useHistoricalGEX,
  useSummaryStats,
  useHealthCheck,
  queryKeys,
} from '@/hooks/useGEXData';
import type {
  GEXSnapshot,
  GEXByStrike,
  RegimeData,
  GEXHistorical,
  SummaryStatistics,
  HealthStatus,
  RegimeType,
} from '@/types';

// Mock the API module
vi.mock('@/lib/api', () => ({
  gexAPI: {
    getCurrentGEX: vi.fn(),
    getGEXByStrikes: vi.fn(),
    getCurrentRegime: vi.fn(),
    getHistoricalGEX: vi.fn(),
  },
  analyticsAPI: {
    getSummaryStats: vi.fn(),
  },
  healthAPI: {
    check: vi.fn(),
  },
}));

// Mock the UI store
vi.mock('@/stores/uiStore', () => ({
  useUIStore: () => ({
    autoRefreshEnabled: true,
    refreshInterval: 5,
    demoModeEnabled: true,
  }),
}));

import { gexAPI, analyticsAPI, healthAPI } from '@/lib/api';

// Create a wrapper with QueryClientProvider
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  return function Wrapper({ children }: { children: ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

describe('queryKeys', () => {
  it('should have correct structure for gex keys', () => {
    expect(queryKeys.gex.current('demo')).toEqual(['gex', 'demo', 'current']);
    expect(queryKeys.gex.strikes('demo')).toEqual(['gex', 'demo', 'strikes']);
    expect(queryKeys.gex.regime('demo')).toEqual(['gex', 'demo', 'regime']);
  });

  it('should generate historical keys with dates', () => {
    const key = queryKeys.gex.historical('demo', '2025-01-01', '2025-01-31');
    expect(key).toEqual(['gex', 'demo', 'historical', '2025-01-01', '2025-01-31']);
  });

  it('should generate analytics summary keys', () => {
    const key = queryKeys.analytics.summary('demo', '2025-01-01', '2025-01-31');
    expect(key).toEqual(['analytics', 'demo', 'summary', '2025-01-01', '2025-01-31']);
  });
});

describe('useCurrentGEX', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it('should fetch current GEX data', async () => {
    const mockData: GEXSnapshot = {
      net_gex: -1500000000,
      spot_price: 5900,
      zero_gamma_level: 5920,
      total_call_gex: -2000000000,
      total_put_gex: 500000000,
      timestamp: '2025-01-15T10:30:00-05:00',
      gex_by_strike: { 5900: -500000000 },
      dominant_strike: 5900,
      metrics: {},
    };

    vi.mocked(gexAPI.getCurrentGEX).mockResolvedValue(mockData);

    const { result } = renderHook(() => useCurrentGEX(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockData);
    expect(gexAPI.getCurrentGEX).toHaveBeenCalledWith({ demo: true });
  });

  it('should handle API errors', async () => {
    vi.mocked(gexAPI.getCurrentGEX).mockRejectedValue(new Error('API Error'));

    const { result } = renderHook(() => useCurrentGEX(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toBeDefined();
  });

  it('should start with loading state', () => {
    vi.mocked(gexAPI.getCurrentGEX).mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );

    const { result } = renderHook(() => useCurrentGEX(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });
});

describe('useGEXByStrikes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch strikes data without filters', async () => {
    const mockData: GEXByStrike = {
      strikes: [5850, 5900, 5950],
      gex_values: [-100000000, -200000000, -150000000],
      spot_price: 5900,
      zero_gamma_level: 5920,
    };

    vi.mocked(gexAPI.getGEXByStrikes).mockResolvedValue(mockData);

    const { result } = renderHook(() => useGEXByStrikes(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockData);
    expect(gexAPI.getGEXByStrikes).toHaveBeenCalledWith(undefined, undefined, { demo: true });
  });

  it('should fetch strikes data with filters', async () => {
    const mockData: GEXByStrike = {
      strikes: [5900],
      gex_values: [-200000000],
      spot_price: 5900,
      zero_gamma_level: 5920,
    };

    vi.mocked(gexAPI.getGEXByStrikes).mockResolvedValue(mockData);

    const { result } = renderHook(() => useGEXByStrikes(5850, 5950), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(gexAPI.getGEXByStrikes).toHaveBeenCalledWith(5850, 5950, { demo: true });
  });
});

describe('useCurrentRegime', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch regime data', async () => {
    const mockRegime: RegimeData = {
      regime: 'short_gamma' as RegimeType,
      net_gex: -1500000000,
      net_gex_billions: -1.5,
      description: 'Market in short gamma - expect higher volatility',
      color: 'red',
      timestamp: '2025-01-15T10:30:00-05:00',
    };

    vi.mocked(gexAPI.getCurrentRegime).mockResolvedValue(mockRegime);

    const { result } = renderHook(() => useCurrentRegime(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.regime).toBe('short_gamma');
    expect(result.current.data?.color).toBe('red');
    expect(gexAPI.getCurrentRegime).toHaveBeenCalledWith({ demo: true });
  });

  it('should return long_gamma regime', async () => {
    const mockRegime: RegimeData = {
      regime: 'long_gamma' as RegimeType,
      net_gex: 2000000000,
      net_gex_billions: 2.0,
      description: 'Market in long gamma - expect mean reversion',
      color: 'green',
      timestamp: '2025-01-15T10:30:00-05:00',
    };

    vi.mocked(gexAPI.getCurrentRegime).mockResolvedValue(mockRegime);

    const { result } = renderHook(() => useCurrentRegime(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.regime).toBe('long_gamma');
    expect(result.current.data?.color).toBe('green');
  });

  it('should return neutral regime', async () => {
    const mockRegime: RegimeData = {
      regime: 'neutral' as RegimeType,
      net_gex: 500000000,
      net_gex_billions: 0.5,
      description: 'Market in neutral gamma',
      color: 'yellow',
      timestamp: '2025-01-15T10:30:00-05:00',
    };

    vi.mocked(gexAPI.getCurrentRegime).mockResolvedValue(mockRegime);

    const { result } = renderHook(() => useCurrentRegime(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.regime).toBe('neutral');
    expect(result.current.data?.color).toBe('yellow');
  });
});

describe('useHistoricalGEX', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch historical data with date range', async () => {
    const mockHistorical: GEXHistorical = {
      data: [
        {
          timestamp: '2025-01-14T10:00:00-05:00',
          net_gex: -1000000000,
          spot_price: 5900,
          total_call_gex: -1500000000,
          total_put_gex: 500000000,
          zero_gamma_level: 5920,
          gex_by_strike: {},
          dominant_strike: 5900,
          metrics: {},
        },
        {
          timestamp: '2025-01-14T11:00:00-05:00',
          net_gex: -1200000000,
          spot_price: 5890,
          total_call_gex: -1700000000,
          total_put_gex: 500000000,
          zero_gamma_level: 5910,
          gex_by_strike: {},
          dominant_strike: 5890,
          metrics: {},
        },
      ],
      start_date: '2025-01-14',
      end_date: '2025-01-14',
      count: 2,
    };

    vi.mocked(gexAPI.getHistoricalGEX).mockResolvedValue(mockHistorical);

    const { result } = renderHook(
      () => useHistoricalGEX('2025-01-14', '2025-01-14', '1h'),
      {
        wrapper: createWrapper(),
      }
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.data.length).toBe(2);
    expect(gexAPI.getHistoricalGEX).toHaveBeenCalledWith(
      '2025-01-14',
      '2025-01-14',
      '1h',
      { demo: true }
    );
  });

  it('should not fetch when dates are missing', () => {
    const { result } = renderHook(() => useHistoricalGEX('', ''), {
      wrapper: createWrapper(),
    });

    // Query should be disabled
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isFetching).toBe(false);
  });
});

describe('useSummaryStats', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch summary statistics', async () => {
    const mockStats: SummaryStatistics = {
      mean_gex: -800000000,
      std_gex: 500000000,
      max_gex: 2000000000,
      min_gex: -2500000000,
      median_gex: -700000000,
      pct_negative_days: 0.65,
      sample_size: 252,
    };

    vi.mocked(analyticsAPI.getSummaryStats).mockResolvedValue(mockStats);

    const { result } = renderHook(() => useSummaryStats(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.mean_gex).toBe(-800000000);
  });

  it('should accept optional date parameters', async () => {
    const mockStats: SummaryStatistics = {
      mean_gex: 0,
      std_gex: 0,
      max_gex: 0,
      min_gex: 0,
      median_gex: 0,
      pct_negative_days: 0,
      sample_size: 0,
    };
    vi.mocked(analyticsAPI.getSummaryStats).mockResolvedValue(mockStats);

    renderHook(() => useSummaryStats('2025-01-01', '2025-01-31'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(analyticsAPI.getSummaryStats).toHaveBeenCalledWith(
        '2025-01-01',
        '2025-01-31',
        { demo: true }
      );
    });
  });
});

describe('useHealthCheck', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should check health status', async () => {
    const mockHealth: HealthStatus = {
      status: 'healthy',
    };

    vi.mocked(healthAPI.check).mockResolvedValue(mockHealth);

    const { result } = renderHook(() => useHealthCheck(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.status).toBe('healthy');
  });

  it('should handle unhealthy status', async () => {
    const mockHealth: HealthStatus = {
      status: 'unhealthy',
    };

    vi.mocked(healthAPI.check).mockResolvedValue(mockHealth);

    const { result } = renderHook(() => useHealthCheck(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.status).toBe('unhealthy');
  });
});
