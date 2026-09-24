<img
  src="assets/0dte-poster-brutalist.svg"
  alt="0DTE Dealer GEX Monitor brutalist poster"
  style="width: 100%; max-width: 900px; height: auto;"
/>
# 0DTE Dealer Gamma Exposure (GEX) Monitor

Near-real-time (5s poll, provider-delayed) dashboard to monitor Dealer Gamma Exposure for 0DTE (zero-days-to-expiration) options on SPX.

**Goal:** Identify the "Zero Gamma Level" and "Net GEX" to predict intraday volatility regimes.

> Source-available under `PolyForm Noncommercial 1.0.0`. Personal study, research,
> and other noncommercial use are allowed under the license. Commercial use requires
> separate written permission from the copyright holders.



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

- **Near-real-time GEX Calculation** - Vectorized Black-Scholes Greeks (~0.5ms p50 for 1000 contracts, vectorized NumPy — see `docs/BENCHMARKS.md`)
- **Zero Gamma Level** - Linear interpolation where cumulative GEX crosses zero
- **Market Regime Detection** - Short gamma (🔴) / Long gamma (🟢) / Neutral (🟡)
- **WebSocket Streaming** - Live updates every 5 seconds during market hours
- **Interactive Charts** - Strike-by-strike GEX visualization with Recharts
- **Historical Analysis** - Backtesting and volatility analysis tools
- **Persistent Historical Storage** - Provider-separated SQLite/Postgres storage for GEX snapshots, IV surfaces, and replay sessions
- **Provider-Based Data Layer** - Configurable market-data providers with a free local-development path

---

## Tech Stack

| Layer         | Technology                                                          |
| ------------- | ------------------------------------------------------------------- |
| **Frontend**  | Next.js 16, TypeScript, TailwindCSS, React Query, Zustand, Recharts |
| **Backend**   | Python 3.13, FastAPI, NumPy (vectorized), SciPy, Pydantic v2        |
| **Database**  | SQLite (local default, zero-setup) / PostgreSQL 18 (opt-in, Docker or cloud) |
| **Near-real-time (5s poll, provider-delayed)** | WebSocket                                                           |
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
- Docker & Docker Compose (optional — only needed for the Postgres path)

### 1. Clone and Bootstrap Env

```bash
git clone https://github.com/<your-org>/odte-dealer-gamma.git
cd odte-dealer-gamma

# Idempotent: copies the templates into place ONLY if missing
# (existing backend/.env / frontend/.env.local are never overwritten).
./scripts/setup_env.sh --sqlite            # default: zero-setup SQLite
# ./scripts/setup_env.sh --postgres-local  # project-owned Postgres on 127.0.0.1:55432
# ./scripts/setup_env.sh --postgres-docker # Docker Compose Postgres on localhost:5432

# Optional: if you want to use Tradier instead of the default provider,
# set TRADIER_API_KEY in backend/.env
```

