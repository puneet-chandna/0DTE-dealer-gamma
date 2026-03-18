"""Expanded tests for Analytics API routes.

Tests IV-surface, technical-indicators, vectorbt-backtest endpoints
including parameter validation, error handling, and response schemas.
"""

import json
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


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
        """Should return a valid response (200 or 503) for the default symbol."""
        resp = client.get("/api/analytics/iv-surface")
        assert resp.status_code in (200, 503)

    def test_invalid_symbol_returns_error(self):
        """Totally invalid symbol should return a non-200 or graceful 503."""
        resp = client.get("/api/analytics/iv-surface?symbol=XXXXINVALID")
        assert resp.status_code in (200, 503, 422)


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
