# Data Provider Integration & Migration Plan

## Recent Architecture Changes
We recently decoupled the backend from its hardcoded dependency on YFinance by introducing a **Modular Data Provider Architecture**. The core changes include:

1. **`DataProvider` Protocol:** Created an abstract base class (`app/core/base_provider.py`) defining standard interfaces (`get_options_chain_for_gex`, `get_spot_price`, `get_ticker_symbol`). This ensures all data sources return standardized structures (e.g., matching the `OptionContract` schema).
2. **`ProviderRegistry`:** Implemented a central factory (`app/core/provider_registry.py`) to manage singleton instances of registered data providers and gracefully handle connection closures on shutdown.
3. **Dynamic Routing:** All API routes (`/options-chain`, `/spot-price`, `/gex/*`, `/market-status`) were refactored to accept an optional `?provider=` query parameter. If none is passed, the system falls back to the default configured in `app/config.py` (e.g., `yfinance`).
4. **Cache Partitioning:** Cache keys are now partitioned by the active provider (e.g., `gex:current:SPY:{provider}`) to prevent data collisions when viewing the dashboard from different sources.
5. **Background Refresh:** The background tasks now utilize the active data provider efficiently without raising type errors. 
6. **Robust Testing:** The entire test suite (290 tests) was adapted and verifies that this abstraction hasn't broken any historical YFinance behavior.

## Project Impact
- **Flexibility:** The backend can now dynamically serve data from multiple APIs on-the-fly without restarting or altering global state.
- **Scalability:** Adding new providers (such as Tradier or AkShare) only requires writing a single class that adheres to the `DataProvider` protocol and adding a single line to the registry. The rest of the backend will "just work."
- **Resilience:** The backend is much safer and structured to handle timeouts, empty data structures, and edge cases uniformly.

---

## Remaining Implementation Checklist (To-Do)

To fully integrate the target providers (Tradier and AkShare) and ensure the application remains compatible and smooth across both backend and frontend, the following tasks remain:

### 1. Tradier Integration
- [ ] Read the latest Tradier developer documentation for API options quotes and chains.
- [ ] Implement `TradierClient` (in `app/core/tradier_provider.py`) implementing the `DataProvider` protocol.
- [ ] Map Tradier's JSON responses (and integrated ORATS Greeks) into our standard DataFrame/OptionContract schema.
- [ ] Add `test_tradier_provider.py` to test the new client using mocked API responses.

### 2. AkShare Integration (Optional/Later)
- [ ] Implement `AkShareClient` (in `app/core/akshare_provider.py`).
- [ ] Map Chinese/Global stock option data into our standard GEX calculation logic.
- [ ] Ensure formatting handles potential differences in strike intervals or date strings.

### 3. Frontend Implementation
- [ ] Add `DataProvider` feature configuration typings in `src/types/index.ts`.
- [ ] Add `selectedProvider` and `availableProviders` state to the Zustand store (`uiStore.ts`).
- [ ] Create a "Data Source Selector" UI component (perhaps in the Header or Settings modal) so the user can flick between YFinance, Tradier, and AkShare.
- [ ] Refactor fetch calls in `api.ts` to append the `?provider=` parameter based on the `selectedProvider` state.
- [ ] Adapt UI elements: If a chosen data provider does not support certain features (e.g., no historical data, or no Greeks), the frontend should gracefully hide or disable those charts rather than breaking.

### 4. Final End-to-End Testing
- [ ] Verify that selecting Tradier on the dashboard updates the GEX profile using live Tradier production data.
- [ ] Verify that invalid API keys or missing providers fall back gracefully.
