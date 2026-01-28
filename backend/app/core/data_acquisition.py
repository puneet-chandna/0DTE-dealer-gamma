"""0DTE GEX Backend - Data Acquisition Module.

Handles data fetching from Polygon.io API with rate limiting,
market hours checking, and data filtering for 0DTE options.
"""

import asyncio
import logging
from collections import deque
from datetime import datetime, date, timedelta
from time import time
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo

import httpx
import pandas as pd
from polygon import RESTClient
from polygon.rest.models import OptionsContract

from app.core.constants import (
    MARKET_OPEN_HOUR,
    MARKET_OPEN_MINUTE,
    MARKET_CLOSE_HOUR,
    MARKET_CLOSE_MINUTE,
    POLYGON_FREE_TIER_RATE,
    POLYGON_PAID_TIER_RATE,
    STRIKE_RANGE_PERCENT,
    MIN_IV,
    MAX_IV,
)

logger = logging.getLogger(__name__)

# Eastern Time timezone
ET = ZoneInfo("America/New_York")


class RateLimiter:
    """
    Token bucket rate limiter for API calls.

    Tracks the last N calls and enforces a minimum interval between calls
    to stay within the API rate limit.
    """

    def __init__(self, calls_per_minute: int = 5):
        """
        Initialize rate limiter.

        Args:
            calls_per_minute: Maximum number of API calls allowed per minute.
        """
        self.calls_per_minute = calls_per_minute
        self.min_interval = 60.0 / calls_per_minute  # seconds between calls
        self._call_times: deque[float] = deque(maxlen=calls_per_minute)
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """
        Wait if necessary to respect rate limit.

        This method should be called before each API request.
        """
        async with self._lock:
            now = time()

            if len(self._call_times) >= self.calls_per_minute:
                oldest = self._call_times[0]
                wait_time = 60.0 - (now - oldest)
                if wait_time > 0:
                    logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)

            self._call_times.append(time())

    def reset(self) -> None:
        """Reset the rate limiter (useful for testing)."""
        self._call_times.clear()

    @property
    def remaining_calls(self) -> int:
        """Number of calls remaining in the current window."""
        now = time()
        # Count calls made in the last 60 seconds
        recent_calls = sum(1 for t in self._call_times if now - t < 60)
        return max(0, self.calls_per_minute - recent_calls)


def is_market_open(now: Optional[datetime] = None) -> bool:
    """
    Check if US equity market is currently open.

    Market hours: 9:30 AM - 4:00 PM Eastern Time, Monday-Friday.

    Args:
        now: Optional datetime to check (defaults to current time).

    Returns:
        True if market is open, False otherwise.
    """
    if now is None:
        now = datetime.now(ET)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=ET)

    # Skip weekends (Monday=0, Sunday=6)
    if now.weekday() >= 5:
        return False

    # Check market hours
    market_open = now.replace(
        hour=MARKET_OPEN_HOUR,
        minute=MARKET_OPEN_MINUTE,
        second=0,
        microsecond=0,
    )
    market_close = now.replace(
        hour=MARKET_CLOSE_HOUR,
        minute=MARKET_CLOSE_MINUTE,
        second=0,
        microsecond=0,
    )

    return market_open <= now <= market_close


