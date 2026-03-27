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
    selectedProvider: 'yfinance' as 'yfinance' | 'tradier',
  },
}));

const websocketState = vi.hoisted(() => {
  const reconnect = vi.fn();
  const disconnect = vi.fn();
  const createStream = (): {
    data:
      | {
          net_gex: number;
          net_gex_billions: number;
          zero_gamma_level: number;
          spot_price: number;
          regime: 'short_gamma';
          timestamp: string;
          is_stale?: boolean;
          is_mock?: boolean;
          is_demo?: boolean;
        }
      | null;
    isConnected: boolean;
    connectionState: 'connected' | 'disconnected';
    error: string | null;
    retryCount: number;
    lastUpdateTime: number | null;
    reconnect: typeof reconnect;
    disconnect: typeof disconnect;
  } => ({
    data: {
      net_gex: -1450000000,
      net_gex_billions: -1.45,
      zero_gamma_level: 5915,
      spot_price: 5898,
      regime: 'short_gamma' as const,
      timestamp: '2026-03-23T10:30:00.000Z',
    },
    isConnected: true,
    connectionState: 'connected',
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
    getHistoricalGEX: vi.fn(),
  },
}));

vi.mock('@/stores/uiStore', () => ({
  useUIStore: () => storeState.state,
}));

vi.mock('./useWebSocket', () => ({
  useGEXStream: vi.fn(() => websocketState.stream),
}));

