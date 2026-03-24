"""0DTE GEX Backend - WebSocket Endpoint for Real-time Streaming.

Provides real-time GEX updates to connected clients with 5-second intervals.
"""

import asyncio
import logging
import math
from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.config import Settings, get_settings
from app.core.data_acquisition import is_market_open
from app.core.demo_data import get_demo_data_service
from app.core.provider_registry import ProviderRegistry, get_data_client
from app.core.gex_calculator import GEXCalculator
from app.services.cache import get_cache
from app.services.historical_data import get_historical_data_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Eastern Time timezone
ET = ZoneInfo("America/New_York")

# WebSocket update interval (seconds)
WS_UPDATE_INTERVAL = 5
WS_LIVE_FETCH_TIMEOUT_SECONDS = 4
SUPPORTED_SYMBOLS = {"SPX", "SPY", "QQQ", "IWM"}


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


def _build_ws_payload_from_snapshot(
    *,
    snapshot,
    provider: str,
    is_demo: bool,
    is_replay: bool,
) -> dict:
    """Convert a stored or synthetic snapshot into the websocket payload shape."""
    gex_calculator = get_gex_calculator()
    regime, _, _ = gex_calculator.determine_regime(snapshot.net_gex)
    payload = {
        "net_gex": snapshot.net_gex,
        "net_gex_billions": snapshot.net_gex / 1e9,
        "zero_gamma_level": snapshot.zero_gamma_level,
        "spot_price": snapshot.spot_price,
        "regime": regime,
        "provider": provider,
        "timestamp": snapshot.timestamp.isoformat() if hasattr(snapshot.timestamp, "isoformat") else str(snapshot.timestamp),
        "is_mock": is_demo and not is_replay,
        "is_demo": is_demo,
        "is_replay": is_replay,
        "is_stale": False,
    }
    return payload


def _is_reasonable_gex_payload(payload: dict) -> bool:
    """Reject obviously broken live payloads before they reach clients."""
    net_gex = payload.get("net_gex")
    spot_price = payload.get("spot_price")
    zero_gamma_level = payload.get("zero_gamma_level")

    numeric_fields = (net_gex, spot_price, zero_gamma_level)
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in numeric_fields):
        return False

    if not 100 <= spot_price <= 10_000:
        return False

    if not 100 <= zero_gamma_level <= 10_000:
        return False

    return True


def _coerce_gex_snapshot(snapshot_like):
    """Normalize cached snapshot shapes into a GEXSnapshot model."""
    if isinstance(snapshot_like, str):
        import json

        snapshot_like = json.loads(snapshot_like)

    if isinstance(snapshot_like, dict):
        from app.models.schemas import GEXSnapshot

        snapshot_like = GEXSnapshot(**snapshot_like)

    return snapshot_like


def _build_live_ws_payload_from_snapshot(snapshot, provider: str, *, is_stale: bool) -> dict:
    """Build a websocket payload from a live or cached snapshot."""
    gex_calculator = get_gex_calculator()
    regime, _, _ = gex_calculator.determine_regime(snapshot.net_gex)

    payload = {
        "net_gex": snapshot.net_gex,
        "net_gex_billions": snapshot.net_gex / 1e9,
        "zero_gamma_level": snapshot.zero_gamma_level,
        "spot_price": snapshot.spot_price,
        "regime": regime,
        "is_mock": False,
        "is_stale": is_stale,
        "provider": provider,
        "timestamp": snapshot.timestamp.isoformat()
        if hasattr(snapshot.timestamp, "isoformat")
        else str(snapshot.timestamp),
    }
    return payload if _is_reasonable_gex_payload(payload) else _generate_mock_gex_data()


async def _get_latest_persisted_ws_payload(
    *,
    symbol: str,
    provider: str,
    is_stale: bool,
) -> Optional[dict]:
    """Build a websocket payload from the latest persisted snapshot."""
    snapshot = await get_historical_data_service().get_latest_snapshot(
        provider=provider,
        symbol=symbol,
    )
    if snapshot is None:
        return None
    return _build_live_ws_payload_from_snapshot(
        snapshot,
        provider,
        is_stale=is_stale,
    )


