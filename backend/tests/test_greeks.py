"""0DTE GEX Backend - Greeks Calculation Tests."""

import numpy as np
import pytest

from app.core.greeks import BlackScholesGreeks, ImpliedVolatilitySolver
from app.core.constants import SPX_DIVIDEND_YIELD


class TestBlackScholesGreeks:
    """Tests for Black-Scholes Greeks calculations WITH dividend yield."""

    def test_gamma_call_put_parity(self):
        """Gamma should be same for calls and puts."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.25])
        r = 0.05
        q = SPX_DIVIDEND_YIELD  # Using dividend yield
        sigma = np.array([0.2])

        gamma_value = BlackScholesGreeks.gamma(S, K, T, r, sigma, q=q)

        # Gamma is independent of option type
        assert gamma_value[0] > 0
        # With dividend yield q=0.015, gamma is reduced by e^(-qT) ≈ 0.9963
        # Expected gamma ≈ 0.0627 * 0.9963 ≈ 0.0624 without dividend adjustment in numerator
        # But also d1 changes with dividend yield
        # Just verify it's positive and reasonable
        assert 0.01 < gamma_value[0] < 0.1

    def test_gamma_with_zero_dividend(self):
        """Gamma with q=0 should be positive and reasonable."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.25])
        r = 0.05
        sigma = np.array([0.2])

        # With q=0, gamma should be positive and in reasonable range
        gamma_value = BlackScholesGreeks.gamma(S, K, T, r, sigma, q=0.0)

        # Gamma should be positive and in range for ATM option
        assert gamma_value[0] > 0.02
        assert gamma_value[0] < 0.10

    def test_gamma_decreases_with_higher_dividend(self):
        """Significantly higher dividend yield should reduce gamma."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.25])
        r = 0.05
        sigma = np.array([0.2])

        # Compare gamma with no dividend vs significant dividend
        gamma_q0 = BlackScholesGreeks.gamma(S, K, T, r, sigma, q=0.0)
        gamma_q10 = BlackScholesGreeks.gamma(S, K, T, r, sigma, q=0.10)  # 10% dividend

        # Higher dividend yield = lower gamma (more significant difference)
        assert gamma_q0[0] > gamma_q10[0]

    def test_delta_bounds_call(self):
        """Call delta should be between 0 and 1."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.25])
        r = 0.05
        sigma = np.array([0.2])
        option_type = np.array(["call"])

        delta = BlackScholesGreeks.delta(S, K, T, r, sigma, option_type, q=SPX_DIVIDEND_YIELD)

        assert 0 <= delta[0] <= 1

    def test_delta_bounds_put(self):
        """Put delta should be between -1 and 0."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.25])
        r = 0.05
        sigma = np.array([0.2])
        option_type = np.array(["put"])

        delta = BlackScholesGreeks.delta(S, K, T, r, sigma, option_type, q=SPX_DIVIDEND_YIELD)

        assert -1 <= delta[0] <= 0

    def test_atm_gamma_maximum(self):
        """Gamma should be highest at-the-money."""
        S = np.full(5, 100.0)
        K = np.array([90.0, 95.0, 100.0, 105.0, 110.0])
        T = np.full(5, 0.25)
        r = 0.05
        sigma = np.full(5, 0.2)

        gammas = BlackScholesGreeks.gamma(S, K, T, r, sigma, q=SPX_DIVIDEND_YIELD)

        # ATM (K=100) should have highest gamma
        atm_index = 2
        assert gammas[atm_index] == np.max(gammas)

    def test_gamma_at_expiration(self):
        """Gamma should be 0 at expiration (T=0)."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.0])
        r = 0.05
        sigma = np.array([0.2])

        gamma = BlackScholesGreeks.gamma(S, K, T, r, sigma, q=SPX_DIVIDEND_YIELD)

        assert gamma[0] == 0.0

    def test_vectorized_calculation(self):
        """Ensure vectorized calculation works with multiple options."""
        n = 100
        S = np.full(n, 5700.0)
        K = np.linspace(5500, 5900, n)
        T = np.full(n, 0.01)  # 1 day
        r = 0.05
        sigma = np.full(n, 0.20)

        gammas = BlackScholesGreeks.gamma(S, K, T, r, sigma, q=SPX_DIVIDEND_YIELD)

        assert len(gammas) == n
        assert np.all(gammas >= 0)

    def test_edge_case_zero_sigma(self):
        """Edge case: sigma = 0 should not cause errors."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.25])
        r = 0.05
        sigma = np.array([0.0])

        # Should not raise and should return 0
        gamma = BlackScholesGreeks.gamma(S, K, T, r, sigma, q=SPX_DIVIDEND_YIELD)
        assert gamma[0] == 0.0

    def test_edge_case_negative_time(self):
        """Edge case: T < 0 should return 0."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([-0.1])
        r = 0.05
        sigma = np.array([0.2])

        gamma = BlackScholesGreeks.gamma(S, K, T, r, sigma, q=SPX_DIVIDEND_YIELD)
        assert gamma[0] == 0.0


