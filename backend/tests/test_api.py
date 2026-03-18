"""0DTE GEX Backend - API Tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestHealthEndpoints:
    """Test health and root endpoints."""

    def test_root_endpoint(self):
        """Root should return API info."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "0DTE GEX API"
        assert "version" in data

    def test_health_check(self):
        """Health check should return healthy status."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestGEXEndpoints:
    """Test GEX API endpoints."""

    def test_current_gex_returns_valid_response(self):
        """Current GEX should return 200 with mock data (no API key)."""
        response = client.get("/api/gex/current")

        # Without API key, should return mock data with 200
        # or 503 if trying to fetch real data fails
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "net_gex" in data
            assert "spot_price" in data
            assert "zero_gamma_level" in data
            assert "gex_by_strike" in data

    def test_regime_returns_valid_response(self):
        """Regime endpoint should return valid regime data."""
        response = client.get("/api/gex/regime")

        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "regime" in data
            assert data["regime"] in ["short_gamma", "long_gamma", "neutral"]
            assert "net_gex" in data
            assert "color" in data

    def test_historical_gex_requires_dates(self):
        """Historical GEX requires start_date and end_date params."""
        response = client.get("/api/gex/historical")

        # Should fail validation without required params
        assert response.status_code == 422

    def test_historical_gex_with_dates(self):
        """Historical GEX with valid dates returns data."""
        response = client.get(
            "/api/gex/historical",
            params={"start_date": "2024-01-01", "end_date": "2024-01-15"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "count" in data

    def test_strikes_returns_valid_response(self):
        """Strikes endpoint should return sorted strike data."""
        response = client.get("/api/gex/strikes")

        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "strikes" in data
            assert "gex_values" in data
            assert "spot_price" in data
            assert len(data["strikes"]) == len(data["gex_values"])


class TestDataEndpoints:
    """Test Data API endpoints."""

    def test_market_status(self):
        """Market status should return current status."""
        response = client.get("/api/data/market-status")

        assert response.status_code == 200
        data = response.json()
        assert "is_open" in data
        assert "status" in data
        assert data["status"] in ["open", "pre_market", "after_hours", "closed_weekend"]
        assert "current_time_et" in data

    def test_options_chain_endpoint(self):
        """Options chain should return data via YFinance (no API key required)."""
        response = client.get("/api/data/options-chain")
        # YFinance may succeed (200) or have network issues (503)
        assert response.status_code in (200, 503)

    def test_spot_price_endpoint(self):
        """Spot price should return data via YFinance (no API key required)."""
        response = client.get("/api/data/spot-price")
        # YFinance may succeed (200) or have network issues (503)
        assert response.status_code in (200, 503)


class TestAnalyticsEndpoints:
    """Test Analytics API endpoints."""

    def test_summary_statistics(self):
        """Summary statistics should work with default dates."""
        response = client.get("/api/analytics/summary-statistics")

        assert response.status_code == 200
        data = response.json()
        assert "mean_gex" in data
        assert "std_gex" in data
        assert "sample_size" in data

    def test_gex_volatility_requires_dates(self):
        """GEX volatility analysis requires date range."""
        response = client.get("/api/analytics/gex-volatility")

        # Should fail validation without required params
        assert response.status_code == 422

    def test_gex_volatility_with_dates(self):
        """GEX volatility with valid dates returns analysis."""
        response = client.get(
            "/api/analytics/gex-volatility",
            params={"start_date": "2024-01-01", "end_date": "2024-01-15"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "mean_rv_negative_gex" in data
        assert "mean_rv_positive_gex" in data
        assert "p_value" in data

    def test_backtest_requires_dates(self):
        """Backtest requires start and end dates."""
        response = client.get("/api/analytics/backtest")

        # Should fail validation without required params
        assert response.status_code == 422

    def test_backtest_with_valid_params(self):
        """Backtest with valid params returns results."""
        response = client.get(
            "/api/analytics/backtest",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-15",
                "entry_threshold": -1e9,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_trades" in data
        assert "win_rate" in data
        assert "sharpe_ratio" in data


class TestWebSocketEndpoints:
    """Test WebSocket connection endpoints."""

    def test_websocket_connections_endpoint(self):
        """Connections count endpoint should work."""
        response = client.get("/ws/connections")

        assert response.status_code == 200
        data = response.json()
        assert "active_connections" in data
        assert isinstance(data["active_connections"], int)
