"""0DTE GEX Backend - Dynamic Risk-Free Rate Provider.

Fetches the current risk-free rate from FRED (Federal Reserve Economic Data)
via pandas-datareader. Caches the result for 24 hours and falls back to
the hardcoded default if the network call fails.
"""

import logging
import threading
from datetime import datetime, timedelta

import pandas_datareader.data as web  # noqa: E402 — requires setuptools on Python 3.13+

from app.core.constants import (
    DEFAULT_RISK_FREE_RATE,
    FRED_RATE_SYMBOL,
    RATE_CACHE_TTL,
)

logger = logging.getLogger(__name__)


class RiskFreeRateProvider:
    """Fetch and cache the risk-free rate from FRED.

    Uses the 4-Week Treasury Bill rate (DTB4WK) as the risk-free rate
    proxy for Black-Scholes calculations. The rate is cached in memory
    for 24 hours and refreshed automatically on the next call.

    Falls back to DEFAULT_RISK_FREE_RATE if FRED is unreachable.
    """

    def __init__(self, cache_ttl_seconds: int = RATE_CACHE_TTL) -> None:
        self._cached_rate: float | None = None
        self._last_fetched: datetime | None = None
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._is_fallback: bool = True
        self._source: str = "default"
        self._lock = threading.Lock()

    def _fetch_from_fred(self) -> float:
        """Fetch the latest 4-Week T-Bill rate from FRED.

        Returns:
            Annualized risk-free rate as a decimal (e.g. 0.05 for 5%).

        Raises:
            Exception: If the FRED fetch fails for any reason.
        """
        end = datetime.now()
        start = end - timedelta(days=30)  # Look back 30 days for latest data

        df = web.DataReader(FRED_RATE_SYMBOL, "fred", start, end)

        # Drop NaN rows (weekends / holidays have no data)
        df = df.dropna()

        if df.empty:
            raise ValueError(f"No data returned from FRED for {FRED_RATE_SYMBOL}")

        # Get the most recent observation
        latest_rate_pct = float(df.iloc[-1, 0])

        # FRED returns the rate as a percentage (e.g. 5.25 for 5.25%)
        # Convert to decimal for Black-Scholes
        rate = latest_rate_pct / 100.0

        logger.info(
            f"Fetched risk-free rate from FRED: {latest_rate_pct:.2f}% "
            f"({FRED_RATE_SYMBOL}, date={df.index[-1].date()})"
        )
        return rate

    def _is_cache_valid(self) -> bool:
        """Check if the cached rate is still fresh."""
        if self._cached_rate is None or self._last_fetched is None:
            return False
        return (datetime.now() - self._last_fetched) < self._cache_ttl

    def get_rate(self) -> float:
        """Get the current risk-free rate (thread-safe).

        Returns the cached FRED rate if fresh, otherwise fetches a new one.
        Falls back to DEFAULT_RISK_FREE_RATE on any error.

        Returns:
            Annualized risk-free rate as a decimal.
        """
        with self._lock:
            if self._is_cache_valid():
                return self._cached_rate  # type: ignore[return-value]

            try:
                rate = self._fetch_from_fred()
                self._cached_rate = rate
                self._last_fetched = datetime.now()
                self._is_fallback = False
                self._source = f"FRED ({FRED_RATE_SYMBOL})"
                return rate
            except Exception as e:
                logger.warning(
                    f"Failed to fetch rate from FRED: {e}. "
                    f"Using fallback rate: {DEFAULT_RISK_FREE_RATE}"
                )
                # Use fallback but don't cache it so we retry next time
                self._is_fallback = True
                self._source = "default (fallback)"
                return DEFAULT_RISK_FREE_RATE

    def get_rate_info(self) -> dict:
        """Get rate with metadata for API responses.

        Returns:
            Dictionary with rate, source, fetched_at, and is_fallback fields.
        """
        rate = self.get_rate()
        return {
            "rate": rate,
            "rate_pct": round(rate * 100, 4),
            "source": self._source,
            "symbol": FRED_RATE_SYMBOL,
            "fetched_at": (
                self._last_fetched.isoformat() if self._last_fetched else None
            ),
            "is_fallback": self._is_fallback,
            "cache_ttl_seconds": int(self._cache_ttl.total_seconds()),
        }


# Module-level singleton
_provider: RiskFreeRateProvider | None = None


def get_rate_provider() -> RiskFreeRateProvider:
    """Get or create the singleton rate provider."""
    global _provider
    if _provider is None:
        _provider = RiskFreeRateProvider()
    return _provider
