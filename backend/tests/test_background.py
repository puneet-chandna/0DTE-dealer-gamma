"""Tests for the Background Tasks Service.

Comprehensive tests for background tasks including periodic refresh,
cache warmup, and task lifecycle management.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.services import background
from app.services.background import (
    get_gex_calculator,
    get_polygon_client,
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


class TestGetGEXCalculator:
    """Test GEX calculator instance management."""

    def setup_method(self):
        """Reset global state before each test."""
        background._gex_calculator = None

    def test_creates_calculator(self):
        """Should create a GEXCalculator instance."""
        calc = get_gex_calculator()
        assert calc is not None
        from app.core.gex_calculator import GEXCalculator
        assert isinstance(calc, GEXCalculator)

    def test_returns_same_instance(self):
        """Should return the same instance on subsequent calls."""
        calc1 = get_gex_calculator()
        calc2 = get_gex_calculator()
        assert calc1 is calc2


class TestGetPolygonClient:
    """Test Polygon client instance management."""

    def setup_method(self):
        """Reset global state before each test."""
        background._polygon_client = None

    @pytest.mark.asyncio
    async def test_returns_none_without_api_key(self):
        """Should return None when API key not configured."""
        with patch("app.services.background.get_settings") as mock_settings:
            mock_settings.return_value.polygon_api_key = ""
            client = await get_polygon_client()
            assert client is None

    @pytest.mark.asyncio
    async def test_creates_client_with_api_key(self):
        """Should create client when API key is configured."""
        with patch("app.services.background.get_settings") as mock_settings:
            mock_settings.return_value.polygon_api_key = "test_key"
            with patch("app.services.background.PolygonClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                
                client = await get_polygon_client()
                
                assert client is mock_client
                mock_client_class.assert_called_once_with(api_key="test_key", tier="free")

    @pytest.mark.asyncio
    async def test_returns_same_client_instance(self):
        """Should return the same client on subsequent calls."""
        with patch("app.services.background.get_settings") as mock_settings:
            mock_settings.return_value.polygon_api_key = "test_key"
            with patch("app.services.background.PolygonClient") as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client
                
                client1 = await get_polygon_client()
                client2 = await get_polygon_client()
                
                assert client1 is client2
                # Should only be called once
                assert mock_client_class.call_count == 1


class TestCacheWarmup:
    """Test cache warmup functionality."""

    def setup_method(self):
        """Reset global state before each test."""
        background._gex_calculator = None
        background._polygon_client = None
        reset_cache()

    @pytest.mark.asyncio
    async def test_skips_when_market_closed(self):
        """Should skip warmup when market is closed."""
        with patch("app.services.background.is_market_open", return_value=False):
            await cache_warmup()
            # Should not raise, just return early

    @pytest.mark.asyncio
    async def test_skips_without_api_key(self):
        """Should skip warmup when no API key configured."""
        with patch("app.services.background.is_market_open", return_value=True):
            with patch("app.services.background.get_polygon_client", return_value=None):
                await cache_warmup()
                # Should not raise, just return early

    @pytest.mark.asyncio
    async def test_warms_cache_successfully(self):
        """Should warm up cache with GEX data."""
        mock_options_df = pd.DataFrame({
            "contractType": ["call", "put"],
            "strike": [5900.0, 5900.0],
            "openInterest": [1000, 1000],
            "impliedVolatility": [0.2, 0.2],
            "gamma": [0.01, 0.01],
            "delta": [0.5, -0.5],
            "expiration": ["2099-01-15", "2099-01-15"],
        })
        
        mock_client = AsyncMock()
        mock_client.get_options_chain_for_gex = AsyncMock(
            return_value=(mock_options_df, 5900.0)
        )

        mock_snapshot = MagicMock()
        mock_snapshot.net_gex = -1.5e9

        mock_calculator = MagicMock()
        mock_calculator.calculate_gex_from_chain.return_value = mock_snapshot

        with patch("app.services.background.is_market_open", return_value=True):
            with patch("app.services.background.get_polygon_client", return_value=mock_client):
                with patch("app.services.background.get_gex_calculator", return_value=mock_calculator):
                    with patch("app.services.background.get_cache") as mock_cache:
                        mock_cache_instance = MagicMock()
                        mock_cache.return_value = mock_cache_instance
                        
                        await cache_warmup()
                        
                        # Should have called cache operations
                        mock_cache_instance.update_spot_price.assert_called_once_with(5900.0)
                        mock_cache_instance.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_warmup_error(self):
        """Should handle errors during warmup gracefully."""
        mock_client = AsyncMock()
        mock_client.get_options_chain_for_gex = AsyncMock(
            side_effect=Exception("API Error")
        )

        with patch("app.services.background.is_market_open", return_value=True):
            with patch("app.services.background.get_polygon_client", return_value=mock_client):
                # Should not raise
                await cache_warmup()


class TestPeriodicGEXRefresh:
    """Test periodic GEX refresh task."""

    def setup_method(self):
        """Reset global state before each test."""
        background._gex_calculator = None
        background._polygon_client = None
        background._shutdown_event = None
        reset_cache()

    @pytest.mark.asyncio
    async def test_stops_on_shutdown_event(self):
        """Should stop when shutdown event is set."""
        background._shutdown_event = asyncio.Event()
        background._shutdown_event.set()

        # Should return quickly
        await asyncio.wait_for(periodic_gex_refresh(), timeout=1.0)

    @pytest.mark.asyncio
    async def test_sleeps_when_market_closed(self):
        """Should sleep longer when market is closed."""
        background._shutdown_event = asyncio.Event()

        call_count = 0

        async def mock_sleep(duration):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                background._shutdown_event.set()
            # Don't actually sleep

        with patch("app.services.background.is_market_open", return_value=False):
            with patch("asyncio.sleep", side_effect=mock_sleep):
                await asyncio.wait_for(periodic_gex_refresh(), timeout=2.0)

    @pytest.mark.asyncio
    async def test_skips_without_polygon_client(self):
        """Should skip refresh when no Polygon client."""
        background._shutdown_event = asyncio.Event()

        call_count = 0

        async def mock_sleep(duration):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                background._shutdown_event.set()

        with patch("app.services.background.is_market_open", return_value=True):
            with patch("app.services.background.get_polygon_client", return_value=None):
                with patch("asyncio.sleep", side_effect=mock_sleep):
                    await asyncio.wait_for(periodic_gex_refresh(), timeout=2.0)

    @pytest.mark.asyncio
    async def test_handles_cancellation(self):
        """Should handle task cancellation gracefully."""
        background._shutdown_event = asyncio.Event()

        call_count = 0
        
        original_sleep = asyncio.sleep
        
        async def controlled_sleep(duration):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call - allow task to be cancelled
                await original_sleep(0.5)
            else:
                background._shutdown_event.set()

        with patch("app.services.background.is_market_open", return_value=False):
            with patch("asyncio.sleep", side_effect=controlled_sleep):
                task = asyncio.create_task(periodic_gex_refresh())
                await original_sleep(0.1)
                task.cancel()
                
                try:
                    await asyncio.wait_for(task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass  # Expected


class TestPeriodicSpotRefresh:
    """Test periodic spot price refresh task."""

    def setup_method(self):
        """Reset global state before each test."""
        background._polygon_client = None
        background._shutdown_event = None
        reset_cache()

    @pytest.mark.asyncio
    async def test_stops_on_shutdown_event(self):
        """Should stop when shutdown event is set."""
        background._shutdown_event = asyncio.Event()
        background._shutdown_event.set()

        await asyncio.wait_for(periodic_spot_refresh(), timeout=1.0)

    @pytest.mark.asyncio
    async def test_sleeps_when_market_closed(self):
        """Should sleep when market is closed."""
        background._shutdown_event = asyncio.Event()

        call_count = 0

        async def mock_sleep(duration):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                background._shutdown_event.set()

        with patch("app.services.background.is_market_open", return_value=False):
            with patch("asyncio.sleep", side_effect=mock_sleep):
                await asyncio.wait_for(periodic_spot_refresh(), timeout=2.0)

    @pytest.mark.asyncio
    async def test_refreshes_spot_price(self):
        """Should refresh spot price when market is open."""
        background._shutdown_event = asyncio.Event()

        mock_client = AsyncMock()
        mock_client.get_spot_price = AsyncMock(return_value=5900.0)

        call_count = 0

        async def mock_sleep(duration):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                background._shutdown_event.set()

        with patch("app.services.background.is_market_open", return_value=True):
            with patch("app.services.background.get_polygon_client", return_value=mock_client):
                with patch("asyncio.sleep", side_effect=mock_sleep):
                    with patch("app.services.background.get_cache") as mock_cache:
                        mock_cache_instance = MagicMock()
                        mock_cache.return_value = mock_cache_instance

                        await asyncio.wait_for(periodic_spot_refresh(), timeout=2.0)

                        mock_cache_instance.update_spot_price.assert_called_with(5900.0)


class TestStartBackgroundTasks:
    """Test starting background tasks."""

    def setup_method(self):
        """Reset global state before each test."""
        background._background_tasks = []
        background._shutdown_event = None
        background._polygon_client = None
        background._gex_calculator = None
        reset_cache()

    def teardown_method(self):
        """Clean up tasks after each test."""
        for task in background._background_tasks:
            if not task.done():
                task.cancel()
        background._background_tasks = []

    @pytest.mark.asyncio
    async def test_creates_shutdown_event(self):
        """Should create shutdown event."""
        with patch("app.services.background.cache_warmup", new_callable=AsyncMock):
            with patch("app.services.background.get_settings") as mock_settings:
                mock_settings.return_value.polygon_api_key = ""
                
                await start_background_tasks()
                
                assert background._shutdown_event is not None
                assert isinstance(background._shutdown_event, asyncio.Event)

    @pytest.mark.asyncio
    async def test_runs_cache_warmup(self):
        """Should run cache warmup."""
        with patch("app.services.background.cache_warmup", new_callable=AsyncMock) as mock_warmup:
            with patch("app.services.background.get_settings") as mock_settings:
                mock_settings.return_value.polygon_api_key = ""
                
                await start_background_tasks()
                
                mock_warmup.assert_called_once()

    @pytest.mark.asyncio
    async def test_starts_tasks_with_api_key(self):
        """Should start background tasks when API key is configured."""
        with patch("app.services.background.cache_warmup", new_callable=AsyncMock):
            with patch("app.services.background.get_settings") as mock_settings:
                mock_settings.return_value.polygon_api_key = "test_key"
                with patch("app.services.background.periodic_gex_refresh", new_callable=AsyncMock):
                    with patch("app.services.background.periodic_spot_refresh", new_callable=AsyncMock):
                        await start_background_tasks()
                        
                        # Should have created 2 tasks
                        assert len(background._background_tasks) == 2
                        
                        # Clean up
                        background._shutdown_event.set()
                        for task in background._background_tasks:
                            task.cancel()

    @pytest.mark.asyncio
    async def test_no_tasks_without_api_key(self):
        """Should not start data refresh tasks without API key."""
        with patch("app.services.background.cache_warmup", new_callable=AsyncMock):
            with patch("app.services.background.get_settings") as mock_settings:
                mock_settings.return_value.polygon_api_key = ""
                
                await start_background_tasks()
                
                assert len(background._background_tasks) == 0


class TestStopBackgroundTasks:
    """Test stopping background tasks."""

    def setup_method(self):
        """Reset global state before each test."""
        background._background_tasks = []
        background._shutdown_event = asyncio.Event()
        background._polygon_client = None
        reset_cache()

    @pytest.mark.asyncio
    async def test_sets_shutdown_event(self):
        """Should set shutdown event."""
        await stop_background_tasks()
        
        assert background._shutdown_event.is_set()

    @pytest.mark.asyncio
    async def test_cancels_running_tasks(self):
        """Should cancel running tasks."""
        # Create a dummy task
        async def dummy_task():
            await asyncio.sleep(100)

        task = asyncio.create_task(dummy_task())
        task.set_name("dummy")
        background._background_tasks.append(task)

        await stop_background_tasks()

        assert task.cancelled() or task.done()
        assert len(background._background_tasks) == 0

    @pytest.mark.asyncio
    async def test_closes_polygon_client(self):
        """Should close Polygon client."""
        mock_client = AsyncMock()
        background._polygon_client = mock_client

        await stop_background_tasks()

        mock_client.close.assert_called_once()
        assert background._polygon_client is None

    @pytest.mark.asyncio
    async def test_handles_already_done_tasks(self):
        """Should handle tasks that are already done."""
        # Create a task that completes immediately
        async def quick_task():
            return "done"

        task = asyncio.create_task(quick_task())
        await task  # Let it complete
        task.set_name("quick")
        background._background_tasks.append(task)

        # Should not raise
        await stop_background_tasks()
        assert len(background._background_tasks) == 0


class TestConstants:
    """Test module constants."""

    def test_refresh_intervals(self):
        """Should have expected refresh intervals."""
        assert GEX_REFRESH_INTERVAL == 5
        assert SPOT_REFRESH_INTERVAL == 2