The defaults run on SQLite — no Docker or database setup required.
`backend/.env` ships with `DATABASE_URL=sqlite+aiosqlite:///./odte_gex.db`
(a file created inside `backend/` on first run). To use Postgres instead,
set `DATABASE_URL` to a Postgres connection string (see
[Local Database Defaults](#local-database-defaults)).

`setup_env.sh` also validates `DATABASE_URL` plus `NEXT_PUBLIC_API_URL` /
`NEXT_PUBLIC_WS_URL` (fails fast with a clear message) and removes the stale
`POLYGON_API_KEY` entry from the root `.env` if present.

The canonical setup templates are [backend/.env.example](backend/.env.example)
and [frontend/.env.example](frontend/.env.example). The root [.env.example](.env.example)
is a combined reference for local development, but the backend/frontend templates should
be treated as the primary setup docs.

### Environment Variables (minimum)

Backend (`backend/.env`):
- `DATABASE_URL` (SQLite by default; set a Postgres connection string to opt in)
- `DATA_PROVIDER` (`yfinance` by default, `tradier` if configured)
- `TRADIER_API_KEY` (only required when using `tradier`)
- `HOST`, `PORT`
- `ENVIRONMENT` (development | staging | production)
- `CORS_ORIGINS` (JSON array string)

Frontend (`frontend/.env.local`):
- `NEXT_PUBLIC_API_URL=http://localhost:8000`
- `NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws`

### 2. Run Everything (SQLite Default — No Docker)

```bash
./scripts/dev.sh
```

This single-process runner applies migrations (`alembic upgrade head`), then
starts the backend (`uvicorn app.main:app --reload`) and the frontend
(`pnpm dev`) as one child process group:

- SQLite file: `backend/odte_gex.db` (created on first run). No database
  terminal, no TCP wait, no Docker.
- One PID file: `.local-run/dev.pid`. One log file: `.local-run/dev.log`
  with `[backend]` / `[frontend]` prefixes per line.
- Stop everything with `Ctrl+C` (INT/TERM shuts down backend, frontend, and
  their descendants — no orphans).
- API: http://localhost:8000/docs — Dashboard: http://localhost:3000

### 3. Postgres Opt-In (Optional)

Only if you want Postgres instead of SQLite. Pick one server, point
`DATABASE_URL` at it (via `./scripts/setup_env.sh --postgres-local` or
`--postgres-docker`), then run `./scripts/dev.sh` as usual — the runner
preserves the Postgres flow (ensures the local server / waits for the
external one) before migrating and starting the services.

```txt
DATABASE_URL=postgresql+asyncpg://odte_user:your_secure_password_here@localhost:5432/odte_gex
DATABASE_URL=postgresql+asyncpg://odte_user:odte_password@127.0.0.1:55432/odte_gex
```

```bash
docker compose up -d
# ... or, without Docker: ./scripts/setup_local_postgres.sh
./scripts/dev.sh
```

### Appendix A. Legacy Multi-Terminal Startup

`./scripts/dev.sh` (above) is the recommended runner. The multi-terminal
launchers remain as legacy shims (no deletion) and still support the SQLite
default (no DB terminal for `sqlite:` URLs) and the Postgres flow. You can
launch the whole app with one command and get separate terminals for:
- database logs
- backend logs
- frontend logs

Linux / Git Bash / WSL:

```bash
./scripts/start_app.sh
```

Linux / Git Bash / WSL stop command:

```bash
./scripts/stop_app.sh
```

Native Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_app.ps1
```

Behavior:
- The DB gets its own visible terminal so you can watch logs and stop it with `Ctrl+C`.
- The backend gets its own terminal and runs `uvicorn --reload`.
- The frontend gets its own terminal and runs `pnpm dev`.
- No `tmux` is required.
- `stop_app.sh` stops frontend first, backend second, and local PostgreSQL last.
- The local DB is stopped through `pg_ctl`, not by force-killing database processes.

Notes:
- `start_app.sh` supports the local project-owned Postgres fallback on port `55432`.
- `start_app.ps1` is guidance-first on native Windows. It recommends WSL or Git Bash for the repo-standard local PostgreSQL flow.
- If PostgreSQL is not installed or not reachable on native Windows, `start_app.ps1` stops and shows colored setup guidance instead of trying to install it automatically.
- If you stop the backend or frontend terminals, the DB can keep running until you stop the DB terminal separately.

### Appendix B. Manual Setup (No Runner)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

API available at: http://localhost:8000/docs

```bash
cd frontend
pnpm install
pnpm dev
```

Dashboard available at: http://localhost:3000

### Local Database Defaults

The repo defaults to SQLite for zero-setup local runs. With no `DATABASE_URL`
override, the backend uses:

```txt
sqlite+aiosqlite:///./odte_gex.db
```

(a file created inside `backend/` on first run, i.e. `backend/odte_gex.db`).
That means the normal local flow (`./scripts/setup_env.sh --sqlite`, then
`./scripts/dev.sh`) needs no Docker and no DB terminal at all.

To use Postgres instead (Docker or the local fallback), see
[Postgres Opt-In](#3-postgres-opt-in-optional) for the `DATABASE_URL` values.

---

## Key Concepts

### GEX Formula

Black-Scholes Gamma (Γ) is computed with a dividend yield suitable for SPX (approximately `q ≈ 0.015`).

For each option contract `i`, the raw (magnitude) gamma exposure is:

```txt
raw_gex_i = OI_i × Γ_i × 100 × S²
```

The trader-facing Net GEX values in this project are normalized to a 1% underlying
move and signed by option type:

```txt
gex_i = raw_gex_i × 0.01
```

- Calls contribute **positive** GEX
- Puts contribute **negative** GEX

| Symbol | Description                               |
| ------ | ----------------------------------------- |
| OI     | Open Interest                             |
| Γ      | Black-Scholes Gamma (with dividend yield) |
| 100    | Contract multiplier                       |
| S      | Spot price                                |
| 0.01   | Convert to dollar gamma per 1% move       |

### Dealer Positioning

| Option Type | GEX Sign     |
| ----------- | ------------ |
| Calls       | **Positive** |
| Puts        | **Negative** |

**Net GEX = Σ(Call GEX) + Σ(Put GEX)**.

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
cd backend && pytest -q

# Frontend
cd frontend && pnpm test:run

# Type checking
cd backend && mypy app
cd frontend && pnpm tsc --noEmit
```

Both default test commands now print a coverage summary at the end of the run.

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
