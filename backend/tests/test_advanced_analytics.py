"""Tests for advanced analytics state management and enrichment safety."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Event

import pandas as pd
import pytest

from app.core import advanced_analytics as analytics
from app.core.hawkes_engine import HawkesState
from app.models.schemas import AdvancedAnalytics, GEXSnapshot, HawkesStateModel


def _build_snapshot(*, advanced: AdvancedAnalytics | None = None) -> GEXSnapshot:
    return GEXSnapshot(
        timestamp=datetime.fromisoformat("2026-03-27T10:30:00-04:00"),
        spot_price=5805.0,
        total_call_gex=-2.0e8,
        total_put_gex=1.5e8,
        net_gex=-5.0e7,
        zero_gamma_level=5795.0,
        gex_by_strike={5800.0: -5.0e7},
        dominant_strike=5800.0,
        metrics={},
        advanced_analytics=advanced,
    )


class TestAnalyticsStateCaches:
    def setup_method(self) -> None:
        analytics.reset_advanced_analytics_state()

    def teardown_method(self) -> None:
        analytics.reset_advanced_analytics_state()

    def test_get_hawkes_engine_creates_one_instance_per_stream_under_concurrency(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        release_constructor = Event()
        first_constructor_started = Event()
        second_constructor_started = Event()

        class FakeHawkesEngine:
            constructor_count = 0

            def __init__(self) -> None:
                type(self).constructor_count += 1
                if type(self).constructor_count == 1:
                    first_constructor_started.set()
                else:
                    second_constructor_started.set()
                release_constructor.wait(timeout=1)

        monkeypatch.setattr(analytics, "HawkesEngine", FakeHawkesEngine)

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_one = executor.submit(
                analytics.get_hawkes_engine,
                symbol="SPX",
                provider="tradier",
            )
            assert first_constructor_started.wait(timeout=1)

            future_two = executor.submit(
                analytics.get_hawkes_engine,
                symbol="SPX",
                provider="tradier",
            )

            try:
                assert not second_constructor_started.wait(timeout=0.1)
            finally:
                release_constructor.set()

            engine_one = future_one.result(timeout=1)
            engine_two = future_two.result(timeout=1)

        assert engine_one is engine_two
        assert FakeHawkesEngine.constructor_count == 1

    def test_get_kalman_filter_creates_one_instance_per_stream_under_concurrency(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        release_constructor = Event()
        first_constructor_started = Event()
        second_constructor_started = Event()

        class FakeKalmanFilter:
            constructor_count = 0

            def __init__(self) -> None:
                type(self).constructor_count += 1
                if type(self).constructor_count == 1:
                    first_constructor_started.set()
                else:
                    second_constructor_started.set()
                release_constructor.wait(timeout=1)

        monkeypatch.setattr(analytics, "GEXKalmanFilter", FakeKalmanFilter)

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_one = executor.submit(
                analytics.get_kalman_filter,
                symbol="SPX",
                provider="tradier",
            )
            assert first_constructor_started.wait(timeout=1)

            future_two = executor.submit(
                analytics.get_kalman_filter,
                symbol="SPX",
                provider="tradier",
            )

            try:
                assert not second_constructor_started.wait(timeout=0.1)
            finally:
                release_constructor.set()

            filter_one = future_one.result(timeout=1)
            filter_two = future_two.result(timeout=1)

        assert filter_one is filter_two
        assert FakeKalmanFilter.constructor_count == 1


class TestAdvancedAnalyticsEnrichment:
    def setup_method(self) -> None:
        analytics.reset_advanced_analytics_state()

    def teardown_method(self) -> None:
        analytics.reset_advanced_analytics_state()

    def test_same_stream_enrichments_do_not_overlap_updates(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        first_update_entered = Event()
        release_first_update = Event()
        overlap_detected = Event()

        class FakeEngine:
            def __init__(self) -> None:
                self.in_update = False

            def snapshot_state(self) -> dict[str, bool]:
                return {"in_update": self.in_update}

            def restore_state(self, state: dict[str, bool]) -> None:
                self.in_update = state["in_update"]

            def update(
                self,
                options_df: pd.DataFrame,
                timestamp: float,
                *,
                spot_price: float | None = None,
                provider_mode: str | None = None,
            ) -> HawkesState:
                del options_df, timestamp
                assert spot_price == 5805.0
                assert provider_mode == "tradier_rich"
                if self.in_update:
                    overlap_detected.set()
                self.in_update = True
                first_update_entered.set()
                release_first_update.wait(timeout=1)
                self.in_update = False
                return HawkesState(
                    call_intensity=1.0,
                    put_intensity=0.5,
                    net_toxicity=0.5,
                    squeeze_probability=0.25,
                )

        class FakeKalmanFilter:
            def snapshot_state(self) -> dict[str, None]:
                return {"unused": None}

            def restore_state(self, state: dict[str, None]) -> None:
                del state

            def update(self, measurement: float) -> float:
                return measurement

        monkeypatch.setattr(analytics, "HawkesEngine", FakeEngine)
        monkeypatch.setattr(analytics, "GEXKalmanFilter", FakeKalmanFilter)

        snapshot_one = _build_snapshot()
        snapshot_two = _build_snapshot()
        options_df = pd.DataFrame({"strike": [5800.0], "type": ["call"], "volume": [100]})

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_one = executor.submit(
                analytics.enrich_snapshot_with_advanced_analytics,
                snapshot_one,
                options_df=options_df,
                symbol="SPX",
                provider="tradier",
                timestamp_seconds=1.0,
            )
            assert first_update_entered.wait(timeout=1)

            future_two = executor.submit(
                analytics.enrich_snapshot_with_advanced_analytics,
                snapshot_two,
                options_df=options_df,
                symbol="SPX",
                provider="tradier",
                timestamp_seconds=2.0,
            )

            try:
                assert not overlap_detected.wait(timeout=0.1)
            finally:
                release_first_update.set()

            future_one.result(timeout=1)
            future_two.result(timeout=1)

        assert snapshot_one.advanced_analytics is not None
        assert snapshot_two.advanced_analytics is not None

    def test_enrichment_restores_state_and_snapshot_when_kalman_update_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FakeEngine:
            def __init__(self) -> None:
                self.state = {"updates": 0}

            def snapshot_state(self) -> dict[str, int]:
                return dict(self.state)

            def restore_state(self, state: dict[str, int]) -> None:
                self.state = dict(state)

            def update(
                self,
                options_df: pd.DataFrame,
                timestamp: float,
                *,
                spot_price: float | None = None,
                provider_mode: str | None = None,
            ) -> HawkesState:
                del options_df, timestamp
                assert spot_price == 5805.0
                assert provider_mode == "tradier_rich"
                self.state["updates"] += 1
                return HawkesState(
                    call_intensity=1.0,
                    put_intensity=0.5,
                    net_toxicity=0.5,
                    squeeze_probability=0.25,
                )

        class FakeKalmanFilter:
            def __init__(self) -> None:
                self.state = {"updates": 0}

            def snapshot_state(self) -> dict[str, int]:
                return dict(self.state)

            def restore_state(self, state: dict[str, int]) -> None:
                self.state = dict(state)

            def update(self, measurement: float) -> float:
                del measurement
                self.state["updates"] += 1
                raise RuntimeError("kalman blew up")

        engine = FakeEngine()
        kalman = FakeKalmanFilter()
        original_advanced = AdvancedAnalytics(
            hawkes=HawkesStateModel(
                call_intensity=9.0,
                put_intensity=3.0,
                net_toxicity=6.0,
                squeeze_probability=0.8,
            ),
            smoothed_net_gex=-123.0,
        )
        snapshot = _build_snapshot(advanced=original_advanced)

        monkeypatch.setattr(analytics, "get_hawkes_engine", lambda **_: engine)
        monkeypatch.setattr(analytics, "get_kalman_filter", lambda **_: kalman)

        result = analytics.enrich_snapshot_with_advanced_analytics(
            snapshot,
            options_df=pd.DataFrame({"strike": [5800.0], "type": ["call"], "volume": [100]}),
            symbol="SPX",
            provider="tradier",
            timestamp_seconds=1.0,
        )

        assert result is snapshot
        assert snapshot.advanced_analytics == original_advanced
        assert engine.state == {"updates": 0}
        assert kalman.state == {"updates": 0}

    def test_enrichment_reraises_memory_error_after_restoring_state(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class FakeEngine:
            def __init__(self) -> None:
                self.state = {"updates": 0}

            def snapshot_state(self) -> dict[str, int]:
                return dict(self.state)

            def restore_state(self, state: dict[str, int]) -> None:
                self.state = dict(state)

            def update(
                self,
                options_df: pd.DataFrame,
                timestamp: float,
                *,
                spot_price: float | None = None,
                provider_mode: str | None = None,
            ) -> HawkesState:
                del options_df, timestamp
                assert spot_price == 5805.0
                assert provider_mode == "tradier_rich"
                self.state["updates"] += 1
                return HawkesState(
                    call_intensity=1.0,
                    put_intensity=0.5,
                    net_toxicity=0.5,
                    squeeze_probability=0.25,
                )

        class FakeKalmanFilter:
            def __init__(self) -> None:
                self.state = {"updates": 0}

            def snapshot_state(self) -> dict[str, int]:
                return dict(self.state)

            def restore_state(self, state: dict[str, int]) -> None:
                self.state = dict(state)

            def update(self, measurement: float) -> float:
                del measurement
                self.state["updates"] += 1
                raise MemoryError("out of memory")

        engine = FakeEngine()
        kalman = FakeKalmanFilter()
        snapshot = _build_snapshot()

        monkeypatch.setattr(analytics, "get_hawkes_engine", lambda **_: engine)
        monkeypatch.setattr(analytics, "get_kalman_filter", lambda **_: kalman)

        with pytest.raises(MemoryError, match="out of memory"):
            analytics.enrich_snapshot_with_advanced_analytics(
                snapshot,
                options_df=pd.DataFrame({"strike": [5800.0], "type": ["call"], "volume": [100]}),
                symbol="SPX",
                provider="tradier",
                timestamp_seconds=1.0,
            )

        assert engine.state == {"updates": 0}
        assert kalman.state == {"updates": 0}
