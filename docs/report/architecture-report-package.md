# Architecture Report Package

This package turns the project architecture into three synchronized report artifacts:

1. Mermaid source diagrams for direct editing and export
2. A DiagramGPT prompt for polished external rendering
3. A finished diagram brief with figure titles, labels, captions, and short report-ready explanations

## Artifact Index

- Mermaid source: `docs/report/figure-1-high-level-system-architecture.mmd`
- Eraser source: `docs/report/figure-1-high-level-system-architecture.eraserdiagram`
- Mermaid source: `docs/report/figure-2-runtime-data-and-processing-flow.mmd`
- Eraser source: `docs/report/figure-2-runtime-data-and-processing-flow.eraserdiagram`
- Rendered SVG: `docs/report/figure-1-high-level-system-architecture.svg`
- Rendered SVG: `docs/report/figure-2-runtime-data-and-processing-flow.svg`

## Canonical Architecture Notes

- The system is a split web application with a Next.js frontend and a FastAPI backend.
- The backend retrieves market data through a provider registry that currently supports `yfinance` and `tradier`.
- Real-time monitoring is supported by background refresh services, an in-memory TTL cache, REST endpoints, and a WebSocket stream.
- Historical persistence and replay are backed by PostgreSQL and store market sessions, GEX snapshots, strike-level breakdowns, raw options captures, and IV-surface data.
- The frontend uses React Query for server state, Zustand for UI-only state, and a WebSocket-first dashboard flow with REST fallback.
- Redis is intentionally excluded from the report diagrams because it is commented out as an optional service and is not part of the active runtime architecture.

## DiagramGPT Prompt

Copy only the text inside the fenced `text` code block below. The sections after this block are reference material for your report package and are not part of the DiagramGPT prompt.

