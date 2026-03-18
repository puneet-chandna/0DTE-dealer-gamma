"""0DTE GEX Backend - Data Acquisition Module.

Handles market hours checking, rate limiting utilities, and data
filtering helpers. Data fetching is handled by YFinanceClient.
"""

import asyncio
import logging
from collections import deque
from datetime import datetime, date, timedelta
from time import time
from typing import Optional, Dict, Any
from zoneinfo import ZoneInfo

import pandas as pd

from app.core.constants import (
    MARKET_OPEN_HOUR,
    MARKET_OPEN_MINUTE,
    MARKET_CLOSE_HOUR,
    MARKET_CLOSE_MINUTE,
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


# ---------------------------------------------------------------------------
# NOTE: PolygonClient and MockPolygonClient have been removed.
# Data acquisition is now handled entirely by YFinanceClient
# (see app/core/yfinance_provider.py).
# ---------------------------------------------------------------------------

