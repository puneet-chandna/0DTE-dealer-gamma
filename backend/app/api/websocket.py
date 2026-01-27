"""0DTE GEX Backend - WebSocket Endpoint for Real-time Streaming."""

from typing import List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class ConnectionManager:
    """Manage WebSocket connections for real-time GEX streaming."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        """Send message to all connected clients."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Connection lost, will be cleaned up on next disconnect
                pass


manager = ConnectionManager()


@router.websocket("/gex-stream")
async def websocket_gex_stream(websocket: WebSocket) -> None:
    """
    Real-time GEX streaming via WebSocket.

    Client receives updates every 5 seconds with:
    - net_gex: Current net dealer gamma exposure
    - zero_gamma_level: Price where net GEX = 0
    - spot_price: Current SPX price
    - timestamp: Update timestamp
    """
    await manager.connect(websocket)

    try:
        while True:
            # Wait for any message from client (keepalive)
            data = await websocket.receive_text()

            # TODO: Implement real-time GEX streaming
            # For now, echo back to confirm connection
            await websocket.send_json(
                {
                    "type": "info",
                    "message": "GEX streaming pending implementation",
                    "received": data,
                }
            )

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("Client disconnected from GEX stream")
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)
