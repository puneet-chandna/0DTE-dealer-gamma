# Benchmarks

Measured numbers, not marketing claims. Re-run with
`backend/tests/test_greeks_perf.py` (synthetic) or the live procedure below.

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
| max of 5 (`p99~max`) | ~0.6–0.9 ms |

CI bound in `test_greeks_perf.py` is a generous `<200ms` — the test records a
measurement and never gates on hardware speed.

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

- **Yahoo Finance is delayed (~15 min) and unofficial** — usable for structure /
  regime context, not for tick-accurate execution. OI refreshes on exchange
  cadence (typically once per day / per session), not on every poll.
- **Tradier (live, ORATS Greeks)** could not be measured in this run: the
  configured `TRADIER_API_KEY` returned `401 Unauthorized` on both
  `https://api.tradier.com/v1` and `https://sandbox.tradier.com/v1`.
  Re-run once a valid key is configured.
- App poll cadence is 5 s WS / 30 s REST **during 9:30–16:00 ET only**; quotes
  are only as fresh as the upstream provider.

## SPY-proxy disclosure (yfinance)

When `provider=yfinance`, `YFinanceClient` fetches **SPY** options and scales
by `SPY_TO_SPX_RATIO = 10.0`: spot price, strikes, bid, and ask are all
SPY×10 approximations of SPX — not real SPX quotes. Greeks (`has_greeks`) are
**false** for yfinance; all Greeks are computed locally by the vectorized
Black-Scholes engine. Tradier serves real SPX/SPXW chains with ORATS Greeks.
