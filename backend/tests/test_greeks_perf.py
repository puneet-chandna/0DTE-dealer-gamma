"""Non-gating Greeks latency distributions on fixed 1,000/10,000-contract inputs."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from app.core.greeks import BlackScholesGreeks


@pytest.mark.parametrize("contracts", [1000, 10000])
def test_calculate_all_greeks_reports_distribution(contracts):
    script = Path(__file__).resolve().parents[2] / "scripts/benchmark_pipeline.py"
    spec = importlib.util.spec_from_file_location("benchmark_pipeline", script)
    benchmark = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(benchmark)
    spot, strikes, expiry, sigma, option_type = benchmark.greeks_inputs(contracts)

    def calculate():
        return BlackScholesGreeks.calculate_all_greeks(
            spot, strikes, expiry, 0.043, sigma, option_type
        )

    result = calculate()
    assert all(len(value) == contracts and np.isfinite(value).all() for value in result)
    timing = benchmark.measure(calculate, contracts, samples=500)
    assert len(timing["samples_ms"]) == 500
    environment = benchmark.environment()
    print(
        "\n[greeks-perf] "
        + json.dumps(
            {
                "contracts": contracts,
                "retained_samples": 500,
                **{key: value for key, value in timing.items() if key != "samples_ms"},
                "environment": {
                    key: environment[key]
                    for key in ("python", "numpy", "scipy", "cpu", "thread_environment")
                },
            }
        )
    )
