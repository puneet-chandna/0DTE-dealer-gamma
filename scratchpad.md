# Tradier API Documentation Extraction Task

## Progress Checklist
- [x] Extract details from `get-quotes` (https://documentation.tradier.com/brokerage-api/markets/get-quotes)
- [x] Extract details from `get-options-expirations` (https://documentation.tradier.com/brokerage-api/markets/get-options-expirations)
- [x] Extract details from `get-options-strikes` (https://documentation.tradier.com/brokerage-api/markets/get-options-strikes)

## Extracted Details

### Get Quotes
- **HTTP Method:** GET
- **URL Path:** `/v1/markets/quotes`
- **Query Parameters:**
    - `symbols` (string, required): A comma-separated list of symbols.
    - `greeks` (boolean, optional): Defaults to false. Include greek calculations for options.
    - `includeLotSize` (boolean, optional): Defaults to false. Include lot size information.
- **JSON Response Example:**
```json
{
  "quotes": {
    "quote": {
      "symbol": "AAPL",
      "description": "Apple Inc",
      "exch": "Q",
      "type": "stock",
      "last": 273.47,
      "change": -1.78,
      "volume": 47994892,
      "open": 275,
      "high": 275.73,
      "low": 271.7,
      "close": 273.47,
      "bid": 273.53,
      "ask": 273.59,
      "change_percentage": -0.65,
      "average_volume": 50967638,
      "last_volume": 0,
      "trade_date": 1762982100011,
      "prevclose": 275.25,
      "week_52_high": 277.32,
      "week_52_low": 169.2101,
      "bidsize": 100,
      "bidexch": "Z",
      "bid_date": 1762982138000,
      "asksize": 200,
      "askexch": "Q",
      "ask_date": 1762982257000,
      "root_symbols": "AAPL",
      "lot_size": 100
    }
  }
}
```
- **Notes:** The `quote` field can be an object (for a single symbol) or an array (for multiple symbols). Authentication is via Bearer token in the header.

### Get Options Expirations
- **HTTP Method:** GET
- **URL Path:** `/v1/markets/options/expirations`
- **Query Parameters:**
    - `symbol` (string, required): The underlying security symbol.
    - `includeAllRoots` (boolean, required): Defaults to false. Include all option roots.
    - `strikes` (boolean, optional): Defaults to false. Include strikes in response.
    - `contractSize` (boolean, optional): Defaults to false. Include contract size in response.
    - `expirationType` (boolean, optional): Defaults to false. Include expiration type in response.
- **JSON Response Example:**
```json
{
  "expirations": {
    "date": [
      "2021-02-05",
      "2021-02-12",
      "2021-02-19",
      "2021-02-26",
      "2021-03-19",
      "2021-04-16",
      "2021-06-18",
      "2021-09-17",
      "2022-01-21",
      "2022-06-17",
      "2023-01-20"
    ]
  }
}
```

### Get Options Strikes
- **HTTP Method:** GET
- **URL Path:** `/v1/markets/options/strikes`
- **Query Parameters:**
    - `symbol` (string, required): The underlying security symbol.
    - `expiration` (date, required): The expiration date (YYYY-MM-DD).
- **JSON Response Example:**
```json
{
  "strikes": {
    "strike": [
      115,
      120,
      125,
      130,
      135
    ]
  }
}
```
