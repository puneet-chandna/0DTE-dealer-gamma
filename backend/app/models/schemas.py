"""0DTE GEX Backend - Pydantic Schemas for API Models."""

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

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
    interval: Literal["5m", "15m", "1h", "1d"] = Field(default="1h", description="Data interval")


class MarketStatusResponse(BaseModel):
    """Response model for market status endpoint."""

    is_open: bool = Field(..., description="Whether market is currently open")
    status: Literal["open", "pre_market", "after_hours", "closed_weekend"] = Field(
        ..., description="Detailed market status"
    )
    next_open: str | None = Field(None, description="When market opens next")
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
    implied_vol: float | None = None
    delta: float | None = None
    gamma: float | None = None
    vega: float | None = None
    theta: float | None = None

    class Config:
        populate_by_name = True


class OptionsChainResponse(BaseModel):
    """Full options chain response including all contracts."""

    model_config = ConfigDict(allow_inf_nan=False)

    underlying: str
    spot_price: float
    expiration_date: str
    contract_count: int
    contracts: list[dict[str, float | str | int | None]]
    timestamp: str
    provider: str | None = None
    is_stale: bool = False
    age_seconds: float = Field(default=0, ge=0, description="Age of this backend capture")
    captured_at: str | None = None
    market_status: Literal["open", "closed"] = "closed"


class SpotPriceResponse(BaseModel):
    """Spot capture with response-time cache freshness and market status."""

    symbol: str
    price: float
    timestamp: str
    provider: str | None = None
    is_stale: bool = False
    age_seconds: float = Field(default=0, ge=0, description="Age of this backend capture")
    captured_at: str | None = None
    market_status: Literal["open", "closed"] = "closed"


class GEXSnapshot(BaseModel):
    """GEX calculation result for a point in time."""

    timestamp: datetime
    spot_price: float
    total_call_gex: float  # Positive signed-inventory convention
    total_put_gex: float  # Negative signed-inventory convention
    net_gex: float  # Sum of above
    zero_gamma_level: float  # Repriced root only when metrics.zero_gamma_crossing_found
    gex_by_strike: dict[float, float]  # Strike-level breakdown
    dominant_strike: float  # Strike with max |GEX|
    metrics: dict[str, Any] = Field(default_factory=dict)
    provider: str | None = None
    advanced_analytics: Optional["AdvancedAnalytics"] = None


class CharmVannaSnapshot(BaseModel):
    """Charm & Vanna hidden flow calculation result."""

    charm_flow: float = Field(
        ...,
        description="Fixed-spot signed-inventory hedge scenario from time decay (dollar notional)",
    )
    vanna_flow: float = Field(
        ...,
        description="Fixed-spot signed-inventory hedge scenario from absolute IV change (dollar notional)",
    )
    net_hidden_flow: float = Field(..., description="Combined charm + vanna flow (dollars)")
    charm_by_strike: dict[float, float] = Field(default_factory=dict)
    vanna_by_strike: dict[float, float] = Field(default_factory=dict)


class HawkesStateModel(BaseModel):
    """Current state of the Hawkes-style snapshot flow process."""

    call_intensity: float = Field(
        ..., description="Hawkes-style call intensity from snapshot changes"
    )
    put_intensity: float = Field(
        ..., description="Hawkes-style put intensity from snapshot changes"
    )
    net_toxicity: float = Field(..., description="call_intensity - put_intensity")
    squeeze_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        validation_alias=AliasChoices("squeeze_score", "squeeze_probability"),
        description="Uncalibrated 0-1 snapshot imbalance score, not an event probability",
    )
    baseline_ready: bool = Field(
        default=False,
        description="Whether consecutive snapshots have established a valid baseline",
    )
    confidence_score: float = Field(
        default=0.0,
        description="Estimated trust score for the current Hawkes-style snapshot proxy",
    )
    provider_mode: str = Field(
        default="tradier_rich",
        description="Provider quality mode: tradier_rich or yfinance_proxy",
    )
    event_count: int = Field(
        default=0,
        description="Number of contracts that contributed new events in this update",
    )


