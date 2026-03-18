"""Tests for the Background Tasks Service.

Revised to match the YFinance-based implementation (Polygon removed).
Tests periodic refresh, cache warmup, and task lifecycle management.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.services import background
from app.services.background import (
    get_gex_calculator,
    get_data_client,
    periodic_gex_refresh,
    periodic_spot_refresh,
    cache_warmup,
    start_background_tasks,
    stop_background_tasks,
    GEX_REFRESH_INTERVAL,
    SPOT_REFRESH_INTERVAL,
)
from app.services.cache import reset_cache

ET = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_options_df() -> pd.DataFrame:
    """Return a minimal valid options DataFrame."""
    return pd.DataFrame(
        {
            "contractType": ["call", "put"],
            "strike": [5900.0, 5900.0],
            "openInterest": [1000, 1000],
            "impliedVolatility": [0.2, 0.2],
            "gamma": [0.01, 0.01],
            "delta": [0.5, -0.5],
            "expiration": ["2099-01-15", "2099-01-15"],
        }
    )


# ---------------------------------------------------------------------------
# get_gex_calculator
# ---------------------------------------------------------------------------

class TestGetGEXCalculator:
    """Test GEX calculator singleton management."""

    def setup_method(self):
        background._gex_calculator = None

    def test_creates_calculator(self):
        """Should create a GEXCalculator instance."""
        from app.core.gex_calculator import GEXCalculator
        calc = get_gex_calculator()
        assert calc is not None
        assert isinstance(calc, GEXCalculator)

    def test_returns_same_instance(self):
        """Should return the same instance on subsequent calls (singleton)."""
        calc1 = get_gex_calculator()
        calc2 = get_gex_calculator()
        assert calc1 is calc2


# ---------------------------------------------------------------------------
# get_data_client
# ---------------------------------------------------------------------------

class TestGetDataClient:
    """Test YFinance data client singleton management."""

    def setup_method(self):
        background._data_client = None

    @pytest.mark.asyncio
    async def test_creates_client(self):
        """Should create a YFinanceClient instance."""
        from app.core.yfinance_provider import YFinanceClient
        client = await get_data_client()
        assert client is not None
        assert isinstance(client, YFinanceClient)

    @pytest.mark.asyncio
    async def test_returns_same_instance(self):
        """Should return the same client on subsequent calls (singleton)."""
        client1 = await get_data_client()
        client2 = await get_data_client()
        assert client1 is client2

    def teardown_method(self):
        background._data_client = None


# ---------------------------------------------------------------------------
# cache_warmup
# ---------------------------------------------------------------------------

class TestCacheWarmup:
    """Test cache warmup logic."""

    def setup_method(self):
        background._gex_calculator = None
        background._data_client = None
        reset_cache()

    @pytest.mark.asyncio
    async def test_skips_when_market_closed(self):
        """Should return early when market is closed, no errors."""
        with patch("app.services.background.is_market_open", return_value=False):
            await cache_warmup()  # should not raise

    @pytest.mark.asyncio
    async def test_warms_cache_successfully(self):
        """Should populate cache when market is open and data fetch succeeds."""
        mock_df = _make_options_df()
        mock_client = AsyncMock()
        mock_client.get_options_chain_for_gex = AsyncMock(return_value=(mock_df, 5900.0))

        mock_snapshot = MagicMock()
        mock_snapshot.net_gex = -1.5e9

        mock_calculator = MagicMock()
        mock_calculator.calculate_gex_from_chain.return_value = mock_snapshot

        with patch("app.services.background.is_market_open", return_value=True):
            with patch("app.services.background.get_data_client", return_value=mock_client):
                with patch("app.services.background.get_gex_calculator", return_value=mock_calculator):
                    with patch("app.services.background.get_cache") as mock_get_cache:
                        mock_cache = MagicMock()
                        mock_get_cache.return_value = mock_cache

                        await cache_warmup()

                        mock_cache.update_spot_price.assert_called_once_with(5900.0)
                        mock_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_fetch_error_gracefully(self):
        """Should log and swallow errors during warmup."""
        mock_client = AsyncMock()
        mock_client.get_options_chain_for_gex = AsyncMock(
            side_effect=Exception("yfinance timeout")
        )

        with patch("app.services.background.is_market_open", return_value=True):
            with patch("app.services.background.get_data_client", return_value=mock_client):
                await cache_warmup()  # should not raise


# ---------------------------------------------------------------------------
# periodic_gex_refresh
# ---------------------------------------------------------------------------

class TestPeriodicGEXRefresh:
    """Test the periodic GEX refresh background loop."""

    def setup_method(self):
        background._gex_calculator = None
        background._data_client = None
        background._shutdown_event = None
        reset_cache()

    @pytest.mark.asyncio
    async def test_stops_on_shutdown_event(self):
        """Should exit the loop immediately when shutdown event is set."""
        background._shutdown_event = asyncio.Event()
        background._shutdown_event.set()
        await asyncio.wait_for(periodic_gex_refresh(), timeout=1.0)

    @pytest.mark.asyncio
    async def test_sleeps_when_market_closed(self):
        """Should sleep (long interval) and not fetch data when market closed."""
        background._shutdown_event = asyncio.Event()
        calls = []

        async def mock_sleep(duration):
            calls.append(duration)
            background._shutdown_event.set()

        with patch("app.services.background.is_market_open", return_value=False):
            with patch("asyncio.sleep", side_effect=mock_sleep):
                await asyncio.wait_for(periodic_gex_refresh(), timeout=2.0)

        assert len(calls) >= 1
        assert calls[0] == 60  # off-hours sleep

    @pytest.mark.asyncio
    async def test_refreshes_successfully_when_open(self):
        """Should fetch, calculate, and cache GEX when market is open."""
        background._shutdown_event = asyncio.Event()
        calls = []

        mock_df = _make_options_df()
        mock_client = AsyncMock()
        mock_client.get_options_chain_for_gex = AsyncMock(return_value=(mock_df, 5900.0))

        mock_snap = MagicMock()
        mock_snap.net_gex = -1e9
        mock_snap.spot_price = 5900.0
        mock_calc = MagicMock()
        mock_calc.calculate_gex_from_chain.return_value = mock_snap

        async def mock_sleep(duration):
            calls.append(duration)
            background._shutdown_event.set()

        with patch("app.services.background.is_market_open", return_value=True):
            with patch("app.services.background.get_data_client", return_value=mock_client):
                with patch("app.services.background.get_gex_calculator", return_value=mock_calc):
                    with patch("app.services.background.get_cache") as mock_get_cache:
                        mock_cache = MagicMock()
                        mock_get_cache.return_value = mock_cache
                        with patch("asyncio.sleep", side_effect=mock_sleep):
                            await asyncio.wait_for(periodic_gex_refresh(), timeout=2.0)

        mock_cache.update_spot_price.assert_called()
        mock_cache.set.assert_called()

    @pytest.mark.asyncio
    async def test_handles_cancellation(self):
        """Should clean up on asyncio.CancelledError."""
        background._shutdown_event = asyncio.Event()
        original_sleep = asyncio.sleep

        async def slow_sleep(duration):
            if duration == 60:
                await original_sleep(10)  # blocks until cancelled
            else:
                background._shutdown_event.set()

        with patch("app.services.background.is_market_open", return_value=False):
            with patch("asyncio.sleep", side_effect=slow_sleep):
                task = asyncio.create_task(periodic_gex_refresh())
                await original_sleep(0.05)
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass


# ---------------------------------------------------------------------------
# periodic_spot_refresh
# ---------------------------------------------------------------------------

class TestPeriodicSpotRefresh:
    """Test the periodic spot price refresh background loop."""

    def setup_method(self):
        background._data_client = None
        background._shutdown_event = None
        reset_cache()

    @pytest.mark.asyncio
    async def test_stops_on_shutdown_event(self):
        """Should exit immediately when shutdown event is set."""
        background._shutdown_event = asyncio.Event()
        background._shutdown_event.set()
        await asyncio.wait_for(periodic_spot_refresh(), timeout=1.0)

    @pytest.mark.asyncio
    async def test_sleeps_when_market_closed(self):
        """Should sleep long interval when market is closed."""
        background._shutdown_event = asyncio.Event()
        calls = []

        async def mock_sleep(duration):
            calls.append(duration)
            background._shutdown_event.set()

        with patch("app.services.background.is_market_open", return_value=False):
            with patch("asyncio.sleep", side_effect=mock_sleep):
                await asyncio.wait_for(periodic_spot_refresh(), timeout=2.0)

        assert calls[0] == 60

    @pytest.mark.asyncio
    async def test_refreshes_spot_price_when_open(self):
        """Should fetch spot price and update cache when market is open."""
        background._shutdown_event = asyncio.Event()

        mock_client = AsyncMock()
        mock_client.get_spot_price = AsyncMock(return_value=5910.0)

        async def mock_sleep(duration):
            background._shutdown_event.set()

        with patch("app.services.background.is_market_open", return_value=True):
            with patch("app.services.background.get_data_client", return_value=mock_client):
                with patch("app.services.background.get_cache") as mock_get_cache:
                    mock_cache = MagicMock()
                    mock_get_cache.return_value = mock_cache
                    with patch("asyncio.sleep", side_effect=mock_sleep):
                        await asyncio.wait_for(periodic_spot_refresh(), timeout=2.0)

        mock_cache.update_spot_price.assert_called_with(5910.0)

    @pytest.mark.asyncio
    async def test_handles_spot_fetch_error(self):
        """Should log and continue on spot fetch failure."""
        background._shutdown_event = asyncio.Event()
        calls = []

        mock_client = AsyncMock()
        mock_client.get_spot_price = AsyncMock(side_effect=Exception("network error"))

        async def mock_sleep(duration):
            calls.append(duration)
            background._shutdown_event.set()

        with patch("app.services.background.is_market_open", return_value=True):
            with patch("app.services.background.get_data_client", return_value=mock_client):
                with patch("asyncio.sleep", side_effect=mock_sleep):
                    await asyncio.wait_for(periodic_spot_refresh(), timeout=2.0)

        assert len(calls) >= 1


# ---------------------------------------------------------------------------
# start_background_tasks
# ---------------------------------------------------------------------------

class TestStartBackgroundTasks:
    """Test application startup task creation."""

    def setup_method(self):
        background._background_tasks = []
        background._shutdown_event = None
        background._data_client = None
        background._gex_calculator = None
        reset_cache()

    def teardown_method(self):
        # Ensure shutdown event is set so loops exit
        if background._shutdown_event:
            background._shutdown_event.set()
        background._background_tasks = []

    @pytest.mark.asyncio
    async def test_creates_shutdown_event(self):
        """Should always create a shutdown asyncio.Event."""
        with patch("app.services.background.cache_warmup", new_callable=AsyncMock):
            with patch("app.services.background.periodic_gex_refresh", new_callable=AsyncMock):
                with patch("app.services.background.periodic_spot_refresh", new_callable=AsyncMock):
                    await start_background_tasks()
                    assert background._shutdown_event is not None
                    assert isinstance(background._shutdown_event, asyncio.Event)
                    # Clean up tasks
                    background._shutdown_event.set()
                    for task in background._background_tasks:
                        task.cancel()
                    background._background_tasks = []

    @pytest.mark.asyncio
    async def test_runs_cache_warmup(self):
        """Should call cache_warmup exactly once during startup."""
        with patch("app.services.background.cache_warmup", new_callable=AsyncMock) as mock_warmup:
            with patch("app.services.background.periodic_gex_refresh", new_callable=AsyncMock):
                with patch("app.services.background.periodic_spot_refresh", new_callable=AsyncMock):
                    await start_background_tasks()
                    mock_warmup.assert_called_once()
                    # Clean up tasks
                    background._shutdown_event.set()
                    for task in background._background_tasks:
                        task.cancel()
                    background._background_tasks = []

    @pytest.mark.asyncio
    async def test_always_starts_background_tasks(self):
        """YFinance needs no API key — tasks should always be created."""
        with patch("app.services.background.cache_warmup", new_callable=AsyncMock):
            with patch("app.services.background.periodic_gex_refresh", new_callable=AsyncMock):
                with patch("app.services.background.periodic_spot_refresh", new_callable=AsyncMock):
                    await start_background_tasks()
                    # Should have created 2 tasks (GEX + Spot)
                    assert len(background._background_tasks) == 2
                    # Clean up
                    background._shutdown_event.set()
                    for task in background._background_tasks:
                        task.cancel()
                    background._background_tasks = []


# ---------------------------------------------------------------------------
# stop_background_tasks
# ---------------------------------------------------------------------------

class TestStopBackgroundTasks:
    """Test graceful shutdown of background tasks."""

    def setup_method(self):
        background._background_tasks = []
        background._shutdown_event = asyncio.Event()
        background._data_client = None
        reset_cache()

    @pytest.mark.asyncio
    async def test_sets_shutdown_event(self):
        """Should set the shutdown asyncio.Event."""
        await stop_background_tasks()
        assert background._shutdown_event.is_set()

    @pytest.mark.asyncio
    async def test_cancels_running_tasks(self):
        """Should cancel and clear all running tasks."""
        async def long_running():
            await asyncio.sleep(100)

        task = asyncio.create_task(long_running())
        task.set_name("dummy")
        background._background_tasks.append(task)

        await stop_background_tasks()

        assert task.cancelled() or task.done()
        assert len(background._background_tasks) == 0

    @pytest.mark.asyncio
    async def test_closes_data_client(self):
        """Should close the YFinance data client on shutdown."""
        mock_client = AsyncMock()
        background._data_client = mock_client

        await stop_background_tasks()

        mock_client.close.assert_called_once()
        assert background._data_client is None

    @pytest.mark.asyncio
    async def test_handles_already_done_tasks(self):
        """Should handle tasks that are already complete without error."""
        async def quick():
            return "done"

        task = asyncio.create_task(quick())
        await task
        task.set_name("quick")
        background._background_tasks.append(task)

        await stop_background_tasks()
        assert len(background._background_tasks) == 0

    @pytest.mark.asyncio
    async def test_no_polygon_client_attribute(self):
        """Ensures the module no longer has _polygon_client state."""
        assert not hasattr(background, "_polygon_client"), (
            "_polygon_client has been removed; background service now uses _data_client"
        )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify module-level constants are correct."""

    def test_refresh_intervals(self):
        assert GEX_REFRESH_INTERVAL == 5
        assert SPOT_REFRESH_INTERVAL == 2
