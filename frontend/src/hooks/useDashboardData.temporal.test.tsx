import React, { type ReactNode } from 'react';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DashboardDataProvider, useDashboardData, useIntradayTimeSeries } from './useDashboardData';
import { queryKeys } from './useGEXData';
import type { useGEXStream } from './useWebSocket';
import { gexAPI } from '@/lib/api';
import type { GEXSnapshot, RegimeData } from '@/types';

const state = vi.hoisted(() => ({
  store: { autoRefreshEnabled: false, refreshInterval: 5, demoModeEnabled: false, selectedProvider: 'yfinance' },
  day: '2026-10-14',
  stream: null as ReturnType<typeof useGEXStream> | null,
}));
vi.mock('@/stores/uiStore', () => ({ useUIStore: () => state.store }));
vi.mock('./useWebSocket', () => ({ useGEXStream: () => state.stream }));
vi.mock('./useMarketStatus', () => ({ useMarketStatus: () => ({ data: {
  is_open: true, status: 'open', next_open: null, current_time_et: `${state.day}T10:00:00-04:00`,
} }) }));
vi.mock('@/lib/api', () => ({ gexAPI: {
  getCurrentGEX: vi.fn(), getGEXByStrikes: vi.fn(), getCurrentRegime: vi.fn(), getHistoricalGEX: vi.fn(),
} }));

const clients: QueryClient[] = [];
const currentKey = queryKeys.gex.current('live', 'yfinance');
const regimeKey = queryKeys.gex.regime('live', 'yfinance');
function snapshot(timestamp: string, netGex: number): GEXSnapshot {
  return {
    timestamp, net_gex: netGex, spot_price: 5900, zero_gamma_level: 5900,
    total_call_gex: 100, total_put_gex: netGex - 100, gex_by_strike: { 5900: netGex },
    dominant_strike: 5900, metrics: {}, provider: 'yfinance',
  };
}
function regime(timestamp: string, netGex: number): RegimeData {
  return { timestamp, net_gex: netGex, net_gex_billions: netGex / 1e9, regime: 'short_gamma', description: '', color: 'red' };
}
function connected(timestamp: string, netGex: number): ReturnType<typeof useGEXStream> {
  return {
    data: { ...snapshot(timestamp, netGex), ...regime(timestamp, netGex), is_stale: false, is_mock: false, is_demo: state.store.demoModeEnabled },
    isConnected: true, connectionState: 'connected', lastUpdateTime: Date.now(),
    error: null, retryCount: 0, reconnect: vi.fn(), disconnect: vi.fn(), sendMessage: vi.fn(),
  };
}
function wrapper(dashboard = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity, refetchOnWindowFocus: false } } });
  clients.push(client);
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{dashboard ? <DashboardDataProvider>{children}</DashboardDataProvider> : children}</QueryClientProvider>;
  }
  return { client, wrapper: Wrapper };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  return { promise: new Promise<T>((done) => { resolve = done; }), resolve: (value: T) => resolve(value) };
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-14T14:00:20Z'));
  vi.clearAllMocks();
  state.day = '2026-10-14';
  state.store.demoModeEnabled = false;
  state.stream = { ...connected('2026-10-14T14:00:00Z', -100), data: null, isConnected: false, connectionState: 'disconnected' };
  vi.mocked(gexAPI.getCurrentGEX).mockResolvedValue(snapshot('2026-10-14T14:00:10Z', 200));
  vi.mocked(gexAPI.getCurrentRegime).mockResolvedValue(regime('2026-10-14T14:00:10Z', 200));
  vi.mocked(gexAPI.getGEXByStrikes).mockResolvedValue({ strikes: [5900], gex_values: [200], spot_price: 5900, zero_gamma_level: 5900 });
  vi.mocked(gexAPI.getHistoricalGEX).mockResolvedValue({ data: [], count: 0, start_date: state.day, end_date: state.day });
});
afterEach(() => {
  cleanup();
  clients.splice(0).forEach((client) => client.clear());
  vi.useRealTimers();
});

