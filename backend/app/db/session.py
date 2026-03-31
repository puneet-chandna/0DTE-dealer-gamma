"""Async SQLAlchemy session helpers."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def normalize_database_url(database_url: str) -> str:
    """Normalize supported DATABASE_URL formats for SQLAlchemy async use."""
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


def get_database_url() -> str:
    """Return the normalized application database URL."""
    return normalize_database_url(get_settings().database_url)


def get_engine() -> AsyncEngine:
    """Return the shared async engine instance."""
    global _engine

    if _engine is None:
        database_url = get_database_url()
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        _engine = create_async_engine(
            database_url,
            pool_pre_ping=not database_url.startswith("sqlite"),
            connect_args=connect_args,
        )

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the shared async session factory."""
    global _session_factory

    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )

    return _session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency for an async DB session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session


async def ping_database() -> bool:
    """Return whether the configured database can be reached."""
    try:
        async with get_engine().begin():
            return True
    except SQLAlchemyError as exc:
        logger.warning("Database ping failed: %s", exc)
        return False


async def dispose_engine() -> None:
    """Dispose the shared engine and reset cached session state."""
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _session_factory = None
