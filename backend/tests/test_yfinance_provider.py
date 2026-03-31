"""Tests for YFinance data provider."""

from datetime import date

import pandas as pd
import pytest

from app.core.yfinance_provider import YFinanceClient


class TestYFinanceClient:
    """Tests for YFinanceClient."""

    @pytest.fixture
    def client(self):
        """Create a YFinanceClient instance."""
        return YFinanceClient(calls_per_minute=60)  # Higher limit for testing

    def test_init(self, client):
        """Test client initialization."""
        assert client.use_spy_as_proxy is True
        assert client.SPY_TO_SPX_RATIO == 10.0

    def test_get_ticker_symbol_spx(self, client):
        """Test SPX is converted to SPY when proxy is enabled."""
        assert client._get_ticker_symbol("SPX") == "SPY"
        assert client._get_ticker_symbol("spx") == "SPY"

    def test_get_ticker_symbol_spy(self, client):
        """Test SPY remains SPY."""
        assert client._get_ticker_symbol("SPY") == "SPY"

    def test_get_ticker_symbol_other(self, client):
        """Test other symbols are passed through."""
        assert client._get_ticker_symbol("AAPL") == "AAPL"
        assert client._get_ticker_symbol("qqq") == "QQQ"

    def test_get_ticker_symbol_no_proxy(self):
        """Test SPX remains SPX when proxy is disabled."""
        client = YFinanceClient(use_spy_as_proxy=False)
        assert client._get_ticker_symbol("SPX") == "SPX"


class TestYFinanceClientFilters:
    """Tests for YFinanceClient filter methods."""

    @pytest.fixture
    def sample_options_df(self):
        """Create sample options data."""
        return pd.DataFrame({
            "symbol": ["O:SPY250131C500", "O:SPY250131P500", "O:SPY250131C510"],
            "strike": [5000.0, 5000.0, 5100.0],
            "expiration": ["2025-01-31", "2025-01-31", "2025-01-31"],
            "type": ["call", "put", "call"],
            "bid": [10.0, 8.0, 5.0],
            "ask": [11.0, 9.0, 6.0],
            "mid": [10.5, 8.5, 5.5],
            "open_interest": [1000, 800, 500],
            "volume": [100, 80, 50],
            "implied_vol": [0.20, 0.22, 0.25],
            "delta": [None, None, None],
            "gamma": [None, None, None],
            "vega": [None, None, None],
            "theta": [None, None, None],
        })

    @pytest.fixture
    def client(self):
        """Create a YFinanceClient instance."""
        return YFinanceClient(calls_per_minute=60)

    def test_filter_strike_range(self, sample_options_df, client):
        """Test filtering by strike range."""
        result = client.filter_strike_range(
            sample_options_df, spot_price=5050.0, range_percent=0.02
        )
        # Only strikes within ±2% of 5050 (4949-5151)
        assert len(result) == 3  # All strikes are within range

    def test_filter_strike_range_narrow(self, sample_options_df, client):
        """Test filtering with narrow range."""
        result = client.filter_strike_range(
            sample_options_df, spot_price=5050.0, range_percent=0.005
        )
        # ±0.5% of 5050 = 5024.75-5075.25
        # Our sample strikes are 5000 and 5100, neither is within this narrow range
        assert len(result) == 0  # No strikes within narrow range

    def test_filter_strike_range_empty_df(self, client):
        """Test filtering empty DataFrame."""
        empty_df = pd.DataFrame()
        result = client.filter_strike_range(empty_df, 5900.0)
        assert result.empty

    def test_filter_0dte_contracts(self, sample_options_df, client):
        """Test filtering to 0DTE contracts."""
        result = client.filter_0dte_contracts(
            sample_options_df, target_date=date(2025, 1, 31)
        )
        assert len(result) == 3

    def test_filter_0dte_empty_df(self, client):
        """Test filtering empty DataFrame."""
        empty_df = pd.DataFrame()
        result = client.filter_0dte_contracts(empty_df)
        assert result.empty


@pytest.mark.asyncio
class TestYFinanceClientAsync:
    """Async tests for YFinanceClient API methods."""

    @pytest.fixture
    def client(self):
        """Create a YFinanceClient instance."""
        return YFinanceClient(calls_per_minute=60)

    async def test_close(self, client):
        """Test close is a no-op."""
        await client.close()  # Should not raise


@pytest.mark.integration
@pytest.mark.asyncio
class TestYFinanceClientIntegration:
    """Integration tests that hit the real Yahoo Finance API.

    These tests are marked with @pytest.mark.integration and are
    skipped by default. Run with: pytest -m integration
    """

    @pytest.fixture
    def client(self):
        """Create a YFinanceClient instance."""
        return YFinanceClient(calls_per_minute=5)

    async def test_get_spot_price_spy(self, client):
        """Test fetching SPY spot price."""
        price = await client.get_spot_price("SPY")
        assert price > 0
        assert 100 < price < 1000  # Reasonable SPY range

    async def test_get_spot_price_spx(self, client):
        """Test fetching SPX spot price (via SPY proxy)."""
        price = await client.get_spot_price("SPX")
        assert price > 0
        assert 3000 < price < 10000  # Reasonable SPX range

    async def test_get_expirations(self, client):
        """Test fetching available expirations."""
        expirations = await client.get_expirations("SPY")
        assert len(expirations) > 0
        # Expirations should be date strings
        assert all("-" in exp for exp in expirations)

    async def test_get_options_chain_snapshot(self, client):
        """Test fetching options chain snapshot."""
        df = await client.get_options_chain_snapshot("SPY")
        assert not df.empty
        assert "strike" in df.columns
        assert "type" in df.columns
        assert "open_interest" in df.columns
        assert "implied_vol" in df.columns
        # Greeks should be None (yfinance doesn't provide them)
        assert df["delta"].isna().all()
        assert df["gamma"].isna().all()

    async def test_get_options_chain_for_gex(self, client):
        """Test the main GEX data acquisition method."""
        df, spot_price = await client.get_options_chain_for_gex("SPY")
        assert spot_price > 0
        # May be empty if no 0DTE options available
        if not df.empty:
            assert "strike" in df.columns
            assert "open_interest" in df.columns
