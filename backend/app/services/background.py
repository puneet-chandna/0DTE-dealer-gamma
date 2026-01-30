"""0DTE GEX Backend - Background Tasks Service.

Handles periodic data fetching, cache warming, and scheduled tasks.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.core.data_acquisition import is_market_open
from app.core.yfinance_provider import YFinanceClient
from app.core.gex_calculator import GEXCalculator
from app.services.cache import get_cache

logger = logging.getLogger(__name__)

# Eastern Time timezone
ET = ZoneInfo("America/New_York")

# Background task interval (seconds)
GEX_REFRESH_INTERVAL = 5
SPOT_REFRESH_INTERVAL = 2

# Task management
_background_tasks: list[asyncio.Task] = []
_shutdown_event: Optional[asyncio.Event] = None

# Module-level instances
_gex_calculator: Optional[GEXCalculator] = None
_data_client: Optional[YFinanceClient] = None


def get_gex_calculator() -> GEXCalculator:
    """Get or create the GEX calculator instance."""
    global _gex_calculator
    if _gex_calculator is None:
        _gex_calculator = GEXCalculator()
    return _gex_calculator


async def get_data_client() -> YFinanceClient:
    """Get or create the YFinance data client instance.

    Uses Yahoo Finance via yfinance library (free, no API key required).
    Uses SPY as proxy for SPX options data.
    """
    global _data_client

    if _data_client is None:
        _data_client = YFinanceClient(
            calls_per_minute=10,  # Conservative rate limit
            use_spy_as_proxy=True,
        )
    return _data_client


async def periodic_gex_refresh() -> None:
    """Periodically fetch and cache GEX data during market hours.

    Runs every 5 seconds when market is open, caching the latest
    GEX calculation for fast API response times.
    """
    global _shutdown_event
    cache = get_cache()
    gex_calculator = get_gex_calculator()

    logger.info("Starting periodic GEX refresh task")

    while True:
        try:
            # Check for shutdown signal
            if _shutdown_event and _shutdown_event.is_set():
                logger.info("GEX refresh task received shutdown signal")
                break

            # Only refresh during market hours
            if not is_market_open():
                # During off-hours, check less frequently
                await asyncio.sleep(60)
                continue

            # Get data client (YFinance)
            data_client = await get_data_client()

            try:
                # Fetch options chain and spot price via YFinance (uses SPY as proxy)
                options_df, spot_price = await data_client.get_options_chain_for_gex("SPY")

                # Update spot price in cache (may trigger invalidation)
                cache.update_spot_price(spot_price)

                # Calculate GEX
                timestamp = datetime.now(ET)
                snapshot = gex_calculator.calculate_gex_from_chain(
                    options_df=options_df,
                    spot_price=spot_price,
                    timestamp=timestamp,
                )

                # Cache the result
                cache.set("gex:current", snapshot)

                logger.debug(
                    f"GEX refreshed: net_gex={snapshot.net_gex/1e9:.3f}B, "
                    f"spot={snapshot.spot_price:.2f}"
                )

            except Exception as e:
                logger.error(f"GEX refresh failed: {e}")

            # Wait for next refresh
            await asyncio.sleep(GEX_REFRESH_INTERVAL)

        except asyncio.CancelledError:
            logger.info("GEX refresh task cancelled")
            break
        except Exception as e:
            logger.error(f"Unexpected error in GEX refresh task: {e}")
            await asyncio.sleep(GEX_REFRESH_INTERVAL)

    logger.info("GEX refresh task stopped")


async def periodic_spot_refresh() -> None:
    """Periodically refresh spot price with shorter interval.

    Spot price updates more frequently (every 2 seconds) since it's
    critical for cache invalidation logic.
    """
    global _shutdown_event
    cache = get_cache()

    logger.info("Starting periodic spot price refresh task")

    while True:
        try:
            # Check for shutdown signal
            if _shutdown_event and _shutdown_event.is_set():
                logger.info("Spot refresh task received shutdown signal")
                break

            # Only refresh during market hours
            if not is_market_open():
                await asyncio.sleep(60)
                continue

            # Get data client (YFinance)
            data_client = await get_data_client()

            try:
                spot_price = await data_client.get_spot_price("SPY")
                cache.update_spot_price(spot_price)
                logger.debug(f"Spot price refreshed: {spot_price:.2f}")

            except Exception as e:
                logger.warning(f"Spot refresh failed: {e}")

            await asyncio.sleep(SPOT_REFRESH_INTERVAL)

        except asyncio.CancelledError:
            logger.info("Spot refresh task cancelled")
            break
        except Exception as e:
            logger.error(f"Unexpected error in spot refresh task: {e}")
            await asyncio.sleep(SPOT_REFRESH_INTERVAL)

    logger.info("Spot refresh task stopped")


async def cache_warmup() -> None:
    """Warm up cache with initial data on startup.

    Runs once at startup to pre-populate cache if market is open.
    """
    logger.info("Starting cache warmup")

    if not is_market_open():
        logger.info("Market is closed, skipping cache warmup")
        return

    data_client = await get_data_client()

    cache = get_cache()
    gex_calculator = get_gex_calculator()

    try:
        # Fetch initial data via YFinance (uses SPY as proxy)
        options_df, spot_price = await data_client.get_options_chain_for_gex("SPY")
        cache.update_spot_price(spot_price)

        # Calculate and cache GEX
        snapshot = gex_calculator.calculate_gex_from_chain(
            options_df=options_df,
            spot_price=spot_price,
            timestamp=datetime.now(ET),
        )
        cache.set("gex:current", snapshot)

        logger.info(
            f"Cache warmup complete: net_gex={snapshot.net_gex/1e9:.3f}B, "
            f"spot={spot_price:.2f}, contracts={len(options_df)}"
        )

    except Exception as e:
        logger.error(f"Cache warmup failed: {e}")


async def start_background_tasks() -> None:
    """Start all background tasks on application startup."""
    global _background_tasks, _shutdown_event

    logger.info("Starting background tasks...")

    # Create shutdown event
    _shutdown_event = asyncio.Event()

    # Run cache warmup first
    await cache_warmup()

    # Start periodic tasks
    settings = get_settings()

    # Start data refresh tasks (YFinance - no API key required)
    gex_task = asyncio.create_task(periodic_gex_refresh())
    gex_task.set_name("gex_refresh")
    _background_tasks.append(gex_task)

    spot_task = asyncio.create_task(periodic_spot_refresh())
    spot_task.set_name("spot_refresh")
    _background_tasks.append(spot_task)

    logger.info(
        f"Started {len(_background_tasks)} background tasks "
        f"(using YFinance - free data)"
    )

    logger.info("Background tasks initialization complete")


async def stop_background_tasks() -> None:
    """Stop all background tasks on application shutdown."""
    global _background_tasks, _shutdown_event, _data_client

    logger.info("Stopping background tasks...")

    # Signal shutdown
    if _shutdown_event:
        _shutdown_event.set()

    # Cancel all background tasks
    for task in _background_tasks:
        if not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception as e:
                logger.error(f"Error stopping task {task.get_name()}: {e}")

    _background_tasks.clear()

    # Close data client
    if _data_client:
        await _data_client.close()
        _data_client = None

    logger.info("Background tasks stopped")
