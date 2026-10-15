"""Live producers keep source clocks and never substitute generated exposure."""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.api import websocket as ws
from app.api.routes import gex
from app.config import Settings
from app.core.advanced_analytics import reset_advanced_analytics_state
from app.core.gex_calculator import GEXCalculator
from app.models.schemas import GEXSnapshot
from app.services import background
from app.services.cache import GEXCache

ET = ZoneInfo("America/New_York")
SOURCE = {
    "actual_instrument": "SPY",
    "is_proxy": True,
    "nominal_options_delay_minutes": 15,
    "source_received_at": "2026-10-14T10:00:00-04:00",
    "quote_freshness": "unknown; last trade is not a bid/ask timestamp",
    "open_interest_frequency": "daily",
    "open_interest_asof": None,
}


def options_frame():
    expiry = datetime.now(ET) + timedelta(hours=1)
    frame = pd.DataFrame(
        [
            {
                "strike": strike,
                "type": kind,
                "open_interest": oi,
                "implied_vol": 0.2,
                "expiration": expiry,
                "volume": 100,
                "bid": 10.0,
                "ask": 10.2,
                "mid": 10.1,
            }
            for strike in [5980.0, 5990.0, 6000.0, 6010.0, 6020.0]
            for kind, oi in [("call", 1000), ("put", 1200)]
        ]
    )
    frame.attrs["source_metadata"] = dict(SOURCE)
    return frame


def captured_snapshot(**metrics):
    return GEXSnapshot(
        timestamp=datetime(2026, 10, 14, 10, tzinfo=ET),
        spot_price=6000,
        total_call_gex=2e8,
        total_put_gex=-3e8,
        net_gex=-1e8,
        zero_gamma_level=6000,
        dominant_strike=6000,
        gex_by_strike={6000: -1e8},
        metrics={**SOURCE, "is_replay_eligible": True, **metrics},
    )


@pytest.fixture(autouse=True)
def isolate_analytics():
    reset_advanced_analytics_state()
    yield
    reset_advanced_analytics_state()


def provider(frame):
    return SimpleNamespace(
        provider_name="yfinance",
        get_options_chain_for_gex=AsyncMock(return_value=(frame, 6000)),
    )


@pytest.mark.asyncio
async def test_empty_live_rest_capture_is_unavailable_instead_of_generated(monkeypatch):
    monkeypatch.setattr(gex, "get_data_client", lambda _: provider(pd.DataFrame()))
    with pytest.raises(RuntimeError, match="no contracts"):
        await gex._get_live_gex_snapshot("SPX", "yfinance")


@pytest.mark.asyncio
@pytest.mark.parametrize("synthetic_flag", ["is_mock_data", "is_demo_data"])
@pytest.mark.parametrize("fallback", ["cache", "persisted"])
async def test_rest_resolver_rejects_synthetic_non_demo_fallbacks(
    monkeypatch, synthetic_flag, fallback
):
    cache = GEXCache()
    snapshot = captured_snapshot(**{synthetic_flag: 1})
    if fallback == "cache":
        cache.set("gex:current:SPX:yfinance", snapshot)
    monkeypatch.setattr(
        gex, "_get_live_gex_snapshot", AsyncMock(side_effect=RuntimeError("provider unavailable"))
    )
    monkeypatch.setattr(
        gex,
        "_get_latest_persisted_snapshot",
        AsyncMock(return_value=snapshot if fallback == "persisted" else None),
    )
    with pytest.raises(RuntimeError):
        await gex._resolve_best_snapshot_payload(
            symbol="SPX", active_provider="yfinance", default_provider="yfinance", cache=cache
        )


@pytest.mark.asyncio
async def test_current_rest_response_preserves_source_metrics(monkeypatch):
    cache = GEXCache()
    snapshot = captured_snapshot()
    cache.set("gex:current:SPX:yfinance", snapshot)
    monkeypatch.setattr(gex, "get_cache", lambda: cache)
    payload = await gex.get_current_gex(symbol="SPX", provider="yfinance", demo=False)
    assert payload["provider"] == "yfinance"
    for key, value in SOURCE.items():
        assert payload["metrics"][key] == value


@pytest.mark.asyncio
@pytest.mark.parametrize("producer", ["rest", "websocket", "refresh", "warmup", "historical"])
async def test_every_live_producer_stamps_source_metadata_after_enrichment(monkeypatch, producer):
    module = gex if producer == "rest" else ws if producer == "websocket" else background
    frame = options_frame()
    client = provider(frame)
    cache = GEXCache()
    calculator = GEXCalculator()
    monkeypatch.setattr(module, "get_data_client", lambda *args: client)
    monkeypatch.setattr(module, "get_gex_calculator", lambda: calculator)
    monkeypatch.setattr(module, "get_cache", lambda: cache)
    monkeypatch.setattr(background, "is_market_open", lambda: True)
    monkeypatch.setattr(background, "get_settings", lambda: Settings(data_provider="yfinance"))
    ended = []
    original_enrich = module.enrich_snapshot_with_advanced_analytics

    def enrich(*args, **kwargs):
        result = original_enrich(*args, **kwargs)
        ended.append(datetime.now(ET))
        return result

    monkeypatch.setattr(module, "enrich_snapshot_with_advanced_analytics", enrich)
    if producer == "rest":
        payload = await gex._get_live_gex_snapshot("SPX", "yfinance")
    elif producer == "websocket":
        payload = await ws._get_gex_update(Settings(data_provider="yfinance"))
    elif producer == "historical":
        history = SimpleNamespace(persist_capture=AsyncMock(return_value=True))
        await background._capture_symbol_for_provider(
            provider_name="yfinance",
            symbol="SPX",
            default_provider="yfinance",
            cache=cache,
            gex_calculator=calculator,
            historical_data_service=history,
            capture_timeout_seconds=1,
        )
        payload = cache.get("gex:current:SPX:yfinance").model_dump()
    else:
        if producer == "refresh":
            monkeypatch.setattr(background, "_shutdown_event", asyncio.Event())

            async def stop(_):
                background._shutdown_event.set()

            monkeypatch.setattr(background.asyncio, "sleep", stop)
            await background.periodic_gex_refresh()
        else:
            await background.cache_warmup()
        payload = cache.get("gex:current:SPX:yfinance").model_dump()
    assert ended
    for key, value in SOURCE.items():
        assert payload["metrics"][key] == value
    assert datetime.fromisoformat(payload["metrics"]["feature_available_at"]) >= ended[-1]


