/**
 * 0DTE GEX Frontend - TypeScript Type Definitions
 *
 * These types match the backend Pydantic schemas for type safety.
 * RULE: Avoid using 'any' - always specify explicit types.
 */

/**
 * GEX calculation snapshot for a point in time.
 */
export interface GEXSnapshot {
  timestamp: string;
  spot_price: number;
  total_call_gex: number;
  total_put_gex: number;
  net_gex: number;
  zero_gamma_level: number;
  gex_by_strike: Record<number, number>;
  dominant_strike: number;
  metrics: Record<string, number>;
}

/**
 * GEX breakdown by strike price for charting.
 */
export interface GEXByStrike {
  strikes: number[];
  gex_values: number[];
  spot_price: number;
  zero_gamma_level: number;
}

/**
 * Market regime based on dealer positioning.
 */
export type RegimeType = 'short_gamma' | 'long_gamma' | 'neutral';

/**
 * WebSocket connection state.
 */
export type ConnectionState = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'error';

export interface RegimeData {
  regime: RegimeType;
  description: string;
  color: string;
  net_gex: number;
  net_gex_billions: number;
  timestamp: string;
}

/**
 * Historical GEX data for backtesting and analysis.
 */
export interface GEXHistorical {
  data: GEXSnapshot[];
  start_date: string;
  end_date: string;
  count: number;
}

/**
 * Statistical analysis result for GEX-volatility relationship.
 */
export interface AnalyticsResult {
  mean_rv_negative_gex: number;
  mean_rv_positive_gex: number;
  volatility_increase_pct: number;
  t_statistic: number;
  p_value: number;
  significant: boolean;
  sample_size_negative: number;
  sample_size_positive: number;
}

/**
 * Summary statistics for dashboard display.
 */
export interface SummaryStatistics {
  mean_gex: number;
  std_gex: number;
  min_gex: number;
  max_gex: number;
  median_gex: number;
  pct_negative_days: number;
  sample_size: number;
}

/**
 * WebSocket message format for real-time updates.
 */
export type WebSocketMessageType = 'gex_update' | 'price_update' | 'alert';

export interface WebSocketMessage {
  type: WebSocketMessageType;
  data: Record<string, number | string>;
  timestamp: string;
}

/**
 * Real-time GEX update from WebSocket.
 */
export interface GEXUpdate {
  net_gex: number;
  net_gex_billions: number;
  zero_gamma_level: number;
  spot_price: number;
  regime: RegimeType;
  is_mock?: boolean;
  is_stale?: boolean;
  timestamp?: string;
}

/**
 * Chart data format for GEX bar chart.
 */
export interface GEXChartDataPoint {
  strike: number;
  gex: number;
  gexBillions: number;
}

/**
 * Time series data point for intraday GEX chart.
 */
export interface TimeSeriesDataPoint {
  timestamp: string;
  netGex: number;
  netGexBillions: number;
  spotPrice?: number;
}

/**
 * API error response format.
 */
export interface APIError {
  detail: string;
  status_code?: number;
}

/**
 * Health check response.
 */
export interface HealthStatus {
  status: 'healthy' | 'unhealthy';
}
