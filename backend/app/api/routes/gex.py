"""0DTE GEX Backend - GEX API Endpoints.

Provides real-time GEX data, strike breakdowns, and market regime detection.
"""

import asyncio
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
from app.services.historical_data import get_historical_data_service
from app.core.rate_provider import get_rate_provider

logger = logging.getLogger(__name__)

router = APIRouter()

# Eastern Time timezone
ET = ZoneInfo("America/New_York")
LIVE_FETCH_TIMEOUT_SECONDS = 4

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


async def _get_replay_snapshot(
    symbol: str,
    provider: str,
) -> Optional[GEXSnapshot]:
    """Return the latest stored snapshot for replay/demo mode when available."""
    today_et = datetime.now(ET).date()
    snapshots = await get_historical_data_service().get_historical_snapshots(
        provider=provider,
        symbol=symbol,
        start_date=today_et,
        end_date=today_et,
        interval="5s",
        prefer_replay=True,
    )
    if not snapshots:
        return None
    return snapshots[-1]


async def _get_latest_persisted_snapshot(
    *,
    symbol: str,
    provider: str,
    prefer_replay: bool = False,
) -> Optional[GEXSnapshot]:
    """Return the latest persisted snapshot when the live path is unavailable."""
    return await get_historical_data_service().get_latest_snapshot(
        provider=provider,
        symbol=symbol,
        prefer_replay=prefer_replay,
    )


def _serialize_persisted_snapshot(snapshot: GEXSnapshot, *, provider: str) -> dict:
    """Mark persisted fallback payloads so the frontend can distinguish them."""
    payload = snapshot.model_dump()
    payload["provider"] = provider
    payload.setdefault("metrics", {})
    payload["metrics"]["is_persisted_fallback"] = 1.0
    return payload


def _snapshot_is_mock(snapshot_payload: dict) -> bool:
    """Detect generated fallback snapshots masquerading as live data."""
    metrics = snapshot_payload.get("metrics") or {}
    provider = str(snapshot_payload.get("provider", "")).lower()
    return bool(metrics.get("is_mock_data") == 1.0 or provider.startswith("mock"))


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
    settings = get_settings()
    active_provider = ProviderRegistry.resolve_provider_name(
        provider,
        default_provider=settings.data_provider,
    )

    if demo:
        replay_snapshot = await _get_replay_snapshot(symbol=symbol, provider=active_provider)
        if replay_snapshot is not None:
            replay_payload = replay_snapshot.model_dump()
            replay_payload["provider"] = active_provider
            replay_payload.setdefault("metrics", {})
            replay_payload["metrics"]["is_replay_data"] = 1.0
            return replay_payload
        demo_snapshot = get_demo_data_service().get_current_snapshot(symbol=symbol)
        replay_payload = demo_snapshot.model_dump()
        replay_payload["provider"] = active_provider
        return replay_payload

    default_provider = ProviderRegistry.resolve_provider_name(
        default_provider=settings.data_provider,
    )

    cache = get_cache()
    cache_key = f"gex:current:{symbol}:{active_provider}"
    legacy_key = (
        f"gex:current:{symbol}"
        if active_provider == default_provider
        else None
    )

    # Try specific provider key first, then fallback to legacy key if it matches default provider
    cached_data = cache.get_if_fresh(cache_key)
    if cached_data is None and legacy_key is not None:
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
        snapshot_dict = await asyncio.wait_for(
            _get_live_gex_snapshot(symbol, provider),
            timeout=LIVE_FETCH_TIMEOUT_SECONDS,
        )
        if _snapshot_is_mock(snapshot_dict):
            persisted_snapshot = await _get_latest_persisted_snapshot(
                symbol=symbol,
                provider=active_provider,
            )
            if persisted_snapshot is not None:
                snapshot_dict = _serialize_persisted_snapshot(
                    persisted_snapshot,
                    provider=active_provider,
                )
        
        # Save to specific cache
        cache.set(cache_key, snapshot_dict)

        # Also save to legacy cache if it's the default provider
        if legacy_key is not None:
            cache.set(legacy_key, snapshot_dict)
            
        return snapshot_dict
    except Exception as e:
        logger.error(f"Failed to compute live GEX: {e}")
        # Try to return stale cache data
        stale = cache.get(cache_key) or (cache.get(legacy_key) if legacy_key is not None else None)
        if stale is not None:
            logger.warning("Returning stale cached GEX snapshot")
            if hasattr(stale, 'model_dump'):
                 dump = stale.model_dump()
                 dump["provider"] = active_provider
                 return GEXSnapshot(**dump)
            if isinstance(stale, dict):
                stale["provider"] = stale.get("provider", active_provider)
            return stale

        persisted_snapshot = await _get_latest_persisted_snapshot(
            symbol=symbol,
            provider=active_provider,
        )
        if persisted_snapshot is not None:
            logger.warning(
                "Returning latest persisted GEX snapshot for %s (%s) after live fetch failure",
                symbol,
                active_provider,
            )
            return _serialize_persisted_snapshot(
                persisted_snapshot,
                provider=active_provider,
            )
        raise HTTPException(status_code=503, detail=f"Unable to fetch GEX data: {str(e)}")


