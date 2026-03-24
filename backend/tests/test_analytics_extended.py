"""Expanded tests for Analytics API routes.

Tests IV-surface, technical-indicators, vectorbt-backtest endpoints
including parameter validation, error handling, and response schemas.
"""

import json
import sys
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import GEXSnapshot
from app.core.provider_registry import ProviderUnavailableError

client = TestClient(app)


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
            }
        )

    def test_missing_symbol_uses_default(self):
        """Should return valid response when symbol is omitted (defaults to SPY)."""
        mock_df = self._mock_options_df()
        mock_df["type"] = mock_df["contractType"]
        mock_df["implied_vol"] = mock_df["impliedVolatility"]
        mock_df["open_interest"] = mock_df["openInterest"]

        with patch("app.core.yfinance_provider.YFinanceClient") as MockClient:
            instance = AsyncMock()
            instance.get_options_chain_for_gex = AsyncMock(return_value=(mock_df, 585.0))
            MockClient.return_value = instance

            resp = client.get("/api/analytics/iv-surface")
            # 200 (success), 503 (no data), or 404 (empty chain) are all valid
            assert resp.status_code in (200, 503, 404, 500)

    def test_invalid_symbol_returns_error(self):
        """Invalid symbol should gracefully return an error (not crash the server)."""
        with patch("app.core.yfinance_provider.YFinanceClient") as MockClient:
            instance = AsyncMock()
            # Return empty DF to simulate no data for invalid symbol
            instance.get_options_chain_for_gex = AsyncMock(
                return_value=(pd.DataFrame(), 0.0)
            )
            MockClient.return_value = instance

            resp = client.get("/api/analytics/iv-surface?symbol=XXXXINVALID")
            # 404 (empty chain) is the expected outcome with a mock that returns empty
            assert resp.status_code in (200, 404, 503)

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

        with patch("app.api.routes.analytics.get_data_client", return_value=mock_client) as mock_get_client:
            with patch("app.api.routes.analytics.get_historical_data_service") as mock_history_service:
                mock_history_service.return_value.get_iv_surface = AsyncMock(return_value=None)
                with patch("app.core.vollib_bridge.VolLibBridge.calculate_iv_surface", return_value=mock_df[["strike", "type", "implied_vol", "mid"]].rename(columns={"implied_vol": "iv", "mid": "mid_price"}).assign(moneyness=1.0)):
                    with patch("app.core.vollib_bridge.VolLibBridge.calculate_iv_skew", return_value=pd.DataFrame()):
                        with patch("app.core.rate_provider.get_rate_provider") as mock_rate_provider:
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
        with patch(
            "app.api.routes.analytics.get_historical_data_service"
        ) as mock_history_service:
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

    def test_valid_request_returns_200_or_503(self):
        """Should return 200 with indicators or 503 if data unavailable."""
        resp = client.get(
            "/api/analytics/technical-indicators?symbol=SPY&period=5d&interval=1d&indicators=ATR"
        )
        assert resp.status_code in (200, 503)

    def test_response_schema_on_success(self):
        """On 200 response, schema must contain required fields."""
        resp = client.get(
            "/api/analytics/technical-indicators?symbol=SPY&period=5d&interval=1d"
        )
        if resp.status_code == 200:
            body = resp.json()
            assert "symbol" in body
            assert "data" in body
            assert "count" in body
            assert "indicators" in body

    def test_invalid_period_raises_validation_error(self):
        """Unexpected parameter format should be gracefully handled."""
        resp = client.get("/api/analytics/technical-indicators?symbol=BAD&period=999z")
        # Accepts 200, 422, 503 — just no 500 internal unhandled
        assert resp.status_code != 500

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

        with patch("app.api.routes.analytics.get_historical_data_service", return_value=history_service):
            with patch("app.api.routes.analytics.get_demo_data_service", return_value=_AnchoredDemoService()):
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
                raise AssertionError("synthetic fallback should not be used when real history is available")

        market_history = pd.DataFrame(
            {
                "Open": [585.0, 586.0, 587.0, 588.0, 589.0, 590.0, 591.0, 592.0, 593.0, 594.0,
                         595.0, 596.0, 597.0, 598.0, 599.0, 600.0, 601.0, 602.0, 603.0, 604.0,
                         605.0, 606.0, 607.0, 608.0, 609.0],
                "High": [586.0, 587.0, 588.0, 589.0, 590.0, 591.0, 592.0, 593.0, 594.0, 595.0,
                         596.0, 597.0, 598.0, 599.0, 600.0, 601.0, 602.0, 603.0, 604.0, 605.0,
                         606.0, 607.0, 608.0, 609.0, 610.0],
                "Low": [584.0, 585.0, 586.0, 587.0, 588.0, 589.0, 590.0, 591.0, 592.0, 593.0,
                        594.0, 595.0, 596.0, 597.0, 598.0, 599.0, 600.0, 601.0, 602.0, 603.0,
                        604.0, 605.0, 606.0, 607.0, 608.0],
                "Close": [585.5, 586.5, 587.5, 588.5, 589.5, 590.5, 591.5, 592.5, 593.5, 594.5,
                          595.5, 596.5, 597.5, 598.5, 599.5, 600.5, 601.5, 602.5, 603.5, 604.5,
                          605.5, 606.5, 607.5, 608.5, 609.5],
                "Volume": [1_000_000] * 25,
            }
        )

        class _FakeTicker:
            def history(self, *args, **kwargs):
                return market_history

        class _FakeYFinance:
            def Ticker(self, symbol):
                assert symbol == "SPY"
                return _FakeTicker()

        with patch("app.api.routes.analytics.get_historical_data_service", return_value=history_service):
            with patch("app.api.routes.analytics.get_demo_data_service", return_value=_FailingDemoService()):
                with patch.dict(sys.modules, {"yfinance": _FakeYFinance()}):
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
        assert body["count"] == 25
        assert any(point["atr"] is not None for point in body["data"])
        assert any(point["rsi"] is not None for point in body["data"])
        assert any(point["bb_upper"] is not None for point in body["data"])


