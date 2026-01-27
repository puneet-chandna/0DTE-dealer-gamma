"""0DTE GEX Backend - FastAPI Application Entry Point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analytics, data, gex
from app.api.websocket import router as ws_router
from app.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup/shutdown events."""
    # Startup: Initialize resources
    print("🚀 Starting 0DTE GEX API Server...")
    # TODO: Initialize database connection pool
    # TODO: Start background data fetching tasks
    yield
    # Shutdown: Cleanup resources
    print("👋 Shutting down 0DTE GEX API Server...")
    # TODO: Close database connections
    # TODO: Stop background tasks


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
