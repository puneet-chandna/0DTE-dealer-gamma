"""0DTE GEX Backend - GEX API Endpoints.

Provides real-time GEX data, strike breakdowns, and market regime detection.
"""

import logging
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import Settings, get_settings
from app.core.analytics import generate_synthetic_gex_data
from app.core import (
    GEXCalculator,
    ProviderRegistry,
    get_data_client,
    get_current_trading_date,
    is_market_open,
)
from app.core.demo_data import get_demo_data_service
from app.models.schemas import (
    GEXByStrike,
    GEXHistorical,
    GEXSnapshot,
    RegimeData,
    MarketStatusResponse,
)
from app.services.cache import get_cache
from app.core.rate_provider import get_rate_provider

logger = logging.getLogger(__name__)

router = APIRouter()

# Eastern Time timezone
ET = ZoneInfo("America/New_York")

# Module-level instances (lazy initialization)
_gex_calculator: Optional[GEXCalculator] = None


def get_gex_calculator() -> GEXCalculator:
    """Get or create the GEX calculator instance."""
    global _gex_calculator
    if _gex_calculator is None:
        _gex_calculator = GEXCalculator(rate_provider=get_rate_provider())
    return _gex_calculator


async def _get_live_gex_snapshot(
    symbol: str, 
    provider: Optional[str] = None
) -> dict:
    """Fetch live data and calculate GEX snapshot.
    
    Args:
        symbol: The underlying symbol (e.g. "SPX").
        provider: Optional data provider name (e.g. "yfinance", "tradier").
    """
    gex_calculator = get_gex_calculator()
    data_client = get_data_client(provider)

    # Log appropriate message
    request_symbol = getattr(data_client, "_get_ticker_symbol", lambda s: s)(symbol)
    logger.info(f"Fetching live options data for {symbol} ({request_symbol}) via {data_client.provider_name}")

    # Fetch filtered data
    options_df, spot_price = await data_client.get_options_chain_for_gex(
        underlying=symbol
    )

    if options_df.empty:
        logger.warning(f"No valid 0DTE options data found for {symbol} (possibly weekend). Falling back to mock data.")
        mock_snapshot = _generate_mock_gex_snapshot(spot_price=spot_price)
        raw = mock_snapshot.model_dump()
        raw["provider"] = f"mock ({data_client.provider_name} empty)"
        return raw

    # Calculate live GEX
    snapshot = gex_calculator.calculate_gex_from_chain(
        options_df=options_df,
        spot_price=spot_price,
        timestamp=datetime.now(ET),
    )

    # Add provider info
    raw = snapshot.model_dump()
    raw["provider"] = data_client.provider_name
    return raw


def _generate_mock_gex_snapshot(spot_price: float = 5950.0) -> GEXSnapshot:
    """Generate a mock GEX snapshot for demo/testing purposes."""
    import numpy as np

    now = datetime.now(ET)

    # Generate realistic mock data
    np.random.seed(int(now.timestamp()) % 10000)
    net_gex = np.random.uniform(-3e9, 2e9)
    call_gex = np.random.uniform(-2e9, -0.5e9)
    put_gex = net_gex - call_gex

    # Generate strike breakdown
    strikes = np.arange(spot_price - 100, spot_price + 105, 5)
    gex_by_strike = {}
    for strike in strikes:
        distance = abs(strike - spot_price)
        magnitude = np.exp(-distance / 50) * np.random.uniform(-5e8, 5e8)
        gex_by_strike[float(strike)] = float(magnitude)

    # Find dominant strike
    dominant_strike = max(gex_by_strike.keys(), key=lambda k: abs(gex_by_strike[k]))

    # Zero gamma level (mock)
    zgl = spot_price + np.random.uniform(-20, 20)

    return GEXSnapshot(
        timestamp=now,
        spot_price=spot_price,
        total_call_gex=call_gex,
        total_put_gex=put_gex,
        net_gex=net_gex,
        zero_gamma_level=zgl,
        gex_by_strike=gex_by_strike,
        dominant_strike=dominant_strike,
        metrics={
            "regime_code": 0.0 if net_gex > 0 else -1.0,
            "gex_imbalance": abs(call_gex) / max(abs(put_gex), 1),
            "is_mock_data": 1.0,
        },
    )


