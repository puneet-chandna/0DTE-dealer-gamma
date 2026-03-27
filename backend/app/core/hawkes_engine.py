"""0DTE GEX Backend - Hawkes Process Engine.

Snapshot-based pseudo-Hawkes process that measures order flow
momentum/toxicity by tracking volume deltas between polling intervals.

The Hawkes conditional intensity:
    λ(t) = μ + Σ α × e^(-β × (t - t_i))

In our discrete adaptation:
    intensity_new = intensity_old × e^(-β × Δt) + α × ΔVolume

A spike in call_intensity means call buying is self-reinforcing.
A spike in put_intensity means put buying is self-reinforcing.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from app.core.constants import (
    HAWKES_ALPHA,
    HAWKES_BETA,
    HAWKES_VOLUME_THRESHOLD,
)

logger = logging.getLogger(__name__)


@dataclass
class HawkesState:
    """Current state of the Hawkes process."""

    call_intensity: float = 0.0
    put_intensity: float = 0.0
    net_toxicity: float = 0.0       # call_intensity - put_intensity
    squeeze_probability: float = 0.0  # normalized 0-1


class HawkesEngine:
    """
    Snapshot-based pseudo-Hawkes process for options order flow.

    On each options chain snapshot, we compute the change in volume (ΔVol)
    per strike since the last snapshot. Significant ΔVol events increase
    the call or put intensity, which then decays exponentially over time.

    Usage:
        engine = HawkesEngine()
        # On each polling cycle:
        state = engine.update(options_df, timestamp_seconds)
    """

    def __init__(
        self,
        alpha: float = HAWKES_ALPHA,
        beta: float = HAWKES_BETA,
        volume_threshold: int = HAWKES_VOLUME_THRESHOLD,
    ):
        self.alpha = alpha
        self.beta = beta
        self.volume_threshold = volume_threshold

        # Internal state
        self._call_intensity: float = 0.0
        self._put_intensity: float = 0.0
        self._last_volumes: Dict[str, int] = {}  # "strike_type" -> volume
        self._last_timestamp: Optional[float] = None
        self._max_observed_intensity: float = 1.0  # for normalization

    def update(
        self,
        options_df: pd.DataFrame,
        timestamp: Optional[float] = None,
    ) -> HawkesState:
        """
        Update the Hawkes state with a new options chain snapshot.

        Args:
            options_df: DataFrame with columns: strike, type, volume
            timestamp: Unix timestamp of this snapshot (auto-generated if None)

        Returns:
            Current HawkesState after update.
        """
        if timestamp is None:
            timestamp = time.time()

        if options_df.empty:
            return self.get_state()

        # Check if volume column exists
        if "volume" not in options_df.columns:
            logger.debug("No 'volume' column in options_df, skipping Hawkes update")
            return self.get_state()

        # Calculate time delta
        if self._last_timestamp is not None:
            dt = timestamp - self._last_timestamp
            if dt <= 0:
                dt = 1.0  # safety
        else:
            dt = 5.0  # default 5 seconds for first update

        # Apply exponential decay to existing intensities
        decay = np.exp(-self.beta * dt)
        self._call_intensity *= decay
        self._put_intensity *= decay

        # Build current volume map
        current_volumes: Dict[str, int] = {}
        call_delta_volume = 0
        put_delta_volume = 0

        for _, row in options_df.iterrows():
            strike = row.get("strike", 0)
            opt_type = row.get("type", "")
            volume = int(row.get("volume", 0))

            key = f"{strike}_{opt_type}"
            current_volumes[key] = volume

            # Calculate delta from previous snapshot
            if self._last_volumes:
                prev_volume = self._last_volumes.get(key, 0)
                delta = max(0, volume - prev_volume)  # only count increases

                if delta >= self.volume_threshold:
                    if opt_type == "call":
                        call_delta_volume += delta
                    elif opt_type == "put":
                        put_delta_volume += delta

        # Update intensities with new events
        if call_delta_volume > 0:
            self._call_intensity += self.alpha * call_delta_volume
        if put_delta_volume > 0:
            self._put_intensity += self.alpha * put_delta_volume

        # Track max for normalization
        current_max = max(self._call_intensity, self._put_intensity)
        if current_max > self._max_observed_intensity:
            self._max_observed_intensity = current_max

        # Save state for next update
        self._last_volumes = current_volumes
        self._last_timestamp = timestamp

        state = self.get_state()

        logger.debug(
            f"Hawkes update: call_intensity={state.call_intensity:.4f}, "
            f"put_intensity={state.put_intensity:.4f}, "
            f"squeeze_prob={state.squeeze_probability:.4f}"
        )

        return state

    def get_state(self) -> HawkesState:
        """Get the current Hawkes state without updating."""
        net_toxicity = self._call_intensity - self._put_intensity

        # Squeeze probability: normalize net intensity to 0-1 range
        # High call intensity in short gamma = squeeze
        if self._max_observed_intensity > 0:
            raw_prob = abs(net_toxicity) / self._max_observed_intensity
            squeeze_probability = min(1.0, raw_prob)
        else:
            squeeze_probability = 0.0

        return HawkesState(
            call_intensity=round(self._call_intensity, 6),
            put_intensity=round(self._put_intensity, 6),
            net_toxicity=round(net_toxicity, 6),
            squeeze_probability=round(squeeze_probability, 6),
        )

    def snapshot_state(self) -> dict[str, Any]:
        """Capture the full mutable engine state for rollback-safe updates."""
        return {
            "call_intensity": self._call_intensity,
            "put_intensity": self._put_intensity,
            "last_volumes": dict(self._last_volumes),
            "last_timestamp": self._last_timestamp,
            "max_observed_intensity": self._max_observed_intensity,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore a previously captured engine state."""
        required_keys = (
            "call_intensity",
            "put_intensity",
            "max_observed_intensity",
        )
        missing_keys = [key for key in required_keys if key not in state]
        if missing_keys:
            raise ValueError(
                f"restore_state missing required keys: {', '.join(missing_keys)}"
            )

        last_volumes = state.get("last_volumes")
        last_timestamp = state.get("last_timestamp")
        try:
            call_intensity = float(state["call_intensity"])
            put_intensity = float(state["put_intensity"])
            max_observed_intensity = float(state["max_observed_intensity"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "restore_state requires numeric call_intensity, put_intensity, "
                "and max_observed_intensity values"
            ) from exc

        restored_last_volumes = dict(last_volumes) if isinstance(last_volumes, dict) else {}
        restored_last_timestamp = (
            float(last_timestamp)
            if isinstance(last_timestamp, int | float)
            else None
        )

        self._call_intensity = call_intensity
        self._put_intensity = put_intensity
        self._last_volumes = restored_last_volumes
        self._last_timestamp = restored_last_timestamp
        self._max_observed_intensity = max_observed_intensity

    def reset(self) -> None:
        """Reset the engine state (e.g., at market open)."""
        self._call_intensity = 0.0
        self._put_intensity = 0.0
        self._last_volumes = {}
        self._last_timestamp = None
        self._max_observed_intensity = 1.0
        logger.info("Hawkes engine state reset")
