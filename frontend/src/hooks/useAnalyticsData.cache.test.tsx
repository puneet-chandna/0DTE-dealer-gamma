import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { analyticsQueryKeys, useIVSurface, useTechnicalIndicators } from './useAnalyticsData';
import type { IVSurfaceResponse, TechnicalIndicatorResponse } from '@/types';

const { api, store } = vi.hoisted(() => ({
  api: { getIVSurface: vi.fn(), getTechnicalIndicators: vi.fn() },
  store: { demoModeEnabled: false, selectedProvider: 'yfinance' },
}));

vi.mock('@/lib/api', () => ({ analyticsAPI: api }));
vi.mock('@/stores/uiStore', () => ({ useUIStore: () => store }));

const ivSnapshot: IVSurfaceResponse = {
  symbol: 'SPY', spot_price: 600, surface: [], skew: [], count: 0,
};
const technicalSnapshot: TechnicalIndicatorResponse = {
  symbol: 'SPY', period: '1mo', indicators: ['ATR', 'RSI', 'BBANDS'], count: 1,
  data: [{ timestamp: '2025-01-01', close: 600, atr: 1, rsi: 50,
    bb_upper: 610, bb_mid: 600, bb_lower: 590 }],
};
const ivKey = analyticsQueryKeys.ivSurface('live', 'yfinance', 'SPY');
const technicalKey = analyticsQueryKeys.technicalIndicators('live', 'yfinance', 'SPY', '1mo', '1d', 'ATR,RSI,BBANDS');
let client: QueryClient;

function Wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function useLiveAnalytics() {
  return { iv: useIVSurface(), technical: useTechnicalIndicators() };
}

function seedCache(updatedAt: number) {
  client.setQueryData(ivKey, ivSnapshot, { updatedAt });
  client.setQueryData(technicalKey, technicalSnapshot, { updatedAt });
}

beforeEach(() => {
  vi.clearAllMocks();
  store.demoModeEnabled = false;
  store.selectedProvider = 'yfinance';
  api.getIVSurface.mockResolvedValue({ ...ivSnapshot, spot_price: 601 });
  api.getTechnicalIndicators.mockResolvedValue({ ...technicalSnapshot, data: [{ ...technicalSnapshot.data[0], close: 601 }] });
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  focusManager.setFocused(true);
  onlineManager.setOnline(true);
});

afterEach(() => {
  cleanup();
  client.clear();
  focusManager.setFocused(undefined);
});

describe('live analytics cache freshness', () => {
  it.each(['mount', 'focus', 'reconnect'])('refreshes stale IV and technical data on %s', async (event) => {
    const staleAt = Date.now() - 6 * 60 * 1000;
    seedCache(event === 'mount' ? staleAt : Date.now());
    const { result } = renderHook(useLiveAnalytics, { wrapper: Wrapper });

    if (event !== 'mount') {
      expect(api.getIVSurface).not.toHaveBeenCalled();
      expect(api.getTechnicalIndicators).not.toHaveBeenCalled();
      await act(async () => { seedCache(staleAt); });
      await waitFor(() => expect(result.current.iv.isStale && result.current.technical.isStale).toBe(true));
      await act(async () => {
        if (event === 'focus') {
          focusManager.setFocused(false);
          focusManager.setFocused(true);
        } else {
          onlineManager.setOnline(false);
          onlineManager.setOnline(true);
        }
      });
    }

    await waitFor(() => {
      expect(result.current.iv.data?.spot_price).toBe(601);
      expect(result.current.technical.data?.data[0].close).toBe(601);
    });
    expect(api.getIVSurface).toHaveBeenCalledTimes(1);
    expect(api.getTechnicalIndicators).toHaveBeenCalledTimes(1);
    expect(api.getIVSurface).toHaveBeenCalledWith('SPY', { demo: false, provider: 'yfinance' });
    expect(api.getTechnicalIndicators).toHaveBeenCalledWith('SPY', '1mo', '1d', 'ATR,RSI,BBANDS', { demo: false, provider: 'yfinance' });
  });

  it('keeps fresh snapshots isolated by mode and provider', async () => {
    seedCache(Date.now());
    const { result, rerender } = renderHook(useLiveAnalytics, { wrapper: Wrapper });
    expect(result.current.iv.data?.spot_price).toBe(600);
    expect(api.getIVSurface).not.toHaveBeenCalled();

    store.demoModeEnabled = true;
    rerender();
    await waitFor(() => expect(result.current.iv.data?.spot_price).toBe(601));
    expect(api.getIVSurface).toHaveBeenLastCalledWith('SPY', { demo: true, provider: 'yfinance' });
    expect(api.getTechnicalIndicators).toHaveBeenLastCalledWith('SPY', '1mo', '1d', 'ATR,RSI,BBANDS', { demo: true, provider: 'yfinance' });

    api.getIVSurface.mockResolvedValue({ ...ivSnapshot, spot_price: 602 });
    store.demoModeEnabled = false;
    store.selectedProvider = 'tradier';
    rerender();
    await waitFor(() => expect(result.current.iv.data?.spot_price).toBe(602));
    expect(api.getIVSurface).toHaveBeenLastCalledWith('SPY', { demo: false, provider: 'tradier' });
    expect(api.getTechnicalIndicators).toHaveBeenLastCalledWith('SPY', '1mo', '1d', 'ATR,RSI,BBANDS', { demo: false, provider: 'tradier' });

    store.selectedProvider = 'yfinance';
    rerender();
    expect(result.current.iv.data?.spot_price).toBe(600);
    expect(api.getIVSurface).toHaveBeenCalledTimes(2);
    expect(api.getTechnicalIndicators).toHaveBeenCalledTimes(2);
  });
});
