"""0DTE GEX Backend - Vectorized Black-Scholes Greeks Calculations.

CRITICAL: All calculations use NumPy vectorization. No Python loops.
CRITICAL: SPX pays dividends - all formulas include dividend yield q.
"""

import logging
from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray
from scipy.stats import norm

from app.core.constants import (
    MIN_IV,
    MAX_IV,
    RISK_FREE_RATE,
    SPX_DIVIDEND_YIELD,
)

logger = logging.getLogger(__name__)


class GreeksResult(NamedTuple):
    """Container for all Greeks calculated in one pass."""

    delta: NDArray[np.float64]
    gamma: NDArray[np.float64]
    theta: NDArray[np.float64]
    vega: NDArray[np.float64]
    charm: NDArray[np.float64]
    vanna: NDArray[np.float64]
    d1: NDArray[np.float64]
    d2: NDArray[np.float64]


class BlackScholesGreeks:
    """
    Vectorized Black-Scholes-Merton Greeks calculations WITH dividend yield.

    Convention:
    - Volatility (sigma) is annualized
    - Time to expiration (T) is in years
    - Interest rate (r) is annualized
    - Dividend yield (q) is annualized (CRITICAL for SPX)
    """

    @staticmethod
    def _validate_inputs(
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        sigma: NDArray[np.float64],
    ) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
        """
        Validate and sanitize inputs to prevent numerical errors.

        Returns sanitized (T, sigma, valid_mask) arrays.
        """
        # Create validity mask
        valid_mask = np.ones(len(S), dtype=bool)

        # Check for NaN/Inf in inputs
        valid_mask &= np.isfinite(S) & np.isfinite(K) & np.isfinite(T) & np.isfinite(sigma)

        # Check sigma bounds
        sigma_valid = (sigma >= MIN_IV) & (sigma <= MAX_IV)
        if not np.all(sigma_valid):
            invalid_count = np.sum(~sigma_valid & valid_mask)
            if invalid_count > 0:
                logger.warning(f"Skipping {invalid_count} contracts with invalid IV (outside {MIN_IV*100:.0f}%-{MAX_IV*100:.0f}%)")
        valid_mask &= sigma_valid

        # Sanitize T (prevent division by zero)
        T_safe = np.maximum(T, 1e-10)

        # Sanitize sigma (prevent division by zero)
        sigma_safe = np.maximum(sigma, 1e-10)

        return T_safe, sigma_safe, valid_mask

    @staticmethod
    def d1(
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        r: float,
        q: float,
        sigma: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        """
        Calculate d1 parameter (vectorized) WITH dividend yield.

        Formula: d1 = (ln(S/K) + (r - q + σ²/2)T) / (σ√T)
        """
        with np.errstate(divide="ignore", invalid="ignore"):
            # Use safe values for T and sigma
            T_safe = np.maximum(T, 1e-10)
            sigma_safe = np.maximum(sigma, 1e-10)

            result = (np.log(S / K) + (r - q + 0.5 * sigma_safe**2) * T_safe) / (
                sigma_safe * np.sqrt(T_safe)
            )
            result = np.where(T <= 0, 0.0, result)
            result = np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)
        return result

    @staticmethod
    def d2(
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        r: float,
        q: float,
        sigma: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        """
        Calculate d2 parameter (vectorized) WITH dividend yield.

        Formula: d2 = d1 - σ√T
        """
        sigma_safe = np.maximum(sigma, 1e-10)
        T_safe = np.maximum(T, 1e-10)
        return BlackScholesGreeks.d1(S, K, T, r, q, sigma) - sigma_safe * np.sqrt(T_safe)

    @staticmethod
    def gamma(
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        r: float,
        sigma: NDArray[np.float64],
        q: float = SPX_DIVIDEND_YIELD,
    ) -> NDArray[np.float64]:
        """
        Calculate Gamma (∂²V/∂S²) - vectorized WITH dividend yield.

        Formula: Γ = e^(-qT) × N'(d1) / (S × σ × √T)

        Note: Gamma is same for calls and puts (put-call parity).
        """
        d1 = BlackScholesGreeks.d1(S, K, T, r, q, sigma)

        with np.errstate(divide="ignore", invalid="ignore"):
            T_safe = np.maximum(T, 1e-10)
            sigma_safe = np.maximum(sigma, 1e-10)

            # Include dividend yield discount factor
            discount = np.exp(-q * T_safe)
            gamma = discount * norm.pdf(d1) / (S * sigma_safe * np.sqrt(T_safe))

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
        q: float = SPX_DIVIDEND_YIELD,
    ) -> NDArray[np.float64]:
        """
        Calculate Delta (∂V/∂S) - vectorized WITH dividend yield.

        Formula (call): Δ = e^(-qT) × N(d1)
        Formula (put): Δ = e^(-qT) × (N(d1) - 1)
        """
        d1 = BlackScholesGreeks.d1(S, K, T, r, q, sigma)
        is_call = option_type == "call"
        T_safe = np.maximum(T, 1e-10)

        # Dividend discount factor
        discount = np.exp(-q * T_safe)

        # At expiration (T=0)
        call_delta_at_exp = np.where(S > K, 1.0, 0.0)
        put_delta_at_exp = np.where(S < K, -1.0, 0.0)

        # Normal case with dividend yield
        call_delta = discount * norm.cdf(d1)
        put_delta = discount * (norm.cdf(d1) - 1)

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
        q: float = SPX_DIVIDEND_YIELD,
    ) -> NDArray[np.float64]:
        """
        Calculate Vega (∂V/∂σ) per 1% change - vectorized WITH dividend yield.

        Formula: ν = S × e^(-qT) × N'(d1) × √T / 100
        """
        d1 = BlackScholesGreeks.d1(S, K, T, r, q, sigma)
        T_safe = np.maximum(T, 1e-10)

        # Dividend discount factor
        discount = np.exp(-q * T_safe)

        with np.errstate(invalid="ignore"):
            vega = S * discount * norm.pdf(d1) * np.sqrt(T_safe) / 100  # Per 1% change
            vega = np.where(T <= 0, 0.0, vega)
            vega = np.nan_to_num(vega, nan=0.0)

        return vega

    @staticmethod
    def charm(
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        r: float,
        sigma: NDArray[np.float64],
        option_type: NDArray[np.str_],
        q: float = SPX_DIVIDEND_YIELD,
    ) -> NDArray[np.float64]:
        """
        Calculate Charm (∂Δ/∂t) - Delta decay over time - vectorized WITH dividend yield.

        Charm measures how much Delta changes as time passes (all else equal).
        Critical for 0DTE: dealers must rehedge just because the clock ticks.

        Formula (call): Charm = -e^(-qT) × [N'(d1) × (2(r-q)T - d2σ√T) / (2Tσ√T)]
                                + q × e^(-qT) × N(d1)
        Formula (put):  Charm = -e^(-qT) × [N'(d1) × (2(r-q)T - d2σ√T) / (2Tσ√T)]
                                - q × e^(-qT) × N(-d1)

        Returns per-day Charm (divide by 365).
        """
        d1_val = BlackScholesGreeks.d1(S, K, T, r, q, sigma)
        d2_val = BlackScholesGreeks.d2(S, K, T, r, q, sigma)
        is_call = option_type == "call"

        T_safe = np.maximum(T, 1e-10)
        sigma_safe = np.maximum(sigma, 1e-10)
        sqrt_T = np.sqrt(T_safe)
        discount_q = np.exp(-q * T_safe)

        with np.errstate(divide="ignore", invalid="ignore"):
            pdf_d1 = norm.pdf(d1_val)

            # Common term for both calls and puts
            common = -discount_q * pdf_d1 * (
                (2.0 * (r - q) * T_safe - d2_val * sigma_safe * sqrt_T)
                / (2.0 * T_safe * sigma_safe * sqrt_T)
            )

            # Dividend adjustment differs by type
            call_charm = common + q * discount_q * norm.cdf(d1_val)
            put_charm = common - q * discount_q * norm.cdf(-d1_val)

            charm = np.where(is_call, call_charm, put_charm) / 365  # Per day
            charm = np.where(T <= 0, 0.0, charm)
            charm = np.nan_to_num(charm, nan=0.0, posinf=0.0, neginf=0.0)

        return charm

    @staticmethod
    def vanna(
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        r: float,
        sigma: NDArray[np.float64],
        q: float = SPX_DIVIDEND_YIELD,
    ) -> NDArray[np.float64]:
        """
        Calculate Vanna (∂Δ/∂σ = ∂Vega/∂S) - vectorized WITH dividend yield.

        Vanna measures how much Delta changes when IV changes.
        Critical for understanding hedging flows after IV crush/spike events.

        Formula: Vanna = -e^(-qT) × N'(d1) × d2 / σ

        Note: Vanna is the same for calls and puts (sign-agnostic on type,
        but dealer positioning sign is applied by the calculator).
        """
        d1_val = BlackScholesGreeks.d1(S, K, T, r, q, sigma)
        d2_val = BlackScholesGreeks.d2(S, K, T, r, q, sigma)

        T_safe = np.maximum(T, 1e-10)
        sigma_safe = np.maximum(sigma, 1e-10)
        discount_q = np.exp(-q * T_safe)

        with np.errstate(divide="ignore", invalid="ignore"):
            vanna = -discount_q * norm.pdf(d1_val) * d2_val / sigma_safe
            vanna = np.where(T <= 0, 0.0, vanna)
            vanna = np.nan_to_num(vanna, nan=0.0, posinf=0.0, neginf=0.0)

        return vanna

    @staticmethod
    def theta(
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        r: float,
        sigma: NDArray[np.float64],
        option_type: NDArray[np.str_],
        q: float = SPX_DIVIDEND_YIELD,
    ) -> NDArray[np.float64]:
        """
        Calculate Theta (∂V/∂t) per day - vectorized WITH dividend yield.

        Formula (call): θ = -[S × e^(-qT) × N'(d1) × σ / (2√T)]
                          - r × K × e^(-rT) × N(d2)
                          + q × S × e^(-qT) × N(d1)

        Formula (put): θ = -[S × e^(-qT) × N'(d1) × σ / (2√T)]
                         + r × K × e^(-rT) × N(-d2)
                         - q × S × e^(-qT) × N(-d1)
        """
        d1 = BlackScholesGreeks.d1(S, K, T, r, q, sigma)
        d2 = BlackScholesGreeks.d2(S, K, T, r, q, sigma)
        is_call = option_type == "call"

        T_safe = np.maximum(T, 1e-10)
        sigma_safe = np.maximum(sigma, 1e-10)

        with np.errstate(divide="ignore", invalid="ignore"):
            # Common term (same for calls and puts)
            term1 = -(S * np.exp(-q * T_safe) * norm.pdf(d1) * sigma_safe) / (2 * np.sqrt(T_safe))

            # Rate terms (different for calls and puts)
            call_rate_term = -r * K * np.exp(-r * T_safe) * norm.cdf(d2)
            put_rate_term = r * K * np.exp(-r * T_safe) * norm.cdf(-d2)

            # Dividend terms (different for calls and puts)
            call_div_term = q * S * np.exp(-q * T_safe) * norm.cdf(d1)
            put_div_term = -q * S * np.exp(-q * T_safe) * norm.cdf(-d1)

            # Combine terms
            call_theta = term1 + call_rate_term + call_div_term
            put_theta = term1 + put_rate_term + put_div_term

            theta = np.where(is_call, call_theta, put_theta) / 365  # Per day
            theta = np.where(T <= 0, 0.0, theta)
            theta = np.nan_to_num(theta, nan=0.0)

        return theta

    @staticmethod
    def calculate_all_greeks(
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        r: float,
        sigma: NDArray[np.float64],
        option_type: NDArray[np.str_],
        q: float = SPX_DIVIDEND_YIELD,
    ) -> GreeksResult:
        """
        Calculate all Greeks in a single pass for efficiency.

        Returns a GreeksResult namedtuple with all Greeks.
        """
        # Calculate d1 and d2 once (used by multiple Greeks)
        d1 = BlackScholesGreeks.d1(S, K, T, r, q, sigma)
        d2 = BlackScholesGreeks.d2(S, K, T, r, q, sigma)

        T_safe = np.maximum(T, 1e-10)
        sigma_safe = np.maximum(sigma, 1e-10)
        discount_q = np.exp(-q * T_safe)
        discount_r = np.exp(-r * T_safe)
        is_call = option_type == "call"
        pdf_d1 = norm.pdf(d1)
        sqrt_T = np.sqrt(T_safe)

        # Gamma (same for calls and puts)
        gamma = discount_q * pdf_d1 / (S * sigma_safe * sqrt_T)
        gamma = np.where(T <= 0, 0.0, gamma)
        gamma = np.nan_to_num(gamma, nan=0.0, posinf=0.0, neginf=0.0)

        # Delta
        call_delta = discount_q * norm.cdf(d1)
        put_delta = discount_q * (norm.cdf(d1) - 1)
        call_delta_at_exp = np.where(S > K, 1.0, 0.0)
        put_delta_at_exp = np.where(S < K, -1.0, 0.0)
        delta = np.where(
            T <= 0,
            np.where(is_call, call_delta_at_exp, put_delta_at_exp),
            np.where(is_call, call_delta, put_delta),
        )

        # Vega
        vega = S * discount_q * pdf_d1 * sqrt_T / 100
        vega = np.where(T <= 0, 0.0, vega)
        vega = np.nan_to_num(vega, nan=0.0)

        # Theta
        term1 = -(S * discount_q * pdf_d1 * sigma_safe) / (2 * sqrt_T)
        call_rate_term = -r * K * discount_r * norm.cdf(d2)
        put_rate_term = r * K * discount_r * norm.cdf(-d2)
        call_div_term = q * S * discount_q * norm.cdf(d1)
        put_div_term = -q * S * discount_q * norm.cdf(-d1)
        call_theta = term1 + call_rate_term + call_div_term
        put_theta = term1 + put_rate_term + put_div_term
        theta = np.where(is_call, call_theta, put_theta) / 365
        theta = np.where(T <= 0, 0.0, theta)
        theta = np.nan_to_num(theta, nan=0.0)

        # Charm (∂Δ/∂t)
        common_charm = -discount_q * pdf_d1 * (
            (2.0 * (r - q) * T_safe - d2 * sigma_safe * sqrt_T)
            / (2.0 * T_safe * sigma_safe * sqrt_T)
        )
        call_charm = common_charm + q * discount_q * norm.cdf(d1)
        put_charm = common_charm - q * discount_q * norm.cdf(-d1)
        charm = np.where(is_call, call_charm, put_charm) / 365
        charm = np.where(T <= 0, 0.0, charm)
        charm = np.nan_to_num(charm, nan=0.0, posinf=0.0, neginf=0.0)

        # Vanna (∂Δ/∂σ) — same for calls and puts
        vanna = -discount_q * pdf_d1 * d2 / sigma_safe
        vanna = np.where(T <= 0, 0.0, vanna)
        vanna = np.nan_to_num(vanna, nan=0.0, posinf=0.0, neginf=0.0)

        return GreeksResult(
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            charm=charm,
            vanna=vanna,
            d1=d1,
            d2=d2,
        )


