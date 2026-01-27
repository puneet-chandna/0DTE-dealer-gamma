"""0DTE GEX Backend - Greeks Calculation Tests."""

import numpy as np
import pytest

from app.core.greeks import BlackScholesGreeks, ImpliedVolatilitySolver


class TestBlackScholesGreeks:
    """Tests for Black-Scholes Greeks calculations."""

    def test_gamma_call_put_parity(self):
        """Gamma should be same for calls and puts."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.25])
        r = 0.05
        sigma = np.array([0.2])

        gamma_value = BlackScholesGreeks.gamma(S, K, T, r, sigma)

        # Gamma is independent of option type
        assert gamma_value[0] > 0
        assert np.isclose(gamma_value[0], 0.0627, atol=0.001)

    def test_delta_bounds_call(self):
        """Call delta should be between 0 and 1."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.25])
        r = 0.05
        sigma = np.array([0.2])
        option_type = np.array(["call"])

        delta = BlackScholesGreeks.delta(S, K, T, r, sigma, option_type)

        assert 0 <= delta[0] <= 1

    def test_delta_bounds_put(self):
        """Put delta should be between -1 and 0."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.25])
        r = 0.05
        sigma = np.array([0.2])
        option_type = np.array(["put"])

        delta = BlackScholesGreeks.delta(S, K, T, r, sigma, option_type)

        assert -1 <= delta[0] <= 0

    def test_atm_gamma_maximum(self):
        """Gamma should be highest at-the-money."""
        S = np.full(5, 100.0)
        K = np.array([90.0, 95.0, 100.0, 105.0, 110.0])
        T = np.full(5, 0.25)
        r = 0.05
        sigma = np.full(5, 0.2)

        gammas = BlackScholesGreeks.gamma(S, K, T, r, sigma)

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

        gamma = BlackScholesGreeks.gamma(S, K, T, r, sigma)

        assert gamma[0] == 0.0

    def test_vectorized_calculation(self):
        """Ensure vectorized calculation works with multiple options."""
        n = 100
        S = np.full(n, 5700.0)
        K = np.linspace(5500, 5900, n)
        T = np.full(n, 0.01)  # 1 day
        r = 0.05
        sigma = np.full(n, 0.20)

        gammas = BlackScholesGreeks.gamma(S, K, T, r, sigma)

        assert len(gammas) == n
        assert np.all(gammas >= 0)


class TestImpliedVolatilitySolver:
    """Tests for IV solver."""

    def test_iv_recovery(self):
        """Should recover correct IV from calculated price."""
        S = np.array([100.0])
        K = np.array([100.0])
        T = np.array([0.25])
        r = 0.05
        sigma_true = np.array([0.25])

        # Calculate theoretical price
        price = ImpliedVolatilitySolver.call_price(S, K, T, r, sigma_true)

        # Solve for IV
        sigma_solved = ImpliedVolatilitySolver.solve_iv_newton(
            price, S, K, T, r, np.array(["call"])
        )

        assert np.isclose(sigma_solved[0], sigma_true[0], rtol=1e-3)