async def _get_gex_update(
    settings: Settings,
    demo: bool = False,
    symbol: str = "SPX",
    provider: Optional[str] = None,
) -> dict:
    """Get current GEX data for WebSocket broadcast.

    Args:
        settings: Application settings.

    Returns:
        Dictionary with GEX data for broadcasting.
    """
    active_provider = ProviderRegistry.resolve_provider_name(
        provider,
        default_provider=settings.data_provider,
    )
    default_provider = ProviderRegistry.resolve_provider_name(
        default_provider=settings.data_provider,
    )

    if demo:
        replay_snapshots = await get_historical_data_service().get_historical_snapshots(
            provider=active_provider,
            symbol=symbol,
            start_date=datetime.now(ET).date(),
            end_date=datetime.now(ET).date(),
            interval="5s",
            prefer_replay=True,
        )
        if replay_snapshots:
            bucket_index = int(datetime.now(ET).timestamp()) // WS_UPDATE_INTERVAL
            snapshot = replay_snapshots[bucket_index % len(replay_snapshots)]
            return _build_ws_payload_from_snapshot(
                snapshot=snapshot,
                provider=active_provider,
                is_demo=True,
                is_replay=True,
            )

        payload = get_demo_data_service().get_ws_update(symbol=symbol)
        payload["provider"] = active_provider
        payload["is_replay"] = False
        return payload

    cache = get_cache()
    cache_key = f"gex:current:{symbol}:{active_provider}"
    legacy_cache_key = (
        f"gex:current:{symbol}"
        if active_provider == default_provider
        else None
    )
    cached_key = cache_key

    # Prefer fresh cache only; stale data is handled as a fallback after live fetch fails.
    cached = cache.get_if_fresh(cache_key)
    if cached is None and legacy_cache_key is not None:
        cached_key = legacy_cache_key
        cached = cache.get_if_fresh(legacy_cache_key)
    if cached is not None:
        cached = _coerce_gex_snapshot(cached)
        return _build_live_ws_payload_from_snapshot(
            cached,
            active_provider,
            is_stale=False,
        )

    # If no cached data, fetch fresh data via data provider
    try:
        data_client = get_data_client(active_provider)
        provider_name = data_client.provider_name

        options_df, spot_price = await asyncio.wait_for(
            data_client.get_options_chain_for_gex(underlying=symbol),
            timeout=WS_LIVE_FETCH_TIMEOUT_SECONDS,
        )
        cache.update_spot_price(spot_price, symbol=symbol)

        if options_df.empty:
            logger.warning(f"WebSocket update: empty chain returned by {provider_name}")
            persisted_payload = await _get_latest_persisted_ws_payload(
                symbol=symbol,
                provider=active_provider,
                is_stale=True,
            )
            if persisted_payload is not None:
                return persisted_payload
            return _generate_mock_gex_data()

        gex_calculator = get_gex_calculator()
        snapshot = gex_calculator.calculate_gex_from_chain(
            options_df=options_df,
            spot_price=spot_price,
            timestamp=datetime.now(ET),
        )

        # Store in specific active provider cache and default cache
        cache.set(cache_key, snapshot)
        if legacy_cache_key is not None:
            cache.set(legacy_cache_key, snapshot)

        regime, _, _ = gex_calculator.determine_regime(snapshot.net_gex)

        payload = {
            "net_gex": snapshot.net_gex,
            "net_gex_billions": snapshot.net_gex / 1e9,
            "zero_gamma_level": snapshot.zero_gamma_level,
            "spot_price": snapshot.spot_price,
            "regime": regime,
            "is_mock": False,
            "is_stale": False,
            "provider": provider_name,
            "timestamp": snapshot.timestamp.isoformat(),
        }
        return payload if _is_reasonable_gex_payload(payload) else _generate_mock_gex_data()

    except Exception as e:
        logger.warning(f"Failed to fetch GEX data for WebSocket: {e}")
        stale = cache.get(cache_key)
        stale_key = cache_key
        if stale is None and legacy_cache_key is not None:
            stale = cache.get(legacy_cache_key)
            stale_key = legacy_cache_key
        if stale is not None:
            stale_snapshot = _coerce_gex_snapshot(stale)
            return _build_live_ws_payload_from_snapshot(
                stale_snapshot,
                active_provider,
                is_stale=cache.is_stale(stale_key),
            )
        persisted_payload = await _get_latest_persisted_ws_payload(
            symbol=symbol,
            provider=active_provider,
            is_stale=True,
        )
        if persisted_payload is not None:
            return persisted_payload
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
    demo = websocket.query_params.get("demo", "false").lower() == "true"
    symbol = websocket.query_params.get("symbol", "SPX").strip().upper()
    provider = websocket.query_params.get("provider")
    if provider is not None:
        provider = provider.strip().lower() or None

    if symbol not in SUPPORTED_SYMBOLS:
        logger.warning(f"Rejected websocket connection with unsupported symbol '{symbol}'")
        await websocket.close(
            code=1008,
            reason=f"Unsupported symbol '{symbol}'. Supported symbols: {', '.join(sorted(SUPPORTED_SYMBOLS))}",
        )
        return

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
                "mode": "demo" if demo else "live",
                "provider": provider or settings.data_provider,
            },
            "timestamp": datetime.now(ET).isoformat(),
        })

        while True:
            try:
                # Get current GEX data
                gex_data = await _get_gex_update(
                    settings,
                    demo=demo,
                    symbol=symbol,
                    provider=provider,
                )

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
                logger.exception(f"Error in WebSocket loop: {e}")
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
