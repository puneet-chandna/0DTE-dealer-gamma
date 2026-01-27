"""0DTE GEX Backend - Raw Data API Endpoints."""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/options-chain")
async def get_options_chain() -> dict:
    """
    Get current SPX 0DTE options chain.

    Returns raw options data before GEX calculation.
    """
    # TODO: Implement with Polygon API
    raise HTTPException(
        status_code=501,
        detail="Options chain API pending Polygon integration",
    )


@router.get("/spot-price")
async def get_spot_price() -> dict:
    """
    Get current SPX spot price.

    Returns the latest underlying price.
    """
    # TODO: Implement with Polygon API
    raise HTTPException(
        status_code=501,
        detail="Spot price API pending Polygon integration",
    )
