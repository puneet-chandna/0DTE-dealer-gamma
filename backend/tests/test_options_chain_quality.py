"""Options-chain boundary checks use a fake provider and the real cache."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.cache import GEXCache

ROW = {
    "symbol": "SPXW261014C05500000",
    "strike": 5500.0,
    "expiration": "2026-10-14",
    "type": "call",
    "bid": 10.0,
    "ask": 12.0,
    "mid": 11.0,
    "open_interest": 100,
    "volume": 50,
    "implied_vol": 0.2,
}
PARAMS = {"provider": "yfinance", "expiration": "2026-10-14"}
CACHE_KEY = "options:chain:SPX:2026-10-14:yfinance"


@pytest.fixture
def chain_api(monkeypatch):
    cache = GEXCache()
    provider = SimpleNamespace(
        provider_name="yfinance",
        get_options_chain_snapshot=AsyncMock(return_value=pd.DataFrame([ROW])),
        get_spot_price=AsyncMock(return_value=5500.0),
    )
    monkeypatch.setattr("app.api.routes.data.get_data_client", lambda _: provider)
    monkeypatch.setattr("app.api.routes.data.get_cache", lambda: cache)
    return TestClient(app, raise_server_exceptions=False), provider, cache


@pytest.mark.parametrize("iv", [None, float("nan"), float("inf"), -float("inf"), 0])
def test_missing_or_nonfinite_iv_is_nullable_and_cacheable(chain_api, iv):
    client, provider, cache = chain_api
    provider.get_options_chain_snapshot.return_value = pd.DataFrame([ROW | {"implied_vol": iv}])

    response = client.get("/api/data/options-chain", params=PARAMS)

    assert response.status_code == 200
    assert response.json()["contracts"][0]["implied_vol"] is None
    assert cache.get(CACHE_KEY) == response.json()
    repeated = client.get("/api/data/options-chain", params=PARAMS).json()
    assert repeated["age_seconds"] >= response.json()["age_seconds"]
    assert repeated == response.json() | {"age_seconds": repeated["age_seconds"]}
    provider.get_options_chain_snapshot.assert_awaited_once()


@pytest.mark.parametrize("field", ["spot", "strike", "bid", "ask", "mid", "volume", "open_interest"])
@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("has_stale", [False, True])
def test_invalid_required_numbers_preserve_cache_and_use_valid_stale(chain_api, field, value, has_stale):
    client, provider, cache = chain_api
    previous = None
    if has_stale:
        first = client.get("/api/data/options-chain", params=PARAMS)
        assert first.status_code == 200
        previous = first.json()

    if field == "spot":
        provider.get_spot_price.return_value = value
    else:
        provider.get_options_chain_snapshot.return_value = pd.DataFrame([ROW | {field: value}])

    # Age any good entry beyond its 30-second TTL, retaining the stale fallback.
    with patch("app.services.cache.datetime") as clock:
        clock.now.return_value = datetime.now() + timedelta(minutes=1)
        with (
            patch.object(cache, "update_spot_price", wraps=cache.update_spot_price) as update_spot,
            patch.object(cache, "set", wraps=cache.set) as set_cache,
        ):
            response = client.get("/api/data/options-chain", params=PARAMS)

        assert response.status_code == (200 if has_stale else 503)
        if has_stale:
            body = response.json()
            assert body["is_stale"] is True
            assert body["age_seconds"] >= previous["age_seconds"]
            assert body == previous | {"is_stale": True, "age_seconds": body["age_seconds"]}
        else:
            assert "Unable to fetch options chain" in response.json()["detail"]
        update_spot.assert_not_called()
        set_cache.assert_not_called()
        assert cache.get(CACHE_KEY) == previous
