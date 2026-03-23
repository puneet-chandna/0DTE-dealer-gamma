import React, { type ReactNode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useDashboardData, useIntradayTimeSeries } from './useDashboardData';
import { queryKeys } from './useGEXData';
import { gexAPI } from '@/lib/api';
import type { GEXByStrike, GEXSnapshot, RegimeData } from '@/types';

const storeState = vi.hoisted(() => ({
  state: {
    autoRefreshEnabled: false,
    refreshInterval: 5,
    demoModeEnabled: false,
    selectedProvider: 'yfinance' as const,
  },
}));

const websocketState = vi.hoisted(() => {
  const reconnect = vi.fn();
  const disconnect = vi.fn();
  const createStream = () => ({
    data: {
      net_gex: -1450000000,
      net_gex_billions: -1.45,
      zero_gamma_level: 5915,
      spot_price: 5898,
      regime: 'short_gamma' as const,
      timestamp: '2026-03-23T10:30:00.000Z',
    },
    isConnected: true,
    connectionState: 'connected' as const,
    error: null,
    retryCount: 0,
    lastUpdateTime: Date.parse('2026-03-23T10:30:00.000Z'),
    reconnect,
    disconnect,
  });

  return {
    reconnect,
    disconnect,
    createStream,
    stream: createStream(),
  };
});

vi.mock('@/lib/api', () => ({
  gexAPI: {
    getCurrentGEX: vi.fn(),
    getGEXByStrikes: vi.fn(),
    getCurrentRegime: vi.fn(),
  },
}));

vi.mock('@/stores/uiStore', () => ({
  useUIStore: () => storeState.state,
}));

vi.mock('./useWebSocket', () => ({
  useGEXStream: vi.fn(() => websocketState.stream),
}));

const liveCurrentGex: GEXSnapshot = {
  net_gex: -1500000000,
  spot_price: 5900,
  zero_gamma_level: 5920,
  total_call_gex: -2000000000,
  total_put_gex: 500000000,
  timestamp: '2026-03-23T10:29:55.000Z',
  gex_by_strike: { 5900: -500000000 },
  dominant_strike: 5900,
  metrics: {},
};

const liveRegime: RegimeData = {
  regime: 'short_gamma',
  net_gex: -1500000000,
  net_gex_billions: -1.5,
  description: 'Market in short gamma',
  color: 'red',
  timestamp: '2026-03-23T10:29:55.000Z',
};

const liveStrikes: GEXByStrike = {
  strikes: [5850, 5900, 5950],
  gex_values: [-120000000, -200000000, -80000000],
  spot_price: 5900,
  zero_gamma_level: 5920,
};

function createPendingPromise<T>() {
  return new Promise<T>(() => {});
}

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: Infinity,
        refetchOnWindowFocus: false,
      },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    );
  };
}

