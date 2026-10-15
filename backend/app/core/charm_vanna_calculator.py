"""0DTE GEX Backend - Charm & Vanna Flow Calculator.

Calculates conditional dollar delta-hedge scenarios from:
- Charm: Delta decay from time passing (even if spot doesn't move)
- Vanna: Delta change from IV changing (even if spot doesn't move)

These scenarios assume call-positive/put-negative inventory; OI does not
identify actual dealer positions or executed trading flows.
"""

import logging

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from app.core.constants import (
    CHARM_TIME_ADVANCE_MINUTES,
    CONTRACT_MULTIPLIER,
    MAX_IV,
    MIN_IV,
    RISK_FREE_RATE,
    SPX_DIVIDEND_YIELD,
    VANNA_IV_BUMP,
)
from app.core.greeks import BlackScholesGreeks

logger = logging.getLogger(__name__)


class CharmVannaCalculator:
    """
    Dollar hedge changes under fixed-spot time and IV scenarios.

    Inventory follows the GEX convention: calls positive, puts negative.
    Hedge change is the negative inventory-weighted delta change, times the
    contract multiplier and spot. Positive means buying underlying notional.
    Scenario sums are additive diagnostics, not a joint time-and-IV repricing.
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
        Reprice delta after elapsed minutes, capped at each contract's expiry.

        Time to expiration is in years of 365.25 calendar days, as in GEX.

        Returns:
            (total_charm_flow, charm_by_strike)
            - Positive flow = buy underlying dollar notional
            - Negative flow = sell underlying dollar notional
        """
        if len(strikes) == 0:
            return 0.0, {}

        spot_vector = np.full_like(strikes, spot_price)

        delta_before = BlackScholesGreeks.delta(
            spot_vector,
            strikes,
            time_to_expiration,
            self.risk_free_rate,
            implied_vol,
            option_types,
            q=self.dividend_yield,
        )

        remaining_time = np.maximum(
            time_to_expiration - self.time_advance_minutes / (365.25 * 24 * 60), 0.0
        )
        delta_after = BlackScholesGreeks.delta(
            spot_vector,
            strikes,
            remaining_time,
            self.risk_free_rate,
            implied_vol,
            option_types,
            q=self.dividend_yield,
        )
        charm_flow_raw = (
            open_interest * (delta_after - delta_before) * CONTRACT_MULTIPLIER * spot_price
        )
        charm_flow_raw = np.where(time_to_expiration > 0, charm_flow_raw, 0.0)

        # The delta-neutral hedge changes opposite to assumed signed inventory.
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
        Reprice delta under an absolute annualized-IV bump at unchanged spot/time.

        IV is clamped to the supported bounds; -.01 means one volatility point.

        Returns:
            (total_vanna_flow, vanna_by_strike)
            - Positive flow = buy underlying dollar notional
            - Negative flow = sell underlying dollar notional
        """
        if len(strikes) == 0:
            return 0.0, {}

        spot_vector = np.full_like(strikes, spot_price)

        delta_before = BlackScholesGreeks.delta(
            spot_vector,
            strikes,
            time_to_expiration,
            self.risk_free_rate,
            implied_vol,
            option_types,
            q=self.dividend_yield,
        )

        delta_after = BlackScholesGreeks.delta(
            spot_vector,
            strikes,
            time_to_expiration,
            self.risk_free_rate,
            np.clip(implied_vol + self.iv_bump, MIN_IV, MAX_IV),
            option_types,
            q=self.dividend_yield,
        )
        vanna_flow_raw = (
            open_interest * (delta_after - delta_before) * CONTRACT_MULTIPLIER * spot_price
        )
        vanna_flow_raw = np.where(time_to_expiration > 0, vanna_flow_raw, 0.0)

        # The delta-neutral hedge changes opposite to assumed signed inventory.
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
            f"Hidden flows: Charm={charm_flow / 1e6:.2f}M, "
            f"Vanna={vanna_flow / 1e6:.2f}M, Net={net_hidden_flow / 1e6:.2f}M"
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
        unique_strikes, inverse = np.unique(strikes, return_inverse=True)
        totals = np.bincount(inverse, weights=values)
        return dict(zip(unique_strikes.tolist(), totals.tolist(), strict=True))
