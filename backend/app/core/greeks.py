"""0DTE GEX Backend - Vectorized Black-Scholes Greeks Calculations.

CRITICAL: All calculations use NumPy vectorization. No Python loops.
"""

import numpy as np
from numpy.typing import NDArray
from scipy.stats import norm


class BlackScholesGreeks:
    """
    Vectorized Black-Scholes-Merton Greeks calculations.

    Convention:
    - Volatility (sigma) is annualized
    - Time to expiration (T) is in years
    - Interest rate (r) is annualized
    """

    @staticmethod
    def d1(
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        r: float,
        sigma: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        """Calculate d1 parameter (vectorized)."""
        # Handle T=0 case to avoid division by zero
        with np.errstate(divide="ignore", invalid="ignore"):
            result = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
            result = np.where(T <= 0, 0.0, result)
        return result

    @staticmethod
    def d2(
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        r: float,
        sigma: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        """Calculate d2 parameter (vectorized)."""
        return BlackScholesGreeks.d1(S, K, T, r, sigma) - sigma * np.sqrt(T)

    @staticmethod
    def gamma(
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        r: float,
        sigma: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        """
        Calculate Gamma (∂²V/∂S²) - vectorized.

        Note: Gamma is same for calls and puts (put-call parity).
        """
        d1 = BlackScholesGreeks.d1(S, K, T, r, sigma)

        with np.errstate(divide="ignore", invalid="ignore"):
            gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
            # Handle T=0 case: Gamma is 0 at expiration
            gamma = np.where(T <= 0, 0.0, gamma)
            # Handle NaN/Inf
            gamma = np.nan_to_num(gamma, nan=0.0, posinf=0.0, neginf=0.0)

        return gamma

    @staticmethod
    def delta(
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        r: float,
        sigma: NDArray[np.float64],
        option_type: NDArray[np.str_],
    ) -> NDArray[np.float64]:
        """Calculate Delta (∂V/∂S) - vectorized."""
        d1 = BlackScholesGreeks.d1(S, K, T, r, sigma)
        is_call = option_type == "call"

        # At expiration (T=0)
        call_delta_at_exp = np.where(S > K, 1.0, 0.0)
        put_delta_at_exp = np.where(S < K, -1.0, 0.0)

        # Normal case
        call_delta = norm.cdf(d1)
        put_delta = norm.cdf(d1) - 1

        # Select based on option type and expiration
        delta = np.where(
            T <= 0,
            np.where(is_call, call_delta_at_exp, put_delta_at_exp),
            np.where(is_call, call_delta, put_delta),
        )

        return delta

    @staticmethod
    def vega(
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        r: float,
        sigma: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        """Calculate Vega (∂V/∂σ) per 1% change - vectorized."""
        d1 = BlackScholesGreeks.d1(S, K, T, r, sigma)

        with np.errstate(invalid="ignore"):
            vega = S * norm.pdf(d1) * np.sqrt(T) / 100  # Per 1% change
            vega = np.where(T <= 0, 0.0, vega)
            vega = np.nan_to_num(vega, nan=0.0)

        return vega

    @staticmethod
    def theta(
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        r: float,
        sigma: NDArray[np.float64],
        option_type: NDArray[np.str_],
    ) -> NDArray[np.float64]:
        """Calculate Theta (∂V/∂t) per day - vectorized."""
        d1 = BlackScholesGreeks.d1(S, K, T, r, sigma)
        d2 = BlackScholesGreeks.d2(S, K, T, r, sigma)
        is_call = option_type == "call"

        with np.errstate(divide="ignore", invalid="ignore"):
            term1 = -(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T))

            call_term2 = -r * K * np.exp(-r * T) * norm.cdf(d2)
            put_term2 = r * K * np.exp(-r * T) * norm.cdf(-d2)

            theta = np.where(is_call, term1 + call_term2, term1 + put_term2) / 365
            theta = np.where(T <= 0, 0.0, theta)
            theta = np.nan_to_num(theta, nan=0.0)

        return theta


class ImpliedVolatilitySolver:
    """Solve for implied volatility using Newton-Raphson."""

    @staticmethod
    def call_price(
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        r: float,
        sigma: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        """Black-Scholes call price - vectorized."""
        d1 = BlackScholesGreeks.d1(S, K, T, r, sigma)
        d2 = BlackScholesGreeks.d2(S, K, T, r, sigma)
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)

    @staticmethod
    def put_price(
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        r: float,
        sigma: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        """Black-Scholes put price - vectorized."""
        d1 = BlackScholesGreeks.d1(S, K, T, r, sigma)
        d2 = BlackScholesGreeks.d2(S, K, T, r, sigma)
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

    @staticmethod
    def solve_iv_newton(
        market_price: NDArray[np.float64],
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        r: float,
        option_type: NDArray[np.str_],
        initial_guess: float = 0.2,
        max_iterations: int = 100,
        tolerance: float = 1e-6,
    ) -> NDArray[np.float64]:
        """
        Solve for implied volatility using Newton-Raphson - vectorized.

        Returns NaN for invalid inputs or convergence failures.
        """
        sigma = np.full_like(market_price, initial_guess)
        is_call = option_type == "call"

        for _ in range(max_iterations):
            # Calculate theoretical price
            theo_price = np.where(
                is_call,
                ImpliedVolatilitySolver.call_price(S, K, T, r, sigma),
                ImpliedVolatilitySolver.put_price(S, K, T, r, sigma),
            )

            # Calculate vega
            vega = BlackScholesGreeks.vega(S, K, T, r, sigma) * 100  # Undo /100

            # Newton-Raphson update
            diff = theo_price - market_price
            with np.errstate(divide="ignore", invalid="ignore"):
                sigma_new = sigma - diff / vega
                sigma_new = np.where(vega == 0, sigma, sigma_new)

            # Check convergence
            if np.all(np.abs(diff) < tolerance):
                break

            sigma = sigma_new

        # Validate results (IV should be between 1% and 300%)
        sigma = np.where((sigma < 0.01) | (sigma > 3.0), np.nan, sigma)
        sigma = np.where(T <= 0, np.nan, sigma)
        sigma = np.where(market_price <= 0, np.nan, sigma)

        return sigma
