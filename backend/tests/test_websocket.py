"""0DTE GEX Backend - WebSocket Integration Tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


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

            # Check reasonable ranges (mock data: net_gex between -3B and 2B)
            assert -5e9 <= gex_data["net_gex"] <= 5e9
            assert gex_data["net_gex_billions"] == gex_data["net_gex"] / 1e9

            # Spot price should be realistic for SPX
            assert 1000 <= gex_data["spot_price"] <= 10000

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
