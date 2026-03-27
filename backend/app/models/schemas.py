"""0DTE GEX Backend - Pydantic Schemas for API Models."""

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Request Models
# ============================================================================


class GEXCurrentRequest(BaseModel):
    """Request parameters for current GEX endpoint."""

    symbol: str = Field(default="SPX", description="Underlying symbol")
    include_greeks: bool = Field(default=True, description="Include Greeks in response")


class GEXHistoricalRequest(BaseModel):
    """Request parameters for historical GEX query."""

    start_date: date = Field(..., description="Start date for historical data")
    end_date: date = Field(..., description="End date for historical data")
    interval: Literal["5m", "15m", "1h", "1d"] = Field(
        default="1h", description="Data interval"
    )


class MarketStatusResponse(BaseModel):
    """Response model for market status endpoint."""

    is_open: bool = Field(..., description="Whether market is currently open")
    status: Literal["open", "pre_market", "after_hours", "closed_weekend"] = Field(
        ..., description="Detailed market status"
    )
    next_open: Optional[str] = Field(None, description="When market opens next")
    current_time_et: str = Field(..., description="Current time in Eastern Time")


# ============================================================================
# Data Models
# ============================================================================


class OptionContract(BaseModel):
    """Individual option contract data."""

    symbol: str
    strike: float
    expiration: datetime
    option_type: Literal["call", "put"] = Field(..., alias="type")
    bid: float
    ask: float
    mid: float
    open_interest: int
    volume: int
    implied_vol: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    vega: Optional[float] = None
    theta: Optional[float] = None

    class Config:
        populate_by_name = True


class OptionsChainResponse(BaseModel):
    """Full options chain response including all contracts."""

    underlying: str
    spot_price: float
    expiration_date: str
    contract_count: int
    contracts: List[Dict[str, float | str | int]]
    timestamp: str
    provider: Optional[str] = None


class GEXSnapshot(BaseModel):
    """GEX calculation result for a point in time."""

    timestamp: datetime
    spot_price: float
    total_call_gex: float  # Negative (dealers short)
    total_put_gex: float  # Positive (dealers long)
    net_gex: float  # Sum of above
    zero_gamma_level: float  # Price where net_gex = 0
    gex_by_strike: Dict[float, float]  # Strike-level breakdown
    dominant_strike: float  # Strike with max |GEX|
    metrics: Dict[str, Any] = Field(default_factory=dict)
    provider: Optional[str] = None
    advanced_analytics: Optional["AdvancedAnalytics"] = None


class CharmVannaSnapshot(BaseModel):
    """Charm & Vanna hidden flow calculation result."""

    charm_flow: float = Field(
        ..., description="Expected dealer hedging flow from time decay (dollars)"
    )
    vanna_flow: float = Field(
        ..., description="Expected dealer hedging flow from IV change (dollars)"
    )
    net_hidden_flow: float = Field(
        ..., description="Combined charm + vanna flow (dollars)"
    )
    charm_by_strike: Dict[float, float] = Field(default_factory=dict)
    vanna_by_strike: Dict[float, float] = Field(default_factory=dict)


class HawkesStateModel(BaseModel):
    """Current state of the Hawkes order flow momentum process."""

    call_intensity: float = Field(
        ..., description="Self-exciting intensity of call order flow"
    )
    put_intensity: float = Field(
        ..., description="Self-exciting intensity of put order flow"
    )
    net_toxicity: float = Field(
        ..., description="call_intensity - put_intensity"
    )
    squeeze_probability: float = Field(
        ..., description="Normalized 0-1 probability of a gamma squeeze"
    )


class AdvancedAnalytics(BaseModel):
    """Combined advanced analytics from all three engines."""

    charm_vanna: Optional[CharmVannaSnapshot] = None
    hawkes: Optional[HawkesStateModel] = None
    smoothed_net_gex: Optional[float] = Field(
        None, description="Kalman-filtered net GEX value"
    )


class GEXHistorical(BaseModel):
    """Historical GEX data for a date range."""

    data: List[GEXSnapshot]
    start_date: datetime
    end_date: datetime
    count: int


class GEXByStrike(BaseModel):
    """GEX breakdown by strike price."""

    strikes: List[float]
    gex_values: List[float]
    spot_price: float
    zero_gamma_level: float


class RegimeData(BaseModel):
    """Current market regime based on GEX."""

    regime: Literal["short_gamma", "long_gamma", "neutral"]
    description: str
    color: str
    net_gex: float
    net_gex_billions: float
    timestamp: datetime


class AnalyticsResult(BaseModel):
    """Statistical analysis result."""

    mean_rv_negative_gex: float
    mean_rv_positive_gex: float
    volatility_increase_pct: float
    t_statistic: float
    p_value: float
    significant: bool
    sample_size_negative: int
    sample_size_positive: int


class SummaryStatistics(BaseModel):
    """Summary statistics of GEX over time period."""

    mean_gex: float
    std_gex: float
    min_gex: float
    max_gex: float
    median_gex: float
    pct_negative_days: float
    sample_size: int


class BacktestResult(BaseModel):
    """Results from backtesting a trading strategy."""

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_return: float
    average_return: float
    sharpe_ratio: float
    max_drawdown: float
    profit_factor: float
    average_trade_duration: float  # in minutes
    start_date: datetime
    end_date: datetime


class WebSocketMessage(BaseModel):
    """WebSocket message format."""

    type: Literal["gex_update", "price_update", "alert"]
    data: Dict[str, float | str | int]
    timestamp: datetime


# ============================================================================
# New Integration Schemas
# ============================================================================


class RiskFreeRateResponse(BaseModel):
    """Response for risk-free rate endpoint."""

    rate: float = Field(..., description="Annualized risk-free rate (decimal)")
    rate_pct: float = Field(..., description="Rate as percentage")
    source: str = Field(..., description="Data source (FRED or fallback)")
    symbol: str = Field(..., description="FRED symbol used")
    fetched_at: Optional[str] = Field(None, description="When rate was fetched")
    is_fallback: bool = Field(..., description="Whether using fallback rate")
    cache_ttl_seconds: int = Field(..., description="Cache TTL in seconds")


class TechnicalIndicatorData(BaseModel):
    """Single data point for technical indicators."""

    timestamp: str
    close: float
    atr: Optional[float] = None
    rsi: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_mid: Optional[float] = None
    bb_lower: Optional[float] = None


class TechnicalIndicatorResponse(BaseModel):
    """Response for technical indicators endpoint."""

    symbol: str
    period: str
    indicators: List[str]
    data: List[TechnicalIndicatorData]
    count: int


class IVSurfaceData(BaseModel):
    """Single data point for IV surface."""

    strike: float
    option_type: str = Field(..., alias="type")
    iv: float
    mid_price: float
    moneyness: float

    class Config:
        populate_by_name = True


class IVSurfaceResponse(BaseModel):
    """Response for IV surface endpoint."""

    symbol: str
    spot_price: float
    surface: List[IVSurfaceData]
    skew: List[Dict[str, float]]
    count: int


class VectorBTBacktestResult(BaseModel):
    """Enhanced backtest results from vectorbt."""

    total_return: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    avg_trade_return: float
    best_trade: float
    worst_trade: float
    avg_trade_duration_minutes: float
    start_date: datetime
    end_date: datetime
    equity_curve: List[float]
