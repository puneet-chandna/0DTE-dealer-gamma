import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_URL,
});

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
  getCurrentGEX: async () => {
    const response = await api.get('/api/gex/current');
    return response.data;
  },
  getGEXByStrikes: async (minStrike?: number, maxStrike?: number) => {
    const params = new URLSearchParams();
    if (minStrike) params.append('min_strike', minStrike.toString());
    if (maxStrike) params.append('max_strike', maxStrike.toString());
    const response = await api.get(`/api/gex/strikes?${params.toString()}`);
    return response.data;
  },
  getCurrentRegime: async () => {
    const response = await api.get('/api/gex/regime');
    return response.data;
  },
  getHistoricalGEX: async (startDate: string, endDate: string, interval?: string) => {
    const params = new URLSearchParams();
    params.append('start_date', startDate);
    params.append('end_date', endDate);
    if (interval) params.append('interval', interval);
    const response = await api.get(`/api/gex/historical?${params.toString()}`);
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
  getSummaryStats: async (startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    const response = await api.get(`/api/analytics/summary-statistics?${params.toString()}`);
    return response.data;
  },
  getIVSurface: async (symbol: string) => {
    const response = await api.get(`/api/analytics/iv-surface?symbol=${symbol}`);
    return response.data;
  },
  getTechnicalIndicators: async (symbol: string, period: number, interval: string, indicators: string[]) => {
    const params = new URLSearchParams();
    params.append('symbol', symbol);
    params.append('period', period.toString());
    params.append('interval', interval);
    indicators.forEach(ind => params.append('indicators', ind));
    const response = await api.get(`/api/analytics/technical-indicators?${params.toString()}`);
    return response.data;
  },
  runVectorbtBacktest: async (params: any) => {
    const response = await api.get(`/api/analytics/vectorbt-backtest`, { params });
    return response.data;
  },
  getGexVolatility: async () => {
    const response = await api.get('/api/analytics/gex-volatility');
    return response.data;
  },
  getBacktest: async (params: any) => {
    const response = await api.get('/api/analytics/backtest', { params });
    return response.data;
  }
};

export const websocketAPI = {
  getConnections: async () => {
    const response = await api.get('/ws/connections');
    return response.data;
  }
};
