"""Expanded tests for Analytics API routes.

Tests IV-surface, technical-indicators, vectorbt-backtest endpoints
including parameter validation, error handling, and response schemas.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.provider_registry import ProviderUnavailableError
from app.core.rate_provider import RiskFreeRateProvider
from app.main import app
from app.models.schemas import GEXSnapshot

client = TestClient(app)


@pytest.fixture(autouse=True)
def offline_rate_provider(monkeypatch):
    provider = RiskFreeRateProvider()
    monkeypatch.setattr(provider, "_fetch_from_fred", lambda: 0.05)
    monkeypatch.setattr("app.core.rate_provider.get_rate_provider", lambda: provider)


@pytest.fixture(autouse=True)
def empty_analytics_history(monkeypatch):
    history = MagicMock()
    history.get_iv_surface = AsyncMock(return_value=None)
    history.get_latest_snapshot = AsyncMock(return_value=None)
    history.get_technical_indicators = AsyncMock(return_value=None)
    history.get_time_series_frames = AsyncMock(return_value=(pd.DataFrame(), pd.DataFrame()))
    monkeypatch.setattr("app.api.routes.analytics.get_historical_data_service", lambda: history)


def _build_snapshot(
    *,
    spot_price: float,
    net_gex: float,
    zero_gamma_level: float,
) -> GEXSnapshot:
    return GEXSnapshot(
        timestamp="2026-03-25T10:30:00-04:00",
        spot_price=spot_price,
        total_call_gex=-abs(net_gex) - 2.0e8,
        total_put_gex=2.0e8,
        net_gex=net_gex,
        zero_gamma_level=zero_gamma_level,
        gex_by_strike={float(round(spot_price)): net_gex / 4},
        dominant_strike=float(round(spot_price)),
        metrics={"capture_quality": 0.99},
    )


# ---------------------------------------------------------------------------
# /api/data/risk-free-rate
# ---------------------------------------------------------------------------


class TestRiskFreeRateEndpoint:
    """Tests for GET /api/data/risk-free-rate."""

    def test_returns_200(self):
        resp = client.get("/api/data/risk-free-rate")
        assert resp.status_code == 200

    def test_response_schema(self):
        resp = client.get("/api/data/risk-free-rate")
        body = resp.json()
        assert "rate" in body
        assert "rate_pct" in body
        assert "source" in body
        assert "symbol" in body
        assert "is_fallback" in body
        assert "cache_ttl_seconds" in body

    def test_rate_is_decimal(self):
        resp = client.get("/api/data/risk-free-rate")
        rate = resp.json()["rate"]
        assert 0.0 < rate < 1.0

    def test_rate_pct_matches(self):
        resp = client.get("/api/data/risk-free-rate")
        body = resp.json()
        assert abs(body["rate_pct"] - body["rate"] * 100) < 0.001


# ---------------------------------------------------------------------------
# /api/analytics/iv-surface
# ---------------------------------------------------------------------------


class TestIVSurfaceEndpoint:
    """Tests for GET /api/analytics/iv-surface."""

    def _mock_options_df(self):
        return pd.DataFrame(
            {
                "contractType": ["call", "put", "call", "put"],
                "strike": [580.0, 580.0, 590.0, 590.0],
                "lastPrice": [10.0, 5.0, 5.5, 9.0],
                "bid": [9.8, 4.8, 5.3, 8.8],
                "ask": [10.2, 5.2, 5.7, 9.2],
                "impliedVolatility": [0.22, 0.20, 0.18, 0.24],
                "openInterest": [1000, 800, 1200, 900],
                "expiration": ["2099-01-15"] * 4,
                "T": [0.01] * 4,
            }
        )

    def test_missing_symbol_uses_default(self):
        """Should return valid response when symbol is omitted (defaults to SPY)."""
        mock_df = self._mock_options_df()
        mock_df["type"] = mock_df["contractType"]
        mock_df["implied_vol"] = mock_df["impliedVolatility"]
        mock_df["open_interest"] = mock_df["openInterest"]

        with patch("app.api.routes.analytics.get_data_client") as mock_client_cls:
            instance = AsyncMock()
            instance.get_options_chain_for_gex = AsyncMock(return_value=(mock_df, 585.0))
            mock_client_cls.return_value = instance

            resp = client.get("/api/analytics/iv-surface")
            assert resp.status_code == 200

    def test_empty_provider_chain_returns_an_empty_surface(self):
        with patch("app.api.routes.analytics.get_data_client") as mock_client_cls:
            instance = AsyncMock()
            # Return empty DF to simulate no data for invalid symbol
            instance.get_options_chain_for_gex = AsyncMock(return_value=(pd.DataFrame(), 0.0))
            mock_client_cls.return_value = instance

            resp = client.get("/api/analytics/iv-surface?symbol=XXXXINVALID")
            assert resp.status_code == 200
            assert resp.json()["count"] == 0
            assert resp.json()["surface"] == []

    def test_provider_param_keeps_registry_managed_client_open(self):
        """IV surface should honor provider selection without closing the cached provider."""
        mock_df = pd.DataFrame(
            [
                {
                    "symbol": "SPXW20990115C05000000",
                    "strike": 5000.0,
                    "expiration": "2099-01-15",
                    "type": "call",
                    "bid": 10.0,
                    "ask": 12.0,
                    "mid": 11.0,
                    "T": 0.01,
                    "implied_vol": 0.2,
                    "open_interest": 100,
                }
            ]
        )
        mock_client = MagicMock()
        mock_client.provider_name = "tradier"
        mock_client.get_options_chain_for_gex = AsyncMock(return_value=(mock_df, 5005.0))
        mock_client.close = AsyncMock()

        with patch(
            "app.api.routes.analytics.get_data_client", return_value=mock_client
        ) as mock_get_client:
            with patch(
                "app.api.routes.analytics.get_historical_data_service"
            ) as mock_history_service:
                mock_history_service.return_value.get_iv_surface = AsyncMock(return_value=None)
                with patch(
                    "app.core.vollib_bridge.VolLibBridge.calculate_iv_surface",
                    return_value=mock_df[["strike", "type", "implied_vol", "mid"]]
                    .rename(columns={"implied_vol": "iv", "mid": "mid_price"})
                    .assign(moneyness=1.0),
                ):
                    with patch(
                        "app.core.vollib_bridge.VolLibBridge.calculate_iv_skew",
                        return_value=pd.DataFrame(),
                    ):
                        with patch(
                            "app.core.rate_provider.get_rate_provider"
                        ) as mock_rate_provider:
                            mock_rate_provider.return_value.get_rate.return_value = 0.05
                            resp = client.get("/api/analytics/iv-surface?provider=tradier")

        assert resp.status_code == 200
        mock_get_client.assert_called_once_with("tradier")
        mock_client.close.assert_not_awaited()

    def test_invalid_provider_returns_400(self):
        """Invalid provider names should be treated as client input errors."""
        with patch(
            "app.api.routes.analytics.get_data_client",
            side_effect=ValueError("Unknown provider 'bogus'"),
        ):
            resp = client.get("/api/analytics/iv-surface?provider=bogus")

        assert resp.status_code == 400
        assert "Unknown provider" in resp.json()["detail"]

    def test_unavailable_provider_returns_503(self):
        """Unavailable providers should surface as service failures."""
        with patch("app.api.routes.analytics.get_historical_data_service") as mock_history_service:
            mock_history_service.return_value.get_iv_surface = AsyncMock(return_value=None)
            with patch(
                "app.api.routes.analytics.get_data_client",
                side_effect=ProviderUnavailableError(
                    "TRADIER_API_KEY environment variable is missing"
                ),
            ):
                resp = client.get("/api/analytics/iv-surface?provider=tradier")

        assert resp.status_code == 503
        assert "TRADIER_API_KEY" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# /api/analytics/technical-indicators
# ---------------------------------------------------------------------------


class TestTechnicalIndicatorsEndpoint:
    """Tests for GET /api/analytics/technical-indicators."""

    @pytest.mark.integration
    def test_valid_request_returns_200_or_503(self):
        """Should return 200 with indicators or 503 if data unavailable."""
        resp = client.get(
            "/api/analytics/technical-indicators?symbol=SPY&period=5d&interval=1d&indicators=ATR"
        )
        assert resp.status_code in (200, 503)

    @pytest.mark.integration
    def test_response_schema_on_success(self):
        """On 200 response, schema must contain required fields."""
        resp = client.get("/api/analytics/technical-indicators?symbol=SPY&period=5d&interval=1d")
        if resp.status_code == 200:
            body = resp.json()
            assert "symbol" in body
            assert "data" in body
            assert "count" in body
            assert "indicators" in body

    @pytest.mark.integration
    def test_invalid_period_raises_validation_error(self):
        """Unexpected parameter format should be gracefully handled."""
        resp = client.get("/api/analytics/technical-indicators?symbol=BAD&period=999z")
        # Accepts 200, 422, 503 — just no 500 internal unhandled
        assert resp.status_code != 500

    @pytest.mark.integration
    def test_multiple_indicators_requested(self):
        """Should accept comma-separated indicators string."""
        resp = client.get(
            "/api/analytics/technical-indicators?symbol=SPY&indicators=ATR,RSI,BBANDS"
        )
        assert resp.status_code in (200, 503)

    def test_demo_mode_falls_back_to_synthetic_when_real_history_is_unavailable(self):
        """Demo mode should synthesize usable indicators when persisted and real history are both unusable."""
        persisted_payload = {
            "symbol": "SPY",
            "period": "1mo",
            "indicators": ["ATR", "RSI", "BBANDS"],
            "count": 1,
            "data": [
                {
                    "timestamp": "2026-03-25T10:30:00-04:00",
                    "close": 590.0,
                    "atr": None,
                    "rsi": None,
                    "bb_upper": None,
                    "bb_mid": None,
                    "bb_lower": None,
                }
            ],
        }
        synthetic_payload = {
            "symbol": "SPY",
            "period": "1mo",
            "indicators": ["ATR", "RSI", "BBANDS"],
            "count": 2,
            "data": [
                {
                    "timestamp": "2026-03-25T10:30:00-04:00",
                    "close": 590.0,
                    "atr": 4.2,
                    "rsi": 51.0,
                    "bb_upper": 594.0,
                    "bb_mid": 590.0,
                    "bb_lower": 586.0,
                },
                {
                    "timestamp": "2026-03-25T10:31:00-04:00",
                    "close": 590.5,
                    "atr": 4.1,
                    "rsi": 52.0,
                    "bb_upper": 594.2,
                    "bb_mid": 590.2,
                    "bb_lower": 586.2,
                },
            ],
        }
        history_service = MagicMock()
        history_service.get_technical_indicators = AsyncMock(return_value=persisted_payload)
        history_service.get_latest_snapshot = AsyncMock(
            return_value=_build_snapshot(
                spot_price=590.0,
                net_gex=-5.5e8,
                zero_gamma_level=588.5,
            )
        )

        class _AnchoredDemoService:
            def get_technical_indicators(
                self,
                *,
                symbol,
                period,
                interval,
                indicators,
                now=None,
                anchor_snapshot,
            ):
                assert symbol == "SPY"
                assert period == "1mo"
                assert interval == "1d"
                assert indicators == ["ATR", "RSI", "BBANDS"]
                assert anchor_snapshot.spot_price == 590.0
                return synthetic_payload

        with patch(
            "app.api.routes.analytics.get_historical_data_service", return_value=history_service
        ):
            with patch(
                "app.api.routes.analytics.get_demo_data_service",
                return_value=_AnchoredDemoService(),
            ):
                with patch(
                    "app.api.routes.analytics._load_yfinance_history",
                    return_value=pd.DataFrame(),
                ):
                    resp = client.get(
                        "/api/analytics/technical-indicators",
                        params={
                            "demo": "true",
                            "symbol": "SPY",
                            "period": "1mo",
                            "interval": "1d",
                            "indicators": "ATR,RSI,BBANDS",
                        },
                    )

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        assert body["data"][0]["atr"] == 4.2
        assert body["data"][0]["rsi"] == 51.0
        assert body["data"][0]["bb_upper"] == 594.0

    def test_demo_mode_prefers_real_historical_price_data_for_indicator_chart(self):
        """Demo mode should use real historical price data when available."""
        history_service = MagicMock()
        history_service.get_technical_indicators = AsyncMock(return_value=None)
        history_service.get_latest_snapshot = AsyncMock(
            return_value=_build_snapshot(
                spot_price=590.0,
                net_gex=-5.5e8,
                zero_gamma_level=588.5,
            )
        )

        class _FailingDemoService:
            def get_technical_indicators(self, *args, **kwargs):
                raise AssertionError(
                    "synthetic fallback should not be used when real history is available"
                )

        market_history = pd.DataFrame(
            {
                "Open": [
                    585.0,
                    586.0,
                    587.0,
                    588.0,
                    589.0,
                    590.0,
                    591.0,
                    592.0,
                    593.0,
                    594.0,
                    595.0,
                    596.0,
                    597.0,
                    598.0,
                    599.0,
                    600.0,
                    601.0,
                    602.0,
                    603.0,
                    604.0,
                    605.0,
                    606.0,
                    607.0,
                    608.0,
                    609.0,
                ],
                "High": [
                    586.0,
                    587.0,
                    588.0,
                    589.0,
                    590.0,
                    591.0,
                    592.0,
                    593.0,
                    594.0,
                    595.0,
                    596.0,
                    597.0,
                    598.0,
                    599.0,
                    600.0,
                    601.0,
                    602.0,
                    603.0,
                    604.0,
                    605.0,
                    606.0,
                    607.0,
                    608.0,
                    609.0,
                    610.0,
                ],
                "Low": [
                    584.0,
                    585.0,
                    586.0,
                    587.0,
                    588.0,
                    589.0,
                    590.0,
                    591.0,
                    592.0,
                    593.0,
                    594.0,
                    595.0,
                    596.0,
                    597.0,
                    598.0,
                    599.0,
                    600.0,
                    601.0,
                    602.0,
                    603.0,
                    604.0,
                    605.0,
                    606.0,
                    607.0,
                    608.0,
                ],
                "Close": [
                    585.5,
                    586.5,
                    587.5,
                    588.5,
                    589.5,
                    590.5,
                    591.5,
                    592.5,
                    593.5,
                    594.5,
                    595.5,
                    596.5,
                    597.5,
                    598.5,
                    599.5,
                    600.5,
                    601.5,
                    602.5,
                    603.5,
                    604.5,
                    605.5,
                    606.5,
                    607.5,
                    608.5,
                    609.5,
                ],
                "Volume": [1_000_000] * 25,
            }
        )

        class _FakeTicker:
            def history(self, *args, **kwargs):
                return market_history

        def _build_fake_ticker(symbol):
            assert symbol == "SPY"
            return _FakeTicker()

        with patch(
            "app.api.routes.analytics.get_historical_data_service", return_value=history_service
        ):
            with patch(
                "app.api.routes.analytics.get_demo_data_service", return_value=_FailingDemoService()
            ):
                with patch("yfinance.Ticker", side_effect=_build_fake_ticker) as ticker:
                    resp = client.get(
                        "/api/analytics/technical-indicators",
                        params={
                            "demo": "true",
                            "symbol": "SPY",
                            "period": "1mo",
                            "interval": "1d",
                            "indicators": "ATR,RSI,BBANDS",
                        },
                    )

        assert resp.status_code == 200
        ticker.assert_called_once_with("SPY")
        body = resp.json()
        assert body["count"] == 25
        assert any(point["atr"] is not None for point in body["data"])
        assert any(point["rsi"] is not None for point in body["data"])
        assert any(point["bb_upper"] is not None for point in body["data"])


# ---------------------------------------------------------------------------
# /api/analytics/vectorbt-backtest
# ---------------------------------------------------------------------------


class TestVectorbtBacktestEndpoint:
    """Exercise real execution and response serialization from captured fixtures."""

    @pytest.fixture
    def captured_client(self, monkeypatch):
        from app.api.routes import analytics as routes

        index = pd.date_range("2025-01-06 09:30", periods=4, freq="5min", tz="America/New_York")
        prices = pd.DataFrame({"close": [100, 110, 99, 121]}, index=index)
        gex = pd.DataFrame({"net_gex": [-2e9, -2e9, 2e9, 2e9]}, index=index)
        history = MagicMock()
        history.get_time_series_frames = AsyncMock(return_value=(prices, gex))
        monkeypatch.setattr(routes, "get_historical_data_service", lambda: history)
        return TestClient(app), {
            "start_date": "2025-01-01",
            "end_date": "2025-03-01",
            "provider": "yfinance",
            "symbol": "SPY",
            "initial_cash": 1000,
            "fees": 0,
            "slippage": 0,
        }

    def test_serializes_completed_directional_trade_and_actual_equity(self, captured_client):
        fixture_client, params = captured_client
        response = fixture_client.get("/api/analytics/vectorbt-backtest", params=params)
        assert response.status_code == 200, response.json()
        body = response.json()
        assert body["total_return"] == pytest.approx(0.1)
        assert body["avg_trade_return"] == pytest.approx(0.1)
        assert body["total_trades"] == body["closed_trades"] == 1
        assert body["open_trades"] == body["losing_trades"] == 0
        assert body["winning_trades"] == 1
        assert body["profit_factor"] is None
        assert body["avg_trade_duration_minutes"] == 10
        assert body["equity_curve"] == pytest.approx([1000, 1000, 900, 1100])
        assert len(body["equity_timestamps"]) == 4
        assert body["bar_interval_minutes"] == 5
        assert body["provenance"]["data_kind"] == "captured"

    def test_request_costs_reduce_the_actual_equity(self, captured_client):
        fixture_client, params = captured_client
        response = fixture_client.get(
            "/api/analytics/vectorbt-backtest", params={**params, "fees": 0.01, "slippage": 0.02}
        )
        assert response.status_code == 200, response.json()
        assert response.json()["total_return"] == pytest.approx(0.035934769947582934)

    def test_invalid_date_order_is_a_client_error(self, captured_client):
        fixture_client, params = captured_client
        response = fixture_client.get(
            "/api/analytics/vectorbt-backtest", params={**params, "start_date": "2025-06-01"}
        )
        assert response.status_code == 400

    @pytest.mark.parametrize(
        "control,value", [("fees", -0.1), ("position_size", 0), ("execution_delay_bars", 0)]
    )
    def test_invalid_execution_controls_are_rejected(self, captured_client, control, value):
        fixture_client, params = captured_client
        response = fixture_client.get(
            "/api/analytics/vectorbt-backtest", params={**params, control: value}
        )
        assert response.status_code == 422


class TestSummaryStatsEdgeCases:
    """Missing captured history must produce an explicit absence response."""

    @pytest.mark.parametrize("params", [{}, {"start_date": "2025-01-01", "end_date": "2025-03-01"}])
    def test_missing_history_returns_404(self, monkeypatch, params):
        from app.api.routes import analytics as routes

        history = MagicMock()
        history.get_time_series_frames = AsyncMock(return_value=(pd.DataFrame(), pd.DataFrame()))
        monkeypatch.setattr(routes, "get_historical_data_service", lambda: history)
        response = client.get("/api/analytics/summary-statistics", params=params)
        assert response.status_code == 404
        assert "history" in response.json()["detail"].lower()