```text
Create a clean, report-ready, C4-lite academic architecture set for a project titled:
"0DTE Dealer Gamma Exposure (GEX) Monitor"

Generate two separate diagrams with a consistent visual language.

Global styling requirements:
- white or very light background
- blue/gray academic palette
- solid arrows for primary flows
- dashed arrows for fallback or optional flows
- simple rectangular containers with clear titles
- no code file paths inside the diagrams
- readable in an academic project report
- landscape orientation, balanced spacing, minimal clutter

Diagram 1 title:
Figure 1. High-Level System Architecture

Diagram 1 layout:
- left-to-right
- use five grouped containers:
  1. End User
  2. Frontend Application
  3. Backend Platform
  4. External Market Data Providers
  5. PostgreSQL Persistence

Diagram 1 contents:
- End User group:
  - Trader / Analyst / Research User
- Frontend Application group:
  - Next.js 16 Web Application
  - User-Facing Pages: Dashboard, Analytics, Backtest, Dealer Flows
  - React Query Server-State Layer
  - Zustand UI State
  - Charts & Visualization Layer
- Backend Platform group:
  - FastAPI REST API
  - WebSocket Stream (/ws/gex-stream)
  - Provider Registry
  - GEX / Greeks Calculation Engine
  - Analytics & Backtesting Engines
  - Background Refresh Services
  - In-Memory TTL Cache
  - Historical Persistence & Replay Service
- External Market Data Providers group:
  - YFinance Provider
  - Tradier Provider
- PostgreSQL Persistence group:
  - PostgreSQL 18
  - Market Sessions
  - GEX Snapshots & Strike Breakdown
  - Raw Options Snapshots & IV Surface

Diagram 1 required relationships:
- Trader / Analyst / Research User -> Next.js 16 Web Application
- User-Facing Pages -> React Query Server-State Layer
- User-Facing Pages -> Zustand UI State
- User-Facing Pages -> Charts & Visualization Layer
- React Query Server-State Layer -> FastAPI REST API labeled "REST / JSON"
- Next.js 16 Web Application -> WebSocket Stream labeled "WebSocket updates"
- FastAPI REST API -> Provider Registry
- FastAPI REST API -> In-Memory TTL Cache
- FastAPI REST API -> GEX / Greeks Calculation Engine
- FastAPI REST API -> Analytics & Backtesting Engines
- FastAPI REST API -> Historical Persistence & Replay Service
- WebSocket Stream -> Provider Registry
- WebSocket Stream -> In-Memory TTL Cache
- WebSocket Stream -> GEX / Greeks Calculation Engine
- Background Refresh Services -> Provider Registry
- Background Refresh Services -> GEX / Greeks Calculation Engine
- Background Refresh Services -> In-Memory TTL Cache
- Background Refresh Services -> Historical Persistence & Replay Service
- Analytics & Backtesting Engines -> Historical Persistence & Replay Service
- Provider Registry -> YFinance Provider
- Provider Registry -> Tradier Provider
- Historical Persistence & Replay Service -> PostgreSQL 18
- PostgreSQL 18 -> Market Sessions
- PostgreSQL 18 -> GEX Snapshots & Strike Breakdown
- PostgreSQL 18 -> Raw Options Snapshots & IV Surface

Diagram 2 title:
Figure 2. Runtime Data and Processing Flow

Diagram 2 layout:
- top-to-bottom
- lane-style grouped sections:
  1. External Sources
  2. Real-Time Monitoring
  3. Historical Persistence / Replay
  4. Frontend Consumption
  5. Resilience Paths

Diagram 2 contents:
- External Sources:
  - Provider Selection: YFinance or Tradier
  - Spot Price + Options Chain
- Real-Time Monitoring:
  - Background Refresh Services (cache warmup + periodic refresh)
  - GEX / Greeks Calculation
  - Hawkes + Kalman Enrichment
  - In-Memory TTL Cache
  - FastAPI REST Endpoints
  - WebSocket Stream (/ws/gex-stream)
  - Analytics & Backtesting Engines
- Historical Persistence / Replay:
  - Historical Persistence & Replay Service
  - PostgreSQL 18
  - Market Sessions / GEX Snapshots / Raw Options & IV Surface
- Frontend Consumption:
  - Frontend Initial Load
  - WebSocket Hook
  - React Query Cache Sync
  - Dashboard Components
  - Analytics and Backtest Pages
  - REST Polling Fallback
- Resilience Paths:
  - Live fetch on cache miss
  - Persisted replay / demo fallback

Diagram 2 primary flows:
- Provider Selection -> Spot Price + Options Chain labeled "selected provider"
- Spot Price + Options Chain -> Background Refresh Services labeled "options chain + spot"
- Background Refresh Services -> GEX / Greeks Calculation labeled "filtered contracts"
- GEX / Greeks Calculation -> Hawkes + Kalman Enrichment labeled "GEX snapshot"
- Hawkes + Kalman Enrichment -> In-Memory TTL Cache labeled "fresh live snapshot"
- Hawkes + Kalman Enrichment -> Historical Persistence & Replay Service labeled "persist eligible snapshot"
- Historical Persistence & Replay Service -> PostgreSQL 18
- PostgreSQL 18 -> Market Sessions / GEX Snapshots / Raw Options & IV Surface
- Frontend Initial Load -> FastAPI REST Endpoints labeled "REST requests"
- FastAPI REST Endpoints -> In-Memory TTL Cache labeled "check cache"
- FastAPI REST Endpoints -> Analytics & Backtesting Engines labeled "analytics or backtest requests"
- Analytics & Backtesting Engines -> Historical Persistence & Replay Service labeled "historical and replay queries"
- Analytics & Backtesting Engines -> FastAPI REST Endpoints
- FastAPI REST Endpoints -> Analytics and Backtest Pages labeled "summary, IV, technical, backtest payloads"
- In-Memory TTL Cache -> Dashboard Components labeled "current, strikes, and market payloads"
- In-Memory TTL Cache -> WebSocket Stream labeled "live snapshot"
- WebSocket Stream -> WebSocket Hook labeled "gex_update"
- WebSocket Hook -> React Query Cache Sync labeled "sync latest snapshot"
- React Query Cache Sync -> Dashboard Components

Diagram 2 fallback and resilience flows using dashed arrows:
- Analytics & Backtesting Engines -> Provider Selection labeled "provider-backed indicator fetches when needed"
- FastAPI REST Endpoints -> Live fetch on cache miss labeled "cache miss"
- Live fetch on cache miss -> Provider Selection
- Live fetch on cache miss -> GEX / Greeks Calculation
- FastAPI REST Endpoints -> Persisted replay / demo fallback labeled "provider unavailable or low-quality snapshot"
- PostgreSQL 18 -> Persisted replay / demo fallback labeled "replay-eligible session data"
- Persisted replay / demo fallback -> Dashboard Components labeled "persisted or demo response"
- WebSocket Hook -> REST Polling Fallback labeled "stream unavailable"
- REST Polling Fallback -> FastAPI REST Endpoints labeled "REST fallback"

The final result should look formal, minimal, and suitable for an official engineering or academic project report.
```

## Finished Diagram Brief

### Figure 1. High-Level System Architecture

**Purpose**

Show the static container-level architecture of the system, from user interaction through frontend delivery, backend processing, external market-data ingestion, and PostgreSQL-backed persistence.

