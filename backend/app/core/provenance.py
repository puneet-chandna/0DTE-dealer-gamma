"""Data identity and clocks; a receipt timestamp never proves quote freshness."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from app.models.schemas import DataProvenance


def source_timestamp(value: object, *, unix: bool = False) -> str | None:
    """Normalize supplied timestamps, leaving absent/invalid source clocks unknown."""
    try:
        if value is None or pd.isna(value):
            return None
        if unix:
            number = float(value)
            if number <= 0:
                return None
            parsed = pd.to_datetime(number, unit="ms" if number >= 1e12 else "s", utc=True)
        else:
            parsed = pd.to_datetime(value, utc=True)
        return None if pd.isna(parsed) else parsed.isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def live_capture_metadata(options_df: pd.DataFrame) -> dict:
    """Record feature completion separately from pricing and provider receipt time."""
    metadata = dict(options_df.attrs.get("source_metadata", {}))
    metadata["feature_available_at"] = datetime.now(ZoneInfo("America/New_York")).isoformat()
    return metadata


def data_provenance(
    frame: pd.DataFrame, *, provider: str, symbol: str, synthetic: bool = False
) -> DataProvenance:
    metadata = dict(frame.attrs.get("source_metadata", {}))
    is_proxy = bool(metadata.get("is_proxy", provider == "yfinance" and symbol.upper() == "SPX"))
    limitations = list(frame.attrs.get("quality_limitations", []))
    limitations.append(
        "Synthetic scenario; no market evidence."
        if synthetic
        else "Source quote freshness is not certified; captured prices are sampled observations."
    )
    if not synthetic:
        limitations.append(
            "Open interest is daily information; the exact as-of date may be unknown."
        )
    if is_proxy:
        limitations.append(
            "SPY options and open interest are an SPX proxy, not measured SPX dealer inventory."
        )
    return DataProvenance(
        provider=provider,
        requested_symbol=symbol.upper(),
        actual_instrument=str(
            metadata.get("actual_instrument", "SPY" if is_proxy else symbol.upper())
        ),
        is_proxy=is_proxy,
        data_kind="synthetic" if synthetic else "captured",
        sample_count=len(frame),
        actual_start=frame.index.min() if len(frame) else None,
        actual_end=frame.index.max() if len(frame) else None,
        timestamp_basis="generated scenario clock"
        if synthetic
        else str(
            frame.attrs.get("timestamp_basis", "capture reference; feature completion unknown")
        ),
        nominal_options_delay_minutes=15
        if provider == "yfinance" and not synthetic
        else metadata.get("nominal_options_delay_minutes"),
        calculation_versions=list(frame.attrs.get("calculation_versions", [])),
        quality_limitations=list(dict.fromkeys(limitations)),
    )
