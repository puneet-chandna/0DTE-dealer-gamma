"""Deterministic regressions for cache identity, expiry, freshness and shared fetches."""

import asyncio
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from fastapi import HTTPException

from app.api import websocket as ws
from app.api.routes import data, gex
from app.models.schemas import GEXSnapshot
from app.services import background
from app.services.cache import GEXCache

ET = ZoneInfo("America/New_York")


def chain(expiration=date(2026, 10, 14)):
    return pd.DataFrame(
        [
            {
                "symbol": "SPX_contract",
                "strike": 6000,
                "expiration": expiration,
                "type": "call",
                "implied_vol": 0.2,
            }
        ]
    )


def snapshot(**kwargs):
    return GEXSnapshot(
        timestamp=kwargs["timestamp"],
        spot_price=kwargs["spot_price"],
        total_call_gex=2e8,
        total_put_gex=-3e8,
        net_gex=-1e8,
        zero_gamma_level=6000,
        dominant_strike=6000,
        gex_by_strike={6000: -1e8},
        provider="yfinance",
        metrics={"is_replay_eligible": True},
    )


def test_provider_baselines_and_invalidation_are_independent():
    cache = GEXCache()
    yahoo = {"provider": "yfinance"}
    tradier = {"provider": "tradier"}
    for key, value in {
        "gex:current:SPX": yahoo,
        "gex:current:SPX:yfinance": yahoo,
        "gex:current:SPX:tradier": tradier,
        "gex:current:SPY:yfinance": yahoo,
        "options:chain:SPX:2026-10-14:yfinance": yahoo,
        "options:chain:SPX:2026-10-14:tradier": tradier,
    }.items():
        cache.set(key, value)
    for provider, spot in [("yfinance", 6000), ("tradier", 6120), ("yfinance", 6000)]:
        assert not cache.update_spot_price(spot, symbol="SPX", provider=provider)
    assert cache.update_spot_price(6300, symbol="SPX", provider="tradier")
    assert cache.get("gex:current:SPX:tradier") is None
    assert cache.get("options:chain:SPX:2026-10-14:tradier") is None
    assert cache.get("gex:current:SPX") == yahoo
    assert cache.get("gex:current:SPX:yfinance") == yahoo
    assert cache.get("gex:current:SPY:yfinance") == yahoo
    assert cache.get("options:chain:SPX:2026-10-14:yfinance") == yahoo
    assert cache.update_spot_price(6200, symbol="SPX", provider="yfinance")
    assert cache.get("gex:current:SPX") is None


@pytest.mark.asyncio
async def test_default_chain_changes_at_open_and_rejects_previous_expiration():
    cache = GEXCache()
    clock = datetime(2026, 10, 14, 9, 29, 50, tzinfo=ET)
    client = SimpleNamespace(
        provider_name="yfinance",
        get_options_chain_snapshot=AsyncMock(side_effect=[chain(date(2026, 10, 13)), chain()]),
        get_spot_price=AsyncMock(return_value=6000),
    )
    with (
        patch.object(data, "get_cache", return_value=cache),
        patch.object(data, "get_data_client", return_value=client),
        patch.object(data, "datetime", wraps=datetime) as endpoint_clock,
        patch("app.services.cache.datetime") as cached_clock,
    ):
        endpoint_clock.now.return_value = clock
        cached_clock.now.return_value = clock.replace(tzinfo=None)
        before = await data.get_options_chain("SPX", None, "yfinance")
        endpoint_clock.now.return_value = clock + timedelta(seconds=20)
        cached_clock.now.return_value += timedelta(seconds=20)
        after = await data.get_options_chain("SPX", None, "yfinance")
        assert before.expiration_date == "2026-10-13"
        assert after.expiration_date == "2026-10-14"
        assert client.get_options_chain_snapshot.await_count == 2
        # An expired resolved chain cannot be relabelled with the new session key.
        cache.clear()
        client.get_options_chain_snapshot.side_effect = [chain(date(2026, 10, 13))]
        with pytest.raises(HTTPException) as error:
            await data.get_options_chain("SPX", None, "yfinance")
        assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_preopen_chain_is_not_default_fallback_after_open():
    cache = GEXCache()
    client = SimpleNamespace(
        provider_name="yfinance",
        get_options_chain_snapshot=AsyncMock(return_value=chain(date(2026, 10, 13))),
        get_spot_price=AsyncMock(return_value=6000),
    )
    with (
        patch.object(data, "get_cache", return_value=cache),
        patch.object(data, "get_data_client", return_value=client),
        patch.object(data, "datetime", wraps=datetime) as clock,
    ):
        clock.now.return_value = datetime(2026, 10, 14, 9, 29, 50, tzinfo=ET)
        await data.get_options_chain("SPX", None, "yfinance")
        clock.now.return_value += timedelta(seconds=20)
        client.get_options_chain_snapshot.side_effect = RuntimeError("offline")
        with pytest.raises(HTTPException) as error:
            await data.get_options_chain("SPX", None, "yfinance")
        assert error.value.status_code == 503
        # Explicit past expirations keep the established historical-request behavior.
        client.get_options_chain_snapshot.side_effect = None
        explicit = await data.get_options_chain("SPX", "2026-10-13", "yfinance")
        assert explicit.expiration_date == "2026-10-13"


