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
from scipy.optimize import brentq

from app.core.charm_vanna_calculator import CharmVannaCalculator
from app.core.constants import (
    CONTRACT_MULTIPLIER,
    MAX_IV,
    MIN_IV,
    RISK_FREE_RATE,
    SPX_DIVIDEND_YIELD,
    STRIKE_RANGE_PERCENT,
)
from app.core.greeks import BlackScholesGreeks
from app.models.schemas import AdvancedAnalytics, CharmVannaSnapshot, GEXSnapshot

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
ONE_PERCENT_MOVE = 0.01
CALCULATION_VERSION = "sticky_iv_delta_scenarios_v1"


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
        risk_free_rate = self.risk_free_rate

        # Calculate gamma for all contracts WITH dividend yield
        gammas = BlackScholesGreeks.gamma(
            spot_vector,
            strikes,
            time_to_expiration,
            risk_free_rate,
            implied_vol,
            q=self.dividend_yield,
        )

        # Calculate GEX per contract on a 1% underlying move basis.
        gex_raw = open_interest * gammas * CONTRACT_MULTIPLIER * (spot_price**2) * ONE_PERCENT_MOVE

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
            self._find_zero_gamma_level(
                strikes,
                option_types,
                open_interest,
                implied_vol,
                time_to_expiration,
                spot_price,
                risk_free_rate,
            )
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
            self._charm_vanna.risk_free_rate = risk_free_rate
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
            self._normalize_expiration_value(raw_value) for raw_value in expiration_values.tolist()
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
        - Non-finite or non-positive strike/OI
        - Unsupported option types
        - IV outside valid bounds
        - NaN values in critical columns
        """
        original_len = len(df)

        df = df[
            np.isfinite(df["open_interest"])
            & (df["open_interest"] > 0)
            & np.isfinite(df["strike"])
            & (df["strike"] > 0)
            & df["type"].isin(["call", "put"])
        ]
        if len(df) < original_len:
            logger.debug(f"Removed {original_len - len(df)} contracts with invalid strike/OI/type")

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
                "zero_gamma_crossing_found": False,
                "calculation_version": CALCULATION_VERSION,
                "zero_gamma_method": "repriced_fixed_contract_iv",
                "inventory_convention": "call_positive_put_negative",
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

        unique_strikes, inverse = np.unique(strikes, return_inverse=True)
        totals = np.bincount(inverse, weights=gex_values)
        return dict(zip(unique_strikes.tolist(), totals.tolist(), strict=True))

    def _find_zero_gamma_level(
        self,
        strikes: NDArray[np.float64],
        option_types: NDArray[np.str_],
        open_interest: NDArray[np.float64],
        implied_vol: NDArray[np.float64],
        time_to_expiration: NDArray[np.float64],
        spot_price: float,
        risk_free_rate: float,
    ) -> tuple[float, bool, str | None]:
        """
        Find the nearest sign-changing net-gamma root within ±20% of spot.

        Each active contract keeps its observed IV, expiry and signed OI as spot
        changes. Scaling gamma by a common positive factor preserves roots and
        prevents underflow in the tails from masquerading as exact zero gamma.
        No crossing (including identically cancelled inventory) uses spot only
        as a finite compatibility value and carries no directional relation.
        """
        active = time_to_expiration > 0
        if not np.any(active):
            return spot_price, False, None

        signs = np.where(option_types[active] == "call", 1.0, -1.0)
        if np.all(signs == signs[0]):
            return spot_price, False, None

        # Identical pricing inputs share gamma; combine only their signed inventory.
        kernels, inverse = np.unique(
            np.column_stack((strikes[active], implied_vol[active], time_to_expiration[active])),
            axis=0,
            return_inverse=True,
        )
        signed_interest = np.bincount(inverse, weights=signs * open_interest[active])
        exposed = signed_interest != 0
        if not np.any(exposed):
            return spot_price, False, None
        kernels = kernels[exposed]
        signed_interest = signed_interest[exposed]
        signs = np.sign(signed_interest)
        if np.all(signs == signs[0]):
            return spot_price, False, None
        active_strikes = kernels[:, 0]
        sigma = kernels[:, 1]
        active_time = np.maximum(kernels[:, 2], 1e-10)
        width = sigma * np.sqrt(active_time)
        log_centers = (
            np.log(active_strikes)
            - (risk_free_rate - self.dividend_yield + 0.5 * sigma**2) * active_time
        )
        log_weights = (
            np.log(np.abs(signed_interest)) - self.dividend_yield * active_time - np.log(width)
        )

        def signed_gamma(candidate: float) -> float:
            d1 = (np.log(candidate) - log_centers) / width
            log_gamma = log_weights - 0.5 * d1**2
            scaled_gamma = np.exp(log_gamma - np.max(log_gamma))
            return float(np.dot(signs, scaled_gamma) / np.sum(scaled_gamma))

        lower = spot_price * (1 - STRIKE_RANGE_PERCENT)
        upper = spot_price * (1 + STRIKE_RANGE_PERCENT)
        # Sample centers and both one-sigma flanks to resolve narrow 0DTE mixtures.
        centers = np.exp(log_centers[:, None] + width[:, None] * [-1, 0, 1]).ravel()
        points = np.unique(
            np.concatenate(
                (
                    np.geomspace(lower, upper, 257),
                    [spot_price],
                    active_strikes[(active_strikes >= lower) & (active_strikes <= upper)],
                    centers[(centers >= lower) & (centers <= upper)],
                )
            )
        )
        values = np.empty(points.size)
        # Bound temporary matrices while sampling many distinct contract kernels.
        chunk_size = max(1, 65536 // width.size)
        for start in range(0, points.size, chunk_size):
            stop = start + chunk_size
            log_gamma = (np.log(points[start:stop, None]) - log_centers) / width
            np.square(log_gamma, out=log_gamma)
            log_gamma *= -0.5
            log_gamma += log_weights
            log_gamma -= np.max(log_gamma, axis=1, keepdims=True)
            scaled_gamma = np.exp(log_gamma, out=log_gamma)
            values[start:stop] = np.sum(signs * scaled_gamma, axis=1) / np.sum(scaled_gamma, axis=1)
        cancellation_tolerance = 64 * np.finfo(float).eps
        nonzero = np.flatnonzero(np.abs(values) > cancellation_tolerance)
        roots = []
        # Verify an endpoint zero locally; a zero without a sign flip is not a crossing.
        for boundary, value in ((lower, values[0]), (upper, values[-1])):
            if nonzero.size and abs(value) <= cancellation_tolerance:
                step = boundary * np.sqrt(np.finfo(float).eps)
                left_value = signed_gamma(boundary - step)
                right_value = signed_gamma(boundary + step)
                if left_value * right_value < 0:
                    root = brentq(signed_gamma, boundary - step, boundary + step, xtol=1e-9)
                    if lower - 1e-9 <= root <= upper + 1e-9:
                        roots.append(float(np.clip(root, lower, upper)))
        for left, right in zip(nonzero[:-1], nonzero[1:], strict=True):
            if np.signbit(values[left]) != np.signbit(values[right]):
                roots.append(brentq(signed_gamma, points[left], points[right], xtol=1e-9))
        if not roots:
            return spot_price, False, None
        return float(min(roots, key=lambda root: (abs(root - spot_price), root))), True, "in_range"

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

        metrics: dict[str, float | bool | str] = {
            "gex_billions": net_gex / 1e9,
            "call_put_ratio": call_put_ratio,
            "zgl_distance": zgl_distance,
            "zgl_distance_pct": zgl_distance_pct,
            "regime_code": regime_code,  # -1=short, 0=neutral, 1=long
            "num_strikes": float(len(gex_by_strike)),
            "zero_gamma_crossing_found": zero_gamma_crossing_found,
            "calculation_version": CALCULATION_VERSION,
            "zero_gamma_method": "repriced_fixed_contract_iv",
            "inventory_convention": "call_positive_put_negative",
        }
        if zero_gamma_relation is not None:
            metrics["zero_gamma_relation"] = zero_gamma_relation
        return metrics

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
                "Negative signed GEX proxy; volatility amplification is a hypothesis.",
                "red",
            )
        elif gex_billions > threshold_billions:
            return (
                "long_gamma",
                "Positive signed GEX proxy; volatility dampening is a hypothesis.",
                "green",
            )
        else:
            return (
                "neutral",
                "Near-zero signed GEX proxy; no volatility prediction.",
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
