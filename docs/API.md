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

Get current real-time GEX calculation.

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
  "description": "Negative gamma environment - expect amplified market moves",
  "color": "red",
  "net_gex": -1500000000,
  "net_gex_billions": -1.5,
  "timestamp": "2026-01-30T10:30:00-05:00"
}
```

**Regime Values:**

| Regime        | Condition             | Description              |
| ------------- | --------------------- | ------------------------ |
| `short_gamma` | Net GEX < -$1B        | High volatility expected |
| `long_gamma`  | Net GEX > +$1B        | Low volatility expected  |
| `neutral`     | -$1B ≤ Net GEX ≤ +$1B | Normal conditions        |

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

Backtest trading strategy based on GEX signals.

**Parameters:**

| Name              | Type   | Default               | Description             |
| ----------------- | ------ | --------------------- | ----------------------- |
| `start_date`      | date   | -                     | Backtest start date     |
| `end_date`        | date   | -                     | Backtest end date       |
| `strategy`        | string | `volatility_breakout` | Strategy to test        |
| `entry_threshold` | float  | `-1000000000`         | GEX threshold for entry |
| `stop_loss_pct`   | float  | `0.02`                | Stop loss (2%)          |
| `take_profit_pct` | float  | `0.05`                | Take profit (5%)        |

**Response:**

```json
{
  "strategy": "volatility_breakout",
  "period": {
    "start": "2026-01-01",
    "end": "2026-01-30"
  },
  "results": {
    "total_trades": 25,
    "win_rate": 0.64,
    "avg_return": 0.023,
    "sharpe_ratio": 1.85,
    "max_drawdown": -0.08
  }
}
```

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
      "has_greeks": true,
      "needs_api_key": false,
      "requires_auth": false
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
  "timestamp": "2026-01-30T10:30:00-05:00"
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
  "market_status": "open"
}
```

---

## WebSocket

### `WS /ws/gex-stream`

Real-time GEX updates via WebSocket.

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

**Update Frequency:** Every 5 seconds during market hours.

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
| `400` | Bad Request - Invalid parameters                               |
| `422` | Validation Error - Missing or invalid fields                   |
| `503` | Service Unavailable - API key missing or external service down |
| `500` | Internal Server Error                                          |

---

## Rate Limiting

- **Provider Dependent:** The rate limits vary by registered `DataProvider`.
- The backend includes a `RateLimiter` class configured specifically for the active API limits (e.g. YFinance or Tradier tiers).
- Most heavy calculations are cached and intelligently return stale requests or fallbacks if the limit is exceeded. 
