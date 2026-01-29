"""0DTE GEX Backend - FastAPI Application Entry Point."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analytics, data, gex
from app.api.websocket import router as ws_router
from app.config import get_settings
from app.services.background import start_background_tasks, stop_background_tasks

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup/shutdown events."""
    # Startup: Initialize resources
    logger.info("🚀 Starting 0DTE GEX API Server...")

    # Start background tasks (data fetching, cache warming)
    await start_background_tasks()

    logger.info("✅ 0DTE GEX API Server ready")

    yield

    # Shutdown: Cleanup resources
    logger.info("👋 Shutting down 0DTE GEX API Server...")

    # Stop background tasks
    await stop_background_tasks()

    logger.info("🛑 0DTE GEX API Server stopped")


app = FastAPI(
    title="0DTE GEX API",
    description="Real-time Dealer Gamma Exposure Analysis for 0DTE Options",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(gex.router, prefix="/api/gex", tags=["GEX"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(data.router, prefix="/api/data", tags=["Data"])
app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint with API information."""
    return {
        "message": "0DTE GEX API",
        "docs": "/docs",
        "version": "1.0.0",
    }


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for monitoring."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
    )
