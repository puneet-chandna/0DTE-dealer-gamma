"""Backend demo mode tests."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
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
        def get_current_snapshot(self, symbol, now=None, *, anchor_snapshot, provider="demo"):
            assert symbol == "SPX"
            assert anchor_snapshot.spot_price == 6030.0
            assert provider == "yfinance"
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


def test_current_gex_demo_mode_preserves_above_range_zero_gamma_relation(monkeypatch):
    """Anchored demo current GEX should mark zero gamma as above-range when the anchor says so."""
    import app.api.routes.gex as gex_routes

    anchor_snapshot = _build_snapshot(
        spot_price=6030.0,
        net_gex=-8.2e8,
        zero_gamma_level=6175.0,
    )
    anchor_snapshot.metrics["zero_gamma_crossing_found"] = False
    anchor_snapshot.metrics["zero_gamma_relation"] = "above_range"

    monkeypatch.setattr(gex_routes, "_get_replay_snapshot", AsyncMock(return_value=None))
    monkeypatch.setattr(
        gex_routes,
        "_get_latest_persisted_snapshot",
        AsyncMock(return_value=anchor_snapshot),
    )

    response = client.get(
        "/api/gex/current",
        params={"demo": "true", "provider": "yfinance", "symbol": "SPX"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["metrics"]["zero_gamma_crossing_found"] is False
    assert data["metrics"]["zero_gamma_relation"] == "above_range"


def test_current_gex_demo_mode_synthetic_fallback_includes_advanced_analytics(monkeypatch):
    """Synthetic demo current GEX should include advanced analytics when replay is unavailable."""
    import app.api.routes.gex as gex_routes

    monkeypatch.setattr(gex_routes, "_get_replay_snapshot", AsyncMock(return_value=None))
    monkeypatch.setattr(
        gex_routes,
        "_get_latest_persisted_snapshot",
        AsyncMock(return_value=None),
    )

    response = client.get(
        "/api/gex/current",
        params={"demo": "true", "provider": "tradier", "symbol": "SPX"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["advanced_analytics"]["charm_vanna"] is not None
    assert data["advanced_analytics"]["hawkes"] is not None
    assert data["advanced_analytics"]["smoothed_net_gex"] is not None


def test_current_gex_demo_replay_backfills_advanced_analytics_when_missing(monkeypatch):
    """Replay demo current GEX should synthesize advanced analytics when older snapshots lack them."""
    import app.api.routes.gex as gex_routes

    replay_snapshot = _build_snapshot(
        spot_price=6031.0,
        net_gex=-7.4e8,
        zero_gamma_level=6020.0,
    )

    monkeypatch.setattr(gex_routes, "_get_replay_snapshot", AsyncMock(return_value=replay_snapshot))

    response = client.get(
        "/api/gex/current",
        params={"demo": "true", "provider": "tradier", "symbol": "SPX"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["metrics"]["is_replay_data"] == 1.0
    assert data["advanced_analytics"]["charm_vanna"] is not None
    assert data["advanced_analytics"]["hawkes"] is not None
    assert data["advanced_analytics"]["smoothed_net_gex"] is not None


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
        def get_ws_update(self, symbol="SPX", now=None, *, anchor_snapshot, provider="demo"):
            assert symbol == "SPX"
            assert anchor_snapshot.spot_price == 6012.0
            assert provider == "yfinance"
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
                "advanced_analytics": {
                    "charm_vanna": {"charm_flow": 1.0, "vanna_flow": 2.0, "net_hidden_flow": 3.0, "charm_by_strike": {}, "vanna_by_strike": {}},
                    "hawkes": {"call_intensity": 0.0, "put_intensity": 0.0, "net_toxicity": 0.0, "squeeze_probability": 0.0},
                },
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


@pytest.mark.asyncio
async def test_demo_websocket_synthetic_fallback_includes_advanced_analytics(monkeypatch):
    """Synthetic demo websocket fallback should include advanced analytics payloads."""
    import app.api.websocket as websocket_routes
    from app.config import Settings

    history_service = SimpleNamespace(
        get_historical_snapshots=AsyncMock(return_value=[]),
        get_latest_snapshot=AsyncMock(return_value=None),
    )

    monkeypatch.setattr(
        websocket_routes,
        "get_historical_data_service",
        lambda: history_service,
    )

    payload = await websocket_routes._get_gex_update(
        Settings(data_provider="tradier"),
        demo=True,
        symbol="SPX",
        provider="tradier",
    )

    assert payload["is_demo"] is True
    assert payload["is_replay"] is False
    assert payload["advanced_analytics"]["charm_vanna"] is not None
    assert payload["advanced_analytics"]["hawkes"] is not None


@pytest.mark.asyncio
async def test_demo_websocket_replay_backfills_advanced_analytics_when_missing(monkeypatch):
    """Replay demo websocket updates should synthesize advanced analytics when older snapshots lack them."""
    import app.api.websocket as websocket_routes
    from app.config import Settings

    replay_snapshot = _build_snapshot(
        spot_price=6014.0,
        net_gex=-5.8e8,
        zero_gamma_level=6008.0,
    )
    history_service = SimpleNamespace(
        get_historical_snapshots=AsyncMock(return_value=[replay_snapshot]),
    )

    monkeypatch.setattr(
        websocket_routes,
        "get_historical_data_service",
        lambda: history_service,
    )

    payload = await websocket_routes._get_gex_update(
        Settings(data_provider="tradier"),
        demo=True,
        symbol="SPX",
        provider="tradier",
    )

    assert payload["is_demo"] is True
    assert payload["is_replay"] is True
    assert payload["advanced_analytics"]["charm_vanna"] is not None
    assert payload["advanced_analytics"]["hawkes"] is not None


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


def test_demo_vectorbt_backtest_always_uses_requested_range_synthetic_series(monkeypatch):
    """Demo vectorbt backtests should bypass persisted backtest helpers entirely."""
    import app.api.routes.analytics as analytics_routes

    anchor_snapshot = _build_snapshot(
        spot_price=6030.0,
        net_gex=-8.2e8,
        zero_gamma_level=6021.5,
    )
    history_service = SimpleNamespace(
        run_vectorbt_backtest=AsyncMock(
            side_effect=AssertionError("persisted vectorbt backtest should not be used in demo mode")
        ),
        get_latest_snapshot=AsyncMock(return_value=anchor_snapshot),
    )
    captured_demo_request: dict[str, object] = {}

    class _DemoService:
        def get_time_series(self, symbol, start_date, end_date, interval="1min", *, anchor_snapshot=None):
            captured_demo_request.update(
                {
                    "symbol": symbol,
                    "start_date": start_date,
                    "end_date": end_date,
                    "anchor_snapshot": anchor_snapshot,
                }
            )
            return "demo-price-series", "demo-gex-series"

    monkeypatch.setattr(
        analytics_routes,
        "get_historical_data_service",
        lambda: history_service,
    )
    monkeypatch.setattr(
        analytics_routes,
        "get_demo_data_service",
        lambda: _DemoService(),
    )

    demo_result = SimpleNamespace(
        total_return=0.08,
        sharpe_ratio=1.6,
        sortino_ratio=2.0,
        calmar_ratio=1.1,
        max_drawdown=-0.05,
        total_trades=6,
        winning_trades=4,
        losing_trades=2,
        win_rate=4 / 6,
        profit_factor=1.8,
        avg_trade_return=0.012,
        best_trade=0.04,
        worst_trade=-0.01,
        avg_trade_duration_minutes=42.0,
        start_date=datetime(2025, 1, 1, 9, 30, tzinfo=ET),
        end_date=datetime(2025, 3, 1, 15, 55, tzinfo=ET),
        equity_curve=[100000.0, 103500.0, 108000.0],
    )

    with patch(
        "app.core.vectorbt_backtester.VectorBTBacktester.run_gex_signal_backtest",
        return_value=demo_result,
    ):
        response = client.get(
            "/api/analytics/vectorbt-backtest",
            params={
                "provider": "yfinance",
                "symbol": "SPX",
                "start_date": "2025-01-01",
                "end_date": "2025-03-01",
                "demo": "true",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["start_date"].startswith("2025-01-01T09:30:00")
    assert body["end_date"].startswith("2025-03-01T15:55:00")
    assert captured_demo_request == {
        "symbol": "SPX",
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 3, 1),
        "anchor_snapshot": anchor_snapshot,
    }
    history_service.get_latest_snapshot.assert_awaited_once_with(
        provider="yfinance",
        symbol="SPX",
    )


def test_demo_legacy_backtest_always_uses_requested_range_synthetic_series(monkeypatch):
    """Demo legacy backtests should bypass persisted backtest helpers entirely."""
    import app.api.routes.analytics as analytics_routes

    anchor_snapshot = _build_snapshot(
        spot_price=5995.0,
        net_gex=-6.1e8,
        zero_gamma_level=6004.5,
    )
    history_service = SimpleNamespace(
        run_backtest=AsyncMock(
            side_effect=AssertionError("persisted legacy backtest should not be used in demo mode")
        ),
        get_latest_snapshot=AsyncMock(return_value=anchor_snapshot),
    )
    captured_demo_request: dict[str, object] = {}

    class _DemoService:
        def get_time_series(self, symbol, start_date, end_date, interval="1min", *, anchor_snapshot=None):
            captured_demo_request.update(
                {
                    "symbol": symbol,
                    "start_date": start_date,
                    "end_date": end_date,
                    "anchor_snapshot": anchor_snapshot,
                }
            )
            return "demo-price-series", "demo-gex-series"

    monkeypatch.setattr(
        analytics_routes,
        "get_historical_data_service",
        lambda: history_service,
    )
    monkeypatch.setattr(
        analytics_routes,
        "get_demo_data_service",
        lambda: _DemoService(),
    )

    demo_result = SimpleNamespace(
        total_trades=5,
        winning_trades=3,
        losing_trades=2,
        win_rate=0.6,
        total_return=0.07,
        average_return=0.013,
        sharpe_ratio=1.4,
        max_drawdown=-0.04,
        profit_factor=1.7,
        average_trade_duration=37.0,
        start_date=datetime(2025, 1, 1, 9, 30, tzinfo=ET),
        end_date=datetime(2025, 3, 1, 15, 55, tzinfo=ET),
    )

    with patch.object(
        analytics_routes.TradingStrategy,
        "volatility_breakout_strategy",
        return_value=demo_result,
    ):
        response = client.get(
            "/api/analytics/backtest",
            params={
                "provider": "yfinance",
                "symbol": "SPX",
                "start_date": "2025-01-01",
                "end_date": "2025-03-01",
                "demo": "true",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["start_date"].startswith("2025-01-01T09:30:00")
    assert body["end_date"].startswith("2025-03-01T15:55:00")
    assert captured_demo_request == {
        "symbol": "SPX",
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 3, 1),
        "anchor_snapshot": anchor_snapshot,
    }
    history_service.get_latest_snapshot.assert_awaited_once_with(
        provider="yfinance",
        symbol="SPX",
    )


@pytest.mark.parametrize(
    ("endpoint", "start_date", "end_date"),
    [
        ("/api/analytics/vectorbt-backtest", "2026-03-28", "2026-03-29"),
        ("/api/analytics/vectorbt-backtest", "2026-03-26", "2026-03-28"),
        ("/api/analytics/backtest", "2026-03-28", "2026-03-29"),
        ("/api/analytics/backtest", "2026-03-26", "2026-03-28"),
    ],
)
def test_backtest_endpoints_reject_future_dates_against_current_new_york_market_date(
    monkeypatch,
    endpoint,
    start_date,
    end_date,
):
    """Future backtest dates should fail fast against the New York market date."""
    import app.api.routes.analytics as analytics_routes

    history_service = SimpleNamespace(
        run_vectorbt_backtest=AsyncMock(
            side_effect=AssertionError("persisted vectorbt backtest should not run for future dates")
        ),
        run_backtest=AsyncMock(
            side_effect=AssertionError("persisted legacy backtest should not run for future dates")
        ),
        get_latest_snapshot=AsyncMock(
            side_effect=AssertionError("demo anchor lookup should not run for future dates")
        ),
    )

    monkeypatch.setattr(
        analytics_routes,
        "get_current_trading_date",
        lambda now=None: date(2026, 3, 27),
    )
    monkeypatch.setattr(
        analytics_routes,
        "get_historical_data_service",
        lambda: history_service,
    )

    response = client.get(
        endpoint,
        params={
            "provider": "yfinance",
            "symbol": "SPX",
            "start_date": start_date,
            "end_date": end_date,
            "demo": "true",
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "2026-03-27" in detail
    assert "new york market date" in detail.lower()
