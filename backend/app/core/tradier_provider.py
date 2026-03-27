"""0DTE GEX Backend - Tradier Data Provider.

Production-grade data provider using the Tradier brokerage API.
Provides real SPX/SPXW options chains with ORATS-sourced Greeks.

Official docs: https://docs.tradier.com/reference
"""

import asyncio
import logging
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

from app.core.base_provider import DataProvider
from app.core.constants import STRIKE_RANGE_PERCENT
from app.core.data_acquisition import (
    RateLimiter,
    get_current_trading_date,
)

logger = logging.getLogger(__name__)

# Eastern Time timezone
ET = ZoneInfo("America/New_York")


class TradierClient(DataProvider):
    """Tradier brokerage API client for options data.

    Key advantages over YFinance:
    - Real SPX / SPXW options chains (no SPY proxy)
    - ORATS-sourced Greeks (delta, gamma, theta, vega, rho, phi)
    - Multiple IV values (bid_iv, mid_iv, ask_iv, smv_vol)
    - Up to 120 requests/minute in production (60/minute in sandbox)
    - Production-quality data

    Requires a Tradier API key (production or sandbox).
    """

    # ---- DataProvider metadata ----
    provider_name = "tradier"
    display_name = "Tradier"
    provides_greeks = True
    supports_spx_directly = True
    rate_limit = 120
    requires_api_key = True

    # ---- Tradier defaults ----
    DEFAULT_BASE_URL = "https://api.tradier.com/v1"

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        calls_per_minute: int = 120,
    ) -> None:
        """Initialise the Tradier client.

        Args:
            api_key: Tradier production or sandbox bearer token.
            base_url: API base URL (override for sandbox).
            calls_per_minute: Rate-limit ceiling.

        Raises:
            ValueError: If *api_key* is empty.
        """
        if not api_key:
            raise ValueError("Tradier API key is required")

        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._rate_limiter = RateLimiter(calls_per_minute=calls_per_minute)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

        logger.info(
            f"Initialised TradierClient @ {self._base_url} "
            f"({calls_per_minute} req/min)"
        )

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _safe_float(value) -> float:
        """Safely convert a value to float, handling None / NaN."""
        if value is None:
            return 0.0
        try:
            f = float(value)
            return 0.0 if f != f else f  # NaN check
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _safe_int(value) -> int:
        """Safely convert a value to int, handling None / NaN."""
        if value is None:
            return 0
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    async def _request(self, path: str, params: dict | None = None) -> dict:
        """Make a rate-limited GET request to the Tradier API.

        Args:
            path: API path (e.g. ``/markets/quotes``).
            params: Query-string parameters.

        Returns:
            Parsed JSON response body.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        await self._rate_limiter.acquire()

        response = await self._client.get(path, params=params)
        response.raise_for_status()

        # Log rate-limit headers when present
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            logger.debug(f"Tradier rate-limit remaining: {remaining}")

        return response.json()

    # ------------------------------------------------------------------ #
    #  DataProvider interface                                              #
    # ------------------------------------------------------------------ #

    async def get_spot_price(self, symbol: str = "SPX") -> float:
        """Fetch the current spot price via Tradier quotes endpoint.

        Uses ``/markets/quotes`` with the provided symbol.  For index
        symbols such as ``SPX`` Tradier may return the index value under
        the ``last`` field; if that is ``None`` we fall back to the
        ``close`` or ``prevclose`` field.
        """
        data = await self._request(
            "/markets/quotes",
            params={"symbols": symbol.upper(), "greeks": "false"},
        )

        quotes = data.get("quotes", {})
        quote = quotes.get("quote")

        # Tradier responses can flip between an object and a list depending
        # on symbol count, so normalize the single-symbol shape here.
        if isinstance(quote, list):
            quote = quote[0] if quote else {}
        if quote is None:
            quote = {}

        price = (
            quote.get("last")
            or quote.get("close")
            or quote.get("prevclose")
        )

        if price is None:
            raise ValueError(
                f"Could not extract spot price for {symbol} from Tradier"
            )

        price = float(price)
        logger.info(f"Tradier spot price for {symbol}: {price}")
        return price

    async def get_expirations(self, underlying: str = "SPX") -> list[str]:
        """Fetch available option expiration dates."""
        data = await self._request(
            "/markets/options/expirations",
            params={
                "symbol": underlying.upper(),
                "includeAllRoots": "true",
            },
        )

        expirations = data.get("expirations", {})
        dates = expirations.get("date", [])

        if isinstance(dates, str):
            dates = [dates]

        logger.debug(
            f"Tradier expirations for {underlying}: {len(dates)} dates"
        )
        return dates

    async def get_options_chain_snapshot(
        self,
        underlying: str = "SPX",
        expiration_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Fetch the options chain with Greeks for a given expiration.

        Returns a DataFrame with the standard column layout expected by
        the GEX calculator.
        """
        if expiration_date is None:
            expiration_date = get_current_trading_date()

        exp_str = expiration_date.strftime("%Y-%m-%d")

        # Check available expirations and find closest
        expirations = await self.get_expirations(underlying)
        if not expirations:
            logger.warning(f"No expirations for {underlying} on Tradier")
            return pd.DataFrame()

        target_exp = exp_str
        if exp_str not in expirations:
            exp_dates = [
                datetime.strptime(e, "%Y-%m-%d").date()
                for e in expirations
            ]
            closest = min(
                exp_dates,
                key=lambda x: abs((x - expiration_date).days),
            )
            target_exp = closest.strftime("%Y-%m-%d")
            logger.info(
                f"Target expiration {exp_str} not available, "
                f"using {target_exp}"
            )

        # Fetch chain with Greeks
        data = await self._request(
            "/markets/options/chains",
            params={
                "symbol": underlying.upper(),
                "expiration": target_exp,
                "greeks": "true",
            },
        )

        options_raw = data.get("options", {})
        option_list = options_raw.get("option", [])

        if not option_list:
            logger.warning(
                f"Empty chain for {underlying} exp {target_exp}"
            )
            return pd.DataFrame()

        # Tradier returns a dict for a single contract and a list for
        # multiple contracts, so normalize the payload before mapping.
        if isinstance(option_list, dict):
            option_list = [option_list]

        # ---- Map to standard DataFrame ----
        rows: list[dict] = []
        for opt in option_list:
            greeks = opt.get("greeks") or {}

            rows.append(
                {
                    "symbol": opt.get("symbol", ""),
                    "strike": self._safe_float(opt.get("strike")),
                    "expiration": opt.get("expiration_date", target_exp),
                    "type": (
                        "call"
                        if opt.get("option_type", "").lower() == "call"
                        else "put"
                    ),
                    "bid": self._safe_float(opt.get("bid")),
                    "ask": self._safe_float(opt.get("ask")),
                    "mid": (
                        self._safe_float(opt.get("bid"))
                        + self._safe_float(opt.get("ask"))
                    )
                    / 2,
                    "open_interest": self._safe_int(
                        opt.get("open_interest")
                    ),
                    "volume": self._safe_int(opt.get("volume")),
                    # Tradier serves ORATS Greeks directly
                    "implied_vol": self._safe_float(
                        greeks.get("mid_iv")
                    ),
                    "delta": self._safe_float(greeks.get("delta"))
                    if greeks.get("delta") is not None
                    else None,
                    "gamma": self._safe_float(greeks.get("gamma"))
                    if greeks.get("gamma") is not None
                    else None,
                    "vega": self._safe_float(greeks.get("vega"))
                    if greeks.get("vega") is not None
                    else None,
                    "theta": self._safe_float(greeks.get("theta"))
                    if greeks.get("theta") is not None
                    else None,
                }
            )

        df = pd.DataFrame(rows)
        logger.info(
            f"Tradier: fetched {len(df)} contracts for "
            f"{underlying} exp {target_exp}"
        )
        return df

    # ---- Filtering helpers (shared logic) ----

    def filter_0dte_contracts(
        self,
        df: pd.DataFrame,
        target_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Keep only contracts expiring on *target_date* (0DTE)."""
        if df.empty:
            return df

        if target_date is None:
            target_date = get_current_trading_date()

        df = df.copy()
        df["expiration_date"] = pd.to_datetime(df["expiration"]).dt.date

        mask = df["expiration_date"] == target_date
        filtered = df[mask].copy()

        if len(filtered) < len(df):
            logger.debug(
                f"Filtered to {len(filtered)} 0DTE contracts "
                f"(from {len(df)})"
            )

        return filtered.drop(columns=["expiration_date"])

    def filter_strike_range(
        self,
        df: pd.DataFrame,
        spot_price: float,
        range_percent: float = STRIKE_RANGE_PERCENT,
    ) -> pd.DataFrame:
        """Keep only strikes within ±*range_percent* of *spot_price*."""
        if df.empty:
            return df

        lo = spot_price * (1 - range_percent)
        hi = spot_price * (1 + range_percent)

        mask = (df["strike"] >= lo) & (df["strike"] <= hi)
        filtered = df[mask].copy()

        if len(filtered) < len(df):
            logger.debug(
                f"Filtered to {len(filtered)} strikes within "
                f"±{range_percent * 100:.0f}% of spot (from {len(df)})"
            )

        return filtered

    async def get_options_chain_for_gex(
        self,
        underlying: str = "SPX",
    ) -> tuple[pd.DataFrame, float]:
        """Filtered options chain ready for GEX calculation.

        Because Tradier supports SPX directly there is no need for a SPY
        proxy conversion.
        """
        spot_price, df = await asyncio.gather(
            self.get_spot_price(underlying),
            self.get_options_chain_snapshot(underlying),
        )
        logger.info(f"Tradier spot price: {spot_price}")

        if df.empty:
            logger.warning("Empty options chain from Tradier")
            return pd.DataFrame(), spot_price

        df = self.filter_0dte_contracts(df)
        df = self.filter_strike_range(df, spot_price)

        logger.info(f"Prepared {len(df)} contracts for GEX calculation")
        return df, spot_price

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
        logger.info("TradierClient closed")
