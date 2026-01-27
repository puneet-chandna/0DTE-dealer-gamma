"""0DTE GEX Backend - Pydantic Schemas for API Models."""

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


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
    metrics: Dict[str, float] = Field(default_factory=dict)


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


class WebSocketMessage(BaseModel):
    """WebSocket message format."""

    type: Literal["gex_update", "price_update", "alert"]
    data: Dict[str, float | str | int]
    timestamp: datetime
