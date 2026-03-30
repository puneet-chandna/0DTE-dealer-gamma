/**
 * 0DTE GEX Frontend - TypeScript Type Definitions
 *
 * These types match the backend Pydantic schemas for type safety.
 * RULE: Avoid using 'any' - always specify explicit types.
 */

/**
 * GEX calculation snapshot for a point in time.
 */
export type SnapshotMetricValue = number | string | boolean | null | string[];

export interface GEXSnapshot {
  timestamp: string;
  spot_price: number;
  total_call_gex: number;
  total_put_gex: number;
  net_gex: number;
  zero_gamma_level: number;
  gex_by_strike: Record<number, number>;
  dominant_strike: number;
  metrics: Record<string, SnapshotMetricValue>;
  provider?: string;
  advanced_analytics?: AdvancedAnalytics | null;
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
  provider?: string;
  is_mock?: boolean;
  is_demo?: boolean;
  is_stale?: boolean;
  timestamp?: string;
  advanced_analytics?: AdvancedAnalytics | null;
}

export type MarketStatusType = 'open' | 'pre_market' | 'after_hours' | 'closed_weekend';

export interface MarketStatus {
  is_open: boolean;
  status: MarketStatusType;
  next_open: string | null;
  current_time_et: string;
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

export type ProviderName = 'yfinance' | 'tradier';

export interface DataProviderInfo {
  name: ProviderName;
  display_name: string;
  provides_greeks: boolean;
  supports_spx_directly: boolean;
  rate_limit: number;
  requires_api_key: boolean;
  is_available: boolean;
  unavailable_reason: string | null;
  features: string[];
}

export interface ProvidersResponse {
  providers: DataProviderInfo[];
  active_default: ProviderName;
}

export interface ProviderFeatureConfig {
  displayName: string;
  supportsDashboard: boolean;
  supportsIvSurface: boolean;
  supportsTechnicalIndicators: boolean;
  technicalIndicatorsUnavailableReason?: string;
}

export const PROVIDER_FEATURES: Record<ProviderName, ProviderFeatureConfig> = {
  yfinance: {
    displayName: 'Yahoo Finance',
    supportsDashboard: true,
    supportsIvSurface: true,
    supportsTechnicalIndicators: true,
  },
  tradier: {
    displayName: 'Tradier',
    supportsDashboard: true,
    supportsIvSurface: true,
    supportsTechnicalIndicators: true,
  },
};

// ============================================================================
// New Integration Types
// ============================================================================

/**
 * Risk-free rate info from FRED.
 */
export interface RiskFreeRateInfo {
  rate: number;
  rate_pct: number;
  source: string;
  symbol: string;
  fetched_at: string | null;
  is_fallback: boolean;
  cache_ttl_seconds: number;
}

/**
 * IV surface data point.
 */
export interface IVSurfacePoint {
  strike: number;
  type: string;
  iv: number;
  mid_price: number;
  moneyness: number;
}

/**
 * IV skew data point (put IV - call IV at a strike).
 */
export interface IVSkewPoint {
  strike: number;
  call_iv: number;
  put_iv: number;
  skew: number;
  moneyness: number;
}

/**
 * Full IV surface response from the backend.
 */
export interface IVSurfaceResponse {
  symbol: string;
  spot_price: number;
  surface: IVSurfacePoint[];
  skew: IVSkewPoint[];
  count: number;
}

/**
 * Single data point for technical indicators.
 */
export interface TechnicalIndicatorPoint {
  timestamp: string;
  close: number;
  atr: number | null;
  rsi: number | null;
  bb_upper: number | null;
  bb_mid: number | null;
  bb_lower: number | null;
}

/**
 * Technical indicator response from backend.
 */
export interface TechnicalIndicatorResponse {
  symbol: string;
  period: string;
  indicators: string[];
  data: TechnicalIndicatorPoint[];
  count: number;
}

/**
 * Enhanced backtest result from vectorbt.
 */
export interface VectorBTBacktestResult {
  total_return: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  max_drawdown: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  profit_factor: number;
  avg_trade_return: number;
  best_trade: number;
  worst_trade: number;
  avg_trade_duration_minutes: number;
  start_date: string;
  end_date: string;
  equity_curve: number[];
}

// ============================================================================
// Advanced Analytics Types
// ============================================================================

/**
 * Charm & Vanna hidden flow calculation result.
 */
export interface CharmVannaSnapshot {
  charm_flow: number;
  vanna_flow: number;
  net_hidden_flow: number;
  charm_by_strike: Record<number, number>;
  vanna_by_strike: Record<number, number>;
}

/**
 * Hawkes-style snapshot flow intensity state.
 */
export interface HawkesState {
  call_intensity: number;
  put_intensity: number;
  net_toxicity: number;
  squeeze_probability: number;
  baseline_ready?: boolean;
  confidence_score?: number;
  provider_mode?: 'tradier_rich' | 'yfinance_proxy' | string;
  event_count?: number;
}

/**
 * Combined advanced analytics from all three engines.
 */
export interface AdvancedAnalytics {
  charm_vanna: CharmVannaSnapshot | null;
  hawkes: HawkesState | null;
  smoothed_net_gex: number | null;
}
