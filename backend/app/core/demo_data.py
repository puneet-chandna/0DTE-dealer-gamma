"""Shared demo data service for reviewer-safe synthetic sessions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.core.analytics import VolatilityAnalyzer
from app.core.constants import LONG_GAMMA_THRESHOLD, SHORT_GAMMA_THRESHOLD
from app.core.data_acquisition import get_current_trading_date
from app.core.gex_calculator import GEXCalculator
from app.core.technical_indicators import TechnicalIndicatorEngine
from app.models.schemas import GEXSnapshot

ET = ZoneInfo("America/New_York")
SESSION_START = time(9, 30)
SESSION_MINUTES = 390
WEBSOCKET_BUCKET_SECONDS = 5

DEFAULT_SYMBOL_PRICES = {
    "SPX": 5900.0,
    "SPY": 590.0,
    "QQQ": 505.0,
    "IWM": 225.0,
}

SYMBOL_STRIKE_STEPS = {
    "SPX": 5.0,
    "SPY": 1.0,
    "QQQ": 1.0,
    "IWM": 1.0,
}

PERIOD_TO_DAYS = {
    "1d": 1,
    "5d": 5,
    "1mo": 30,
    "3mo": 90,
    "6mo": 180,
    "1y": 365,
}

RESAMPLE_RULES = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "1h": "1h",
    "1d": "1D",
    "1wk": "1W",
}


@dataclass(frozen=True)
class DemoSession:
    """Synthetic market session for a single symbol and trading date."""

    symbol: str
    trading_date: date
    price_data: pd.DataFrame
    gex_data: pd.DataFrame
    strike_step: float


class DemoDataService:
    """Generate deterministic, coherent demo data across app surfaces."""

    def __init__(self) -> None:
        self._gex_calculator = GEXCalculator()

    def get_current_snapshot(
        self,
        symbol: str = "SPX",
        now: Optional[datetime] = None,
        anchor_snapshot: Optional[GEXSnapshot] = None,
    ) -> GEXSnapshot:
        """Return the current synthetic snapshot for the active 5-second bucket."""
        normalized_now = self._normalize_now(now)
        session = self._resolve_session(
            symbol,
            get_current_trading_date(normalized_now),
            anchor_snapshot=anchor_snapshot,
        )
        bucket_index = int(normalized_now.timestamp()) // WEBSOCKET_BUCKET_SECONDS
        row_index = bucket_index % len(session.gex_data)
        return self._snapshot_from_session_row(
            session=session,
            row_index=row_index,
            timestamp=normalized_now,
            bucket_index=bucket_index,
        )

    def get_time_series(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        interval: str = "1min",
        anchor_snapshot: Optional[GEXSnapshot] = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return aligned price and GEX data across the requested date range."""
        sessions = [
            self._resolve_session(symbol, trading_date, anchor_snapshot=anchor_snapshot)
            for trading_date in self._iter_trading_dates(start_date, end_date)
        ]
        if not sessions:
            sessions = [self._resolve_session(symbol, start_date, anchor_snapshot=anchor_snapshot)]

        price_frames = [session.price_data for session in sessions]
        gex_frames = [session.gex_data for session in sessions]

        price_data = pd.concat(price_frames).sort_index()
        gex_data = pd.concat(gex_frames).sort_index()

        if interval in {"1min", "1m"}:
            return price_data, gex_data

        rule = RESAMPLE_RULES.get(interval)
        if not rule:
            return price_data, gex_data

        return self._resample_time_series(price_data, gex_data, rule)

    def get_historical_snapshots(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        interval: str,
        anchor_snapshot: Optional[GEXSnapshot] = None,
    ) -> list[GEXSnapshot]:
        """Build historical snapshots for charts and replay views."""
        _, gex_data = self.get_time_series(
            symbol,
            start_date,
            end_date,
            interval,
            anchor_snapshot=anchor_snapshot,
        )

        snapshots: list[GEXSnapshot] = []
        for row_index, (timestamp, row) in enumerate(gex_data.iterrows()):
            session = self._resolve_session(
                symbol,
                timestamp.astimezone(ET).date(),
                anchor_snapshot=anchor_snapshot,
            )
            intraday_index = self._session_row_index(timestamp)
            snapshots.append(
                self._snapshot_from_session_row(
                    session=session,
                    row_index=intraday_index,
                    timestamp=timestamp.to_pydatetime(),
                    bucket_index=row_index,
                    override_row=row,
                )
            )
        return snapshots

    def get_summary_statistics(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        anchor_snapshot: Optional[GEXSnapshot] = None,
    ):
        """Compute summary statistics from the coherent demo GEX history."""
        _, gex_data = self.get_time_series(
            symbol,
            start_date,
            end_date,
            anchor_snapshot=anchor_snapshot,
        )
        return VolatilityAnalyzer.compute_summary_statistics(gex_data)

    def get_iv_surface(
        self,
        symbol: str,
        now: Optional[datetime] = None,
        anchor_snapshot: Optional[GEXSnapshot] = None,
    ) -> dict:
        """Generate a deterministic IV surface and skew from the active demo session."""
        snapshot = self.get_current_snapshot(
            symbol=symbol,
            now=now,
            anchor_snapshot=anchor_snapshot,
        )
        spot = snapshot.spot_price
        strikes = sorted(snapshot.gex_by_strike.keys())
        regime_shift = 0.03 if snapshot.net_gex < SHORT_GAMMA_THRESHOLD else 0.0
        now_dt = self._normalize_now(now)
        bucket_index = int(now_dt.timestamp()) // WEBSOCKET_BUCKET_SECONDS

        surface = []
        skew = []
        for index, strike in enumerate(strikes):
            moneyness = (strike - spot) / max(spot, 1.0)
            base_iv = 0.16 + abs(moneyness) * 1.8 + regime_shift
            call_iv = max(0.08, base_iv + 0.01 * np.sin(index + bucket_index / 11))
            put_iv = max(0.09, base_iv + 0.03 + 0.012 * np.cos(index + bucket_index / 13))

            call_intrinsic = max(spot - strike, 0.0)
            put_intrinsic = max(strike - spot, 0.0)
            time_value = max(0.25, abs(moneyness) * spot * 0.18)

            surface.append(
                {
                    "strike": float(strike),
                    "type": "call",
                    "iv": float(round(call_iv, 4)),
                    "mid_price": float(round(call_intrinsic + time_value, 4)),
                    "moneyness": float(round(moneyness, 6)),
                }
            )
            surface.append(
                {
                    "strike": float(strike),
                    "type": "put",
                    "iv": float(round(put_iv, 4)),
                    "mid_price": float(round(put_intrinsic + time_value * 1.05, 4)),
                    "moneyness": float(round(moneyness, 6)),
                }
            )
            skew.append(
                {
                    "strike": float(strike),
                    "call_iv": float(round(call_iv, 4)),
                    "put_iv": float(round(put_iv, 4)),
                    "skew": float(round(put_iv - call_iv, 4)),
                    "moneyness": float(round(moneyness, 6)),
                }
            )

        return {
            "symbol": symbol,
            "spot_price": spot,
            "surface": surface,
            "skew": skew,
            "count": len(surface),
        }

    def get_technical_indicators(
        self,
        symbol: str,
        period: str,
        interval: str,
        indicators: list[str],
        now: Optional[datetime] = None,
        anchor_snapshot: Optional[GEXSnapshot] = None,
    ) -> dict:
        """Generate deterministic indicator overlays from the same demo price series."""
        normalized_now = self._normalize_now(now)
        end_date = normalized_now.date()
        start_date = end_date - timedelta(days=PERIOD_TO_DAYS.get(period, 30) - 1)
        price_data, _ = self.get_time_series(
            symbol,
            start_date,
            end_date,
            interval,
            anchor_snapshot=anchor_snapshot,
        )
        indicator_list = [indicator.strip().upper() for indicator in indicators if indicator.strip()]
        if not indicator_list:
            indicator_list = ["ATR", "RSI", "BBANDS"]

        if len(price_data) >= 5:
            indicator_df = TechnicalIndicatorEngine.compute_indicators(
                price_data,
                indicators=indicator_list,
            )
        else:
            indicator_df = price_data.copy()
            for column in ("atr", "rsi", "bb_upper", "bb_mid", "bb_lower"):
                indicator_df[column] = np.nan

        data = []
        for idx, row in indicator_df.iterrows():
            data.append(
                {
                    "timestamp": str(idx),
                    "close": float(row["close"]),
                    "atr": None if pd.isna(row.get("atr")) else float(row["atr"]),
                    "rsi": None if pd.isna(row.get("rsi")) else float(row["rsi"]),
                    "bb_upper": None if pd.isna(row.get("bb_upper")) else float(row["bb_upper"]),
                    "bb_mid": None if pd.isna(row.get("bb_mid")) else float(row["bb_mid"]),
                    "bb_lower": None if pd.isna(row.get("bb_lower")) else float(row["bb_lower"]),
                }
            )

        return {
            "symbol": symbol,
            "period": period,
            "indicators": indicator_list,
            "data": data,
            "count": len(data),
        }

    def get_ws_update(
        self,
        symbol: str = "SPX",
        now: Optional[datetime] = None,
        anchor_snapshot: Optional[GEXSnapshot] = None,
    ) -> dict:
        """Build the lightweight WebSocket update payload for demo mode."""
        snapshot = self.get_current_snapshot(
            symbol=symbol,
            now=now,
            anchor_snapshot=anchor_snapshot,
        )
        regime, _, _ = self._gex_calculator.determine_regime(snapshot.net_gex)
        return {
            "net_gex": snapshot.net_gex,
            "net_gex_billions": snapshot.net_gex / 1e9,
            "zero_gamma_level": snapshot.zero_gamma_level,
            "spot_price": snapshot.spot_price,
            "regime": regime,
            "timestamp": snapshot.timestamp.isoformat(),
            "is_mock": True,
            "is_demo": True,
            "is_stale": False,
        }

    @staticmethod
    def _optional_rounded_anchor(value: Optional[float], *, digits: int = 4) -> Optional[float]:
        """Convert snapshot metrics for anchoring; None stays None (no float(None))."""
        if value is None:
            return None
        return round(float(value), digits)

    def _resolve_session(
        self,
        symbol: str,
        trading_date: date,
        anchor_snapshot: Optional[GEXSnapshot] = None,
    ) -> DemoSession:
        if anchor_snapshot is None:
            return self._get_session(symbol, trading_date)

        return self._get_anchored_session(
            symbol,
            trading_date,
            DemoDataService._optional_rounded_anchor(anchor_snapshot.spot_price),
            DemoDataService._optional_rounded_anchor(anchor_snapshot.net_gex),
            DemoDataService._optional_rounded_anchor(anchor_snapshot.zero_gamma_level),
            DemoDataService._optional_rounded_anchor(anchor_snapshot.total_call_gex),
            DemoDataService._optional_rounded_anchor(anchor_snapshot.total_put_gex),
        )

    @staticmethod
    @lru_cache(maxsize=256)
    def _get_anchored_session(
        symbol: str,
        trading_date: date,
        anchor_spot_price: Optional[float],
        anchor_net_gex: Optional[float],
        anchor_zero_gamma_level: Optional[float],
        anchor_total_call_gex: Optional[float],
        anchor_total_put_gex: Optional[float],
    ) -> DemoSession:
        base_session = DemoDataService._get_session(symbol, trading_date)

        price_data = base_session.price_data.copy()
        price_close_mean = float(price_data["close"].mean())
        eff_spot = anchor_spot_price if anchor_spot_price is not None else price_close_mean
        price_shift = eff_spot - price_close_mean
        for column in ("open", "high", "low", "close"):
            price_data[column] = price_data[column] + price_shift

        gex_data = base_session.gex_data.copy()
        gex_spot_mean = float(gex_data["spot_price"].mean())
        gex_data["spot_price"] = gex_data["spot_price"] + (eff_spot - gex_spot_mean)

        net_mean = float(gex_data["net_gex"].mean())
        eff_net = anchor_net_gex if anchor_net_gex is not None else net_mean
        gex_data["net_gex"] = np.clip(
            gex_data["net_gex"] + (eff_net - net_mean),
            -3.2e9,
            2.4e9,
        )

        base_call_abs = np.abs(base_session.gex_data["total_call_gex"].to_numpy())
        call_mean_abs = float(base_call_abs.mean())
        eff_call = anchor_total_call_gex if anchor_total_call_gex is not None else call_mean_abs
        target_call_abs = max(abs(eff_call), abs(eff_net) * 0.55, 8.5e8)
        call_scale = target_call_abs / max(float(base_call_abs.mean()), 1.0)
        gex_data["total_call_gex"] = -np.maximum(base_call_abs * call_scale, 1.0)
        gex_data["total_put_gex"] = gex_data["net_gex"] - gex_data["total_call_gex"]

        zero_gamma_offset = (
            base_session.gex_data["zero_gamma_level"] - base_session.gex_data["spot_price"]
        )
        if anchor_zero_gamma_level is not None:
            target_offset = anchor_zero_gamma_level - eff_spot
            offset_shift = target_offset - float(zero_gamma_offset.mean())
        else:
            offset_shift = 0.0
        gex_data["zero_gamma_level"] = gex_data["spot_price"] + zero_gamma_offset + offset_shift

        if anchor_total_put_gex is not None:
            put_adjustment = anchor_total_put_gex - float(gex_data["total_put_gex"].mean())
            gex_data["total_put_gex"] = gex_data["total_put_gex"] + put_adjustment
            gex_data["total_call_gex"] = gex_data["net_gex"] - gex_data["total_put_gex"]

        return DemoSession(
            symbol=base_session.symbol,
            trading_date=base_session.trading_date,
            price_data=price_data,
            gex_data=gex_data,
            strike_step=base_session.strike_step,
        )

    def _snapshot_from_session_row(
        self,
        session: DemoSession,
        row_index: int,
        timestamp: datetime,
        bucket_index: int,
        override_row: Optional[pd.Series] = None,
    ) -> GEXSnapshot:
        row = override_row if override_row is not None else session.gex_data.iloc[row_index]
        spot = float(row["spot_price"])
        net_gex = float(row["net_gex"])
        total_call_gex = float(row["total_call_gex"])
        total_put_gex = float(row["total_put_gex"])
        zero_gamma_level = float(row["zero_gamma_level"])
        gex_by_strike = self._build_strike_map(
            spot=spot,
            net_gex=net_gex,
            strike_step=session.strike_step,
            row_index=row_index,
        )
        dominant_strike = max(gex_by_strike, key=lambda strike: abs(gex_by_strike[strike]))
        regime_code = 1.0 if net_gex > LONG_GAMMA_THRESHOLD else -1.0 if net_gex < SHORT_GAMMA_THRESHOLD else 0.0

        return GEXSnapshot(
            timestamp=timestamp,
            spot_price=spot,
            total_call_gex=total_call_gex,
            total_put_gex=total_put_gex,
            net_gex=net_gex,
            zero_gamma_level=zero_gamma_level,
            gex_by_strike=gex_by_strike,
            dominant_strike=float(dominant_strike),
            metrics={
                "regime_code": regime_code,
                "gex_imbalance": abs(total_call_gex) / max(abs(total_put_gex), 1.0),
                "is_demo_data": 1.0,
                "demo_bucket": float(bucket_index),
            },
        )

    def _build_strike_map(
        self,
        spot: float,
        net_gex: float,
        strike_step: float,
        row_index: int,
    ) -> dict[float, float]:
        center = round(spot / strike_step) * strike_step
        offsets = np.arange(-8, 9, dtype=float)
        gaussian = np.exp(-0.18 * np.square(offsets))
        wave = np.cos((offsets + row_index / 9) / 1.7)
        raw = gaussian * wave
        scale = max(abs(net_gex) * 1.3, 3.5e8)
        values = raw / max(np.sum(np.abs(raw)), 1e-6) * scale

        strike_map = {}
        for offset, value in zip(offsets, values):
            strike = round(center + offset * strike_step, 4)
            strike_map[float(strike)] = float(value)
        return strike_map

    @staticmethod
    def _resample_time_series(
        price_data: pd.DataFrame,
        gex_data: pd.DataFrame,
        rule: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        price_resampled = (
            price_data.resample(rule)
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna()
        )

        gex_resampled = (
            gex_data.resample(rule)
            .agg(
                {
                    "spot_price": "last",
                    "net_gex": "last",
                    "total_call_gex": "last",
                    "total_put_gex": "last",
                    "zero_gamma_level": "last",
                }
            )
            .dropna()
        )
        return price_resampled, gex_resampled

    @staticmethod
    def _session_row_index(timestamp: pd.Timestamp) -> int:
        localized = timestamp.tz_convert(ET) if timestamp.tzinfo else timestamp.tz_localize(ET)
        session_open = datetime.combine(localized.date(), SESSION_START, tzinfo=ET)
        delta_minutes = int((localized.to_pydatetime() - session_open).total_seconds() // 60)
        return max(0, min(SESSION_MINUTES - 1, delta_minutes))

    @staticmethod
    def _iter_trading_dates(start_date: date, end_date: date) -> Iterable[date]:
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                yield current
            current += timedelta(days=1)

    @staticmethod
    def _normalize_now(now: Optional[datetime]) -> datetime:
        if now is None:
            return datetime.now(ET)
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone.utc).astimezone(ET)
        return now.astimezone(ET)

    @staticmethod
    def _seed_for(symbol: str, trading_date: date) -> int:
        digest = hashlib.sha256(f"{symbol}:{trading_date.isoformat()}".encode("utf-8")).hexdigest()
        return int(digest[:16], 16) % (2**32)

    @staticmethod
    def _base_price_for(symbol: str) -> float:
        return DEFAULT_SYMBOL_PRICES.get(symbol.upper(), 250.0)

    @staticmethod
    def _strike_step_for(symbol: str) -> float:
        return SYMBOL_STRIKE_STEPS.get(symbol.upper(), 1.0)

    @staticmethod
    @lru_cache(maxsize=128)
    def _get_session(symbol: str, trading_date: date) -> DemoSession:
        symbol = symbol.upper()
        seed = DemoDataService._seed_for(symbol, trading_date)
        rng = np.random.default_rng(seed)
        base_price = DemoDataService._base_price_for(symbol)
        strike_step = DemoDataService._strike_step_for(symbol)

        session_open = datetime.combine(trading_date, SESSION_START, tzinfo=ET)
        index = pd.date_range(session_open, periods=SESSION_MINUTES, freq="1min", tz=ET)
        minutes = np.arange(SESSION_MINUTES)

        trend = np.linspace(0.0, rng.normal(0.0, base_price * 0.01), SESSION_MINUTES)
        intraday_wave = np.sin(np.linspace(0.0, 2.7 * np.pi, SESSION_MINUTES) + rng.uniform(-1.0, 1.0))
        secondary_wave = np.cos(np.linspace(0.0, 7.5 * np.pi, SESSION_MINUTES) + rng.uniform(-1.0, 1.0))
        noise = rng.normal(0.0, base_price * 0.0015, SESSION_MINUTES).cumsum() * 0.08

        close = base_price + trend + intraday_wave * base_price * 0.004 + secondary_wave * base_price * 0.0015 + noise
        open_ = np.concatenate(([close[0]], close[:-1])) + rng.normal(0.0, base_price * 0.0004, SESSION_MINUTES)
        spread = np.abs(rng.normal(base_price * 0.0012, base_price * 0.0002, SESSION_MINUTES))
        high = np.maximum(open_, close) + spread
        low = np.minimum(open_, close) - spread
        volume = rng.integers(5_000, 25_000, SESSION_MINUTES)

        normalized_move = (close - close.mean()) / max(base_price, 1.0)
        gex_wave = np.sin(np.linspace(0.0, 3.5 * np.pi, SESSION_MINUTES) + rng.uniform(-0.8, 0.8)) * 1.15e9
        gex_shock = np.cos(np.linspace(0.0, 10 * np.pi, SESSION_MINUTES) + rng.uniform(-0.8, 0.8)) * 3.2e8
        gex_bias = rng.uniform(-1.2e9, 1.1e9)
        net_gex = np.clip(gex_bias + gex_wave + gex_shock - normalized_move * 1.8e9, -3.2e9, 2.4e9)
        call_abs = np.abs(net_gex) * 0.55 + rng.uniform(8.5e8, 1.45e9, SESSION_MINUTES)
        total_call_gex = -call_abs
        total_put_gex = net_gex - total_call_gex
        zero_gamma_level = close + np.tanh(-net_gex / 1.4e9) * 14 + np.sin(minutes / 17) * 2.5

        price_data = pd.DataFrame(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            },
            index=index,
        )

        gex_data = pd.DataFrame(
            {
                "spot_price": close,
                "net_gex": net_gex,
                "total_call_gex": total_call_gex,
                "total_put_gex": total_put_gex,
                "zero_gamma_level": zero_gamma_level,
            },
            index=index,
        )

        return DemoSession(
            symbol=symbol,
            trading_date=trading_date,
            price_data=price_data,
            gex_data=gex_data,
            strike_step=strike_step,
        )


_demo_data_service: Optional[DemoDataService] = None


def get_demo_data_service() -> DemoDataService:
    """Return the shared demo data service singleton."""
    global _demo_data_service
    if _demo_data_service is None:
        _demo_data_service = DemoDataService()
    return _demo_data_service
