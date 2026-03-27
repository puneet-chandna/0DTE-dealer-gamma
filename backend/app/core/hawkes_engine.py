"""0DTE GEX Backend - Hawkes-style snapshot flow engine.

This module intentionally does not implement a mathematically fitted
event-arrival Hawkes process. Instead, it provides a stable Hawkes-style proxy
using consecutive options-chain snapshots.

For each contract seen in consecutive snapshots we:
1. Measure positive changes in volume and open interest.
2. Weight those changes by contract importance using price/Greek context.
3. Add the weighted event score to call/put intensities.
4. Exponentially decay the existing intensities through time.

The resulting signal is more stable than a raw delta-volume counter and avoids
false spikes from contract-universe churn.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Deque, Dict, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.core.constants import DEFAULT_RISK_FREE_RATE, SPX_DIVIDEND_YIELD
from app.core.constants import (
    HAWKES_ALPHA,
    HAWKES_BETA,
    HAWKES_VOLUME_THRESHOLD,
)
from app.core.greeks import BlackScholesGreeks

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
SECONDS_PER_YEAR = 365.0 * 24.0 * 60.0 * 60.0
ROLLING_WINDOW = 24
MIN_NORMALIZATION_SCALE = 0.25


@dataclass
class ContractSnapshot:
    """Normalized contract features needed for consecutive-snapshot scoring."""

    strike: float
    option_type: str
    expiration: str
    volume: float
    open_interest: float
    bid: float
    ask: float
    mid: float
    implied_vol: float
    delta: float
    gamma: float

    def to_dict(self) -> dict[str, float | str]:
        """Serialize contract state for rollback-safe snapshots."""
        return {
            "strike": self.strike,
            "option_type": self.option_type,
            "expiration": self.expiration,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "bid": self.bid,
            "ask": self.ask,
            "mid": self.mid,
            "implied_vol": self.implied_vol,
            "delta": self.delta,
            "gamma": self.gamma,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ContractSnapshot":
        """Rehydrate a serialized contract snapshot."""
        return cls(
            strike=float(payload.get("strike", 0.0)),
            option_type=str(payload.get("option_type", "")),
            expiration=str(payload.get("expiration", "")),
            volume=float(payload.get("volume", 0.0)),
            open_interest=float(payload.get("open_interest", 0.0)),
            bid=float(payload.get("bid", 0.0)),
            ask=float(payload.get("ask", 0.0)),
            mid=float(payload.get("mid", 0.0)),
            implied_vol=float(payload.get("implied_vol", 0.0)),
            delta=float(payload.get("delta", 0.0)),
            gamma=float(payload.get("gamma", 0.0)),
        )


@dataclass
class HawkesState:
    """Current state of the Hawkes-style flow process."""

    call_intensity: float = 0.0
    put_intensity: float = 0.0
    net_toxicity: float = 0.0
    squeeze_probability: float = 0.0
    baseline_ready: bool = False
    confidence_score: float = 0.0
    provider_mode: str = "tradier_rich"
    event_count: int = 0


class HawkesEngine:
    """
    Snapshot-based Hawkes-style proxy for options order flow.

    On each options-chain snapshot, we score only contracts seen in
    consecutive snapshots. That makes the signal robust to option-universe
    churn while still capturing self-reinforcing flow behavior.

    Usage:
        engine = HawkesEngine()
        # On each polling cycle:
        state = engine.update(options_df, timestamp_seconds)
    """

    def __init__(
        self,
        alpha: float = HAWKES_ALPHA,
        beta: float = HAWKES_BETA,
        volume_threshold: int = HAWKES_VOLUME_THRESHOLD,
        rolling_window: int = ROLLING_WINDOW,
    ):
        self.alpha = alpha
        self.beta = beta
        self.volume_threshold = volume_threshold
        self.rolling_window = rolling_window

        # Internal state
        self._call_intensity: float = 0.0
        self._put_intensity: float = 0.0
        self._last_contracts: Dict[str, ContractSnapshot] = {}
        self._last_timestamp: Optional[float] = None
        self._last_trading_day: Optional[date] = None
        self._provider_mode: str = "tradier_rich"
        self._baseline_ready: bool = False
        self._confidence_score: float = 0.0
        self._event_count: int = 0
        self._rolling_imbalance: Deque[float] = deque(maxlen=self.rolling_window)
        self._rolling_total_intensity: Deque[float] = deque(maxlen=self.rolling_window)

    def update(
        self,
        options_df: pd.DataFrame,
        timestamp: Optional[float] = None,
        *,
        spot_price: Optional[float] = None,
        provider_mode: Optional[str] = None,
    ) -> HawkesState:
        """
        Update the Hawkes-style state with a new options-chain snapshot.

        Args:
            options_df: Standardized options chain DataFrame
            timestamp: Unix timestamp of this snapshot (auto-generated if None)
            spot_price: Underlying spot price used for weighting / fallback Greeks
            provider_mode: "tradier_rich" or "yfinance_proxy"

        Returns:
            Current HawkesState after update.
        """
        if timestamp is None:
            timestamp = time.time()

        if options_df.empty:
            self._event_count = 0
            return self.get_state()

        if "volume" not in options_df.columns and "open_interest" not in options_df.columns:
            logger.debug(
                "No 'volume' or 'open_interest' column in options_df, skipping Hawkes update"
            )
            self._event_count = 0
            return self.get_state()

        resolved_provider_mode = self._normalize_provider_mode(provider_mode)
        snapshot_day = self._resolve_trading_day(timestamp)
        if self._should_reset_for_new_stream(
            timestamp=timestamp,
            provider_mode=resolved_provider_mode,
            snapshot_day=snapshot_day,
        ):
            self.reset()

        dt = self._calculate_dt(timestamp)
        decay = float(np.exp(-self.beta * dt))
        self._call_intensity *= decay
        self._put_intensity *= decay

        normalized_df, native_greek_ratio, computed_greek_ratio = self._normalize_options_df(
            options_df,
            timestamp=timestamp,
            spot_price=spot_price,
            provider_mode=resolved_provider_mode,
        )
        current_contracts = self._build_contract_map(normalized_df)

        call_event_score = 0.0
        put_event_score = 0.0
        event_count = 0
        overlap_count = 0
        effective_spot = self._resolve_effective_spot(spot_price, normalized_df)

        for key, current_contract in current_contracts.items():
            previous_contract = self._last_contracts.get(key)
            if previous_contract is None:
                continue

            overlap_count += 1
            event_score = self._score_contract_event(
                current_contract=current_contract,
                previous_contract=previous_contract,
                spot_price=effective_spot,
            )
            if event_score <= 0:
                continue

            event_count += 1
            if current_contract.option_type == "call":
                call_event_score += event_score
            elif current_contract.option_type == "put":
                put_event_score += event_score

        if call_event_score > 0:
            self._call_intensity += self.alpha * call_event_score
        if put_event_score > 0:
            self._put_intensity += self.alpha * put_event_score

        self._baseline_ready = overlap_count > 0
        self._event_count = event_count
        self._provider_mode = resolved_provider_mode
        self._confidence_score = self._calculate_confidence_score(
            provider_mode=resolved_provider_mode,
            baseline_ready=self._baseline_ready,
            overlap_count=overlap_count,
            native_greek_ratio=native_greek_ratio,
            computed_greek_ratio=computed_greek_ratio,
        )

        self._record_normalization_history()

        self._last_timestamp = timestamp
        self._last_trading_day = snapshot_day
        self._last_contracts = current_contracts

        state = self.get_state()

        logger.debug(
            "Hawkes-style update: call_intensity=%.4f, put_intensity=%.4f, "
            "squeeze_prob=%.4f, provider_mode=%s, baseline_ready=%s, events=%s",
            state.call_intensity,
            state.put_intensity,
            state.squeeze_probability,
            state.provider_mode,
            state.baseline_ready,
            state.event_count,
        )

        return state

    def get_state(self) -> HawkesState:
        """Get the current Hawkes-style state without updating."""
        net_toxicity = self._call_intensity - self._put_intensity
        total_intensity = self._call_intensity + self._put_intensity
        squeeze_probability = self._calculate_squeeze_probability(
            net_toxicity=net_toxicity,
            total_intensity=total_intensity,
        )

        return HawkesState(
            call_intensity=round(self._call_intensity, 6),
            put_intensity=round(self._put_intensity, 6),
            net_toxicity=round(net_toxicity, 6),
            squeeze_probability=round(squeeze_probability, 6),
            baseline_ready=self._baseline_ready,
            confidence_score=round(self._confidence_score, 6),
            provider_mode=self._provider_mode,
            event_count=self._event_count,
        )

    def snapshot_state(self) -> dict[str, Any]:
        """Capture the full mutable engine state for rollback-safe updates."""
        return {
            "call_intensity": self._call_intensity,
            "put_intensity": self._put_intensity,
            "last_contracts": {
                key: contract.to_dict() for key, contract in self._last_contracts.items()
            },
            "last_timestamp": self._last_timestamp,
            "last_trading_day": self._last_trading_day.isoformat()
            if self._last_trading_day is not None
            else None,
            "provider_mode": self._provider_mode,
            "baseline_ready": self._baseline_ready,
            "confidence_score": self._confidence_score,
            "event_count": self._event_count,
            "rolling_imbalance": list(self._rolling_imbalance),
            "rolling_total_intensity": list(self._rolling_total_intensity),
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore a previously captured engine state."""
        required_keys = (
            "call_intensity",
            "put_intensity",
            "provider_mode",
            "baseline_ready",
            "confidence_score",
            "event_count",
            "rolling_imbalance",
            "rolling_total_intensity",
        )
        missing_keys = [key for key in required_keys if key not in state]
        if missing_keys:
            raise ValueError(
                f"restore_state missing required keys: {', '.join(missing_keys)}"
            )

        last_contracts = state.get("last_contracts")
        last_timestamp = state.get("last_timestamp")
        last_trading_day = state.get("last_trading_day")
        try:
            call_intensity = float(state["call_intensity"])
            put_intensity = float(state["put_intensity"])
            confidence_score = float(state["confidence_score"])
            baseline_ready = bool(state["baseline_ready"])
            event_count = int(state["event_count"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "restore_state requires numeric call_intensity, put_intensity, "
                "confidence_score, and event_count values"
            ) from exc

        restored_last_contracts = (
            {
                key: ContractSnapshot.from_dict(payload)
                for key, payload in last_contracts.items()
            }
            if isinstance(last_contracts, dict)
            else {}
        )
        restored_last_timestamp = (
            float(last_timestamp)
            if isinstance(last_timestamp, (int, float))
            else None
        )
        restored_last_trading_day = (
            date.fromisoformat(last_trading_day)
            if isinstance(last_trading_day, str)
            else None
        )

        rolling_imbalance = state["rolling_imbalance"]
        rolling_total_intensity = state["rolling_total_intensity"]
        if not isinstance(rolling_imbalance, list) or not isinstance(
            rolling_total_intensity, list
        ):
            raise ValueError(
                "restore_state requires rolling_imbalance and rolling_total_intensity lists"
            )

        self._call_intensity = call_intensity
        self._put_intensity = put_intensity
        self._last_contracts = restored_last_contracts
        self._last_timestamp = restored_last_timestamp
        self._last_trading_day = restored_last_trading_day
        self._provider_mode = str(state["provider_mode"])
        self._baseline_ready = baseline_ready
        self._confidence_score = confidence_score
        self._event_count = event_count
        self._rolling_imbalance = deque(
            [float(value) for value in rolling_imbalance],
            maxlen=self.rolling_window,
        )
        self._rolling_total_intensity = deque(
            [float(value) for value in rolling_total_intensity],
            maxlen=self.rolling_window,
        )

    def reset(self) -> None:
        """Reset the engine state (e.g., at market open)."""
        self._call_intensity = 0.0
        self._put_intensity = 0.0
        self._last_contracts = {}
        self._last_timestamp = None
        self._last_trading_day = None
        self._baseline_ready = False
        self._confidence_score = 0.0
        self._event_count = 0
        self._provider_mode = "tradier_rich"
        self._rolling_imbalance.clear()
        self._rolling_total_intensity.clear()
        logger.info("Hawkes engine state reset")

    def _calculate_dt(self, timestamp: float) -> float:
        """Resolve the elapsed time used for exponential decay."""
        if self._last_timestamp is None:
            return 5.0
        return max(1.0, timestamp - self._last_timestamp)

    def _normalize_provider_mode(self, provider_mode: Optional[str]) -> str:
        """Normalize provider mode labels used across the backend and UI."""
        normalized = (provider_mode or self._provider_mode or "tradier_rich").strip().lower()
        if normalized in {"tradier", "tradier_rich"}:
            return "tradier_rich"
        return "yfinance_proxy"

    def _resolve_trading_day(self, timestamp: float) -> date:
        """Map the snapshot timestamp to the current ET trading day."""
        return datetime.fromtimestamp(timestamp, tz=ET).date()

    def _should_reset_for_new_stream(
        self,
        *,
        timestamp: float,
        provider_mode: str,
        snapshot_day: date,
    ) -> bool:
        """Reset state when the stream changes or timestamps become invalid."""
        if self._last_timestamp is None:
            return False
        if provider_mode != self._provider_mode:
            return True
        if snapshot_day != self._last_trading_day:
            return True
        if timestamp < self._last_timestamp:
            return True
        return False

    def _normalize_options_df(
        self,
        options_df: pd.DataFrame,
        *,
        timestamp: float,
        spot_price: Optional[float],
        provider_mode: str,
    ) -> tuple[pd.DataFrame, float, float]:
        """Create a normalized snapshot and fill missing Greeks when possible."""
        frame = options_df.copy()

        for column in (
            "strike",
            "volume",
            "open_interest",
            "bid",
            "ask",
            "mid",
            "implied_vol",
            "delta",
            "gamma",
        ):
            if column not in frame.columns:
                frame[column] = np.nan

        if "type" not in frame.columns:
            frame["type"] = ""
        if "expiration" not in frame.columns:
            frame["expiration"] = ""

        numeric_columns = (
            "strike",
            "volume",
            "open_interest",
            "bid",
            "ask",
            "mid",
            "implied_vol",
            "delta",
            "gamma",
        )
        for column in numeric_columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

        frame["type"] = frame["type"].astype(str).str.lower().str.strip()
        frame["expiration"] = frame["expiration"].fillna("").astype(str)
        frame["mid"] = frame["mid"].where(frame["mid"].notna(), (frame["bid"] + frame["ask"]) / 2.0)
        frame["mid"] = frame["mid"].fillna(0.0)
        frame["implied_vol"] = frame["implied_vol"].clip(lower=0.01).fillna(0.2)
        frame["volume"] = frame["volume"].fillna(0.0).clip(lower=0.0)
        frame["open_interest"] = frame["open_interest"].fillna(0.0).clip(lower=0.0)

        native_greek_mask = frame["delta"].notna() & frame["gamma"].notna()
        native_greek_ratio = float(native_greek_mask.mean()) if len(frame) > 0 else 0.0
        frame, computed_greek_ratio = self._fill_missing_greeks(
            frame,
            timestamp=timestamp,
            spot_price=spot_price,
            provider_mode=provider_mode,
        )

        return frame, native_greek_ratio, computed_greek_ratio

    def _fill_missing_greeks(
        self,
        frame: pd.DataFrame,
        *,
        timestamp: float,
        spot_price: Optional[float],
        provider_mode: str,
    ) -> tuple[pd.DataFrame, float]:
        """Fill missing delta/gamma values using Black-Scholes when needed."""
        missing_mask = frame["delta"].isna() | frame["gamma"].isna()
        if not missing_mask.any():
            return frame, 0.0

        if spot_price is None or not np.isfinite(spot_price) or spot_price <= 0:
            frame["delta"] = frame["delta"].fillna(0.0)
            frame["gamma"] = frame["gamma"].fillna(0.0)
            return frame, 0.0

        expirations = pd.to_datetime(frame["expiration"], utc=True, errors="coerce")
        valid_mask = (
            missing_mask
            & expirations.notna()
            & frame["strike"].notna()
            & frame["implied_vol"].notna()
            & frame["type"].isin(["call", "put"])
        )
        if not valid_mask.any():
            frame["delta"] = frame["delta"].fillna(0.0)
            frame["gamma"] = frame["gamma"].fillna(0.0)
            return frame, 0.0

        expiry_timestamps = expirations[valid_mask].astype("int64") / 1e9
        time_to_expiry = np.maximum((expiry_timestamps.to_numpy() - timestamp) / SECONDS_PER_YEAR, 1e-10)
        strikes = frame.loc[valid_mask, "strike"].to_numpy(dtype=float)
        sigmas = frame.loc[valid_mask, "implied_vol"].to_numpy(dtype=float)
        option_types = frame.loc[valid_mask, "type"].to_numpy(dtype=str)
        spots = np.full(len(strikes), float(spot_price), dtype=float)

        computed_delta = BlackScholesGreeks.delta(
            spots,
            strikes,
            time_to_expiry,
            DEFAULT_RISK_FREE_RATE,
            sigmas,
            option_types,
            q=SPX_DIVIDEND_YIELD,
        )
        computed_gamma = BlackScholesGreeks.gamma(
            spots,
            strikes,
            time_to_expiry,
            DEFAULT_RISK_FREE_RATE,
            sigmas,
            q=SPX_DIVIDEND_YIELD,
        )

        delta_series = pd.Series(computed_delta, index=frame.index[valid_mask])
        gamma_series = pd.Series(computed_gamma, index=frame.index[valid_mask])
        frame.loc[valid_mask & frame["delta"].isna(), "delta"] = delta_series
        frame.loc[valid_mask & frame["gamma"].isna(), "gamma"] = gamma_series
        frame["delta"] = frame["delta"].fillna(0.0)
        frame["gamma"] = frame["gamma"].fillna(0.0)

        computed_ratio = float(valid_mask.mean()) if len(frame) > 0 else 0.0
        if computed_ratio > 0:
            logger.debug(
                "Computed fallback Greeks for %.0f%% of %s snapshot rows",
                computed_ratio * 100,
                provider_mode,
            )

        return frame, computed_ratio

    def _build_contract_map(self, frame: pd.DataFrame) -> Dict[str, ContractSnapshot]:
        """Build the normalized contract lookup for one snapshot."""
        contracts: Dict[str, ContractSnapshot] = {}
        for row in frame.itertuples(index=False):
            option_type = getattr(row, "type", "")
            if option_type not in {"call", "put"}:
                continue

            contract = ContractSnapshot(
                strike=float(getattr(row, "strike", 0.0) or 0.0),
                option_type=option_type,
                expiration=str(getattr(row, "expiration", "") or ""),
                volume=float(getattr(row, "volume", 0.0) or 0.0),
                open_interest=float(getattr(row, "open_interest", 0.0) or 0.0),
                bid=float(getattr(row, "bid", 0.0) or 0.0),
                ask=float(getattr(row, "ask", 0.0) or 0.0),
                mid=float(getattr(row, "mid", 0.0) or 0.0),
                implied_vol=float(getattr(row, "implied_vol", 0.0) or 0.0),
                delta=float(getattr(row, "delta", 0.0) or 0.0),
                gamma=float(getattr(row, "gamma", 0.0) or 0.0),
            )
            contracts[self._contract_key(contract)] = contract
        return contracts

    def _contract_key(self, contract: ContractSnapshot) -> str:
        """Create a stable contract identity across snapshots."""
        return f"{contract.expiration}|{contract.strike:.6f}|{contract.option_type}"

    def _resolve_effective_spot(
        self,
        spot_price: Optional[float],
        frame: pd.DataFrame,
    ) -> float:
        """Use the supplied spot or fall back to the median strike."""
        if spot_price is not None and np.isfinite(spot_price) and spot_price > 0:
            return float(spot_price)
        if "strike" in frame.columns and frame["strike"].notna().any():
            return float(frame["strike"].median())
        return 1.0

    def _score_contract_event(
        self,
        *,
        current_contract: ContractSnapshot,
        previous_contract: ContractSnapshot,
        spot_price: float,
    ) -> float:
        """Score one contract's positive snapshot-to-snapshot change."""
        delta_volume = max(0.0, current_contract.volume - previous_contract.volume)
        delta_open_interest = max(
            0.0, current_contract.open_interest - previous_contract.open_interest
        )
        combined_change = delta_volume + delta_open_interest
        if combined_change < self.volume_threshold:
            return 0.0

        importance = self._contract_importance(current_contract, spot_price=spot_price)
        normalized_volume = np.log1p(delta_volume / max(float(self.volume_threshold), 1.0))
        normalized_oi = np.log1p(
            delta_open_interest / max(float(self.volume_threshold), 1.0)
        )
        return float(importance * (normalized_volume + 0.7 * normalized_oi))

    def _contract_importance(
        self,
        contract: ContractSnapshot,
        *,
        spot_price: float,
    ) -> float:
        """Weight a contract by how meaningful it is to dealer hedging flow."""
        strike_gap = abs(contract.strike - spot_price) / max(spot_price, 1.0)
        moneyness_weight = max(0.35, 1.25 - 3.0 * strike_gap)
        gamma_weight = min(2.0, 1.0 + abs(contract.gamma) * spot_price * 0.02)
        delta_weight = 0.6 + min(0.8, abs(contract.delta))
        oi_weight = 0.75 + min(0.75, np.log1p(max(contract.open_interest, 0.0)) / 8.0)
        premium_weight = 0.8 + min(0.8, max(contract.mid, 0.0) / 20.0)
        iv_weight = 0.85 + min(0.4, max(contract.implied_vol, 0.0))

        importance = (
            moneyness_weight
            * gamma_weight
            * delta_weight
            * oi_weight
            * premium_weight
            * iv_weight
        ) / 3.5
        return float(max(0.25, importance))

    def _record_normalization_history(self) -> None:
        """Update rolling windows used for squeeze normalization."""
        net_toxicity = self._call_intensity - self._put_intensity
        total_intensity = self._call_intensity + self._put_intensity
        self._rolling_imbalance.append(abs(net_toxicity))
        self._rolling_total_intensity.append(total_intensity)

    def _calculate_squeeze_probability(
        self,
        *,
        net_toxicity: float,
        total_intensity: float,
    ) -> float:
        """Normalize squeeze risk from rolling imbalance instead of session max."""
        if total_intensity <= 0:
            return 0.0

        imbalance = abs(net_toxicity)
        imbalance_reference = self._rolling_reference(self._rolling_imbalance)
        dominance = imbalance / max(total_intensity, MIN_NORMALIZATION_SCALE)
        rolling_imbalance_score = min(1.0, imbalance / imbalance_reference)
        return float(np.clip(0.75 * rolling_imbalance_score + 0.25 * dominance, 0.0, 1.0))

    def _rolling_reference(self, values: Deque[float]) -> float:
        """Return a stable rolling normalization anchor."""
        if not values:
            return MIN_NORMALIZATION_SCALE
        return float(max(np.percentile(list(values), 75), MIN_NORMALIZATION_SCALE))

    def _calculate_confidence_score(
        self,
        *,
        provider_mode: str,
        baseline_ready: bool,
        overlap_count: int,
        native_greek_ratio: float,
        computed_greek_ratio: float,
    ) -> float:
        """Estimate how trustworthy the current snapshot proxy is."""
        base_confidence = 0.92 if provider_mode == "tradier_rich" else 0.62
        if not baseline_ready:
            base_confidence -= 0.28
        if overlap_count == 0:
            base_confidence -= 0.12

        confidence = base_confidence + (0.04 * native_greek_ratio)
        confidence -= computed_greek_ratio * (
            0.08 if provider_mode == "yfinance_proxy" else 0.03
        )

        return float(np.clip(confidence, 0.05, 0.98))
