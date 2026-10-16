"""Raw market data keeps unavailable values distinct from genuine zeroes."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.routes import analytics, data, gex
from app.core.base_provider import optional_market_number
from app.core.gex_calculator import GEXCalculator
from app.core.provider_registry import ProviderRegistry
from app.core.tradier_provider import TradierClient
from app.core.vollib_bridge import VolLibBridge
from app.core.yfinance_provider import YFinanceClient
from app.services.cache import GEXCache

app = FastAPI()
app.include_router(data.router, prefix="/api/data")
app.include_router(gex.router, prefix="/api/gex")
app.include_router(analytics.router, prefix="/api/analytics")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value", [None, pd.NA, float("nan"), float("inf"), -float("inf"), "unavailable"]
)
async def test_options_chain_serializes_unavailable_numeric_cells_as_null(monkeypatch, value):
    row = {
        "symbol": "SPY20990115C00600000",
        "strike": 6000,
        "expiration": date(2099, 1, 15),
        "type": "call",
        **dict.fromkeys(("bid", "ask", "mid", "open_interest", "volume", "implied_vol"), value),
    }
    cache = GEXCache()
    provider = SimpleNamespace(
        provider_name="yfinance",
        get_options_chain_snapshot=AsyncMock(return_value=pd.DataFrame([row])),
        get_spot_price=AsyncMock(return_value=6000),
    )
    monkeypatch.setattr(data, "get_data_client", lambda _: provider)
    monkeypatch.setattr(data, "get_cache", lambda: cache)
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    for _ in range(2):  # The fresh response and cache hit must both be valid JSON.
        response = await client.get(
            "/api/data/options-chain", params={"provider": "yfinance", "expiration": "2099-01-15"}
        )
        assert response.status_code == 200, response.text
        contract = response.json()["contracts"][0]
        assert {
            field: contract[field]
            for field in ("bid", "ask", "mid", "open_interest", "volume", "implied_vol")
        } == dict.fromkeys(("bid", "ask", "mid", "open_interest", "volume", "implied_vol"))
    provider.get_options_chain_snapshot.assert_awaited_once()


@pytest.mark.asyncio
async def test_options_chain_preserves_zeroes_and_missing_columns(monkeypatch):
    base = {
        "symbol": "SPY_contract",
        "strike": 6000,
        "expiration": date(2099, 1, 15),
        "type": "call",
    }
    rows = [
        base,
        {**base, "bid": 0, "ask": 2, "mid": 1, "open_interest": 0, "volume": 7, "implied_vol": 0},
    ]
    provider = SimpleNamespace(
        provider_name="yfinance",
        get_options_chain_snapshot=AsyncMock(return_value=pd.DataFrame(rows)),
        get_spot_price=AsyncMock(return_value=6000),
    )
    monkeypatch.setattr(data, "get_data_client", lambda _: provider)
    monkeypatch.setattr(data, "get_cache", lambda: GEXCache())

    response = await AsyncClient(transport=ASGITransport(app=app), base_url="http://test").get(
        "/api/data/options-chain", params={"provider": "yfinance", "expiration": "2099-01-15"}
    )
    assert response.status_code == 200, response.text
    missing, valid = response.json()["contracts"]
    assert all(
        missing[field] is None
        for field in ("bid", "ask", "mid", "open_interest", "volume", "implied_vol")
    )
    assert {
        field: valid[field]
        for field in ("bid", "ask", "mid", "open_interest", "volume", "implied_vol")
    } == {"bid": 0, "ask": 2, "mid": 1, "open_interest": 0, "volume": 7, "implied_vol": None}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/gex/current",
        "/api/gex/strikes",
        "/api/gex/regime",
        "/api/gex/historical",
        "/api/data/options-chain",
        "/api/data/spot-price",
        "/api/analytics/technical-indicators",
    ],
)
@pytest.mark.parametrize("demo", [False, True])
async def test_unknown_provider_is_a_client_error_before_data_access(monkeypatch, path, demo):
    def unexpected_client(_):
        pytest.fail("Unknown providers must be rejected before constructing a data client")

    monkeypatch.setattr(data, "get_data_client", unexpected_client)
    response = await AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ).get(
        path,
        params={
            "provider": "unknown",
            "demo": str(demo).lower(),
            "start_date": "2025-01-01",
            "end_date": "2025-01-02",
        },
    )
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Unknown provider 'unknown'"


def test_provider_defaults_and_strict_explicit_validation_are_unchanged():
    assert ProviderRegistry.resolve_provider_name(" YFINANCE ") == "yfinance"
    assert ProviderRegistry.resolve_provider_name(default_provider="unknown") == "yfinance"
    with pytest.raises(ValueError, match="Unknown provider 'unknown'"):
        ProviderRegistry.resolve_provider_name("unknown")


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/data/options-chain", "/api/data/spot-price"])
async def test_registered_unavailable_provider_keeps_service_unavailable_status(monkeypatch, path):
    monkeypatch.setattr(ProviderRegistry, "_instances", {})
    monkeypatch.setattr(
        "app.core.provider_registry.get_settings",
        lambda: SimpleNamespace(data_provider="yfinance", tradier_api_key=None),
    )
    monkeypatch.setattr(data, "get_cache", lambda: GEXCache())
    response = await AsyncClient(transport=ASGITransport(app=app), base_url="http://test").get(
        path, params={"provider": "tradier"}
    )
    assert response.status_code == 503
    assert "TRADIER_API_KEY" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name", ["yfinance", "tradier"])
@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -float("inf"), 0])
async def test_provider_chains_preserve_unavailable_quotes_and_counts(
    monkeypatch, provider_name, value
):
    row = {"strike": 600, "bid": value, "ask": 2, "volume": value}
    if provider_name == "yfinance":
        row.update(contractSymbol="SPY_contract", openInterest=value, impliedVolatility=0.2)
        ticker = SimpleNamespace(
            options=["2099-01-15"],
            option_chain=lambda _: SimpleNamespace(calls=pd.DataFrame([row]), puts=pd.DataFrame()),
        )
        monkeypatch.setattr("app.core.yfinance_provider.yf.Ticker", lambda _: ticker)
        provider = YFinanceClient()
    else:
        row.update(
            symbol="SPX_contract", open_interest=value, option_type="call", greeks={"mid_iv": 0.2}
        )
        provider = TradierClient(api_key="fixture-key")
        monkeypatch.setattr(provider, "get_expirations", AsyncMock(return_value=["2099-01-15"]))
        monkeypatch.setattr(
            provider, "_request", AsyncMock(return_value={"options": {"option": [row]}})
        )
    try:
        frame = await provider.get_options_chain_snapshot("SPX", date(2099, 1, 15))
    finally:
        await provider.close()
    result = frame.iloc[0]
    if value == 0:
        assert result["bid"] == result["open_interest"] == result["volume"] == 0
        assert result["mid"] == (10 if provider_name == "yfinance" else 1)
    else:
        assert all(pd.isna(result[field]) for field in ("bid", "mid", "open_interest", "volume"))
    assert result["ask"] == (20 if provider_name == "yfinance" else 2)
    # Missing counts must remain a numeric frame that the GEX filter can reject.
    assert (
        GEXCalculator()
        .calculate_gex_from_chain(
            frame, spot_price=6000, timestamp=datetime(2099, 1, 15, tzinfo=UTC)
        )
        .net_gex
        == 0
    )


@pytest.mark.parametrize("mid", [None, pd.NA, float("nan"), float("inf"), -float("inf")])
def test_iv_surface_skips_unavailable_mid_prices(mid):
    frame = pd.DataFrame([{"strike": 6000, "type": "call", "mid": mid}])
    assert VolLibBridge.calculate_iv_surface(frame, spot_price=6000).empty


@pytest.mark.parametrize("value", [-1, 1.5])
def test_invalid_contract_counts_are_unavailable_instead_of_truncated(value):
    assert optional_market_number(value, integer=True) is None
