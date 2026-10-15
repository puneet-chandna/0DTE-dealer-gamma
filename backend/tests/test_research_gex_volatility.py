"""Engineering fixtures for the offline study; these are not market evidence."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/research_gex_volatility.py"
ET = ZoneInfo("America/New_York")


def study_module():
    spec = importlib.util.spec_from_file_location("research_gex_volatility", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_capture_db(path):
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE alembic_version (version_num TEXT);
            INSERT INTO alembic_version VALUES ('fixture_v1');
            CREATE TABLE market_sessions (
                id INTEGER PRIMARY KEY, provider TEXT, symbol TEXT,
                trading_date TEXT, status TEXT, completeness_ratio REAL,
                snapshot_count INTEGER, raw_snapshot_count INTEGER,
                first_captured_at TEXT, last_captured_at TEXT, capture_metadata TEXT
            );
            CREATE TABLE gex_snapshots (
                id INTEGER PRIMARY KEY, session_id INTEGER, provider TEXT, symbol TEXT,
                captured_at TEXT, spot_price REAL, total_call_gex REAL,
                total_put_gex REAL, net_gex REAL, zero_gamma_level REAL,
                dominant_strike REAL, metrics TEXT
            );
            CREATE TABLE raw_options_snapshots (
                id INTEGER PRIMARY KEY, session_id INTEGER, provider TEXT, symbol TEXT,
                captured_at TEXT, spot_price REAL, expiration_date TEXT,
                contract_count INTEGER, payload TEXT, source_metadata TEXT
            );
        """)


def minute_captures(minutes=391):
    start = datetime(2026, 10, 5, 9, 30, tzinfo=ET)
    return [
        {
            "id": minute + 1,
            "captured_at": (start + timedelta(minutes=minute)).isoformat(),
            "spot_price": float(100 * np.exp(0.001 * minute)),
            "net_gex": float(minute),
            "metrics": json.dumps(
                {
                    "calculation_version": "fixture_v1",
                    "capture_quality": 1,
                    "feature_available_at": (start + timedelta(minutes=minute)).isoformat(),
                }
            ),
        }
        for minute in range(minutes)
    ]


def test_empty_capture_cli_freezes_insufficient_audit_without_mutating_database(tmp_path):
    # Dropping read-only access or substituting synthetic data must fail this check.
    db = tmp_path / "captures.db"
    create_capture_db(db)
    before = db.read_bytes()
    output = tmp_path / "audit"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--database",
            str(db),
            "--provider",
            "yfinance",
            "--symbol",
            "SPX",
            "--calculation-version",
            "fixture_v1",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((output / "report.json").read_text())
    manifest = json.loads((output / "manifest.json").read_text())
    assert report["status"] == "insufficient_data"
    assert report["eligible_sessions"] == 0
    assert "SPY" in manifest["instrument"]
    assert manifest["source_quote_freshness"] == "unknown unless recorded in capture metadata"
    assert manifest["capture_rows"] == 0
    assert manifest["file_sha256"]["captures.jsonl"] == hashlib.sha256(b"").hexdigest()
    assert not (output / "predictions.csv").exists()
    assert db.read_bytes() == before
    repeat = subprocess.run(result.args, capture_output=True, text=True, check=False)
    assert repeat.returncode != 0


def test_minute_grid_target_uses_only_receipts_available_at_t():
    # Using the next snapshot or overnight returns would change these hand-derived values.
    rows = minute_captures()
    rows.append(
        {
            **rows[30],
            "id": 1000,
            "captured_at": "2026-10-05T10:00:20-04:00",
            "net_gex": 9999,
            "metrics": json.dumps(
                {
                    "calculation_version": "fixture_v1",
                    "capture_quality": 1,
                    "feature_available_at": "2026-10-05T10:00:20-04:00",
                }
            ),
        }
    )
    samples, audit = study_module().build_samples(rows, "fixture_v1")
    assert len(samples) == 12
    assert samples[0]["timestamp"] == "2026-10-05T10:00:00-04:00"
    assert samples[0]["net_gex"] == 30
    assert samples[0]["recent_rv"] == pytest.approx(np.sqrt(30) * 0.001)
    assert samples[0]["forward_rv"] == pytest.approx(np.sqrt(30) * 0.001)
    assert audit["sessions"][0]["observed_grid_points"] == 391
    assert samples[-1]["timestamp"] == "2026-10-05T15:30:00-04:00"


def test_missing_quote_invalidates_windows_instead_of_filling_returns():
    rows = minute_captures()
    del rows[45]
    samples, audit = study_module().build_samples(rows, "fixture_v1")
    assert len(samples) == 10
    assert samples[0]["timestamp"] == "2026-10-05T11:00:00-04:00"
    assert audit["excluded_windows"]["missing_minute"] == 2


def test_legacy_quality_flags_and_weekend_captures_are_excluded():
    rows = minute_captures(61)
    rows[20]["metrics"] = json.dumps({"calculation_version": "legacy"})
    rows[40]["metrics"] = json.dumps(
        {"calculation_version": "fixture_v1", "quality_flags": ["provider_gex_outlier"]}
    )
    rows.append({**rows[0], "captured_at": "2026-10-10T10:00:00-04:00"})
    samples, audit = study_module().build_samples(rows, "fixture_v1")
    assert samples == []
    assert audit["excluded_captures"]["calculation_version"] == 1
    assert audit["excluded_captures"]["quality_flags"] == 1
    assert audit["excluded_captures"]["outside_regular_session"] == 1


