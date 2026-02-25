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
from app.core.data_acquisition import get_market_status, is_market_open
from app.core.yfinance_provider import YFinanceClient
from app.core.gex_calculator import GEXCalculator
from app.models.schemas import (
    GEXByStrike,
    GEXHistorical,
    GEXSnapshot,
    RegimeData,
)
from app.services.cache import get_cache

logger = logging.getLogger(__name__)

router = APIRouter()

# Eastern Time timezone
ET = ZoneInfo("America/New_York")

# Module-level instances (lazy initialization)
_gex_calculator: Optional[GEXCalculator] = None
_data_client: Optional[YFinanceClient] = None


from app.core.rate_provider import get_rate_provider


def get_gex_calculator() -> GEXCalculator:
    """Get or create the GEX calculator instance."""
    global _gex_calculator
    if _gex_calculator is None:
        _gex_calculator = GEXCalculator(rate_provider=get_rate_provider())
    return _gex_calculator


def get_data_client() -> YFinanceClient:
    """Get or create the YFinance data client instance.

    Uses Yahoo Finance via yfinance library (free, no API key required).
    Uses SPY as proxy for SPX options data.
    """
    global _data_client
    if _data_client is None:
        _data_client = YFinanceClient(
            calls_per_minute=10,
            use_spy_as_proxy=True,
        )
    return _data_client


async def _get_live_gex_snapshot(
    data_client: YFinanceClient,
    gex_calculator: GEXCalculator,
) -> GEXSnapshot:
    """Fetch live options data and compute GEX snapshot.

    Args:
        data_client: YFinance data client.
        gex_calculator: GEX computation engine.

    Returns:
        Computed GEX snapshot.

    Raises:
        HTTPException: If data fetch or calculation fails.
    """
    cache = get_cache()

    # Check cache first
    cached = cache.get_if_fresh("gex:current")
    if cached is not None:
        logger.debug("Returning cached GEX snapshot")
        return cached

    try:
        # Fetch options chain and spot price via YFinance (uses SPY as proxy)
        options_df, spot_price = await data_client.get_options_chain_for_gex("SPY")

        # Update spot price and check for cache invalidation
        cache.update_spot_price(spot_price)

        # Calculate GEX from chain
        timestamp = datetime.now(ET)
        snapshot = gex_calculator.calculate_gex_from_chain(
            options_df=options_df,
            spot_price=spot_price,
            timestamp=timestamp,
        )

        # Cache the result
        cache.set("gex:current", snapshot)
        logger.info(
            f"GEX computed: net_gex={snapshot.net_gex/1e9:.3f}B, "
            f"spot={snapshot.spot_price:.2f}, "
            f"zgl={snapshot.zero_gamma_level:.2f}"
        )

        return snapshot

    except Exception as e:
        logger.error(f"Failed to compute live GEX: {e}")

        # Try to return stale cache data
        stale = cache.get("gex:current")
        if stale is not None:
            logger.warning("Returning stale cached GEX snapshot")
            return stale

        raise HTTPException(
            status_code=503,
            detail=f"Unable to fetch GEX data: {str(e)}",
        )


def _generate_mock_gex_snapshot(spot_price: float = 5950.0) -> GEXSnapshot:
    """Generate a mock GEX snapshot for demo/testing purposes.

    Args:
        spot_price: Simulated spot price.

    Returns:
        Mock GEX snapshot with realistic values.
    """
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
    settings: Settings = Depends(get_settings),
) -> GEXSnapshot:
    """Get current real-time GEX calculation.

    Returns the latest GEX snapshot including net GEX, zero gamma level,
    and breakdown by strike.

    Uses YFinance (free Yahoo Finance data) - no API key required.
    Uses SPY as proxy for SPX options.
    """
    gex_calculator = get_gex_calculator()
    data_client = get_data_client()

    try:
        return await _get_live_gex_snapshot(data_client, gex_calculator)
    finally:
        pass  # YFinanceClient.close() is a no-op


@router.get("/historical", response_model=GEXHistorical)
async def get_historical_gex(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    interval: str = Query("1h", description="Data interval: 5m, 15m, 1h, 1d"),
) -> GEXHistorical:
    """Get historical GEX data for date range.

    Note: Currently returns synthetic data for demonstration.
    Database storage will be implemented in a future phase.
    """
    # Validate date range
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be before or equal to end_date",
        )

    if (end_date - start_date).days > 365:
        raise HTTPException(
            status_code=400,
            detail="Date range cannot exceed 365 days",
        )

    # Generate synthetic data for demo
    try:
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        synthetic_gex = generate_synthetic_gex_data(
            start_date=start_dt,
            end_date=end_dt,
            freq=interval,
        )

        # Convert to GEXSnapshot list
        snapshots = []
        for _, row in synthetic_gex.iterrows():
            # Create minimal snapshot from synthetic data
            snapshot = _generate_mock_gex_snapshot(spot_price=5950.0)
            # Override with actual timestamp
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
            data=snapshots[:100],  # Limit to 100 snapshots for demo
            start_date=start_dt,
            end_date=end_dt,
            count=len(snapshots[:100]),
        )

    except Exception as e:
        logger.error(f"Failed to generate historical GEX data: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate historical data: {str(e)}",
        )


@router.get("/strikes", response_model=GEXByStrike)
async def get_gex_by_strikes(
    min_strike: Optional[float] = Query(None, description="Minimum strike price"),
    max_strike: Optional[float] = Query(None, description="Maximum strike price"),
    settings: Settings = Depends(get_settings),
) -> GEXByStrike:
    """Get GEX breakdown by strike price.

    Returns arrays of strikes and corresponding GEX values for charting.
    """
    # Get current GEX snapshot
    snapshot = await get_current_gex(settings=settings)

    # Extract strike data
    gex_by_strike = snapshot.gex_by_strike

    # Filter by strike range if specified
    if min_strike is not None:
        gex_by_strike = {k: v for k, v in gex_by_strike.items() if k >= min_strike}
    if max_strike is not None:
        gex_by_strike = {k: v for k, v in gex_by_strike.items() if k <= max_strike}

    # Sort by strike
    sorted_strikes = sorted(gex_by_strike.keys())
    sorted_values = [gex_by_strike[s] for s in sorted_strikes]

    return GEXByStrike(
        strikes=sorted_strikes,
        gex_values=sorted_values,
        spot_price=snapshot.spot_price,
        zero_gamma_level=snapshot.zero_gamma_level,
    )


@router.get("/regime", response_model=RegimeData)
async def get_current_regime(
    settings: Settings = Depends(get_settings),
) -> RegimeData:
    """Get current market regime based on GEX.

    Returns regime classification (short_gamma, long_gamma, neutral)
    with description and suggested color for UI.
    """
    # Get current GEX snapshot
    snapshot = await get_current_gex(settings=settings)

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
