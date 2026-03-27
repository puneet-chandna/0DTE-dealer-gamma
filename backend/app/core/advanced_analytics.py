"""Shared advanced analytics enrichment for live and cached snapshots."""

from __future__ import annotations

import logging
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


def _normalize_stream_key(*, symbol: str, provider: str) -> StreamKey:
    """Use a stable provider/symbol key so each data stream keeps its own state."""
    return (provider.strip().lower(), symbol.strip().upper())


def get_hawkes_engine(*, symbol: str, provider: str) -> HawkesEngine:
    """Get or create the Hawkes engine for one provider/symbol stream."""
    key = _normalize_stream_key(symbol=symbol, provider=provider)
    engine = _hawkes_engines.get(key)
    if engine is None:
        engine = HawkesEngine()
        _hawkes_engines[key] = engine
    return engine


def get_kalman_filter(*, symbol: str, provider: str) -> GEXKalmanFilter:
    """Get or create the Kalman filter for one provider/symbol stream."""
    key = _normalize_stream_key(symbol=symbol, provider=provider)
    kalman = _kalman_filters.get(key)
    if kalman is None:
        kalman = GEXKalmanFilter()
        _kalman_filters[key] = kalman
    return kalman


def reset_advanced_analytics_state(*, symbol: Optional[str] = None, provider: Optional[str] = None) -> None:
    """Reset cached state for tests or lifecycle boundaries."""
    if symbol is None and provider is None:
        _hawkes_engines.clear()
        _kalman_filters.clear()
        return

    if symbol is None or provider is None:
        raise ValueError("symbol and provider must both be provided when resetting one stream")

    key = _normalize_stream_key(symbol=symbol, provider=provider)
    _hawkes_engines.pop(key, None)
    _kalman_filters.pop(key, None)


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

    try:
        hawkes_state = get_hawkes_engine(symbol=symbol, provider=provider).update(
            options_df,
            timestamp_seconds,
        )
        smoothed_gex = get_kalman_filter(symbol=symbol, provider=provider).update(snapshot.net_gex)

        advanced = snapshot.advanced_analytics or AdvancedAnalytics()
        advanced.hawkes = HawkesStateModel(
            call_intensity=hawkes_state.call_intensity,
            put_intensity=hawkes_state.put_intensity,
            net_toxicity=hawkes_state.net_toxicity,
            squeeze_probability=hawkes_state.squeeze_probability,
        )
        advanced.smoothed_net_gex = smoothed_gex
        snapshot.advanced_analytics = advanced
    except Exception as exc:
        logger.warning("Advanced analytics enrichment failed for %s/%s: %s", provider, symbol, exc)

    return snapshot
