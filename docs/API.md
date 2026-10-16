# API Reference

Complete REST API and WebSocket documentation for the 0DTE GEX Backend.

**Base URL:** `http://localhost:8000` (development) or your Railway URL (production)

---

## Authentication

Currently, the API does not require authentication. All endpoints are public.

> **Note:** WebSocket authentication can be enabled via `WS_AUTH_ENABLED=true` environment variable.

---

## GEX Endpoints

### `GET /api/gex/current`

Get the current GEX snapshot. Freshness depends on the selected provider,
cache state, and any saved-data fallback. REST GEX polling is a client setting
(30 seconds by default), and automatic polling can be disabled.

**Parameters:**

| Name       | Type   | Required | Description                     |
| ---------- | ------ | -------- | ------------------------------- |
| `symbol`   | string | No       | Ticker symbol (default: `SPX`)  |
| `provider` | string | No       | Data provider e.g., `yfinance`  |

**Response:**

```json
{
  "timestamp": "2026-01-30T10:30:00-05:00",
  "spot_price": 5950.25,
  "total_call_gex": -2100000000,
  "total_put_gex": 1800000000,
  "net_gex": -300000000,
  "zero_gamma_level": 5945.5,
  "dominant_strike": 5950.0,
  "gex_by_strike": {
    "5900": -150000000,
    "5925": -200000000,
    "5950": 100000000
  },
  "metrics": {
    "regime_code": -1,
    "put_call_ratio": 0.857,
    "gex_imbalance": 0.143,
    "max_abs_gex": 400000000
  }
}
```

---

### `GET /api/gex/historical`

Get historical GEX data for a date range.

**Parameters:**

| Name         | Type   | Required | Description                                            |
| ------------ | ------ | -------- | ------------------------------------------------------ |
| `start_date` | date   | Yes      | Start date (YYYY-MM-DD)                                |
| `end_date`   | date   | Yes      | End date (YYYY-MM-DD)                                  |
| `interval`   | string | No       | Data interval: `5m`, `15m`, `1h`, `1d` (default: `1h`) |
| `symbol`     | string | No       | Ticker symbol (default: `SPX`)                         |
| `provider`   | string | No       | Data provider, e.g., `yfinance`                        |

**Example:** `GET /api/gex/historical?start_date=2026-01-01&end_date=2026-01-30&symbol=SPX`

**Response:**

```json
{
  "start_date": "2026-01-01",
  "end_date": "2026-01-30",
  "interval": "1h",
  "data_points": [
    {
      "timestamp": "2026-01-30T09:30:00-05:00",
      "net_gex": -500000000,
      "zero_gamma_level": 5940.0,
      "spot_price": 5945.0,
      "regime": "short_gamma"
    }
  ]
}
```

---

### `GET /api/gex/strikes`

Get GEX breakdown by strike price.

**Parameters:**

| Name         | Type  | Required | Description                 |
| ------------ | ----- | -------- | --------------------------- |
| `min_strike` | float  | No       | Minimum strike price filter |
| `max_strike` | float  | No       | Maximum strike price filter |
| `symbol`     | string | No       | Ticker symbol (default: `SPX`) |
| `provider`   | string | No       | Data provider, e.g., `yfinance` |

**Response:**

```json
{
  "strikes": [5900, 5925, 5950, 5975, 6000],
  "gex_values": [-150000000, -200000000, 100000000, 300000000, 50000000],
  "spot_price": 5950.25,
  "zero_gamma_level": 5945.5,
  "timestamp": "2026-01-30T10:30:00-05:00"
}
```

---

### `GET /api/gex/regime`

Get current market regime based on GEX.

**Parameters:**

| Name       | Type   | Required | Description                     |
| ---------- | ------ | -------- | ------------------------------- |
| `symbol`   | string | No       | Ticker symbol (default: `SPX`)  |
| `provider` | string | No       | Data provider e.g., `yfinance`  |

**Response:**

```json
{
  "regime": "short_gamma",
  "description": "Negative signed GEX proxy; volatility amplification is a hypothesis.",
  "color": "red",
  "net_gex": -1500000000,
  "net_gex_billions": -1.5,
  "timestamp": "2026-01-30T10:30:00-05:00"
}
```

**Regime Values:**

| Regime        | Condition             | Description              |
| ------------- | --------------------- | ------------------------ |
| `short_gamma` | Net GEX < -$1B        | Negative signed GEX proxy |
| `long_gamma`  | Net GEX > +$1B        | Positive signed GEX proxy  |
| `neutral`     | -$1B ≤ Net GEX ≤ +$1B | GEX proxy near the regime threshold |

---

## Analytics Endpoints

### `GET /api/analytics/gex-volatility`

Analyze relationship between GEX and realized volatility.

**Parameters:**

| Name         | Type | Required | Description             |
| ------------ | ---- | -------- | ----------------------- |
| `start_date` | date | Yes      | Start date for analysis |
| `end_date`   | date | Yes      | End date for analysis   |

