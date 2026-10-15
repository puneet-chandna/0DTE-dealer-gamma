#!/usr/bin/env python3
"""Fixed 18-cell cost/latency diagnostic on read-only captured bars; no edge claim."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import platform
import sqlite3
import sys
from datetime import date, datetime, time
from itertools import product
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.api.routes.analytics import _backtest_prices  # noqa: E402
from app.core.provenance import data_provenance  # noqa: E402
from app.core.vectorbt_backtester import VectorBTBacktester  # noqa: E402
from app.services.historical_data import HistoricalDataService  # noqa: E402

ET = ZoneInfo("America/New_York")


def evaluate_grid(prices, gex, provider, symbol):
    """Use one fixed dataset and policy for all cells; never select a better segment."""
    report = {
        "status": "insufficient_data",
        "used_bars": 0,
        "claim_scope": "cost and latency diagnostic; no strategy edge or executable-fill claim",
    }

    def insufficient(reason):
        report["reason"] = reason
        return report, []

    if prices.empty or gex.empty:
        return insufficient("No quality-eligible captured bars in the requested range.")
    if not isinstance(prices.index, pd.DatetimeIndex) or prices.index.tz is None:
        return insufficient("Captured bars require an aware datetime index.")
    if (
        not prices.index.equals(gex.index)
        or not prices.index.is_unique
        or not prices.index.is_monotonic_increasing
    ):
        return insufficient("Price/GEX bars must have identical unique chronological timestamps.")
    if not str(gex.attrs.get("timestamp_basis", "")).startswith("feature completion"):
        return insufficient("Unknown feature-completion clocks cannot supply as-of signals.")
    versions = gex.attrs.get("calculation_versions", [])
    if len(versions) != 1 or versions[0] in {"unknown_legacy", "unknown", None}:
        return insufficient(
            "A single known calculation version is required; mixed/legacy data excluded."
        )

    local = prices.index.tz_convert(ET)
    complete = local <= pd.Timestamp(datetime.now(ET))
    report["excluded_incomplete_bars"] = int(np.sum(~complete))
    prices, gex = prices.loc[complete], gex.loc[complete]
    local = local[complete]
    if len(prices) < 3:
        return insufficient(
            "At least three complete captured minute bars are required for the two-bar delay."
        )
    if any(value.weekday() >= 5 or not time(9, 31) <= value.time() <= time(16) for value in local):
        return insufficient("Only regular-session ET minute bars are supported.")
    same_session = np.array(
        [left.date() == right.date() for left, right in zip(local[:-1], local[1:], strict=True)]
    )
    if np.any((np.diff(local.asi8) != 60_000_000_000) & same_session):
        return insufficient(
            "Irregular within-session gaps prevent interpreting delays as one-minute bars."
        )
    try:
        close = prices["close"].to_numpy(dtype=float)
        signals = gex["net_gex"].to_numpy(dtype=float)
    except (KeyError, TypeError, ValueError):
        return insufficient("Numeric close and net_gex columns are required.")
    if not np.isfinite(close).all() or not np.isfinite(signals).all() or np.any(close <= 0):
        return insufficient("Nonfinite or nonpositive price/GEX observations cannot be replaced.")

    provenance = data_provenance(gex, provider=provider, symbol=symbol)
    if provenance.actual_instrument.upper() in {"SPX", "^GSPC"} and not provenance.is_proxy:
        return insufficient("SPX is not a tradable stock; use captured SPY or another stock/ETF.")
    prices = _backtest_prices(prices, provider=provider, symbol=symbol)
    rows = []
    for fees_bps, slippage_bps, delay in product((0, 5, 10), (0, 5, 10), (1, 2)):
        result = VectorBTBacktester.run_gex_signal_backtest(
            price_data=prices,
            gex_data=gex,
            entry_threshold=-1e9,
            exit_threshold=0,
            initial_cash=100_000,
            position_size=1,
            fees=fees_bps / 10_000,
            slippage=slippage_bps / 10_000,
            execution_delay_bars=delay,
            stop_loss_pct=None,
            take_profit_pct=None,
        )
        rows.append(
            {
                "fees_bps": fees_bps,
                "slippage_bps": slippage_bps,
                "execution_delay_bars": delay,
                "marked_total_return": result.total_return,
                "marked_equity": result.equity_curve[-1],
                "max_drawdown": result.max_drawdown,
                "total_trades": result.total_trades,
                "closed_trades": result.closed_trades,
                "open_trades": result.open_trades,
                "avg_closed_trade_return": result.avg_trade_return
                if result.closed_trades
                else None,
            }
        )
    report.update(
        {
            "status": "evaluated",
            "used_bars": len(prices),
            "cells": len(rows),
            "provenance": provenance.model_dump(mode="json"),
            "limitations": [
                "Short or partial captured coverage is not evidence of an edge.",
                "Marked return includes unrealized positions; no forced exit or imagined exit fee.",
                "Close-sampled fills, fractional positions, and costs are assumptions; no verified executable quotes.",
            ],
        }
    )
    return report, rows


async def run_diagnostic(database, provider, symbol, start_date, end_date, output):
    database = Path(database).resolve(strict=True)
    uri = database.as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if not {"market_sessions", "gex_snapshots"} <= tables:
            raise ValueError("Database is missing the captured-data schema.")
    finally:
        connection.close()
    engine = create_async_engine("sqlite+aiosqlite:///" + database.as_uri() + "?mode=ro&uri=true")
    try:
        service = HistoricalDataService(
            session_factory=async_sessionmaker(engine, expire_on_commit=False)
        )
        prices, gex = await service.get_time_series_frames(
            provider=provider,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            interval="1m",
            prefer_replay=True,
            allow_latest_replay_fallback=False,
        )
    finally:
        await engine.dispose()

    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    bars = prices.add_prefix("price_").join(gex.add_prefix("gex_"), how="outer")
    bars.to_csv(output / "bars.csv", index_label="timestamp")
    provenance = data_provenance(gex, provider=provider, symbol=symbol).model_dump(mode="json")
    report, rows = evaluate_grid(prices, gex, provider, symbol)
    if rows:
        pd.DataFrame(rows).to_csv(output / "grid.csv", index=False)
    manifest = {
        "diagnostic_version": "fixed_cost_latency_v1",
        "read_only": True,
        "source_database": str(database),
        "provider": provider,
        "requested_symbol": symbol,
        "requested_start": start_date.isoformat(),
        "requested_end": end_date.isoformat(),
        "bar_count": len(bars),
        "bars_sha256": hashlib.sha256((output / "bars.csv").read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "provenance": provenance,
        "created_at_utc": datetime.now(ZoneInfo("UTC")).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "policy": {
            "fees_bps": [0, 5, 10],
            "slippage_bps": [0, 5, 10],
            "execution_delay_bars": [1, 2],
            "entry_threshold": -1e9,
            "exit_threshold": 0,
            "initial_cash": 100_000,
            "position_size": 1,
            "stops": None,
            "partial_bar_policy": "exclude bars whose end label is in the future",
            "gap_policy": "reject irregular sessions; do not select a favorable segment",
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--provider", choices=("yfinance", "tradier"), required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.start_date > args.end_date or args.end_date > datetime.now(ET).date():
        parser.error("use an ordered date range ending no later than today in New York")
    if not args.symbol.strip():
        parser.error("symbol cannot be empty")
    try:
        report = asyncio.run(
            run_diagnostic(
                args.database,
                args.provider,
                args.symbol.strip().upper(),
                args.start_date,
                args.end_date,
                args.output,
            )
        )
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "status": report["status"],
                "used_bars": report["used_bars"],
                "reason": report.get("reason"),
                "output": str(args.output.resolve()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
