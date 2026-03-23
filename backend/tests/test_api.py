"""0DTE GEX Backend - API Tests."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
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

    def test_strikes_refreshes_when_cached_snapshot_is_stale(self):
        """Strike breakdown should prefer a fresh live snapshot over stale cache data."""
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
        fresh_snapshot = {
            "timestamp": "2099-01-15T10:35:00-05:00",
            "spot_price": 6575.0,
            "total_call_gex": -3.0,
            "total_put_gex": 2.0,
            "net_gex": -1.0,
            "zero_gamma_level": 6570.0,
            "gex_by_strike": {"6570.0": 4.0, "6580.0": -5.0},
            "dominant_strike": 6580.0,
            "metrics": {},
        }
        mock_cache = MagicMock()
        mock_cache.get_if_fresh.return_value = None
        mock_cache.get.side_effect = (
            lambda key: stale_snapshot if key == "gex:current:SPX:yfinance" else None
        )

        with patch("app.api.routes.gex.get_cache", return_value=mock_cache):
            with patch("app.api.routes.gex.get_settings") as mock_get_settings:
                mock_get_settings.return_value.data_provider = "yfinance"
                with patch(
                    "app.api.routes.gex._get_live_gex_snapshot",
                    new_callable=AsyncMock,
                ) as mock_live_snapshot:
                    mock_live_snapshot.return_value = fresh_snapshot
                    response = client.get("/api/gex/strikes")

        assert response.status_code == 200
        assert response.json()["spot_price"] == 6575.0
        mock_live_snapshot.assert_awaited_once()

    def test_current_gex_uses_symbol_scoped_legacy_cache_key(self):
        """Default-provider cache fallback should stay symbol-specific."""
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

        with patch("app.api.routes.gex.get_cache", return_value=mock_cache):
            with patch("app.api.routes.gex.get_settings") as mock_get_settings:
                mock_get_settings.return_value.data_provider = "yfinance"
                with patch(
                    "app.api.routes.gex._get_live_gex_snapshot",
                    new_callable=AsyncMock,
                ) as mock_live_snapshot:
                    mock_live_snapshot.return_value = cached_snapshot
                    response = client.get("/api/gex/current?symbol=QQQ")

        assert response.status_code == 200
        mock_cache.get_if_fresh.assert_any_call("gex:current:QQQ")
        mock_live_snapshot.assert_not_awaited()


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

    def test_providers_endpoint_includes_availability_metadata(self):
        """Provider metadata should expose runtime availability for the UI."""
        response = client.get("/api/data/providers")

        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert "active_default" in data
        assert data["providers"]
        for provider in data["providers"]:
            assert "is_available" in provider
            assert "unavailable_reason" in provider

    def test_options_chain_uses_snapshot_and_spot_price_for_provider_requests(self):
        """Options chain should fetch an explicit expiration via snapshot path."""
        mock_client = MagicMock()
        mock_client.provider_name = "tradier"
        mock_client.get_options_chain_snapshot = AsyncMock(
            return_value=pd.DataFrame(
                [
                    {
                        "symbol": "SPXW20990115C05000000",
                        "strike": 5000.0,
                        "expiration": date(2099, 1, 15),
                        "type": "call",
                        "bid": 10.0,
                        "ask": 12.0,
                        "mid": 11.0,
                        "open_interest": 100,
                        "volume": 50,
                        "implied_vol": 0.21,
                    }
                ]
            )
        )
        mock_client.get_spot_price = AsyncMock(return_value=5005.0)
        mock_client.close = AsyncMock()

        mock_cache = MagicMock()
        mock_cache.get_if_fresh.return_value = None
        mock_cache.get.return_value = None

        with patch("app.api.routes.data.get_data_client", return_value=mock_client) as mock_get_client:
            with patch("app.api.routes.data.get_cache", return_value=mock_cache):
                response = client.get(
                    "/api/data/options-chain",
                    params={"provider": "tradier", "expiration": "2099-01-15"},
                )

        assert response.status_code == 200
        mock_get_client.assert_called_once_with("tradier")
        mock_client.get_options_chain_snapshot.assert_awaited_once_with(
            underlying="SPX",
            expiration_date=date(2099, 1, 15),
        )
        mock_client.get_spot_price.assert_awaited_once_with(symbol="SPX")
        mock_client.close.assert_not_awaited()

    def test_spot_price_keeps_registry_managed_provider_open(self):
        """Spot price requests should not close registry-managed providers."""
        mock_client = MagicMock()
        mock_client.provider_name = "tradier"
        mock_client.get_spot_price = AsyncMock(return_value=5001.25)
        mock_client.close = AsyncMock()

        mock_cache = MagicMock()
        mock_cache.get_if_fresh.return_value = None
        mock_cache.get.return_value = None

        with patch("app.api.routes.data.get_data_client", return_value=mock_client):
            with patch("app.api.routes.data.get_cache", return_value=mock_cache):
                response = client.get(
                    "/api/data/spot-price",
                    params={"provider": "tradier", "symbol": "SPX"},
                )

        assert response.status_code == 200
        assert response.json()["provider"] == "tradier"
        mock_client.get_spot_price.assert_awaited_once_with(symbol="SPX")
        mock_client.close.assert_not_awaited()

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
