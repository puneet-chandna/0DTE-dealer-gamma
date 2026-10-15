"""Engineering checks for the fixed cost grid; generated bars are not market evidence."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from tests.test_research_gex_volatility import create_capture_db

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/backtest_cost_sensitivity.py"


def cost_module():
    spec = importlib.util.spec_from_file_location("backtest_cost_sensitivity", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def captured_fixture(prices=(100, 100, 100, 110, 110, 110), signals=None):
    index = pd.date_range(
        "2025-10-06 09:31", periods=len(prices), freq="min", tz="America/New_York"
    )
    prices = pd.DataFrame({"close": prices}, index=index)
    if signals is None:
        signals = [-2e9, -2e9, 1e9, 1e9, 1e9, 1e9]
    gex = pd.DataFrame({"net_gex": signals}, index=index)
    gex.attrs = {
        "timestamp_basis": "feature completion; bars labeled at end",
        "calculation_versions": ["fixture_v1"],
        "source_metadata": {"actual_instrument": "SPY", "is_proxy": False},
        "quality_limitations": ["Engineering fixture only."],
    }
    return prices, gex


def test_fixed18_cells_hold_signals_constant_and_charge_both_orders():
    # A cost grid choosing different signals or charging only entry fees changes these returns.
    prices, gex = captured_fixture()
    original = prices.copy(deep=True)
    report, rows = cost_module().evaluate_grid(prices, gex, "yfinance", "SPY")
    assert report["status"] == "evaluated"
    assert len(rows) == 18
    assert (
        len({(row["fees_bps"], row["slippage_bps"], row["execution_delay_bars"]) for row in rows})
        == 18
    )
    zero = next(
        row
        for row in rows
        if row["fees_bps"] == row["slippage_bps"] == 0 and row["execution_delay_bars"] == 1
    )
    worst = next(
        row
        for row in rows
        if row["fees_bps"] == row["slippage_bps"] == 10 and row["execution_delay_bars"] == 1
    )
    assert zero["marked_total_return"] == pytest.approx(0.10)
    assert zero["closed_trades"] == 1
    assert zero["open_trades"] == 0
    assert worst["marked_total_return"] == pytest.approx(0.0956087868)
    pd.testing.assert_frame_equal(prices, original)


def test_open_position_is_marked_without_inventing_an_exit():
    prices, gex = captured_fixture(prices=(100, 100, 110), signals=[-2e9] * 3)
    report, rows = cost_module().evaluate_grid(prices, gex, "yfinance", "SPY")
    assert report["status"] == "evaluated"
    zero = next(
        row
        for row in rows
        if row["fees_bps"] == row["slippage_bps"] == 0 and row["execution_delay_bars"] == 1
    )
    assert zero["marked_total_return"] == pytest.approx(0.10)
    assert zero["open_trades"] == 1
    assert zero["closed_trades"] == 0


def test_irregular_gap_is_not_treated_as_a_one_minute_fill_delay():
    prices, gex = captured_fixture()
    prices = prices.drop(prices.index[2])
    gex = gex.drop(gex.index[2])
    report, rows = cost_module().evaluate_grid(prices, gex, "yfinance", "SPY")
    assert report["status"] == "insufficient_data"
    assert rows == []
    assert "gap" in report["reason"].lower()


@pytest.mark.parametrize(
    "change", ["unknown_clock", "mixed_versions", "too_short", "invalid_price"]
)
def test_unqualified_data_does_not_produce_grid_results(change):
    prices, gex = captured_fixture()
    if change == "unknown_clock":
        gex.attrs["timestamp_basis"] = "capture reference; feature completion unknown"
    elif change == "mixed_versions":
        gex.attrs["calculation_versions"] = ["fixture_v1", "legacy"]
    elif change == "too_short":
        prices, gex = prices.iloc[:2], gex.iloc[:2]
    else:
        prices.iloc[2, 0] = float("nan")
    report, rows = cost_module().evaluate_grid(prices, gex, "yfinance", "SPY")
    assert report["status"] == "insufficient_data"
    assert rows == []


def test_empty_read_only_cli_freezes_bars_and_no_synthetic_results(tmp_path):
    db = tmp_path / "source.db"
    create_capture_db(db)
    before = db.read_bytes()
    output = tmp_path / "costs"
    command = [
        sys.executable,
        str(SCRIPT),
        "--database",
        str(db),
        "--provider",
        "yfinance",
        "--symbol",
        "SPY",
        "--start-date",
        "2025-10-06",
        "--end-date",
        "2025-10-06",
        "--output",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    report = json.loads((output / "report.json").read_text())
    manifest = json.loads((output / "manifest.json").read_text())
    assert report["status"] == "insufficient_data"
    assert manifest["bar_count"] == 0
    assert manifest["read_only"] is True
    assert len(manifest["bars_sha256"]) == 64
    assert not (output / "grid.csv").exists()
    assert db.read_bytes() == before
