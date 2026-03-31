"""Tests for snapshot-quality evaluation and annotation."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from app.core.gex_calculator import GEXCalculator
from app.core.snapshot_quality import annotate_snapshot_quality

ET = ZoneInfo("America/New_York")


def _build_yfinance_like_spx_chain() -> tuple[pd.DataFrame, float]:
    spot_price = 6530.0
    expiration = "2026-03-24"
    strikes = [6490.0, 6500.0, 6510.0, 6520.0, 6530.0, 6540.0, 6550.0, 6560.0, 6570.0]

    rows: list[dict[str, float | int | str | None]] = []
    for offset, strike in enumerate(strikes):
        rows.append(
            {
                "symbol": f"SPY260324C{int(strike * 1000):08d}",
                "strike": strike,
                "expiration": expiration,
                "type": "call",
                "bid": max(0.1, 35.0 - offset * 4.0),
                "ask": max(0.2, 35.5 - offset * 4.0),
                "mid": max(0.15, 35.25 - offset * 4.0),
                "open_interest": 1200 + offset * 50,
                "volume": 100 + offset,
                "implied_vol": 0.19 + offset * 0.005,
                "delta": None,
                "gamma": None,
                "vega": None,
                "theta": None,
            }
        )
        rows.append(
            {
                "symbol": f"SPY260324P{int(strike * 1000):08d}",
                "strike": strike,
                "expiration": expiration,
                "type": "put",
                "bid": max(0.1, 0.8 + offset * 0.4),
                "ask": max(0.2, 1.1 + offset * 0.45),
                "mid": max(0.15, 0.95 + offset * 0.425),
                "open_interest": 1800 + offset * 100,
                "volume": 80 + offset,
                "implied_vol": 0.00001,
                "delta": None,
                "gamma": None,
                "vega": None,
                "theta": None,
            }
        )

    return pd.DataFrame(rows), spot_price


def _build_concentrated_march_27_yfinance_chain() -> tuple[pd.DataFrame, float]:
    """Approximate the March 27, 2026 Yahoo proxy shape that produced trillion-scale replay values."""
    spot_price = 6351.7999267578125
    expiration = "2026-03-27"
    rows = [
        {"symbol": "SPY260327C00630000", "strike": 6300.0, "expiration": expiration, "type": "call", "bid": 51.0, "ask": 51.4, "mid": 51.2, "open_interest": 872, "volume": 8427, "implied_vol": 0.00001, "delta": None, "gamma": None, "vega": None, "theta": None},
        {"symbol": "SPY260327P00630000", "strike": 6300.0, "expiration": expiration, "type": "put", "bid": 1.8, "ask": 1.9, "mid": 1.85, "open_interest": 25668, "volume": 125420, "implied_vol": 0.098642, "delta": None, "gamma": None, "vega": None, "theta": None},
        {"symbol": "SPY260327C00635000", "strike": 6350.0, "expiration": expiration, "type": "call", "bid": 21.5, "ask": 21.8, "mid": 21.65, "open_interest": 827, "volume": 82056, "implied_vol": 0.060434, "delta": None, "gamma": None, "vega": None, "theta": None},
        {"symbol": "SPY260327P00635000", "strike": 6350.0, "expiration": expiration, "type": "put", "bid": 19.7, "ask": 20.1, "mid": 19.9, "open_interest": 29402, "volume": 387675, "implied_vol": 0.088388, "delta": None, "gamma": None, "vega": None, "theta": None},
        {"symbol": "SPY260327C00636000", "strike": 6360.0, "expiration": expiration, "type": "call", "bid": 15.6, "ask": 15.9, "mid": 15.75, "open_interest": 226, "volume": 152234, "implied_vol": 0.066538, "delta": None, "gamma": None, "vega": None, "theta": None},
        {"symbol": "SPY260327P00636000", "strike": 6360.0, "expiration": expiration, "type": "put", "bid": 23.1, "ask": 23.5, "mid": 23.3, "open_interest": 18585, "volume": 326542, "implied_vol": 0.095834, "delta": None, "gamma": None, "vega": None, "theta": None},
        {"symbol": "SPY260327C00640000", "strike": 6400.0, "expiration": expiration, "type": "call", "bid": 4.5, "ask": 4.7, "mid": 4.6, "open_interest": 1577, "volume": 483427, "implied_vol": 0.097665, "delta": None, "gamma": None, "vega": None, "theta": None},
        {"symbol": "SPY260327P00640000", "strike": 6400.0, "expiration": expiration, "type": "put", "bid": 49.8, "ask": 50.3, "mid": 50.05, "open_interest": 51100, "volume": 468138, "implied_vol": 0.160897, "delta": None, "gamma": None, "vega": None, "theta": None},
        {"symbol": "SPY260327C00645000", "strike": 6450.0, "expiration": expiration, "type": "call", "bid": 1.5, "ask": 1.6, "mid": 1.55, "open_interest": 6095, "volume": 239538, "implied_vol": 0.151376, "delta": None, "gamma": None, "vega": None, "theta": None},
        {"symbol": "SPY260327P00645000", "strike": 6450.0, "expiration": expiration, "type": "put", "bid": 98.4, "ask": 99.2, "mid": 98.8, "open_interest": 41958, "volume": 40650, "implied_vol": 0.223152, "delta": None, "gamma": None, "vega": None, "theta": None},
    ]

    return pd.DataFrame(rows), spot_price


def test_annotate_snapshot_quality_marks_corrupted_near_spot_put_iv_as_ineligible():
    """Yahoo-like chains with near-spot put IV collapse should be flagged as bad replay data."""
    options_df, spot_price = _build_yfinance_like_spx_chain()
    snapshot = GEXCalculator().calculate_gex_from_chain(
        options_df=options_df,
        spot_price=spot_price,
        timestamp=datetime(2026, 3, 24, 15, 59, tzinfo=ET),
    )

    annotated = annotate_snapshot_quality(snapshot, options_df=options_df)

    assert annotated.metrics["is_replay_eligible"] is False
    assert annotated.metrics["capture_quality"] < 1.0
    assert annotated.metrics["meaningful_strike_count"] >= 0
    assert "put_iv_corrupted" in annotated.metrics["quality_flags"]


def test_annotate_snapshot_quality_rejects_provider_outlier_yfinance_replay_snapshot():
    """Provider-aware replay screening should reject concentrated Yahoo proxy outliers."""
    options_df, spot_price = _build_concentrated_march_27_yfinance_chain()
    snapshot = GEXCalculator().calculate_gex_from_chain(
        options_df=options_df,
        spot_price=spot_price,
        timestamp=datetime(2026, 3, 27, 15, 34, tzinfo=ET),
    )

    annotated = annotate_snapshot_quality(
        snapshot,
        options_df=options_df,
        provider="yfinance",
    )

    assert annotated.metrics["is_replay_eligible"] is False
    assert annotated.metrics["capture_quality"] < 1.0
    assert "provider_gex_outlier" in annotated.metrics["quality_flags"]
