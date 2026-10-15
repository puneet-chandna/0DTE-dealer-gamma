"""Analytics must never present generated data as captured market history."""

from datetime import datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.routes import analytics as routes
from app.main import app
from app.services.cache import reset_cache


class EmptyHistory:
    async def get_time_series_frames(self, **kwargs):
        return pd.DataFrame(), pd.DataFrame()

    async def run_backtest(self, **kwargs):
        return None

    async def run_vectorbt_backtest(self, **kwargs):
        return None

    async def get_summary_statistics(self, **kwargs):
        return None

    async def get_latest_snapshot(self, **kwargs):
        return None


@pytest.fixture
def client(monkeypatch):
    reset_cache()
    monkeypatch.setattr(routes, "get_historical_data_service", lambda: EmptyHistory())
    return TestClient(app)


@pytest.mark.parametrize(
    "endpoint", ["backtest", "vectorbt-backtest", "summary-statistics", "gex-volatility"]
)
def test_missing_captured_history_does_not_become_synthetic_success(client, endpoint):
    response = client.get(
        f"/api/analytics/{endpoint}",
        params={
            "start_date": "2025-01-01",
            "end_date": "2025-01-10",
            "provider": "yfinance",
        },
    )
    assert response.status_code == 404
    assert "history" in response.json()["detail"].lower()


@pytest.mark.parametrize(
    "endpoint", ["backtest", "vectorbt-backtest", "summary-statistics", "gex-volatility"]
)
def test_explicit_demo_labels_synthetic_results(client, endpoint):
    response = client.get(
        f"/api/analytics/{endpoint}",
        params={
            "start_date": "2025-01-01",
            "end_date": "2025-01-10",
            "provider": "yfinance",
            "demo": True,
        },
    )
    assert response.status_code == 200
    provenance = response.json()["provenance"]
    assert provenance["data_kind"] == "synthetic"
    assert provenance["provider"] == "yfinance"
    assert provenance["actual_instrument"] == "SPY"
    assert provenance["is_proxy"] is True
    assert provenance["sample_count"] > 0


def test_captured_proxy_backtest_identifies_actual_range_and_instrument(client, monkeypatch):
    index = pd.date_range("2025-01-06 09:31", periods=12, freq="1min", tz="America/New_York")
    prices = pd.DataFrame({"close": [6000.0 + n * 10 for n in range(12)]}, index=index)
    gex = pd.DataFrame({"net_gex": [-2e9] * 8 + [1e9] * 4}, index=index)

    class CapturedHistory(EmptyHistory):
        async def get_time_series_frames(self, **kwargs):
            assert kwargs["prefer_replay"] is True
            assert kwargs["allow_latest_replay_fallback"] is False
            return prices.copy(), gex.copy()

    monkeypatch.setattr(routes, "get_historical_data_service", lambda: CapturedHistory())
    response = client.get(
        "/api/analytics/vectorbt-backtest",
        params={
            "start_date": "2025-01-01",
            "end_date": "2025-01-10",
            "provider": "yfinance",
        },
    )
    assert response.status_code == 200
    provenance = response.json()["provenance"]
    assert provenance["data_kind"] == "captured"
    assert provenance["actual_instrument"] == "SPY"
    assert provenance["sample_count"] == 12
    assert datetime.fromisoformat(provenance["actual_start"]) == index[0]
    assert datetime.fromisoformat(provenance["actual_end"]) == index[-1]
    assert "freshness" in " ".join(provenance["quality_limitations"]).lower()


@pytest.mark.parametrize("endpoint", ["backtest", "vectorbt-backtest"])
def test_direct_index_history_is_not_presented_as_tradable_underlying(client, endpoint):
    response = client.get(
        f"/api/analytics/{endpoint}",
        params={
            "start_date": "2025-01-01",
            "end_date": "2025-01-10",
            "provider": "tradier",
            "symbol": "SPX",
        },
    )
    assert response.status_code == 422
    assert "SPY" in response.json()["detail"]
