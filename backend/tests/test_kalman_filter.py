"""Tests for the Kalman Filter."""

import numpy as np

from app.core.kalman_filter import GEXKalmanFilter


class TestGEXKalmanFilter:
    """Tests for the 1D Kalman filter."""

    def test_first_measurement_initializes(self):
        """First measurement should set the estimate directly."""
        kf = GEXKalmanFilter()

        result = kf.update(42.0)
        assert result == 42.0
        assert kf.is_initialized

    def test_smoothing_reduces_noise(self):
        """Smoothed output should have less variance than raw measurements."""
        kf = GEXKalmanFilter(process_noise=0.001, measurement_noise=0.1)
        np.random.seed(42)

        true_value = 5.0
        noisy_measurements = true_value + np.random.randn(100) * 0.5
        smoothed = [kf.update(m) for m in noisy_measurements]

        # Last few smoothed values should be closer to true value than raw
        raw_errors = np.abs(noisy_measurements[-10:] - true_value)
        smooth_errors = np.abs(np.array(smoothed[-10:]) - true_value)

        assert np.mean(smooth_errors) < np.mean(raw_errors)

    def test_handles_nan_gracefully(self):
        """NaN measurements should not corrupt the filter state."""
        kf = GEXKalmanFilter()
        kf.update(10.0)
        kf.update(11.0)

        # NaN input should return previous estimate
        result = kf.update(float("nan"))
        assert np.isfinite(result)

    def test_handles_inf_gracefully(self):
        """Inf measurements should not corrupt the filter state."""
        kf = GEXKalmanFilter()
        kf.update(10.0)

        result = kf.update(float("inf"))
        assert np.isfinite(result)

    def test_step_response_converges(self):
        """After a step change, filter should converge to new value."""
        kf = GEXKalmanFilter(process_noise=0.01, measurement_noise=0.1)

        # Feed constant 0 for a while
        for _ in range(20):
            kf.update(0.0)

        # Step change to 10
        smoothed = []
        for _ in range(50):
            smoothed.append(kf.update(10.0))

        # Should converge close to 10
        assert abs(smoothed[-1] - 10.0) < 1.0

    def test_kalman_gain_decreases(self):
        """Kalman gain should decrease as the filter becomes more certain."""
        kf = GEXKalmanFilter(process_noise=0.001, measurement_noise=0.1)

        kf.update(1.0)
        gain_early = kf.kalman_gain

        for _ in range(20):
            kf.update(1.0)

        gain_late = kf.kalman_gain
        assert gain_late < gain_early

    def test_reset(self):
        """Reset should clear filter state."""
        kf = GEXKalmanFilter()
        kf.update(42.0)
        kf.update(43.0)

        kf.reset()
        assert not kf.is_initialized
        assert kf.current_estimate == 0.0

    def test_current_estimate_before_init(self):
        """current_estimate should return 0 before initialization."""
        kf = GEXKalmanFilter()
        assert kf.current_estimate == 0.0
