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
from app.core.base_provider import DataProvider
from app.core.greeks import BlackScholesGreeks, ImpliedVolatilitySolver, GreeksResult
from app.core.gex_calculator import GEXCalculator
from app.core.data_acquisition import (
    RateLimiter,
    is_market_open,
    get_market_status,
    get_current_trading_date,
)
from app.core.provider_registry import get_data_client, ProviderRegistry
from app.core.tradier_provider import TradierClient
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
from app.core.charm_vanna_calculator import CharmVannaCalculator
from app.core.hawkes_engine import HawkesEngine
from app.core.kalman_filter import GEXKalmanFilter

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
