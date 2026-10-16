"""Indicator downloads and computation must leave unrelated API requests responsive."""

import asyncio
import threading
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pandas as pd
import pytest

from app.api.routes import analytics
from app.core.demo_data import DemoDataService
from app.core.technical_indicators import TechnicalIndicatorEngine
from app.main import app
from app.services.historical_data import HistoricalDataService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,demo,stage",
    [
        ("yfinance", demo, stage)
        for demo in (False, True)
        for stage in ("download", "compute", "serialize")
    ]
    + [("captured", False, stage) for stage in ("compute", "serialize")]
    + [("synthetic", True, "compute")],
)
async def test_indicator_work_allows_health_request_before_it_finishes(
    monkeypatch, source, demo, stage
):
    loop = asyncio.get_running_loop()
    loop_thread = threading.get_ident()
    started = asyncio.Event()
    release = threading.Event()
    prices = pd.DataFrame(
        {
            "open": [100.0 + n for n in range(25)],
            "high": [101.0 + n for n in range(25)],
            "low": [99.0 + n for n in range(25)],
            "close": [100.0 + n for n in range(25)],
            "volume": [1000] * 25,
        },
        index=pd.date_range("2026-10-01", periods=25, freq="1h", tz="America/New_York"),
    )

    def hold_work():
        loop.call_soon_threadsafe(started.set)
        assert threading.get_ident() != loop_thread, "indicator work ran on the event loop"
        assert release.wait(5), "test watchdog expired before health completed"

    def download(**kwargs):
        if stage == "download":
            hold_work()
        return pd.DataFrame() if source == "synthetic" else prices.copy()

    monkeypatch.setattr(analytics, "_load_yfinance_history", download)
    if source == "captured":
        history = HistoricalDataService()
        monkeypatch.setattr(
            history,
            "get_latest_timestamp",
            AsyncMock(return_value=datetime.fromisoformat("2026-10-02T16:00:00-04:00")),
        )
        monkeypatch.setattr(
            history,
            "get_time_series_frames",
            AsyncMock(return_value=(prices.copy(), pd.DataFrame())),
        )
    else:
        history = SimpleNamespace(
            get_technical_indicators=AsyncMock(return_value=None),
            get_latest_snapshot=AsyncMock(return_value=None),
        )
    monkeypatch.setattr(analytics, "get_historical_data_service", lambda: history)

    if stage == "compute":
        compute = TechnicalIndicatorEngine.compute_indicators

        def compute_indicators(*args, **kwargs):
            hold_work()
            return compute(*args, **kwargs)

        monkeypatch.setattr(TechnicalIndicatorEngine, "compute_indicators", compute_indicators)
    elif stage == "serialize":
        iterrows = pd.DataFrame.iterrows

        def serialize_rows(frame):
            hold_work()
            return iterrows(frame)

        monkeypatch.setattr(pd.DataFrame, "iterrows", serialize_rows)

    if source == "synthetic":
        monkeypatch.setattr(analytics, "get_demo_data_service", DemoDataService)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        request = asyncio.create_task(
            client.get(
                "/api/analytics/technical-indicators",
                params={
                    "provider": "yfinance",
                    "symbol": "QQQ",
                    "period": "1mo",
                    "interval": "1h",
                    "demo": demo,
                },
            )
        )
        try:
            await asyncio.wait_for(started.wait(), 5)
            assert not request.done(), request.result().text
            response = await client.get("/health")
            assert response.status_code == 200
            assert response.json()["status"] == "healthy"
            assert not request.done()
        finally:
            release.set()
            response = await request

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "QQQ"
    assert body["count"] > 0
    assert any(point.get("rsi") is not None for point in body["data"])
    if source != "synthetic":
        assert body["count"] == 25
        assert body["data"][-1]["close"] == 124.0
        assert body["data"][-1]["atr"] == 2.0


@pytest.mark.asyncio
@pytest.mark.parametrize("demo", [False, True])
async def test_cancelled_indicator_request_leaves_health_responsive(monkeypatch, demo):
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    finished = threading.Event()

    def download(**kwargs):
        loop.call_soon_threadsafe(started.set)
        try:
            assert release.wait(5), "test watchdog expired before cancellation"
            return pd.DataFrame()
        finally:
            finished.set()

    history = SimpleNamespace(get_technical_indicators=AsyncMock(return_value=None))
    monkeypatch.setattr(analytics, "get_historical_data_service", lambda: history)
    monkeypatch.setattr(analytics, "_load_yfinance_history", download)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        request = asyncio.create_task(
            client.get(
                "/api/analytics/technical-indicators",
                params={"provider": "yfinance", "symbol": "QQQ", "demo": demo},
            )
        )
        try:
            await asyncio.wait_for(started.wait(), 5)
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
            assert (await client.get("/health")).status_code == 200
            assert not finished.is_set()
        finally:
            release.set()
            await asyncio.gather(request, return_exceptions=True)
            assert await asyncio.to_thread(finished.wait, 5)
