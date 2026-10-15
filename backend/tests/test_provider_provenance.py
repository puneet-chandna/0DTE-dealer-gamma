"""Provider clocks survive normalization without confusing trades with quotes."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from app.core.provenance import source_timestamp
from app.core.tradier_provider import TradierClient
from app.core.yfinance_provider import YFinanceClient
from app.models.schemas import HawkesStateModel


@pytest.mark.asyncio
async def test_yahoo_retains_trade_and_receipt_clocks_but_does_not_invent_quote_time(monkeypatch):
    calls = pd.DataFrame(
        [
            {
                "contractSymbol": "SPY250106C00600000",
                "strike": 600.0,
                "bid": 1.0,
                "ask": 1.2,
                "openInterest": 100,
                "volume": 20,
                "impliedVolatility": 0.2,
                "lastTradeDate": pd.Timestamp("2025-01-06T14:30:00Z"),
            }
        ]
    )
    ticker = SimpleNamespace(
        options=["2025-01-06"],
        option_chain=lambda _: SimpleNamespace(calls=calls, puts=calls.iloc[:0]),
    )
    monkeypatch.setattr("app.core.yfinance_provider.yf.Ticker", lambda _: ticker)
    frame = await YFinanceClient().get_options_chain_snapshot("SPX", date(2025, 1, 6))
    assert frame.iloc[0]["last_trade_at"] == "2025-01-06T14:30:00+00:00"
    assert frame.iloc[0]["bid_timestamp"] is None
    assert frame.iloc[0]["ask_timestamp"] is None
    assert frame.iloc[0]["received_at"]
    assert frame.attrs["source_metadata"]["actual_instrument"] == "SPY"
    assert frame.attrs["source_metadata"]["is_proxy"] is True
    assert frame.attrs["source_metadata"]["nominal_options_delay_minutes"] == 15
    assert frame.attrs["source_metadata"]["open_interest_asof"] is None


@pytest.mark.asyncio
async def test_tradier_preserves_bid_ask_trade_and_greek_source_clocks(monkeypatch):
    provider = TradierClient(api_key="fixture-not-a-real-key")
    monkeypatch.setattr(provider, "get_expirations", AsyncMock(return_value=["2025-01-06"]))
    monkeypatch.setattr(
        provider,
        "_request",
        AsyncMock(
            return_value={
                "options": {
                    "option": [
                        {
                            "symbol": "SPY250106C00600000",
                            "strike": 600,
                            "option_type": "call",
                            "bid_date": 1736173800000,
                            "ask_date": 1736173801000,
                            "trade_date": 1736173799000,
                            "greeks": {"updated_at": "2025-01-06 09:29:00"},
                        }
                    ]
                }
            }
        ),
    )
    frame = await provider.get_options_chain_snapshot("SPY", date(2025, 1, 6))
    assert frame.iloc[0]["bid_timestamp"] == "2025-01-06T14:30:00+00:00"
    assert frame.iloc[0]["ask_timestamp"] == "2025-01-06T14:30:01+00:00"
    assert frame.iloc[0]["last_trade_at"] == "2025-01-06T14:29:59+00:00"
    assert frame.iloc[0]["greeks_updated_at"] == "2025-01-06 09:29:00"
    assert frame.iloc[0]["received_at"]
    assert frame.attrs["source_metadata"]["actual_instrument"] == "SPY"
    assert frame.attrs["source_metadata"]["is_proxy"] is False
    await provider.close()


@pytest.mark.parametrize(
    "value, unix, expected",
    [
        (1736173800000, True, "2025-01-06T14:30:00+00:00"),
        (1736173800, True, "2025-01-06T14:30:00+00:00"),
        (None, False, None),
        ("bad-source-clock", False, None),
        (float("nan"), True, None),
    ],
)
def test_missing_or_invalid_source_clock_remains_unknown(value, unix, expected):
    assert source_timestamp(value, unix=unix) == expected


def test_legacy_stored_hawkes_field_is_read_but_current_output_is_a_score():
    state = HawkesStateModel(
        call_intensity=1, put_intensity=0, net_toxicity=1, squeeze_probability=0.7
    )
    assert state.model_dump()["squeeze_score"] == 0.7
    assert "squeeze_probability" not in state.model_dump()