class ImpliedVolatilitySolver:
    """Solve for implied volatility using Newton-Raphson WITH dividend yield."""

    @staticmethod
    def call_price(
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        r: float,
        sigma: NDArray[np.float64],
        q: float = SPX_DIVIDEND_YIELD,
    ) -> NDArray[np.float64]:
        """Black-Scholes call price - vectorized WITH dividend yield."""
        d1 = BlackScholesGreeks.d1(S, K, T, r, q, sigma)
        d2 = BlackScholesGreeks.d2(S, K, T, r, q, sigma)
        return S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)

    @staticmethod
    def put_price(
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        r: float,
        sigma: NDArray[np.float64],
        q: float = SPX_DIVIDEND_YIELD,
    ) -> NDArray[np.float64]:
        """Black-Scholes put price - vectorized WITH dividend yield."""
        d1 = BlackScholesGreeks.d1(S, K, T, r, q, sigma)
        d2 = BlackScholesGreeks.d2(S, K, T, r, q, sigma)
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)

    @staticmethod
    def solve_iv_newton(
        market_price: NDArray[np.float64],
        S: NDArray[np.float64],
        K: NDArray[np.float64],
        T: NDArray[np.float64],
        r: float,
        option_type: NDArray[np.str_],
        q: float = SPX_DIVIDEND_YIELD,
        initial_guess: float = 0.2,
        max_iterations: int = 100,
        tolerance: float = 1e-6,
    ) -> NDArray[np.float64]:
        """
        Solve for implied volatility using Newton-Raphson - vectorized WITH dividend yield.

        Returns NaN for invalid inputs or convergence failures.
        """
        sigma = np.full_like(market_price, initial_guess)
        is_call = option_type == "call"

        for _ in range(max_iterations):
            # Calculate theoretical price
            theo_price = np.where(
                is_call,
                ImpliedVolatilitySolver.call_price(S, K, T, r, sigma, q),
                ImpliedVolatilitySolver.put_price(S, K, T, r, sigma, q),
            )

            # Calculate vega (undo the /100 in vega calculation)
            vega = BlackScholesGreeks.vega(S, K, T, r, sigma, q) * 100

            # Newton-Raphson update
            diff = theo_price - market_price
            with np.errstate(divide="ignore", invalid="ignore"):
                sigma_new = sigma - diff / vega
                sigma_new = np.where(vega == 0, sigma, sigma_new)
                # Clamp to reasonable bounds during iteration
                sigma_new = np.clip(sigma_new, 0.001, 10.0)

            # Check convergence
            if np.all(np.abs(diff) < tolerance):
                break

            sigma = sigma_new

        # Validate results (IV should be between MIN_IV and MAX_IV)
        sigma = np.where((sigma < MIN_IV) | (sigma > MAX_IV), np.nan, sigma)
        sigma = np.where(T <= 0, np.nan, sigma)
        sigma = np.where(market_price <= 0, np.nan, sigma)

        return sigma
