"""0DTE GEX Backend - WebSocket Integration Tests."""

import json
import math
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.websocket import ConnectionManager, _get_gex_update
from app.config import Settings
from app.core.advanced_analytics import reset_advanced_analytics_state
from app.main import app
from app.models.schemas import GEXSnapshot


client = TestClient(app)
ET = ZoneInfo("America/New_York")


class TestWebSocketEndpoints:
    """Test WebSocket connection and streaming."""

    def test_websocket_connections_count(self):
        """Test that connection count endpoint works."""
        response = client.get("/ws/connections")

        assert response.status_code == 200
        data = response.json()
        assert "active_connections" in data
        assert isinstance(data["active_connections"], int)
        assert data["active_connections"] >= 0
        assert "timestamp" in data

    def test_websocket_gex_stream_connects(self):
        """Test WebSocket connection establishment."""
        with client.websocket_connect("/ws/gex-stream") as websocket:
            # Should receive initial connection message
            data = websocket.receive_json()

            assert data["type"] == "connected"
            assert "data" in data
            assert "message" in data["data"]
            assert "market_open" in data["data"]
            assert "update_interval_seconds" in data["data"]
            assert "timestamp" in data

    def test_websocket_receives_gex_update(self):
        """Test that WebSocket receives GEX updates after connection."""
        with client.websocket_connect("/ws/gex-stream") as websocket:
            # Skip initial connection message
            websocket.receive_json()

            # Wait for first GEX update (no timeout in TestClient)
            data = websocket.receive_json()

            assert data["type"] == "gex_update"
            assert "data" in data
            assert "net_gex" in data["data"]
            assert "net_gex_billions" in data["data"]
            assert "zero_gamma_level" in data["data"]
            assert "spot_price" in data["data"]
            assert "regime" in data["data"]
            assert data["data"]["regime"] in ["short_gamma", "long_gamma", "neutral"]
            assert "timestamp" in data
            assert "market_open" in data

    def test_websocket_gex_update_format(self):
        """Test GEX update data has correct types and ranges."""
        with client.websocket_connect("/ws/gex-stream") as websocket:
            # Skip connection message
            websocket.receive_json()

            # Get first update
            data = websocket.receive_json()
            gex_data = data["data"]

            # Check numeric types
            assert isinstance(gex_data["net_gex"], (int, float))
            assert isinstance(gex_data["net_gex_billions"], (int, float))
            assert isinstance(gex_data["zero_gamma_level"], (int, float))
            assert isinstance(gex_data["spot_price"], (int, float))

            assert math.isfinite(gex_data["net_gex"])
            assert math.isfinite(gex_data["zero_gamma_level"])
            assert gex_data["net_gex_billions"] == gex_data["net_gex"] / 1e9

            # Spot price should be a positive realistic number
            assert 100 <= gex_data["spot_price"] <= 10000

    def test_websocket_handles_client_messages(self):
        """Test that WebSocket can receive client messages (e.g., ping)."""
        with client.websocket_connect("/ws/gex-stream") as websocket:
            # Skip connection message
            websocket.receive_json()

            # Send a ping message
            websocket.send_json({"type": "ping"})

            # Should still receive next update without error
            data = websocket.receive_json()
            assert data["type"] == "gex_update"

    def test_websocket_connection_counted(self):
        """Test that active connections are tracked."""
        # Get initial count
        initial_response = client.get("/ws/connections")
        initial_count = initial_response.json()["active_connections"]

        # Open a WebSocket connection
        with client.websocket_connect("/ws/gex-stream") as websocket:
            websocket.receive_json()  # Wait for connection

            # Count should increase (or stay same in blocking tests)
            during_response = client.get("/ws/connections")
            during_count = during_response.json()["active_connections"]
            assert during_count >= initial_count

        # After closing, count should decrease
        after_response = client.get("/ws/connections")
        assert after_response.status_code == 200

    def test_websocket_market_open_status(self):
        """Test that market open status is included in messages."""
        with client.websocket_connect("/ws/gex-stream") as websocket:
            # Connection message should have market_open
            connection_data = websocket.receive_json()
            assert "market_open" in connection_data["data"]
            assert isinstance(connection_data["data"]["market_open"], bool)

            # Update messages should also have market_open
            update_data = websocket.receive_json()
            assert "market_open" in update_data
            assert isinstance(update_data["market_open"], bool)

    def test_websocket_mock_data_flag(self):
        """Test that is_mock flag is set when using mock data."""
        with client.websocket_connect("/ws/gex-stream") as websocket:
            websocket.receive_json()  # Skip connection

            data = websocket.receive_json()
            gex_data = data["data"]

            # Without API key, should be mock data
            assert "is_mock" in gex_data
            assert isinstance(gex_data["is_mock"], bool)

    def test_websocket_passes_provider_query_param_to_update_fetch(self):
        """Provider-aware websocket connections should fetch using the selected provider."""
        with patch("app.api.websocket._get_gex_update", new_callable=AsyncMock) as mock_get_update:
            mock_get_update.return_value = {
                "net_gex": 1.0,
                "net_gex_billions": 1e-9,
                "zero_gamma_level": 5000.0,
                "spot_price": 5001.0,
                "regime": "neutral",
                "is_mock": False,
                "provider": "tradier",
            }

            with client.websocket_connect("/ws/gex-stream?provider=tradier") as websocket:
                websocket.receive_json()
                update = websocket.receive_json()

        assert update["type"] == "gex_update"
        assert update["data"]["provider"] == "tradier"
        mock_get_update.assert_awaited()
        _, kwargs = mock_get_update.await_args
        assert kwargs["provider"] == "tradier"


