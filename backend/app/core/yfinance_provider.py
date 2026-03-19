"""0DTE GEX Backend - YFinance Data Provider.

Alternative data provider using Yahoo Finance via yfinance library.
Provides free real-time options chain data for SPX/SPY options.
"""

import asyncio
import logging
from datetime import datetime, date
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from app.core.base_provider import DataProvider
from app.core.constants import STRIKE_RANGE_PERCENT
from app.core.data_acquisition import (
    RateLimiter,
    get_current_trading_date,
)

logger = logging.getLogger(__name__)

# Eastern Time timezone
ET = ZoneInfo("America/New_York")


class YFinanceClient(DataProvider):
    """
    Yahoo Finance API client for options data via yfinance library.

    Provides free real-time options chain data. Note that yfinance is an
    unofficial API and may be subject to rate limiting or changes.

    Key characteristics:
    - Greeks are NOT provided by yfinance (must be calculated separately)
    - Uses SPY as proxy for SPX (SPX options not available on Yahoo)
    - No historical options data available
    - No API key required (free)
    """

    # ---- DataProvider metadata ----
    provider_name = "yfinance"
    display_name = "Yahoo Finance"
    provides_greeks = False
    supports_spx_directly = False
    rate_limit = 10
    requires_api_key = False
    
    # SPY is used as proxy since SPX options aren't on Yahoo Finance
    # SPY tracks S&P 500 at ~1/10th the price
    SPY_TO_SPX_RATIO = 10.0
    
    def __init__(
        self,
        calls_per_minute: int = 5,
        use_spy_as_proxy: bool = True,
    ):
        """
        Initialize YFinance client.
        
        Args:
            calls_per_minute: Rate limit for API calls (conservative default).
            use_spy_as_proxy: If True, use SPY options as proxy for SPX.
        """
        self._rate_limiter = RateLimiter(calls_per_minute=calls_per_minute)
        self.use_spy_as_proxy = use_spy_as_proxy
        
        logger.info(
            f"Initialized YFinanceClient with {calls_per_minute} req/min, "
            f"SPY proxy: {use_spy_as_proxy}"
        )
    
    @staticmethod
    def _safe_int(value) -> int:
        """Safely convert a value to int, handling NaN and None."""
        if value is None or pd.isna(value):
            return 0
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0
    
    @staticmethod
    def _safe_float(value) -> float:
        """Safely convert a value to float, handling NaN and None."""
        if value is None or pd.isna(value):
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    
    def _get_ticker_symbol(self, underlying: str) -> str:
        """
        Get the appropriate ticker symbol for yfinance.
        
        Args:
            underlying: The underlying symbol (e.g., 'SPX', 'SPY').
            
        Returns:
            The ticker symbol to use with yfinance.
        """
        if underlying.upper() == "SPX" and self.use_spy_as_proxy:
            return "SPY"
        return underlying.upper()
    
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
        
        ticker_symbol = self._get_ticker_symbol(symbol)
        
        try:
            # Run yfinance in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            ticker = await loop.run_in_executor(
                None, yf.Ticker, ticker_symbol
            )
            
            # Get current price from fast_info or history
            info = await loop.run_in_executor(
                None, lambda: ticker.fast_info
            )
            
            price = info.get("lastPrice") or info.get("regularMarketPrice")
            
            if price is None:
                # Fallback to history
                hist = await loop.run_in_executor(
                    None, lambda: ticker.history(period="1d")
                )
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])
            
            if price is None:
                raise ValueError(f"Could not fetch spot price for {ticker_symbol}")
            
            # Convert SPY to SPX equivalent if needed
            if symbol.upper() == "SPX" and ticker_symbol == "SPY":
                price *= self.SPY_TO_SPX_RATIO
                logger.debug(f"Converted SPY price to SPX equivalent: {price}")
            
            logger.info(f"Got spot price for {symbol}: {price}")
            return float(price)
            
        except Exception as e:
            logger.error(f"Error fetching spot price for {symbol}: {e}")
            raise ValueError(f"Failed to fetch spot price: {e}") from e
    
    async def get_expirations(self, underlying: str = "SPX") -> list[str]:
        """
        Get available expiration dates for options.
        
        Args:
            underlying: The underlying symbol.
            
        Returns:
            List of expiration dates as strings (YYYY-MM-DD).
        """
        await self._rate_limiter.acquire()
        
        ticker_symbol = self._get_ticker_symbol(underlying)
        
        try:
            loop = asyncio.get_event_loop()
            ticker = await loop.run_in_executor(
                None, yf.Ticker, ticker_symbol
            )
            
            expirations = await loop.run_in_executor(
                None, lambda: ticker.options
            )
            
            logger.debug(f"Available expirations for {ticker_symbol}: {expirations}")
            return list(expirations)
            
        except Exception as e:
            logger.error(f"Error fetching expirations: {e}")
            return []
    
    async def get_options_chain_snapshot(
        self,
        underlying: str = "SPX",
        expiration_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """
        Fetch options chain snapshot.
        
        Args:
            underlying: The underlying symbol (default: SPX).
            expiration_date: Optional expiration date (defaults to nearest 0DTE).
            
        Returns:
            DataFrame with options chain data.
        """
        await self._rate_limiter.acquire()
        
        ticker_symbol = self._get_ticker_symbol(underlying)
        
        if expiration_date is None:
            expiration_date = get_current_trading_date()
        
        exp_str = expiration_date.strftime("%Y-%m-%d")
        
        try:
            loop = asyncio.get_event_loop()
            ticker = await loop.run_in_executor(
                None, yf.Ticker, ticker_symbol
            )
            
            # Get available expirations
            expirations = await loop.run_in_executor(
                None, lambda: ticker.options
            )
            
            if not expirations:
                logger.warning(f"No expirations available for {ticker_symbol}")
                return pd.DataFrame()
            
            # Find the closest expiration to target date
            target_exp = exp_str
            if exp_str not in expirations:
                # Find nearest expiration
                exp_dates = [datetime.strptime(e, "%Y-%m-%d").date() for e in expirations]
                closest = min(exp_dates, key=lambda x: abs((x - expiration_date).days))
                target_exp = closest.strftime("%Y-%m-%d")
                logger.info(f"Target expiration {exp_str} not available, using {target_exp}")
            
            # Fetch options chain
            chain = await loop.run_in_executor(
                None, lambda: ticker.option_chain(target_exp)
            )
            
            # Combine calls and puts into single DataFrame
            calls_df = chain.calls.copy()
            calls_df["type"] = "call"
            
            puts_df = chain.puts.copy()
            puts_df["type"] = "put"
            
            combined = pd.concat([calls_df, puts_df], ignore_index=True)
            
            if combined.empty:
                logger.warning(f"Empty options chain for {ticker_symbol} exp {target_exp}")
                return pd.DataFrame()
            
            # Transform to standard format
            options_data = []
            for _, row in combined.iterrows():
                strike = float(row.get("strike", 0))
                
                # Convert SPY strikes to SPX equivalent if using proxy
                if underlying.upper() == "SPX" and ticker_symbol == "SPY":
                    strike *= self.SPY_TO_SPX_RATIO
                
                bid = float(row.get("bid", 0) or 0)
                ask = float(row.get("ask", 0) or 0)
                
                # Convert option prices to SPX equivalent if using proxy
                if underlying.upper() == "SPX" and ticker_symbol == "SPY":
                    bid *= self.SPY_TO_SPX_RATIO
                    ask *= self.SPY_TO_SPX_RATIO
                
                options_data.append({
                    "symbol": row.get("contractSymbol", ""),
                    "strike": strike,
                    "expiration": target_exp,
                    "type": row["type"],
                    "bid": bid,
                    "ask": ask,
                    "mid": (bid + ask) / 2 if (bid + ask) > 0 else 0,
                    "open_interest": self._safe_int(row.get("openInterest")),
                    "volume": self._safe_int(row.get("volume")),
                    # yfinance provides IV but not other Greeks
                    "implied_vol": self._safe_float(row.get("impliedVolatility")),
                    "delta": None,  # Must be calculated
                    "gamma": None,  # Must be calculated
                    "vega": None,   # Must be calculated
                    "theta": None,  # Must be calculated
                })
            
            df = pd.DataFrame(options_data)
            logger.info(f"Fetched {len(df)} contracts for {underlying} exp {target_exp}")
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching options chain: {e}")
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
    
    async def get_options_chain_for_gex(
        self,
        underlying: str = "SPX",
    ) -> tuple[pd.DataFrame, float]:
        """
        Get filtered options chain ready for GEX calculation.
        
        This is the main entry point for data acquisition.
        Note: Greeks must be calculated separately as yfinance doesn't provide them.
        
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
        
        logger.info(f"Prepared {len(df)} contracts for GEX calculation")
        
        return df, spot_price
    
    async def close(self) -> None:
        """Close the client (no-op for yfinance)."""
        pass
