"""0DTE GEX Backend - Core Constants.

These constants are used throughout the GEX calculation engine.
Update quarterly or as market conditions change.
"""

# Risk-free rate FALLBACK (used when FRED is unreachable)
# Live rate is fetched from FRED via pandas-datareader (see rate_provider.py)
# Source: Federal Reserve Bank of New York
# Last updated: 2024-Q4
DEFAULT_RISK_FREE_RATE: float = 0.05  # 5% annualized

# Backward-compatible alias (deprecated — prefer DEFAULT_RISK_FREE_RATE)
RISK_FREE_RATE: float = DEFAULT_RISK_FREE_RATE

# FRED (Federal Reserve Economic Data) settings
FRED_RATE_SYMBOL: str = "DTB4WK"  # 4-Week Treasury Bill rate
RATE_CACHE_TTL: int = 86400  # 24 hours in seconds

# SPX dividend yield
# Source: S&P 500 Index dividend data
# Last updated: 2024-Q4
SPX_DIVIDEND_YIELD: float = 0.015  # 1.5% annualized

# Standard US options contract multiplier
CONTRACT_MULTIPLIER: int = 100

# Volatility bounds for data validation
MIN_IV: float = 0.01  # 1% - below this is suspicious
MAX_IV: float = 5.0   # 500% - above this is data error

# Trading hours (Eastern Time)
MARKET_OPEN_HOUR: int = 9
MARKET_OPEN_MINUTE: int = 30
MARKET_CLOSE_HOUR: int = 16
MARKET_CLOSE_MINUTE: int = 0

# GEX regime thresholds (in dollars)
SHORT_GAMMA_THRESHOLD: float = -1e9  # -$1 billion
LONG_GAMMA_THRESHOLD: float = 1e9    # +$1 billion

# Strike filtering (percentage of spot price)
STRIKE_RANGE_PERCENT: float = 0.20  # ±20% of spot

# API rate limiting
POLYGON_FREE_TIER_RATE: int = 5  # requests per minute
POLYGON_PAID_TIER_RATE: int = 100  # requests per minute

# Cache TTL (seconds)
GEX_CACHE_TTL: int = 5
SPOT_CACHE_TTL: int = 1
OPTIONS_CHAIN_CACHE_TTL: int = 30
ANALYTICS_CACHE_TTL: int = 300  # 5 minutes