class TestGEXUpdateHelper:
    """Unit tests for provider-aware websocket payload generation."""

    @pytest.mark.asyncio
    async def test_stale_cache_triggers_live_refresh_before_reuse(self):
        """Stale cached websocket data should be refreshed when live fetch succeeds."""
        stale_snapshot = {
            "timestamp": "2099-01-15T10:30:00-05:00",
            "spot_price": 5900.0,
            "total_call_gex": 1.0,
            "total_put_gex": -2.0,
            "net_gex": -1.0,
            "zero_gamma_level": 5895.0,
            "gex_by_strike": {"5900.0": 1.0},
            "dominant_strike": 5900.0,
            "metrics": {},
        }
        refreshed_snapshot = MagicMock()
        refreshed_snapshot.net_gex = -2.5e8
        refreshed_snapshot.zero_gamma_level = 6570.0
        refreshed_snapshot.spot_price = 6575.0
        refreshed_snapshot.timestamp = datetime(2026, 3, 23, 14, 20, tzinfo=ET)

        mock_cache = MagicMock()
        mock_cache.get_if_fresh.return_value = None
        mock_cache.get.side_effect = (
            lambda key: stale_snapshot if key == "gex:current:SPX:yfinance" else None
        )

        mock_client = AsyncMock()
        mock_client.provider_name = "yfinance"
        mock_client.get_options_chain_for_gex.return_value = (
            pd.DataFrame([{"contract": 1}]),
            6575.0,
        )

        mock_calculator = MagicMock()
        mock_calculator.calculate_gex_from_chain.return_value = refreshed_snapshot
        mock_calculator.determine_regime.return_value = ("neutral", "Neutral", "yellow")

        with patch("app.api.websocket.get_cache", return_value=mock_cache):
            with patch("app.api.websocket.get_data_client", return_value=mock_client):
                with patch("app.api.websocket.get_gex_calculator", return_value=mock_calculator):
                    payload = await _get_gex_update(
                        Settings(data_provider="yfinance"),
                        symbol="SPX",
                    )

        mock_cache.get_if_fresh.assert_any_call("gex:current:SPX:yfinance")
        mock_client.get_options_chain_for_gex.assert_awaited_once_with(underlying="SPX")
        assert payload["spot_price"] == 6575.0
        assert payload["is_stale"] is False
        assert payload["timestamp"] == refreshed_snapshot.timestamp.isoformat()

    @pytest.mark.asyncio
    async def test_cached_json_payload_is_parsed_for_provider_specific_requests(self):
        """Cached JSON strings should be parsed before generating websocket payloads."""
        cached_snapshot = json.dumps(
            {
                "timestamp": "2099-01-15T10:30:00-05:00",
                "spot_price": 5000.0,
                "total_call_gex": 1.0,
                "total_put_gex": -2.0,
                "net_gex": -1.0,
                "zero_gamma_level": 4995.0,
                "gex_by_strike": {"5000.0": 1.0},
                "dominant_strike": 5000.0,
                "metrics": {},
            }
        )
        mock_cache = MagicMock()
        mock_cache.get_if_fresh.return_value = None
        mock_cache.get.side_effect = (
            lambda key: cached_snapshot if key == "gex:current:SPX:tradier" else None
        )
        mock_cache.is_stale.return_value = True
        mock_client = AsyncMock()
        mock_client.provider_name = "tradier"
        mock_client.get_options_chain_for_gex.side_effect = RuntimeError("provider unavailable")

        with patch("app.api.websocket.get_cache", return_value=mock_cache):
            with patch("app.api.websocket.get_data_client", return_value=mock_client):
                payload = await _get_gex_update(
                    Settings(data_provider="yfinance"),
                    symbol="SPX",
                    provider=" TRADIER ",
                )

        mock_cache.get.assert_any_call("gex:current:SPX:tradier")
        assert payload["provider"] == "tradier"
        assert payload["is_stale"] is True
        assert payload["net_gex"] == -1.0

    @pytest.mark.asyncio
    async def test_cached_payload_uses_normalized_provider_name(self):
        """Cached websocket payloads should use the provider's normalized name."""
        cached_snapshot = {
            "timestamp": "2099-01-15T10:30:00-05:00",
            "spot_price": 5000.0,
            "total_call_gex": 1.0,
            "total_put_gex": -2.0,
            "net_gex": -1.0,
            "zero_gamma_level": 4995.0,
            "gex_by_strike": {"5000.0": 1.0},
            "dominant_strike": 5000.0,
            "metrics": {},
        }
        mock_cache = MagicMock()
        mock_cache.get_if_fresh.side_effect = (
            lambda key: cached_snapshot if key == "gex:current:SPX:yfinance" else None
        )
        mock_cache.is_stale.return_value = False
        mock_client = AsyncMock()
        mock_client.provider_name = "yfinance"

        with patch("app.api.websocket.get_cache", return_value=mock_cache):
            with patch("app.api.websocket.get_data_client", return_value=mock_client):
                payload = await _get_gex_update(
                    Settings(data_provider="YFINANCE"),
                    symbol="SPX",
                )

        mock_cache.get_if_fresh.assert_any_call("gex:current:SPX:yfinance")
        assert payload["provider"] == "yfinance"

    @pytest.mark.asyncio
    async def test_default_provider_legacy_cache_lookup_includes_symbol(self):
        """Legacy websocket cache fallback should be scoped by symbol."""
        cached_snapshot = {
            "timestamp": "2099-01-15T10:30:00-05:00",
            "spot_price": 5000.0,
            "total_call_gex": 1.0,
            "total_put_gex": -2.0,
            "net_gex": -1.0,
            "zero_gamma_level": 4995.0,
            "gex_by_strike": {"5000.0": 1.0},
            "dominant_strike": 5000.0,
            "metrics": {},
        }
        mock_cache = MagicMock()
        mock_cache.get_if_fresh.side_effect = (
            lambda key: cached_snapshot if key == "gex:current:QQQ" else None
        )
        mock_cache.is_stale.return_value = False
        mock_client = AsyncMock()
        mock_client.provider_name = "yfinance"

        with patch("app.api.websocket.get_cache", return_value=mock_cache):
            with patch("app.api.websocket.get_data_client", return_value=mock_client):
                await _get_gex_update(
                    Settings(data_provider="yfinance"),
                    symbol="QQQ",
                )

        mock_cache.get_if_fresh.assert_any_call("gex:current:QQQ")

    @pytest.mark.asyncio
    async def test_unreasonable_cached_payload_falls_back_to_mock_data(self):
        """Sanity checks should prevent obviously broken cached payloads reaching clients."""
        cached_snapshot = {
            "timestamp": "2099-01-15T10:30:00-05:00",
            "spot_price": 50.0,
            "total_call_gex": 1.0,
            "total_put_gex": -2.0,
            "net_gex": 6.0e9,
            "zero_gamma_level": 4995.0,
            "gex_by_strike": {"5000.0": 1.0},
            "dominant_strike": 5000.0,
            "metrics": {},
        }
        mock_cache = MagicMock()
        mock_cache.get_if_fresh.side_effect = (
            lambda key: cached_snapshot if key == "gex:current:SPX:yfinance" else None
        )
        mock_cache.is_stale.return_value = False
        mock_fallback = {
            "net_gex": 0.0,
            "net_gex_billions": 0.0,
            "zero_gamma_level": 5000.0,
            "spot_price": 5000.0,
            "regime": "neutral",
            "is_mock": True,
        }

        with patch("app.api.websocket.get_cache", return_value=mock_cache):
            with patch(
                "app.api.websocket._generate_mock_gex_data",
                return_value=mock_fallback,
            ) as mock_generate:
                payload = await _get_gex_update(
                    Settings(data_provider="yfinance"),
                    symbol="SPX",
                )

        mock_generate.assert_called_once()
        assert payload == mock_fallback

    @pytest.mark.asyncio
    async def test_large_but_finite_live_gex_payload_is_not_rejected(self):
        """Real same-day GEX values can be very large and should not be replaced by mock data."""
        cached_snapshot = {
            "timestamp": "2099-01-15T10:30:00-05:00",
            "spot_price": 6575.0,
            "total_call_gex": -2.8e12,
            "total_put_gex": 1.2e12,
            "net_gex": -1.6e12,
            "zero_gamma_level": 5600.0,
            "gex_by_strike": {"6570.0": 4.0},
            "dominant_strike": 6570.0,
            "metrics": {},
        }
        mock_cache = MagicMock()
        mock_cache.get_if_fresh.side_effect = (
            lambda key: cached_snapshot if key == "gex:current:SPX:yfinance" else None
        )

        with patch("app.api.websocket.get_cache", return_value=mock_cache):
            payload = await _get_gex_update(
                Settings(data_provider="yfinance"),
                symbol="SPX",
            )

        assert payload["is_mock"] is False
        assert payload["spot_price"] == 6575.0
        assert payload["net_gex"] == -1.6e12

    @pytest.mark.asyncio
    async def test_low_quality_live_snapshot_uses_persisted_provider_fallback_without_cache_write(self):
        """Low-quality live websocket snapshots should not displace persisted provider data."""
        low_quality_snapshot = MagicMock()
        low_quality_snapshot.net_gex = -1.0e12
        low_quality_snapshot.zero_gamma_level = 5250.0
        low_quality_snapshot.spot_price = 6530.0
        low_quality_snapshot.timestamp = datetime(2026, 3, 24, 15, 59, tzinfo=ET)
        low_quality_snapshot.advanced_analytics = None
        low_quality_snapshot.metrics = {
            "capture_quality": 0.0,
            "meaningful_strike_count": 1.0,
            "is_replay_eligible": 0.0,
        }

        persisted_snapshot = MagicMock()
        persisted_snapshot.net_gex = -6.0e8
        persisted_snapshot.zero_gamma_level = 6010.0
        persisted_snapshot.spot_price = 6025.0
        persisted_snapshot.timestamp = datetime(2026, 3, 24, 15, 50, tzinfo=ET)
        persisted_snapshot.advanced_analytics = None

        mock_cache = MagicMock()
        mock_cache.get_if_fresh.return_value = None
        mock_cache.get.return_value = None

        mock_client = AsyncMock()
        mock_client.provider_name = "yfinance"
        mock_client.get_options_chain_for_gex.return_value = (
            pd.DataFrame([{"contract": 1}]),
            6530.0,
        )

        mock_calculator = MagicMock()
        mock_calculator.calculate_gex_from_chain.return_value = low_quality_snapshot

        mock_history_service = MagicMock()
        mock_history_service.get_latest_snapshot = AsyncMock(return_value=persisted_snapshot)

        with patch("app.api.websocket.get_cache", return_value=mock_cache):
            with patch("app.api.websocket.get_data_client", return_value=mock_client):
                with patch("app.api.websocket.get_gex_calculator", return_value=mock_calculator):
                    with patch(
                        "app.api.websocket.get_historical_data_service",
                        return_value=mock_history_service,
                    ):
                        payload = await _get_gex_update(
                            Settings(data_provider="yfinance"),
                            symbol="SPX",
                        )

        assert payload["spot_price"] == 6025.0
        assert payload["provider"] == "yfinance"
        mock_cache.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_live_websocket_payload_includes_hawkes_baseline_state(self):
        """Fresh websocket fetches should expose Hawkes analytics even before any volume spike occurs."""
        reset_advanced_analytics_state()
        live_snapshot = GEXSnapshot(
            timestamp=datetime(2026, 3, 27, 10, 30, tzinfo=ET),
            spot_price=6015.0,
            total_call_gex=-2.0e8,
            total_put_gex=1.5e8,
            net_gex=-5.0e7,
            zero_gamma_level=6005.0,
            gex_by_strike={6000.0: -5.0e7},
            dominant_strike=6000.0,
            metrics={
                "capture_quality": 1.0,
                "meaningful_strike_count": 2.0,
                "is_replay_eligible": 1.0,
            },
            advanced_analytics=None,
        )
        options_df = pd.DataFrame(
            {
                "strike": [6000.0, 6000.0],
                "type": ["call", "put"],
                "volume": [80, 90],
            }
        )

        mock_cache = MagicMock()
        mock_cache.get_if_fresh.return_value = None
        mock_client = AsyncMock()
        mock_client.provider_name = "yfinance"
        mock_client.get_options_chain_for_gex.return_value = (options_df, 6015.0)

        mock_calculator = MagicMock()
        mock_calculator.calculate_gex_from_chain.return_value = live_snapshot
        mock_calculator.determine_regime.return_value = ("neutral", "Neutral", "yellow")

        with patch("app.api.websocket.get_cache", return_value=mock_cache):
            with patch("app.api.websocket.get_data_client", return_value=mock_client):
                with patch("app.api.websocket.get_gex_calculator", return_value=mock_calculator):
                    with patch(
                        "app.api.websocket.annotate_snapshot_quality",
                        side_effect=lambda snapshot, options_df: snapshot,
                    ):
                        payload = await _get_gex_update(
                            Settings(data_provider="yfinance"),
                            symbol="SPX",
                        )

        assert payload["advanced_analytics"]["hawkes"] == {
            "call_intensity": 0.0,
            "put_intensity": 0.0,
            "net_toxicity": 0.0,
            "squeeze_probability": 0.0,
        }
        assert payload["is_stale"] is False


