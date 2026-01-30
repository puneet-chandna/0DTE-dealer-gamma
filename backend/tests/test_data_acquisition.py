"""0DTE GEX Backend - Data Acquisition Tests.

Tests for rate limiting, market hours, and Polygon.io API client
with mocked HTTP responses.
"""

import asyncio
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
import httpx

from app.core.data_acquisition import (
    RateLimiter,
    is_market_open,
    get_market_status,
    get_current_trading_date,
    PolygonClient,
    MockPolygonClient,
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


class TestIsMarketOpen:
    """Tests for is_market_open function."""

    def test_market_open_during_trading_hours(self):
        """Market should be open during trading hours on weekday."""
        # Wednesday at 10:00 AM ET
        trading_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=ET)
        assert is_market_open(trading_time) is True

    def test_market_closed_before_open(self):
        """Market should be closed before 9:30 AM ET."""
        # Wednesday at 9:00 AM ET
        pre_market = datetime(2025, 1, 15, 9, 0, 0, tzinfo=ET)
        assert is_market_open(pre_market) is False

    def test_market_closed_after_hours(self):
        """Market should be closed after 4:00 PM ET."""
        # Wednesday at 5:00 PM ET
        after_hours = datetime(2025, 1, 15, 17, 0, 0, tzinfo=ET)
        assert is_market_open(after_hours) is False

    def test_market_open_at_930(self):
        """Market should be open exactly at 9:30 AM ET."""
        market_open = datetime(2025, 1, 15, MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE, 0, tzinfo=ET)
        assert is_market_open(market_open) is True

    def test_market_open_at_400(self):
        """Market should still be open at 4:00 PM ET."""
        market_close = datetime(2025, 1, 15, MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE, 0, tzinfo=ET)
        assert is_market_open(market_close) is True

    def test_market_closed_on_saturday(self):
        """Market should be closed on Saturday."""
        # Saturday at noon
        saturday = datetime(2025, 1, 18, 12, 0, 0, tzinfo=ET)
        assert is_market_open(saturday) is False

    def test_market_closed_on_sunday(self):
        """Market should be closed on Sunday."""
        # Sunday at noon
        sunday = datetime(2025, 1, 19, 12, 0, 0, tzinfo=ET)
        assert is_market_open(sunday) is False

    def test_handles_naive_datetime(self):
        """Should handle naive datetime by assuming ET."""
        naive_time = datetime(2025, 1, 15, 10, 0, 0)  # No timezone
        result = is_market_open(naive_time)
        assert result is True


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


class TestPolygonClientFilters:
    """Tests for PolygonClient filter methods."""

    @pytest.fixture
    def sample_options_df(self):
        """Create a sample options DataFrame for testing."""
        return pd.DataFrame({
            "symbol": ["OPT1", "OPT2", "OPT3", "OPT4", "OPT5"],
            "strike": [5700.0, 5800.0, 5900.0, 6000.0, 6100.0],
            "expiration": [
                "2025-01-15",
                "2025-01-15",
                "2025-01-15",
                "2025-01-16",  # Different date
                "2025-01-15",
            ],
            "type": ["call", "put", "call", "call", "put"],
            "open_interest": [100, 200, 300, 400, 500],
            "implied_vol": [0.20, 0.22, 0.25, 0.18, 0.30],
        })

    @pytest.fixture
    def mock_polygon_client(self):
        """Create a mock PolygonClient."""
        with patch.object(PolygonClient, "__init__", lambda self, *args, **kwargs: None):
            client = PolygonClient.__new__(PolygonClient)
            return client

    def test_filter_0dte_contracts(self, sample_options_df, mock_polygon_client):
        """Should filter to only 0DTE contracts."""
        target_date = date(2025, 1, 15)
        result = mock_polygon_client.filter_0dte_contracts(sample_options_df, target_date)
        
        assert len(result) == 4  # OPT4 has different date
        assert "OPT4" not in result["symbol"].values

    def test_filter_0dte_empty_df(self, mock_polygon_client):
        """Should handle empty DataFrame."""
        empty_df = pd.DataFrame()
        result = mock_polygon_client.filter_0dte_contracts(empty_df)
        assert result.empty

    def test_filter_strike_range(self, sample_options_df, mock_polygon_client):
        """Should filter strikes within range of spot."""
        spot_price = 5900.0
        # With 10% range: 5310 to 6490
        result = mock_polygon_client.filter_strike_range(
            sample_options_df, spot_price, range_percent=0.10
        )
        
        # All strikes 5700-6100 are within 10% of 5900
        assert len(result) == 5

    def test_filter_strike_range_narrow(self, sample_options_df, mock_polygon_client):
        """Should filter out strikes outside narrow range."""
        spot_price = 5900.0
        # With 2% range: 5782 to 6018
        result = mock_polygon_client.filter_strike_range(
            sample_options_df, spot_price, range_percent=0.02
        )
        
        # Only 5800, 5900, 6000 are within 2%
        assert len(result) == 3
        assert 5700.0 not in result["strike"].values
        assert 6100.0 not in result["strike"].values

    def test_filter_strike_range_empty_df(self, mock_polygon_client):
        """Should handle empty DataFrame."""
        empty_df = pd.DataFrame()
        result = mock_polygon_client.filter_strike_range(empty_df, 5900.0)
        assert result.empty


