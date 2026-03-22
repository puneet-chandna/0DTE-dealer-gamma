"""Backend demo mode tests."""

from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ET = ZoneInfo("America/New_York")


async def _raise_async_live_call(*args, **kwargs):
    raise AssertionError("live provider should not be called in demo mode")


def _raise_sync_live_call(*args, **kwargs):
    raise AssertionError("live provider should not be called in demo mode")


class _FailingTicker:
    def history(self, *args, **kwargs):
        raise AssertionError("yfinance should not be called in demo mode")


class _FailingYFinance:
    def Ticker(self, *args, **kwargs):
        return _FailingTicker()


def test_current_gex_demo_mode_skips_live_provider(monkeypatch):
    """Demo current GEX should not hit the live provider path."""
    import app.api.routes.gex as gex_routes

    monkeypatch.setattr(gex_routes, "_get_live_gex_snapshot", _raise_async_live_call)

    response = client.get("/api/gex/current", params={"demo": "true"})

    assert response.status_code == 200
    data = response.json()
    assert data["metrics"]["is_demo_data"] == 1.0
    assert "net_gex" in data
    assert "gex_by_strike" in data


def test_demo_analytics_endpoints_skip_live_market_calls(monkeypatch):
    """Demo analytics endpoints should avoid provider and yfinance access."""
    import sys
    import app.api.routes.analytics as analytics_routes

    monkeypatch.setattr(analytics_routes, "get_data_client", _raise_sync_live_call)
    monkeypatch.setitem(sys.modules, "yfinance", _FailingYFinance())

    iv_response = client.get("/api/analytics/iv-surface", params={"demo": "true", "symbol": "SPY"})
    technical_response = client.get(
        "/api/analytics/technical-indicators",
        params={
            "demo": "true",
            "symbol": "SPY",
            "period": "1mo",
            "interval": "1d",
        },
    )

    assert iv_response.status_code == 200
    assert technical_response.status_code == 200
    assert iv_response.json()["count"] > 0
    assert technical_response.json()["count"] > 0


def test_demo_websocket_identifies_demo_stream(monkeypatch):
    """Demo WebSocket stream should identify itself explicitly."""
    import app.api.websocket as websocket_routes

    monkeypatch.setattr(websocket_routes, "get_data_client", _raise_sync_live_call)

    with client.websocket_connect("/ws/gex-stream?demo=true") as websocket:
        connection_data = websocket.receive_json()
        update = websocket.receive_json()

    assert connection_data["type"] == "connected"
    assert connection_data["data"]["mode"] == "demo"
    assert update["type"] == "gex_update"
    assert update["data"]["is_demo"] is True


def test_websocket_rejects_unsupported_symbol():
    """WebSocket should reject symbols outside the allowlist."""
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/gex-stream?symbol=bad-symbol"):
            pass


def test_demo_session_is_deterministic_for_same_bucket():
    """Demo session should be stable inside a time bucket and change across buckets."""
    from app.core.demo_data import DemoDataService

    service = DemoDataService()
    reference = datetime(2026, 3, 20, 10, 15, 2, tzinfo=ET)

    first = service.get_current_snapshot("SPY", now=reference)
    second = service.get_current_snapshot("SPY", now=reference)
    next_bucket = service.get_current_snapshot(
        "SPY",
        now=datetime(2026, 3, 20, 10, 15, 7, tzinfo=ET),
    )

    assert first.net_gex == second.net_gex
    assert first.spot_price == second.spot_price
    assert first.zero_gamma_level == second.zero_gamma_level
    assert (
        next_bucket.net_gex != first.net_gex
        or next_bucket.spot_price != first.spot_price
        or next_bucket.zero_gamma_level != first.zero_gamma_level
    )


def test_demo_session_treats_naive_datetimes_as_utc():
    """Naive datetimes should be interpreted consistently before ET conversion."""
    from app.core.demo_data import DemoDataService

    normalized = DemoDataService._normalize_now(datetime(2026, 3, 20, 14, 30, 0))

    assert normalized.tzinfo == ET
    assert normalized.hour == 10
    assert normalized.minute == 30
