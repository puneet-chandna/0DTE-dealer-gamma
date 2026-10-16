"""Tests for historical persistence, replay, and DB-backed route reads."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.services.historical_data as historical_data_module
from app.core.gex_calculator import GEXCalculator
from app.core.snapshot_quality import evaluate_snapshot_quality
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
    total_call_gex: float = -2.15e9,
    total_put_gex: float = 8.0e8,
) -> GEXSnapshot:
    return GEXSnapshot(
        timestamp=captured_at,
        spot_price=spot_price,
        total_call_gex=total_call_gex,
        total_put_gex=total_put_gex,
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


def _with_metrics(snapshot: GEXSnapshot, **metrics) -> GEXSnapshot:
    return snapshot.model_copy(
        update={
            "metrics": {
                **snapshot.metrics,
                **metrics,
            }
        }
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


def _build_concentrated_yfinance_options_df() -> pd.DataFrame:
    expiration = "2026-03-27"
    return pd.DataFrame(
        [
            {
                "symbol": "SPY260327C00635000",
                "strike": 6350.0,
                "expiration": expiration,
                "type": "call",
                "bid": 21.5,
                "ask": 21.8,
                "mid": 21.65,
                "open_interest": 827,
                "volume": 82056,
                "implied_vol": 0.060434,
            },
            {
                "symbol": "SPY260327P00635000",
                "strike": 6350.0,
                "expiration": expiration,
                "type": "put",
                "bid": 19.7,
                "ask": 20.1,
                "mid": 19.9,
                "open_interest": 29402,
                "volume": 387675,
                "implied_vol": 0.088388,
            },
            {
                "symbol": "SPY260327C00640000",
                "strike": 6400.0,
                "expiration": expiration,
                "type": "call",
                "bid": 4.5,
                "ask": 4.7,
                "mid": 4.6,
                "open_interest": 1577,
                "volume": 483427,
                "implied_vol": 0.097665,
            },
            {
                "symbol": "SPY260327P00640000",
                "strike": 6400.0,
                "expiration": expiration,
                "type": "put",
                "bid": 49.8,
                "ask": 50.3,
                "mid": 50.05,
                "open_interest": 51100,
                "volume": 468138,
                "implied_vol": 0.160897,
            },
        ]
    )


def _build_time_series_frames(
    start_time: datetime,
    *,
    periods: int = 15,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    index = pd.date_range(start_time, periods=periods, freq="1min")
    close = pd.Series(5900.0 + (0.5 * pd.RangeIndex(periods)), index=index, dtype=float)
    price_data = pd.DataFrame(
        {
            "open": close - 0.25,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 0.0,
        },
        index=index,
    )
    gex_data = pd.DataFrame(
        {
            "spot_price": close,
            "net_gex": [-2.0e9] * 5 + [2.0e9] * (periods - 5),
            "total_call_gex": [-2.4e9] * periods,
            "total_put_gex": [4.0e8] * periods,
            "zero_gamma_level": [5910.0] * periods,
        },
        index=index,
    )
    return price_data, gex_data


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
@pytest.mark.parametrize("missing_quote", [None, pd.NA, float("nan")])
async def test_missing_option_mid_preserves_raw_and_gex_capture(history_service, missing_quote):
    service, session_factory = history_service
    options = _build_options_df().to_dict(orient="records")
    options[1].update(bid=missing_quote, ask=missing_quote, mid=missing_quote)

    persisted = await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=_build_snapshot(datetime(2026, 3, 20, 10, 5, tzinfo=ET)),
        options_df=pd.DataFrame(options),
        force_raw_capture=True,
    )

    assert persisted is True
    async with session_factory() as session:
        market_session = (await session.execute(select(MarketSessionRecord))).scalar_one()
        gex_snapshot = (await session.execute(select(GEXSnapshotRecord))).scalar_one()
        strike_points = (await session.execute(select(GEXByStrikePointRecord))).scalars().all()
        raw_snapshot = (await session.execute(select(RawOptionsSnapshotRecord))).scalar_one()
        iv_points = (await session.execute(select(IVSurfacePointRecord))).scalars().all()

    assert market_session.snapshot_count == market_session.raw_snapshot_count == 1
    assert gex_snapshot.net_gex == -1.35e9
    assert gex_snapshot.metrics["has_raw_snapshot"] is True
    assert len(strike_points) == 3
    assert raw_snapshot.contract_count == 2
    assert raw_snapshot.payload[1]["implied_vol"] == 0.205
    assert {field: raw_snapshot.payload[1][field] for field in ("bid", "ask", "mid")} == {
        "bid": None,
        "ask": None,
        "mid": None,
    }
    assert [(point.option_type, point.mid_price, point.iv) for point in iv_points] == [
        ("call", 14.5, 0.19)
    ]


def test_nullable_raw_counts_round_trip_remains_usable_for_gex():
    payload = _build_options_df().to_dict(orient="records")
    for option in payload:
        option.update(open_interest=None, volume=None)
    raw_record = RawOptionsSnapshotRecord(
        payload=payload,
        source_metadata={"provider": "yfinance"},
        expiration_date=date(2099, 1, 15),
    )

    options = HistoricalDataService._deserialize_options_payload(raw_record)
    snapshot = GEXCalculator().calculate_gex_from_chain(
        options,
        spot_price=5905.0,
        timestamp=datetime(2026, 3, 20, 10, 5, tzinfo=ET),
    )
    quality = evaluate_snapshot_quality(snapshot, options_df=options, provider="yfinance")

    assert snapshot.net_gex == 0.0
    assert snapshot.gex_by_strike == {}
    assert options["open_interest"].isna().all()
    assert options["volume"].isna().all()
    assert quality.is_replay_eligible is False
    assert "insufficient_meaningful_strikes" in quality.quality_flags
    assert HistoricalDataService._serialize_options_payload(options) == payload
    assert all(
        option["open_interest"] is None and option["volume"] is None
        for option in raw_record.payload
    )


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
async def test_current_route_falls_back_to_latest_persisted_snapshot_when_live_fetch_fails(
    history_service,
):
    service, _ = history_service
    captured_at = datetime(2026, 3, 20, 13, 45, 0, tzinfo=ET)

    await service.persist_capture(
        provider="tradier",
        symbol="SPX",
        snapshot=_build_snapshot(captured_at, spot_price=6032.5, net_gex=7.8e8),
        options_df=_build_options_df(),
        force_raw_capture=True,
    )

    with patch("app.api.routes.gex.get_historical_data_service", return_value=service):
        with patch("app.api.routes.gex.get_cache") as mock_get_cache:
            mock_cache = mock_get_cache.return_value
            mock_cache.get_if_fresh.return_value = None
            mock_cache.get.return_value = None
            with patch(
                "app.api.routes.gex._get_live_gex_snapshot",
                new_callable=AsyncMock,
                side_effect=RuntimeError("live provider timeout"),
            ):
                response = client.get(
                    "/api/gex/current",
                    params={"provider": "tradier", "symbol": "SPX"},
                )

    assert response.status_code == 200
    body = response.json()
    assert body["spot_price"] == 6032.5
    assert body["net_gex"] == 7.8e8
    assert body["zero_gamma_level"] == 5912.5
    assert body["metrics"]["capture_quality"] == 0.99
    assert body["metrics"]["is_persisted_fallback"] == 1.0


@pytest.mark.asyncio
async def test_backfill_from_raw_overwrites_legacy_yfinance_snapshot_and_marks_it_ineligible(
    history_service,
):
    service, session_factory = history_service
    captured_at = datetime(2026, 3, 27, 15, 34, 43, tzinfo=ET)

    await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=_build_snapshot(captured_at, spot_price=6351.8, net_gex=1.1625236653103598e13),
        options_df=_build_concentrated_yfinance_options_df(),
        force_raw_capture=True,
    )

    async with session_factory() as session:
        snapshot_record = (
            await session.execute(
                select(GEXSnapshotRecord).where(GEXSnapshotRecord.provider == "yfinance")
            )
        ).scalar_one()
        snapshot_record.total_call_gex = -3.992868594729168e11
        snapshot_record.total_put_gex = 1.2024523512576514e13
        snapshot_record.net_gex = 1.1625236653103598e13
        snapshot_record.metrics = {"capture_quality": 1.0, "is_replay_eligible": 1.0}
        await session.commit()

    rebuilt = await service.rebuild_gex_snapshots_from_raw(provider="yfinance", symbol="SPX")
    latest = await service.get_latest_snapshot(
        provider="yfinance",
        symbol="SPX",
        replay_eligible_only=False,
    )

    assert rebuilt == 1
    assert latest is not None
    assert latest.net_gex < 0
    assert abs(latest.net_gex) < 2.0e11
    assert latest.metrics["is_replay_eligible"] is False
    assert "provider_gex_outlier" in latest.metrics["quality_flags"]


@pytest.mark.asyncio
async def test_backfill_from_raw_uses_market_close_for_date_only_expiration_with_utc_capture(
    history_service,
):
    service, session_factory = history_service
    captured_at_utc = datetime(2026, 3, 27, 19, 34, 43, tzinfo=ZoneInfo("UTC"))

    async with session_factory() as session:
        market_session = MarketSessionRecord(
            provider="yfinance",
            symbol="SPX",
            trading_date=date(2026, 3, 27),
            status="complete",
            completeness_ratio=1.0,
            snapshot_count=1,
            raw_snapshot_count=1,
            first_captured_at=captured_at_utc,
            last_captured_at=captured_at_utc,
            capture_metadata={},
        )
        session.add(market_session)
        await session.flush()

        session.add(
            GEXSnapshotRecord(
                session_id=market_session.id,
                provider="yfinance",
                symbol="SPX",
                captured_at=captured_at_utc,
                spot_price=6351.8,
                total_call_gex=0.0,
                total_put_gex=0.0,
                net_gex=0.0,
                zero_gamma_level=6351.8,
                dominant_strike=6350.0,
                metrics={"capture_quality": 0.0, "is_replay_eligible": 0.0},
            )
        )
        session.add(
            RawOptionsSnapshotRecord(
                session_id=market_session.id,
                provider="yfinance",
                symbol="SPX",
                captured_at=captured_at_utc,
                spot_price=6351.8,
                expiration_date=date(2026, 3, 27),
                contract_count=2,
                payload=[
                    {
                        "symbol": "SPY260327C00635000",
                        "strike": 6350.0,
                        "expiration": "2026-03-27",
                        "type": "call",
                        "bid": 21.5,
                        "ask": 21.8,
                        "mid": 21.65,
                        "open_interest": 827,
                        "volume": 82056,
                        "implied_vol": 0.060434,
                    },
                    {
                        "symbol": "SPY260327P00635000",
                        "strike": 6350.0,
                        "expiration": "2026-03-27",
                        "type": "put",
                        "bid": 19.7,
                        "ask": 20.1,
                        "mid": 19.9,
                        "open_interest": 29402,
                        "volume": 387675,
                        "implied_vol": 0.088388,
                    },
                ],
                source_metadata={"storage_format": "normalized_options_chain", "columns": []},
            )
        )
        await session.commit()

    rebuilt = await service.rebuild_gex_snapshots_from_raw(provider="yfinance", symbol="SPX")
    latest = await service.get_latest_snapshot(provider="yfinance", symbol="SPX")

    assert rebuilt == 1
    assert latest is not None
    assert latest.net_gex != 0.0


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


@pytest.mark.asyncio
async def test_prefer_replay_skips_newest_ineligible_session_and_uses_latest_good_anchor(
    history_service,
):
    service, _ = history_service
    older_capture = datetime(2026, 3, 26, 15, 58, 0, tzinfo=ET)
    newer_capture = datetime(2026, 3, 27, 15, 58, 0, tzinfo=ET)

    await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=_with_metrics(
            _build_snapshot(older_capture, spot_price=5911.0, net_gex=-7.5e8),
            is_replay_eligible=True,
            capture_quality=0.99,
        ),
        options_df=_build_options_df(),
        force_raw_capture=True,
    )
    await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=_with_metrics(
            _build_snapshot(newer_capture, spot_price=6351.8, net_gex=-1.15e11),
            is_replay_eligible=False,
            capture_quality=0.66,
            quality_flags=["provider_gex_outlier"],
        ),
        options_df=_build_concentrated_yfinance_options_df(),
        force_raw_capture=True,
    )

    replay_snapshot = await service.get_latest_snapshot(
        provider="yfinance",
        symbol="SPX",
        prefer_replay=True,
    )

    assert replay_snapshot is not None
    assert HistoricalDataService._normalize_timestamp(replay_snapshot.timestamp) == older_capture
    assert replay_snapshot.spot_price == 5911.0
    assert replay_snapshot.metrics["is_replay_eligible"] is True


@pytest.mark.asyncio
async def test_prefer_replay_skips_explicitly_eligible_but_hard_invalid_session(history_service):
    service, session_factory = history_service
    older_capture = datetime(2026, 3, 26, 15, 58, 0, tzinfo=ET)
    newer_capture = datetime(2026, 3, 27, 15, 58, 0, tzinfo=ET)

    await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=_with_metrics(
            _build_snapshot(older_capture, spot_price=5911.0, net_gex=-7.5e8),
            is_replay_eligible=True,
            capture_quality=0.99,
        ),
        options_df=_build_options_df(),
        force_raw_capture=True,
    )
    await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=_with_metrics(
            _build_snapshot(
                newer_capture,
                spot_price=6351.8,
                net_gex=6.6e12,
                total_call_gex=-1.11e11,
                total_put_gex=6.71e12,
            ),
            is_replay_eligible=True,
            capture_quality=0.66,
            quality_flags=["provider_gex_outlier"],
        ),
        options_df=_build_options_df(),
        force_raw_capture=True,
    )

    async with session_factory() as session:
        sessions = (await session.execute(select(MarketSessionRecord))).scalars().all()
        for market_session in sessions:
            market_session.status = "complete"

        latest_record = (
            await session.execute(
                select(GEXSnapshotRecord).where(
                    GEXSnapshotRecord.provider == "yfinance",
                    GEXSnapshotRecord.symbol == "SPX",
                    GEXSnapshotRecord.captured_at == newer_capture,
                )
            )
        ).scalar_one()
        latest_record.metrics = {
            **dict(latest_record.metrics or {}),
            "quality_flags": ["provider_gex_outlier"],
            "has_raw_snapshot": False,
            "is_replay_eligible": True,
        }
        await session.commit()

    replay_snapshot = await service.get_latest_snapshot(
        provider="yfinance",
        symbol="SPX",
        prefer_replay=True,
    )

    assert replay_snapshot is not None
    assert HistoricalDataService._normalize_timestamp(replay_snapshot.timestamp) == older_capture
    assert replay_snapshot.spot_price == 5911.0


@pytest.mark.asyncio
async def test_iv_surface_prefer_replay_skips_explicitly_eligible_but_hard_invalid_session(
    history_service,
):
    service, session_factory = history_service
    older_capture = datetime(2026, 3, 26, 15, 58, 0, tzinfo=ET)
    newer_capture = datetime(2026, 3, 27, 15, 58, 0, tzinfo=ET)

    await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=_with_metrics(
            _build_snapshot(older_capture, spot_price=5911.0, net_gex=-7.5e8),
            is_replay_eligible=True,
            capture_quality=0.99,
        ),
        options_df=_build_options_df(),
        force_raw_capture=True,
    )
    await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=_with_metrics(
            _build_snapshot(
                newer_capture,
                spot_price=6351.8,
                net_gex=6.6e12,
                total_call_gex=-1.11e11,
                total_put_gex=6.71e12,
            ),
            is_replay_eligible=True,
            capture_quality=0.66,
            quality_flags=["provider_gex_outlier"],
        ),
        options_df=_build_options_df(),
        force_raw_capture=True,
    )

    async with session_factory() as session:
        sessions = (await session.execute(select(MarketSessionRecord))).scalars().all()
        for market_session in sessions:
            market_session.status = "complete"

        latest_record = (
            await session.execute(
                select(GEXSnapshotRecord).where(
                    GEXSnapshotRecord.provider == "yfinance",
                    GEXSnapshotRecord.symbol == "SPX",
                    GEXSnapshotRecord.captured_at == newer_capture,
                )
            )
        ).scalar_one()
        latest_record.metrics = {
            **dict(latest_record.metrics or {}),
            "quality_flags": ["provider_gex_outlier"],
            "has_raw_snapshot": False,
            "is_replay_eligible": True,
        }
        await session.commit()

    surface = await service.get_iv_surface(
        provider="yfinance",
        symbol="SPX",
        prefer_replay=True,
    )

    assert surface is not None
    assert surface["spot_price"] == 5911.0


@pytest.mark.asyncio
async def test_latest_snapshot_skips_hard_invalid_outlier_rows_for_persisted_reads(history_service):
    service, session_factory = history_service
    earlier_capture = datetime(2026, 3, 27, 15, 42, 0, tzinfo=ET)
    later_capture = datetime(2026, 3, 27, 15, 43, 0, tzinfo=ET)

    await service.persist_capture(
        provider="tradier",
        symbol="SPX",
        snapshot=_with_metrics(
            _build_snapshot(earlier_capture, spot_price=6365.8, net_gex=-2.8e10),
            quality_flags=["insufficient_meaningful_strikes"],
            is_replay_eligible=False,
        ),
        options_df=None,
        force_raw_capture=False,
    )
    await service.persist_capture(
        provider="tradier",
        symbol="SPX",
        snapshot=_with_metrics(
            _build_snapshot(
                later_capture,
                spot_price=6366.4,
                net_gex=2.7683e12,
                total_call_gex=-7.68e10,
                total_put_gex=2.8451e12,
            ),
            quality_flags=["provider_gex_outlier"],
            is_replay_eligible=False,
        ),
        options_df=None,
        force_raw_capture=False,
    )

    async with session_factory() as session:
        latest_record = (
            await session.execute(
                select(GEXSnapshotRecord).where(
                    GEXSnapshotRecord.provider == "tradier",
                    GEXSnapshotRecord.symbol == "SPX",
                    GEXSnapshotRecord.captured_at == later_capture,
                )
            )
        ).scalar_one()
        latest_record.metrics = {
            **dict(latest_record.metrics or {}),
            "quality_flags": ["provider_gex_outlier"],
            "has_raw_snapshot": False,
            "is_replay_eligible": False,
        }
        await session.commit()

    latest = await service.get_latest_snapshot(provider="tradier", symbol="SPX")

    assert latest is not None
    assert HistoricalDataService._normalize_timestamp(latest.timestamp) == earlier_capture
    assert latest.net_gex == -2.8e10
    assert "provider_gex_outlier" not in latest.metrics["quality_flags"]


@pytest.mark.asyncio
async def test_latest_timestamp_scans_limited_batches_until_it_finds_usable_record(
    history_service,
    monkeypatch,
):
    service, session_factory = history_service
    earlier_capture = datetime(2026, 3, 27, 15, 42, 0, tzinfo=ET)
    later_capture = datetime(2026, 3, 27, 15, 43, 0, tzinfo=ET)

    monkeypatch.setattr(historical_data_module, "LATEST_RECORD_SCAN_BATCH_SIZE", 1)

    await service.persist_capture(
        provider="tradier",
        symbol="SPX",
        snapshot=_with_metrics(
            _build_snapshot(earlier_capture, spot_price=6365.8, net_gex=-2.8e10),
            quality_flags=["insufficient_meaningful_strikes"],
            is_replay_eligible=False,
        ),
        options_df=None,
        force_raw_capture=False,
    )
    await service.persist_capture(
        provider="tradier",
        symbol="SPX",
        snapshot=_with_metrics(
            _build_snapshot(
                later_capture,
                spot_price=6366.4,
                net_gex=2.7683e12,
                total_call_gex=-7.68e10,
                total_put_gex=2.8451e12,
            ),
            quality_flags=["provider_gex_outlier"],
            is_replay_eligible=False,
        ),
        options_df=None,
        force_raw_capture=False,
    )

    async with session_factory() as session:
        latest_record = (
            await session.execute(
                select(GEXSnapshotRecord).where(
                    GEXSnapshotRecord.provider == "tradier",
                    GEXSnapshotRecord.symbol == "SPX",
                    GEXSnapshotRecord.captured_at == later_capture,
                )
            )
        ).scalar_one()
        latest_record.metrics = {
            **dict(latest_record.metrics or {}),
            "quality_flags": ["provider_gex_outlier"],
            "has_raw_snapshot": False,
            "is_replay_eligible": False,
        }
        await session.commit()

    latest_timestamp = await service.get_latest_timestamp(provider="tradier", symbol="SPX")

    assert latest_timestamp is not None
    assert HistoricalDataService._normalize_timestamp(latest_timestamp) == earlier_capture


@pytest.mark.asyncio
async def test_historical_snapshots_exclude_hard_invalid_outlier_rows_from_non_replay_reads(
    history_service,
):
    service, session_factory = history_service
    base_capture = datetime(2026, 3, 27, 15, 40, 0, tzinfo=ET)

    await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=_with_metrics(
            _build_snapshot(base_capture, spot_price=6349.0, net_gex=-4.9e10),
            quality_flags=["insufficient_meaningful_strikes", "put_iv_corrupted"],
            is_replay_eligible=False,
        ),
        options_df=None,
        force_raw_capture=False,
    )
    await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=_with_metrics(
            _build_snapshot(
                base_capture.replace(minute=41),
                spot_price=6345.0,
                net_gex=6.59404e12,
                total_call_gex=-1.11e11,
                total_put_gex=6.70504e12,
            ),
            quality_flags=[
                "insufficient_meaningful_strikes",
                "put_iv_corrupted",
                "provider_gex_outlier",
            ],
            is_replay_eligible=False,
        ),
        options_df=None,
        force_raw_capture=False,
    )
    await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=_with_metrics(
            _build_snapshot(base_capture.replace(minute=42), spot_price=6341.2, net_gex=-6.5e10),
            quality_flags=["insufficient_meaningful_strikes", "put_iv_corrupted"],
            is_replay_eligible=False,
        ),
        options_df=None,
        force_raw_capture=False,
    )

    async with session_factory() as session:
        outlier_record = (
            await session.execute(
                select(GEXSnapshotRecord).where(
                    GEXSnapshotRecord.provider == "yfinance",
                    GEXSnapshotRecord.symbol == "SPX",
                    GEXSnapshotRecord.captured_at == base_capture.replace(minute=41),
                )
            )
        ).scalar_one()
        outlier_record.metrics = {
            **dict(outlier_record.metrics or {}),
            "quality_flags": [
                "insufficient_meaningful_strikes",
                "put_iv_corrupted",
                "provider_gex_outlier",
            ],
            "has_raw_snapshot": False,
            "is_replay_eligible": False,
        }
        await session.commit()

    snapshots = await service.get_historical_snapshots(
        provider="yfinance",
        symbol="SPX",
        start_date=date(2026, 3, 27),
        end_date=date(2026, 3, 27),
        interval="5s",
    )

    assert [snapshot.spot_price for snapshot in snapshots] == [6349.0, 6341.2]
    assert all(
        "provider_gex_outlier" not in snapshot.metrics["quality_flags"] for snapshot in snapshots
    )


@pytest.mark.asyncio
async def test_demo_historical_falls_back_to_synthetic_when_no_persisted_snapshots_exist(
    history_service,
):
    service, _ = history_service
    demo_snapshot = _build_snapshot(
        datetime(2026, 3, 21, 10, 0, 0, tzinfo=ET),
        spot_price=5922.0,
        net_gex=-5.5e8,
    )

    class _DemoService:
        def get_historical_snapshots(self, *args, **kwargs):
            return [demo_snapshot]

    with patch("app.api.routes.gex.get_historical_data_service", return_value=service):
        with patch("app.api.routes.gex.get_demo_data_service", return_value=_DemoService()):
            response = client.get(
                "/api/gex/historical",
                params={
                    "provider": "yfinance",
                    "symbol": "SPX",
                    "start_date": "2026-03-21",
                    "end_date": "2026-03-21",
                    "interval": "1m",
                    "demo": "true",
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["data"][0]["spot_price"] == 5922.0
    assert body["data"][0]["net_gex"] == -5.5e8


@pytest.mark.asyncio
async def test_range_sensitive_backtest_helpers_skip_latest_replay_when_requested_window_is_empty(
    history_service,
):
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

    vectorbt_result = await service.run_vectorbt_backtest(
        provider="yfinance",
        symbol="SPX",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 3, 1),
        entry_threshold=-1e9,
        exit_threshold=0.0,
        initial_cash=100_000.0,
        prefer_replay=True,
        allow_latest_replay_fallback=False,
    )
    legacy_result = await service.run_backtest(
        provider="yfinance",
        symbol="SPX",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 3, 1),
        strategy="volatility_breakout",
        entry_threshold=-1e9,
        exit_threshold=0.0,
        stop_loss_pct=0.02,
        take_profit_pct=0.05,
        prefer_replay=True,
        allow_latest_replay_fallback=False,
    )

    assert vectorbt_result is None
    assert legacy_result is None


@pytest.mark.asyncio
async def test_demo_vectorbt_backtest_honors_requested_range_when_replay_window_is_empty(
    history_service,
):
    service, session_factory = history_service
    captured_at = datetime(2026, 3, 20, 15, 58, 0, tzinfo=ET)

    await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=_build_snapshot(captured_at, spot_price=6031.0, net_gex=-7.5e8),
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

    expected_anchor = await service.get_latest_snapshot(provider="yfinance", symbol="SPX")
    demo_price_data, demo_gex_data = _build_time_series_frames(
        datetime(2025, 1, 2, 9, 30, tzinfo=ET)
    )
    demo_gex_data = demo_gex_data.copy()
    demo_gex_data["net_gex"] = 2.0e9

    class _DemoService:
        def get_time_series(
            self, symbol, start_date, end_date, interval="1min", *, anchor_snapshot=None
        ):
            assert symbol == "SPX"
            assert start_date == date(2025, 1, 1)
            assert end_date == date(2025, 3, 1)
            assert anchor_snapshot is not None
            assert anchor_snapshot.spot_price == expected_anchor.spot_price
            return demo_price_data, demo_gex_data

    with patch("app.api.routes.analytics.get_historical_data_service", return_value=service):
        with patch("app.api.routes.analytics.get_demo_data_service", return_value=_DemoService()):
            response = client.get(
                "/api/analytics/vectorbt-backtest",
                params={
                    "provider": "yfinance",
                    "symbol": "SPX",
                    "start_date": "2025-01-01",
                    "end_date": "2025-03-01",
                    "demo": "true",
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["start_date"].startswith("2025-01-02T09:30:00")
    assert body["end_date"].startswith("2025-01-02T09:44:00")
    assert body["total_trades"] == 0


@pytest.mark.asyncio
async def test_demo_legacy_backtest_honors_requested_range_when_replay_window_is_empty(
    history_service,
):
    service, session_factory = history_service
    captured_at = datetime(2026, 3, 20, 15, 58, 0, tzinfo=ET)

    await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=_build_snapshot(captured_at, spot_price=6031.0, net_gex=-7.5e8),
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

    expected_anchor = await service.get_latest_snapshot(provider="yfinance", symbol="SPX")
    demo_price_data, demo_gex_data = _build_time_series_frames(
        datetime(2025, 1, 2, 9, 30, tzinfo=ET)
    )
    demo_gex_data = demo_gex_data.copy()
    demo_gex_data["net_gex"] = 2.0e9

    class _DemoService:
        def get_time_series(
            self, symbol, start_date, end_date, interval="1min", *, anchor_snapshot=None
        ):
            assert symbol == "SPX"
            assert start_date == date(2025, 1, 1)
            assert end_date == date(2025, 3, 1)
            assert anchor_snapshot is not None
            assert anchor_snapshot.spot_price == expected_anchor.spot_price
            return demo_price_data, demo_gex_data

    with patch("app.api.routes.analytics.get_historical_data_service", return_value=service):
        with patch("app.api.routes.analytics.get_demo_data_service", return_value=_DemoService()):
            response = client.get(
                "/api/analytics/backtest",
                params={
                    "provider": "yfinance",
                    "symbol": "SPX",
                    "start_date": "2025-01-01",
                    "end_date": "2025-03-01",
                    "demo": "true",
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["start_date"].startswith("2025-01-02T09:30:00")
    assert body["end_date"].startswith("2025-01-02T09:44:00")
    assert body["total_trades"] == 0


@pytest.mark.asyncio
async def test_demo_current_skips_ineligible_latest_replay_and_uses_latest_good_same_provider_snapshot(
    history_service,
):
    service, session_factory = history_service
    earlier_good = datetime(2026, 3, 20, 15, 45, 0, tzinfo=ET)
    later_bad = datetime(2026, 3, 20, 15, 58, 0, tzinfo=ET)

    await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=_with_metrics(
            _build_snapshot(earlier_good, spot_price=6011.0, net_gex=-7.5e8),
            is_replay_eligible=1.0,
        ),
        options_df=_build_options_df(),
        force_raw_capture=True,
    )
    await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=_with_metrics(
            _build_snapshot(later_bad, spot_price=6530.0, net_gex=-1.05e12),
            capture_quality=0.0,
            meaningful_strike_count=1.0,
            is_replay_eligible=0.0,
        ),
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
        def get_current_snapshot(self, *args, **kwargs):
            raise AssertionError("synthetic demo fallback should not be used")

    with patch("app.api.routes.gex.get_historical_data_service", return_value=service):
        with patch("app.api.routes.gex.get_demo_data_service", return_value=_FailingDemoService()):
            response = client.get(
                "/api/gex/current",
                params={
                    "provider": "yfinance",
                    "symbol": "SPX",
                    "demo": "true",
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["spot_price"] == 6011.0
    assert body["metrics"]["is_replay_data"] == 1.0


@pytest.mark.asyncio
async def test_demo_current_falls_back_to_synthetic_without_cross_provider_replay_when_only_other_provider_is_good(
    history_service,
):
    service, session_factory = history_service
    captured_at = datetime(2026, 3, 20, 15, 58, 0, tzinfo=ET)

    await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=_with_metrics(
            _build_snapshot(captured_at, spot_price=6530.0, net_gex=-1.05e12),
            capture_quality=0.0,
            meaningful_strike_count=1.0,
            is_replay_eligible=0.0,
        ),
        options_df=_build_options_df(),
        force_raw_capture=True,
    )
    await service.persist_capture(
        provider="tradier",
        symbol="SPX",
        snapshot=_with_metrics(
            _build_snapshot(captured_at, spot_price=6042.0, net_gex=8.2e8),
            is_replay_eligible=1.0,
        ),
        options_df=_build_options_df(),
        force_raw_capture=True,
    )

    async with session_factory() as session:
        sessions = (await session.execute(select(MarketSessionRecord))).scalars().all()
        for market_session in sessions:
            market_session.status = "complete"
        await session.commit()

    synthetic_snapshot = _build_snapshot(
        datetime(2026, 3, 21, 10, 0, 0, tzinfo=ET),
        spot_price=5902.0,
        net_gex=-4.8e8,
    )

    class _DemoService:
        def get_current_snapshot(self, symbol, now=None, *, anchor_snapshot, provider="demo"):
            assert symbol == "SPX"
            assert anchor_snapshot is None
            assert provider == "yfinance"
            return synthetic_snapshot

    with patch("app.api.routes.gex.get_historical_data_service", return_value=service):
        with patch("app.api.routes.gex.get_demo_data_service", return_value=_DemoService()):
            response = client.get(
                "/api/gex/current",
                params={
                    "provider": "yfinance",
                    "symbol": "SPX",
                    "demo": "true",
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["spot_price"] == 5902.0
    assert body["provider"] == "yfinance"


@pytest.mark.asyncio
async def test_get_technical_indicators_returns_null_indicators_for_short_history(history_service):
    service, _ = history_service
    base_time = datetime(2026, 3, 20, 10, 0, 0, tzinfo=ET)

    for offset_minutes, spot_price in enumerate((5901.0, 5903.0, 5902.5)):
        await service.persist_capture(
            provider="yfinance",
            symbol="SPX",
            snapshot=_build_snapshot(
                base_time.replace(minute=base_time.minute + offset_minutes),
                spot_price=spot_price,
                net_gex=-1.1e9 + (offset_minutes * 1.0e7),
            ),
            options_df=_build_options_df(),
            force_raw_capture=False,
        )

    indicators = await service.get_technical_indicators(
        provider="yfinance",
        symbol="SPX",
        period="5d",
        interval="1m",
        indicators=[" atr ", "rsi"],
    )

    assert indicators is not None
    assert indicators["symbol"] == "SPX"
    assert indicators["indicators"] == ["ATR", "RSI"]
    assert indicators["count"] == 3
    assert all(point["atr"] is None for point in indicators["data"])
    assert all(point["rsi"] is None for point in indicators["data"])
    assert all(point["bb_upper"] is None for point in indicators["data"])


@pytest.mark.asyncio
async def test_captured_bars_use_et_completion_time_and_end_labels(history_service):
    service, _ = history_service
    captured_at = datetime(2025, 1, 6, 9, 30, 10, tzinfo=ET)
    snapshot = _build_snapshot(captured_at)
    snapshot.metrics["feature_available_at"] = "2025-01-06T09:30:40-05:00"
    snapshot.metrics["quality_flags"] = ["put_iv_corrupted"]
    await service.persist_capture(
        provider="yfinance", symbol="SPX", snapshot=snapshot, options_df=None
    )
    prices, gex = await service.get_time_series_frames(
        provider="yfinance",
        symbol="SPX",
        start_date=date(2025, 1, 6),
        end_date=date(2025, 1, 6),
        interval="1m",
    )
    assert prices.index[0] == pd.Timestamp("2025-01-06T09:31:00-05:00")
    assert gex.index[0] == prices.index[0]
    assert gex.attrs["timestamp_basis"] == "feature completion; bars labeled at end"
    assert "put_iv_corrupted" in " ".join(gex.attrs["quality_limitations"])
    snapshots = await service.get_historical_snapshots(
        provider="yfinance",
        symbol="SPX",
        start_date=date(2025, 1, 6),
        end_date=date(2025, 1, 6),
        interval="1m",
    )
    assert snapshots[0].timestamp == datetime(2025, 1, 6, 9, 31, tzinfo=ET)
    latest = await service.get_latest_snapshot(provider="yfinance", symbol="SPX")
    assert latest.timestamp == captured_at


@pytest.mark.asyncio
async def test_open_minute_is_not_published_as_a_completed_backtest_bar(
    history_service, monkeypatch
):
    service, _ = history_service
    now = datetime(2025, 1, 6, 9, 31, 20, tzinfo=ET)

    class DateTimeMeta(type):
        def __instancecheck__(cls, value):
            return isinstance(value, datetime)

    class FrozenDateTime(datetime, metaclass=DateTimeMeta):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz else now.replace(tzinfo=None)

    monkeypatch.setattr(historical_data_module, "datetime", FrozenDateTime)
    for minute in (30, 31):
        capture = datetime(2025, 1, 6, 9, minute, 10, tzinfo=ET)
        snapshot = _build_snapshot(capture)
        snapshot.metrics["feature_available_at"] = capture.isoformat()
        await service.persist_capture(
            provider="yfinance", symbol="SPX", snapshot=snapshot, options_df=None
        )
    prices, gex = await service.get_time_series_frames(
        provider="yfinance", symbol="SPX", start_date=now.date(), end_date=now.date(), interval="1m"
    )
    assert list(prices.index) == [pd.Timestamp("2025-01-06T09:31:00-05:00")]
    assert list(gex.index) == list(prices.index)


@pytest.mark.asyncio
@pytest.mark.parametrize("keep_derived", [True, False])
async def test_raw_rebuild_preserves_source_identity_but_invalidates_feature_asof_clock(
    history_service, keep_derived
):
    service, session_factory = history_service
    captured_at = datetime(2026, 3, 27, 15, 34, 43, tzinfo=ET)
    original_completion = "2026-03-27T15:34:44-04:00"
    source = {
        "actual_instrument": "SPY",
        "is_proxy": True,
        "source_received_at": "2026-03-27T15:34:42-04:00",
        "nominal_options_delay_minutes": 15,
        "quote_freshness": "unknown",
        "open_interest_frequency": "daily",
        "open_interest_asof": None,
    }
    options = _build_concentrated_yfinance_options_df()
    options.attrs["source_metadata"] = {**source, "feature_available_at": original_completion}
    snapshot = _with_metrics(
        _build_snapshot(captured_at, spot_price=6351.8),
        feature_available_at=original_completion,
        calculation_version="legacy_cumulative_strikes",
        audit_note="retain original capture evidence",
    )
    await service.persist_capture(
        provider="yfinance",
        symbol="SPX",
        snapshot=snapshot,
        options_df=options,
        force_raw_capture=True,
    )
    if not keep_derived:
        async with session_factory() as session:
            record = (await session.execute(select(GEXSnapshotRecord))).scalar_one()
            await session.delete(record)
            await session.commit()

    before_rebuild = datetime.now(ET)
    for _ in range(2):
        assert await service.rebuild_gex_snapshots_from_raw(provider="yfinance", symbol="SPX") == 1
        rebuilt = await service.get_latest_snapshot(
            provider="yfinance",
            symbol="SPX",
            replay_eligible_only=False,
        )
        assert rebuilt.timestamp == captured_at
        for key, value in source.items():
            assert rebuilt.metrics[key] == value
        assert rebuilt.metrics["feature_available_at"] is None
        assert rebuilt.metrics["original_feature_available_at"] == original_completion
        assert datetime.fromisoformat(rebuilt.metrics["reconstructed_at"]) >= before_rebuild
        assert rebuilt.metrics["calculation_version"] == "sticky_iv_delta_scenarios_v1"
        if keep_derived:
            assert rebuilt.metrics["audit_note"] == "retain original capture evidence"
        prices, gex = await service.get_time_series_frames(
            provider="yfinance",
            symbol="SPX",
            start_date=captured_at.date(),
            end_date=captured_at.date(),
            interval="1m",
        )
        assert prices.index[0] == pd.Timestamp(captured_at).ceil("min")
        assert gex.attrs["timestamp_basis"] == "capture reference; feature completion unknown"


@pytest.mark.asyncio
async def test_retention_keeps_enough_calendar_history_for_30_trading_sessions(history_service):
    service, session_factory = history_service
    reference = date(2026, 10, 14)
    for days_ago in (91, 90, 45):
        captured = datetime.combine(
            reference - timedelta(days=days_ago), datetime.min.time(), ET
        ).replace(hour=10)
        await service.persist_capture(
            provider="yfinance", symbol="SPY", snapshot=_build_snapshot(captured), options_df=None
        )
    async with session_factory() as session:
        await service._apply_retention(session, reference_date=reference)
        await session.commit()
        days = (await session.execute(select(MarketSessionRecord.trading_date))).scalars().all()
    assert sorted(days) == [reference - timedelta(days=90), reference - timedelta(days=45)]