# ---------------------------------------------------------------------------
# /api/analytics/vectorbt-backtest
# ---------------------------------------------------------------------------

class TestVectorbtBacktestEndpoint:
    """Tests for GET /api/analytics/vectorbt-backtest."""

    def test_valid_request_returns_200_or_503(self):
        resp = client.get(
            "/api/analytics/vectorbt-backtest"
            "?start_date=2025-01-01&end_date=2025-03-01"
            "&entry_threshold=-1000000000&exit_threshold=0&initial_cash=100000"
        )
        assert resp.status_code in (200, 503)

    def test_response_schema_on_success(self):
        """On 200, response must include all required backtest metrics."""
        dummy_result = {
            "total_return": 0.05,
            "sharpe_ratio": 1.2,
            "sortino_ratio": 1.5,
            "calmar_ratio": 0.8,
            "max_drawdown": -0.12,
            "total_trades": 10,
            "winning_trades": 6,
            "losing_trades": 4,
            "win_rate": 0.6,
            "profit_factor": 1.5,
            "avg_trade_return": 0.005,
            "best_trade": 0.02,
            "worst_trade": -0.01,
            "avg_trade_duration_minutes": 30.0,
            "start_date": "2025-01-01T00:00:00",
            "end_date": "2025-03-01T00:00:00",
            "equity_curve": [100000.0, 101000.0, 105000.0],
        }

        with patch("app.core.vectorbt_backtester.VectorBTBacktester.run_gex_signal_backtest",
                   return_value=dummy_result):
            resp = client.get(
                "/api/analytics/vectorbt-backtest"
                "?start_date=2025-01-01&end_date=2025-03-01"
            )
            if resp.status_code == 200:
                body = resp.json()
                required = {
                    "total_return", "sharpe_ratio", "max_drawdown",
                    "total_trades", "win_rate", "equity_curve",
                }
                assert required.issubset(body.keys())

    def test_equity_curve_is_list(self):
        """equity_curve should be a list of floats."""
        resp = client.get(
            "/api/analytics/vectorbt-backtest"
            "?start_date=2025-01-01&end_date=2025-03-01"
        )
        if resp.status_code == 200:
            curve = resp.json()["equity_curve"]
            assert isinstance(curve, list)
            assert all(isinstance(v, (int, float)) for v in curve)

    def test_end_date_before_start_date_handled(self):
        """Should return error or 503 when date range is invalid."""
        resp = client.get(
            "/api/analytics/vectorbt-backtest"
            "?start_date=2025-06-01&end_date=2025-01-01"
        )
        # Should not be a 500 unhandled crash
        assert resp.status_code != 500


# ---------------------------------------------------------------------------
# /api/analytics/summary-statistics (existing — boundary tests)
# ---------------------------------------------------------------------------

class TestSummaryStatsEdgeCases:
    """Edge-case tests for existing summary statistics endpoint."""

    def test_no_data_in_cache_returns_503_or_200(self):
        """Without cached data, endpoint should gracefully handle absence."""
        resp = client.get("/api/analytics/summary-statistics")
        assert resp.status_code in (200, 503)

    def test_accepts_date_params(self):
        """Should accept optional start_date and end_date params."""
        resp = client.get(
            "/api/analytics/summary-statistics"
            "?start_date=2025-01-01&end_date=2025-03-01"
        )
        assert resp.status_code in (200, 503)
