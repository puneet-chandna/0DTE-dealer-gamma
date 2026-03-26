import React, { type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useIVSurface, useTechnicalIndicators } from './useAnalyticsData';

const storeState = vi.hoisted(() => ({
  state: {
    demoModeEnabled: false,
    selectedProvider: 'yfinance' as 'yfinance' | 'tradier',
  },
}));

const useQuerySpy = vi.hoisted(() =>
  vi.fn(() => ({ data: undefined, isLoading: false }))
);

vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query');
  return {
    ...actual,
    useQuery: (options: unknown) => useQuerySpy(options),
  };
});

vi.mock('@/stores/uiStore', () => ({
  useUIStore: () => storeState.state,
}));

vi.mock('@/lib/api', () => ({
  dataAPI: {
    getRiskFreeRate: vi.fn(),
  },
  analyticsAPI: {
    getIVSurface: vi.fn(),
    getTechnicalIndicators: vi.fn(),
    runVectorbtBacktest: vi.fn(),
  },
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return function Wrapper({ children }: { children: ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

describe('useAnalyticsData demo polling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    storeState.state = {
      demoModeEnabled: false,
      selectedProvider: 'yfinance',
    };
  });

  it('adds a 5-second refetch interval for IV surface in demo mode only', () => {
    storeState.state = {
      ...storeState.state,
      demoModeEnabled: true,
    };

    renderHook(() => useIVSurface('SPY'), {
      wrapper: createWrapper(),
    });

    expect(useQuerySpy).toHaveBeenCalledWith(
      expect.objectContaining({
        refetchInterval: 5000,
      })
    );
  });

  it('adds a 5-second refetch interval for technical indicators in demo mode only', () => {
    storeState.state = {
      ...storeState.state,
      demoModeEnabled: true,
    };

    renderHook(() => useTechnicalIndicators('SPY', '1mo', '1d', 'ATR,RSI,BBANDS'), {
      wrapper: createWrapper(),
    });

    expect(useQuerySpy).toHaveBeenCalledWith(
      expect.objectContaining({
        refetchInterval: 5000,
      })
    );
  });

  it('keeps live-mode analytics queries on the existing non-polling behavior', () => {
    renderHook(() => useIVSurface('SPY'), {
      wrapper: createWrapper(),
    });

    expect(useQuerySpy).toHaveBeenCalledWith(
      expect.objectContaining({
        refetchInterval: false,
      })
    );
  });
});