vi.mock('./useMarketStatus', () => ({
  useMarketStatus: vi.fn(() => ({
    data: {
      is_open: true,
      status: 'open',
      next_open: null,
      current_time_et: '2026-03-23T10:30:00-04:00',
    },
  })),
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

const persistedHistorical = {
  data: [
    {
      timestamp: '2026-03-23T10:30:00.000Z',
      net_gex: -1450000000,
      spot_price: 5898,
      total_call_gex: -2000000000,
      total_put_gex: 550000000,
      zero_gamma_level: 5915,
      gex_by_strike: {},
      dominant_strike: 5900,
      metrics: {},
    },
  ],
  start_date: '2026-03-23T00:00:00.000Z',
  end_date: '2026-03-23T23:59:59.999Z',
  count: 1,
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
    vi.mocked(gexAPI.getHistoricalGEX).mockResolvedValue(persistedHistorical);
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

  it('treats websocket snapshots flagged stale by the backend as stale data', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-03-23T10:30:00.000Z'));

    websocketState.stream = {
      ...websocketState.createStream(),
      data: {
        ...websocketState.createStream().data!,
        is_stale: true,
        timestamp: '2026-03-23T10:00:00.000Z',
      },
      lastUpdateTime: Date.parse('2026-03-23T10:30:00.000Z'),
    };

    vi.mocked(gexAPI.getCurrentGEX).mockResolvedValue(liveCurrentGex);
    vi.mocked(gexAPI.getCurrentRegime).mockResolvedValue(liveRegime);
    vi.mocked(gexAPI.getGEXByStrikes).mockResolvedValue(liveStrikes);

    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(createQueryClient()),
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.isStale).toBe(true);
    expect(result.current.lastUpdateTime).toBe(Date.parse('2026-03-23T10:00:00.000Z'));
  });

  it('prefers fresher REST timestamps when websocket data is stale and unusable', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-03-23T10:30:00.000Z'));

    websocketState.stream = {
      ...websocketState.createStream(),
      data: {
        ...websocketState.createStream().data!,
        is_stale: true,
        timestamp: '2026-03-23T10:00:00.000Z',
      },
      lastUpdateTime: Date.parse('2026-03-23T10:30:00.000Z'),
    };

    const freshRestSnapshot: GEXSnapshot = {
      ...liveCurrentGex,
      timestamp: '2026-03-23T10:29:55.000Z',
    };

    const queryClient = createQueryClient();
    queryClient.setQueryData(
      queryKeys.gex.current('live', 'yfinance'),
      freshRestSnapshot
    );

    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(queryClient),
    });

    expect(result.current.isRealtime).toBe(false);
    expect(result.current.gexData).toEqual(freshRestSnapshot);
    expect(result.current.lastUpdateTime).toBe(
      Date.parse('2026-03-23T10:29:55.000Z')
    );
    expect(result.current.isStale).toBe(false);
  });

  it('falls back to REST data when the websocket payload is mock data', async () => {
    websocketState.stream = {
      ...websocketState.createStream(),
      data: {
        ...websocketState.createStream().data!,
        is_mock: true,
      },
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
    expect(result.current.gexData).toEqual(liveCurrentGex);
    expect(result.current.regimeData).toEqual(liveRegime);
  });

  it('treats explicit demo websocket payloads as realtime even when they are marked mock', async () => {
    storeState.state = {
      ...storeState.state,
      demoModeEnabled: true,
    };
    websocketState.stream = {
      ...websocketState.createStream(),
      data: {
        ...websocketState.createStream().data!,
        is_mock: true,
        is_demo: true,
      },
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

    expect(result.current.isRealtime).toBe(true);
    expect(result.current.gexData).toMatchObject({
      net_gex: websocketState.stream.data?.net_gex,
      spot_price: websocketState.stream.data?.spot_price,
      zero_gamma_level: websocketState.stream.data?.zero_gamma_level,
    });
    expect(result.current.regimeData).toMatchObject({
      regime: websocketState.stream.data?.regime,
      net_gex: websocketState.stream.data?.net_gex,
    });
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
    vi.mocked(gexAPI.getHistoricalGEX).mockResolvedValue(persistedHistorical);
  });

  it('deduplicates near-identical timestamps and resets accumulation on demo-mode changes', async () => {
    const { result, rerender } = renderHook(
      () => useIntradayTimeSeries(liveCurrentGex, websocketState.stream.lastUpdateTime),
      {
        wrapper: createWrapper(createQueryClient()),
      }
    );

    await waitFor(() => {
      expect(result.current.dataPointCount).toBe(1);
    });

    expect(gexAPI.getHistoricalGEX).toHaveBeenCalledWith(
      '2026-03-23',
      '2026-03-23',
      '1m',
      { demo: false, provider: 'yfinance', symbol: 'SPX' }
    );

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

  it('preserves accumulated intraday points across hook remounts for the same provider session', async () => {
    const queryClient = createQueryClient();

    const { result, rerender, unmount } = renderHook(
      () => useIntradayTimeSeries(liveCurrentGex, websocketState.stream.lastUpdateTime),
      {
        wrapper: createWrapper(queryClient),
      }
    );

    await waitFor(() => {
      expect(result.current.dataPointCount).toBe(1);
    });

    websocketState.stream = {
      ...websocketState.stream,
      lastUpdateTime: websocketState.stream.lastUpdateTime! + 1500,
    };
    rerender();

    await waitFor(() => {
      expect(result.current.dataPointCount).toBe(2);
    });

    websocketState.stream = {
      ...websocketState.stream,
      lastUpdateTime: websocketState.stream.lastUpdateTime! + 1500,
    };
    rerender();

    await waitFor(() => {
      expect(result.current.dataPointCount).toBe(3);
    });

    unmount();

    const remounted = renderHook(
      () => useIntradayTimeSeries(liveCurrentGex, websocketState.stream.lastUpdateTime),
      {
        wrapper: createWrapper(queryClient),
      }
    );

    await waitFor(() => {
      expect(remounted.result.current.dataPointCount).toBe(3);
    });
  });

  it('does not write the previous provider intraday series into the new provider cache key', async () => {
    const queryClient = createQueryClient();

    const { result, rerender } = renderHook(
      () => useIntradayTimeSeries(liveCurrentGex, websocketState.stream.lastUpdateTime),
      {
        wrapper: createWrapper(queryClient),
      }
    );

    await waitFor(() => {
      expect(result.current.dataPointCount).toBe(1);
    });

    websocketState.stream = {
      ...websocketState.stream,
      lastUpdateTime: websocketState.stream.lastUpdateTime! + 1500,
    };
    rerender();

    await waitFor(() => {
      expect(result.current.dataPointCount).toBe(2);
    });

    websocketState.stream = {
      ...websocketState.stream,
      lastUpdateTime: websocketState.stream.lastUpdateTime! + 1500,
    };
    rerender();

    await waitFor(() => {
      expect(result.current.dataPointCount).toBe(3);
    });

    storeState.state = {
      ...storeState.state,
      selectedProvider: 'tradier',
    };
    rerender();

    const tradierKey = queryKeys.gex.intradaySeries('live', 'tradier', 'SPX', '2026-03-23');

    await waitFor(() => {
      expect(result.current.dataPointCount).toBe(1);
    });

    await waitFor(() => {
      expect(queryClient.getQueryData<Array<{ timestamp: number }>>(tradierKey)).toHaveLength(1);
    });
  });

  it('skips writing stale accumulated points during a provider key transition', async () => {
    const queryClient = createQueryClient();
    const setQueryDataSpy = vi.spyOn(queryClient, 'setQueryData');

    const { result, rerender } = renderHook(
      () => useIntradayTimeSeries(liveCurrentGex, websocketState.stream.lastUpdateTime),
      {
        wrapper: createWrapper(queryClient),
      }
    );

    await waitFor(() => {
      expect(result.current.dataPointCount).toBe(1);
    });

    websocketState.stream = {
      ...websocketState.stream,
      lastUpdateTime: websocketState.stream.lastUpdateTime! + 1500,
    };
    rerender();

    await waitFor(() => {
      expect(result.current.dataPointCount).toBe(2);
    });

    websocketState.stream = {
      ...websocketState.stream,
      lastUpdateTime: websocketState.stream.lastUpdateTime! + 1500,
    };
    rerender();

    await waitFor(() => {
      expect(result.current.dataPointCount).toBe(3);
    });

    setQueryDataSpy.mockClear();

    storeState.state = {
      ...storeState.state,
      selectedProvider: 'tradier',
    };
    rerender();

    const tradierKey = queryKeys.gex.intradaySeries('live', 'tradier', 'SPX', '2026-03-23');

    await waitFor(() => {
      expect(result.current.dataPointCount).toBe(1);
    });

    const staleTradierWrites = setQueryDataSpy.mock.calls.filter(
      ([key, value]) =>
        JSON.stringify(key) === JSON.stringify(tradierKey) &&
        Array.isArray(value) &&
        value.length > 1
    );

    expect(staleTradierWrites).toHaveLength(0);
  });
});
