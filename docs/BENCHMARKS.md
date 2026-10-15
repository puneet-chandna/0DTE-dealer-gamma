# Benchmarks

Measured numbers, with workload and measurement boundaries. Install the backend
dependencies, then run the deterministic local pipeline benchmark from the
repository root:

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python scripts/benchmark_pipeline.py --samples 500 \
  --output /tmp/gex-pipeline-benchmark.json
```

The output path must be new. The JSON preserves every retained timing, empirical
p50/p95/p99, throughput, per-stage traced memory, process peak RSS, source hashes,
calculation version, CPU, platform, Python/library versions, NumPy build, and
thread settings. Three warmups precede each stage. The default is 200 retained
samples; use 500 or more for a less sparse upper tail. Percentiles are estimates
from one local run, not service-level guarantees.

The workloads are fixed **synthetic engineering inputs**: 1,000 and 10,000
contracts, paired calls/puts, the same 100 distinct strikes within ±3% of 6,600,
IV 18%, deterministic open interest, and four hours to expiry at
2026-10-14 12:00 ET. The benchmark has no provider calls or server startup.
Contract rows repeat within the fixed strike universe to isolate contract-count
scaling; this is a stress workload, not a claim that a real 0DTE chain contains
10,000 distinct contracts.

The `local_pipeline_v2` report also includes `realistic_spx_workload`: a fixed
2,010-contract engineering fixture with 201 strikes at five-point spacing,
five expiries, distinct per-contract IV, deterministic integer open interest,
and a synthetic skew/term structure around SPX 6,600. This measures
`calculate_gex_from_chain` with 2,010 distinct pricing kernels instead of
collapsing the same strike/IV/expiry rows. The fixture is synthetic and is not
a quote snapshot or evidence of tradable prices.

## Measurement boundaries

- **Greeks:** the vectorized `calculate_all_greeks` call on prebuilt NumPy arrays.
- **GEX calculation:** the actual calculator on a prebuilt pandas chain,
  including validation, Greeks, aggregation, repriced zero-gamma scenarios,
  and charm/vanna calculations. This contains some of the separately measured
  stages; their timings must not be added to this total.
- **Aggregation:** the production grouping method on prebuilt strikes and
  deterministic signed weights. This isolates grouping cost.
- **Serialization:** Pydantic JSON serialization of a precomputed full snapshot.
- **SQLite JSON commit:** inserting that already serialized snapshot into a
  disposable local SQLite table and committing each row. This measures stdlib
  SQLite persistence, not the application's ORM, capture service, or IV writes.

`contracts_per_second` is workload size divided by median latency for that
stage. It is single-process batch throughput, not concurrent request capacity.
Memory is observed in a separate untimed call so tracing does not inflate the
latency samples. `tracemalloc` is not a complete native-memory profiler; the
reported process peak RSS includes imports, all stages, and native allocations,
and cannot attribute the peak to one stage. SQLite filesystem/cache settings,
CPU frequency, background activity, and OS scheduling affect these numbers.
The zero-gamma search scans unique strikes and contract centers and reprices
the active contracts at each scenario. Its work grows with scenario count times
contract count; increasing the number of unique strikes changes that workload
too. The fixed 100-strike benchmark does not measure this worst case; the additional
distinct-IV fixture exercises a broader kernel mix without claiming a worst-case
bound. Zero-gamma candidate points are sampled in bounded NumPy blocks, while
scalar root refinement and the original crossing/nearest-root rules are retained.

Provider fetch, network transport, HTTP/ASGI routing, browser rendering, database
concurrency, and production tail latency are **unmeasured**. The script leaves
the application capture database untouched and removes only its own temporary
SQLite files.

The small non-gating pytest probe reports 500 retained Greek timings for each
workload and gates only output shape/finiteness:

```bash
cd backend
python -m pytest --no-cov -s tests/test_greeks_perf.py
python -m pytest --no-cov tests/test_benchmark_pipeline.py
```

The offline [captured-data research command](../scripts/research_gex_volatility.py)
is separate from this synthetic benchmark. The original local database remains empty. A separate short
live-validation capture was audited on 2026-10-14; it is insufficient for a
predictive study and does not turn these synthetic workloads into market evidence.

## Local pipeline measurements — 2026-10-14

The final run retained **500 samples per stage/workload** under Python 3.13.15,
NumPy 2.2.6, SciPy 1.15.1 and pandas 2.3.3 on the i5-1235U. OMP, OpenBLAS and
MKL thread environment variables were each set to 1. The local application was
being launched and audited in a browser during this run; the development host,
CPU frequency and background work were not isolated.

Each sequence below is **p50 / p95 / p99 in milliseconds**, first for 1,000
contracts and then for 10,000 contracts, with 100 distinct strikes in both.

- Greeks: **0.617 / 1.383 / 1.735**; **2.658 / 2.942 / 3.228**.
  Median batch throughput was 1.62M and 3.76M contracts/s.
- Full GEX calculation: **10.575 / 20.956 / 28.788**;
  **80.541 / 95.835 / 148.002**. Median batch throughput was 94.6k and
  124.2k contracts/s.
- Aggregation: **0.035 / 0.038 / 0.046**; **0.221 / 0.237 / 0.246**.
- Snapshot JSON serialization: **0.058 / 0.062 / 0.068**;
  **0.060 / 0.064 / 0.066**. Serialized outputs were 9,467 and 9,424 bytes;
  a fixed strike count keeps this output size nearly constant.
- SQLite JSON row commit: **0.029 / 0.036 / 0.042**;
  **0.030 / 0.037 / 0.045**. This is a disposable local `/tmp` database,
  not measured durability or latency for production persistence.

Separate traced allocation peaks were 263,425 / 2,580,729 bytes for Greeks and
301,098 / 2,699,604 bytes for full GEX calculation. The process peak RSS was
241,299,456 bytes (about 230.1 MiB). Raw timing arrays, all stage throughput and
memory figures, source hashes, library/build metadata and the declared
background workload are saved locally in
`data/processed/improvements-evidence-2026-10-14/odte-pipeline-benchmark-final-20261014.json`.
The evidence directory is intentionally ignored by Git.
These figures describe this developer-host run; they are not a production SLA
or an unqualified performance improvement over another implementation.

## Aggregation comparison — 2026-10-14

A separate deterministic microbenchmark compared the previous per-strike
mask/sum loop with the new unique/inverse-index/bincount grouping. It used seed
3401, three warmups, and nine retained samples per implementation, on the
i5-1235U with Python 3.13.15 and NumPy 2.2.6. Before/after outputs matched at
`rtol=1e-12, atol=1e-8` in the fixture checks.

- 1,000 contracts / 500 distinct strikes: GEX aggregation median **1.770 ms →
  0.0934 ms**, about **19×**; charm/vanna grouping **1.621 ms → 0.0682 ms**,
  about **24×**.
- 10,000 contracts / 5,000 distinct strikes: GEX aggregation median **30.211 ms
  → 0.7038 ms**, about **43×**; charm/vanna grouping **30.346 ms → 0.7447 ms**,
  about **41×**.

These are grouping-only median ratios on a different strike distribution from
the fixed 100-strike pipeline workload. Nine samples do not justify a p99 or a
service-capacity claim. The saved local timing arrays are in
`data/processed/improvements-evidence-2026-10-14/odte-math-perf.json`;
the local ignored file also records the separate exploratory run
and root-search timings. Faster grouping does not make the entire calculator
43× faster: the new repriced zero-gamma search adds different work.

## Historical measurements — 2026-09-24

The following previously recorded figures are retained with their original
workload. They were not rerun during the 2026-10-14 offline work, and their
five-sample maxima are not p99 estimates. The current zero-gamma method also does
more work than that historical calculator, so these full-calculation timings
are not a controlled before/after comparison.

### Machine

- CPU: 12th Gen Intel Core i5-1235U (x86_64), 12 threads
- Python 3.13.15, NumPy 2.2.6, SciPy 1.15.1
- Run host: local dev machine, 2026-09-24

### Historical synthetic Greeks throughput

`BlackScholesGreeks.calculate_all_greeks`, n=1000 0DTE-like contracts
(tight ±3% strikes, ~4h to expiry, IV 18%), median of 5 timed runs after warmup:

| Metric | Measured |
| ------ | -------- |
| p50    | ~0.5–0.6 ms |
| max of 5 | ~0.6–0.9 ms |

The original probe checked output shape and finiteness without a hardware-speed
assertion. The maximum of five samples is not a p99.

### Live market run — 2026-09-24 ~12:15 PM ET (market OPEN)

Procedure: `YFinanceClient.get_options_chain_for_gex("SPX")` then
`GEXCalculator.calculate_gex_from_chain` × 5 (GEX calc = gamma + charm/vanna +
aggregation; p50 over 5 runs).

| Provider | Spot | Contracts (gex-ready / strikes) | Fetch latency | GEX calc p50 | GEX calc max |
| -------- | ---- | ------------------------------- | ------------- | ------------ | ------------ |
| yfinance (SPY×10 proxy) | 7641.30 | 247 / 124 | ~1.4–1.7 s | 3.69 ms | 3.97 ms |
| tradier | — | — | FAILED (HTTP 401 on prod **and** sandbox) | — | — |

Live snapshot values (yfinance run): net GEX ≈ −3.555e10, zero-gamma ≈ 6150.

### Provider-delay disclaimer

- **Yahoo Finance publishes a nominal 15-minute OPRA options delay.** See
  [Yahoo's exchange and data-provider table](https://help.yahoo.com/kb/finance/article-exchanges-data-delays-sln2310.html).
  Through yfinance, per-quote freshness remains unverified: last-trade time is
  not bid/ask time, and frequent polling does not guarantee new quotes or OI.
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

## Distinct-IV zero-gamma scan comparison — 2026-10-15

A paired local run compared the prior scalar point scan with the chunked NumPy
scan inside the full `calculate_gex_from_chain` call. The fixed synthetic SPX
chain contains 2,010 contracts, 201 strikes from 6,100 to 7,100 in five-point
steps, and expiries 0/1/7/30/58 calendar days after the reference date, all on
weekdays. Every contract has distinct IV and integer open interest. Spot is
6,600 and the reference clock remains 2026-10-14 12:00 ET.

After three warmups per implementation, the run retained 100 timings each,
alternating before/after order. Median full-calculation latency was
**160.647 ms scalar → 129.097 ms chunked** (1.244× throughput at this workload,
19.6% lower median latency). Empirical p95 was **206.961 → 163.702 ms**.
Every snapshot field matched exactly in all timed calls, including the
zero-gamma root **6,595.760701976612**.

The separate traced allocation peak increased from **814,130 to 2,203,457 bytes**
for the bounded vector workspace. Tracing is not included in latency samples
and is not a complete native-memory measurement. The run took **31.939 seconds**
for warmups, paired trials, equality checks and allocation calls, excluding
imports and fixture setup.

Environment: Python 3.13.15, NumPy 2.2.6, SciPy 1.15.1, pandas 2.3.3, i5-1235U.
Thread environment variables were unset; CPU frequency and background work were
uncontrolled. These measurements establish a local engineering improvement for
this fixture, not an HFT latency or production tail guarantee. The exact source
copies, fixture CSV, raw timings, environment and hashes are retained locally in
`data/processed/coderabbit-fixes-2026-10-15/zero-gamma/`.