@router.get("/historical", response_model=GEXHistorical)
async def get_historical_gex(
    symbol: str = Query("SPX", description="Underlying symbol (default: SPX)"),
    provider: Optional[str] = Query(None, description="Data provider to use (e.g. yfinance, tradier)"),
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    interval: str = Query("1h", description="Data interval: 5s, 1m, 5m, 15m, 1h, 1d, 1wk"),
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
        settings = get_settings()
        active_provider = ProviderRegistry.resolve_provider_name(
            provider,
            default_provider=settings.data_provider,
        )

        persisted_snapshots = await get_historical_data_service().get_historical_snapshots(
            provider=active_provider,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            interval=interval,
            prefer_replay=demo,
        )
        if persisted_snapshots:
            return GEXHistorical(
                data=persisted_snapshots,
                start_date=start_dt,
                end_date=end_dt,
                count=len(persisted_snapshots),
            )

        if demo:
            snapshots = get_demo_data_service().get_historical_snapshots(
                symbol=symbol,
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

        return GEXHistorical(
            data=[],
            start_date=start_dt,
            end_date=end_dt,
            count=0,
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
        settings = get_settings()
        active_provider = ProviderRegistry.resolve_provider_name(
            provider,
            default_provider=settings.data_provider,
        )
        snapshot = await _get_replay_snapshot(symbol=symbol, provider=active_provider)
        if snapshot is None:
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
    
    settings = get_settings()
    active_provider = ProviderRegistry.resolve_provider_name(
        provider,
        default_provider=settings.data_provider,
    )
    default_provider = ProviderRegistry.resolve_provider_name(
        default_provider=settings.data_provider,
    )
    cache_key = f"gex:current:{symbol}:{active_provider}"
    legacy_key = (
        f"gex:current:{symbol}"
        if active_provider == default_provider
        else None
    )

    cached_data = cache.get_if_fresh(cache_key)
    if cached_data is None and legacy_key is not None:
        cached_data = cache.get_if_fresh(legacy_key)

    try:
        if cached_data is None:
            # Need to compute
            snapshot_dict = await asyncio.wait_for(
                _get_live_gex_snapshot(symbol, provider),
                timeout=LIVE_FETCH_TIMEOUT_SECONDS,
            )
            if _snapshot_is_mock(snapshot_dict):
                persisted_snapshot = await _get_latest_persisted_snapshot(
                    symbol=symbol,
                    provider=active_provider,
                )
                if persisted_snapshot is not None:
                    snapshot_dict = _serialize_persisted_snapshot(
                        persisted_snapshot,
                        provider=active_provider,
                    )
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
        stale_data = cache.get(cache_key)
        if stale_data is None and legacy_key is not None:
            stale_data = cache.get(legacy_key)

        if stale_data is not None:
            logger.warning("Returning stale cached GEX strikes for %s (%s)", symbol, active_provider)
            snapshot_dict = (
                stale_data.model_dump()
                if hasattr(stale_data, "model_dump")
                else stale_data
            )
            snapshot = GEXSnapshot(**snapshot_dict)
            sorted_strikes = sorted(snapshot.gex_by_strike.keys())
            sorted_values = [snapshot.gex_by_strike[s] for s in sorted_strikes]
            return GEXByStrike(
                strikes=sorted_strikes,
                gex_values=sorted_values,
                spot_price=snapshot.spot_price,
                zero_gamma_level=snapshot.zero_gamma_level,
            )

        persisted_snapshot = await _get_latest_persisted_snapshot(
            symbol=symbol,
            provider=active_provider,
        )
        if persisted_snapshot is not None:
            logger.warning(
                "Returning latest persisted strike breakdown for %s (%s)",
                symbol,
                active_provider,
            )
            sorted_strikes = sorted(persisted_snapshot.gex_by_strike.keys())
            sorted_values = [persisted_snapshot.gex_by_strike[s] for s in sorted_strikes]
            return GEXByStrike(
                strikes=sorted_strikes,
                gex_values=sorted_values,
                spot_price=persisted_snapshot.spot_price,
                zero_gamma_level=persisted_snapshot.zero_gamma_level,
            )

        raise HTTPException(status_code=503, detail=f"Failed to get GEX by strikes: {e}")


@router.get("/regime", response_model=RegimeData)
async def get_market_regime(
    symbol: str = Query("SPX", description="Underlying symbol (default: SPX)"),
    provider: Optional[str] = Query(None, description="Data provider to use (e.g. yfinance, tradier)"),
    demo: bool = Query(False, description="Return deterministic demo data"),
):
    """Get current market regime based on GEX positioning."""
    if demo:
        settings = get_settings()
        active_provider = ProviderRegistry.resolve_provider_name(
            provider,
            default_provider=settings.data_provider,
        )
        snapshot = await _get_replay_snapshot(symbol=symbol, provider=active_provider)
        if snapshot is None:
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
    
    settings = get_settings()
    active_provider = ProviderRegistry.resolve_provider_name(
        provider,
        default_provider=settings.data_provider,
    )
    default_provider = ProviderRegistry.resolve_provider_name(
        default_provider=settings.data_provider,
    )
    cache_key = f"gex:current:{symbol}:{active_provider}"
    legacy_key = (
        f"gex:current:{symbol}"
        if active_provider == default_provider
        else None
    )

    cached_data = cache.get_if_fresh(cache_key)
    if cached_data is None and legacy_key is not None:
        cached_data = cache.get_if_fresh(legacy_key)

    try:
        if cached_data is None:
            snapshot_dict = await asyncio.wait_for(
                _get_live_gex_snapshot(symbol, provider),
                timeout=LIVE_FETCH_TIMEOUT_SECONDS,
            )
            if _snapshot_is_mock(snapshot_dict):
                persisted_snapshot = await _get_latest_persisted_snapshot(
                    symbol=symbol,
                    provider=active_provider,
                )
                if persisted_snapshot is not None:
                    snapshot_dict = _serialize_persisted_snapshot(
                        persisted_snapshot,
                        provider=active_provider,
                    )
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
        stale_data = cache.get(cache_key)
        if stale_data is None and legacy_key is not None:
            stale_data = cache.get(legacy_key)

        if stale_data is not None:
            logger.warning(
                "Returning stale cached regime snapshot for %s (%s)",
                symbol,
                active_provider,
            )
            snapshot_dict = (
                stale_data.model_dump()
                if hasattr(stale_data, "model_dump")
                else stale_data
            )
            stale_snapshot = GEXSnapshot(**snapshot_dict)
            regime, description, color = get_gex_calculator().determine_regime(
                stale_snapshot.net_gex
            )
            return RegimeData(
                regime=regime,
                description=description,
                color=color,
                net_gex=stale_snapshot.net_gex,
                net_gex_billions=stale_snapshot.net_gex / 1e9,
                timestamp=stale_snapshot.timestamp,
            )

        persisted_snapshot = await _get_latest_persisted_snapshot(
            symbol=symbol,
            provider=active_provider,
        )
        if persisted_snapshot is not None:
            regime, description, color = get_gex_calculator().determine_regime(
                persisted_snapshot.net_gex
            )
            return RegimeData(
                regime=regime,
                description=description,
                color=color,
                net_gex=persisted_snapshot.net_gex,
                net_gex_billions=persisted_snapshot.net_gex / 1e9,
                timestamp=persisted_snapshot.timestamp,
            )
        raise HTTPException(status_code=503, detail=f"Failed to determine regime: {e}")