**Response:**

```json
{
  "analysis_type": "gex_volatility_relationship",
  "hypothesis": "H1: Negative GEX corresponds to higher realized volatility",
  "result": {
    "t_statistic": 3.45,
    "p_value": 0.001,
    "significant": true
  },
  "short_gamma_volatility": {
    "mean": 0.018,
    "std": 0.005,
    "sample_size": 45
  },
  "long_gamma_volatility": {
    "mean": 0.008,
    "std": 0.003,
    "sample_size": 55
  }
}
```

---

### `GET /api/analytics/backtest`

Both `/api/analytics/backtest` and `/api/analytics/vectorbt-backtest` simulate a
directional long position in the underlying. The legacy strategy name
`volatility_breakout` is accepted as an alias; responses identify
`gex_long_underlying`. This is not a long-volatility options trade.

Required query parameters: `start_date` and `end_date`. Optional parameters:
`provider`, `symbol`, `demo=false`, `entry_threshold=-1e9`, `exit_threshold=0`,
`initial_cash=100000`, `position_size=1` (fraction of available cash),
`fees=0.001`, `slippage=0.001` (fraction per side), `execution_delay_bars=1`.
The legacy route additionally accepts `stop_loss_pct=0.02` and
`take_profit_pct=0.05`. The engine infers the nominal bar interval from the modal
within-session price delta; the shorter mode wins ties. It still requires at
least one within-session delta.

Signals detected at a close fill at a later eligible close in the same session.
Positions can carry overnight; old signals cannot. Stops/targets also fill after
detection, so gaps can exceed a stop. Costs affect both entry and exit; fractional
units are permitted. Marked-to-market equity includes open positions. Entry counts
include open trades; win/loss statistics use closed trades. Undefined risk ratios
and profit factor are JSON `null`.

Missing or off-grid price bars break signal continuity. Pending entries, exits,
stops and targets cannot execute across a break, and pre-gap GEX is not carried
forward until a fresh observation arrives after resumption. Open positions still
mark every observed price change across the gap. Regime comparisons exclude
returns spanning a break; portfolio risk ratios retain nominal-interval
annualization. The separate captured-data research/cost diagnostic still rejects
irregular sessions for qualification.

Non-demo routes return **404** when captured history is insufficient. Explicit demo
mode returns labelled synthetic scenarios. Yahoo SPX history models **SPY** after
undoing the ×10 proxy price scale; direct Tradier SPX index backtests return **422**
and ask for captured SPY history. Costs and fill timing are assumptions, not
validated exchange execution.

Responses include equity values and `equity_timestamps`, closed/open trade counts,
submitted costs/delay, and `provenance`: provider, requested symbol, actual
instrument, proxy flag, captured/synthetic kind, actual coverage, sample count,
calculation versions, timestamp basis and quality limitations. Summary statistics
and GEX/volatility analysis use the same provenance/history boundary. The latter
is descriptive: overlapping backward volatility windows do not establish forward
prediction. See the [offline research command](../scripts/research_gex_volatility.py)
for the held-out study implementation.

---

### `GET /api/analytics/summary-statistics`

Get summary statistics of GEX over time period.

**Parameters:**

| Name         | Type | Required | Description                       |
| ------------ | ---- | -------- | --------------------------------- |
| `start_date` | date | No       | Start date (default: 30 days ago) |
| `end_date`   | date | No       | End date (default: today)         |

**Response:**

```json
{
  "period": {
    "start": "2026-01-01",
    "end": "2026-01-30"
  },
  "net_gex": {
    "mean": -200000000,
    "median": -150000000,
    "std": 500000000,
    "min": -2500000000,
    "max": 1800000000
  },
  "regime_percentages": {
    "short_gamma": 35.0,
    "neutral": 45.0,
    "long_gamma": 20.0
  }
}
```

---

## Data Endpoints

### `GET /api/data/market-status`

Get current market status. Does not require API key.

**Response:**

```json
{
  "is_open": true,
  "status": "open",
  "next_open": null,
  "current_time_et": "2026-01-30T10:30:00-05:00"
}
```

**Status Values:** `open`, `pre_market`, `after_hours`, `closed_weekend`

---

### `GET /api/data/providers`

Get list of all supported dynamic data providers and the active default.

**Response:**

```json
{
  "providers": {
    "yfinance": {
      "has_greeks": false,
      "needs_api_key": false,
      "requires_auth": false,
      "note": "SPX via SPY x10 proxy; Greeks computed locally; Yahoo delayed"
    },
    "tradier": {
      "has_greeks": true,
      "needs_api_key": true,
      "requires_auth": true
    }
  },
  "active_default": "yfinance"
}
```

---

### `GET /api/data/options-chain`

Get current 0DTE options chain. Supports different API sources dynamically.

