"""Snapshot quality guards for replay and fallback selection."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import pandas as pd

from app.core.constants import MIN_IV
from app.models.schemas import GEXSnapshot

MEANINGFUL_GEX_ABS_THRESHOLD = 1_000_000.0
NEAR_SPOT_WINDOW_PCT = 0.015
EXTREME_GEX_IMBALANCE_RATIO = 100.0
MIN_WEAK_SIDE_NEAR_SPOT_CONTRACTS = 8
CORRUPTED_SIDE_THRESHOLD = 0.4

INSUFFICIENT_MEANINGFUL_STRIKES_FLAG = "insufficient_meaningful_strikes"
EXTREME_IMBALANCE_FLAG = "extreme_call_put_imbalance"
CALL_IV_CORRUPTED_FLAG = "call_iv_corrupted"
PUT_IV_CORRUPTED_FLAG = "put_iv_corrupted"


@dataclass(frozen=True)
class SnapshotQualityReport:
    """Quality verdict for one snapshot."""

    capture_quality: float
    quality_flags: tuple[str, ...]
    meaningful_strike_count: int
    is_replay_eligible: bool


def evaluate_snapshot_quality(
    snapshot_like: Any,
    *,
    options_df: Optional[pd.DataFrame] = None,
) -> SnapshotQualityReport:
    """Evaluate whether a snapshot is safe to reuse for replay/fallback."""
    snapshot = _coerce_snapshot_payload(snapshot_like)
    gex_by_strike = snapshot.get("gex_by_strike")
    meaningful_strike_count = _count_meaningful_strikes(gex_by_strike or {})
    quality_flags: list[str] = []

    if gex_by_strike is not None and meaningful_strike_count < 5:
        quality_flags.append(INSUFFICIENT_MEANINGFUL_STRIKES_FLAG)

    spot_price = _coerce_float(snapshot.get("spot_price"))
    total_call_abs = abs(_coerce_float(snapshot.get("total_call_gex")))
    total_put_abs = abs(_coerce_float(snapshot.get("total_put_gex")))
    imbalance_ratio = _get_gex_imbalance_ratio(total_call_abs, total_put_abs)

    if options_df is not None and not options_df.empty and spot_price > 0:
        near_spot_rows = _prepare_near_spot_contract_rows(options_df, spot_price=spot_price)

        if imbalance_ratio > EXTREME_GEX_IMBALANCE_RATIO:
            weak_side = "put" if total_call_abs >= total_put_abs else "call"
            weak_side_near_spot = near_spot_rows[
                (near_spot_rows["type"] == weak_side)
                & (near_spot_rows["open_interest"] > 0)
            ]
            if len(weak_side_near_spot) >= MIN_WEAK_SIDE_NEAR_SPOT_CONTRACTS:
                quality_flags.append(EXTREME_IMBALANCE_FLAG)

        for option_type, flag in (
            ("call", CALL_IV_CORRUPTED_FLAG),
            ("put", PUT_IV_CORRUPTED_FLAG),
        ):
            side_rows = near_spot_rows[
                (near_spot_rows["type"] == option_type)
                & (near_spot_rows["open_interest"] > 0)
            ]
            if side_rows.empty:
                continue

            corrupted_share = float((side_rows["implied_vol"] <= MIN_IV).mean())
            if corrupted_share >= CORRUPTED_SIDE_THRESHOLD:
                quality_flags.append(flag)

    quality_flags = list(dict.fromkeys(quality_flags))
    is_replay_eligible = not quality_flags
    capture_quality = 1.0 if is_replay_eligible else max(0.0, 1.0 - 0.34 * len(quality_flags))

    return SnapshotQualityReport(
        capture_quality=capture_quality,
        quality_flags=tuple(quality_flags),
        meaningful_strike_count=meaningful_strike_count,
        is_replay_eligible=is_replay_eligible,
    )


def annotate_snapshot_quality(
    snapshot_like: Any,
    *,
    options_df: Optional[pd.DataFrame] = None,
):
    """Merge snapshot quality metadata into a snapshot model or payload dict."""
    quality = evaluate_snapshot_quality(snapshot_like, options_df=options_df)
    payload = _coerce_snapshot_payload(snapshot_like)
    existing_metrics = _coerce_metrics(payload.get("metrics"))
    existing_quality_flags = existing_metrics.get("quality_flags")
    explicit_eligibility = _coerce_optional_bool(existing_metrics.get("is_replay_eligible"))
    existing_capture_quality = existing_metrics.get("capture_quality")
    existing_meaningful_strikes = existing_metrics.get("meaningful_strike_count")

    merged_quality_flags = list(quality.quality_flags)
    if isinstance(existing_quality_flags, list):
        merged_quality_flags = list(dict.fromkeys([*existing_quality_flags, *merged_quality_flags]))

    capture_quality = quality.capture_quality
    if isinstance(existing_capture_quality, (int, float)):
        capture_quality = min(float(existing_capture_quality), capture_quality)

    meaningful_strike_count = quality.meaningful_strike_count
    if isinstance(existing_meaningful_strikes, (int, float)):
        meaningful_strike_count = max(int(existing_meaningful_strikes), meaningful_strike_count)

    is_replay_eligible = quality.is_replay_eligible and not merged_quality_flags
    if explicit_eligibility is not None:
        is_replay_eligible = is_replay_eligible and explicit_eligibility

    merged_metrics = {
        **existing_metrics,
        "capture_quality": capture_quality,
        "quality_flags": merged_quality_flags,
        "meaningful_strike_count": meaningful_strike_count,
        "is_replay_eligible": is_replay_eligible,
    }

    if isinstance(snapshot_like, GEXSnapshot) and hasattr(snapshot_like, "model_copy"):
        return snapshot_like.model_copy(update={"metrics": merged_metrics})
    if isinstance(snapshot_like, Mapping):
        payload["metrics"] = merged_metrics
        return payload
    if (
        not isinstance(snapshot_like, Mapping)
        and not isinstance(snapshot_like, GEXSnapshot)
        and hasattr(snapshot_like, "__dict__")
    ):
        copied_snapshot = copy.copy(snapshot_like)
        copied_snapshot.metrics = merged_metrics
        return copied_snapshot

    payload["metrics"] = merged_metrics
    return payload


def is_snapshot_replay_eligible(snapshot_like: Any) -> bool:
    """Return whether a snapshot should be reused for replay/fallback."""
    payload = _coerce_snapshot_payload(snapshot_like)
    metrics = _coerce_metrics(payload.get("metrics"))

    explicit_eligibility = _coerce_optional_bool(metrics.get("is_replay_eligible"))
    if explicit_eligibility is not None:
        return explicit_eligibility

    quality_flags = metrics.get("quality_flags")
    if isinstance(quality_flags, list) and quality_flags:
        return False

    capture_quality = metrics.get("capture_quality")
    if isinstance(capture_quality, (int, float)):
        return float(capture_quality) > 0

    call_put_ratio = metrics.get("call_put_ratio")
    if isinstance(call_put_ratio, (int, float)):
        meaningful_strike_count = _count_meaningful_strikes(payload.get("gex_by_strike") or {})
        if (
            meaningful_strike_count < 5
            and float(call_put_ratio) > EXTREME_GEX_IMBALANCE_RATIO
        ):
            return False

    return True


def _prepare_near_spot_contract_rows(
    options_df: pd.DataFrame,
    *,
    spot_price: float,
) -> pd.DataFrame:
    """Normalize an options chain into a numeric near-spot working frame."""
    if options_df.empty:
        return pd.DataFrame(columns=["type", "strike", "open_interest", "implied_vol"])

    working = options_df.copy()
    working["type"] = _get_column_series(working, "type", "").astype(str).str.lower()
    working["strike"] = pd.to_numeric(
        _get_column_series(working, "strike"),
        errors="coerce",
    )
    working["open_interest"] = pd.to_numeric(
        _get_column_series(working, "open_interest", 0.0),
        errors="coerce",
    ).fillna(0.0)
    working["implied_vol"] = pd.to_numeric(
        _get_column_series(working, "implied_vol", 0.0),
        errors="coerce",
    ).fillna(0.0)

    distance_limit = abs(spot_price) * NEAR_SPOT_WINDOW_PCT
    return working[
        working["strike"].notna()
        & working["type"].isin({"call", "put"})
        & ((working["strike"] - spot_price).abs() <= distance_limit)
    ].copy()


def _count_meaningful_strikes(gex_by_strike: Mapping[Any, Any]) -> int:
    return sum(
        1
        for value in gex_by_strike.values()
        if isinstance(value, (int, float)) and abs(float(value)) >= MEANINGFUL_GEX_ABS_THRESHOLD
    )


def _get_gex_imbalance_ratio(total_call_abs: float, total_put_abs: float) -> float:
    stronger_side = max(total_call_abs, total_put_abs)
    weaker_side = min(total_call_abs, total_put_abs)
    return stronger_side / max(weaker_side, 1.0)


def _coerce_snapshot_payload(snapshot_like: Any) -> dict[str, Any]:
    if isinstance(snapshot_like, Mapping):
        return dict(snapshot_like)
    if isinstance(snapshot_like, GEXSnapshot) and hasattr(snapshot_like, "model_dump"):
        dumped = snapshot_like.model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)

    object_fields = vars(snapshot_like) if hasattr(snapshot_like, "__dict__") else {}
    payload = {
        "timestamp": object_fields.get("timestamp"),
        "spot_price": object_fields.get("spot_price"),
        "total_call_gex": object_fields.get("total_call_gex"),
        "total_put_gex": object_fields.get("total_put_gex"),
        "net_gex": object_fields.get("net_gex"),
        "zero_gamma_level": object_fields.get("zero_gamma_level"),
        "gex_by_strike": object_fields.get("gex_by_strike"),
        "dominant_strike": object_fields.get("dominant_strike"),
        "metrics": object_fields.get("metrics"),
    }
    if any(value is not None for value in payload.values()):
        return payload

    raise TypeError(f"Unsupported snapshot payload: {type(snapshot_like)!r}")


def _coerce_metrics(metrics_like: Any) -> dict[str, Any]:
    if isinstance(metrics_like, Mapping):
        return dict(metrics_like)
    return {}


def _coerce_optional_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return None


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _get_column_series(
    frame: pd.DataFrame,
    column: str,
    default: Any = None,
) -> pd.Series:
    if column in frame.columns:
        return frame[column]
    return pd.Series([default] * len(frame), index=frame.index)
