# Provider Integration and Remaining Work Plan

Reviewed on **2026-10-14** against implementation commit `bad0579`, merged into
`main` through [PR #9](https://github.com/puneet-chandna/0DTE-dealer-gamma/pull/9).
Completed checkboxes describe implemented
behavior; live provider acceptance and cloud rollout remain separate milestones.

The goal is to validate the supported providers before expanding data sources,
then complete capability handling and shared-history support where needed.

## Completed Implementation

### Backend provider integration

- [x] Define the shared abstract [DataProvider contract](../backend/app/core/base_provider.py): spot prices, expirations, chain snapshots, GEX-ready chains, and resource cleanup.
- [x] Register YFinance and Tradier, reuse client instances, and close them on shutdown in [ProviderRegistry](../backend/app/core/provider_registry.py).
- [x] Accept provider selection on provider-sensitive data, GEX, and analytics requests. Partition their GEX/options-chain caches and frontend query keys by provider.
- [x] Capture historical data through provider-specific workers in [background.py](../backend/app/services/background.py).
- [x] Implement [TradierClient](../backend/app/core/tradier_provider.py), including quote/expiration parsing and options/ORATS Greek mapping to the shared DataFrame schema.
- [x] Add [mocked Tradier tests](../backend/tests/test_tradier_provider.py) for quote extraction, expiration normalization, and options-chain mapping.
- [x] Report missing-key availability through the provider registry, with [registry tests](../backend/tests/test_provider_registry.py). A present key is not proof that authentication succeeds.

### Frontend provider selection

- [x] Define provider names, metadata, and the initial static feature configuration in [types/index.ts](../frontend/src/types/index.ts).
- [x] Store `selectedProvider` and `availableProviders`, and recover an unavailable saved selection in [uiStore.ts](../frontend/src/stores/uiStore.ts).
- [x] Add the [ProviderSelector](../frontend/src/components/ui/ProviderSelector.tsx) for YFinance and Tradier, disabling unavailable options. AkShare is not implemented.
- [x] Pass provider selection through [REST requests](../frontend/src/lib/api.ts), WebSocket requests, and provider-specific query keys.
- [x] Add [selector tests](../frontend/src/components/ui/ProviderSelector.test.tsx) and [store tests](../frontend/src/stores/uiStore.test.ts).
- [x] Add an IV query enablement hook in analytics. Full unsupported-feature UI handling remains in priority 2 below.

### Validation baseline

The [CI run for `bad0579`](https://github.com/puneet-chandna/0DTE-dealer-gamma/actions/runs/38500293782)
passed all five jobs on `namespace-profile-puneet-chandna`: backend Ruff,
**515 backend tests with six integration tests excluded**, frontend ESLint,
**203 frontend tests**, and the production build. Local type checking,
SQLite migrations, and combined startup/shutdown checks also passed during
that review. This dated baseline does not establish live Tradier acceptance.

The [2026-09-24 benchmark](BENCHMARKS.md#live-market-run--2026-09-24-1215-pm-et-market-open)
records HTTP 401 for Tradier production and sandbox. Preserve that result;
append a new dated result when a successful live run is available.

## Prioritized Remaining Work

Priorities are execution order, not merge blockers for the existing local-run
change. Offline provider tests and capability work can proceed while a valid
live credential or market-hours window is unavailable.

### 1. P1 — Validate current providers and authentication failures

**Why first:** Tradier is implemented, but a successful production dashboard
run is still unverified. Missing-key detection alone does not cover invalid keys.

**Scope:** [Tradier adapter/tests](../backend/app/core/tradier_provider.py),
[API tests](../backend/tests/test_api.py), [WebSocket tests](../backend/tests/test_websocket.py),
provider-selection UI, and [BENCHMARKS.md](BENCHMARKS.md).

- [ ] Add deterministic HTTP failure cases for invalid keys (401/403), rate limiting (429), timeouts, and malformed/empty responses. Exercise both a usable cache/persisted fallback and no usable fallback.
- [ ] Check that the UI exposes unavailable/stale data clearly and that provider switching keeps responses, charts, and caches associated with the requested provider. Do not silently substitute another provider's data.
- [ ] With a valid production credential during market hours, select Tradier and verify REST/WebSocket GEX, spot, contract counts, timestamps, and historical capture against that provider's fetched chain. Check YFinance switching separately.
- [ ] Record environment, provider, timestamp, contract count, fetch/calculation timings, and sanitized results. Keep production and sandbox results distinct and live checks separate from deterministic CI.

**Done when:** offline failure cases pass and a dated successful production run
is recorded. If access is unavailable, retain the unchecked live step and record
the blocker rather than marking acceptance complete.

### 2. P2 — Complete provider capability and unavailable-state handling

**Why next:** `PROVIDER_FEATURES` currently enables every listed feature for both
providers. Analytics gates its IV request, but still renders the chart container;
technical indicators do not use the feature flag. The general adaptation item
is therefore only partially implemented.

**Scope:** [provider metadata](../backend/app/core/provider_registry.py),
[feature types](../frontend/src/types/index.ts), [analytics page](../frontend/src/app/analytics/page.tsx),
[analytics hooks](../frontend/src/hooks/useAnalyticsData.ts), and their existing tests.

- [ ] Define effective capabilities for the supported provider/environment combinations, including Tradier production versus sandbox. Reuse the existing metadata/configuration before adding a new capability mechanism.
- [ ] Suppress unsupported requests and show an explicit reason in place of an unsupported chart. Cover provider changes and unavailable selections in component/hook tests.
- [ ] Preserve locally computed Greeks and captured-history features: a provider lacking supplied Greeks or historical endpoints does not by itself make those application features unavailable.

**Done when:** tests cover at least one unavailable capability, prove that its
request is not sent, and verify recovery after switching to a supported provider
without losing the existing YFinance and Tradier views.

### 3. P2 — Roll out shared PostgreSQL when teammates need shared history

**Why after provider validation:** shared persistence is already supported by
the database adapter. The remaining work is an operational rollout, not a new
database implementation. This is [bug tracker item 8](bugs.md#8-shared-cloud-database-for-teammates-is-still-missing).

**Scope:** [DEPLOYMENT.md](DEPLOYMENT.md), [POSTGRES_SCHEMA.md](POSTGRES_SCHEMA.md),
the existing [DATABASE_URL handling](../backend/app/db/session.py), and persistence checks.

- [ ] Choose the shared database host, access arrangements, and capture owner. Start with one capture backend so multiple teammate app instances do not unintentionally duplicate collection.
- [ ] Reuse `DATABASE_URL` and existing Alembic migrations to configure a disposable shared PostgreSQL database. Document connection setup and migration ownership; keep SQLite as the local default.
- [ ] Verify that two clients read the same provider/symbol/session history, records survive a backend restart, and backup/restore works. Record how existing local history is retained or explicitly imported rather than replacing it silently.
- [ ] Update the deployment guide and close tracker item 8 only after the shared setup is tested and its access instructions are usable by a teammate.

**Done when:** shared-history and recovery evidence is recorded and the existing
SQLite path remains usable. This milestone depends on an actual collaboration
need and a selected host.

### 4. P3 — Evaluate AkShare, then implement one defined market

**Why last:** this is optional expansion. The old plan's broad promise of
Chinese/global options support does not define a usable instrument or prove data
coverage and compatibility with the current US-market assumptions.

- [ ] Select one exchange/instrument and verify available option chains, spot, volume, open interest, and expiration data before committing to an adapter.
- [ ] Specify contract multiplier, currency, Greek units, trading timezone/session, expiration conventions, and symbol mapping. Check the calculator and historical storage assumptions against those values.
- [ ] If that feasibility check passes, implement `backend/app/core/akshare_provider.py` against the existing DataProvider contract, register it, and extend frontend provider types/selection/capabilities and capture configuration for the supported scope.
- [ ] Add sanitized response fixtures and tests for missing fields, date/strike normalization, contract units, and provider isolation, followed by a separate live acceptance run.

**Done when:** one explicitly supported market works through acquisition,
calculation, persistence, and UI without SPY-to-SPX proxy assumptions leaking into
it. If coverage is inadequate or the market is not needed, leave this deferred.

## Status Maintenance

Mark implementation complete only with a code/test reference. Mark live
acceptance or deployment complete only with dated runtime evidence. Keep the
[bug tracker](bugs.md) for observed issues; keep this document for remaining
milestones and their acceptance criteria. Create detailed implementation plans
for individual milestones when their inputs and scope are settled.
