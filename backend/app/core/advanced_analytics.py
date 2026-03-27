"""Shared advanced analytics enrichment for live and cached snapshots."""

from __future__ import annotations

import logging
import threading
import time
from typing import Dict, Optional, Tuple

import pandas as pd

from app.core.hawkes_engine import HawkesEngine
from app.core.kalman_filter import GEXKalmanFilter
from app.models.schemas import AdvancedAnalytics, GEXSnapshot, HawkesStateModel

logger = logging.getLogger(__name__)

StreamKey = Tuple[str, str]

_hawkes_engines: Dict[StreamKey, HawkesEngine] = {}
_kalman_filters: Dict[StreamKey, GEXKalmanFilter] = {}
_analytics_lock = threading.Lock()
_stream_locks = {}


def _normalize_stream_key(*, symbol: str, provider: str) -> StreamKey:
    """Use a stable provider/symbol key so each data stream keeps its own state."""
    return (provider.strip().lower(), symbol.strip().upper())


def _resolve_provider_mode(provider: str) -> str:
    """Map provider names to the Hawkes provider-mode labels."""
    normalized = provider.strip().lower()
    if normalized in {"tradier", "tradier_rich"}:
        return "tradier_rich"
    return "yfinance_proxy"


def get_hawkes_engine(*, symbol: str, provider: str) -> HawkesEngine:
    """Get or create the Hawkes engine for one provider/symbol stream."""
    key = _normalize_stream_key(symbol=symbol, provider=provider)
    with _analytics_lock:
        engine = _hawkes_engines.get(key)
        if engine is None:
            engine = HawkesEngine()
            _hawkes_engines[key] = engine
        return engine


def get_kalman_filter(*, symbol: str, provider: str) -> GEXKalmanFilter:
    """Get or create the Kalman filter for one provider/symbol stream."""
    key = _normalize_stream_key(symbol=symbol, provider=provider)
    with _analytics_lock:
        kalman = _kalman_filters.get(key)
        if kalman is None:
            kalman = GEXKalmanFilter()
            _kalman_filters[key] = kalman
        return kalman


def _get_stream_lock(*, symbol: str, provider: str):
    """Get or create the per-stream lock for one provider/symbol stream."""
    key = _normalize_stream_key(symbol=symbol, provider=provider)
    with _analytics_lock:
        stream_lock = _stream_locks.get(key)
        if stream_lock is None:
            stream_lock = threading.Lock()
            _stream_locks[key] = stream_lock
        return stream_lock


def reset_advanced_analytics_state(*, symbol: Optional[str] = None, provider: Optional[str] = None) -> None:
    """Reset cached state for tests or lifecycle boundaries."""
    if symbol is None and provider is None:
        with _analytics_lock:
            _hawkes_engines.clear()
            _kalman_filters.clear()
            _stream_locks.clear()
        return

    if symbol is None or provider is None:
        raise ValueError("symbol and provider must both be provided when resetting one stream")

    key = _normalize_stream_key(symbol=symbol, provider=provider)
    with _analytics_lock:
        _hawkes_engines.pop(key, None)
        _kalman_filters.pop(key, None)
        _stream_locks.pop(key, None)


def enrich_snapshot_with_advanced_analytics(
    snapshot: GEXSnapshot,
    *,
    options_df: pd.DataFrame,
    symbol: str,
    provider: str,
    timestamp_seconds: Optional[float] = None,
) -> GEXSnapshot:
    """Attach Hawkes and Kalman analytics to a snapshot without breaking the caller on failure."""
    if timestamp_seconds is None:
        snapshot_timestamp = getattr(snapshot, "timestamp", None)
        if hasattr(snapshot_timestamp, "timestamp"):
            timestamp_seconds = snapshot_timestamp.timestamp()
        else:
            timestamp_seconds = time.time()

    stream_lock = _get_stream_lock(symbol=symbol, provider=provider)
    hawkes_engine = get_hawkes_engine(symbol=symbol, provider=provider)
    kalman_filter = get_kalman_filter(symbol=symbol, provider=provider)

    with stream_lock:
        hawkes_pre_state = hawkes_engine.snapshot_state()
        kalman_pre_state = kalman_filter.snapshot_state()

        try:
            hawkes_state = hawkes_engine.update(
                options_df,
                timestamp_seconds,
                spot_price=snapshot.spot_price,
                provider_mode=_resolve_provider_mode(provider),
            )
            smoothed_gex = kalman_filter.update(snapshot.net_gex)

            advanced = (
                snapshot.advanced_analytics.model_copy(deep=True)
                if snapshot.advanced_analytics is not None
                else AdvancedAnalytics()
            )
            advanced.hawkes = HawkesStateModel(
                call_intensity=hawkes_state.call_intensity,
                put_intensity=hawkes_state.put_intensity,
                net_toxicity=hawkes_state.net_toxicity,
                squeeze_probability=hawkes_state.squeeze_probability,
                baseline_ready=hawkes_state.baseline_ready,
                confidence_score=hawkes_state.confidence_score,
                provider_mode=hawkes_state.provider_mode,
                event_count=hawkes_state.event_count,
            )
            advanced.smoothed_net_gex = smoothed_gex
            snapshot.advanced_analytics = advanced
        except MemoryError:
            hawkes_engine.restore_state(hawkes_pre_state)
            kalman_filter.restore_state(kalman_pre_state)
            raise
        except Exception as exc:
            hawkes_engine.restore_state(hawkes_pre_state)
            kalman_filter.restore_state(kalman_pre_state)
            logger.warning(
                "Advanced analytics enrichment failed for %s/%s: %s",
                provider,
                symbol,
                exc,
            )

    return snapshot
