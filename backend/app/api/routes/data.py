"""0DTE GEX Backend - Raw Data API Endpoints.

Provides access to options chain data, spot prices, and market status.
"""

import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query

from app.core import (
    ProviderRegistry,
    get_data_client,
    get_market_status,
    is_market_open,
)
from app.models.schemas import MarketStatusResponse, OptionsChainResponse
from app.services.cache import get_cache

logger = logging.getLogger(__name__)

router = APIRouter()

# Eastern Time timezone
ET = ZoneInfo("America/New_York")


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


@router.get("/providers", tags=["Data"])
async def get_providers():
    """
    Get a list of all available data providers and their capabilities.
    """
    try:
        providers = ProviderRegistry.list_providers()

        # Get active default
        from app.config import get_settings
        settings = get_settings()

        return {
            "providers": providers,
            "active_default": settings.data_provider
        }
    except Exception as e:
        logger.error(f"Error fetching providers list: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/options-chain", response_model=OptionsChainResponse, tags=["Data"])
async def get_options_chain(
    symbol: str = Query("SPX", description="Underlying symbol (default: SPX)"),
    expiration: str | None = Query(None, description="Expiration date (YYYY-MM-DD), default is next trading day"),
    provider: str | None = Query(None, description="Data provider to use (e.g. yfinance, tradier)"),
):
    """
    Fetch the complete options chain for a given symbol and expiration date.

    Returns standard GEX dataset including bid/ask, volume, open interest, and implied volatility.
    """
    try:
        # Use provider registry
        client = get_data_client(provider)
        expiration_date: date | None = None
        if expiration:
            try:
                expiration_date = date.fromisoformat(expiration)
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail="expiration must be in YYYY-MM-DD format",
                ) from e

        # Determine actual symbol to request (YFinance needs SPY substitution, Tradier doesn't)
        # Note: the provider abstracts this detail now, but if we need to log it:
        request_symbol = getattr(client, "_get_ticker_symbol", lambda s: s)(symbol)

        logger.info(f"Fetching complete options chain for {symbol} ({request_symbol}) exp={expiration} via {client.provider_name}")

        # Check cache
        cache = get_cache()
        today = datetime.now(ET).date().isoformat()
        cache_key = f"options:chain:{symbol}:{expiration or 'today'}:{client.provider_name}"

        cached = cache.get_if_fresh(cache_key)
        if cached is not None:
            logger.debug(f"Returning cached options chain for {symbol} from {client.provider_name}")
            return OptionsChainResponse(**cached)

        # Fetch the full snapshot for the requested expiration, not the
        # provider's filtered GEX subset.
        options_df = await client.get_options_chain_snapshot(
            underlying=symbol,
            expiration_date=expiration_date,
        )
        spot_price = await client.get_spot_price(symbol=symbol)

        # Update spot price in cache
        cache.update_spot_price(spot_price, symbol=symbol)

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

        if expiration_date is not None:
            resolved_expiration = expiration_date.isoformat()
        else:
            resolved_expiration = today

        if not options_df.empty and "expiration" in options_df.columns:
            first_expiration = options_df.iloc[0]["expiration"]
            resolved_expiration = (
                first_expiration.isoformat()
                if hasattr(first_expiration, "isoformat")
                else str(first_expiration)
            )

        result = {
            "underlying": symbol,
            "spot_price": spot_price,
            "expiration_date": resolved_expiration,
            "contract_count": len(options_list),
            "contracts": options_list,
            "timestamp": datetime.now(ET).isoformat(),
            "provider": client.provider_name,
        }

        # Cache and return
        cache.set(cache_key, result)
        logger.info(f"Fetched {len(options_list)} contracts for {symbol} via {client.provider_name}")

        return OptionsChainResponse(**result)

    except HTTPException:
        raise # Re-raise FastAPI HTTPExceptions
    except Exception as e:
        logger.error(f"Failed to fetch options chain: {e}")

        # Try stale cache
        stale = cache.get(cache_key)
        if stale is not None:
            logger.warning("Returning stale cached options chain")
            return OptionsChainResponse(**stale)

        raise HTTPException(
            status_code=503,
            detail=f"Unable to fetch options chain: {str(e)}",
        )


@router.get("/spot-price", tags=["Data"])
async def get_spot_price(
    symbol: str = Query("SPX", description="Symbol to get price for (default: SPX)"),
    provider: str | None = Query(None, description="Data provider to use (e.g. yfinance, tradier)"),
) -> dict:
    """Get current spot price.

    Returns the latest underlying price.
    """

    try:
        # Use provider registry
        client = get_data_client(provider)

        # Check cache (short TTL for spot price)
        cache = get_cache()
        cache_key = f"spot:{symbol}:{client.provider_name}"

        cached = cache.get_if_fresh(cache_key)
        if cached is not None:
            logger.debug(f"Returning cached spot price for {symbol} from {client.provider_name}")
            return cached

        spot_price = await client.get_spot_price(symbol=symbol)

        # Update cache (and check for invalidation)
        cache.update_spot_price(spot_price, symbol=symbol)

        result = {
            "symbol": symbol,
            "price": spot_price,
            "timestamp": datetime.now(ET).isoformat(),
            "market_status": "open" if is_market_open() else "closed",
            "provider": client.provider_name,
        }

        cache.set(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"Failed to fetch spot price: {e}")

        # Try stale cache (without provider key fallback for simplicity here)
        cache = get_cache()
        stale = cache.get(f"spot:{symbol}:{client.provider_name}" if client else f"spot:{symbol}:yfinance")
        if stale is not None:
            logger.warning("Returning stale cached spot price")
            return stale

        raise HTTPException(
            status_code=503,
            detail=f"Unable to fetch spot price: {str(e)}",
        )



@router.get("/risk-free-rate")
async def get_risk_free_rate() -> dict:
    """Get current risk-free rate used for Black-Scholes calculations.

    Fetches the 4-Week T-Bill rate from FRED (Federal Reserve Economic Data).
    Falls back to a hardcoded default if FRED is unreachable.
    Rate is cached for 24 hours.
    """
    from app.core.rate_provider import get_rate_provider

    provider = get_rate_provider()
    return provider.get_rate_info()
