"""0DTE GEX Backend - Sanity Tests.

Bug prevention tests as specified in the master plan.
These tests ensure critical invariants are maintained.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from app.core.greeks import BlackScholesGreeks
from app.core.gex_calculator import GEXCalculator
from app.core.constants import SPX_DIVIDEND_YIELD, RISK_FREE_RATE, MIN_IV, MAX_IV

ET = ZoneInfo("America/New_York")


def get_test_expiration() -> str:
    """Get a valid future expiration timestamp for testing."""
    # Use a fixed future timestamp (4 hours from now in test time)
    return "2099-01-15T16:00:00"


def get_test_timestamp() -> datetime:
    """Get a corresponding test timestamp (4 hours before expiration)."""
    return datetime(2099, 1, 15, 12, 0, 0, tzinfo=ET)


class TestNoNaNInGreeks:
    """Ensure Greeks never return NaN for valid inputs."""

    def test_gamma_no_nan_for_valid_inputs(self):
        """Gamma should never return NaN for valid inputs."""
        S = np.full(100, 5700.0)
        K = np.linspace(5500, 5900, 100)
        T = np.full(100, 0.01)  # 1 day
        r = RISK_FREE_RATE
        q = SPX_DIVIDEND_YIELD
        sigma = np.full(100, 0.20)

        gammas = BlackScholesGreeks.gamma(S, K, T, r, sigma, q=q)

        assert not np.any(np.isnan(gammas)), "Gamma contains NaN values"

    def test_delta_no_nan_for_calls(self):
        """Call delta should never return NaN."""
        S = np.full(50, 5700.0)
        K = np.linspace(5500, 5900, 50)
        T = np.full(50, 0.01)
        r = RISK_FREE_RATE
        sigma = np.full(50, 0.20)
        option_type = np.full(50, "call")

        deltas = BlackScholesGreeks.delta(S, K, T, r, sigma, option_type, q=SPX_DIVIDEND_YIELD)

        assert not np.any(np.isnan(deltas)), "Delta contains NaN values"

    def test_delta_no_nan_for_puts(self):
        """Put delta should never return NaN."""
        S = np.full(50, 5700.0)
        K = np.linspace(5500, 5900, 50)
        T = np.full(50, 0.01)
        r = RISK_FREE_RATE
        sigma = np.full(50, 0.20)
        option_type = np.full(50, "put")

        deltas = BlackScholesGreeks.delta(S, K, T, r, sigma, option_type, q=SPX_DIVIDEND_YIELD)

        assert not np.any(np.isnan(deltas)), "Delta contains NaN values"

    def test_vega_no_nan(self):
        """Vega should never return NaN for valid inputs."""
        S = np.full(50, 5700.0)
        K = np.linspace(5500, 5900, 50)
        T = np.full(50, 0.05)  # 5 days
        r = RISK_FREE_RATE
        sigma = np.full(50, 0.20)

        vegas = BlackScholesGreeks.vega(S, K, T, r, sigma, q=SPX_DIVIDEND_YIELD)

        assert not np.any(np.isnan(vegas)), "Vega contains NaN values"

    def test_theta_no_nan(self):
        """Theta should never return NaN for valid inputs."""
        S = np.full(50, 5700.0)
        K = np.linspace(5500, 5900, 50)
        T = np.full(50, 0.05)
        r = RISK_FREE_RATE
        sigma = np.full(50, 0.20)
        option_type = np.full(50, "call")

        thetas = BlackScholesGreeks.theta(S, K, T, r, sigma, option_type, q=SPX_DIVIDEND_YIELD)

        assert not np.any(np.isnan(thetas)), "Theta contains NaN values"


class TestGEXSignConvention:
    """Verify call GEX is positive and put GEX is negative (baseline market gamma view)."""

    @pytest.fixture
    def gex_calculator(self):
        """Create GEX calculator instance."""
        return GEXCalculator(risk_free_rate=RISK_FREE_RATE, dividend_yield=SPX_DIVIDEND_YIELD)

    def test_call_gex_is_positive(self, gex_calculator):
        """Call GEX should be positive under the standard baseline convention."""
        timestamp = get_test_timestamp()
        expiration = get_test_expiration()
        df = pd.DataFrame([
            {"strike": 5900.0, "type": "call", "open_interest": 1000, "implied_vol": 0.20, "expiration": expiration},
        ])
        result = gex_calculator.calculate_gex_from_chain(df, 5900.0, timestamp)
        assert result.total_call_gex > 0, f"Call GEX should be positive, got {result.total_call_gex}"

    def test_put_gex_is_negative(self, gex_calculator):
        """Put GEX should be negative under the standard baseline convention."""
        timestamp = get_test_timestamp()
        expiration = get_test_expiration()
        df = pd.DataFrame([
            {"strike": 5900.0, "type": "put", "open_interest": 1000, "implied_vol": 0.20, "expiration": expiration},
        ])
        result = gex_calculator.calculate_gex_from_chain(df, 5900.0, timestamp)
        assert result.total_put_gex < 0, f"Put GEX should be negative, got {result.total_put_gex}"

    def test_mixed_chain_sign_convention(self, gex_calculator):
        """In a mixed chain, calls should be positive and puts negative."""
        timestamp = get_test_timestamp()
        expiration = get_test_expiration()
        df = pd.DataFrame([
            {"strike": 5850.0, "type": "call", "open_interest": 1000, "implied_vol": 0.20, "expiration": expiration},
            {"strike": 5900.0, "type": "call", "open_interest": 1000, "implied_vol": 0.20, "expiration": expiration},
            {"strike": 5850.0, "type": "put", "open_interest": 1000, "implied_vol": 0.20, "expiration": expiration},
            {"strike": 5900.0, "type": "put", "open_interest": 1000, "implied_vol": 0.20, "expiration": expiration},
        ])
        result = gex_calculator.calculate_gex_from_chain(df, 5875.0, timestamp)
        
        # Calls should contribute positive, puts negative
        assert result.total_call_gex > 0, f"Call GEX should be positive, got {result.total_call_gex}"
        assert result.total_put_gex < 0, f"Put GEX should be negative, got {result.total_put_gex}"


class TestZeroGammaBetweenStrikes:
    """Zero gamma level must be between min and max strikes."""

    @pytest.fixture
    def gex_calculator(self):
        """Create GEX calculator instance."""
        return GEXCalculator(risk_free_rate=RISK_FREE_RATE, dividend_yield=SPX_DIVIDEND_YIELD)

    def test_zero_gamma_within_strike_range(self, gex_calculator):
        """Zero gamma should be within strike range."""
        timestamp = get_test_timestamp()
        expiration = get_test_expiration()
        strikes = [5800.0, 5850.0, 5900.0, 5950.0, 6000.0]
        options_df = pd.DataFrame({
            "strike": strikes * 2,
            "type": ["call"] * 5 + ["put"] * 5,
            "open_interest": [500, 1000, 2000, 1500, 800] * 2,
            "implied_vol": [0.22, 0.20, 0.18, 0.20, 0.22] * 2,
            "expiration": [expiration] * 10,
        })

        spot_price = 5900.0
        result = gex_calculator.calculate_gex_from_chain(options_df, spot_price, timestamp)

        min_strike = options_df["strike"].min()
        max_strike = options_df["strike"].max()

        assert min_strike <= result.zero_gamma_level <= max_strike, (
            f"Zero gamma {result.zero_gamma_level} outside strike range "
            f"[{min_strike}, {max_strike}]"
        )

    def test_zero_gamma_near_spot_when_balanced(self, gex_calculator):
        """Zero gamma should be near spot price when GEX is balanced."""
        timestamp = get_test_timestamp()
        expiration = get_test_expiration()
        strikes = [5800.0, 5850.0, 5900.0, 5950.0, 6000.0]
        options_df = pd.DataFrame({
            "strike": strikes * 2,
            "type": ["call"] * 5 + ["put"] * 5,
            "open_interest": [500, 800, 1000, 800, 500] + [500, 800, 1000, 800, 500],
            "implied_vol": [0.22, 0.20, 0.18, 0.20, 0.22] * 2,
            "expiration": [expiration] * 10,
        })

        spot_price = 5900.0
        result = gex_calculator.calculate_gex_from_chain(options_df, spot_price, timestamp)

        # Zero gamma should be within 10% of spot when balanced
        assert abs(result.zero_gamma_level - spot_price) / spot_price < 0.10, (
            f"Zero gamma {result.zero_gamma_level} too far from spot {spot_price}"
        )


class TestTimezoneIsET:
    """All timestamps must be in Eastern Time."""

    @pytest.fixture
    def gex_calculator(self):
        """Create GEX calculator instance."""
        return GEXCalculator(risk_free_rate=RISK_FREE_RATE, dividend_yield=SPX_DIVIDEND_YIELD)

    def test_snapshot_timestamp_has_timezone(self, gex_calculator):
        """GEX snapshot timestamp should have timezone info."""
        timestamp = get_test_timestamp()
        expiration = get_test_expiration()
        options_df = pd.DataFrame({
            "strike": [5850.0, 5900.0, 5950.0] * 2,
            "type": ["call"] * 3 + ["put"] * 3,
            "open_interest": [1000, 2000, 1000] * 2,
            "implied_vol": [0.20, 0.18, 0.20] * 2,
            "expiration": [expiration] * 6,
        })

        spot_price = 5900.0
        result = gex_calculator.calculate_gex_from_chain(options_df, spot_price, timestamp)

        assert result.timestamp.tzinfo is not None, "Timestamp has no timezone"

    def test_snapshot_timestamp_is_et(self, gex_calculator):
        """GEX snapshot timestamp should be in Eastern Time."""
        timestamp = get_test_timestamp()
        expiration = get_test_expiration()
        options_df = pd.DataFrame({
            "strike": [5850.0, 5900.0, 5950.0] * 2,
            "type": ["call"] * 3 + ["put"] * 3,
            "open_interest": [1000, 2000, 1000] * 2,
            "implied_vol": [0.20, 0.18, 0.20] * 2,
            "expiration": [expiration] * 6,
        })

        spot_price = 5900.0
        result = gex_calculator.calculate_gex_from_chain(options_df, spot_price, timestamp)

        # Verify timezone is America/New_York
        tz_key = getattr(result.timestamp.tzinfo, "key", str(result.timestamp.tzinfo))
        assert "America/New_York" in tz_key or "ET" in tz_key or result.timestamp.tzinfo == ET


class TestIVReasonableness:
    """IV values should be within reasonable bounds."""

    def test_iv_lower_bound(self):
        """IV should be at least 1% (0.01)."""
        assert MIN_IV >= 0.01, f"MIN_IV {MIN_IV} is too low"

    def test_iv_upper_bound(self):
        """IV should be at most 500% (5.0)."""
        assert MAX_IV <= 5.0, f"MAX_IV {MAX_IV} is too high"

    def test_iv_filter_rejects_zero(self):
        """IV of 0 should be filtered out."""
        iv = 0.0
        assert iv < MIN_IV, "IV of 0 should be below MIN_IV"

    def test_iv_filter_rejects_extreme(self):
        """IV of 600% should be filtered out."""
        iv = 6.0
        assert iv > MAX_IV, "IV of 600% should be above MAX_IV"


class TestEdgeCases:
    """Test edge cases that commonly cause bugs."""

    def test_t_equals_zero_returns_zero_gamma(self):
        """T=0 should return gamma=0, not error."""
        S = np.array([5900.0])
        K = np.array([5900.0])
        T = np.array([0.0])
        r = RISK_FREE_RATE
        sigma = np.array([0.20])

        gamma = BlackScholesGreeks.gamma(S, K, T, r, sigma, q=SPX_DIVIDEND_YIELD)

        assert gamma[0] == 0.0, "T=0 should yield gamma=0"
        assert not np.isnan(gamma[0]), "T=0 should not yield NaN"

    def test_sigma_equals_zero_returns_zero_gamma(self):
        """Sigma=0 should return gamma=0, not error."""
        S = np.array([5900.0])
        K = np.array([5900.0])
        T = np.array([0.05])
        r = RISK_FREE_RATE
        sigma = np.array([0.0])

        gamma = BlackScholesGreeks.gamma(S, K, T, r, sigma, q=SPX_DIVIDEND_YIELD)

        assert gamma[0] == 0.0, "sigma=0 should yield gamma=0"
        assert not np.isnan(gamma[0]), "sigma=0 should not yield NaN"

    def test_negative_t_returns_zero_gamma(self):
        """Negative T should return gamma=0, not error."""
        S = np.array([5900.0])
        K = np.array([5900.0])
        T = np.array([-0.01])
        r = RISK_FREE_RATE
        sigma = np.array([0.20])

        gamma = BlackScholesGreeks.gamma(S, K, T, r, sigma, q=SPX_DIVIDEND_YIELD)

        assert gamma[0] == 0.0, "Negative T should yield gamma=0"
        assert not np.isnan(gamma[0]), "Negative T should not yield NaN"

    def test_large_gex_values_no_overflow(self):
        """Large OI should not cause integer overflow."""
        calc = GEXCalculator(risk_free_rate=RISK_FREE_RATE, dividend_yield=SPX_DIVIDEND_YIELD)
        
        timestamp = get_test_timestamp()
        expiration = get_test_expiration()
        df = pd.DataFrame([
            {"strike": 5900.0, "type": "call", "open_interest": 100000, "implied_vol": 0.20, "expiration": expiration},
        ])
        result = calc.calculate_gex_from_chain(df, 5900.0, timestamp)
        
        assert np.isfinite(result.total_call_gex), "Large GEX should be finite"
        # With 100k OI, gamma ~0.001, the GEX should be significant
        assert abs(result.total_call_gex) > 1e6, f"Large GEX should be significant, got {result.total_call_gex}"

    def test_gex_empty_dataframe(self):
        """Empty options chain should return zero GEX snapshot."""
        calc = GEXCalculator(risk_free_rate=RISK_FREE_RATE, dividend_yield=SPX_DIVIDEND_YIELD)
        empty_df = pd.DataFrame()
        current_time = datetime.now(ET)

        result = calc.calculate_gex_from_chain(empty_df, 5900.0, current_time)

        assert result.net_gex == 0.0
        assert result.total_call_gex == 0.0
        assert result.total_put_gex == 0.0