class AdvancedAnalytics(BaseModel):
    """Combined advanced analytics from all three engines."""

    charm_vanna: CharmVannaSnapshot | None = None
    hawkes: HawkesStateModel | None = None
    smoothed_net_gex: float | None = Field(None, description="Kalman-filtered net GEX value")


class GEXHistorical(BaseModel):
    """Historical GEX data for a date range."""

    data: list[GEXSnapshot]
    start_date: datetime
    end_date: datetime
    count: int


class GEXByStrike(BaseModel):
    """GEX breakdown by strike price."""

    strikes: list[float]
    gex_values: list[float]
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


class DataProvenance(BaseModel):
    """Observed data coverage and limitations, independent of model performance."""

    provider: str
    requested_symbol: str
    actual_instrument: str
    is_proxy: bool
    data_kind: Literal["captured", "synthetic"]
    sample_count: int
    actual_start: datetime | None = None
    actual_end: datetime | None = None
    timestamp_basis: str = "capture reference; source freshness unknown"
    nominal_options_delay_minutes: int | None = None
    open_interest_frequency: str = "daily; exact as-of date unknown"
    calculation_versions: list[str] = Field(default_factory=list)
    quality_limitations: list[str] = Field(default_factory=list)


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
    provenance: DataProvenance | None = None


class SummaryStatistics(BaseModel):
    """Summary statistics of GEX over time period."""

    mean_gex: float
    std_gex: float
    min_gex: float
    max_gex: float
    median_gex: float
    pct_negative_days: float
    sample_size: int
    provenance: DataProvenance | None = None


class BacktestResult(BaseModel):
    """Results from backtesting a trading strategy."""

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_return: float
    average_return: float
    sharpe_ratio: float | None
    max_drawdown: float
    profit_factor: float | None
    average_trade_duration: float  # in minutes
    start_date: datetime
    end_date: datetime
    closed_trades: int = 0
    open_trades: int = 0
    initial_cash: float = 100_000.0
    fees: float = 0.001
    slippage: float = 0.001
    position_size: float = 1.0
    execution_delay_bars: int = 1
    bar_interval_minutes: float = 1.0
    equity_curve: list[float] = Field(default_factory=list)
    equity_timestamps: list[datetime] = Field(default_factory=list)
    strategy: str = "gex_long_underlying"
    provenance: DataProvenance | None = None


class WebSocketMessage(BaseModel):
    """WebSocket message format."""

    type: Literal["gex_update", "price_update", "alert"]
    data: dict[str, float | str | int]
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
    fetched_at: str | None = Field(None, description="When rate was fetched")
    is_fallback: bool = Field(..., description="Whether using fallback rate")
    cache_ttl_seconds: int = Field(..., description="Cache TTL in seconds")


class TechnicalIndicatorData(BaseModel):
    """Single data point for technical indicators."""

    timestamp: str
    close: float
    atr: float | None = None
    rsi: float | None = None
    bb_upper: float | None = None
    bb_mid: float | None = None
    bb_lower: float | None = None


class TechnicalIndicatorResponse(BaseModel):
    """Response for technical indicators endpoint."""

    symbol: str
    period: str
    indicators: list[str]
    data: list[TechnicalIndicatorData]
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
    surface: list[IVSurfaceData]
    skew: list[dict[str, float]]
    count: int


class VectorBTBacktestResult(BaseModel):
    """Enhanced backtest results from vectorbt."""

    total_return: float
    sharpe_ratio: float | None
    sortino_ratio: float | None
    calmar_ratio: float | None
    max_drawdown: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float | None
    avg_trade_return: float
    best_trade: float
    worst_trade: float
    avg_trade_duration_minutes: float
    start_date: datetime
    end_date: datetime
    equity_curve: list[float]
    equity_timestamps: list[datetime] = Field(default_factory=list)
    closed_trades: int = 0
    open_trades: int = 0
    initial_cash: float = 100_000.0
    fees: float = 0.001
    slippage: float = 0.001
    position_size: float = 1.0
    execution_delay_bars: int = 1
    bar_interval_minutes: float = 1.0
    strategy: str = "gex_long_underlying"
    provenance: DataProvenance | None = None
