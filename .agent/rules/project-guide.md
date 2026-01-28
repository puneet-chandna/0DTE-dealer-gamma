---
trigger: model_decision
description: this rule should be almost aplied always other then when working with frontend design.
---

# 0DTE Dealer GEX - Cursor Rules

## Quick Reference (See master_plan.md for full details)

### Immutable Math Rules

- **GEX Sign Convention**: Calls = NEGATIVE, Puts = POSITIVE dealer exposure
- **Black-Scholes**: MUST include dividend yield `q ≈ 0.015` for SPX
- **Zero Gamma**: Linear interpolation where cumulative GEX crosses zero
- **Formula**: `raw_gex = OI × Γ × 100 × S²` → apply sign → sum all

### Backend Rules (Python 3.13 / FastAPI)

- **NEVER** use Python loops for Greeks — NumPy vectorization only
- **ALWAYS** guard divisions: `T = np.maximum(T, 1e-10)` and `sigma = np.maximum(sigma, 1e-10)`
- **ALWAYS** clean NaN: `np.nan_to_num(result, nan=0.0)`
- **ALWAYS** use Pydantic v2 for all API schemas
- **ALWAYS** use `ZoneInfo('America/New_York')` for timestamps

### Frontend Rules (Next.js 16 / TypeScript)

- **Server state**: React Query ONLY (`@tanstack/react-query`)
- **Client state**: Zustand ONLY (UI settings like theme, thresholds)
- **NEVER** store API responses in Zustand
- **ALWAYS** memoize chart components with `React.memo()`
- **ALWAYS** throttle chart updates (max 1 render per 200ms)
- **ALWAYS** wrap charts in `ChartErrorBoundary`

### Data Filtering Rules

- **Timestamps**: Normalize ALL to ET (America/New_York)
- **0DTE Filter**: `expiration_date == datetime.now(ET).date()`
- **Strike Filter**: Keep only strikes within ±20% of spot price
- **OI Filter**: Skip contracts with `OI == 0`
- **IV Filter**: Skip if `IV > 500%` or `IV < 1%`

### API & Rate Limiting

- **Polygon.io free tier**: 5 requests/minute — use RateLimiter class
- **Cache TTL**: 5s for GEX, 1s for spot price
- **Invalidate cache**: When spot moves >1%

### For detailed implementation, refer to: `master_plan.md`
