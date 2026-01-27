# 0DTE Dealer Gamma Exposure (GEX) Monitor

Real-time dashboard to monitor Dealer Gamma Exposure for 0DTE (zero-days-to-expiration) options on SPX.

**Goal:** Identify the "Zero Gamma Level" and "Net GEX" to predict intraday volatility regimes.

## Tech Stack

| Layer         | Technology                                                          |
| ------------- | ------------------------------------------------------------------- |
| **Frontend**  | Next.js 16, TypeScript, TailwindCSS, React Query, Zustand, Recharts |
| **Backend**   | Python 3.13, FastAPI, NumPy (vectorized), SciPy, Pydantic v2        |
| **Database**  | PostgreSQL 16 (via Docker Compose)                                  |
| **Real-time** | WebSocket                                                           |
| **Data**      | Polygon.io (real-time), CBOE (historical)                           |

## Project Structure

```
odte-dealer-gamma/
├── backend/           # Python FastAPI server
│   ├── app/
│   │   ├── api/       # REST & WebSocket endpoints
│   │   ├── core/      # Greeks, GEX calculator, analytics
│   │   ├── models/    # Pydantic schemas
│   │   └── services/  # Background tasks, caching
│   └── tests/         # pytest tests
├── frontend/          # Next.js 16 app
│   └── src/
│       ├── app/       # App Router pages
│       ├── components/# UI components
│       ├── hooks/     # React Query & WebSocket hooks
│       ├── lib/       # API client, utilities
│       ├── stores/    # Zustand (UI state only)
│       └── types/     # TypeScript interfaces
├── data/              # Raw/processed data storage
├── notebooks/         # Jupyter analysis notebooks
└── docker-compose.yml # PostgreSQL service
```

## Quick Start

### Prerequisites

- Python 3.11+ (project uses 3.13.7)
- Bun (JavaScript runtime)
- pnpm (package manager)
- Docker & Docker Compose

### 1. Clone and Setup Environment

```bash
# Copy environment files
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# Update .env files with your API keys (especially POLYGON_API_KEY)
```

### 2. Start Database

```bash
docker compose up -d
```

### 3. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn app.main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

### 4. Frontend Setup

```bash
cd frontend

# Install dependencies
pnpm install

# Run development server
pnpm dev
```

Dashboard available at: http://localhost:3000

## Development

### Backend Tests

```bash
cd backend
pytest -v
```

### Frontend Tests

```bash
cd frontend
pnpm test
```

### Type Checking

```bash
# Backend
cd backend && mypy app

# Frontend
cd frontend && pnpm tsc --noEmit
```

## Key Concepts

### GEX Formula

```
GEX_i = OI_i × Γ_i × 100 × S²
```

- **OI:** Open Interest
- **Γ:** Black-Scholes Gamma
- **100:** Contract multiplier
- **S:** Spot price

### Dealer Positioning

- **Short Calls:** Customers buy → Dealers sell → Negative GEX
- **Long Puts:** Customers buy → Dealers sell → Positive GEX
- **Net GEX = Σ(Put GEX) - Σ(Call GEX)**

### Zero Gamma Level

The price where Net GEX = 0. This level often acts as intraday support/resistance.

## Architecture Rules

1. **Vectorization:** All Greeks calculations use NumPy - no Python loops
2. **State Management:**
   - Server state: React Query
   - Client state: Zustand (UI only)
3. **Type Safety:** Strict TypeScript, no `any` types
4. **Timezones:** All SPX data normalized to ET

## License

MIT
