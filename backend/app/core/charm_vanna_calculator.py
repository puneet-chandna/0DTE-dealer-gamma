"""0DTE GEX Backend - Charm & Vanna Flow Calculator.

Calculates "hidden" dealer hedging flows from:
- Charm: Delta decay from time passing (even if spot doesn't move)
- Vanna: Delta change from IV changing (even if spot doesn't move)

These are the invisible structural forces that move the market.
"""

import logging

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from app.core.constants import (
    CHARM_TIME_ADVANCE_MINUTES,
    CONTRACT_MULTIPLIER,
    RISK_FREE_RATE,
    SPX_DIVIDEND_YIELD,
    VANNA_IV_BUMP,
)
from app.core.greeks import BlackScholesGreeks

logger = logging.getLogger(__name__)


class CharmVannaCalculator:
    """
    Calculate dealer Charm & Vanna exposure from options chain data.

    Charm Flow: Expected dealer hedging volume purely from time decay.
        "Even if the market doesn't move, dealers must buy/sell X futures
         because 30 minutes passed."

    Vanna Flow: Expected dealer hedging volume from a 1% IV change.
        "If IV drops 1%, dealers must buy/sell X futures to rebalance."

    Dealer positioning conventions (same as GEX):
    - Dealers SHORT calls → Charm/Vanna adjustments are NEGATIVE for calls
    - Dealers LONG puts → Charm/Vanna adjustments are POSITIVE for puts
    """

    def __init__(
        self,
        risk_free_rate: float = RISK_FREE_RATE,
        dividend_yield: float = SPX_DIVIDEND_YIELD,
        time_advance_minutes: int = CHARM_TIME_ADVANCE_MINUTES,
        iv_bump: float = VANNA_IV_BUMP,
    ):
        self.risk_free_rate = risk_free_rate
        self.dividend_yield = dividend_yield
        self.time_advance_minutes = time_advance_minutes
        self.iv_bump = iv_bump

    def calculate_charm_flow(
        self,
        strikes: NDArray[np.float64],
        option_types: NDArray[np.str_],
        open_interest: NDArray[np.float64],
        implied_vol: NDArray[np.float64],
        time_to_expiration: NDArray[np.float64],
        spot_price: float,
    ) -> tuple[float, dict[float, float]]:
        """
        Calculate expected dealer hedging flow from Charm (time decay).

        Returns:
            (total_charm_flow, charm_by_strike)
            - Positive flow = dealers must BUY futures (upward pressure)
            - Negative flow = dealers must SELL futures (downward pressure)
        """
        if len(strikes) == 0:
            return 0.0, {}

        spot_vector = np.full_like(strikes, spot_price)

        # Calculate Charm for all contracts
        charms = BlackScholesGreeks.charm(
            spot_vector,
            strikes,
            time_to_expiration,
            self.risk_free_rate,
            implied_vol,
            option_types,
            q=self.dividend_yield,
        )

        # Charm flow: OI × Charm × 100 (contract multiplier)
        # Charm already has the per-day rate; scale by time_advance fraction
        time_fraction = self.time_advance_minutes / (24 * 60)  # fraction of a day
        charm_flow_raw = open_interest * charms * CONTRACT_MULTIPLIER * time_fraction

        # Apply dealer positioning: calls negative, puts positive
        is_call = option_types == "call"
        charm_flow = np.where(is_call, -charm_flow_raw, charm_flow_raw)

        # Aggregate by strike
        charm_by_strike = self._aggregate_by_strike(strikes, charm_flow)

        total_charm_flow = float(np.sum(charm_flow))

        return total_charm_flow, charm_by_strike

    def calculate_vanna_flow(
        self,
        strikes: NDArray[np.float64],
        option_types: NDArray[np.str_],
        open_interest: NDArray[np.float64],
        implied_vol: NDArray[np.float64],
        time_to_expiration: NDArray[np.float64],
        spot_price: float,
    ) -> tuple[float, dict[float, float]]:
        """
        Calculate expected dealer hedging flow from Vanna (IV change).

        Simulates what happens if IV changes by self.iv_bump (-1% by default).

        Returns:
            (total_vanna_flow, vanna_by_strike)
            - Positive flow = dealers must BUY futures (upward pressure)
            - Negative flow = dealers must SELL futures (downward pressure)
        """
        if len(strikes) == 0:
            return 0.0, {}

        spot_vector = np.full_like(strikes, spot_price)

        # Calculate Vanna for all contracts
        vannas = BlackScholesGreeks.vanna(
            spot_vector,
            strikes,
            time_to_expiration,
            self.risk_free_rate,
            implied_vol,
            q=self.dividend_yield,
        )

        # Vanna flow: OI × Vanna × ΔIV × 100
        vanna_flow_raw = open_interest * vannas * self.iv_bump * CONTRACT_MULTIPLIER

        # Apply dealer positioning: calls negative, puts positive
        is_call = option_types == "call"
        vanna_flow = np.where(is_call, -vanna_flow_raw, vanna_flow_raw)

        # Aggregate by strike
        vanna_by_strike = self._aggregate_by_strike(strikes, vanna_flow)

        total_vanna_flow = float(np.sum(vanna_flow))

        return total_vanna_flow, vanna_by_strike

    def calculate_all(
        self,
        options_df: pd.DataFrame,
        spot_price: float,
        time_to_expiration: NDArray[np.float64],
    ) -> dict:
        """
        Calculate both Charm and Vanna flows from an options DataFrame.

        Args:
            options_df: DataFrame with columns: strike, type, open_interest, implied_vol
            spot_price: Current underlying price
            time_to_expiration: Time to expiration array (in years), aligned with
                options_df rows

        Returns:
            Dictionary with charm_flow, vanna_flow, net_hidden_flow, and per-strike breakdowns.
        """
        if options_df.empty:
            return {
                "charm_flow": 0.0,
                "vanna_flow": 0.0,
                "net_hidden_flow": 0.0,
                "charm_by_strike": {},
                "vanna_by_strike": {},
            }

        strikes = options_df["strike"].values.astype(np.float64)
        option_types = options_df["type"].values
        open_interest = options_df["open_interest"].values.astype(np.float64)
        implied_vol = options_df["implied_vol"].values.astype(np.float64)

        charm_flow, charm_by_strike = self.calculate_charm_flow(
            strikes,
            option_types,
            open_interest,
            implied_vol,
            time_to_expiration,
            spot_price,
        )

        vanna_flow, vanna_by_strike = self.calculate_vanna_flow(
            strikes,
            option_types,
            open_interest,
            implied_vol,
            time_to_expiration,
            spot_price,
        )

        net_hidden_flow = charm_flow + vanna_flow

        logger.debug(
            f"Hidden flows: Charm={charm_flow/1e6:.2f}M, "
            f"Vanna={vanna_flow/1e6:.2f}M, Net={net_hidden_flow/1e6:.2f}M"
        )

        return {
            "charm_flow": charm_flow,
            "vanna_flow": vanna_flow,
            "net_hidden_flow": net_hidden_flow,
            "charm_by_strike": charm_by_strike,
            "vanna_by_strike": vanna_by_strike,
        }

    @staticmethod
    def _aggregate_by_strike(
        strikes: NDArray[np.float64],
        values: NDArray[np.float64],
    ) -> dict[float, float]:
        """Aggregate values by strike price."""
        if len(strikes) == 0:
            return {}
        unique_strikes = np.unique(strikes)
        result: dict[float, float] = {}
        for strike in unique_strikes:
            mask = strikes == strike
            result[float(strike)] = float(np.sum(values[mask]))
        return result
