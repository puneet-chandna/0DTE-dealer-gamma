"""Tests for the Tradier data provider."""

from datetime import date
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from app.core.tradier_provider import TradierClient


@pytest.mark.asyncio
async def test_get_spot_price_uses_last_close_or_prevclose():
    """Spot price extraction should handle the common quote response shapes."""
    client = TradierClient(api_key="test-key")
    client._request = AsyncMock(return_value={"quotes": {"quote": {"last": None, "close": 5012.5}}})

    try:
        price = await client.get_spot_price("SPX")
    finally:
        await client.close()

    assert price == 5012.5


@pytest.mark.asyncio
async def test_get_expirations_normalizes_single_date_response():
    """Single expiration string payloads should be normalized to a list."""
    client = TradierClient(api_key="test-key")
    client._request = AsyncMock(
        return_value={"expirations": {"date": "2099-01-15"}}
    )

    try:
        expirations = await client.get_expirations("SPX")
    finally:
        await client.close()

    assert expirations == ["2099-01-15"]


@pytest.mark.asyncio
async def test_get_options_chain_snapshot_maps_tradier_payload_to_standard_columns():
    """Options chain mapping should preserve the shared provider schema."""
    client = TradierClient(api_key="test-key")
    client.get_expirations = AsyncMock(return_value=["2099-01-15"])
    client._request = AsyncMock(
        return_value={
            "options": {
                "option": [
                    {
                        "symbol": "SPXW20990115C05000000",
                        "strike": 5000,
                        "expiration_date": "2099-01-15",
                        "option_type": "call",
                        "bid": 10.0,
                        "ask": 12.0,
                        "open_interest": 100,
                        "volume": 50,
                        "greeks": {
                            "mid_iv": 0.21,
                            "delta": 0.51,
                            "gamma": 0.01,
                            "vega": 0.12,
                            "theta": -0.03,
                        },
                    }
                ]
            }
        }
    )

    try:
        result = await client.get_options_chain_snapshot(
            "SPX", expiration_date=date(2099, 1, 15)
        )
    finally:
        await client.close()

    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == [
        "symbol",
        "strike",
        "expiration",
        "type",
        "bid",
        "ask",
        "mid",
        "open_interest",
        "volume",
        "implied_vol",
        "delta",
        "gamma",
        "vega",
        "theta",
    ]
    assert result.iloc[0].to_dict() == {
        "symbol": "SPXW20990115C05000000",
        "strike": 5000.0,
        "expiration": "2099-01-15",
        "type": "call",
        "bid": 10.0,
        "ask": 12.0,
        "mid": 11.0,
        "open_interest": 100,
        "volume": 50,
        "implied_vol": 0.21,
        "delta": 0.51,
        "gamma": 0.01,
        "vega": 0.12,
        "theta": -0.03,
    }