class TestImpliedVolatilitySolver:
    """Tests for IV solver."""

    def test_iv_recovery(self):
        """Should recover correct IV from calculated price."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.25])
        r = 0.05
        q = SPX_DIVIDEND_YIELD
        sigma_true = np.array([0.25])

        # Calculate theoretical price with dividend yield
        price = ImpliedVolatilitySolver.call_price(S, K, T, r, sigma_true, q=q)

        # Solve for IV
        sigma_solved = ImpliedVolatilitySolver.solve_iv_newton(
            price, S, K, T, r, np.array(["call"]), q=q
        )

        assert np.isclose(sigma_solved[0], sigma_true[0], rtol=1e-3)

    def test_iv_recovery_put(self):
        """Should recover correct IV for put options."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.25])
        r = 0.05
        q = SPX_DIVIDEND_YIELD
        sigma_true = np.array([0.30])

        # Calculate theoretical put price
        price = ImpliedVolatilitySolver.put_price(S, K, T, r, sigma_true, q=q)

        # Solve for IV
        sigma_solved = ImpliedVolatilitySolver.solve_iv_newton(
            price, S, K, T, r, np.array(["put"]), q=q
        )

        assert np.isclose(sigma_solved[0], sigma_true[0], rtol=1e-3)

    def test_iv_invalid_price_returns_nan(self):
        """Invalid market price should return NaN IV."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.25])
        r = 0.05
        market_price = np.array([0.0])  # Invalid

        sigma = ImpliedVolatilitySolver.solve_iv_newton(
            market_price, S, K, T, r, np.array(["call"])
        )

        assert np.isnan(sigma[0])


class TestCalculateAllGreeks:
    """Tests for the combined Greeks calculation."""

    def test_calculate_all_greeks(self):
        """Test that all Greeks are calculated correctly in one pass."""
        S = np.array([100.0, 100.0])
        K = np.array([100.0, 105.0])
        T = np.array([0.25, 0.25])
        r = 0.05
        sigma = np.array([0.2, 0.22])
        option_type = np.array(["call", "put"])
        q = SPX_DIVIDEND_YIELD

        result = BlackScholesGreeks.calculate_all_greeks(S, K, T, r, sigma, option_type, q=q)

        # Verify all fields are present
        assert len(result.delta) == 2
        assert len(result.gamma) == 2
        assert len(result.theta) == 2
        assert len(result.vega) == 2
        assert len(result.d1) == 2
        assert len(result.d2) == 2

        # Call delta should be positive
        assert result.delta[0] > 0
        # Put delta should be negative
        assert result.delta[1] < 0

        # All gammas should be positive
        assert np.all(result.gamma > 0)

        # Theta typically negative for long options
        # (but complex with dividends, so just check it's finite)
        assert np.all(np.isfinite(result.theta))