Default requests use the effective trading session in their cache key. Before
09:30 ET this is the previous weekday; providers may resolve a later available
expiry. An expired resolved default chain cannot be reused after the session
advances. Explicit `expiration` requests retain their separate dated keys.

Unavailable or nonfinite `bid`, `ask`, `mid`, `volume`, `open_interest`, and
`implied_vol` values are returned as `null`. Source-reported zero quotes and
counts remain zero; zero implied volatility is treated as unavailable. Missing
optional values do not discard the chain. Spot and strike must remain finite.

**Parameters:**

| Name         | Type   | Default | Description                            |
| ------------ | ------ | ------- | -------------------------------------- |
| `symbol`     | string | `SPX`   | Underlying symbol                      |
| `expiration` | string | `None`  | Expiration date filter (YYYY-MM-DD)    |
| `provider`   | string | `None`  | Specific data provider to use          |

**Response:**

```json
{
  "underlying": "SPX",
  "spot_price": 5950.25,
  "expiration_date": "2026-01-30",
  "contract_count": 150,
  "contracts": [
    {
      "symbol": "O:SPX260130C05950000",
      "strike": 5950.0,
      "expiration": "2026-01-30",
      "type": "call",
      "bid": 12.5,
      "ask": 13.0,
      "mid": 12.75,
      "open_interest": 5000,
      "volume": 1200,
      "implied_vol": 0.18
    }
  ],
  "timestamp": "2026-01-30T10:30:00-05:00",
  "captured_at": "2026-01-30T10:30:00-05:00",
  "provider": "tradier",
  "is_stale": false,
  "age_seconds": 0,
  "market_status": "open"
}
```

---

### `GET /api/data/spot-price`

Get current spot price based on active provider.

**Parameters:**

| Name       | Type   | Default | Description                     |
| ---------- | ------ | ------- | ------------------------------- |
| `symbol`   | string | `SPX`   | Symbol to get price for         |
| `provider` | string | `None`  | Specific data provider to use   |

**Response:**

```json
{
  "symbol": "SPX",
  "price": 5950.25,
  "timestamp": "2026-01-30T10:30:00-05:00",
  "captured_at": "2026-01-30T10:30:00-05:00",
  "provider": "tradier",
  "is_stale": false,
  "age_seconds": 0,
  "market_status": "open"
}
```

Both raw-data routes expose backend capture age on every response. `timestamp`
and `captured_at` retain the original backend capture time; `age_seconds` is
recomputed when serving the response. Failed fetches may return a cached payload
up to one hour old with `is_stale: true`. `market_status` describes the response
time, including when the cached quote predates the close. Capture age does not
measure vendor quote freshness. Unusable or expired default-chain fallbacks
return HTTP 503.

---

## WebSocket

### `WS /ws/gex-stream`

Repeated GEX snapshots via WebSocket. Delivery cadence does not guarantee
fresh provider quotes.

**Connection:** `ws://localhost:8000/ws/gex-stream`

**Message Format (Server → Client):**

```json
{
  "type": "gex_update",
  "data": {
    "net_gex": -1500000000,
    "zero_gamma_level": 5945.5,
    "spot_price": 5950.25,
    "regime": "short_gamma",
    "total_call_gex": -2100000000,
    "total_put_gex": 1800000000
  },
  "timestamp": "2026-01-30T10:30:00-05:00",
  "is_mock_data": false
}
```

**Message Types:**

| Type            | Description                         |
| --------------- | ----------------------------------- |
| `gex_update`    | Updated GEX calculation             |
| `market_status` | Market open/close notification      |
| `connection`    | Connection established confirmation |

**Update Frequency:** The loop waits up to 5 seconds after each completed
update; provider fetches can make the interval longer. Incoming client messages
can end the wait early. Connections continue receiving updates outside market
hours, with `market_open` reporting the app's market-hours check. Background
refresh tasks separately pause when that check is closed.

---

## Health Check

### `GET /health`

Health check endpoint for monitoring.

**Response:**

```json
{
  "status": "healthy",
  "environment": "production",
  "timestamp": "2026-01-30T10:30:00-05:00",
  "checks": {
    "api": "healthy",
    "data_provider": "yfinance",
    "cache": "healthy"
  }
}
```

---

## Error Responses

All errors return a JSON object:

```json
{
  "detail": "Error message describing the issue"
}
```

**HTTP Status Codes:**

| Code  | Description                                                    |
| ----- | -------------------------------------------------------------- |
| `400` | Bad Request - Invalid parameters, including an unknown explicit provider |
| `422` | Validation Error - Missing or invalid fields                   |
| `503` | Service Unavailable - API key missing or external service down |
| `500` | Internal Server Error                                          |

---

## Rate Limiting

- **Provider Dependent:** The rate limits vary by registered `DataProvider`.
- The backend includes a `RateLimiter` class configured specifically for the active API limits (e.g. YFinance or Tradier tiers).
- Most heavy calculations are cached and intelligently return stale requests or fallbacks if the limit is exceeded. 