@router.get("/current", response_model=GEXSnapshot)
async def get_current_gex(
    symbol: str = Query("SPX", description="Underlying symbol (default: SPX)"),
    provider: Optional[str] = Query(None, description="Data provider to use (e.g. yfinance, tradier)"),
    demo: bool = Query(False, description="Return deterministic demo data"),
):
    """
    Get the most recent 0DTE GEX calculation.
    """
    if demo:
        return get_demo_data_service().get_current_snapshot(symbol=symbol)

    from app.config import get_settings
    settings = get_settings()
    active_provider = provider or settings.data_provider

    cache = get_cache()
    cache_key = f"gex:current:{symbol}:{active_provider}"
    legacy_key = "gex:current"

    # Try specific provider key first, then fallback to legacy key if it matches default provider
    cached_data = cache.get_if_fresh(cache_key)
    if cached_data is None and active_provider == settings.data_provider:
        cached_data = cache.get_if_fresh(legacy_key)

    if cached_data is not None:
        logger.debug(f"Serving current GEX from cache for {symbol} ({active_provider})")
        # Ensure provider field is on the response if missing
        if hasattr(cached_data, 'model_dump'):
             dump = cached_data.model_dump()
             dump["provider"] = active_provider
             return GEXSnapshot(**dump)
        if isinstance(cached_data, dict):
            cached_data["provider"] = cached_data.get("provider", active_provider)
        return cached_data

    # Not in cache, compute live
    logger.info(f"Cache miss for {cache_key}, computing live GEX")
    try:
        snapshot_dict = await _get_live_gex_snapshot(symbol, provider)
        
        # Save to specific cache
        cache.set(cache_key, snapshot_dict)
        
        # Also save to legacy cache if it's the default provider
        if active_provider == settings.data_provider:
            cache.set(legacy_key, snapshot_dict)
            
        return snapshot_dict
    except Exception as e:
        logger.error(f"Failed to compute live GEX: {e}")
        # Try to return stale cache data
        stale = cache.get(cache_key) or (cache.get(legacy_key) if active_provider == settings.data_provider else None)
        if stale is not None:
            logger.warning("Returning stale cached GEX snapshot")
            if hasattr(stale, 'model_dump'):
                 dump = stale.model_dump()
                 dump["provider"] = active_provider
                 return GEXSnapshot(**dump)
            if isinstance(stale, dict):
                stale["provider"] = stale.get("provider", active_provider)
            return stale
        raise HTTPException(status_code=503, detail=f"Unable to fetch GEX data: {str(e)}")


@router.get("/historical", response_model=GEXHistorical)
async def get_historical_gex(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    interval: str = Query("1h", description="Data interval: 5m, 15m, 1h, 1d"),
    demo: bool = Query(False, description="Return deterministic demo data"),
) -> GEXHistorical:
    """Get historical GEX data for date range.

    Note: Currently returns synthetic data for demonstration.
    """
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")
    if (end_date - start_date).days > 365:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 365 days")

    try:
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        if demo:
            snapshots = get_demo_data_service().get_historical_snapshots(
                symbol="SPX",
                start_date=start_date,
                end_date=end_date,
                interval=interval,
            )
            return GEXHistorical(
                data=snapshots[:100],
                start_date=start_dt,
                end_date=end_dt,
                count=len(snapshots[:100]),
            )

        synthetic_gex = generate_synthetic_gex_data(
            start_date=start_dt,
            end_date=end_dt,
            freq=interval,
        )

        snapshots = []
        for _, row in synthetic_gex.iterrows():
            snapshot = _generate_mock_gex_snapshot(spot_price=5950.0)
            snapshot = GEXSnapshot(
                timestamp=row.name if hasattr(row, 'name') else datetime.now(ET),
                spot_price=snapshot.spot_price,
                total_call_gex=snapshot.total_call_gex,
                total_put_gex=snapshot.total_put_gex,
                net_gex=float(row.get("net_gex", snapshot.net_gex)),
                zero_gamma_level=snapshot.zero_gamma_level,
                gex_by_strike=snapshot.gex_by_strike,
                dominant_strike=snapshot.dominant_strike,
                metrics={"is_synthetic": 1.0},
            )
            snapshots.append(snapshot)

        return GEXHistorical(
            data=snapshots[:100],
            start_date=start_dt,
            end_date=end_dt,
            count=len(snapshots[:100]),
        )

    except Exception as e:
        logger.error(f"Failed to generate historical GEX data: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate historical data: {str(e)}")


