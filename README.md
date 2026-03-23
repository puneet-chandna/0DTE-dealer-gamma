# 0DTE Dealer Gamma Exposure (GEX) Monitor

Real-time dashboard to monitor Dealer Gamma Exposure for 0DTE (zero-days-to-expiration) options on SPX.

**Goal:** Identify the "Zero Gamma Level" and "Net GEX" to predict intraday volatility regimes.

> Source-available under `PolyForm Noncommercial 1.0.0`. Personal study, research,
> and other noncommercial use are allowed under the license. Commercial use requires
> separate written permission from the copyright holders.

<img
  src="assets/0dte-poster-brutalist.svg"
  alt="0DTE Dealer GEX Monitor brutalist poster"
  style="width: 100%; max-width: 900px; height: auto;"
/>

---

## Table of Contents
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Key Concepts](#key-concepts)
- [Tests](#tests)
- [Documentation](#documentation)
- [Deployment](#deployment)
- [Architecture Rules](#architecture-rules)
- [License and Commercial Use](#license-and-commercial-use)
- [Contributing](#contributing)
- [Security](#security)

## Features

- **Real-time GEX Calculation** - Vectorized Black-Scholes Greeks (1000+ contracts in <1ms)
- **Zero Gamma Level** - Linear interpolation where cumulative GEX crosses zero
- **Market Regime Detection** - Short gamma (🔴) / Long gamma (🟢) / Neutral (🟡)
- **WebSocket Streaming** - Live updates every 5 seconds during market hours
- **Interactive Charts** - Strike-by-strike GEX visualization with Recharts
- **Historical Analysis** - Backtesting and volatility analysis tools
- **Persistent Historical Storage** - Provider-separated Postgres storage for GEX snapshots, IV surfaces, and replay sessions
- **Provider-Based Data Layer** - Configurable market-data providers with a free local-development path

---

## Tech Stack

| Layer         | Technology                                                          |
| ------------- | ------------------------------------------------------------------- |
| **Frontend**  | Next.js 16, TypeScript, TailwindCSS, React Query, Zustand, Recharts |
| **Backend**   | Python 3.13, FastAPI, NumPy (vectorized), SciPy, Pydantic v2        |
| **Database**  | PostgreSQL 18 (local Docker first, cloud-ready schema)              |
| **Real-time** | WebSocket                                                           |
| **Data**      | YFinance (default), Tradier, provider registry architecture         |

---

## Project Structure

```
odte-dealer-gamma/
├── backend/           # Python FastAPI server
│   ├── app/
│   │   ├── api/       # REST & WebSocket endpoints
│   │   ├── core/      # Greeks, GEX calculator, analytics
│   │   ├── models/    # Pydantic schemas
│   │   └── services/  # Background tasks, caching
│   └── tests/         # pytest suite
├── frontend/          # Next.js 16 app
│   └── src/
│       ├── app/       # App Router pages
│       ├── components/# UI & chart components
│       ├── hooks/     # React Query & WebSocket hooks
│       ├── lib/       # API client, utilities
│       └── test/      # Vitest suite
├── docs/              # Documentation
└── docker-compose.yml # PostgreSQL service
```

---

## Quick Start

### Prerequisites

- Python 3.11+ (project uses 3.13)
- Node.js 20+ with pnpm
- Docker & Docker Compose

### 1. Clone and Setup

```bash
git clone https://github.com/<your-org>/odte-dealer-gamma.git
cd odte-dealer-gamma

# Copy the canonical app environment templates
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local

# Optional: if you want to use Tradier instead of the default provider,
# set TRADIER_API_KEY in backend/.env
```

The canonical setup templates are [backend/.env.example](backend/.env.example)
and [frontend/.env.example](frontend/.env.example). The root [.env.example](.env.example)
is a combined reference for local development, but the backend/frontend templates should
be treated as the primary setup docs.

### Environment Variables (minimum)

Backend (`backend/.env`):
- `DATABASE_URL` (Postgres connection string)
- `DATA_PROVIDER` (`yfinance` by default, `tradier` if configured)
- `TRADIER_API_KEY` (only required when using `tradier`)
- `HOST`, `PORT`
- `ENVIRONMENT` (development | staging | production)
- `CORS_ORIGINS` (JSON array string)

Frontend (`frontend/.env.local`):
- `NEXT_PUBLIC_API_URL=http://localhost:8000`
- `NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws`

### 2. Start Database

```bash
docker compose up -d
```

### 3. Run Database Migrations

```bash
cd backend
alembic upgrade head
```

### 4. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

API available at: http://localhost:8000/docs

### 5. Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Dashboard available at: http://localhost:3000

### Local Database Defaults

The repo is now wired for local-first Postgres persistence. If you use the
default `docker-compose.yml`, the backend default `DATABASE_URL` already
matches it:

```txt
postgresql+asyncpg://odte_user:odte_password@localhost:5432/odte_gex
```

That means the normal local flow is:

```bash
docker compose up -d
cd backend
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload
```

---

## Key Concepts

### GEX Formula

Black-Scholes Gamma (Γ) is computed with a dividend yield suitable for SPX (approximately `q ≈ 0.015`).

For each option contract `i`, the raw (magnitude) gamma exposure is:

```txt
raw_gex_i = OI_i × Γ_i × 100 × S²
```

Then the project applies the sign convention by option type:
- Calls contribute **negative** GEX
- Puts contribute **positive** GEX

| Symbol | Description                               |
| ------ | ----------------------------------------- |
| OI     | Open Interest                             |
| Γ      | Black-Scholes Gamma (with dividend yield) |
| 100    | Contract multiplier                       |
| S      | Spot price                                |

### Dealer Positioning

| Customer Action | Dealer Position | GEX Sign     |
| --------------- | --------------- | ------------ |
| Buy Calls       | Short Calls     | **Negative** |
| Buy Puts        | Sell Puts       | **Positive** |

**Net GEX = Σ(signed Put GEX) + Σ(signed Call GEX)** (calls are already signed negative).

### Market Regimes

| Regime         | Net GEX | Implication              |
| -------------- | ------- | ------------------------ |
| 🔴 Short Gamma | < -$1B  | High volatility expected |
| 🟢 Long Gamma  | > +$1B  | Low volatility expected  |
| 🟡 Neutral     | ±$1B    | Normal conditions        |

---

## Tests

```bash
# Backend
cd backend && pytest -v

# Frontend
cd frontend && pnpm test:run

# Type checking
cd backend && mypy app
cd frontend && pnpm tsc --noEmit
```

---

## Documentation

| Document                                | Description                         |
| --------------------------------------- | ----------------------------------- |
| [UNDERSTANDING_GEX_DASHBOARD.md](docs/UNDERSTANDING_GEX_DASHBOARD.md) | Beginner guide for traders and non-quant reviewers |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, data flow diagrams   |
| [API.md](docs/API.md)                   | Complete REST & WebSocket reference |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md)     | Railway + Vercel deployment guide   |
| [PROVIDER_INTEGRATION_PLAN.md](docs/PROVIDER_INTEGRATION_PLAN.md) | Provider architecture and rollout notes |

---

## Deployment

Deploy to Vercel (frontend) and Railway (backend):

```bash
# See detailed guide
docs/DEPLOYMENT.md
```

**Quick Links:**

- Backend: Railway auto-deploys from `backend/` folder
- Frontend: Vercel auto-deploys from `frontend/` folder

---

## Architecture Rules

1. **Vectorization** - All Greeks calculations use NumPy (no Python loops)
2. **State Management** - Server state in React Query, UI state in Zustand
3. **Type Safety** - Strict TypeScript, no `any` types
4. **Timezones** - All SPX data normalized to Eastern Time (ET)

---

## License and Commercial Use

This project is `source-available`, not open source.

- Public license: [PolyForm Noncommercial 1.0.0](LICENSE)
- Ownership notice: [NOTICE](NOTICE)
- Commercial-use policy: [COMMERCIAL-LICENSING.md](COMMERCIAL-LICENSING.md)
- Commercial licensing contact: `puneetchandna21@gmail.com`

The public license allows personal study, research, testing, and other noncommercial uses
allowed by the license text. Commercial use, monetized services, business deployment,
commercial derivatives, and other revenue-generating use cases require a separate written
license from Puneet Chandna and Gunjana Sahoo.

---

## Contributing

Issues and pull requests are welcome. Contributions are submitted under the repository's
license terms, and no separate CLA is required.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow and contribution expectations.

---

## Security

Please report security vulnerabilities privately to `puneetchandna21@gmail.com` rather
than opening a public issue.

See [SECURITY.md](SECURITY.md) for reporting guidance and [SUPPORT.md](SUPPORT.md) for
general support routing.

---

**Built with love for quantitative traders and market structure enthusiasts.**
