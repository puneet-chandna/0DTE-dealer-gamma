/**
 * 0DTE GEX Frontend - API Client Tests
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';
import { gexAPI, analyticsAPI, dataAPI, healthAPI } from './api';

// Mock axios
vi.mock('axios', () => {
  const mockAxios = {
    create: vi.fn(() => mockAxios),
    get: vi.fn(),
    isAxiosError: vi.fn(),
  };
  return { default: mockAxios };
});

describe('gexAPI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getCurrentGEX', () => {
    it('returns GEX snapshot on success', async () => {
      const mockData = {
        timestamp: '2026-01-29T10:00:00',
        spot_price: 5950.25,
        total_call_gex: -2e9,
        total_put_gex: 1.5e9,
        net_gex: -0.5e9,
        zero_gamma_level: 5925,
        gex_by_strike: { 5900: -0.1e9, 5950: 0.2e9 },
        dominant_strike: 5950,
        metrics: {},
      };

      vi.mocked(axios.get).mockResolvedValueOnce({ data: mockData });

      const result = await gexAPI.getCurrentGEX();
      expect(result).toEqual(mockData);
    });

    it('throws error on API failure', async () => {
      const error = new Error('Network error');
      vi.mocked(axios.get).mockRejectedValueOnce(error);
      vi.mocked(axios.isAxiosError).mockReturnValue(false);

      await expect(gexAPI.getCurrentGEX()).rejects.toThrow('Network error');
    });

    it('passes provider param when requested', async () => {
      vi.mocked(axios.get).mockResolvedValueOnce({ data: {} });

      await gexAPI.getCurrentGEX({ provider: 'tradier' });

      expect(axios.get).toHaveBeenCalledWith(
        '/api/gex/current',
        expect.objectContaining({
          params: { provider: 'tradier' },
        })
      );
    });
  });

  describe('getGEXByStrikes', () => {
    it('returns GEX by strike data', async () => {
      const mockData = {
        strikes: [5900, 5925, 5950, 5975, 6000],
        gex_values: [-0.1e9, 0.05e9, 0.2e9, 0.1e9, -0.05e9],
        spot_price: 5950,
        zero_gamma_level: 5942,
      };

      vi.mocked(axios.get).mockResolvedValueOnce({ data: mockData });

      const result = await gexAPI.getGEXByStrikes();
      expect(result).toEqual(mockData);
    });

    it('passes min/max strike params', async () => {
      vi.mocked(axios.get).mockResolvedValueOnce({ data: {} });

      await gexAPI.getGEXByStrikes(5800, 6100);

      expect(axios.get).toHaveBeenCalledWith(
        '/api/gex/strikes',
        expect.objectContaining({
          params: { min_strike: 5800, max_strike: 6100 },
        })
      );
    });

    it('omits undefined strike params while preserving provider and demo filters', async () => {
      vi.mocked(axios.get).mockResolvedValueOnce({ data: {} });

      await gexAPI.getGEXByStrikes(undefined, undefined, {
        provider: 'tradier',
        demo: true,
      });

      expect(axios.get).toHaveBeenCalledWith(
        '/api/gex/strikes',
        expect.objectContaining({
          params: {
            provider: 'tradier',
            demo: true,
          },
        })
      );
    });
  });

  describe('getCurrentRegime', () => {
    it('returns regime data', async () => {
      const mockData = {
        regime: 'short_gamma',
        description: 'Dealers are short gamma. Volatility amplification expected.',
        color: 'red',
        net_gex: -1.5e9,
        net_gex_billions: -1.5,
        timestamp: '2026-01-29T10:00:00',
      };

      vi.mocked(axios.get).mockResolvedValueOnce({ data: mockData });

      const result = await gexAPI.getCurrentRegime();
      expect(result).toEqual(mockData);
      expect(result.regime).toBe('short_gamma');
    });
  });

  describe('getHistoricalGEX', () => {
    it('passes date range params correctly', async () => {
      vi.mocked(axios.get).mockResolvedValueOnce({ data: { data: [], count: 0 } });

      await gexAPI.getHistoricalGEX('2026-01-01', '2026-01-29', '1h');

      expect(axios.get).toHaveBeenCalledWith(
        '/api/gex/historical',
        expect.objectContaining({
          params: {
            symbol: 'SPX',
            start_date: '2026-01-01',
            end_date: '2026-01-29',
            interval: '1h',
          },
        })
      );
    });
  });
});

describe('analyticsAPI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getSummaryStats', () => {
    it('returns summary statistics', async () => {
      const mockData = {
        mean_gex: -0.5e9,
        std_gex: 1e9,
        min_gex: -3e9,
        max_gex: 2e9,
        median_gex: -0.2e9,
        pct_negative_days: 65.5,
        sample_size: 252,
      };

      vi.mocked(axios.get).mockResolvedValueOnce({ data: mockData });

      const result = await analyticsAPI.getSummaryStats();
      expect(result).toEqual(mockData);
    });

    it('omits undefined dates and keeps the default symbol in request params', async () => {
      vi.mocked(axios.get).mockResolvedValueOnce({ data: {} });

      await analyticsAPI.getSummaryStats(undefined, undefined, {
        provider: 'yfinance',
      });

      expect(axios.get).toHaveBeenCalledWith(
        '/api/analytics/summary-statistics',
        expect.objectContaining({
          params: {
            symbol: 'SPX',
            provider: 'yfinance',
          },
        })
      );
    });
  });

  describe('getTechnicalIndicators', () => {
    it('normalizes numeric periods and indicator arrays for backward compatibility', async () => {
      vi.mocked(axios.get).mockResolvedValueOnce({ data: { data: [], count: 0 } });

      await analyticsAPI.getTechnicalIndicators('SPY', 30, '1d', ['ATR', 'RSI']);

      expect(axios.get).toHaveBeenCalledWith(
        '/api/analytics/technical-indicators',
        expect.objectContaining({
          params: {
            symbol: 'SPY',
            period: '30',
            interval: '1d',
            indicators: 'ATR,RSI',
          },
        })
      );
    });
  });

  describe('getIVSurface', () => {
    it('passes provider param for provider-aware analytics requests', async () => {
      vi.mocked(axios.get).mockResolvedValueOnce({ data: { surface: [], skew: [], count: 0 } });

      await analyticsAPI.getIVSurface('SPX', { provider: 'tradier' });

      expect(axios.get).toHaveBeenCalledWith(
        '/api/analytics/iv-surface',
        expect.objectContaining({
          params: {
            symbol: 'SPX',
            provider: 'tradier',
          },
        })
      );
    });
  });
});

describe('dataAPI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns klines data on success', async () => {
    const mockData = [{ close: 100 }];
    vi.mocked(axios.get).mockResolvedValueOnce({ data: mockData });

    const result = await dataAPI.getKlines('SPY', '1m', 50, 10, 20);

    expect(result).toEqual(mockData);
    expect(axios.get).toHaveBeenCalledWith(
      '/api/data/market-status?symbol=SPY&interval=1m&limit=50&start_time=10&end_time=20'
    );
  });

  it('passes provider param for spot price requests', async () => {
    vi.mocked(axios.get).mockResolvedValueOnce({ data: { price: 5000 } });

    await dataAPI.getSpotPrice('SPX', { provider: 'tradier' });

    expect(axios.get).toHaveBeenCalledWith(
      '/api/data/spot-price',
      expect.objectContaining({
        params: {
          symbol: 'SPX',
          provider: 'tradier',
        },
      })
    );
  });

  it('returns an empty array when klines request fails', async () => {
    vi.mocked(axios.get).mockRejectedValueOnce(new Error('request failed'));

    const result = await dataAPI.getKlines('SPY', '5m', 25, 100, 200);

    expect(result).toEqual([]);
  });
});

describe('healthAPI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('check', () => {
    it('returns healthy status', async () => {
      vi.mocked(axios.get).mockResolvedValueOnce({ data: { status: 'healthy' } });

      const result = await healthAPI.check();
      expect(result.status).toBe('healthy');
    });

    it('handles unhealthy status', async () => {
      vi.mocked(axios.get).mockResolvedValueOnce({ data: { status: 'unhealthy' } });

      const result = await healthAPI.check();
      expect(result.status).toBe('unhealthy');
    });
  });
});
