# Modular Data Provider Architecture

## Backend
- [x] Create abstract base [DataProvider](file:///home/puneet/codes/ODTE-dealer-gamma/backend/app/core/base_provider.py#15-111) protocol/ABC in [app/core/base_provider.py](file:///home/puneet/codes/ODTE-dealer-gamma/backend/app/core/base_provider.py)
- [x] Refactor [YFinanceClient](file:///home/puneet/codes/ODTE-dealer-gamma/backend/app/core/yfinance_provider.py#29-415) to implement [DataProvider](file:///home/puneet/codes/ODTE-dealer-gamma/backend/app/core/base_provider.py#15-111) interface
- [ ] Create [TradierClient](file:///home/puneet/codes/ODTE-dealer-gamma/backend/app/core/tradier_provider.py#31-396) implementing [DataProvider](file:///home/puneet/codes/ODTE-dealer-gamma/backend/app/core/base_provider.py#15-111) (fetching latest API docs)
- [x] Create provider registry/factory in [app/core/provider_registry.py](file:///home/puneet/codes/ODTE-dealer-gamma/backend/app/core/provider_registry.py)
- [x] Add `DATA_PROVIDER` and `TRADIER_API_KEY` to [config.py](file:///home/puneet/codes/ODTE-dealer-gamma/backend/app/config.py)
- [x] Add new `/api/data/providers` endpoint and modify existing endpoints to accept `?provider=` param
- [x] Refactor [gex.py](file:///home/puneet/codes/ODTE-dealer-gamma/backend/app/api/routes/gex.py), [data.py](file:///home/puneet/codes/ODTE-dealer-gamma/backend/app/api/routes/data.py), [websocket.py](file:///home/puneet/codes/ODTE-dealer-gamma/backend/app/api/websocket.py), [analytics.py](file:///home/puneet/codes/ODTE-dealer-gamma/backend/app/core/analytics.py), [background.py](file:///home/puneet/codes/ODTE-dealer-gamma/backend/tests/test_background.py) to use provider registry
- [x] Update [__init__.py](file:///home/puneet/codes/ODTE-dealer-gamma/backend/app/__init__.py) exports
- [ ] Update [requirements.txt](file:///home/puneet/codes/ODTE-dealer-gamma/backend/requirements.txt) (add `httpx` for Tradier async calls)

## Frontend
- [ ] Add [DataProvider](file:///home/puneet/codes/ODTE-dealer-gamma/backend/app/core/base_provider.py#15-111) type and provider feature config to [types/index.ts](file:///home/puneet/codes/ODTE-dealer-gamma/frontend/src/types/index.ts)
- [ ] Add `selectedProvider` to Zustand store ([uiStore.ts](file:///home/puneet/codes/ODTE-dealer-gamma/frontend/src/stores/uiStore.ts))
- [ ] Add provider selector component
- [ ] Create provider-aware API calls (pass `?provider=` param)
- [ ] Update dashboard page to adapt UI based on provider capabilities
- [ ] Update analytics page to show/hide features per provider

## Testing & Verification
- [ ] Write `test_base_provider.py` for the abstract interface
- [ ] Write `test_tradier_provider.py` with mocked HTTP calls
- [ ] Write `test_provider_registry.py` for factory/registry logic
- [ ] Update [test_api.py](file:///home/puneet/codes/ODTE-dealer-gamma/backend/tests/test_api.py) with provider query param tests
- [x] Run existing test suite to ensure no regressions
