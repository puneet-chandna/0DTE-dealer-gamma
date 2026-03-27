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