@router.get("/strikes", response_model=GEXByStrike)
async def get_gex_by_strikes(
    symbol: str = Query("SPX", description="Underlying symbol (default: SPX)"),
    provider: Optional[str] = Query(None, description="Data provider to use (e.g. yfinance, tradier)"),
    demo: bool = Query(False, description="Return deterministic demo data"),
):
    """Get GEX values separated by strike price."""
    if demo:
        snapshot = get_demo_data_service().get_current_snapshot(symbol=symbol)
        sorted_strikes = sorted(snapshot.gex_by_strike.keys())
        sorted_values = [snapshot.gex_by_strike[strike] for strike in sorted_strikes]
        return GEXByStrike(
            strikes=sorted_strikes,
            gex_values=sorted_values,
            spot_price=snapshot.spot_price,
            zero_gamma_level=snapshot.zero_gamma_level,
        )

    # Try to get from cache first
    cache = get_cache()
    
    from app.config import get_settings
    settings = get_settings()
    active_provider = provider or settings.data_provider
    cache_key = f"gex:current:{symbol}:{active_provider}"
    legacy_key = "gex:current"

    cached_data = cache.get(cache_key)
    if cached_data is None and active_provider == settings.data_provider:
        cached_data = cache.get(legacy_key)

    try:
        if cached_data is None:
            # Need to compute
            snapshot_dict = await _get_live_gex_snapshot(symbol, provider)
        else:
            snapshot_dict = (
                cached_data.model_dump()
                if hasattr(cached_data, "model_dump")
                else cached_data
            )
        # Get current GEX snapshot
        snapshot = GEXSnapshot(**snapshot_dict)

        # Extract strike data
        gex_by_strike = snapshot.gex_by_strike

        # Sort by strike
        sorted_strikes = sorted(gex_by_strike.keys())
        sorted_values = [gex_by_strike[s] for s in sorted_strikes]

        return GEXByStrike(
            strikes=sorted_strikes,
            gex_values=sorted_values,
            spot_price=snapshot.spot_price,
            zero_gamma_level=snapshot.zero_gamma_level,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get GEX by strikes for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get GEX by strikes: {e}")


@router.get("/regime", response_model=RegimeData)
async def get_market_regime(
    symbol: str = Query("SPX", description="Underlying symbol (default: SPX)"),
    provider: Optional[str] = Query(None, description="Data provider to use (e.g. yfinance, tradier)"),
    demo: bool = Query(False, description="Return deterministic demo data"),
):
    """Get current market regime based on GEX positioning."""
    if demo:
        snapshot = get_demo_data_service().get_current_snapshot(symbol=symbol)
        regime, description, color = get_gex_calculator().determine_regime(snapshot.net_gex)
        return RegimeData(
            regime=regime,
            description=description,
            color=color,
            net_gex=snapshot.net_gex,
            net_gex_billions=snapshot.net_gex / 1e9,
            timestamp=snapshot.timestamp,
        )

    cache = get_cache()
    
    from app.config import get_settings
    settings = get_settings()
    active_provider = provider or settings.data_provider
    cache_key = f"gex:current:{symbol}:{active_provider}"
    legacy_key = "gex:current"

    cached_data = cache.get_if_fresh(cache_key)
    if cached_data is None and active_provider == settings.data_provider:
        cached_data = cache.get_if_fresh(legacy_key)

    try:
        if cached_data is None:
            snapshot_dict = await _get_live_gex_snapshot(symbol, provider)
        else:
            snapshot_dict = (
                cached_data.model_dump()
                if hasattr(cached_data, "model_dump")
                else cached_data
            )
        
        snapshot = GEXSnapshot(**snapshot_dict)

        # Determine regime
        gex_calculator = get_gex_calculator()
        regime, description, color = gex_calculator.determine_regime(snapshot.net_gex)

        return RegimeData(
            regime=regime,
            description=description,
            color=color,
            net_gex=snapshot.net_gex,
            net_gex_billions=snapshot.net_gex / 1e9,
            timestamp=snapshot.timestamp,
        )
    except Exception as e:
        logger.error(f"Failed to get regime for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to determine regime: {e}")
