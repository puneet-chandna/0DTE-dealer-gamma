"""0DTE GEX Backend - Data Acquisition Tests.

Tests for market-hours utilities, rate limiting, and data-filtering
helpers. Polygon-specific tests removed (Polygon client retired).
"""

import asyncio
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.core.data_acquisition import (
    RateLimiter,
    is_market_open,
    get_market_status,
    get_current_trading_date,
    ET,
)
from app.core.constants import (
    MARKET_OPEN_HOUR,
    MARKET_OPEN_MINUTE,
    MARKET_CLOSE_HOUR,
    MARKET_CLOSE_MINUTE,
    STRIKE_RANGE_PERCENT,
)


class TestRateLimiter:
    """Tests for the RateLimiter class."""

    @pytest.mark.asyncio
    async def test_initial_remaining_calls(self):
        """Initial remaining calls should equal max calls per minute."""
        limiter = RateLimiter(calls_per_minute=5)
        assert limiter.remaining_calls == 5

    @pytest.mark.asyncio
    async def test_acquire_decrements_remaining(self):
        """Acquiring should decrement remaining calls."""
        limiter = RateLimiter(calls_per_minute=5)
        await limiter.acquire()
        assert limiter.remaining_calls == 4

    @pytest.mark.asyncio
    async def test_reset_clears_call_times(self):
        """Reset should clear all tracked call times."""
        limiter = RateLimiter(calls_per_minute=5)
        await limiter.acquire()
        await limiter.acquire()
        assert limiter.remaining_calls == 3

        limiter.reset()
        assert limiter.remaining_calls == 5

    @pytest.mark.asyncio
    async def test_multiple_acquires(self):
        """Multiple acquires should track correctly."""
        limiter = RateLimiter(calls_per_minute=10)
        for _ in range(5):
            await limiter.acquire()
        assert limiter.remaining_calls == 5

    @pytest.mark.asyncio
    async def test_min_interval_calculation(self):
        """Min interval should be correctly calculated."""
        limiter = RateLimiter(calls_per_minute=60)
        assert limiter.min_interval == 1.0  # 60s / 60 calls = 1s

        limiter5 = RateLimiter(calls_per_minute=5)
        assert limiter5.min_interval == 12.0  # 60s / 5 calls = 12s

    @pytest.mark.asyncio
    async def test_remaining_calls_respects_window(self):
        """remaining_calls should count only last 60 seconds."""
        limiter = RateLimiter(calls_per_minute=3)
        await limiter.acquire()
        await limiter.acquire()
        assert limiter.remaining_calls == 1

    def test_lock_is_asyncio_lock(self):
        """Internal lock should be an asyncio.Lock."""
        limiter = RateLimiter(calls_per_minute=5)
        assert isinstance(limiter._lock, asyncio.locks.Lock)


class TestIsMarketOpen:
    """Tests for is_market_open function."""

    def test_market_open_during_trading_hours(self):
        """Market should be open during trading hours on weekday."""
        trading_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=ET)
        assert is_market_open(trading_time) is True

    def test_market_closed_before_open(self):
        """Market should be closed before 9:30 AM ET."""
        pre_market = datetime(2025, 1, 15, 9, 0, 0, tzinfo=ET)
        assert is_market_open(pre_market) is False

    def test_market_closed_after_hours(self):
        """Market should be closed after 4:00 PM ET."""
        after_hours = datetime(2025, 1, 15, 17, 0, 0, tzinfo=ET)
        assert is_market_open(after_hours) is False

    def test_market_open_at_930(self):
        """Market should be open exactly at 9:30 AM ET."""
        market_open = datetime(
            2025, 1, 15, MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE, 0, tzinfo=ET
        )
        assert is_market_open(market_open) is True

    def test_market_open_at_400(self):
        """Market should still be open at 4:00 PM ET."""
        market_close = datetime(
            2025, 1, 15, MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE, 0, tzinfo=ET
        )
        assert is_market_open(market_close) is True

    def test_market_closed_on_saturday(self):
        """Market should be closed on Saturday."""
        saturday = datetime(2025, 1, 18, 12, 0, 0, tzinfo=ET)
        assert is_market_open(saturday) is False

    def test_market_closed_on_sunday(self):
        """Market should be closed on Sunday."""
        sunday = datetime(2025, 1, 19, 12, 0, 0, tzinfo=ET)
        assert is_market_open(sunday) is False

    def test_handles_naive_datetime(self):
        """Should handle naive datetime by assuming ET."""
        naive_time = datetime(2025, 1, 15, 10, 0, 0)  # No timezone
        result = is_market_open(naive_time)
        assert result is True

    def test_exactly_at_close_still_open(self):
        """At 16:00:00 exactly the market should still be considered open."""
        at_close = datetime(2025, 1, 15, 16, 0, 0, tzinfo=ET)
        assert is_market_open(at_close) is True

    def test_one_second_after_close_is_closed(self):
        """At 16:00:01 the market should be closed."""
        after_close = datetime(2025, 1, 15, 16, 0, 1, tzinfo=ET)
        assert is_market_open(after_close) is False


