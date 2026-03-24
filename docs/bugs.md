# Current Bugs And Data Issues

This file is the working tracker for runtime bugs, data correctness issues, and UX gaps that affect the current project.

## 1. Provider capture loop can fall behind or starve one provider
- Severity: `P0`
- Page/subsystem: `backend historical capture`
- Reproduction steps:
  1. Start the app during market hours.
  2. Keep the frontend on `yfinance`.
  3. Inspect `market_sessions`, `gex_snapshots`, `raw_options_snapshots`, and `iv_surface_points`.
- Actual behavior:
  Only one provider may continue writing rows, or capture can stall instead of advancing cleanly for both providers.
- Expected behavior:
  Backend capture should persist `yfinance` and `tradier` independently, regardless of what provider the frontend is viewing.
- Current evidence from code/runtime:
  Historical capture used a single serial loop and the live runtime showed only `yfinance` rows in the database.
- Suspected root cause:
  Slow provider calls and conservative rate limiting could block or starve the rest of the watchlist cycle.
- Acceptance criteria:
  During market hours, timestamps and counts should keep moving for each available provider/symbol combination.
- Status: `fixed`

## 2. Dashboard intraday series collapses after page navigation
- Severity: `P0`
- Page/subsystem: `frontend dashboard`
- Reproduction steps:
  1. Open the dashboard and let intraday points accumulate.
  2. Navigate to analytics.
  3. Return to the dashboard.
- Actual behavior:
  The intraday chart can fall back to only the small persisted seed instead of the full session seen earlier.
- Expected behavior:
  The intraday chart should preserve the accumulated session for the current provider/symbol/trading date.
- Current evidence from code/runtime:
  The series was owned by hook-local state and reset on remount.
- Suspected root cause:
  Navigation remounted the hook and discarded in-memory accumulated points.
- Acceptance criteria:
  Route changes should not reduce the intraday series back to a tiny seed set.
- Status: `fixed`

## 3. Dashboard sometimes needs manual refresh to recover from stale current data
- Severity: `P1`
- Page/subsystem: `frontend dashboard + backend current routes`
- Reproduction steps:
  1. Leave the dashboard open while provider responses are slow.
  2. Navigate away and return.
  3. Compare the visible values with current market conditions.
- Actual behavior:
  Current GEX, regime, and strike views can appear stale until the manual refresh button is pressed.
- Expected behavior:
  The dashboard should automatically fall back to the newest persisted snapshot when live fetches are slow or empty.
- Current evidence from code/runtime:
  Current-route behavior depended heavily on fresh live fetches or cache hits.
- Suspected root cause:
  Persisted DB history was not being used as a strong fallback for current reads.
- Acceptance criteria:
  Current data should stay populated from DB-backed snapshots even when live provider fetches fail temporarily.
- Status: `fixed`

## 4. Zero gamma can look frozen or obviously stale
- Severity: `P1`
- Page/subsystem: `dashboard metrics + current GEX route`
- Reproduction steps:
  1. Open the dashboard during an unstable provider session.
  2. Compare zero gamma against current spot.
- Actual behavior:
  Zero gamma can remain at an old or mock-looking level.
- Expected behavior:
  Zero gamma should reflect the latest live or persisted snapshot, and stale state should be visible if it cannot.
- Current evidence from code/runtime:
  Mock fallback values and stale cache paths could surface when live data was unavailable.
- Suspected root cause:
  Current routes and websocket fallback paths did not strongly prefer persisted snapshots over weak live fallbacks.
- Acceptance criteria:
  When live fetches fail, zero gamma should still come from the newest persisted capture instead of drifting to mock-like values.
- Status: `fixed`

## 5. Analytics reloads expensively after navigation
- Severity: `P1`
- Page/subsystem: `frontend analytics`
- Reproduction steps:
  1. Open analytics and let the charts load.
  2. Navigate to dashboard.
  3. Return to analytics a few minutes later.
- Actual behavior:
  Analytics can refetch and recompute more aggressively than necessary.
- Expected behavior:
  Repeat visits in the same session should reuse cached provider-specific data where possible.
- Current evidence from code/runtime:
  Query freshness windows were short for heavier analytics views.
- Suspected root cause:
  Analytics queries were treated as near-live instead of DB-backed views with longer useful lifetimes.
- Acceptance criteria:
  Repeat navigation in the same session should feel faster and avoid unnecessary recomputation.
- Status: `fixed`

## 6. Technical Indicators chart can render as an empty-looking chart
- Severity: `P1`
- Page/subsystem: `frontend analytics`
- Reproduction steps:
  1. Open analytics.
  2. Choose an interval/period with very little persisted history.
- Actual behavior:
  The chart can show only a dot or a nearly empty slope with little explanation.
- Expected behavior:
  The UI should explain that more persisted history is needed for ATR/RSI/Bollinger calculations.
- Current evidence from code/runtime:
  The backend can return price points without enough bars to compute indicators.
- Suspected root cause:
  The chart rendered without a dedicated insufficient-history state.
- Acceptance criteria:
  Insufficient-history selections should show a clear message instead of a misleading chart.
- Status: `fixed`

## 7. Technical chart legends and labels are not explicit enough
- Severity: `P2`
- Page/subsystem: `frontend analytics`
- Reproduction steps:
  1. Open the Technical Indicators section.
  2. Try to identify each plotted series quickly.
- Actual behavior:
  Color/series meaning is easy to lose, especially after revisiting the page.
- Expected behavior:
  The chart should visibly label close, Bollinger Bands, ATR, and RSI.
- Current evidence from code/runtime:
  The page relied mostly on axes and tooltip labels.
- Suspected root cause:
  No always-visible legend chips existed near the chart.
- Acceptance criteria:
  Users can identify each plotted series without hovering.
- Status: `fixed`

## 8. Shared cloud database for teammates is still missing
- Severity: `P2`
- Page/subsystem: `infrastructure`
- Reproduction steps:
  1. Ask a teammate to clone the repo on a new machine.
  2. Compare their local history against yours.
- Actual behavior:
  Everyone can run the project locally, but local history stays machine-specific.
- Expected behavior:
  Teammates should be able to point at a shared Postgres instance when collaboration needs shared captured data.
- Current evidence from code/runtime:
  The project is intentionally local-first right now.
- Suspected root cause:
  Cloud DB rollout was deferred until local persistence is stable.
- Acceptance criteria:
  A later infra milestone should add a shared cloud Postgres option with safe env-based switching.
- Status: `planned`
