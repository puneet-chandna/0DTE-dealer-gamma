"""0DTE GEX Backend - Core Package."""

from app.core.analytics import (
    BacktestResult,
    TradingStrategy,
    VolatilityAnalyzer,
)
from app.core.base_provider import DataProvider
from app.core.charm_vanna_calculator import CharmVannaCalculator
from app.core.constants import (
    CONTRACT_MULTIPLIER,
    DEFAULT_RISK_FREE_RATE,
    FRED_RATE_SYMBOL,
    MAX_IV,
    MIN_IV,
    RATE_CACHE_TTL,
    RISK_FREE_RATE,
    SPX_DIVIDEND_YIELD,
)
from app.core.data_acquisition import (
    RateLimiter,
    get_current_trading_date,
    get_market_status,
    is_market_open,
)
from app.core.gex_calculator import GEXCalculator
from app.core.greeks import BlackScholesGreeks, GreeksResult, ImpliedVolatilitySolver
from app.core.hawkes_engine import HawkesEngine
from app.core.kalman_filter import GEXKalmanFilter
from app.core.provider_registry import ProviderRegistry, get_data_client
from app.core.rate_provider import RiskFreeRateProvider, get_rate_provider
from app.core.technical_indicators import TechnicalIndicatorEngine
from app.core.tradier_provider import TradierClient
from app.core.vectorbt_backtester import VectorBTBacktester
from app.core.vollib_bridge import VolLibBridge
from app.core.yfinance_provider import YFinanceClient

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
    # Data Acquisition & Providers
    "DataProvider",
    "get_data_client",
    "ProviderRegistry",
    "YFinanceClient",
    "TradierClient",
    "RateLimiter",
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
    # Advanced Analytics
    "CharmVannaCalculator",
    "HawkesEngine",
    "GEXKalmanFilter",
]