class TestMockPolygonClient:
    """Tests for MockPolygonClient."""

    @pytest.mark.asyncio
    async def test_get_spot_price(self):
        """Should return mock spot price."""
        client = MockPolygonClient()
        price = await client.get_spot_price("SPX")
        assert price == 5900.0

    @pytest.mark.asyncio
    async def test_get_options_chain_snapshot(self):
        """Should generate mock options chain."""
        client = MockPolygonClient()
        df = await client.get_options_chain_snapshot("SPX")
        
        assert not df.empty
        assert "strike" in df.columns
        assert "type" in df.columns
        assert "open_interest" in df.columns
        assert "implied_vol" in df.columns

    @pytest.mark.asyncio
    async def test_options_chain_has_calls_and_puts(self):
        """Mock chain should have both calls and puts."""
        client = MockPolygonClient()
        df = await client.get_options_chain_snapshot("SPX")
        
        assert "call" in df["type"].values
        assert "put" in df["type"].values

    @pytest.mark.asyncio
    async def test_filter_strike_range(self):
        """Should filter strikes within range."""
        client = MockPolygonClient()
        df = await client.get_options_chain_snapshot("SPX")
        spot = await client.get_spot_price("SPX")
        
        filtered = client.filter_strike_range(df, spot, range_percent=0.10)
        
        min_strike = spot * 0.9
        max_strike = spot * 1.1
        assert all(filtered["strike"] >= min_strike)
        assert all(filtered["strike"] <= max_strike)

    @pytest.mark.asyncio
    async def test_get_options_chain_for_gex(self):
        """Should return filtered chain and spot price."""
        client = MockPolygonClient()
        df, spot = await client.get_options_chain_for_gex("SPX")
        
        assert not df.empty
        assert spot == 5900.0

    @pytest.mark.asyncio
    async def test_close_is_noop(self):
        """Close should not raise."""
        client = MockPolygonClient()
        await client.close()  # Should not raise