@pytest.mark.asyncio
@pytest.mark.parametrize("producer", ["refresh", "warmup"])
async def test_empty_background_chain_keeps_captured_cache_without_mock_replacement(
    monkeypatch, producer
):
    cache = GEXCache()
    existing = captured_snapshot()
    cache.set("gex:current:SPX:yfinance", existing)
    monkeypatch.setattr(background, "get_cache", lambda: cache)
    monkeypatch.setattr(background, "get_data_client", lambda: provider(pd.DataFrame()))
    monkeypatch.setattr(background, "is_market_open", lambda: True)
    monkeypatch.setattr(background, "get_settings", lambda: Settings(data_provider="yfinance"))
    if producer == "refresh":
        monkeypatch.setattr(background, "_shutdown_event", asyncio.Event())

        async def stop(_):
            background._shutdown_event.set()

        monkeypatch.setattr(background.asyncio, "sleep", stop)
        await background.periodic_gex_refresh()
    else:
        await background.cache_warmup()
    assert cache.get("gex:current:SPX:yfinance") is existing


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [True, False])
async def test_rejected_historical_capture_does_not_invalidate_usable_cache(monkeypatch, empty):
    cache = GEXCache()
    cache.update_spot_price(6000, symbol="SPX")
    existing = captured_snapshot()
    cache.set("gex:current:SPX:yfinance", existing)
    frame = pd.DataFrame() if empty else options_frame().iloc[:1].copy()
    client = SimpleNamespace(
        provider_name="yfinance",
        get_options_chain_for_gex=AsyncMock(return_value=(frame, 6200)),
    )
    monkeypatch.setattr(background, "get_data_client", lambda _: client)
    history = SimpleNamespace(persist_capture=AsyncMock(return_value=True))
    await background._capture_symbol_for_provider(
        provider_name="yfinance",
        symbol="SPX",
        default_provider="yfinance",
        cache=cache,
        gex_calculator=GEXCalculator(),
        historical_data_service=history,
        capture_timeout_seconds=1,
    )
    assert cache.get("gex:current:SPX:yfinance") is existing


@pytest.mark.asyncio
async def test_empty_live_websocket_capture_fails_without_generated_update(monkeypatch):
    monkeypatch.setattr(ws, "get_cache", GEXCache)
    monkeypatch.setattr(ws, "get_data_client", lambda _: provider(pd.DataFrame()))
    history = SimpleNamespace(get_latest_snapshot=AsyncMock(return_value=None))
    monkeypatch.setattr(ws, "get_historical_data_service", lambda: history)
    with pytest.raises(RuntimeError, match="no contracts"):
        await ws._get_gex_update(Settings(data_provider="yfinance"))


def test_websocket_captured_payload_preserves_metrics():
    payload = ws._build_live_ws_payload_from_snapshot(
        captured_snapshot(), "yfinance", is_stale=True
    )
    assert payload["is_stale"] is True
    assert payload["metrics"] == captured_snapshot().metrics


@pytest.mark.parametrize("stored", [False, True])
def test_websocket_payload_is_one_coherent_snapshot_with_regime_metadata(stored):
    snapshot = captured_snapshot()
    payload = (
        ws._build_ws_payload_from_snapshot(
            snapshot=snapshot, provider="yfinance", is_demo=True, is_replay=True
        )
        if stored
        else ws._build_live_ws_payload_from_snapshot(snapshot, "yfinance", is_stale=False)
    )
    assert payload["total_call_gex"] == 2e8
    assert payload["total_put_gex"] == -3e8
    assert payload["net_gex"] == -1e8
    assert payload["gex_by_strike"] == {6000: -1e8}
    assert payload["dominant_strike"] == 6000
    assert payload["description"] == "Near-zero signed GEX proxy; no volatility prediction."
    assert payload["color"] == "yellow"


def test_invalid_captured_websocket_payload_is_never_generated_data():
    snapshot = captured_snapshot().model_copy(update={"spot_price": 50})
    with pytest.raises(RuntimeError):
        ws._build_live_ws_payload_from_snapshot(snapshot, "yfinance", is_stale=False)


@pytest.mark.asyncio
async def test_websocket_does_not_relabel_persisted_generated_provider_as_captured(monkeypatch):
    snapshot = captured_snapshot().model_copy(update={"provider": "mock (yfinance empty)"})
    monkeypatch.setattr(ws, "get_cache", GEXCache)
    monkeypatch.setattr(ws, "get_data_client", lambda _: provider(pd.DataFrame()))
    history = SimpleNamespace(get_latest_snapshot=AsyncMock(return_value=snapshot))
    monkeypatch.setattr(ws, "get_historical_data_service", lambda: history)
    with pytest.raises(RuntimeError):
        await ws._get_gex_update(Settings(data_provider="yfinance"))
