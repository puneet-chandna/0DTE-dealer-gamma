"""Tests for historical persistence, replay, and DB-backed route reads."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import (
    GEXByStrikePointRecord,
    GEXSnapshotRecord,
    IVSurfacePointRecord,
    MarketSessionRecord,
    RawOptionsSnapshotRecord,
)
from app.main import app
from app.models.schemas import GEXSnapshot
from app.services.historical_data import HistoricalDataService

client = TestClient(app)
ET = ZoneInfo("America/New_York")


def _build_snapshot(
    captured_at: datetime,
    *,
    spot_price: float = 5905.0,
    net_gex: float = -1.35e9,
) -> GEXSnapshot:
    return GEXSnapshot(
        timestamp=captured_at,
        spot_price=spot_price,
        total_call_gex=-2.15e9,
        total_put_gex=8.0e8,
        net_gex=net_gex,
        zero_gamma_level=5912.5,
        gex_by_strike={
            5880.0: -2.5e8,
            5900.0: -3.75e8,
            5920.0: 1.25e8,
        },
        dominant_strike=5900.0,
        metrics={"capture_quality": 0.99},
    )


def _build_options_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "SPXW20990115C05900000",
                "strike": 5900.0,
                "expiration": "2099-01-15",
                "type": "call",
                "bid": 14.2,
                "ask": 14.8,
                "mid": 14.5,
                "open_interest": 1200,
                "volume": 320,
                "implied_vol": 0.19,
            },
            {
                "symbol": "SPXW20990115P05900000",
                "strike": 5900.0,
                "expiration": "2099-01-15",
                "type": "put",
                "bid": 12.5,
                "ask": 13.1,
                "mid": 12.8,
                "open_interest": 980,
                "volume": 280,
                "implied_vol": 0.205,
            },
        ]
    )


@pytest.fixture
async def history_service(tmp_path: Path):
    db_path = tmp_path / "history-test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    service = HistoricalDataService(session_factory=session_factory)
    try:
        yield service, session_factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_persist_capture_stores_provider_separated_history(history_service):
    service, session_factory = history_service
    captured_at = datetime(2026, 3, 20, 10, 5, 0, tzinfo=ET)

    await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=_build_snapshot(captured_at, spot_price=5905.0, net_gex=-1.35e9),
        options_df=_build_options_df(),
        force_raw_capture=True,
    )
    await service.persist_capture(
        provider="tradier",
        symbol="SPX",
        snapshot=_build_snapshot(captured_at, spot_price=5906.0, net_gex=-9.5e8),
        options_df=_build_options_df(),
        force_raw_capture=True,
    )

    async with session_factory() as session:
        sessions = (await session.execute(select(MarketSessionRecord))).scalars().all()
        gex_snapshots = (await session.execute(select(GEXSnapshotRecord))).scalars().all()
        strike_points = (await session.execute(select(GEXByStrikePointRecord))).scalars().all()
        raw_snapshots = (await session.execute(select(RawOptionsSnapshotRecord))).scalars().all()
        iv_points = (await session.execute(select(IVSurfacePointRecord))).scalars().all()

    assert {(row.provider, row.symbol) for row in sessions} == {
        ("yfinance", "SPX"),
        ("tradier", "SPX"),
    }
    assert len(gex_snapshots) == 2
    assert len(strike_points) == 6
    assert len(raw_snapshots) == 2
    assert len(iv_points) == 4


@pytest.mark.asyncio
async def test_historical_route_uses_database_when_history_exists(history_service):
    service, _ = history_service
    captured_at = datetime(2026, 3, 20, 10, 5, 0, tzinfo=ET)

    await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=_build_snapshot(captured_at, spot_price=5905.0, net_gex=-1.35e9),
        options_df=_build_options_df(),
        force_raw_capture=True,
    )

    with patch("app.api.routes.gex.get_historical_data_service", return_value=service):
        response = client.get(
            "/api/gex/historical",
            params={
                "provider": "yfinance",
                "symbol": "SPX",
                "start_date": "2026-03-20",
                "end_date": "2026-03-20",
                "interval": "1m",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["data"][0]["spot_price"] == 5905.0
    assert body["data"][0]["net_gex"] == -1.35e9
    assert body["data"][0]["metrics"]["capture_quality"] == 0.99


@pytest.mark.asyncio
async def test_demo_historical_prefers_latest_replay_session_before_synthetic(history_service):
    service, session_factory = history_service
    captured_at = datetime(2026, 3, 20, 15, 58, 0, tzinfo=ET)

    await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=_build_snapshot(captured_at, spot_price=5911.0, net_gex=-7.5e8),
        options_df=_build_options_df(),
        force_raw_capture=True,
    )

    async with session_factory() as session:
        market_session = (
            await session.execute(
                select(MarketSessionRecord).where(
                    MarketSessionRecord.provider == "yfinance",
                    MarketSessionRecord.symbol == "SPX",
                    MarketSessionRecord.trading_date == date(2026, 3, 20),
                )
            )
        ).scalar_one()
        market_session.status = "complete"
        await session.commit()

    class _FailingDemoService:
        def get_historical_snapshots(self, *args, **kwargs):
            raise AssertionError("synthetic demo fallback should not be used")

    with patch("app.api.routes.gex.get_historical_data_service", return_value=service):
        with patch("app.api.routes.gex.get_demo_data_service", return_value=_FailingDemoService()):
            response = client.get(
                "/api/gex/historical",
                params={
                    "provider": "yfinance",
                    "symbol": "SPX",
                    "start_date": "2026-01-01",
                    "end_date": "2026-03-01",
                    "interval": "1m",
                    "demo": "true",
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["data"][0]["spot_price"] == 5911.0
    assert body["data"][0]["metrics"]["capture_quality"] == 0.99