def get_market_status(now: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Get detailed market status for UI display.

    Returns a dictionary with:
    - is_open: Boolean indicating if market is currently open
    - status: One of 'open', 'pre_market', 'after_hours', 'closed_weekend'
    - next_open: Human-readable string for when market opens next
    - current_time_et: Current time in Eastern Time (ISO format)

    Args:
        now: Optional datetime to check (defaults to current time).
    """
    if now is None:
        now = datetime.now(ET)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=ET)

    is_open = is_market_open(now)

    if now.weekday() >= 5:
        # Weekend
        status = "closed_weekend"
        # Calculate days until Monday
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_open = f"Monday {MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d} AM ET"
    elif now.hour < MARKET_OPEN_HOUR or (
        now.hour == MARKET_OPEN_HOUR and now.minute < MARKET_OPEN_MINUTE
    ):
        # Pre-market
        status = "pre_market"
        next_open = f"Today {MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d} AM ET"
    elif now.hour >= MARKET_CLOSE_HOUR:
        # After hours
        status = "after_hours"
        if now.weekday() == 4:  # Friday
            next_open = f"Monday {MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d} AM ET"
        else:
            next_open = f"Tomorrow {MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d} AM ET"
    else:
        status = "open"
        next_open = None

    return {
        "is_open": is_open,
        "status": status,
        "next_open": next_open,
        "current_time_et": now.isoformat(),
    }


def get_current_trading_date(now: Optional[datetime] = None) -> date:
    """
    Get the current trading date.

    If before market open, returns previous trading day.
    If on weekend, returns previous Friday.

    Args:
        now: Optional datetime to check (defaults to current time).

    Returns:
        The current trading date.
    """
    if now is None:
        now = datetime.now(ET)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=ET)

    current_date = now.date()

    # If it's before market open, use previous trading day
    market_open_time = now.replace(
        hour=MARKET_OPEN_HOUR,
        minute=MARKET_OPEN_MINUTE,
        second=0,
        microsecond=0,
    )

    if now < market_open_time:
        current_date -= timedelta(days=1)

    # Adjust for weekends
    while current_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
        current_date -= timedelta(days=1)

    return current_date


class PolygonClient:
    """
    Polygon.io API client for options data.

    Handles rate limiting, retries, and data transformation for
    the GEX calculation engine.
    """

    def __init__(
        self,
        api_key: str,
        tier: str = "free",
        timeout: float = 30.0,
    ):
        """
        Initialize Polygon client.

        Args:
            api_key: Polygon.io API key.
            tier: API tier ('free' or 'paid') for rate limiting.
            timeout: Request timeout in seconds.
        """
        self.api_key = api_key
        self.tier = tier
        self.timeout = timeout

        # Initialize rate limiter based on tier
        rate_limit = POLYGON_FREE_TIER_RATE if tier == "free" else POLYGON_PAID_TIER_RATE
        self._rate_limiter = RateLimiter(calls_per_minute=rate_limit)

        # Initialize REST client
        self._client = RESTClient(api_key=api_key)

        # HTTP client for custom requests
        self._http_client = httpx.AsyncClient(
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

        logger.info(f"Initialized PolygonClient with {tier} tier ({rate_limit} req/min)")

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http_client.aclose()

    async def get_spot_price(self, symbol: str = "SPX") -> float:
        """
        Fetch current spot price for the underlying.

        Args:
            symbol: The underlying symbol (default: SPX).

        Returns:
            Current spot price.

        Raises:
            ValueError: If price cannot be fetched.
        """
        await self._rate_limiter.acquire()

        try:
            # For SPX, we need to use I:SPX (index prefix)
            ticker = f"I:{symbol}" if symbol == "SPX" else symbol

            # Try to get the latest snapshot
            response = await self._http_client.get(
                f"https://api.polygon.io/v2/snapshot/locale/us/markets/indices/{symbol}",
                params={"apiKey": self.api_key},
            )

            if response.status_code == 200:
                data = response.json()
                if "ticker" in data and "value" in data["ticker"]:
                    return float(data["ticker"]["value"])

            # Fallback to aggs endpoint
            response = await self._http_client.get(
                f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev",
                params={"apiKey": self.api_key},
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("results") and len(data["results"]) > 0:
                    return float(data["results"][0]["c"])  # Close price

            raise ValueError(f"Could not fetch spot price for {symbol}")

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching spot price: {e}")
            raise ValueError(f"Failed to fetch spot price: {e}") from e

    async def get_options_chain_snapshot(
        self,
        underlying: str = "SPX",
        expiration_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """
        Fetch options chain snapshot for 0DTE contracts.

        Args:
            underlying: The underlying symbol (default: SPX).
            expiration_date: Optional expiration date (defaults to today).

        Returns:
            DataFrame with options chain data.
        """
        await self._rate_limiter.acquire()

        if expiration_date is None:
            expiration_date = get_current_trading_date()

        try:
            # Build options chain request
            # For SPX, the options ticker prefix is O:SPXW for weeklies, O:SPX for monthlies
            exp_str = expiration_date.strftime("%Y-%m-%d")

            response = await self._http_client.get(
                f"https://api.polygon.io/v3/snapshot/options/{underlying}",
                params={
                    "apiKey": self.api_key,
                    "expiration_date": exp_str,
                    "limit": 250,
                },
            )

            if response.status_code != 200:
                logger.warning(f"Options chain request failed: {response.status_code}")
                return pd.DataFrame()

            data = response.json()
            results = data.get("results", [])

            if not results:
                logger.warning(f"No options data returned for {underlying} expiring {exp_str}")
                return pd.DataFrame()

            # Transform to DataFrame
            options_data = []
            for contract in results:
                details = contract.get("details", {})
                greeks = contract.get("greeks", {})
                day = contract.get("day", {})
                last_quote = contract.get("last_quote", {})

                options_data.append({
                    "symbol": details.get("ticker", ""),
                    "strike": float(details.get("strike_price", 0)),
                    "expiration": details.get("expiration_date"),
                    "type": details.get("contract_type", "").lower(),
                    "bid": float(last_quote.get("bid", 0)),
                    "ask": float(last_quote.get("ask", 0)),
                    "mid": (float(last_quote.get("bid", 0)) + float(last_quote.get("ask", 0))) / 2,
                    "open_interest": int(contract.get("open_interest", 0)),
                    "volume": int(day.get("volume", 0)),
                    "implied_vol": float(greeks.get("implied_volatility", 0)) if greeks.get("implied_volatility") else None,
                    "delta": float(greeks.get("delta", 0)) if greeks.get("delta") else None,
                    "gamma": float(greeks.get("gamma", 0)) if greeks.get("gamma") else None,
                    "vega": float(greeks.get("vega", 0)) if greeks.get("vega") else None,
                    "theta": float(greeks.get("theta", 0)) if greeks.get("theta") else None,
                })

            return pd.DataFrame(options_data)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching options chain: {e}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error processing options chain: {e}")
            return pd.DataFrame()

    def filter_0dte_contracts(
        self,
        df: pd.DataFrame,
        target_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """
        Filter options chain to only include 0DTE contracts.

        Args:
            df: Options chain DataFrame.
            target_date: The target expiration date (defaults to today).

        Returns:
            Filtered DataFrame with only 0DTE contracts.
        """
        if df.empty:
            return df

        if target_date is None:
            target_date = get_current_trading_date()

        # Convert expiration column to date
        df = df.copy()
        df["expiration_date"] = pd.to_datetime(df["expiration"]).dt.date

        # Filter to target date
        mask = df["expiration_date"] == target_date
        filtered_df = df[mask].copy()

        if len(filtered_df) < len(df):
            logger.debug(
                f"Filtered to {len(filtered_df)} 0DTE contracts "
                f"(from {len(df)} total)"
            )

        return filtered_df.drop(columns=["expiration_date"])

    def filter_strike_range(
        self,
        df: pd.DataFrame,
        spot_price: float,
        range_percent: float = STRIKE_RANGE_PERCENT,
    ) -> pd.DataFrame:
        """
        Filter options chain to strikes within range of spot price.

        Removes deep OTM strikes that have minimal gamma exposure.

        Args:
            df: Options chain DataFrame.
            spot_price: Current spot price of underlying.
            range_percent: Percentage range around spot (default: 0.20 = ±20%).

        Returns:
            Filtered DataFrame.
        """
        if df.empty:
            return df

        min_strike = spot_price * (1 - range_percent)
        max_strike = spot_price * (1 + range_percent)

        mask = (df["strike"] >= min_strike) & (df["strike"] <= max_strike)
        filtered_df = df[mask].copy()

        if len(filtered_df) < len(df):
            logger.debug(
                f"Filtered to {len(filtered_df)} strikes within "
                f"±{range_percent*100:.0f}% of spot (from {len(df)})"
            )

        return filtered_df

    def enrich_with_calculated_iv(
        self,
        df: pd.DataFrame,
        spot_price: float,
    ) -> pd.DataFrame:
        """
        Fill in missing implied volatility using mid price if possible.

        This is a fallback for when Polygon doesn't provide IV.

        Args:
            df: Options chain DataFrame.
            spot_price: Current spot price.

        Returns:
            DataFrame with IV filled in where possible.
        """
        if df.empty:
            return df

        df = df.copy()

        # For now, use ATM IV for missing values
        # In production, you would use Newton-Raphson solver
        has_iv = df["implied_vol"].notna() & (df["implied_vol"] > 0)

        if has_iv.sum() > 0:
            # Calculate ATM IV as average of options near spot
            atm_range = spot_price * 0.02  # Within 2% of spot
            atm_mask = has_iv & (df["strike"] - spot_price).abs() < atm_range
            if atm_mask.sum() > 0:
                atm_iv = df.loc[atm_mask, "implied_vol"].mean()
                df.loc[~has_iv, "implied_vol"] = atm_iv
                logger.debug(f"Filled {(~has_iv).sum()} missing IV values with ATM IV: {atm_iv:.4f}")

        return df

    async def get_options_chain_for_gex(
        self,
        underlying: str = "SPX",
    ) -> tuple[pd.DataFrame, float]:
        """
        Get filtered and enriched options chain ready for GEX calculation.

        This is the main entry point for data acquisition.

        Args:
            underlying: The underlying symbol.

        Returns:
            Tuple of (options DataFrame, spot price).
        """
        # Get spot price
        spot_price = await self.get_spot_price(underlying)
        logger.info(f"Got spot price: {spot_price}")

        # Get options chain
        df = await self.get_options_chain_snapshot(underlying)

        if df.empty:
            logger.warning("Empty options chain returned")
            return pd.DataFrame(), spot_price

        # Filter to 0DTE
        df = self.filter_0dte_contracts(df)

        # Filter strike range
        df = self.filter_strike_range(df, spot_price)

        # Enrich with IV if missing
        df = self.enrich_with_calculated_iv(df, spot_price)

        logger.info(f"Prepared {len(df)} contracts for GEX calculation")

        return df, spot_price


class MockPolygonClient:
    """
    Mock Polygon client for testing and development.

    Generates synthetic options chain data for testing the GEX calculator.
    """

    def __init__(self):
        self._spot_price = 5900.0

    async def get_spot_price(self, symbol: str = "SPX") -> float:
        """Return mock spot price."""
        return self._spot_price

    async def get_options_chain_snapshot(
        self,
        underlying: str = "SPX",
        expiration_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Generate mock options chain."""
        spot = self._spot_price
        strikes = list(range(int(spot - 200), int(spot + 200), 10))

        options_data = []
        for strike in strikes:
            for opt_type in ["call", "put"]:
                # Generate realistic-ish data
                moneyness = (spot - strike) / spot
                base_iv = 0.20 + abs(moneyness) * 0.5  # IV smile

                options_data.append({
                    "symbol": f"O:SPX{strike}{opt_type[0].upper()}",
                    "strike": float(strike),
                    "expiration": datetime.now(ET).strftime("%Y-%m-%d"),
                    "type": opt_type,
                    "bid": max(0, (spot - strike if opt_type == "call" else strike - spot) - 5),
                    "ask": max(0, (spot - strike if opt_type == "call" else strike - spot) + 5),
                    "mid": max(0, spot - strike if opt_type == "call" else strike - spot),
                    "open_interest": int(1000 * (1 - abs(moneyness))),  # Higher OI near ATM
                    "volume": int(500 * (1 - abs(moneyness))),
                    "implied_vol": base_iv,
                    "delta": None,
                    "gamma": None,
                    "vega": None,
                    "theta": None,
                })

        return pd.DataFrame(options_data)

    def filter_0dte_contracts(self, df: pd.DataFrame, target_date: Optional[date] = None) -> pd.DataFrame:
        """No-op filter for mock data (all contracts are already 0DTE)."""
        return df

    def filter_strike_range(
        self,
        df: pd.DataFrame,
        spot_price: float,
        range_percent: float = STRIKE_RANGE_PERCENT,
    ) -> pd.DataFrame:
        """Filter mock data by strike range."""
        min_strike = spot_price * (1 - range_percent)
        max_strike = spot_price * (1 + range_percent)
        return df[(df["strike"] >= min_strike) & (df["strike"] <= max_strike)].copy()

    async def get_options_chain_for_gex(
        self,
        underlying: str = "SPX",
    ) -> tuple[pd.DataFrame, float]:
        """Get mock options chain for GEX calculation."""
        spot_price = await self.get_spot_price(underlying)
        df = await self.get_options_chain_snapshot(underlying)
        df = self.filter_strike_range(df, spot_price)
        return df, spot_price

    async def close(self) -> None:
        """No-op close for mock client."""
        pass