@pytest.mark.asyncio
async def test_blank_expiration_uses_default_expiry_validation_and_cache_identity():
    cache = GEXCache()
    client = SimpleNamespace(
        provider_name="yfinance",
        get_options_chain_snapshot=AsyncMock(return_value=chain(date(2026, 10, 13))),
        get_spot_price=AsyncMock(return_value=6000),
    )
    with (
        patch.object(data, "get_cache", return_value=cache),
        patch.object(data, "get_data_client", return_value=client),
        patch.object(data, "datetime", wraps=datetime) as clock,
    ):
        clock.now.return_value = datetime(2026, 10, 14, 10, tzinfo=ET)
        with pytest.raises(HTTPException) as error:
            await data.get_options_chain("SPX", "", "yfinance")
        assert error.value.status_code == 503
        assert cache.get("options:chain:SPX:default:2026-10-14:yfinance") is None
        client.get_options_chain_snapshot.return_value = chain(date(2026, 10, 14))
        response = await data.get_options_chain("SPX", "", "yfinance")
        same_default = await data.get_options_chain("SPX", None, "yfinance")
        assert response.expiration_date == same_default.expiration_date == "2026-10-14"
        assert client.get_options_chain_snapshot.await_count == 2


@pytest.mark.parametrize("endpoint", ["spot", "chain"])
@pytest.mark.asyncio
async def test_raw_cache_fallback_labels_age_and_current_status_without_mutation(endpoint):
    cache = GEXCache()
    captured = datetime(2026, 10, 14, 15, 59, 59, tzinfo=ET)
    client = SimpleNamespace(
        provider_name="yfinance",
        get_options_chain_snapshot=AsyncMock(return_value=chain()),
        get_spot_price=AsyncMock(return_value=6000),
    )
    fetch = (
        (lambda: data.get_spot_price("SPX", "yfinance"))
        if endpoint == "spot"
        else (lambda: data.get_options_chain("SPX", None, "yfinance"))
    )
    with (
        patch.object(data, "get_cache", return_value=cache),
        patch.object(data, "get_data_client", return_value=client),
        patch.object(data, "datetime", wraps=datetime) as endpoint_clock,
        patch("app.services.cache.datetime") as cached_clock,
        patch.object(data, "is_market_open", return_value=True) as market,
    ):
        endpoint_clock.now.return_value = captured
        cached_clock.now.return_value = captured.replace(tzinfo=None)
        first = await fetch()
        first = first if isinstance(first, dict) else first.model_dump()
        assert first["is_stale"] is False
        # Fresh cache also reflects response-time status across the close.
        market.return_value = False
        fresh = await fetch()
        fresh = fresh if isinstance(fresh, dict) else fresh.model_dump()
        assert fresh["market_status"] == "closed"
        endpoint_clock.now.return_value = captured + timedelta(minutes=5)
        cached_clock.now.return_value += timedelta(minutes=5)
        client.get_spot_price.side_effect = RuntimeError("offline")
        client.get_options_chain_snapshot.side_effect = RuntimeError("offline")
        fallback = await fetch()
        fallback = fallback if isinstance(fallback, dict) else fallback.model_dump()
        assert fallback["is_stale"] is True
        assert fallback["age_seconds"] == 300
        assert fallback["captured_at"] == first["timestamp"] == fallback["timestamp"]
        assert fallback["market_status"] == "closed"
        cached_response = next(
            value for _, value in cache._cache.values() if isinstance(value, dict)
        )
        assert cached_response["is_stale"] is False
        assert cached_response["market_status"] == "open"


@pytest.mark.asyncio
async def test_shared_fetch_success_error_and_copy_isolation():
    cache = GEXCache()
    started, release = asyncio.Event(), asyncio.Event()

    async def fetch():
        started.set()
        await release.wait()
        return chain(), 6000

    call = AsyncMock(side_effect=fetch)
    first = asyncio.create_task(cache.fetch_once("same", call))
    await started.wait()
    second = asyncio.create_task(cache.fetch_once("same", call))
    await asyncio.sleep(0)
    release.set()
    one, two = await asyncio.gather(first, second)
    assert call.await_count == 1
    one[0].loc[0, "strike"] = 1
    assert two[0].loc[0, "strike"] == 6000
    assert not cache._inflight
    failure = AsyncMock(side_effect=RuntimeError("offline"))
    errors = await asyncio.gather(
        cache.fetch_once("error", failure),
        cache.fetch_once("error", failure),
        return_exceptions=True,
    )
    assert all(isinstance(error, RuntimeError) for error in errors)
    assert failure.await_count == 1
    assert not cache._inflight
    assert await cache.fetch_once("error", AsyncMock(return_value=123)) == 123


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_cancel_other_waiter_and_last_waiter_cleans_up():
    cache = GEXCache()
    started, release, canceled = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def fetch():
        started.set()
        try:
            await release.wait()
            return 123
        finally:
            canceled.set()

    first = asyncio.create_task(cache.fetch_once("same", fetch))
    await started.wait()
    second = asyncio.create_task(cache.fetch_once("same", fetch))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert not canceled.is_set()
    release.set()
    assert await second == 123
    assert not cache._inflight
    started.clear()
    release.clear()
    canceled.clear()
    only = asyncio.create_task(cache.fetch_once("same", fetch))
    await started.wait()
    only.cancel()
    with pytest.raises(asyncio.CancelledError):
        await only
    await canceled.wait()
    assert not cache._inflight
    assert await cache.fetch_once("same", AsyncMock(return_value=456)) == 456


