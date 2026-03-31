"""0DTE GEX Backend - API Tests."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.routes import gex as gex_routes
from app.core.advanced_analytics import reset_advanced_analytics_state
from app.main import app
from app.models.schemas import GEXSnapshot

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

    @pytest.mark.parametrize(
        ("path", "assertion"),
        [
            ("/api/gex/current", lambda body: body["spot_price"] == 5000.0),
            ("/api/gex/strikes", lambda body: body["spot_price"] == 5000.0),
            ("/api/gex/regime", lambda body: body["regime"] == "short_gamma"),
        ],
    )
    def test_live_gex_routes_use_resolved_provider_for_snapshot_fetch(self, path, assertion):
        """Live GEX routes should pass the resolved provider into the live snapshot helper."""
        snapshot = {
            "timestamp": "2099-01-15T10:30:00-05:00",
            "spot_price": 5000.0,
            "total_call_gex": -2.0,
            "total_put_gex": 1.0,
            "net_gex": -1.1e9,
            "zero_gamma_level": 4995.0,
            "gex_by_strike": {"5000.0": -3.0},
            "dominant_strike": 5000.0,
            "metrics": {},
        }
        mock_cache = MagicMock()
        mock_cache.get_if_fresh.return_value = None

        with patch("app.api.routes.gex.get_cache", return_value=mock_cache):
            with patch("app.api.routes.gex.get_settings") as mock_get_settings:
                mock_get_settings.return_value.data_provider = "tradier"
                with patch(
                    "app.api.routes.gex._get_live_gex_snapshot",
                    new_callable=AsyncMock,
                ) as mock_live_snapshot:
                    mock_live_snapshot.return_value = snapshot
                    response = client.get(path)

        assert response.status_code == 200
        assert assertion(response.json())
        mock_live_snapshot.assert_awaited_once_with("SPX", "tradier")

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

    def test_current_gex_returns_503_when_live_cache_and_persisted_fallbacks_all_fail(self):
        """Current GEX should fail cleanly when no live, stale, or persisted data exists."""
        mock_cache = MagicMock()
        mock_cache.get_if_fresh.return_value = None
        mock_cache.get.return_value = None

        with patch("app.api.routes.gex.get_cache", return_value=mock_cache):
            with patch("app.api.routes.gex.get_settings") as mock_get_settings:
                mock_get_settings.return_value.data_provider = "yfinance"
                with patch(
                    "app.api.routes.gex._get_live_gex_snapshot",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("provider unavailable"),
                ):
                    with patch(
                        "app.api.routes.gex._get_latest_persisted_snapshot",
                        new_callable=AsyncMock,
                        return_value=None,
                    ):
                        response = client.get("/api/gex/current")

        assert response.status_code == 503
        assert "Unable to fetch GEX data" in response.json()["detail"]

    def test_live_fetch_timeout_is_extended_for_tradier(self):
        """Tradier live fetches should get more time than the default providers."""
        assert gex_routes.get_live_fetch_timeout_seconds("tradier") > 4
        assert gex_routes.get_live_fetch_timeout_seconds("yfinance") == 4

    @pytest.mark.asyncio
    async def test_live_snapshot_includes_hawkes_analytics_even_on_first_baseline(self):
        """Live snapshot payloads should always expose Hawkes state, including neutral zero baselines."""
        reset_advanced_analytics_state()
        options_df = pd.DataFrame(
            {
                "strike": [5800.0, 5800.0],
                "type": ["call", "put"],
                "volume": [100, 120],
            }
        )
        live_snapshot = GEXSnapshot(
            timestamp=pd.Timestamp("2026-03-27T10:30:00-04:00").to_pydatetime(),
            spot_price=5805.0,
            total_call_gex=-2.0e8,
            total_put_gex=1.5e8,
            net_gex=-5.0e7,
            zero_gamma_level=5795.0,
            gex_by_strike={5800.0: -5.0e7},
            dominant_strike=5800.0,
            metrics={},
            advanced_analytics=None,
        )

        mock_client = MagicMock()
        mock_client.provider_name = "tradier"
        mock_client.get_options_chain_for_gex = AsyncMock(return_value=(options_df, 5805.0))

        mock_calculator = MagicMock()
        mock_calculator.calculate_gex_from_chain.return_value = live_snapshot

        with patch("app.api.routes.gex.get_data_client", return_value=mock_client):
            with patch("app.api.routes.gex.get_gex_calculator", return_value=mock_calculator):
                with patch(
                    "app.api.routes.gex.annotate_snapshot_quality",
                    side_effect=lambda snapshot, options_df, provider=None: snapshot,
                ):
                    payload = await gex_routes._get_live_gex_snapshot("SPX", "tradier")

        assert payload["provider"] == "tradier"
        hawkes_payload = payload["advanced_analytics"]["hawkes"]
        assert hawkes_payload["call_intensity"] == 0.0
        assert hawkes_payload["put_intensity"] == 0.0
        assert hawkes_payload["net_toxicity"] == 0.0
        assert hawkes_payload["squeeze_probability"] == 0.0
        assert hawkes_payload["baseline_ready"] is False
        assert hawkes_payload["provider_mode"] == "tradier_rich"
        assert hawkes_payload["event_count"] == 0
        assert 0.0 < hawkes_payload["confidence_score"] < 1.0

    @pytest.mark.asyncio
    async def test_live_snapshot_exposes_provider_metadata_once_baseline_is_ready(self):
        """Live payloads should expose baseline/confidence metadata after consecutive snapshots."""
        reset_advanced_analytics_state()
        first_df = pd.DataFrame(
            {
                "strike": [6000.0],
                "type": ["call"],
                "volume": [70],
                "open_interest": [180],
                "bid": [9.8],
                "ask": [10.2],
                "mid": [10.0],
                "implied_vol": [0.21],
                "delta": [None],
                "gamma": [None],
                "expiration": ["2099-01-15T16:00:00-05:00"],
            }
        )
        second_df = pd.DataFrame(
            {
                "strike": [6000.0],
                "type": ["call"],
                "volume": [105],
                "open_interest": [205],
                "bid": [10.0],
                "ask": [10.5],
                "mid": [10.25],
                "implied_vol": [0.22],
                "delta": [None],
                "gamma": [None],
                "expiration": ["2099-01-15T16:00:00-05:00"],
            }
        )
        live_snapshot = GEXSnapshot(
            timestamp=pd.Timestamp("2026-03-28T10:30:00-04:00").to_pydatetime(),
            spot_price=6030.0,
            total_call_gex=-2.0e8,
            total_put_gex=1.5e8,
            net_gex=-5.0e7,
            zero_gamma_level=6010.0,
            gex_by_strike={6000.0: -5.0e7},
            dominant_strike=6000.0,
            metrics={},
            advanced_analytics=None,
        )

        mock_client = MagicMock()
        mock_client.provider_name = "yfinance"
        mock_client.get_options_chain_for_gex = AsyncMock(
            side_effect=[(first_df, 6030.0), (second_df, 6030.0)]
        )
        mock_client._get_ticker_symbol = lambda symbol: "SPY"

        mock_calculator = MagicMock()
        mock_calculator.calculate_gex_from_chain.side_effect = [live_snapshot, live_snapshot.model_copy(deep=True)]

        with patch("app.api.routes.gex.get_data_client", return_value=mock_client):
            with patch("app.api.routes.gex.get_gex_calculator", return_value=mock_calculator):
                with patch(
                    "app.api.routes.gex.annotate_snapshot_quality",
                    side_effect=lambda snapshot, options_df, provider=None: snapshot,
                ):
                    await gex_routes._get_live_gex_snapshot("SPX", "yfinance")
                    payload = await gex_routes._get_live_gex_snapshot("SPX", "yfinance")

        hawkes_payload = payload["advanced_analytics"]["hawkes"]
        assert hawkes_payload["baseline_ready"] is True
        assert hawkes_payload["provider_mode"] == "yfinance_proxy"
        assert 0.0 < hawkes_payload["confidence_score"] < 0.8
        assert hawkes_payload["event_count"] == 1

    def test_current_gex_low_quality_live_snapshot_uses_persisted_fallback_without_cache_write(self):
        """Low-quality live snapshots should not replace usable provider-specific fallback data."""
        low_quality_snapshot = {
            "timestamp": "2099-01-15T10:30:00-05:00",
            "spot_price": 6530.0,
            "total_call_gex": -1.0e12,
            "total_put_gex": 0.0,
            "net_gex": -1.0e12,
            "zero_gamma_level": 5250.0,
            "gex_by_strike": {"6530.0": -1.0e12},
            "dominant_strike": 6530.0,
            "metrics": {
                "capture_quality": 0.0,
                "meaningful_strike_count": 1.0,
                "is_replay_eligible": 0.0,
            },
        }
        persisted_snapshot = {
            "timestamp": "2099-01-15T10:25:00-05:00",
            "spot_price": 6025.0,
            "total_call_gex": -2.0e9,
            "total_put_gex": 1.4e9,
            "net_gex": -6.0e8,
            "zero_gamma_level": 6010.0,
            "gex_by_strike": {"6000.0": 2.0e8, "6025.0": -3.5e8},
            "dominant_strike": 6025.0,
            "metrics": {"capture_quality": 0.95, "is_replay_eligible": 1.0},
        }
        mock_cache = MagicMock()
        mock_cache.get_if_fresh.return_value = None
        mock_cache.get.return_value = None

        with patch("app.api.routes.gex.get_cache", return_value=mock_cache):
            with patch("app.api.routes.gex.get_settings") as mock_get_settings:
                mock_get_settings.return_value.data_provider = "yfinance"
                with patch(
                    "app.api.routes.gex._get_live_gex_snapshot",
                    new_callable=AsyncMock,
                    return_value=low_quality_snapshot,
                ):
                    with patch(
                        "app.api.routes.gex._get_latest_persisted_snapshot",
                        new_callable=AsyncMock,
                        return_value=GEXSnapshot(**persisted_snapshot),
                    ):
                        response = client.get("/api/gex/current?provider=yfinance")

        assert response.status_code == 200
        body = response.json()
        assert body["spot_price"] == 6025.0
        assert body["metrics"]["is_persisted_fallback"] == 1.0
        mock_cache.set.assert_not_called()

    def test_regime_prefers_stale_cache_before_persisted_fallback(self):
        """Regime should derive from stale cache before jumping to persisted DB history."""
        stale_snapshot = {
            "timestamp": "2099-01-15T10:30:00-05:00",
            "spot_price": 5900.0,
            "total_call_gex": -2.0,
            "total_put_gex": 1.0,
            "net_gex": -1.2e9,
            "zero_gamma_level": 5890.0,
            "gex_by_strike": {"5900.0": -5.0},
            "dominant_strike": 5900.0,
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
                    side_effect=RuntimeError("live fetch failed"),
                ):
                    with patch(
                        "app.api.routes.gex._get_latest_persisted_snapshot",
                        new_callable=AsyncMock,
                        side_effect=AssertionError("persisted fallback should not be used"),
                    ):
                        response = client.get("/api/gex/regime")

        assert response.status_code == 200
        body = response.json()
        assert body["regime"] == "short_gamma"
        assert body["net_gex"] == -1.2e9

    def test_strikes_falls_back_to_persisted_snapshot_when_live_fetch_fails(self):
        """Strike breakdown should use persisted history when live fetch fails and cache is empty."""
        persisted_snapshot = {
            "timestamp": "2099-01-15T10:30:00-05:00",
            "spot_price": 6012.0,
            "total_call_gex": -2.0,
            "total_put_gex": 1.0,
            "net_gex": -1.0e9,
            "zero_gamma_level": 6005.0,
            "gex_by_strike": {6000.0: -3.0, 6010.0: 5.5},
            "dominant_strike": 6010.0,
            "metrics": {},
        }
        mock_cache = MagicMock()
        mock_cache.get_if_fresh.return_value = None
        mock_cache.get.return_value = None

        with patch("app.api.routes.gex.get_cache", return_value=mock_cache):
            with patch("app.api.routes.gex.get_settings") as mock_get_settings:
                mock_get_settings.return_value.data_provider = "yfinance"
                with patch(
                    "app.api.routes.gex._get_live_gex_snapshot",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("provider unavailable"),
                ):
                    with patch(
                        "app.api.routes.gex._get_latest_persisted_snapshot",
                        new_callable=AsyncMock,
                        return_value=GEXSnapshot(**persisted_snapshot),
                    ):
                        response = client.get("/api/gex/strikes")

        assert response.status_code == 200
        body = response.json()
        assert body["strikes"] == [6000.0, 6010.0]
        assert body["gex_values"] == [-3.0, 5.5]
        assert body["spot_price"] == 6012.0

    def test_historical_gex_rejects_inverted_date_range(self):
        """Historical endpoint should reject start dates that come after end dates."""
        response = client.get(
            "/api/gex/historical",
            params={"start_date": "2026-03-10", "end_date": "2026-03-01"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "start_date must be before or equal to end_date"

    def test_historical_gex_rejects_ranges_longer_than_one_year(self):
        """Historical endpoint should reject ranges longer than 365 days."""
        response = client.get(
            "/api/gex/historical",
            params={"start_date": "2024-01-01", "end_date": "2025-01-02"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Date range cannot exceed 365 days"


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
