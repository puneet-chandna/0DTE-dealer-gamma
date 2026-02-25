"""0DTE GEX Backend - Core Package."""

from app.core.constants import (
    RISK_FREE_RATE,
    DEFAULT_RISK_FREE_RATE,
    FRED_RATE_SYMBOL,
    RATE_CACHE_TTL,
    SPX_DIVIDEND_YIELD,
    CONTRACT_MULTIPLIER,
    MIN_IV,
    MAX_IV,
)
from app.core.greeks import BlackScholesGreeks, ImpliedVolatilitySolver, GreeksResult
from app.core.gex_calculator import GEXCalculator
from app.core.data_acquisition import (
    RateLimiter,
    PolygonClient,
    MockPolygonClient,
    is_market_open,
    get_market_status,
    get_current_trading_date,
)
from app.core.yfinance_provider import YFinanceClient
from app.core.analytics import (
    VolatilityAnalyzer,
    TradingStrategy,
    BacktestResult,
)
from app.core.rate_provider import RiskFreeRateProvider, get_rate_provider
from app.core.vollib_bridge import VolLibBridge
from app.core.technical_indicators import TechnicalIndicatorEngine
from app.core.vectorbt_backtester import VectorBTBacktester

__all__ = [
    # Constants
    "RISK_FREE_RATE",
    "DEFAULT_RISK_FREE_RATE",
    "FRED_RATE_SYMBOL",
    "RATE_CACHE_TTL",
    "SPX_DIVIDEND_YIELD",
    "CONTRACT_MULTIPLIER",
    "MIN_IV",
    "MAX_IV",
    # Greeks
    "BlackScholesGreeks",
    "ImpliedVolatilitySolver",
    "GreeksResult",
    # GEX
    "GEXCalculator",
    # Data Acquisition
    "RateLimiter",
    "PolygonClient",
    "MockPolygonClient",
    "YFinanceClient",
    "is_market_open",
    "get_market_status",
    "get_current_trading_date",
    # Analytics
    "VolatilityAnalyzer",
    "TradingStrategy",
    "BacktestResult",
    # New Integrations
    "RiskFreeRateProvider",
    "get_rate_provider",
    "VolLibBridge",
    "TechnicalIndicatorEngine",
    "VectorBTBacktester",
]
