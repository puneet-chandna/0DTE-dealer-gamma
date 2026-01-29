"""0DTE GEX Backend - WebSocket Endpoint for Real-time Streaming.

Provides real-time GEX updates to connected clients with 5-second intervals.
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.config import Settings, get_settings
from app.core.data_acquisition import PolygonClient, is_market_open
from app.core.gex_calculator import GEXCalculator
from app.services.cache import get_cache

logger = logging.getLogger(__name__)

router = APIRouter()

# Eastern Time timezone
ET = ZoneInfo("America/New_York")

# WebSocket update interval (seconds)
WS_UPDATE_INTERVAL = 5


class ConnectionManager:
    """Manage WebSocket connections for real-time GEX streaming."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info(f"Client connected. Total connections: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info(f"Client disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict) -> None:
        """Send message to all connected clients."""
        disconnected = []

        async with self._lock:
            for connection in self.active_connections:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send to client: {e}")
                    disconnected.append(connection)

            # Clean up disconnected clients
            for conn in disconnected:
                if conn in self.active_connections:
                    self.active_connections.remove(conn)

        if disconnected:
            logger.info(f"Cleaned up {len(disconnected)} dead connections")

    @property
    def connection_count(self) -> int:
        """Number of active connections."""
        return len(self.active_connections)


manager = ConnectionManager()

# Module-level instances
_gex_calculator: Optional[GEXCalculator] = None


def get_gex_calculator() -> GEXCalculator:
    """Get or create the GEX calculator instance."""
    global _gex_calculator
    if _gex_calculator is None:
        _gex_calculator = GEXCalculator()
    return _gex_calculator


def _generate_mock_gex_data() -> dict:
    """Generate mock GEX data for WebSocket streaming when API is unavailable."""
    import numpy as np

    now = datetime.now(ET)
    np.random.seed(int(now.timestamp()) % 10000)

    net_gex = np.random.uniform(-3e9, 2e9)
    spot_price = 5950.0 + np.random.uniform(-50, 50)
    zero_gamma_level = spot_price + np.random.uniform(-20, 20)

    # Determine regime
    if net_gex < -1e9:
        regime = "short_gamma"
    elif net_gex > 1e9:
        regime = "long_gamma"
    else:
        regime = "neutral"

    return {
        "net_gex": net_gex,
        "net_gex_billions": net_gex / 1e9,
        "zero_gamma_level": zero_gamma_level,
        "spot_price": spot_price,
        "regime": regime,
        "is_mock": True,
    }


async def _get_gex_update(settings: Settings) -> dict:
    """Get current GEX data for WebSocket broadcast.

    Args:
        settings: Application settings.

    Returns:
        Dictionary with GEX data for broadcasting.
    """
    cache = get_cache()

    # Try to get from cache first
    cached = cache.get("gex:current")
    if cached is not None:
        gex_calculator = get_gex_calculator()
        regime, _, _ = gex_calculator.determine_regime(cached.net_gex)

        return {
            "net_gex": cached.net_gex,
            "net_gex_billions": cached.net_gex / 1e9,
            "zero_gamma_level": cached.zero_gamma_level,
            "spot_price": cached.spot_price,
            "regime": regime,
            "is_mock": False,
            "is_stale": cache.is_stale("gex:current"),
        }

    # If no cached data and no API key, return mock
    if not settings.polygon_api_key:
        return _generate_mock_gex_data()

    # Try to fetch fresh data
    try:
        polygon_client = PolygonClient(
            api_key=settings.polygon_api_key,
            tier="free",
        )

        try:
            options_df, spot_price = await polygon_client.get_options_chain_for_gex()
            cache.update_spot_price(spot_price)

            gex_calculator = get_gex_calculator()
            snapshot = gex_calculator.calculate_gex_from_chain(
                options_df=options_df,
                spot_price=spot_price,
                timestamp=datetime.now(ET),
            )

            cache.set("gex:current", snapshot)
            regime, _, _ = gex_calculator.determine_regime(snapshot.net_gex)

            return {
                "net_gex": snapshot.net_gex,
                "net_gex_billions": snapshot.net_gex / 1e9,
                "zero_gamma_level": snapshot.zero_gamma_level,
                "spot_price": snapshot.spot_price,
                "regime": regime,
                "is_mock": False,
                "is_stale": False,
            }

        finally:
            await polygon_client.close()

    except Exception as e:
        logger.warning(f"Failed to fetch GEX data for WebSocket: {e}")
        return _generate_mock_gex_data()


@router.websocket("/gex-stream")
async def websocket_gex_stream(websocket: WebSocket) -> None:
    """Real-time GEX streaming via WebSocket.

    Client receives updates every 5 seconds with:
    - net_gex: Current net dealer gamma exposure
    - net_gex_billions: Net GEX in billions
    - zero_gamma_level: Price where net GEX = 0
    - spot_price: Current SPX price
    - regime: Current market regime (short_gamma, long_gamma, neutral)
    - timestamp: Update timestamp

    Message Format:
    {
        "type": "gex_update",
        "data": { ... },
        "timestamp": "2024-01-15T10:30:00-05:00"
    }
    """
    await manager.connect(websocket)
    settings = get_settings()

    try:
        # Send initial connection message
        await websocket.send_json({
            "type": "connected",
            "data": {
                "message": "Connected to GEX stream",
                "market_open": is_market_open(),
                "update_interval_seconds": WS_UPDATE_INTERVAL,
            },
            "timestamp": datetime.now(ET).isoformat(),
        })

        while True:
            try:
                # Get current GEX data
                gex_data = await _get_gex_update(settings)

                # Send update
                message = {
                    "type": "gex_update",
                    "data": gex_data,
                    "timestamp": datetime.now(ET).isoformat(),
                    "market_open": is_market_open(),
                }
                await websocket.send_json(message)

                # Wait for next update interval
                # Also listen for any incoming messages (keepalive/ping)
                try:
                    await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=WS_UPDATE_INTERVAL,
                    )
                except asyncio.TimeoutError:
                    # Normal timeout - no client message received
                    pass

            except WebSocketDisconnect:
                raise
            except Exception as e:
                logger.error(f"Error in WebSocket loop: {e}")
                # Send error message to client
                try:
                    await websocket.send_json({
                        "type": "error",
                        "data": {"message": str(e)},
                        "timestamp": datetime.now(ET).isoformat(),
                    })
                except Exception:
                    pass

                # Wait before retrying
                await asyncio.sleep(WS_UPDATE_INTERVAL)

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
        logger.info("Client disconnected from GEX stream")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await manager.disconnect(websocket)


@router.get("/connections")
async def get_connection_count() -> dict:
    """Get current WebSocket connection count.

    Useful for monitoring active client connections.
    """
    return {
        "active_connections": manager.connection_count,
        "timestamp": datetime.now(ET).isoformat(),
    }
