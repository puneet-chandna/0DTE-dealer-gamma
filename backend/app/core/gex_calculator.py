"""0DTE GEX Backend - GEX Calculator Engine."""

from datetime import datetime
from typing import Dict, Tuple

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from app.core.greeks import BlackScholesGreeks
from app.models.schemas import GEXSnapshot


class GEXCalculator:
    """
    Calculate Dealer Gamma Exposure from options chain data.

    GEX Formula: GEX_i = OI_i × Γ_i × 100 × S²

    Dealer Positioning Assumptions:
    - Dealers are SHORT calls (customers buy calls) → Negative GEX
    - Dealers are LONG puts (customers buy puts) → Positive GEX

    Net GEX = Σ(GEX_puts) - Σ(GEX_calls)
    """

    CONTRACT_MULTIPLIER = 100  # Standard US options multiplier

    def __init__(self, risk_free_rate: float = 0.05):
        """Initialize with risk-free rate."""
        self.risk_free_rate = risk_free_rate

    def calculate_gex_from_chain(
        self,
        options_df: pd.DataFrame,
        spot_price: float,
        timestamp: datetime,
    ) -> GEXSnapshot:
        """
        Calculate GEX from options chain DataFrame.

        Expected columns: strike, type, open_interest, implied_vol, expiration
        """
        # Convert to numpy arrays for vectorized calculation
        strikes = options_df["strike"].values.astype(np.float64)
        option_types = options_df["type"].values
        open_interest = options_df["open_interest"].values.astype(np.float64)
        implied_vol = options_df["implied_vol"].values.astype(np.float64)

        # Calculate time to expiration in years
        expiration = pd.to_datetime(options_df["expiration"])
        T = ((expiration - timestamp).dt.total_seconds() / (365.25 * 24 * 3600)).values

        # Ensure T is positive (filter out expired)
        T = np.maximum(T, 0)

        # Vectorized spot price
        S = np.full_like(strikes, spot_price)

        # Calculate gamma for all contracts
        gammas = BlackScholesGreeks.gamma(S, strikes, T, self.risk_free_rate, implied_vol)

        # Calculate GEX per contract: OI × Γ × 100 × S²
        gex_raw = open_interest * gammas * self.CONTRACT_MULTIPLIER * (spot_price**2)

        # Apply dealer positioning: calls negative, puts positive
        is_call = option_types == "call"
        gex_adjusted = np.where(is_call, -gex_raw, gex_raw)

        # Aggregate by strike
        gex_by_strike = self._aggregate_by_strike(strikes, gex_adjusted)

        # Calculate totals
        total_call_gex = float(np.sum(gex_adjusted[is_call]))
        total_put_gex = float(np.sum(gex_adjusted[~is_call]))
        net_gex = total_call_gex + total_put_gex

        # Find zero gamma level
        zero_gamma_level = self._find_zero_gamma_level(gex_by_strike, spot_price)

        # Find dominant strike
        dominant_strike = max(gex_by_strike.keys(), key=lambda k: abs(gex_by_strike[k]))

        return GEXSnapshot(
            timestamp=timestamp,
            spot_price=spot_price,
            total_call_gex=total_call_gex,
            total_put_gex=total_put_gex,
            net_gex=net_gex,
            zero_gamma_level=zero_gamma_level,
            gex_by_strike=gex_by_strike,
            dominant_strike=dominant_strike,
            metrics={
                "gex_billions": net_gex / 1e9,
                "call_put_ratio": abs(total_call_gex / total_put_gex)
                if total_put_gex != 0
                else 0,
            },
        )

    def _aggregate_by_strike(
        self,
        strikes: NDArray[np.float64],
        gex_values: NDArray[np.float64],
    ) -> Dict[float, float]:
        """Aggregate GEX values by strike price."""
        unique_strikes = np.unique(strikes)
        gex_by_strike: Dict[float, float] = {}

        for strike in unique_strikes:
            mask = strikes == strike
            gex_by_strike[float(strike)] = float(np.sum(gex_values[mask]))

        return gex_by_strike

    def _find_zero_gamma_level(
        self,
        gex_by_strike: Dict[float, float],
        spot_price: float,
    ) -> float:
        """
        Find the Zero Gamma Level using linear interpolation.

        The ZGL is where the cumulative GEX curve crosses zero.
        """
        if not gex_by_strike:
            return spot_price

        # Sort strikes
        sorted_strikes = sorted(gex_by_strike.keys())
        cumulative_gex = np.cumsum([gex_by_strike[k] for k in sorted_strikes])

        # Find zero crossing
        for i in range(len(cumulative_gex) - 1):
            if cumulative_gex[i] * cumulative_gex[i + 1] < 0:
                # Linear interpolation
                x1, x2 = sorted_strikes[i], sorted_strikes[i + 1]
                y1, y2 = cumulative_gex[i], cumulative_gex[i + 1]
                zero_level = x1 - y1 * (x2 - x1) / (y2 - y1)
                return float(zero_level)

        # No crossing found, return spot price
        return spot_price

    def determine_regime(
        self,
        net_gex: float,
        threshold_billions: float = 1.0,
    ) -> Tuple[str, str, str]:
        """
        Determine market regime based on net GEX.

        Returns: (regime, description, color)
        """
        gex_billions = net_gex / 1e9

        if gex_billions < -threshold_billions:
            return (
                "short_gamma",
                "Dealers are short gamma - expect amplified volatility",
                "red",
            )
        elif gex_billions > threshold_billions:
            return (
                "long_gamma",
                "Dealers are long gamma - expect dampened volatility",
                "green",
            )
        else:
            return (
                "neutral",
                "Neutral positioning",
                "yellow",
            )