describe('live snapshot ordering', () => {
  it.each(['2026-10-14T14:00:05Z', 'invalid', ''])('retains newer REST data when a WS snapshot has timestamp %j', async (timestamp) => {
    const { client, wrapper: Wrapper } = wrapper();
    const { result, rerender } = renderHook(() => useDashboardData(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.gexData?.net_gex).toBe(200));

    state.stream = connected(timestamp, -100);
    rerender();

    expect(result.current.gexData?.net_gex).toBe(200);
    expect(result.current.regimeData?.net_gex).toBe(200);
    expect(result.current.isRealtime).toBe(false);
    expect(result.current.lastUpdateTime).toBe(Date.parse('2026-10-14T14:00:10Z'));
    expect(client.getQueryData<GEXSnapshot>(currentKey)?.net_gex).toBe(200);
    expect(client.getQueryData<RegimeData>(regimeKey)?.net_gex).toBe(200);
  });

  it.each(['2026-10-14T14:00:05Z', 'invalid'])('retains WS data after an older pending HTTP completion with timestamp %j', async (timestamp) => {
    const pendingGex = deferred<GEXSnapshot>();
    const pendingRegime = deferred<RegimeData>();
    vi.mocked(gexAPI.getCurrentGEX).mockReturnValue(pendingGex.promise);
    vi.mocked(gexAPI.getCurrentRegime).mockReturnValue(pendingRegime.promise);
    const { client, wrapper: Wrapper } = wrapper();
    const { result, rerender } = renderHook(() => useDashboardData(), { wrapper: Wrapper });

    state.stream = connected('2026-10-14T14:00:10Z', 200);
    rerender();
    expect(client.getQueryData<GEXSnapshot>(currentKey)?.net_gex).toBe(200);

    await act(async () => {
      pendingGex.resolve(snapshot(timestamp, -100));
      pendingRegime.resolve(regime(timestamp, -100));
    });
    await waitFor(() => expect(client.getQueryState(currentKey)?.fetchStatus).toBe('idle'));
    expect(client.getQueryData<GEXSnapshot>(currentKey)?.net_gex).toBe(200);
    expect(client.getQueryData<RegimeData>(regimeKey)?.net_gex).toBe(200);

    state.stream = { ...state.stream, isConnected: false, connectionState: 'disconnected' };
    rerender();
    expect(result.current.gexData?.net_gex).toBe(200);
    expect(result.current.regimeData?.net_gex).toBe(200);
    expect(result.current.lastUpdateTime).toBe(Date.parse('2026-10-14T14:00:10Z'));
  });

  it('orders the regime independently of the current GEX snapshot', async () => {
    vi.mocked(gexAPI.getCurrentRegime).mockResolvedValue(regime('2026-10-14T14:00:15Z', 300));
    const { client, wrapper: Wrapper } = wrapper();
    const { result, rerender } = renderHook(() => useDashboardData(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.regimeData?.net_gex).toBe(300));
    state.stream = connected('2026-10-14T14:00:12Z', 250);
    rerender();

    expect(result.current.gexData?.net_gex).toBe(250);
    expect(result.current.isRealtime).toBe(true);
    expect(result.current.regimeData?.net_gex).toBe(300);
    expect(client.getQueryData<RegimeData>(regimeKey)?.net_gex).toBe(300);
  });

  it('accepts an updated WS payload at the same capture timestamp', async () => {
    const { client, wrapper: Wrapper } = wrapper();
    const { result, rerender } = renderHook(() => useDashboardData(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.gexData?.net_gex).toBe(200));
    state.stream = connected('2026-10-14T14:00:10Z', 250);
    rerender();

    expect(result.current.gexData?.net_gex).toBe(250);
    expect(result.current.regimeData?.net_gex).toBe(250);
    expect(result.current.isRealtime).toBe(true);
    expect(client.getQueryData<GEXSnapshot>(currentKey)?.net_gex).toBe(250);
    expect(client.getQueryData<RegimeData>(regimeKey)?.net_gex).toBe(250);
  });

  it('preserves demo replay moving backward in capture time', async () => {
    state.store.demoModeEnabled = true;
    const { client, wrapper: Wrapper } = wrapper();
    const { result, rerender } = renderHook(() => useDashboardData(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.gexData?.net_gex).toBe(200));
    state.stream = connected('2026-10-13T14:00:05Z', -100);
    rerender();

    expect(result.current.gexData?.net_gex).toBe(-100);
    expect(result.current.regimeData?.net_gex).toBe(-100);
    expect(result.current.isRealtime).toBe(true);
    expect(client.getQueryData<GEXSnapshot>(queryKeys.gex.current('demo', 'yfinance'))?.net_gex).toBe(-100);
    expect(client.getQueryData<RegimeData>(queryKeys.gex.regime('demo', 'yfinance'))?.net_gex).toBe(-100);
  });
});

describe('intraday capture date', () => {
  it('does not copy yesterday capture into the new ET day, even when receipt time is today', () => {
    const { client, wrapper: Wrapper } = wrapper(false);
    const { result, rerender } = renderHook(
      ({ data, receivedAt }) => useIntradayTimeSeries(data, receivedAt),
      { wrapper: Wrapper, initialProps: { data: snapshot('2026-10-15T03:59:55Z', -100), receivedAt: Date.parse('2026-10-15T03:59:55Z') } },
    );
    expect(result.current.dataPointCount).toBe(1);

    state.day = '2026-10-15';
    rerender({ data: snapshot('2026-10-15T03:59:55Z', -100), receivedAt: Date.parse('2026-10-15T04:00:05Z') });
    expect(result.current.timeSeries).toEqual([]);
    expect(client.getQueryData(queryKeys.gex.intradaySeries('live', 'yfinance', 'SPX', '2026-10-15'))).toEqual([]);

    rerender({ data: snapshot('2026-10-15T04:00:10Z', 200), receivedAt: Date.parse('2026-10-15T04:00:15Z') });
    expect(result.current.dataPointCount).toBe(1);
    expect(result.current.timeSeries[0]?.netGex).toBe(200);
  });

  it('skips a live snapshot with an invalid capture timestamp', () => {
    const { wrapper: Wrapper } = wrapper(false);
    const { result } = renderHook(() => useIntradayTimeSeries(snapshot('invalid', -100), Date.now()), { wrapper: Wrapper });
    expect(result.current.timeSeries).toEqual([]);
  });

  it('keeps demo replay captures when their date differs from the live ET day', () => {
    state.store.demoModeEnabled = true;
    const { wrapper: Wrapper } = wrapper(false);
    const { result } = renderHook(() => useIntradayTimeSeries(snapshot('2026-10-13T14:00:00Z', -100), Date.parse('2026-10-13T14:00:00Z')), { wrapper: Wrapper });
    expect(result.current.dataPointCount).toBe(1);
  });
});
