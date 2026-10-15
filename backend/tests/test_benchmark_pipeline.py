"""Checks local benchmark execution, never a hardware speed threshold."""

import importlib.util
from pathlib import Path

import numpy as np

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/benchmark_pipeline.py"


def benchmark_module():
    spec = importlib.util.spec_from_file_location("benchmark_pipeline", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixed_chain_produces_finite_results_at_each_local_stage():
    # Missing persistence/serialization or nonfinite fixture arithmetic must fail here.
    result = benchmark_module().benchmark_workload(32, samples=3)
    assert result["contracts"] == 32
    assert result["strikes"] == 16
    assert set(result["stages"]) == {
        "greeks",
        "gex_calculation",
        "aggregation",
        "serialization",
        "sqlite_json_commit",
    }
    for stage in result["stages"].values():
        assert len(stage["samples_ms"]) == 3
        assert np.isfinite(stage["p50_ms"])
        assert 0 <= stage["p50_ms"] <= stage["p95_ms"] <= stage["p99_ms"]
        assert stage["contracts_per_second"] > 0
        assert stage["peak_traced_bytes"] >= 0
    assert result["serialized_bytes"] > 100
    assert result["persisted_rows"] >= 3


def test_workload_is_deterministic_and_benchmark_never_fetches_market_data():
    # A random chain would stop run-to-run comparisons from using the same workload.
    module = benchmark_module()
    first = module.greeks_inputs(32)
    second = module.greeks_inputs(32)
    for left, right in zip(first, second, strict=True):
        np.testing.assert_array_equal(left, right)
    assert first[0][0] == 6600
    assert set(first[-1]) == {"call", "put"}
    assert module.environment()["external_fetch"] == "unmeasured; no network calls"


def test_workload_scaling_keeps_the_same_strike_universe():
    # Growing unique strikes as well as contracts confounds the grouping comparison.
    module = benchmark_module()
    small = module.greeks_inputs(1000)
    large = module.greeks_inputs(10000)
    assert len(small[1]) == 1000
    assert len(large[1]) == 10000
    np.testing.assert_array_equal(np.unique(small[1]), np.unique(large[1]))
    assert len(np.unique(large[1])) == 100


def test_realistic_spx_chain_exercises_distinct_contract_kernels():
    # A shared IV or single expiry hides the zero-gamma scan's real scaling cost.
    module = benchmark_module()
    first = module.realistic_spx_chain()
    second = module.realistic_spx_chain()
    assert first.equals(second)
    assert len(first) == 2010
    assert first["strike"].nunique() == 201
    assert first["expiration"].nunique() == 5
    assert first["implied_vol"].nunique() == len(first)
    assert set(first["type"]) == {"call", "put"}
    assert (first["open_interest"] > 0).all()
    assert np.issubdtype(first["open_interest"].dtype, np.integer)
    assert (first["expiration"].dt.weekday < 5).all()
    result = module.benchmark_realistic_spx_workload(samples=3)
    assert result["contracts"] == len(first)
    assert result["pricing_kernels"] == len(first)
    assert result["expiries"] == 5
    assert result["zero_gamma_crossing_found"] is True
    assert len(result["stages"]["gex_calculation"]["samples_ms"]) == 3
