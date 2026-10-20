"""Analytics panels disclose their actual source and never invent a provider quote."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.routes import analytics
from app.api.websocket import _build_ws_payload_from_snapshot
from app.core.demo_data import DemoDataService
from app.main import app
from app.models.schemas import GEXSnapshot


@pytest.fixture
def client(monkeypatch):
    history = SimpleNamespace(
        get_iv_surface=AsyncMock(return_value=None),
        get_technical_indicators=AsyncMock(return_value=None),
        get_latest_snapshot=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(analytics, "get_historical_data_service", lambda: history)
    return TestClient(app)


def test_iv_provider_failure_returns_safe_error_without_fabricated_spot(client, monkeypatch):
    monkeypatch.setattr(
        analytics, "get_data_client", lambda _: SimpleNamespace(provider_name="tradier")
    )
    monkeypatch.setattr(
        analytics,
        "get_cache",
        lambda: SimpleNamespace(
            fetch_gex_chain=AsyncMock(side_effect=RuntimeError("auth token=private-secret"))
        ),
    )
    response = client.get("/api/analytics/iv-surface?provider=tradier&symbol=SPY")
    assert response.status_code == 502
    assert "private-secret" not in response.text
    assert "5950" not in response.text


def test_live_iv_date_only_expiry_keeps_source_identity_and_signed_coordinates(client, monkeypatch):
    options = pd.DataFrame(
        {"strike": [6000.0, 6000.0], "type": ["call", "put"],
         "mid": [20.0, 20.0], "expiration": ["2099-01-15"] * 2},
    )
    options.attrs["source_metadata"] = {
        "actual_instrument": "SPY", "is_proxy": True,
        "source_received_at": "2026-10-16T14:00:00+00:00",
    }
    monkeypatch.setattr(analytics, "get_data_client", lambda _: object())
    monkeypatch.setattr(
        analytics, "get_cache",
        lambda: SimpleNamespace(fetch_gex_chain=AsyncMock(return_value=(options, 6000.0))),
    )
    monkeypatch.setattr(
        "app.core.rate_provider.get_rate_provider", lambda: SimpleNamespace(get_rate=lambda: 0.0)
    )
    response = client.get("/api/analytics/iv-surface?provider=yfinance&symbol=SPX")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert all(point["moneyness"] == 0 for point in payload["surface"] + payload["skew"])
    provenance = payload["provenance"]
    assert provenance["provider"] == "yfinance"
    assert provenance["requested_symbol"] == "SPX"
    assert provenance["actual_instrument"] == "SPY"
    assert provenance["is_proxy"] is True
    assert provenance["data_kind"] == "captured"
    assert provenance["is_replay"] is False
    assert provenance["actual_start"] == "2026-10-16T14:00:00Z"


@pytest.mark.parametrize("demo", [False, True])
def test_yahoo_history_discloses_actual_provider_even_when_tradier_selected(
    client, monkeypatch, demo
):
    history = pd.DataFrame(
        {"Open": range(100, 130), "High": range(101, 131), "Low": range(99, 129),
         "Close": range(100, 130), "Volume": [1000] * 30},
        index=pd.date_range("2026-09-01", periods=30, tz="America/New_York"),
    )
    monkeypatch.setattr(analytics, "_load_yfinance_history", lambda **_: history.copy())
    response = client.get(
        "/api/analytics/technical-indicators",
        params={"provider": "tradier", "symbol": "SPY", "demo": demo},
    )
    assert response.status_code == 200
    provenance = response.json()["provenance"]
    assert provenance["provider"] == "yfinance"
    assert provenance["actual_instrument"] == "SPY"
    assert provenance["is_proxy"] is False
    assert provenance["data_kind"] == "captured"
    assert provenance["is_replay"] is False
    assert provenance["sample_count"] == 30
    assert datetime.fromisoformat(provenance["actual_start"]) == history.index[0]
    assert datetime.fromisoformat(provenance["actual_end"]) == history.index[-1]


@pytest.mark.parametrize("bar_count", [1, 3])
@pytest.mark.parametrize("demo", [False, True])
def test_short_downloaded_history_preserves_unavailable_indicators_or_explicit_demo(
    client, monkeypatch, bar_count, demo
):
    history = pd.DataFrame(
        {"Open": range(100, 100 + bar_count), "High": range(101, 101 + bar_count),
         "Low": range(99, 99 + bar_count), "Close": range(100, 100 + bar_count),
         "Volume": [1000] * bar_count},
        index=pd.date_range("2026-09-01", periods=bar_count, freq="1W", tz="America/New_York"),
    )
    monkeypatch.setattr(analytics, "_load_yfinance_history", lambda **_: history.copy())
    response = client.get(
        "/api/analytics/technical-indicators",
        params={"provider": "tradier", "symbol": "SPY", "period": "5d",
                "interval": "1wk", "demo": demo},
    )
    assert response.status_code == 200
    payload = response.json()
    if demo:
        assert payload["provenance"]["provider"] == "demo"
        assert payload["provenance"]["data_kind"] == "synthetic"
    else:
        assert payload["count"] == bar_count
        assert [point["close"] for point in payload["data"]] == list(history["Close"])
        assert all(
            point[indicator] is None
            for point in payload["data"]
            for indicator in ("atr", "rsi", "bb_upper", "bb_mid", "bb_lower")
        )
        provenance = payload["provenance"]
        assert provenance["provider"] == "yfinance"
        assert provenance["data_kind"] == "captured"
        assert provenance["sample_count"] == bar_count
        assert datetime.fromisoformat(provenance["actual_start"]) == history.index[0]
        assert datetime.fromisoformat(provenance["actual_end"]) == history.index[-1]


@pytest.mark.parametrize("demo", [False, True])
def test_short_history_still_rejects_unsupported_indicators(client, monkeypatch, demo):
    history = pd.DataFrame(
        {"Open": [100.0], "High": [101.0], "Low": [99.0], "Close": [100.0]},
        index=pd.date_range("2026-09-01", periods=1, tz="America/New_York"),
    )
    monkeypatch.setattr(analytics, "_load_yfinance_history", lambda **_: history.copy())
    response = client.get(
        "/api/analytics/technical-indicators",
        params={"provider": "tradier", "symbol": "SPY", "indicators": "ATR,UNKNOWN",
                "demo": demo},
    )
    assert response.status_code == 400
    assert "Unsupported" in response.json()["detail"]


def test_generated_analytics_disclose_synthetic_source(client, monkeypatch):
    monkeypatch.setattr(analytics, "_load_yfinance_history", lambda **_: pd.DataFrame())
    for endpoint in ("iv-surface", "technical-indicators"):
        response = client.get(
            f"/api/analytics/{endpoint}",
            params={"provider": "tradier", "symbol": "SPY", "demo": True},
        )
        assert response.status_code == 200
        payload = response.json()
        provenance = payload["provenance"]
        assert provenance["provider"] == "demo"
        assert provenance["data_kind"] == "synthetic"
        assert provenance["is_replay"] is False
        assert provenance["sample_count"] == payload["count"]
        assert provenance["actual_start"] is not None


@pytest.mark.parametrize("is_replay", [True, False])
def test_stream_snapshot_metrics_preserve_replay_and_synthetic_identity(is_replay):
    snapshot = DemoDataService().get_current_snapshot(symbol="SPY")
    if is_replay:
        snapshot = GEXSnapshot(**{**snapshot.model_dump(), "metrics": {"capture_quality": 0.99}})
    original_metrics = dict(snapshot.metrics)
    payload = _build_ws_payload_from_snapshot(
        snapshot=snapshot, provider="tradier", is_demo=True, is_replay=is_replay
    )
    assert bool(payload["metrics"]["is_replay_data"]) is is_replay
    assert bool(payload["metrics"]["is_synthetic_data"]) is not is_replay
    assert snapshot.metrics == original_metrics