@pytest.mark.asyncio
async def test_shared_gex_fetch_isolates_provider_and_symbol():
    cache = GEXCache()
    clients = [
        SimpleNamespace(
            provider_name=name, get_options_chain_for_gex=AsyncMock(return_value=(chain(), 6000))
        )
        for name in ("yfinance", "tradier")
    ]
    await asyncio.gather(
        cache.fetch_gex_chain(clients[0], "SPX"),
        cache.fetch_gex_chain(clients[1], "SPX"),
        cache.fetch_gex_chain(clients[0], "SPY"),
    )
    assert clients[0].get_options_chain_for_gex.await_count == 2
    assert clients[1].get_options_chain_for_gex.await_count == 1


@pytest.mark.asyncio
async def test_gex_fetch_inflight_key_changes_at_trading_session_boundary():
    cache = GEXCache()
    release = asyncio.Event()

    async def fetch(underlying):
        await release.wait()
        return chain(), 6000

    client = SimpleNamespace(
        provider_name="yfinance", get_options_chain_for_gex=AsyncMock(side_effect=fetch)
    )
    with patch(
        "app.services.cache.get_current_trading_date", return_value=date(2026, 10, 13)
    ) as session:
        previous = asyncio.create_task(cache.fetch_gex_chain(client, "SPX"))
        await asyncio.sleep(0)
        session.return_value = date(2026, 10, 14)
        current = asyncio.create_task(cache.fetch_gex_chain(client, "SPX"))
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(previous, current)
    assert client.get_options_chain_for_gex.await_count == 2


@pytest.mark.asyncio
async def test_rest_websocket_and_background_share_fetch_and_background_still_persists():
    cache = GEXCache()
    started, release = asyncio.Event(), asyncio.Event()

    async def fetch(underlying):
        started.set()
        await release.wait()
        return chain(), 6000

    client = SimpleNamespace(
        provider_name="yfinance", get_options_chain_for_gex=AsyncMock(side_effect=fetch)
    )
    calculator = SimpleNamespace(calculate_gex_from_chain=snapshot)
    history = SimpleNamespace(persist_capture=AsyncMock(return_value=True))
    with (
        patch.object(background, "get_data_client", return_value=client),
        patch.object(gex, "get_data_client", return_value=client),
        patch.object(gex, "get_cache", return_value=cache),
        patch.object(ws, "get_cache", return_value=cache),
        patch.object(ws, "get_data_client", return_value=client),
        patch.object(ws, "get_gex_calculator", return_value=calculator),
        patch.object(gex, "get_gex_calculator", return_value=calculator),
        patch.object(background, "annotate_snapshot_quality", side_effect=lambda value, **_: value),
        patch.object(
            background,
            "enrich_snapshot_with_advanced_analytics",
            side_effect=lambda value, **_: value,
        ),
        patch.object(gex, "annotate_snapshot_quality", side_effect=lambda value, **_: value),
        patch.object(ws, "annotate_snapshot_quality", side_effect=lambda value, **_: value),
        patch.object(
            ws, "enrich_snapshot_with_advanced_analytics", side_effect=lambda value, **_: value
        ),
        patch.object(
            gex, "enrich_snapshot_with_advanced_analytics", side_effect=lambda value, **_: value
        ),
    ):
        capture = asyncio.create_task(
            background._capture_symbol_for_provider(
                provider_name="yfinance",
                symbol="SPX",
                default_provider="yfinance",
                cache=cache,
                gex_calculator=calculator,
                historical_data_service=history,
                capture_timeout_seconds=1,
            )
        )
        await started.wait()
        rest = asyncio.create_task(
            gex._resolve_best_snapshot_payload(
                symbol="SPX", active_provider="yfinance", default_provider="yfinance", cache=cache
            )
        )
        websocket = asyncio.create_task(
            ws._get_gex_update(SimpleNamespace(data_provider="yfinance"), symbol="SPX")
        )
        for _ in range(4):
            await asyncio.sleep(0)
        assert next(iter(cache._inflight.values()))[1] == 3
        release.set()
        persisted, response, ws_response = await asyncio.gather(capture, rest, websocket)
    assert persisted
    assert response["spot_price"] == 6000
    assert ws_response["spot_price"] == 6000
    assert client.get_options_chain_for_gex.await_count == 1
    history.persist_capture.assert_awaited_once()
