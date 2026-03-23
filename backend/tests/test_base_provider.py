"""Tests for the abstract DataProvider contract."""

from datetime import date

import pandas as pd
import pytest

from app.core.base_provider import DataProvider


class DummyProvider(DataProvider):
    """Minimal concrete implementation for exercising shared helpers."""

    provider_name = "dummy"
    display_name = "Dummy Provider"
    provides_greeks = True
    supports_spx_directly = True
    rate_limit = 42
    requires_api_key = False

    async def get_spot_price(self, symbol: str = "SPX") -> float:
        return 123.45

    async def get_expirations(self, underlying: str = "SPX") -> list[str]:
        return ["2099-01-15"]

    async def get_options_chain_snapshot(
        self,
        underlying: str = "SPX",
        expiration_date: date | None = None,
    ) -> pd.DataFrame:
        return pd.DataFrame()

    async def get_options_chain_for_gex(
        self,
        underlying: str = "SPX",
    ) -> tuple[pd.DataFrame, float]:
        return pd.DataFrame(), 123.45

    async def close(self) -> None:
        return None


def test_data_provider_is_abstract():
    """The base provider must not be directly instantiated."""
    with pytest.raises(TypeError):
        DataProvider()


def test_get_capabilities_reflects_provider_metadata():
    """Shared capability serialization should expose provider metadata."""
    provider = DummyProvider()

    assert provider.get_capabilities() == {
        "name": "dummy",
        "display_name": "Dummy Provider",
        "provides_greeks": True,
        "supports_spx_directly": True,
        "rate_limit": 42,
        "requires_api_key": False,
        "features": ["spot_price", "options_chain", "greeks", "spx_direct"],
    }