class TestGetMarketStatus:
    """Tests for get_market_status function."""

    def test_open_status_during_trading(self):
        """Should return 'open' status during trading hours."""
        trading_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=ET)
        status = get_market_status(trading_time)

        assert status["is_open"] is True
        assert status["status"] == "open"
        assert status["next_open"] is None

    def test_pre_market_status(self):
        """Should return 'pre_market' status before market open."""
        pre_market = datetime(2025, 1, 15, 8, 0, 0, tzinfo=ET)
        status = get_market_status(pre_market)

        assert status["is_open"] is False
        assert status["status"] == "pre_market"
        assert "Today" in status["next_open"]

    def test_after_hours_status(self):
        """Should return 'after_hours' status after market close."""
        after_hours = datetime(2025, 1, 15, 18, 0, 0, tzinfo=ET)
        status = get_market_status(after_hours)

        assert status["is_open"] is False
        assert status["status"] == "after_hours"
        assert "Tomorrow" in status["next_open"]

    def test_after_hours_friday(self):
        """Friday after hours should show Monday as next open."""
        friday_evening = datetime(2025, 1, 17, 18, 0, 0, tzinfo=ET)
        status = get_market_status(friday_evening)

        assert status["status"] == "after_hours"
        assert "Monday" in status["next_open"]

    def test_weekend_status(self):
        """Should return 'closed_weekend' status on weekend."""
        saturday = datetime(2025, 1, 18, 12, 0, 0, tzinfo=ET)
        status = get_market_status(saturday)

        assert status["is_open"] is False
        assert status["status"] == "closed_weekend"
        assert "Monday" in status["next_open"]

    def test_current_time_in_response(self):
        """Response should include current time in ET."""
        trading_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=ET)
        status = get_market_status(trading_time)

        assert "current_time_et" in status
        assert "2025-01-15" in status["current_time_et"]

    def test_response_has_all_required_keys(self):
        """Response dict must always contain all required keys."""
        trading_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=ET)
        status = get_market_status(trading_time)
        required = {"is_open", "status", "next_open", "current_time_et"}
        assert required.issubset(status.keys())

    def test_handles_naive_datetime(self):
        """Should accept naive datetimes."""
        naive = datetime(2025, 1, 15, 10, 0, 0)
        status = get_market_status(naive)
        assert "is_open" in status


class TestGetCurrentTradingDate:
    """Tests for get_current_trading_date function."""

    def test_during_market_hours(self):
        """During market hours, should return today."""
        trading_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=ET)
        result = get_current_trading_date(trading_time)
        assert result == date(2025, 1, 15)

    def test_before_market_open(self):
        """Before market open, should return previous trading day."""
        pre_market = datetime(2025, 1, 15, 8, 0, 0, tzinfo=ET)
        result = get_current_trading_date(pre_market)
        assert result == date(2025, 1, 14)

    def test_saturday_returns_friday(self):
        """Saturday should return Friday."""
        saturday = datetime(2025, 1, 18, 12, 0, 0, tzinfo=ET)
        result = get_current_trading_date(saturday)
        assert result == date(2025, 1, 17)

    def test_sunday_returns_friday(self):
        """Sunday should return Friday."""
        sunday = datetime(2025, 1, 19, 12, 0, 0, tzinfo=ET)
        result = get_current_trading_date(sunday)
        assert result == date(2025, 1, 17)

    def test_monday_before_open_returns_friday(self):
        """Monday before market open should return Friday."""
        monday_early = datetime(2025, 1, 20, 7, 0, 0, tzinfo=ET)
        result = get_current_trading_date(monday_early)
        assert result == date(2025, 1, 17)

    def test_returns_date_not_datetime(self):
        """Result should be a date object, not datetime."""
        trading_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=ET)
        result = get_current_trading_date(trading_time)
        assert isinstance(result, date)
        assert not isinstance(result, datetime)
