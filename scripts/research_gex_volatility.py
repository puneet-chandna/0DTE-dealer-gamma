#!/usr/bin/env python3
"""Read-only, fixed-hypothesis study of normalized captured GEX and volatility."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sqlite3
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ET = ZoneInfo("America/New_York")
STUDY_VERSION = "captured_gex_forward_rv_v1"
FIELDS = (
    "session",
    "timestamp",
    "capture_id",
    "captured_at",
    "feature_available_at",
    "minutes_from_open",
    "recent_rv",
    "net_gex",
    "forward_rv",
)


def _metrics(row):
    value = row.get("metrics") or {}
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("metrics must be an object")
    return value


def build_samples(captures, calculation_version):
    """Use as-of minute observations; any absent/invalid price breaks its window."""
    sessions = defaultdict(list)
    excluded = Counter()
    versions = Counter()
    naive_count = 0
    for row in captures:
        try:
            captured = datetime.fromisoformat(row["captured_at"])
            if captured.tzinfo is None:
                captured = captured.replace(tzinfo=ET)
                naive_count += 1
            captured = captured.astimezone(ET)
        except (TypeError, ValueError, KeyError):
            excluded["invalid_timestamp"] += 1
            continue
        if captured.weekday() >= 5 or not time(9, 30) <= captured.time() <= time(16):
            excluded["outside_regular_session"] += 1
            continue
        reason = None
        available = captured
        try:
            metrics = _metrics(row)
            quality = float(metrics.get("capture_quality", 1))
            versions[str(metrics.get("calculation_version", "unknown"))] += 1
            if metrics.get("calculation_version") != calculation_version:
                reason = "calculation_version"
            elif metrics.get("quality_flags") or metrics.get("is_replay_eligible") is False:
                reason = "quality_flags"
            elif not np.isfinite(quality) or quality <= 0:
                reason = "quality_flags"
            price, gex = float(row["spot_price"]), float(row["net_gex"])
            if not np.isfinite(price) or price <= 0 or not np.isfinite(gex):
                reason = "invalid_price_or_gex"
            if reason is None:
                if not metrics.get("feature_available_at"):
                    reason = "unknown_feature_availability"
                else:
                    available = datetime.fromisoformat(metrics["feature_available_at"])
                    if available.tzinfo is None or available < captured:
                        reason = "invalid_feature_availability"
                        available = captured
                    else:
                        available = available.astimezone(ET)
        except (TypeError, ValueError, KeyError):
            reason = "invalid_price_or_metadata"
        if reason:
            excluded[reason] += 1
        # Keep invalid receipts in the timeline: an older good quote must not hide them.
        sessions[captured.date().isoformat()].append((available, row, reason, captured))

    samples, coverage = [], []
    excluded_windows = Counter()
    for session, rows in sorted(sessions.items()):
        rows.sort(key=lambda value: (value[0], value[1].get("id", 0)))
        times = [row[0] for row in rows]
        opening = datetime.combine(datetime.fromisoformat(session).date(), time(9, 30), ET)
        grid = []
        for minute in range(391):
            boundary = opening + timedelta(minutes=minute)
            index = bisect_right(times, boundary) - 1
            if index < 0 or (boundary - rows[index][3]).total_seconds() > 30 or rows[index][2]:
                grid.append(None)
            else:
                grid.append(rows[index][1])
        valid_windows = 0
        for minute in range(30, 361, 30):
            window = grid[minute - 30 : minute + 31]
            if any(row is None for row in window):
                excluded_windows["missing_minute"] += 1
                continue
            returns = np.diff(np.log([float(row["spot_price"]) for row in window]))
            origin = grid[minute]
            samples.append(
                {
                    "session": session,
                    "timestamp": (opening + timedelta(minutes=minute)).isoformat(),
                    "capture_id": origin.get("id"),
                    "captured_at": origin["captured_at"],
                    "feature_available_at": _metrics(origin)["feature_available_at"],
                    "minutes_from_open": minute,
                    "recent_rv": float(np.sqrt(np.sum(returns[:30] ** 2))),
                    "net_gex": float(origin["net_gex"]),
                    "forward_rv": float(np.sqrt(np.sum(returns[30:] ** 2))),
                }
            )
            valid_windows += 1
        observed = sum(row is not None for row in grid)
        coverage.append(
            {
                "session": session,
                "observed_grid_points": observed,
                "expected_grid_points": 391,
                "coverage_ratio": observed / 391,
                "valid_windows": valid_windows,
            }
        )
    return samples, {
        "sessions": coverage,
        "excluded_captures": dict(excluded),
        "excluded_windows": dict(excluded_windows),
        "calculation_versions": dict(versions),
        "naive_timestamps_assumed_et": naive_count,
    }


def fit_predict(train_x, train_y, test_x):
    """One fixed OLS fit, with centering/scaling derived from training only."""
    mean = np.mean(train_x, axis=0)
    scale = np.std(train_x, axis=0)
    scale = np.where(scale == 0, 1, scale)
    design = np.column_stack([np.ones(len(train_x)), (train_x - mean) / scale])
    coefficients, _, rank, _ = np.linalg.lstsq(design, train_y, rcond=None)
    test_design = np.column_stack([np.ones(len(test_x)), (test_x - mean) / scale])
    predictions = np.maximum(test_design @ coefficients, 0)
    return predictions, {
        "feature_mean": mean.tolist(),
        "feature_scale": scale.tolist(),
        "coefficients": coefficients.tolist(),
        "design_rank": int(rank),
    }


def session_bootstrap(error_difference, sessions):
    """Paired error-difference interval with whole sessions as the resampling unit."""
    unique = np.unique(sessions)
    blocks = [error_difference[sessions == session] for session in unique]
    rng = np.random.default_rng(20261014)
    means = [
        float(np.mean(np.concatenate([blocks[i] for i in draw])))
        for draw in rng.integers(0, len(blocks), size=(2000, len(blocks)))
    ]
    return np.quantile(means, [0.025, 0.975]).tolist()


def evaluate(samples, coverage, *, min_train=20, min_test=10):
    """Chronological session holdout; overrides exist for engineering fixtures only."""
    eligible = sorted(
        row["session"]
        for row in coverage
        if row["coverage_ratio"] >= 0.9 and row["valid_windows"] >= 8
    )
    split = len(eligible) * 2 // 3
    train_sessions, test_sessions = eligible[:split], eligible[split:]
    report = {
        "status": "insufficient_data",
        "eligible_sessions": len(eligible),
        "training_sessions": train_sessions,
        "heldout_sessions": test_sessions,
        "required_training_sessions": min_train,
        "required_heldout_sessions": min_test,
        "claim_scope": "observational comparison of normalized captures; not a trading or causal result",
    }
    if len(train_sessions) < min_train or len(test_sessions) < min_test:
        report["reason"] = "Not enough eligible chronological training and held-out sessions."
        return report, []
    train = [row for row in samples if row["session"] in train_sessions]
    test = [row for row in samples if row["session"] in test_sessions]

    def features(rows):
        return np.array(
            [
                [
                    row["recent_rv"],
                    row["minutes_from_open"] / 390,
                    (row["minutes_from_open"] / 390) ** 2,
                    row["net_gex"] / 1e9,
                ]
                for row in rows
            ]
        )

    train_x, test_x = features(train), features(test)
    train_y = np.array([row["forward_rv"] for row in train])
    test_y = np.array([row["forward_rv"] for row in test])
    baseline, baseline_model = fit_predict(train_x[:, :3], train_y, test_x[:, :3])
    expanded, expanded_model = fit_predict(train_x, train_y, test_x)
    baseline_error, expanded_error = test_y - baseline, test_y - expanded
    delta = baseline_error**2 - expanded_error**2
    report.update(
        {
            "status": "evaluated",
            "training_samples": len(train),
            "heldout_samples": len(test),
            "baseline": {
                "mae": float(np.mean(abs(baseline_error))),
                "mse": float(np.mean(baseline_error**2)),
                "model": baseline_model,
            },
            "baseline_plus_gex": {
                "mae": float(np.mean(abs(expanded_error))),
                "mse": float(np.mean(expanded_error**2)),
                "model": expanded_model,
            },
            "mean_squared_error_improvement": float(np.mean(delta)),
            "session_bootstrap_95pct_interval": session_bootstrap(
                delta, np.array([row["session"] for row in test])
            ),
            "bootstrap_seed": 20261014,
            "bootstrap_resamples": 2000,
            "feature_order": [
                "recent_rv",
                "minutes_from_open / 390",
                "(minutes_from_open / 390)^2",
                "net_gex / 1e9",
            ],
        }
    )
    predictions = [
        {
            **row,
            "baseline_prediction": float(base),
            "gex_prediction": float(gex),
            "squared_error_improvement": float(difference),
        }
        for row, base, gex, difference in zip(test, baseline, expanded, delta, strict=True)
    ]
    return report, predictions


def _write_csv(path, rows, fields):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run_study(database, provider, symbol, calculation_version, output):
    """Freeze selected observed rows and their provenance before evaluating."""
    database = Path(database).resolve(strict=True)
    output = Path(output)
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if not {"market_sessions", "gex_snapshots"} <= tables:
            raise ValueError("Database does not contain the captured-data schema.")
        # shortcut: selected rows stay in memory; stream exports when histories outgrow RAM.
        selected = {}
        schema = {}
        for table in ("gex_snapshots", "market_sessions", "raw_options_snapshots"):
            selected[table] = (
                [
                    dict(row)
                    for row in connection.execute(
                        f"SELECT * FROM {table} WHERE provider=? AND symbol=? ORDER BY id",
                        (provider, symbol),
                    )
                ]
                if table in tables
                else []
            )
            schema[table] = [dict(row) for row in connection.execute(f"PRAGMA table_info({table})")]
        storage_versions = (
            [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")]
            if "alembic_version" in tables
            else []
        )
    finally:
        connection.close()

    output.mkdir(parents=True, exist_ok=False)
    for table, filename in (
        ("gex_snapshots", "captures.jsonl"),
        ("market_sessions", "sessions.jsonl"),
        ("raw_options_snapshots", "raw_options.jsonl"),
    ):
        with (output / filename).open("w") as stream:
            for row in selected[table]:
                stream.write(json.dumps(row, sort_keys=True) + "\n")
    samples, audit = build_samples(selected["gex_snapshots"], calculation_version)
    _write_csv(output / "samples.csv", samples, FIELDS)
    report, predictions = evaluate(samples, audit["sessions"])
    if predictions:
        _write_csv(
            output / "predictions.csv",
            predictions,
            (*FIELDS, "baseline_prediction", "gex_prediction", "squared_error_improvement"),
        )
    hashes = {
        name: hashlib.sha256((output / name).read_bytes()).hexdigest()
        for name in ("captures.jsonl", "sessions.jsonl", "raw_options.jsonl", "samples.csv")
    }
    manifest = {
        "study_version": STUDY_VERSION,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "created_at_utc": datetime.now(ZoneInfo("UTC")).isoformat(),
        "source_database": str(database),
        "read_only": True,
        "provider": provider,
        "requested_symbol": symbol,
        "instrument": "SPY × 10 proxy of requested SPX"
        if provider == "yfinance" and symbol == "SPX"
        else symbol,
        "calculation_version": calculation_version,
        "storage_versions": storage_versions,
        "source_quote_freshness": "unknown unless recorded in capture metadata",
        "availability_basis": "explicit metrics.feature_available_at; unknown completion clocks excluded",
        "naive_timestamp_convention": "America/New_York, matching persistence normalization",
        "capture_rows": len(selected["gex_snapshots"]),
        "raw_options_rows": len(selected["raw_options_snapshots"]),
        "source_schema": schema,
        "file_sha256": hashes,
        "dataset_sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "platform": platform.platform(),
        },
        "policy": {
            "session_et": "weekdays 09:30-16:00; full sessions only",
            "max_capture_age_seconds": 30,
            "minute_grid_points": 391,
            "horizon_minutes": 30,
            "stride_minutes": 30,
            "minimum_session_coverage": 0.9,
            "minimum_windows_per_session": 8,
            "training_fraction": "first 2/3 eligible sessions chronologically",
            "minimum_training_sessions": 20,
            "minimum_heldout_sessions": 10,
            "prediction_floor": 0,
            "bootstrap_unit": "whole held-out session",
        },
        **audit,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--provider", required=True, choices=("yfinance", "tradier"))
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--calculation-version", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not args.symbol.strip() or not args.calculation_version.strip():
        parser.error("symbol and calculation version must not be empty")
    try:
        report = run_study(
            args.database,
            args.provider,
            args.symbol.strip().upper(),
            args.calculation_version.strip(),
            args.output,
        )
    except (OSError, sqlite3.Error, ValueError) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "status": report["status"],
                "eligible_sessions": report["eligible_sessions"],
                "output": str(args.output.resolve()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
