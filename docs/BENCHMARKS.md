# Benchmarks

Measured numbers, not marketing claims. After installing backend dependencies,
re-run the synthetic probe with output visible:

```bash
cd backend
.venv/bin/python -m pytest -s tests/test_greeks_perf.py
```

The live procedure is below.

## Machine

- CPU: 12th Gen Intel Core i5-1235U (x86_64), 12 threads
- Python 3.13.15, NumPy 2.2.6, SciPy 1.15.1
- Run host: local dev machine, 2026-09-24

## Synthetic Greeks throughput (CI probe)

`BlackScholesGreeks.calculate_all_greeks`, n=1000 0DTE-like contracts
(tight ±3% strikes, ~4h to expiry, IV 18%), median of 5 timed runs after warmup:

| Metric | Measured |
| ------ | -------- |
| p50    | ~0.5–0.6 ms |
| max of 5 | ~0.6–0.9 ms |

`test_greeks_perf.py` checks output shape and finiteness. Timings are reported
without a hardware-speed assertion; the maximum of five samples is not a p99.

## Live market run — 2026-09-24 ~12:15 PM ET (market OPEN)

Procedure: `YFinanceClient.get_options_chain_for_gex("SPX")` then
`GEXCalculator.calculate_gex_from_chain` × 5 (GEX calc = gamma + charm/vanna +
aggregation; p50 over 5 runs).

| Provider | Spot | Contracts (gex-ready / strikes) | Fetch latency | GEX calc p50 | GEX calc max |
| -------- | ---- | ------------------------------- | ------------- | ------------ | ------------ |
| yfinance (SPY×10 proxy) | 7641.30 | 247 / 124 | ~1.4–1.7 s | 3.69 ms | 3.97 ms |
| tradier | — | — | FAILED (HTTP 401 on prod **and** sandbox) | — | — |

Live snapshot values (yfinance run): net GEX ≈ −3.555e10, zero-gamma ≈ 6150.

### Provider-delay disclaimer

- **Yahoo Finance through yfinance is an unofficial feed with no freshness
  guarantee here.** The app does not verify a fixed 15-minute delay. More
  frequent polling does not guarantee new quotes or open interest.
- **Tradier** could not be measured in this run: the
  configured `TRADIER_API_KEY` returned `401 Unauthorized` on both
  `https://api.tradier.com/v1` and `https://sandbox.tradier.com/v1`.
  Re-run once a valid key is configured. Tradier distinguishes brokerage
  real-time access from delayed sandbox quotes; sandbox Greeks are unavailable.
  See [Tradier's market-data guide](https://docs.tradier.com/docs/market-data).
- The WebSocket loop waits up to 5 s after each completed update and continues
  outside market hours; fetch time can lengthen the interval. REST GEX polling
  is configurable (30 s by default) and can be disabled. Background refresh
  tasks separately skip work when the app's market-hours check is closed.
  None of these intervals guarantees fresh upstream quotes.

## SPY-proxy disclosure (yfinance)

When `provider=yfinance`, `YFinanceClient` fetches **SPY** options and scales
by `SPY_TO_SPX_RATIO = 10.0`: spot price, strikes, bid, and ask are all
SPY×10 approximations of SPX — not real SPX quotes. Greeks (`has_greeks`) are
**false** for yfinance; all Greeks are computed locally by the vectorized
Black-Scholes engine. Tradier can fetch SPX/SPXW chains directly and use
provider-supplied Greeks when available.
