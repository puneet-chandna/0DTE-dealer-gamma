"""0DTE GEX Backend - GEX Calculator Engine.

Trader-facing baseline convention:
- Calls contribute positive GEX
- Puts contribute negative GEX

GEX Formula: GEX_i = OI_i × Γ_i × 100 × S² × 0.01
"""

import logging
import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from app.core.charm_vanna_calculator import CharmVannaCalculator
from app.core.constants import (
    CONTRACT_MULTIPLIER,
    MAX_IV,
    MIN_IV,
    RISK_FREE_RATE,
    SPX_DIVIDEND_YIELD,
)
from app.core.greeks import BlackScholesGreeks
from app.models.schemas import AdvancedAnalytics, CharmVannaSnapshot, GEXSnapshot

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
ONE_PERCENT_MOVE = 0.01


class GEXCalculator:
    """
    Calculate Dealer Gamma Exposure from options chain data.

    GEX Formula: GEX_i = OI_i × Γ_i × 100 × S² × 0.01

    Trader-facing baseline convention:
    - Calls contribute positive GEX
    - Puts contribute negative GEX

    Net GEX = Σ(GEX_calls) + Σ(GEX_puts)
    """

    def __init__(
        self,
        risk_free_rate: float = RISK_FREE_RATE,
        dividend_yield: float = SPX_DIVIDEND_YIELD,
        rate_provider=None,
    ):
        """Initialize with risk-free rate and dividend yield.

        Args:
            risk_free_rate: Static fallback rate (used if no rate_provider).
            dividend_yield: SPX dividend yield.
            rate_provider: Optional RiskFreeRateProvider for dynamic FRED rates.
        """
        self._rate_provider = rate_provider
        self._static_rate = risk_free_rate
        self.dividend_yield = dividend_yield
        self._charm_vanna = CharmVannaCalculator(
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
        )

    @property
    def risk_free_rate(self) -> float:
        """Get the current risk-free rate (dynamic if provider is set)."""
        if self._rate_provider is not None:
            return self._rate_provider.get_rate()
        return self._static_rate

    def calculate_gex_from_chain(
        self,
        options_df: pd.DataFrame,
        spot_price: float,
        timestamp: datetime,
    ) -> GEXSnapshot:
        """
        Calculate GEX from options chain DataFrame.

        Expected columns: strike, type, open_interest, implied_vol, expiration

        Returns GEXSnapshot with all GEX metrics.
        """
        if options_df.empty:
            logger.warning("Empty options chain received, returning zero GEX")
            return self._create_empty_snapshot(spot_price, timestamp)

        # Create a copy to avoid modifying original
        df = options_df.copy()

        # Filter out invalid data
        initial_count = len(df)
        df = self._filter_valid_contracts(df)
        filtered_count = len(df)

        if filtered_count < initial_count:
            logger.info(
                f"Filtered {initial_count - filtered_count} invalid contracts "
                f"({filtered_count} remaining)"
            )

        if df.empty:
            logger.warning("No valid contracts after filtering, returning zero GEX")
            return self._create_empty_snapshot(spot_price, timestamp)

        # Convert to numpy arrays for vectorized calculation
        strikes = df["strike"].values.astype(np.float64)
        option_types = df["type"].values
        open_interest = df["open_interest"].values.astype(np.float64)
        implied_vol = df["implied_vol"].values.astype(np.float64)

        reference_timestamp = self._normalize_reference_timestamp(timestamp)

        # Calculate time to expiration in years
        expiration = self._normalize_expiration_timestamps(
            expiration_values=df["expiration"],
        )
        time_to_expiration = (
            (expiration - reference_timestamp).dt.total_seconds() / (365.25 * 24 * 3600)
        ).to_numpy(dtype=np.float64)

        # Ensure time to expiration is finite and positive (filter out expired)
        time_to_expiration = np.maximum(
            np.nan_to_num(time_to_expiration, nan=0.0),
            0.0,
        )

        # Vectorized spot price
        spot_vector = np.full_like(strikes, spot_price)

        # Calculate gamma for all contracts WITH dividend yield
        gammas = BlackScholesGreeks.gamma(
            spot_vector,
            strikes,
            time_to_expiration,
            self.risk_free_rate,
            implied_vol,
            q=self.dividend_yield,
        )

        # Calculate GEX per contract on a 1% underlying move basis.
        gex_raw = (
            open_interest
            * gammas
            * CONTRACT_MULTIPLIER
            * (spot_price**2)
            * ONE_PERCENT_MOVE
        )

        # Apply the standard baseline sign convention: calls positive, puts negative.
        is_call = option_types == "call"
        gex_adjusted = np.where(is_call, gex_raw, -gex_raw)

        # Aggregate by strike
        gex_by_strike = self._aggregate_by_strike(strikes, gex_adjusted)

        # Calculate totals
        total_call_gex = float(np.sum(gex_adjusted[is_call]))
        total_put_gex = float(np.sum(gex_adjusted[~is_call]))
        net_gex = total_call_gex + total_put_gex

        # Find zero gamma level
        zero_gamma_level, zero_gamma_crossing_found, zero_gamma_relation = (
            self._find_zero_gamma_level(gex_by_strike, spot_price)
        )

        # Find dominant strike (highest absolute GEX)
        if gex_by_strike:
            dominant_strike = max(gex_by_strike.keys(), key=lambda k: abs(gex_by_strike[k]))
        else:
            dominant_strike = spot_price

        # Calculate additional metrics
        metrics = self._calculate_metrics(
            net_gex=net_gex,
            total_call_gex=total_call_gex,
            total_put_gex=total_put_gex,
            spot_price=spot_price,
            zero_gamma_level=zero_gamma_level,
            gex_by_strike=gex_by_strike,
            zero_gamma_crossing_found=zero_gamma_crossing_found,
            zero_gamma_relation=zero_gamma_relation,
        )

        # Calculate Charm & Vanna hidden flows
        try:
            cv_result = self._charm_vanna.calculate_all(
                options_df=df,
                spot_price=spot_price,
                time_to_expiration=time_to_expiration,
            )
            charm_vanna = CharmVannaSnapshot(
                charm_flow=cv_result["charm_flow"],
                vanna_flow=cv_result["vanna_flow"],
                net_hidden_flow=cv_result["net_hidden_flow"],
                charm_by_strike=cv_result["charm_by_strike"],
                vanna_by_strike=cv_result["vanna_by_strike"],
            )
            advanced = AdvancedAnalytics(charm_vanna=charm_vanna)
        except Exception as e:
            logger.warning(f"Charm/Vanna calculation failed: {e}")
            advanced = None

        return GEXSnapshot(
            timestamp=timestamp,
            spot_price=spot_price,
            total_call_gex=total_call_gex,
            total_put_gex=total_put_gex,
            net_gex=net_gex,
            zero_gamma_level=zero_gamma_level,
            gex_by_strike=gex_by_strike,
            dominant_strike=dominant_strike,
            metrics=metrics,
            advanced_analytics=advanced,
        )

    def _normalize_expiration_timestamps(
        self,
        expiration_values: pd.Series,
    ) -> pd.Series:
        """Normalize expirations into ET market time.

        Date-only expirations are treated as 4:00 PM ET on that session date so
        replay/backfill of stored 0DTE snapshots does not collapse to zero when
        `captured_at` is stored in UTC.
        """
        normalized_values = [
            self._normalize_expiration_value(raw_value)
            for raw_value in expiration_values.tolist()
        ]
        return pd.Series(normalized_values, index=expiration_values.index)

    def _normalize_reference_timestamp(self, timestamp: datetime) -> pd.Timestamp:
        """Normalize the pricing timestamp into ET for option expiry math."""
        reference = pd.Timestamp(timestamp)
        if reference.tzinfo is None:
            return reference.tz_localize(ET)
        return reference.tz_convert(ET)

    def _normalize_expiration_value(self, raw_value: object) -> pd.Timestamp:
        """Normalize one expiration value into ET market time."""
        if raw_value is None or pd.isna(raw_value):
            return pd.NaT

        if isinstance(raw_value, date) and not isinstance(raw_value, datetime):
            return pd.Timestamp(datetime.combine(raw_value, time(16, 0), tzinfo=ET))

        if isinstance(raw_value, str):
            raw_string = raw_value.strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_string):
                expiration_date = date.fromisoformat(raw_string)
                return pd.Timestamp(datetime.combine(expiration_date, time(16, 0), tzinfo=ET))
            parsed = pd.Timestamp(raw_string)
        else:
            parsed = pd.Timestamp(raw_value)

        if pd.isna(parsed):
            return pd.NaT
        if parsed.tzinfo is None:
            return parsed.tz_localize(ET)
        return parsed.tz_convert(ET)

    def _filter_valid_contracts(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter out invalid contracts.

        Removes contracts with:
        - OI = 0 (no exposure)
        - IV outside valid bounds
        - NaN values in critical columns
        """
        original_len = len(df)

        # Filter OI = 0
        df = df[df["open_interest"] > 0]
        if len(df) < original_len:
            logger.debug(f"Removed {original_len - len(df)} contracts with OI=0")

        # Filter NaN implied_vol
        df = df[df["implied_vol"].notna()]

        # Filter IV bounds
        df = df[(df["implied_vol"] >= MIN_IV) & (df["implied_vol"] <= MAX_IV)]

        # Filter NaN in other critical columns
        df = df.dropna(subset=["strike", "type", "expiration"])

        return df

    def _create_empty_snapshot(
        self,
        spot_price: float,
        timestamp: datetime,
    ) -> GEXSnapshot:
        """Create an empty GEX snapshot for edge cases."""
        return GEXSnapshot(
            timestamp=timestamp,
            spot_price=spot_price,
            total_call_gex=0.0,
            total_put_gex=0.0,
            net_gex=0.0,
            zero_gamma_level=spot_price,
            gex_by_strike={},
            dominant_strike=spot_price,
            metrics={
                "gex_billions": 0.0,
                "call_put_ratio": 0.0,
                "regime_code": 0.0,  # neutral
                "num_strikes": 0.0,
            },
        )

    def _aggregate_by_strike(
        self,
        strikes: NDArray[np.float64],
        gex_values: NDArray[np.float64],
    ) -> dict[float, float]:
        """Aggregate GEX values by strike price."""
        if len(strikes) == 0:
            return {}

        unique_strikes = np.unique(strikes)
        gex_by_strike: dict[float, float] = {}

        for strike in unique_strikes:
            mask = strikes == strike
            gex_by_strike[float(strike)] = float(np.sum(gex_values[mask]))

        return gex_by_strike

    def _find_zero_gamma_level(
        self,
        gex_by_strike: dict[float, float],
        spot_price: float,
    ) -> tuple[float, bool, str | None]:
        """
        Find the Zero Gamma Level using linear interpolation.

        The ZGL is where the cumulative GEX curve crosses zero.
        If the curve never crosses zero, return the nearest boundary strike and
        mark the relation so the UI can avoid presenting it as a true in-range
        crossing.
        """
        if not gex_by_strike:
            return spot_price, False, None

        # Sort strikes
        sorted_strikes = sorted(gex_by_strike.keys())

        if len(sorted_strikes) < 2:
            return spot_price, False, None

        # Calculate cumulative GEX from lowest to highest strike
        gex_values = np.array([gex_by_strike[k] for k in sorted_strikes])
        cumulative_gex = np.cumsum(gex_values)

        zero_crossing_tolerance = 1e-8
        exact_crossing_mask = np.isclose(
            cumulative_gex,
            0.0,
            atol=zero_crossing_tolerance,
            rtol=0.0,
        )
        exact_crossings = np.where(exact_crossing_mask)[0]
        if exact_crossings.size > 0:
            return sorted_strikes[int(exact_crossings[0])], True, "in_range"

        # Check if all positive or all negative (no crossing possible)
        if np.all(cumulative_gex >= 0):
            return sorted_strikes[0], False, "below_range"

        if np.all(cumulative_gex <= 0):
            return sorted_strikes[-1], False, "above_range"

        # Find zero crossing
        for i in range(len(cumulative_gex) - 1):
            if cumulative_gex[i] * cumulative_gex[i + 1] < 0:
                # Linear interpolation
                x1, x2 = sorted_strikes[i], sorted_strikes[i + 1]
                y1, y2 = cumulative_gex[i], cumulative_gex[i + 1]

                # Avoid division by zero
                if y2 - y1 == 0:
                    continue

                zero_level = x1 - y1 * (x2 - x1) / (y2 - y1)
                return float(zero_level), True, "in_range"

        # Fall back to the closest boundary if we somehow miss the crossing.
        closest_idx = int(np.argmin(np.abs(cumulative_gex)))
        closest_strike = sorted_strikes[closest_idx]
        relation = "below_range" if closest_strike <= spot_price else "above_range"
        return closest_strike, False, relation

    def _calculate_metrics(
        self,
        net_gex: float,
        total_call_gex: float,
        total_put_gex: float,
        spot_price: float,
        zero_gamma_level: float,
        gex_by_strike: dict[float, float],
        zero_gamma_crossing_found: bool,
        zero_gamma_relation: str | None,
    ) -> dict[str, float | bool | str]:
        """Calculate additional GEX metrics."""
        # Safe division for ratios
        if total_put_gex != 0:
            call_put_ratio = abs(total_call_gex / total_put_gex)
        else:
            call_put_ratio = 0.0

        # Distance from spot to zero gamma level
        zgl_distance = zero_gamma_level - spot_price
        zgl_distance_pct = (zgl_distance / spot_price * 100) if spot_price != 0 else 0.0

        # Regime determination
        regime, _, _ = self.determine_regime(net_gex)

        # Map regime to numeric code for the float-only metrics dict
        regime_code = {"short_gamma": -1.0, "neutral": 0.0, "long_gamma": 1.0}.get(regime, 0.0)

        return {
            "gex_billions": net_gex / 1e9,
            "call_put_ratio": call_put_ratio,
            "zgl_distance": zgl_distance,
            "zgl_distance_pct": zgl_distance_pct,
            "regime_code": regime_code,  # -1=short, 0=neutral, 1=long
            "num_strikes": float(len(gex_by_strike)),
            "zero_gamma_crossing_found": zero_gamma_crossing_found,
            "zero_gamma_relation": zero_gamma_relation or "unknown",
        }

    def determine_regime(
        self,
        net_gex: float,
        threshold_billions: float = 1.0,
    ) -> tuple[str, str, str]:
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

    def calculate_gex_contribution(
        self,
        gex_by_strike: dict[float, float],
        spot_price: float,
        n_top: int = 5,
    ) -> dict[str, list]:
        """
        Get the top contributing strikes to GEX.

        Returns dict with 'positive' and 'negative' lists of top strikes.
        """
        if not gex_by_strike:
            return {"positive": [], "negative": []}

        sorted_by_gex = sorted(gex_by_strike.items(), key=lambda x: x[1])

        # Top negative (most negative GEX)
        negative = [
            {"strike": k, "gex": v, "distance": k - spot_price}
            for k, v in sorted_by_gex[:n_top]
            if v < 0
        ]

        # Top positive (most positive GEX)
        positive = [
            {"strike": k, "gex": v, "distance": k - spot_price}
            for k, v in sorted_by_gex[-n_top:][::-1]
            if v > 0
        ]

        return {"positive": positive, "negative": negative}