class TestPolygonClientAPI:
    """Tests for PolygonClient API methods with mocked HTTP."""

    @pytest.fixture
    def mock_http_client(self):
        """Create a mock HTTP client."""
        return AsyncMock(spec=httpx.AsyncClient)

    @pytest.mark.asyncio
    async def test_get_spot_price_from_snapshot(self, mock_http_client):
        """Should extract spot price from snapshot response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ticker": {"value": 5925.50}
        }
        mock_http_client.get = AsyncMock(return_value=mock_response)

        with patch.object(PolygonClient, "__init__", lambda self, *args, **kwargs: None):
            client = PolygonClient.__new__(PolygonClient)
            client._http_client = mock_http_client
            client._rate_limiter = AsyncMock()
            client._rate_limiter.acquire = AsyncMock()
            client.api_key = "test_key"

            price = await client.get_spot_price("SPX")
            assert price == 5925.50

    @pytest.mark.asyncio
    async def test_get_spot_price_fallback_to_aggs(self, mock_http_client):
        """Should fallback to aggs endpoint if snapshot fails."""
        # First call returns no value
        mock_response_1 = MagicMock()
        mock_response_1.status_code = 200
        mock_response_1.json.return_value = {}

        # Second call returns aggs data
        mock_response_2 = MagicMock()
        mock_response_2.status_code = 200
        mock_response_2.json.return_value = {
            "results": [{"c": 5920.00}]
        }

        mock_http_client.get = AsyncMock(side_effect=[mock_response_1, mock_response_2])

        with patch.object(PolygonClient, "__init__", lambda self, *args, **kwargs: None):
            client = PolygonClient.__new__(PolygonClient)
            client._http_client = mock_http_client
            client._rate_limiter = AsyncMock()
            client._rate_limiter.acquire = AsyncMock()
            client.api_key = "test_key"

            price = await client.get_spot_price("SPX")
            assert price == 5920.00

    @pytest.mark.asyncio
    async def test_get_spot_price_raises_on_failure(self, mock_http_client):
        """Should raise ValueError if price cannot be fetched."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_http_client.get = AsyncMock(return_value=mock_response)

        with patch.object(PolygonClient, "__init__", lambda self, *args, **kwargs: None):
            client = PolygonClient.__new__(PolygonClient)
            client._http_client = mock_http_client
            client._rate_limiter = AsyncMock()
            client._rate_limiter.acquire = AsyncMock()
            client.api_key = "test_key"

            with pytest.raises(ValueError, match="Could not fetch spot price"):
                await client.get_spot_price("SPX")

    @pytest.mark.asyncio
    async def test_get_options_chain_empty_on_error(self, mock_http_client):
        """Should return empty DataFrame on API error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_http_client.get = AsyncMock(return_value=mock_response)

        with patch.object(PolygonClient, "__init__", lambda self, *args, **kwargs: None):
            client = PolygonClient.__new__(PolygonClient)
            client._http_client = mock_http_client
            client._rate_limiter = AsyncMock()
            client._rate_limiter.acquire = AsyncMock()
            client.api_key = "test_key"

            df = await client.get_options_chain_snapshot("SPX")
            assert df.empty

    @pytest.mark.asyncio
    async def test_get_options_chain_parses_results(self, mock_http_client):
        """Should correctly parse options chain response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "details": {
                        "ticker": "O:SPX250115C05900000",
                        "strike_price": 5900,
                        "expiration_date": "2025-01-15",
                        "contract_type": "call",
                    },
                    "greeks": {
                        "implied_volatility": 0.20,
                        "delta": 0.5,
                        "gamma": 0.001,
                    },
                    "day": {"volume": 1000},
                    "last_quote": {"bid": 10.0, "ask": 12.0},
                    "open_interest": 5000,
                }
            ]
        }
        mock_http_client.get = AsyncMock(return_value=mock_response)

        with patch.object(PolygonClient, "__init__", lambda self, *args, **kwargs: None):
            client = PolygonClient.__new__(PolygonClient)
            client._http_client = mock_http_client
            client._rate_limiter = AsyncMock()
            client._rate_limiter.acquire = AsyncMock()
            client.api_key = "test_key"

            df = await client.get_options_chain_snapshot("SPX")

            assert len(df) == 1
            assert df.iloc[0]["strike"] == 5900.0
            assert df.iloc[0]["type"] == "call"
            assert df.iloc[0]["open_interest"] == 5000
            assert df.iloc[0]["implied_vol"] == 0.20


class TestEnrichWithCalculatedIV:
    """Tests for IV enrichment function."""

    @pytest.fixture
    def mock_polygon_client(self):
        """Create a mock PolygonClient."""
        with patch.object(PolygonClient, "__init__", lambda self, *args, **kwargs: None):
            client = PolygonClient.__new__(PolygonClient)
            return client

    def test_fills_missing_iv_with_atm(self, mock_polygon_client):
        """Should fill missing IV with ATM average."""
        df = pd.DataFrame({
            "strike": [5880.0, 5900.0, 5920.0, 5940.0],
            "implied_vol": [0.20, None, 0.22, None],
        })

        spot_price = 5900.0
        result = mock_polygon_client.enrich_with_calculated_iv(df, spot_price)

        # Missing IVs should be filled with ATM average
        assert result["implied_vol"].notna().all()

    def test_handles_empty_df(self, mock_polygon_client):
        """Should handle empty DataFrame."""
        empty_df = pd.DataFrame()
        result = mock_polygon_client.enrich_with_calculated_iv(empty_df, 5900.0)
        assert result.empty

    def test_no_changes_when_all_iv_present(self, mock_polygon_client):
        """Should not modify when all IV values are present."""
        df = pd.DataFrame({
            "strike": [5880.0, 5900.0, 5920.0],
            "implied_vol": [0.20, 0.21, 0.22],
        })

        spot_price = 5900.0
        result = mock_polygon_client.enrich_with_calculated_iv(df, spot_price)

        assert result["implied_vol"].tolist() == [0.20, 0.21, 0.22]
