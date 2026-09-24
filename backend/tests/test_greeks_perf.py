"""0DTE GEX Backend - Greeks Throughput Benchmark (NON-GATING).

Times ``BlackScholesGreeks.calculate_all_greeks`` on n=1000 0DTE-like
contracts and prints p50/p99. The assertion bound is deliberately generous
(<200ms) so CI never flakes on shared runners; this test records a
measurement, it does not gate on hardware speed.

Live market numbers (provider fetch + GEX calc on real chains) are recorded
in ``docs/BENCHMARKS.md`` — see that file for the Tradier/yFinance runs.
"""

import time

import numpy as np

from app.core.greeks import BlackScholesGreeks


def _build_0dte_chain(n: int = 1000) -> tuple:
    """Build a deterministic 0DTE-like chain: tight strikes, hours to expiry."""
    spot = 6600.0
    s = np.full(n, spot, dtype=np.float64)
    k = np.linspace(spot * 0.97, spot * 1.03, n, dtype=np.float64)
    # ~4 trading hours to expiry, floored to avoid div-by-zero
    t = np.full(n, 4.0 / (365.25 * 24.0), dtype=np.float64) + 1e-9
    sigma = np.full(n, 0.18, dtype=np.float64)
    option_type = np.array(["call"] * (n // 2) + ["put"] * (n - n // 2))
    return s, k, t, sigma, option_type


class TestGreeksPerf:
    """Non-gating throughput probe for the vectorized Greeks path."""

    def test_calculate_all_greeks_1000_contracts_reports_timing(self, capsys=None):
        s, k, t, sigma, option_type = _build_0dte_chain(1000)

        # Warmup (imports, first-call overhead) — not timed.
        BlackScholesGreeks.calculate_all_greeks(s, k, t, 0.043, sigma, option_type)

        runs_ms: list[float] = []
        for _ in range(7):
            start = time.perf_counter()
            result = BlackScholesGreeks.calculate_all_greeks(
                s, k, t, 0.043, sigma, option_type
            )
            runs_ms.append((time.perf_counter() - start) * 1000.0)

        # Sanity: outputs are finite and correctly shaped.
        assert len(result.gamma) == 1000
        assert bool(np.all(np.isfinite(result.gamma)))

        timed = sorted(runs_ms[2:])  # drop first two timed runs (cache warmup)
        p50 = float(np.median(timed))
        p99 = float(timed[-1])  # ~max of 5 samples; labelled honestly
        print(
            f"\n[greeks-perf] n=1000 0DTE-like contracts: "
            f"p50={p50:.2f}ms p99~max={p99:.2f}ms "
            f"(runs={[f'{x:.2f}' for x in timed]})"
        )

        # Generous non-gating bound: ~300x headroom over typical ~0.6ms.
        assert p50 < 200.0, f"Greeks p50 unexpectedly slow: {p50:.1f}ms"
