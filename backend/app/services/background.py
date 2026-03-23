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
from app.core.provider_registry import ProviderRegistry, get_data_client
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


def get_gex_calculator() -> GEXCalculator:
    """Get or create the GEX calculator instance."""
    global _gex_calculator
    if _gex_calculator is None:
        _gex_calculator = GEXCalculator()
    return _gex_calculator


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

            if not is_market_open():
                await asyncio.sleep(60)
                continue

            # Get data client
            data_client = get_data_client()

            try:
                # Fetch options chain and spot price
                options_df, spot_price = await data_client.get_options_chain_for_gex()

                # Update spot price in cache (may trigger invalidation)
                cache.update_spot_price(spot_price)

                # Calculate GEX
                timestamp = datetime.now(ET)
                if options_df.empty:
                    from app.api.routes.gex import _generate_mock_gex_snapshot
                    snapshot = _generate_mock_gex_snapshot(spot_price=spot_price)
                else:
                    snapshot = gex_calculator.calculate_gex_from_chain(
                        options_df=options_df,
                        spot_price=spot_price,
                        timestamp=timestamp,
                    )

                # Cache the result
                settings = get_settings()
                default_provider = ProviderRegistry.resolve_provider_name(
                    default_provider=settings.data_provider,
                )
                cache.set(f"gex:current:SPX:{default_provider}", snapshot)
                cache.set("gex:current:SPX", snapshot)

                logger.debug(
                    f"GEX refreshed: net_gex={snapshot.net_gex/1e9:.3f}B, "
                    f"spot={snapshot.spot_price:.2f} via {data_client.provider_name}"
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

            if not is_market_open():
                await asyncio.sleep(60)
                continue

            # Get data client
            data_client = get_data_client()

            try:
                spot_price = await data_client.get_spot_price()
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

    data_client = get_data_client()
    cache = get_cache()
    gex_calculator = get_gex_calculator()

    try:
        # Fetch initial data
        options_df, spot_price = await data_client.get_options_chain_for_gex()
        cache.update_spot_price(spot_price)

        # Calculate and cache GEX
        if options_df.empty:
            from app.api.routes.gex import _generate_mock_gex_snapshot
            snapshot = _generate_mock_gex_snapshot(spot_price=spot_price)
        else:
            snapshot = gex_calculator.calculate_gex_from_chain(
                options_df=options_df,
                spot_price=spot_price,
                timestamp=datetime.now(ET),
            )
        settings = get_settings()
        default_provider = ProviderRegistry.resolve_provider_name(
            default_provider=settings.data_provider,
        )
        cache.set(f"gex:current:SPX:{default_provider}", snapshot)
        cache.set("gex:current:SPX", snapshot)

        logger.info(
            f"Cache warmup complete: net_gex={snapshot.net_gex/1e9:.3f}B, "
            f"spot={spot_price:.2f}, contracts={len(options_df)} via {data_client.provider_name}"
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

    # Start data refresh tasks
    gex_task = asyncio.create_task(periodic_gex_refresh())
    gex_task.set_name("gex_refresh")
    _background_tasks.append(gex_task)

    spot_task = asyncio.create_task(periodic_spot_refresh())
    spot_task.set_name("spot_refresh")
    _background_tasks.append(spot_task)

    logger.info(f"Started {len(_background_tasks)} background tasks")
    logger.info("Background tasks initialization complete")


async def stop_background_tasks() -> None:
    """Stop all background tasks on application shutdown."""
    global _background_tasks, _shutdown_event

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

    # Close data provider instances
    from app.core.provider_registry import ProviderRegistry
    await ProviderRegistry.close_all()

    logger.info("Background tasks stopped")