**Node Labels**

- End User
  - Trader / Analyst / Research User
- Frontend Application
  - Next.js 16 Web Application
  - User-Facing Pages
  - React Query Server-State Layer
  - Zustand UI State
  - Charts & Visualization Layer
- Backend Platform
  - FastAPI REST API
  - WebSocket Stream (`/ws/gex-stream`)
  - Provider Registry
  - GEX / Greeks Calculation Engine
  - Analytics & Backtesting Engines
  - Background Refresh Services
  - In-Memory TTL Cache
  - Historical Persistence & Replay Service
- External Market Data Providers
  - YFinance Provider
  - Tradier Provider
- PostgreSQL Persistence
  - PostgreSQL 18
  - Market Sessions
  - GEX Snapshots & Strike Breakdown
  - Raw Options Snapshots & IV Surface

**Arrow Labels**

- `REST / JSON`
- `WebSocket updates`

**Caption**

Figure 1 presents the high-level architecture of the 0DTE Dealer Gamma Exposure Monitor. The frontend delivers multiple report and dashboard views, while the backend combines real-time REST and WebSocket delivery with provider-based market-data ingestion, in-memory caching, analytics services, and PostgreSQL-backed historical persistence.

**Short Report Explanation**

The architecture follows a web-based client-server model. The Next.js frontend serves the dashboard, analytics, backtest, and dealer-flow views, and uses React Query and Zustand to separate server state from UI state. The FastAPI backend orchestrates provider selection, GEX and Greeks computation, background refresh tasks, and historical replay, while PostgreSQL stores the structured session and snapshot data required for persistence and analytics.

### Figure 2. Runtime Data and Processing Flow

**Purpose**

Show how live market data moves through the system during operation, including background ingestion, GEX computation, streaming delivery, persistence, analytics access, and fallback behavior when live data is degraded.

**Node Labels**

- External Sources
  - Provider Selection
  - Spot Price + Options Chain
- Real-Time Monitoring
  - Background Refresh Services
  - GEX / Greeks Calculation
  - Hawkes + Kalman Enrichment
  - In-Memory TTL Cache
  - FastAPI REST Endpoints
  - WebSocket Stream
  - Analytics & Backtesting Engines
- Historical Persistence / Replay
  - Historical Persistence & Replay Service
  - PostgreSQL 18
  - Market Sessions / GEX Snapshots / Raw Options & IV Surface
- Frontend Consumption
  - Frontend Initial Load
  - WebSocket Hook
  - React Query Cache Sync
  - Dashboard Components
  - Analytics and Backtest Pages
  - REST Polling Fallback
- Resilience Paths
  - Live fetch on cache miss
  - Persisted replay / demo fallback

**Arrow Labels**

- `selected provider`
- `options chain + spot`
- `filtered contracts`
- `GEX snapshot`
- `fresh live snapshot`
- `persist eligible snapshot`
- `REST requests`
- `check cache`
- `analytics or backtest requests`
- `historical and replay queries`
- `provider-backed indicator fetches when needed`
- `summary, IV, technical, backtest payloads`
- `current, strikes, and market payloads`
- `live snapshot`
- `gex_update`
- `sync latest snapshot`
- `cache miss`
- `provider unavailable or low-quality snapshot`
- `replay-eligible session data`
- `persisted or demo response`
- `stream unavailable`
- `REST fallback`

**Caption**

Figure 2 illustrates the runtime flow of data in the 0DTE GEX Monitor. Market data is fetched from an active provider, transformed into GEX snapshots, enriched for advanced analytics, cached for low-latency access, and persisted to PostgreSQL for historical replay and analysis. The frontend prefers live WebSocket delivery and falls back to REST-based polling or replay data when necessary.

**Short Report Explanation**

At runtime, background services continuously fetch spot prices and options-chain data, compute GEX metrics, and enrich the results with Hawkes and Kalman analytics before placing them in the in-memory cache and persisting eligible captures. Client requests are served through REST and WebSocket interfaces, with the dashboard favoring streaming updates and the analytics/backtest pages using REST-based historical and derived data. When live data is unavailable or degraded, the backend falls back to cached, replay, or demo responses, and the frontend can degrade from live streaming to REST polling.

## Validation Notes

- Cache is modeled as **in-memory TTL cache**, not Redis.
- PostgreSQL is modeled as the active persistence layer.
- External market data providers are modeled as **YFinance** and **Tradier** via the provider registry.
- The frontend is modeled as **WebSocket-first with REST fallback**.
- Optional local tooling, notebooks, scripts, and commented-out infrastructure are intentionally excluded from the main figures.
