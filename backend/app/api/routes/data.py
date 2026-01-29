"""0DTE GEX Backend - Raw Data API Endpoints.

Provides access to options chain data, spot prices, and market status.
"""

import logging
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import Settings, get_settings
from app.core.data_acquisition import (
    PolygonClient,
    get_market_status,
    is_market_open,
)
from app.models.schemas import MarketStatusResponse, OptionContract
from app.services.cache import get_cache

logger = logging.getLogger(__name__)

router = APIRouter()

# Eastern Time timezone
ET = ZoneInfo("America/New_York")

# Module-level client (lazy initialization)
_polygon_client: Optional[PolygonClient] = None


@router.get("/market-status", response_model=MarketStatusResponse)
async def get_market_status_endpoint() -> MarketStatusResponse:
    """Get current market status.

    Returns whether market is open, current status, and when it opens next.
    This endpoint does not require an API key.
    """
    status = get_market_status()

    return MarketStatusResponse(
        is_open=status["is_open"],
        status=status["status"],
        next_open=status.get("next_open"),
        current_time_et=status["current_time_et"],
    )


@router.get("/options-chain")
async def get_options_chain(
    symbol: str = Query("SPX", description="Underlying symbol"),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Get current 0DTE options chain.

    Returns raw options data before GEX calculation.

    Requires a valid Polygon API key in environment.
    """
    # Check for API key
    if not settings.polygon_api_key:
        raise HTTPException(
            status_code=503,
            detail="Polygon API key not configured. Set POLYGON_API_KEY environment variable.",
        )

    # Check cache
    cache = get_cache()
    today = datetime.now(ET).date().isoformat()
    cache_key = f"options:chain:{symbol}:{today}"

    cached = cache.get_if_fresh(cache_key)
    if cached is not None:
        logger.debug(f"Returning cached options chain for {symbol}")
        return cached

    # Fetch from Polygon
    polygon_client = PolygonClient(
        api_key=settings.polygon_api_key,
        tier="free",
    )

    try:
        # Get options chain
        options_df, spot_price = await polygon_client.get_options_chain_for_gex(
            underlying=symbol
        )

        # Update spot price in cache
        cache.update_spot_price(spot_price)

        # Convert DataFrame to list of dicts
        options_list = []
        for _, row in options_df.iterrows():
            contract = {
                "symbol": row.get("symbol", ""),
                "strike": float(row["strike"]),
                "expiration": row["expiration"].isoformat() if hasattr(row["expiration"], "isoformat") else str(row["expiration"]),
                "type": row["type"],
                "bid": float(row.get("bid", 0)),
                "ask": float(row.get("ask", 0)),
                "mid": float(row.get("mid", 0)),
                "open_interest": int(row.get("open_interest", 0)),
                "volume": int(row.get("volume", 0)),
                "implied_vol": float(row["implied_vol"]) if row.get("implied_vol") else None,
            }
            options_list.append(contract)

        result = {
            "underlying": symbol,
            "spot_price": spot_price,
            "expiration_date": today,
            "contract_count": len(options_list),
            "contracts": options_list,
            "timestamp": datetime.now(ET).isoformat(),
        }

        # Cache and return
        cache.set(cache_key, result)
        logger.info(f"Fetched {len(options_list)} contracts for {symbol}")

        return result

    except Exception as e:
        logger.error(f"Failed to fetch options chain: {e}")

        # Try stale cache
        stale = cache.get(cache_key)
        if stale is not None:
            logger.warning("Returning stale cached options chain")
            return stale

        raise HTTPException(
            status_code=503,
            detail=f"Unable to fetch options chain: {str(e)}",
        )
    finally:
        await polygon_client.close()


@router.get("/spot-price")
async def get_spot_price(
    symbol: str = Query("SPX", description="Symbol to get price for"),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Get current spot price.

    Returns the latest underlying price.

    Requires a valid Polygon API key in environment.
    """
    # Check for API key
    if not settings.polygon_api_key:
        raise HTTPException(
            status_code=503,
            detail="Polygon API key not configured. Set POLYGON_API_KEY environment variable.",
        )

    # Check cache (short TTL for spot price)
    cache = get_cache()
    cache_key = f"spot:{symbol}"

    cached = cache.get_if_fresh(cache_key)
    if cached is not None:
        logger.debug(f"Returning cached spot price for {symbol}")
        return cached

    # Fetch from Polygon
    polygon_client = PolygonClient(
        api_key=settings.polygon_api_key,
        tier="free",
    )

    try:
        spot_price = await polygon_client.get_spot_price(symbol=symbol)

        # Update cache (and check for invalidation)
        cache.update_spot_price(spot_price)

        result = {
            "symbol": symbol,
            "price": spot_price,
            "timestamp": datetime.now(ET).isoformat(),
            "market_status": "open" if is_market_open() else "closed",
        }

        cache.set(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"Failed to fetch spot price: {e}")

        # Try stale cache
        stale = cache.get(cache_key)
        if stale is not None:
            logger.warning("Returning stale cached spot price")
            return stale

        raise HTTPException(
            status_code=503,
            detail=f"Unable to fetch spot price: {str(e)}",
        )
    finally:
        await polygon_client.close()
