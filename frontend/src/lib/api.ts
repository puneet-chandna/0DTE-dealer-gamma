import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_URL,
});

interface DemoRequestOptions {
  demo?: boolean;
}

function withDemoParam(
  params: Record<string, unknown>,
  options?: DemoRequestOptions
) {
  const normalizedParams = Object.entries(params).reduce<Record<string, string | number | boolean>>(
    (accumulator, [key, value]) => {
      if (
        typeof value === 'string' ||
        typeof value === 'number' ||
        typeof value === 'boolean'
      ) {
        accumulator[key] = value;
      }

      return accumulator;
    },
    {}
  );

  if (!options?.demo) {
    return normalizedParams;
  }

  return {
    ...normalizedParams,
    demo: true,
  };
}

export const healthAPI = {
  check: async () => {
    const response = await api.get('/health');
    return response.data;
  },
  root: async () => {
    const response = await api.get('/');
    return response.data;
  }
};

export const gexAPI = {
  getCurrentGEX: async (options?: DemoRequestOptions) => {
    const response = await api.get('/api/gex/current', {
      params: withDemoParam({}, options),
    });
    return response.data;
  },
  getGEXByStrikes: async (
    minStrike?: number,
    maxStrike?: number,
    options?: DemoRequestOptions
  ) => {
    const response = await api.get('/api/gex/strikes', {
      params: withDemoParam(
        {
          min_strike: minStrike,
          max_strike: maxStrike,
        },
        options
      ),
    });
    return response.data;
  },
  getCurrentRegime: async (options?: DemoRequestOptions) => {
    const response = await api.get('/api/gex/regime', {
      params: withDemoParam({}, options),
    });
    return response.data;
  },
  getHistoricalGEX: async (
    startDate: string,
    endDate: string,
    interval?: string,
    options?: DemoRequestOptions
  ) => {
    const response = await api.get('/api/gex/historical', {
      params: withDemoParam(
        {
          start_date: startDate,
          end_date: endDate,
          interval,
        },
        options
      ),
    });
    return response.data;
  }
};

export const dataAPI = {
  getAvailableSymbols: async () => {
    return ['SPX'];
  },
  getKlines: async (symbol: string, interval: string, limit: number, startTime: number, endTime: number) => {
    const params = new URLSearchParams();
    params.append('symbol', symbol);
    params.append('interval', interval);
    params.append('limit', limit.toString());
    params.append('start_time', startTime.toString());
    params.append('end_time', endTime.toString());
    try {
        const response = await api.get(`/api/data/market-status?${params.toString()}`);
        return response.data;
    } catch {
        return [];
    }
  },
  getMarketStatus: async () => {
    const response = await api.get('/api/data/market-status');
    return response.data;
  },
  getProviders: async () => {
    const response = await api.get('/api/data/providers');
    return response.data;
  },
  getOptionsChain: async (symbol?: string) => {
    const response = await api.get(`/api/data/options-chain${symbol ? `?symbol=${symbol}` : ''}`);
    return response.data;
  },
  getSpotPrice: async (symbol?: string) => {
    const response = await api.get(`/api/data/spot-price${symbol ? `?symbol=${symbol}` : ''}`);
    return response.data;
  },
  getRiskFreeRate: async () => {
    const response = await api.get('/api/data/risk-free-rate');
    return response.data;
  }
};

export const analyticsAPI = {
  getSummaryStats: async (
    startDate?: string,
    endDate?: string,
    options?: DemoRequestOptions
  ) => {
    const response = await api.get('/api/analytics/summary-statistics', {
      params: withDemoParam(
        {
          start_date: startDate,
          end_date: endDate,
        },
        options
      ),
    });
    return response.data;
  },
  getIVSurface: async (symbol: string, options?: DemoRequestOptions) => {
    const response = await api.get('/api/analytics/iv-surface', {
      params: withDemoParam({ symbol }, options),
    });
    return response.data;
  },
  getTechnicalIndicators: async (
    symbol: string,
    period: string | number,
    interval: string,
    indicators: string | string[] = 'ATR,RSI,BBANDS',
    options?: DemoRequestOptions
  ) => {
    const normalizedPeriod = typeof period === 'number' ? String(period) : period;
    const normalizedIndicators = Array.isArray(indicators)
      ? indicators.join(',')
      : indicators;

    const response = await api.get('/api/analytics/technical-indicators', {
      params: withDemoParam(
        {
          symbol,
          period: normalizedPeriod,
          interval,
          indicators: normalizedIndicators,
        },
        options
      ),
    });
    return response.data;
  },
  runVectorbtBacktest: async (params: Record<string, unknown>, options?: DemoRequestOptions) => {
    const response = await api.get('/api/analytics/vectorbt-backtest', {
      params: withDemoParam(params, options),
    });
    return response.data;
  },
  getGexVolatility: async () => {
    const response = await api.get('/api/analytics/gex-volatility');
    return response.data;
  },
  getBacktest: async (params: Record<string, unknown>, options?: DemoRequestOptions) => {
    const response = await api.get('/api/analytics/backtest', {
      params: withDemoParam(params, options),
    });
    return response.data;
  }
};

export const websocketAPI = {
  getConnections: async () => {
    const response = await api.get('/ws/connections');
    return response.data;
  }
};
