"""0DTE GEX Backend - py_vollib Bridge for Greeks Validation & IV Surface.

Provides cross-validation of our custom Black-Scholes implementation
against py_vollib, and IV surface/skew computation helpers.
"""

import logging

import numpy as np
import pandas as pd

from app.core.constants import DEFAULT_RISK_FREE_RATE, SPX_DIVIDEND_YIELD

logger = logging.getLogger(__name__)


class VolLibBridge:
    """Bridge between our Greeks engine and py_vollib for validation and IV.

    Uses py_vollib's Black-Scholes implementation to:
    1. Cross-validate our custom Greeks calculations
    2. Compute implied volatility surfaces from market prices
    3. Calculate IV skew (put IV - call IV) across strikes
    """

    @staticmethod
    def _vollib_greeks(
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        option_type: str,
        q: float = 0.0,
    ) -> dict:
        """Calculate Greeks for a single option using py_vollib.

        Args:
            S: Spot price.
            K: Strike price.
            T: Time to expiration in years.
            r: Risk-free rate (annualized).
            sigma: Implied volatility (annualized).
            option_type: 'call' or 'put'.
            q: Dividend yield (note: py_vollib doesn't natively support q,
               so we use the forward price adjustment: S_adj = S * e^(-qT)).

        Returns:
            Dictionary with delta, gamma, vega, theta, rho.
        """
        from py_vollib.black_scholes.greeks import analytical as greeks

        # py_vollib uses 'c' and 'p' for option types
        flag = "c" if option_type == "call" else "p"

        # Adjust spot price for dividend yield (S_adj = S * e^(-qT))
        S_adj = S * np.exp(-q * T) if q > 0 else S

        try:
            delta = greeks.delta(flag, S_adj, K, T, r, sigma)
            gamma = greeks.gamma(flag, S_adj, K, T, r, sigma)
            vega = greeks.vega(flag, S_adj, K, T, r, sigma)
            theta = greeks.theta(flag, S_adj, K, T, r, sigma)
            rho = greeks.rho(flag, S_adj, K, T, r, sigma)
        except Exception as e:
            logger.warning(f"py_vollib Greeks calculation failed: {e}")
            return {
                "delta": float("nan"),
                "gamma": float("nan"),
                "vega": float("nan"),
                "theta": float("nan"),
                "rho": float("nan"),
            }

        return {
            "delta": delta,
            "gamma": gamma,
            "vega": vega / 100,  # Normalize to per 1% like our implementation
            "theta": theta / 365,  # Per day
            "rho": rho,
        }

    @staticmethod
    def validate_greeks(
        S: float,
        K: float,
        T: float,
        r: float = DEFAULT_RISK_FREE_RATE,
        sigma: float = 0.20,
        q: float = SPX_DIVIDEND_YIELD,
    ) -> dict:
        """Cross-validate our BS Greeks against py_vollib.

        Args:
            S: Spot price.
            K: Strike price.
            T: Time to expiration in years.
            r: Risk-free rate.
            sigma: Implied volatility.
            q: Dividend yield.

        Returns:
            Dictionary with 'our', 'vollib', and 'diff' sections for each Greek.
        """
        from app.core.greeks import BlackScholesGreeks

        S_arr = np.array([S])
        K_arr = np.array([K])
        T_arr = np.array([T])
        sigma_arr = np.array([sigma])

        results = {}
        for opt_type in ["call", "put"]:
            opt_arr = np.array([opt_type])

            # Our implementation
            our_greeks = BlackScholesGreeks.calculate_all_greeks(
                S_arr, K_arr, T_arr, r, sigma_arr, opt_arr, q=q
            )

            # py_vollib implementation
            vol_greeks = VolLibBridge._vollib_greeks(S, K, T, r, sigma, opt_type, q=q)

            results[opt_type] = {
                "our": {
                    "delta": float(our_greeks.delta[0]),
                    "gamma": float(our_greeks.gamma[0]),
                    "vega": float(our_greeks.vega[0]),
                    "theta": float(our_greeks.theta[0]),
                },
                "vollib": vol_greeks,
                "diff": {
                    "delta": abs(float(our_greeks.delta[0]) - vol_greeks["delta"]),
                    "gamma": abs(float(our_greeks.gamma[0]) - vol_greeks["gamma"]),
                    "vega": abs(float(our_greeks.vega[0]) - vol_greeks["vega"]),
                    "theta": abs(float(our_greeks.theta[0]) - vol_greeks["theta"]),
                },
            }

        return results

    @staticmethod
    def calculate_iv_surface(
        options_df: pd.DataFrame,
        spot_price: float,
        r: float = DEFAULT_RISK_FREE_RATE,
    ) -> pd.DataFrame:
        """Calculate IV surface from options market data using py_vollib.

        Args:
            options_df: DataFrame with columns: strike, type, mid (mid price),
                       and optionally implied_vol, expiration.
            spot_price: Current underlying price.
            r: Risk-free rate.

        Returns:
            DataFrame with columns: strike, type, iv, mid_price, moneyness.
        """
        from py_vollib.black_scholes.implied_volatility import implied_volatility

        results = []

        for _, row in options_df.iterrows():
            strike = float(row["strike"])
            option_type = str(row.get("type", row.get("option_type", "call")))
            mid_price = float(row.get("mid", 0.0))

            # Skip invalid prices
            if mid_price <= 0:
                continue

            flag = "c" if option_type == "call" else "p"

            # Default to ~1 day T if not provided
            T = float(row.get("T", 1 / 365))
            if T <= 0:
                T = 1e-10

            try:
                iv = implied_volatility(mid_price, spot_price, strike, T, r, flag)
                if iv <= 0 or iv > 5.0:  # Sanity check
                    continue
            except Exception:
                continue

            results.append(
                {
                    "strike": strike,
                    "type": option_type,
                    "iv": iv,
                    "mid_price": mid_price,
                    "moneyness": strike / spot_price,
                }
            )

        return pd.DataFrame(results)

    @staticmethod
    def calculate_iv_skew(iv_surface_df: pd.DataFrame) -> pd.DataFrame:
        """Calculate IV skew (put IV - call IV) at each strike.

        Args:
            iv_surface_df: Output from calculate_iv_surface().

        Returns:
            DataFrame with columns: strike, call_iv, put_iv, skew, moneyness.
        """
        if iv_surface_df.empty:
            return pd.DataFrame(columns=["strike", "call_iv", "put_iv", "skew", "moneyness"])

        calls = iv_surface_df[iv_surface_df["type"] == "call"].set_index("strike")
        puts = iv_surface_df[iv_surface_df["type"] == "put"].set_index("strike")

        # Join on common strikes
        common = calls.join(puts, lsuffix="_call", rsuffix="_put", how="inner")

        if common.empty:
            return pd.DataFrame(columns=["strike", "call_iv", "put_iv", "skew", "moneyness"])

        return pd.DataFrame(
            {
                "strike": common.index,
                "call_iv": common["iv_call"].values,
                "put_iv": common["iv_put"].values,
                "skew": common["iv_put"].values - common["iv_call"].values,
                "moneyness": common["moneyness_call"].values,
            }
        )