describe('useDashboardData', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    storeState.state = {
      autoRefreshEnabled: false,
      refreshInterval: 5,
      demoModeEnabled: false,
      selectedProvider: 'yfinance',
    };
    websocketState.stream = websocketState.createStream();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('writes websocket snapshots into the cache once per affected query', async () => {
    vi.mocked(gexAPI.getCurrentGEX).mockResolvedValue(liveCurrentGex);
    vi.mocked(gexAPI.getCurrentRegime).mockResolvedValue(liveRegime);
    vi.mocked(gexAPI.getGEXByStrikes).mockResolvedValue(liveStrikes);

    const queryClient = createQueryClient();
    const setQueryDataSpy = vi.spyOn(queryClient, 'setQueryData');

    renderHook(() => useDashboardData(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => {
      expect(gexAPI.getCurrentGEX).toHaveBeenCalledTimes(1);
      expect(gexAPI.getCurrentRegime).toHaveBeenCalledTimes(1);
      expect(gexAPI.getGEXByStrikes).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(setQueryDataSpy).toHaveBeenCalledTimes(2);
    });

    await new Promise((resolve) => setTimeout(resolve, 25));

    expect(setQueryDataSpy).toHaveBeenCalledTimes(2);
  });

  it('falls back to REST data when the websocket is disconnected', async () => {
    websocketState.stream = {
      ...websocketState.createStream(),
      data: null,
      isConnected: false,
      connectionState: 'disconnected',
      lastUpdateTime: null,
    };

    vi.mocked(gexAPI.getCurrentGEX).mockResolvedValue(liveCurrentGex);
    vi.mocked(gexAPI.getCurrentRegime).mockResolvedValue(liveRegime);
    vi.mocked(gexAPI.getGEXByStrikes).mockResolvedValue(liveStrikes);

    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(createQueryClient()),
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.isRealtime).toBe(false);
    expect(result.current.connectionState).toBe('disconnected');
    expect(result.current.gexData).toEqual(liveCurrentGex);
    expect(result.current.regimeData).toEqual(liveRegime);
    expect(result.current.strikesData).toEqual(liveStrikes);
    expect(result.current.error).toBeNull();
  });

  it('marks realtime data stale after the freshness threshold elapses', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-03-23T10:30:00.000Z'));

    vi.mocked(gexAPI.getCurrentGEX).mockResolvedValue(liveCurrentGex);
    vi.mocked(gexAPI.getCurrentRegime).mockResolvedValue(liveRegime);
    vi.mocked(gexAPI.getGEXByStrikes).mockResolvedValue(liveStrikes);

    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(createQueryClient()),
    });

    expect(result.current.isStale).toBe(false);

    await act(async () => {
      vi.advanceTimersByTime(65000);
    });

    expect(result.current.isStale).toBe(true);
  });

  it('updates only the selected provider cache when websocket data arrives', async () => {
    storeState.state = {
      ...storeState.state,
      selectedProvider: 'tradier',
    };

    vi.mocked(gexAPI.getCurrentGEX).mockImplementation(() => createPendingPromise());
    vi.mocked(gexAPI.getCurrentRegime).mockImplementation(() => createPendingPromise());
    vi.mocked(gexAPI.getGEXByStrikes).mockImplementation(() => createPendingPromise());

    const queryClient = createQueryClient();
    queryClient.setQueryData(queryKeys.gex.current('live', 'yfinance'), liveCurrentGex);
    queryClient.setQueryData(queryKeys.gex.regime('live', 'yfinance'), liveRegime);

    renderHook(() => useDashboardData(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => {
      expect(
        queryClient.getQueryData<GEXSnapshot>(queryKeys.gex.current('live', 'tradier'))
      ).toMatchObject({
        net_gex: websocketState.stream.data?.net_gex,
        spot_price: websocketState.stream.data?.spot_price,
        zero_gamma_level: websocketState.stream.data?.zero_gamma_level,
      });
    });

    expect(
      queryClient.getQueryData<GEXSnapshot>(queryKeys.gex.current('live', 'yfinance'))
    ).toEqual(liveCurrentGex);
    expect(
      queryClient.getQueryData<RegimeData>(queryKeys.gex.regime('live', 'yfinance'))
    ).toEqual(liveRegime);
  });
});

describe('useIntradayTimeSeries', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    storeState.state = {
      autoRefreshEnabled: false,
      refreshInterval: 5,
      demoModeEnabled: false,
      selectedProvider: 'yfinance',
    };
    websocketState.stream = websocketState.createStream();
    vi.mocked(gexAPI.getCurrentGEX).mockImplementation(() => createPendingPromise());
    vi.mocked(gexAPI.getCurrentRegime).mockImplementation(() => createPendingPromise());
    vi.mocked(gexAPI.getGEXByStrikes).mockImplementation(() => createPendingPromise());
  });

  it('deduplicates near-identical timestamps and resets accumulation on demo-mode changes', async () => {
    const { result, rerender } = renderHook(() => useIntradayTimeSeries(), {
      wrapper: createWrapper(createQueryClient()),
    });

    await waitFor(() => {
      expect(result.current.dataPointCount).toBe(1);
    });

    websocketState.stream = {
      ...websocketState.stream,
      data: {
        ...websocketState.stream.data!,
        net_gex: -1400000000,
      },
      lastUpdateTime: websocketState.stream.lastUpdateTime! + 500,
    };

    rerender();

    expect(result.current.dataPointCount).toBe(1);

    websocketState.stream = {
      ...websocketState.stream,
      data: {
        ...websocketState.stream.data!,
        net_gex: -1300000000,
      },
      lastUpdateTime: websocketState.stream.lastUpdateTime! + 1500,
    };

    rerender();

    await waitFor(() => {
      expect(result.current.dataPointCount).toBe(2);
    });

    storeState.state = {
      ...storeState.state,
      demoModeEnabled: true,
    };

    rerender();

    await waitFor(() => {
      expect(result.current.dataPointCount).toBe(1);
    });
  });
});