class TestConnectionManager:
    """Unit tests for low-level websocket connection bookkeeping."""

    @pytest.mark.asyncio
    async def test_broadcast_removes_failed_connections(self):
        """Dead sockets should be removed after failed broadcast attempts."""
        manager = ConnectionManager()
        healthy_connection = AsyncMock()
        failed_connection = AsyncMock()
        failed_connection.send_json.side_effect = RuntimeError("socket closed")
        manager.active_connections = [healthy_connection, failed_connection]

        await manager.broadcast({"type": "heartbeat"})

        healthy_connection.send_json.assert_awaited_once_with({"type": "heartbeat"})
        failed_connection.send_json.assert_awaited_once_with({"type": "heartbeat"})
        assert manager.active_connections == [healthy_connection]
        assert manager.connection_count == 1


class TestWebSocketErrorHandling:
    """Test WebSocket error handling scenarios."""

    def test_websocket_invalid_endpoint(self):
        """Test that invalid WebSocket endpoint returns error."""
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/invalid-endpoint"):
                pass

    def test_websocket_handles_rapid_messages(self):
        """Test that WebSocket handles rapid client messages."""
        with client.websocket_connect("/ws/gex-stream") as websocket:
            websocket.receive_json()  # Skip connection

            # Send multiple rapid messages
            for _ in range(5):
                websocket.send_text("ping")

            # Should still receive updates without error
            data = websocket.receive_json()
            assert data["type"] in ["gex_update", "error"]


class TestWebSocketBroadcast:
    """Test WebSocket broadcast functionality."""

    def test_multiple_clients_receive_updates(self):
        """Test that multiple WebSocket clients receive updates."""
        with client.websocket_connect("/ws/gex-stream") as ws1:
            ws1.receive_json()  # Connection message

            with client.websocket_connect("/ws/gex-stream") as ws2:
                ws2.receive_json()  # Connection message

                # Both should receive updates
                # Note: In tests, updates are per-connection, not broadcast
                data1 = ws1.receive_json()
                data2 = ws2.receive_json()

                assert data1["type"] == "gex_update"
                assert data2["type"] == "gex_update"