def test_invalid_latest_capture_does_not_fall_back_to_an_older_good_quote():
    rows = minute_captures(61)
    rows.append({**rows[30], "id": 1001, "spot_price": float("nan")})
    samples, audit = study_module().build_samples(rows, "fixture_v1")
    assert samples == []
    assert audit["excluded_captures"]["invalid_price_or_gex"] == 1


@pytest.mark.parametrize("quality", [float("nan"), float("inf"), 0])
def test_nonfinite_or_zero_capture_quality_breaks_the_price_window(quality):
    rows = minute_captures(61)
    rows[30]["metrics"] = json.dumps(
        {"calculation_version": "fixture_v1", "capture_quality": quality}
    )
    samples, audit = study_module().build_samples(rows, "fixture_v1")
    assert samples == []
    assert audit["excluded_captures"]["quality_flags"] == 1


def test_naive_sqlite_capture_times_follow_explicit_et_storage_convention():
    rows = minute_captures()
    for row in rows:
        row["captured_at"] = row["captured_at"][:19]
    samples, audit = study_module().build_samples(rows, "fixture_v1")
    assert len(samples) == 12
    assert samples[0]["timestamp"] == "2026-10-05T10:00:00-04:00"
    assert audit["naive_timestamps_assumed_et"] == 391


def test_delayed_calculation_cannot_enter_an_earlier_minute():
    rows = minute_captures()
    for row in rows:
        metrics = json.loads(row["metrics"])
        metrics["feature_available_at"] = row["captured_at"]
        row["metrics"] = json.dumps(metrics)
    metrics = json.loads(rows[30]["metrics"])
    metrics["feature_available_at"] = "2026-10-05T10:00:20-04:00"
    rows[30]["metrics"] = json.dumps(metrics)
    samples, _ = study_module().build_samples(rows, "fixture_v1")
    assert len(samples) == 10
    assert samples[0]["timestamp"] == "2026-10-05T11:00:00-04:00"


def test_missing_feature_completion_clock_is_not_predictive_evidence():
    rows = minute_captures(61)
    for row in rows:
        metrics = json.loads(row["metrics"])
        metrics.pop("feature_available_at", None)
        row["metrics"] = json.dumps(metrics)
    samples, audit = study_module().build_samples(rows, "fixture_v1")
    assert samples == []
    assert audit["excluded_captures"]["unknown_feature_availability"] == 61


def test_scaling_and_fitting_see_training_data_only():
    # A scaler fitted on extreme held-out GEX would corrupt the stored training mean.
    train_x = np.array([[1, 0, 10], [2, 0, 20], [3, 0, 10], [4, 0, 20]], dtype=float)
    train_y = np.array([1, 2, 3, 4], dtype=float)
    test_x = np.array([[10, 0, 1e12]], dtype=float)
    predictions, model = study_module().fit_predict(train_x, train_y, test_x)
    assert model["feature_mean"] == [2.5, 0.0, 15.0]
    assert model["feature_scale"][1] == 1.0
    assert predictions[0] == pytest.approx(10.0, abs=0.001)


def test_bootstrap_resamples_whole_sessions_reproducibly():
    module = study_module()
    sessions = np.repeat(["a", "b"], 20)
    delta = np.repeat([1.0, 3.0], 20)
    interval = module.session_bootstrap(delta, sessions)
    assert interval == module.session_bootstrap(delta, sessions)
    assert interval == pytest.approx([1.0, 3.0])


def test_session_split_requires_coverage_and_enough_sessions():
    module = study_module()
    samples, audit = module.build_samples(minute_captures(), "fixture_v1")
    report, predictions = module.evaluate(samples, audit["sessions"])
    assert report["status"] == "insufficient_data"
    assert report["eligible_sessions"] == 1
    assert predictions == []
    # Explicit fixture override exercises mechanics, never the real CLI's coverage gate.
    fixture_rows = []
    coverage = []
    for day in range(3):
        session = f"fixture_session_{day}"
        coverage.append({"session": session, "coverage_ratio": 1.0, "valid_windows": 12})
        for i, sample in enumerate(samples):
            fixture_rows.append(
                {
                    **sample,
                    "session": session,
                    "recent_rv": (i + 1) / 1000,
                    "forward_rv": (i + 1) / 1000,
                    "net_gex": float((i + day) % 3),
                }
            )
    report, predictions = module.evaluate(fixture_rows, coverage, min_train=2, min_test=1)
    assert report["status"] == "evaluated"
    assert report["training_sessions"] == ["fixture_session_0", "fixture_session_1"]
    assert report["heldout_sessions"] == ["fixture_session_2"]
    assert len(predictions) == 12
    assert {row["session"] for row in predictions} == {"fixture_session_2"}
    coverage[-1]["coverage_ratio"] = 0.5
    report, predictions = module.evaluate(fixture_rows, coverage, min_train=2, min_test=1)
    assert report["status"] == "insufficient_data"
    assert predictions == []
