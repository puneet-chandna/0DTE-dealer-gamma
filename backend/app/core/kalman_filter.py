"""0DTE GEX Backend - Kalman Filter for Signal Smoothing.

Lightweight 1D Kalman Filter (pure NumPy, no external dependencies)
that smooths noisy GEX and Hawkes intensity signals before they
reach the frontend.

Eliminates random data glitches from yfinance and makes the dashboard
feel institutional-grade.
"""

import logging
from typing import Any

import numpy as np

from app.core.constants import (
    KALMAN_MEASUREMENT_NOISE,
    KALMAN_PROCESS_NOISE,
)

logger = logging.getLogger(__name__)


class GEXKalmanFilter:
    """
    1D Kalman Filter for smoothing noisy time-series signals.

    State model:  x_k = x_{k-1} + w_k   (random walk)
    Observation:  z_k = x_k + v_k

    Where:
        w_k ~ N(0, Q)  process noise
        v_k ~ N(0, R)  measurement noise

    Usage:
        kf = GEXKalmanFilter()
        smoothed = kf.update(noisy_measurement)
    """

    def __init__(
        self,
        process_noise: float = KALMAN_PROCESS_NOISE,
        measurement_noise: float = KALMAN_MEASUREMENT_NOISE,
        initial_estimate: float | None = None,
        initial_error: float = 1.0,
    ):
        """
        Initialize the Kalman Filter.

        Args:
            process_noise: Q - variance of process noise (how much true state drifts)
            measurement_noise: R - variance of measurement noise (how noisy readings are)
            initial_estimate: Starting estimate (None = use first measurement)
            initial_error: Initial estimation error covariance
        """
        self.Q = process_noise
        self.R = measurement_noise

        # State
        self._x: float | None = initial_estimate  # Current estimate
        self._P: float = initial_error                # Estimation error covariance
        self._initialized: bool = initial_estimate is not None
        self._update_count: int = 0

    def predict(self) -> float:
        """
        Prediction step: project state forward.

        For a random walk model: x_predicted = x_current
        P_predicted = P_current + Q
        """
        if not self._initialized:
            return 0.0

        # In a random walk, the predicted state is the same as current
        # P grows by Q (uncertainty increases)
        self._P += self.Q

        return self._x

    def update(self, measurement: float) -> float:
        """
        Full predict + update step. Returns the smoothed estimate.

        Args:
            measurement: Raw noisy measurement (e.g., raw net_gex value)

        Returns:
            Smoothed estimate after Kalman filtering.
        """
        # Handle NaN/Inf measurements gracefully
        if not np.isfinite(measurement):
            logger.warning(f"Kalman filter received non-finite measurement: {measurement}")
            return self._x if self._initialized else 0.0

        # First measurement initializes the filter
        if not self._initialized:
            self._x = measurement
            self._initialized = True
            self._update_count = 1
            return self._x

        # Predict step
        self.predict()

        # Update step
        # Kalman gain: K = P / (P + R)
        kalman_gain = self._P / (self._P + self.R)

        # Innovation (residual)
        innovation = measurement - self._x

        # Updated estimate
        self._x = self._x + kalman_gain * innovation

        # Updated error covariance
        self._P = (1 - kalman_gain) * self._P

        self._update_count += 1

        return self._x

    @property
    def current_estimate(self) -> float:
        """Get the current smoothed estimate without updating."""
        return self._x if self._initialized else 0.0

    @property
    def kalman_gain(self) -> float:
        """Get the current Kalman gain (0 = trusts state, 1 = trusts measurement)."""
        if not self._initialized:
            return 1.0
        return self._P / (self._P + self.R)

    @property
    def is_initialized(self) -> bool:
        """Whether the filter has received at least one measurement."""
        return self._initialized

    def snapshot_state(self) -> dict[str, Any]:
        """Capture the mutable filter state for rollback-safe updates."""
        return {
            "x": self._x,
            "P": self._P,
            "initialized": self._initialized,
            "update_count": self._update_count,
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore a previously captured filter state."""
        x = state["x"]
        self._x = float(x) if isinstance(x, int | float) else None
        self._P = float(state["P"])
        self._initialized = bool(state["initialized"])
        self._update_count = int(state["update_count"])

    def reset(self, initial_estimate: float | None = None) -> None:
        """Reset the filter state."""
        self._x = initial_estimate
        self._P = 1.0
        self._initialized = initial_estimate is not None
        self._update_count = 0
        logger.debug("Kalman filter reset")
