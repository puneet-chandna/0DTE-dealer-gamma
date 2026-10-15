#!/usr/bin/env python3
"""Non-gating local calculation benchmark; no provider or application startup."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import sqlite3
import sys
import tempfile
import time
import tracemalloc
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import scipy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core.gex_calculator import GEXCalculator  # noqa: E402
from app.core.greeks import BlackScholesGreeks  # noqa: E402

REFERENCE_TIME = datetime(2026, 10, 14, 12, tzinfo=ZoneInfo("America/New_York"))


def greeks_inputs(n):
    """Identical paired call/put contracts on a fixed 0DTE-like strike grid."""
    strikes = np.resize(np.repeat(np.linspace(6402, 6798, min(100, n // 2)), 2), n)
    return (
        np.full(n, 6600.0),
        strikes,
        np.full(n, 4 / (365.25 * 24)),
        np.full(n, 0.18),
        np.tile(["call", "put"], n // 2),
    )


def measure(operation, contracts, samples=200):
    """Retain timings; observe traced allocation in a separate untimed call."""
    for _ in range(3):
        operation()
    timings = []
    for _ in range(samples):
        start = time.perf_counter_ns()
        operation()
        timings.append((time.perf_counter_ns() - start) / 1e6)
    tracemalloc.start()
    try:
        operation()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    p50, p95, p99 = np.quantile(timings, [0.5, 0.95, 0.99])
    return {
        "p50_ms": float(p50),
        "p95_ms": float(p95),
        "p99_ms": float(p99),
        "contracts_per_second": float(contracts / (p50 / 1000)),
        "peak_traced_bytes": peak,
        "samples_ms": timings,
    }


def environment():
    cpu = platform.processor()
    if Path("/proc/cpuinfo").exists():
        cpu = next(
            (
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            cpu,
        )
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "pandas": pd.__version__,
        "platform": platform.platform(),
        "cpu": cpu,
        "logical_cpus": os.cpu_count(),
        "thread_environment": {
            name: os.environ.get(name)
            for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
        },
        "numpy_build": np.show_config(mode="dicts"),
        "external_fetch": "unmeasured; no network calls",
        "api_transport": "unmeasured; no HTTP server or ASGI routing",
        "load_control": "uncontrolled developer host; no CPU affinity or governor changes",
        "memory_scope": "separate tracemalloc peak per stage; process peak RSS includes native allocations",
    }


def benchmark_workload(n, samples=200):
    if n < 2 or n % 2 or samples < 1:
        raise ValueError("contracts must be a positive even count and samples must be positive")
    spot, strikes, expiry, sigma, types = greeks_inputs(n)
    calculator = GEXCalculator(risk_free_rate=0.043)
    chain = pd.DataFrame(
        {
            "strike": strikes,
            "type": types,
            "open_interest": 1000 + np.arange(n) % 1000,
            "implied_vol": sigma,
            "expiration": "2026-10-14",
        }
    )
    greeks = BlackScholesGreeks.calculate_all_greeks(spot, strikes, expiry, 0.043, sigma, types)
    assert all(len(value) == n and np.isfinite(value).all() for value in greeks)
    snapshot = calculator.calculate_gex_from_chain(chain, 6600.0, REFERENCE_TIME)
    assert np.isfinite(snapshot.net_gex)
    assert len(snapshot.gex_by_strike) == min(100, n // 2)
    payload = snapshot.model_dump_json()
    aggregation_values = np.where(types == "call", 1.0, -0.75) * np.arange(1, n + 1)
    stages = {
        "greeks": measure(
            lambda: BlackScholesGreeks.calculate_all_greeks(
                spot, strikes, expiry, 0.043, sigma, types
            ),
            n,
            samples,
        ),
        "gex_calculation": measure(
            lambda: calculator.calculate_gex_from_chain(chain, 6600.0, REFERENCE_TIME), n, samples
        ),
        "aggregation": measure(
            lambda: calculator._aggregate_by_strike(strikes, aggregation_values), n, samples
        ),
        "serialization": measure(snapshot.model_dump_json, n, samples),
    }
    with tempfile.TemporaryDirectory(prefix="gex-benchmark-") as directory:
        with sqlite3.connect(Path(directory) / "snapshots.db") as connection:
            connection.execute(
                "CREATE TABLE snapshots (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
            )

            def persist():
                connection.execute("INSERT INTO snapshots(payload) VALUES (?)", (payload,))
                connection.commit()

            stages["sqlite_json_commit"] = measure(persist, n, samples)
            with sqlite3.connect(Path(directory) / "snapshots.db") as reader:
                persisted = reader.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
                assert persisted == samples + 4
                assert (
                    reader.execute("SELECT payload FROM snapshots LIMIT 1").fetchone()[0] == payload
                )
    return {
        "contracts": n,
        "strikes": min(100, n // 2),
        "calculation_version": snapshot.metrics.get("calculation_version", "unknown"),
        "serialized_bytes": len(payload.encode()),
        "persisted_rows": persisted,
        "stages": stages,
    }


def realistic_spx_chain():
    """Fixed SPX-like skew/term structure with a distinct IV for every contract."""
    index = np.arange(2010)
    strikes = np.tile(np.repeat(np.arange(6100.0, 7105.0, 5.0), 2), 5)
    expiry_days = np.repeat([0, 1, 7, 30, 58], 402)
    is_call = index % 2 == 0
    return pd.DataFrame(
        {
            "strike": strikes,
            "type": np.where(is_call, "call", "put"),
            "open_interest": np.rint(
                (100 + 4000 * np.exp(-0.5 * ((strikes - 6600) / 200) ** 2))
                * np.where(is_call, 1 + (strikes - 6600) / 1000, 1 - (strikes - 6600) / 1000)
            ).astype(np.int64),
            "implied_vol": (
                0.18 - 0.5 * (strikes / 6600 - 1) + expiry_days * 0.0002 + index * 1e-8
            ),
            "expiration": [
                REFERENCE_TIME.replace(hour=16) + timedelta(days=int(days)) for days in expiry_days
            ],
        }
    )


def benchmark_realistic_spx_workload(samples=200):
    """Exercise full calculation without collapsing contracts into shared-IV kernels."""
    chain = realistic_spx_chain()
    calculator = GEXCalculator(risk_free_rate=0.043)
    snapshot = calculator.calculate_gex_from_chain(chain, 6600.0, REFERENCE_TIME)
    assert np.isfinite(snapshot.net_gex) and np.isfinite(snapshot.zero_gamma_level)
    assert snapshot.metrics["zero_gamma_crossing_found"]
    return {
        "fixture": "synthetic_spx_mixed_expiry_distinct_iv",
        "contracts": len(chain),
        "strikes": int(chain["strike"].nunique()),
        "expiries": int(chain["expiration"].nunique()),
        "pricing_kernels": len(chain.drop_duplicates(["strike", "implied_vol", "expiration"])),
        "zero_gamma_crossing_found": snapshot.metrics["zero_gamma_crossing_found"],
        "zero_gamma_level": snapshot.zero_gamma_level,
        "stages": {
            "gex_calculation": measure(
                lambda: calculator.calculate_gex_from_chain(chain, 6600.0, REFERENCE_TIME),
                len(chain),
                samples,
            )
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--samples", type=int, default=200, help="retained samples per stage/workload, minimum 100"
    )
    parser.add_argument("--output", type=Path, help="optional new JSON file; never overwrites")
    args = parser.parse_args()
    if args.samples < 100:
        parser.error("use at least 100 retained samples for reported percentiles")
    if args.output and args.output.exists():
        parser.error(f"output already exists: {args.output}")
    report = {
        "benchmark_version": "local_pipeline_v2",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "calculator_sha256": hashlib.sha256(
            (
                Path(__file__).resolve().parents[1] / "backend/app/core/gex_calculator.py"
            ).read_bytes()
        ).hexdigest(),
        "fixture": "synthetic; engineering only",
        "reference_time": REFERENCE_TIME.isoformat(),
        "warmups": 3,
        "retained_samples": args.samples,
        "environment": environment(),
        "workloads": [benchmark_workload(n, args.samples) for n in (1000, 10000)],
        "realistic_spx_workload": benchmark_realistic_spx_workload(args.samples),
    }
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report["process_peak_rss_bytes"] = int(rss if sys.platform == "darwin" else rss * 1024)
    serialized = json.dumps(report, indent=2, default=str) + "\n"
    if args.output:
        with args.output.open("x") as stream:
            stream.write(serialized)
        print(str(args.output.resolve()))
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()
