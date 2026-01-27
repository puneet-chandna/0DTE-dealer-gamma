"""0DTE GEX Backend - GEX API Endpoints."""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import GEXByStrike, GEXHistorical, GEXSnapshot, RegimeData

router = APIRouter()


@router.get("/current", response_model=GEXSnapshot)
async def get_current_gex() -> GEXSnapshot:
    """
    Get current real-time GEX calculation.

    Returns the latest GEX snapshot including net GEX, zero gamma level,
    and breakdown by strike.
    """
    # TODO: Implement with real data from Polygon API
    # For now, return placeholder to enable API testing
    raise HTTPException(
        status_code=501,
        detail="GEX calculation pending Polygon API integration",
    )


@router.get("/historical", response_model=GEXHistorical)
async def get_historical_gex(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    interval: str = Query("1h", description="Data interval: 5m, 15m, 1h, 1d"),
) -> GEXHistorical:
    """
    Get historical GEX data for date range.

    Useful for backtesting and analysis.
    """
    # TODO: Load from database
    raise HTTPException(
        status_code=501,
        detail="Historical data storage pending implementation",
    )


@router.get("/strikes", response_model=GEXByStrike)
async def get_gex_by_strikes(
    min_strike: Optional[float] = Query(None, description="Minimum strike price"),
    max_strike: Optional[float] = Query(None, description="Maximum strike price"),
) -> GEXByStrike:
    """
    Get GEX breakdown by strike price.

    Returns arrays of strikes and corresponding GEX values for charting.
    """
    # TODO: Implement with real data
    raise HTTPException(
        status_code=501,
        detail="GEX by strikes pending implementation",
    )


@router.get("/regime", response_model=RegimeData)
async def get_current_regime() -> RegimeData:
    """
    Get current market regime based on GEX.

    Returns regime classification (short_gamma, long_gamma, neutral)
    with description and suggested color for UI.
    """
    # TODO: Calculate from current GEX
    raise HTTPException(
        status_code=501,
        detail="Regime detection pending implementation",
    )
