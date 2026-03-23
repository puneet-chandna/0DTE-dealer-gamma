# AKShare Global Data Expansion Plan

## Summary

This document captures the current recommendation for expanding the repo with a free, broader market-data layer centered on `akshare`. The goal is to improve global market coverage, historical data availability, and analytics breadth without disturbing the existing Tradier/YFinance-backed live GEX workflow.

`akshare` is the strongest free breadth play among the reviewed options because it fits the current Python/FastAPI stack, has wide market and macro coverage, and can expand the repo beyond the current SPX-centric live options path. This plan is a future implementation note, not a finalized architecture spec.

The existing [PROVIDER_INTEGRATION_PLAN.md](/home/puneet/codes/ODTE-dealer-gamma/docs/PROVIDER_INTEGRATION_PLAN.md) should remain untouched as historical context.

## Recommendation Hierarchy

### Primary Integration Candidate

- `akshare`
  - Repo: https://github.com/akfamily/akshare
  - Best fit for free global breadth, macro/reference data, and broader analytics use cases.
  - Good candidate for adding historical prices, market context, listings, and non-US dataset coverage.

### Not Recommended As Direct Runtime Dependencies

- `aktools`
  - Repo: https://github.com/akfamily/aktools
  - Not recommended for direct integration because it is effectively an HTTP wrapper around AKShare and would duplicate this repo's own backend role.

- `akquant`
  - Repo: https://github.com/akfamily/akquant
  - Useful as a research/reference project, but not a clean runtime dependency for this app's current provider architecture.

- `akbroker`
  - Repo: https://github.com/akfamily/akbroker
  - More relevant as tutorial/reference material than as an implementation dependency for this repo.

- `awesome-data`
  - Repo: https://github.com/akfamily/awesome-data
  - Useful as a discovery/reference list only, not as a direct code integration target.

## Recommended Companion Tools

- `pandas_market_calendars`
  - Repo: https://github.com/rsheftel/pandas_market_calendars
  - Recommended for exchange-session correctness, holiday handling, and future global market open/close behavior.

- `FinanceDataReader`
  - Repo: https://github.com/FinanceData/FinanceDataReader
  - Recommended only as a fallback if AKShare coverage turns out to be uneven for specific global historical-price use cases.

## Implementation Direction

- `akshare` may appear in the frontend provider selector.
- `akshare` should be treated as a partial-capability provider rather than as a full replacement for `tradier` or `yfinance`.
- Dashboard live GEX, options-chain views, and the live websocket path should remain Tradier/YFinance-backed unless AKShare later proves equivalent support for the required SPX options data.
- Analytics, global-context views, and historical-data surfaces are the right places to expand first with AKShare.
- Unsupported `akshare` features should be gated explicitly instead of silently falling back to another provider.

## Concrete Next-Step Items

- Add `AkShareClient` in the backend provider layer.
- Extend provider capability metadata so the frontend can distinguish between full live-GEX providers and partial historical/context providers.
- Add `get_price_history(...)` to the shared provider contract so non-options providers can still power analytics and historical workflows.
- Gate unsupported GEX/options features cleanly for `akshare`.
- Add a global-context surface powered by AKShare.
- Integrate `pandas_market_calendars` for exchange/session correctness.

## Assumptions

- This file is intended to be a future implementation plan, not a finalized architecture spec.
- The plan preserves the already-discussed AKShare recommendation rather than expanding scope into a new architecture decision.
- No existing docs file should be overwritten.
