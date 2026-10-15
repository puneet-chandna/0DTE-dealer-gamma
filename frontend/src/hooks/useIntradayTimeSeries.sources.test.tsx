import React, { type ReactNode } from 'react';
import { cleanup, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useIntradayTimeSeries } from './useDashboardData';
import { queryKeys } from './useGEXData';

const source = vi.hoisted(() => ({ provider: 'yfinance', demo: false, day: '2026-10-14' }));
vi.mock('@/stores/uiStore', () => ({ useUIStore: () => ({ selectedProvider: source.provider, demoModeEnabled: source.demo }) }));
vi.mock('./useMarketStatus', () => ({ useMarketStatus: () => ({ data: {
  is_open: true, status: 'open', next_open: null, current_time_et: `${source.day}T10:00:00-04:00`,
} }) }));
vi.mock('./useGEXData', async (importOriginal) => ({
  ...await importOriginal<typeof import('./useGEXData')>(),
  useHistoricalGEX: () => ({ data: undefined }),
}));

const first = { timestamp: 1000, netGex: -100, spotPrice: 500 };
const second = { timestamp: 1000, netGex: 200, spotPrice: 600 };

describe('intraday source isolation', () => {
  beforeEach(() => { source.provider = 'yfinance'; source.demo = false; source.day = '2026-10-14'; });
  afterEach(cleanup);

  it.each(['provider', 'mode', 'day'] as const)('replaces cached points on a %s switch without a stale first render', (change) => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
    const origin = queryKeys.gex.intradaySeries('live', 'yfinance', 'SPX', '2026-10-14');
    const target = queryKeys.gex.intradaySeries(
      change === 'mode' ? 'demo' : 'live', change === 'provider' ? 'tradier' : 'yfinance', 'SPX',
      change === 'day' ? '2026-10-15' : '2026-10-14',
    );
    client.setQueryData(origin, [first]);
    client.setQueryData(target, [second]);
    const renders: typeof first[][] = [];
    function Wrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    }
    const { result, rerender } = renderHook(() => {
      const series = useIntradayTimeSeries(null, null);
      renders.push(series.timeSeries);
      return series;
    }, { wrapper: Wrapper });
    expect(result.current.timeSeries).toEqual([first]);
    const renderCount = renders.length;

    if (change === 'provider') source.provider = 'tradier';
    if (change === 'mode') source.demo = true;
    if (change === 'day') source.day = '2026-10-15';
    rerender();
    expect(renders[renderCount]).not.toContainEqual(first);
    expect(result.current.timeSeries).toEqual([second]);
    expect(client.getQueryData(target)).toEqual([second]);
    expect(client.getQueryData(origin)).toEqual([first]);
  });
});
