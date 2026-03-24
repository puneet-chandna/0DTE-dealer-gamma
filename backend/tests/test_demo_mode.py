"""Backend demo mode tests."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import GEXSnapshot

client = TestClient(app)
ET = ZoneInfo("America/New_York")


async def _raise_async_live_call(*args, **kwargs):
    raise AssertionError("live provider should not be called in demo mode")


def _raise_sync_live_call(*args, **kwargs):
    raise AssertionError("live provider should not be called in demo mode")


def _build_snapshot(
    *,
    spot_price: float,
    net_gex: float,
    zero_gamma_level: float,
    timestamp: datetime | None = None,
) -> GEXSnapshot:
    return GEXSnapshot(
        timestamp=timestamp or datetime(2026, 3, 25, 10, 30, tzinfo=ET),
        spot_price=spot_price,
        total_call_gex=-abs(net_gex) - 2.5e8,
        total_put_gex=2.5e8,
        net_gex=net_gex,
        zero_gamma_level=zero_gamma_level,
        gex_by_strike={float(round(spot_price)): net_gex / 4},
        dominant_strike=float(round(spot_price)),
        metrics={"capture_quality": 0.99},
    )


def test_current_gex_demo_mode_skips_live_provider(monkeypatch):
    """Demo current GEX should not hit the live provider path."""
    import app.api.routes.gex as gex_routes

    monkeypatch.setattr(gex_routes, "_get_live_gex_snapshot", _raise_async_live_call)

    response = client.get("/api/gex/current", params={"demo": "true"})

    assert response.status_code == 200
    data = response.json()
    assert (
        data["metrics"].get("is_demo_data") == 1.0
        or data["metrics"].get("is_replay_data") == 1.0
    )
    assert "net_gex" in data
    assert "gex_by_strike" in data


def test_current_gex_demo_mode_shapes_synthetic_fallback_from_latest_snapshot(monkeypatch):
    """Demo current GEX should anchor synthetic fallback to the latest persisted snapshot."""
    import app.api.routes.gex as gex_routes

    anchor_snapshot = _build_snapshot(
        spot_price=6030.0,
        net_gex=-8.2e8,
        zero_gamma_level=6021.5,
    )
    anchored_demo_snapshot = _build_snapshot(
        spot_price=6028.0,
        net_gex=-7.9e8,
        zero_gamma_level=6020.0,
    )

    class _AnchoredDemoService:
        def get_current_snapshot(self, symbol, now=None, *, anchor_snapshot):
            assert symbol == "SPX"
            assert anchor_snapshot.spot_price == 6030.0
            return anchored_demo_snapshot

    monkeypatch.setattr(gex_routes, "_get_replay_snapshot", AsyncMock(return_value=None))
    monkeypatch.setattr(
        gex_routes,
        "_get_latest_persisted_snapshot",
        AsyncMock(return_value=anchor_snapshot),
    )
    monkeypatch.setattr(gex_routes, "get_demo_data_service", lambda: _AnchoredDemoService())

    response = client.get(
        "/api/gex/current",
        params={"demo": "true", "provider": "yfinance", "symbol": "SPX"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["spot_price"] == 6028.0
    assert data["zero_gamma_level"] == 6020.0
    assert data["net_gex"] == -7.9e8


def test_demo_iv_surface_endpoint_skips_live_market_calls(monkeypatch):
    """Demo IV surface should still avoid live provider and yfinance access."""
    import app.api.routes.analytics as analytics_routes

    monkeypatch.setattr(analytics_routes, "get_data_client", _raise_sync_live_call)
    iv_response = client.get("/api/analytics/iv-surface", params={"demo": "true", "symbol": "SPY"})

    assert iv_response.status_code == 200
    assert iv_response.json()["count"] > 0


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


@pytest.mark.asyncio
async def test_demo_websocket_shapes_synthetic_fallback_from_latest_snapshot(monkeypatch):
    """Demo WebSocket fallback should anchor synthetic updates to the latest persisted snapshot."""
    import app.api.websocket as websocket_routes
    from app.config import Settings

    anchor_snapshot = _build_snapshot(
        spot_price=6012.0,
        net_gex=-6.7e8,
        zero_gamma_level=6005.0,
    )

    class _AnchoredDemoService:
        def get_ws_update(self, symbol="SPX", now=None, *, anchor_snapshot):
            assert symbol == "SPX"
            assert anchor_snapshot.spot_price == 6012.0
            return {
                "net_gex": -6.5e8,
                "net_gex_billions": -0.65,
                "zero_gamma_level": 6004.0,
                "spot_price": 6010.0,
                "regime": "neutral",
                "timestamp": "2026-03-25T10:30:00-04:00",
                "is_mock": True,
                "is_demo": True,
                "is_stale": False,
            }

    history_service = SimpleNamespace(
        get_historical_snapshots=AsyncMock(return_value=[]),
        get_latest_snapshot=AsyncMock(return_value=anchor_snapshot),
    )

    monkeypatch.setattr(
        websocket_routes,
        "get_historical_data_service",
        lambda: history_service,
    )
    monkeypatch.setattr(
        websocket_routes,
        "get_demo_data_service",
        lambda: _AnchoredDemoService(),
    )

    payload = await websocket_routes._get_gex_update(
        Settings(data_provider="yfinance"),
        demo=True,
        symbol="SPX",
        provider="yfinance",
    )

    assert payload["spot_price"] == 6010.0
    assert payload["zero_gamma_level"] == 6004.0
    assert payload["is_demo"] is True


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


def test_anchored_demo_session_applies_zero_total_put_gex_anchor():
    """A zero put-GEX anchor should still be applied when shaping the synthetic session."""
    from app.core.demo_data import DemoDataService

    anchored_session = DemoDataService._get_anchored_session(
        "SPY",
        date(2026, 3, 25),
        590.0,
        -5.5e8,
        588.5,
        -7.5e8,
        0.0,
    )

    assert abs(float(anchored_session.gex_data["total_put_gex"].mean())) < 1e-6
    recomputed_call = anchored_session.gex_data["net_gex"] - anchored_session.gex_data["total_put_gex"]
    assert (anchored_session.gex_data["total_call_gex"] == recomputed_call).all()
