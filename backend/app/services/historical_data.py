"""Historical persistence and replay service backed by PostgreSQL/SQLite."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.analytics import TradingStrategy, VolatilityAnalyzer
from app.core.snapshot_quality import is_snapshot_replay_eligible
from app.core.technical_indicators import TechnicalIndicatorEngine
from app.core.vectorbt_backtester import VectorBTBacktester
from app.db.models import (
    GEXByStrikePointRecord,
    GEXSnapshotRecord,
    IVSurfacePointRecord,
    MarketSessionRecord,
    RawOptionsSnapshotRecord,
)
from app.db.session import get_session_factory
from app.models.schemas import GEXSnapshot

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)
REPLAY_COMPLETE_AFTER = time(15, 55)
RAW_SNAPSHOT_INTERVAL_SECONDS = 60
RETENTION_DAYS = 30
WATCHLIST_SYMBOLS = ("SPX", "SPY", "QQQ", "IWM")

INTERVAL_RULES = {
    "5s": None,
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "1h": "1h",
    "1d": "1D",
    "1wk": "1W",
}

PERIOD_TO_DAYS = {
    "1d": 1,
    "5d": 5,
    "1mo": 30,
    "3mo": 90,
    "6mo": 180,
    "1y": 365,
}

_historical_data_service: Optional["HistoricalDataService"] = None


def get_historical_data_service() -> "HistoricalDataService":
    """Return the shared historical data service."""
    global _historical_data_service
    if _historical_data_service is None:
        _historical_data_service = HistoricalDataService()
    return _historical_data_service


class HistoricalDataService:
    """Persist live captures and serve DB-backed historical/replay data."""

    def __init__(
        self,
        *,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_factory = session_factory

    def _get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory or get_session_factory()

    async def persist_capture(
        self,
        *,
        provider: str,
        symbol: str,
        snapshot: GEXSnapshot | dict[str, Any],
        options_df: Optional[pd.DataFrame],
        force_raw_capture: bool = False,
    ) -> bool:
        """Persist a derived GEX snapshot and optional raw options sidecar."""
        provider_name = provider.strip().lower()
        underlying = symbol.strip().upper()
        snapshot_dict = self._normalize_snapshot(snapshot)
        captured_at = self._normalize_timestamp(snapshot_dict["timestamp"])
        trading_date = captured_at.astimezone(ET).date()

        try:
            async with self._get_session_factory()() as session:
                market_session = await self._get_or_create_market_session(
                    session=session,
                    provider=provider_name,
                    symbol=underlying,
                    trading_date=trading_date,
                )

                gex_snapshot = GEXSnapshotRecord(
                    session_id=market_session.id,
                    provider=provider_name,
                    symbol=underlying,
                    captured_at=captured_at,
                    spot_price=float(snapshot_dict["spot_price"]),
                    total_call_gex=float(snapshot_dict["total_call_gex"]),
                    total_put_gex=float(snapshot_dict["total_put_gex"]),
                    net_gex=float(snapshot_dict["net_gex"]),
                    zero_gamma_level=float(snapshot_dict["zero_gamma_level"]),
                    dominant_strike=float(snapshot_dict["dominant_strike"]),
                    metrics=dict(snapshot_dict.get("metrics") or {}),
                )
                session.add(gex_snapshot)
                await session.flush()

                strike_points = [
                    GEXByStrikePointRecord(
                        snapshot_id=gex_snapshot.id,
                        strike=float(strike),
                        gex_value=float(value),
                    )
                    for strike, value in sorted((snapshot_dict.get("gex_by_strike") or {}).items())
                ]
                session.add_all(strike_points)

                raw_persisted = False
                normalized_chain = self._normalize_options_df(options_df)
                if force_raw_capture or await self._should_persist_raw_snapshot(
                    session=session,
                    provider=provider_name,
                    symbol=underlying,
                    captured_at=captured_at,
                ):
                    raw_record = await self._persist_raw_options_snapshot(
                        session=session,
                        market_session=market_session,
                        provider=provider_name,
                        symbol=underlying,
                        captured_at=captured_at,
                        spot_price=float(snapshot_dict["spot_price"]),
                        options_df=normalized_chain,
                    )
                    raw_persisted = raw_record is not None
                    if raw_record is not None:
                        iv_points = self._build_iv_surface_points(
                            raw_snapshot_id=raw_record.id,
                            provider=provider_name,
                            symbol=underlying,
                            captured_at=captured_at,
                            spot_price=float(snapshot_dict["spot_price"]),
                            options_df=normalized_chain,
                        )
                        session.add_all(iv_points)

                market_session.snapshot_count += 1
                first_captured_at = (
                    self._normalize_timestamp(market_session.first_captured_at)
                    if market_session.first_captured_at is not None
                    else None
                )
                last_captured_at = (
                    self._normalize_timestamp(market_session.last_captured_at)
                    if market_session.last_captured_at is not None
                    else None
                )

                if first_captured_at is None or captured_at < first_captured_at:
                    market_session.first_captured_at = captured_at
                    first_captured_at = captured_at
                if last_captured_at is None or captured_at > last_captured_at:
                    market_session.last_captured_at = captured_at
                    last_captured_at = captured_at
                if raw_persisted:
                    market_session.raw_snapshot_count += 1

                market_session.completeness_ratio = self._calculate_completeness_ratio(
                    trading_date=trading_date,
                    first_captured_at=first_captured_at,
                    last_captured_at=last_captured_at,
                )
                market_session.status = self._determine_session_status(
                    trading_date=trading_date,
                    last_captured_at=last_captured_at,
                )

                await self._apply_retention(session, reference_date=trading_date)
                await session.commit()
            return True
        except Exception as exc:
            logger.warning(
                "Historical capture persistence failed for %s/%s: %s",
                provider_name,
                underlying,
                exc,
            )
            return False

    async def finalize_stale_sessions(self, reference_time: Optional[datetime] = None) -> bool:
        """Mark completed sessions as replayable after the market has moved on."""
        normalized_reference = self._normalize_timestamp(reference_time or datetime.now(ET))
        current_et_date = normalized_reference.astimezone(ET).date()
        current_et_time = normalized_reference.astimezone(ET).time()

        try:
            async with self._get_session_factory()() as session:
                result = await session.execute(
                    select(MarketSessionRecord).where(MarketSessionRecord.status != "complete")
                )
                sessions = result.scalars().all()

                changed = False
                for market_session in sessions:
                    should_complete = market_session.trading_date < current_et_date or (
                        market_session.trading_date == current_et_date
                        and current_et_time >= SESSION_CLOSE
                    )
                    if should_complete:
                        market_session.status = "complete"
                        market_session.completeness_ratio = max(
                            market_session.completeness_ratio,
                            1.0 if market_session.last_captured_at else market_session.completeness_ratio,
                        )
                        changed = True

                if changed:
                    await session.commit()
                else:
                    await session.rollback()
            return True
        except Exception as exc:
            logger.warning("Historical session finalization failed: %s", exc)
            return False

    async def get_historical_snapshots(
        self,
        *,
        provider: str,
        symbol: str,
        start_date: date,
        end_date: date,
        interval: str = "1m",
        prefer_replay: bool = False,
    ) -> list[GEXSnapshot]:
        """Return stored historical GEX snapshots for the requested range."""
        records = await self._load_snapshot_records(
            provider=provider,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        if prefer_replay:
            records = self._filter_replay_eligible_records(records)
        if not records and prefer_replay:
            records = self._filter_replay_eligible_records(
                await self._load_latest_replay_snapshot_records(provider=provider, symbol=symbol)
            )

        return self._records_to_snapshots(records, interval=interval)

    async def get_summary_statistics(
        self,
        *,
        provider: str,
        symbol: str,
        start_date: date,
        end_date: date,
        prefer_replay: bool = False,
    ):
        """Compute summary statistics from stored GEX history."""
        _, gex_data = await self.get_time_series_frames(
            provider=provider,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            interval="1m",
            prefer_replay=prefer_replay,
        )
        if gex_data.empty:
            return None
        return VolatilityAnalyzer.compute_summary_statistics(gex_data)

    async def get_iv_surface(
        self,
        *,
        provider: str,
        symbol: str,
        prefer_replay: bool = False,
    ) -> Optional[dict[str, Any]]:
        """Return the latest stored IV surface for a provider/symbol."""
        provider_name = provider.strip().lower()
        underlying = symbol.strip().upper()

        try:
            async with self._get_session_factory()() as session:
                raw_snapshot = await self._get_latest_raw_snapshot(
                    session=session,
                    provider=provider_name,
                    symbol=underlying,
                    prefer_replay=prefer_replay,
                )
                if raw_snapshot is None:
                    return None

                iv_rows = (
                    await session.execute(
                        select(IVSurfacePointRecord)
                        .where(IVSurfacePointRecord.raw_snapshot_id == raw_snapshot.id)
                        .order_by(IVSurfacePointRecord.strike, IVSurfacePointRecord.option_type)
                    )
                ).scalars().all()

            if not iv_rows:
                return None

            surface = [
                {
                    "strike": row.strike,
                    "type": row.option_type,
                    "iv": row.iv,
                    "mid_price": row.mid_price,
                    "moneyness": row.moneyness,
                }
                for row in iv_rows
            ]
            skew = self._build_skew_points(iv_rows)
            return {
                "symbol": underlying,
                "spot_price": raw_snapshot.spot_price,
                "surface": surface,
                "skew": skew,
                "count": len(surface),
            }
        except Exception as exc:
            logger.warning("IV surface lookup failed for %s/%s: %s", provider_name, underlying, exc)
            return None

    async def get_technical_indicators(
        self,
        *,
        provider: str,
        symbol: str,
        period: str,
        interval: str,
        indicators: list[str],
        prefer_replay: bool = False,
    ) -> Optional[dict[str, Any]]:
        """Compute technical indicators from persisted spot-price history."""
        latest_timestamp = await self.get_latest_timestamp(
            provider=provider,
            symbol=symbol,
            prefer_replay=prefer_replay,
        )
        if latest_timestamp is None:
            return None

        end_date = latest_timestamp.astimezone(ET).date()
        start_date = end_date - timedelta(days=self._days_for_period(period) - 1)
        price_data, _ = await self.get_time_series_frames(
            provider=provider,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            interval=interval,
            prefer_replay=prefer_replay,
        )
        if price_data.empty:
            return None

        indicator_names = [item.strip().upper() for item in indicators if item.strip()]
        if not indicator_names:
            indicator_names = ["ATR", "RSI", "BBANDS"]

        if len(price_data) >= 5:
            indicator_df = TechnicalIndicatorEngine.compute_indicators(price_data, indicators=indicator_names)
        else:
            indicator_df = price_data.copy()
            for column in ("atr", "rsi", "bb_upper", "bb_mid", "bb_lower"):
                indicator_df[column] = pd.NA

        points = []
        for idx, row in indicator_df.iterrows():
            points.append(
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
            "symbol": symbol.strip().upper(),
            "period": period,
            "indicators": indicator_names,
            "data": points,
            "count": len(points),
        }

    async def get_time_series_frames(
        self,
        *,
        provider: str,
        symbol: str,
        start_date: date,
        end_date: date,
        interval: str = "1m",
        prefer_replay: bool = False,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return price and GEX DataFrames derived from stored captures."""
        records = await self._load_snapshot_records(
            provider=provider,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        if prefer_replay:
            records = self._filter_replay_eligible_records(records)
        if not records and prefer_replay:
            records = self._filter_replay_eligible_records(
                await self._load_latest_replay_snapshot_records(provider=provider, symbol=symbol)
            )
        if not records:
            return pd.DataFrame(), pd.DataFrame()

        frame = pd.DataFrame(
            [
                {
                    "captured_at": record.captured_at,
                    "spot_price": record.spot_price,
                    "net_gex": record.net_gex,
                    "total_call_gex": record.total_call_gex,
                    "total_put_gex": record.total_put_gex,
                    "zero_gamma_level": record.zero_gamma_level,
                }
                for record in records
            ]
        )
        frame["captured_at"] = pd.to_datetime(frame["captured_at"], utc=True).dt.tz_convert(ET)
        frame = frame.set_index("captured_at").sort_index()

        rule = self._get_resample_rule(interval)
        close_series = frame["spot_price"]

        if rule is None:
            price_data = pd.DataFrame(
                {
                    "open": close_series,
                    "high": close_series,
                    "low": close_series,
                    "close": close_series,
                    "volume": 0.0,
                }
            )
            gex_data = frame[
                ["spot_price", "net_gex", "total_call_gex", "total_put_gex", "zero_gamma_level"]
            ].copy()
            return price_data, gex_data

        ohlc = close_series.resample(rule).ohlc().dropna()
        ohlc["volume"] = 0.0
        gex_data = (
            frame[["spot_price", "net_gex", "total_call_gex", "total_put_gex", "zero_gamma_level"]]
            .resample(rule)
            .last()
            .dropna()
        )
        return ohlc, gex_data

    async def run_backtest(
        self,
        *,
        provider: str,
        symbol: str,
        start_date: date,
        end_date: date,
        strategy: str,
        entry_threshold: float,
        exit_threshold: float,
        stop_loss_pct: float,
        take_profit_pct: float,
        prefer_replay: bool = False,
    ):
        """Run the core backtest from persisted history."""
        price_data, gex_data = await self.get_time_series_frames(
            provider=provider,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            interval="1m",
            prefer_replay=prefer_replay,
        )
        if gex_data.empty or price_data.empty:
            return None
        if strategy != "volatility_breakout":
            raise ValueError(f"Unknown strategy: {strategy}")
        return TradingStrategy.volatility_breakout_strategy(
            gex_data=gex_data,
            price_data=price_data,
            entry_threshold=entry_threshold,
            exit_threshold=exit_threshold,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
        )

    async def run_vectorbt_backtest(
        self,
        *,
        provider: str,
        symbol: str,
        start_date: date,
        end_date: date,
        entry_threshold: float,
        exit_threshold: float,
        initial_cash: float,
        prefer_replay: bool = False,
    ):
        """Run the vectorbt backtest from persisted history."""
        price_data, gex_data = await self.get_time_series_frames(
            provider=provider,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            interval="1m",
            prefer_replay=prefer_replay,
        )
        if gex_data.empty or price_data.empty:
            return None
        return VectorBTBacktester.run_gex_signal_backtest(
            price_data=price_data,
            gex_data=gex_data,
            entry_threshold=entry_threshold,
            exit_threshold=exit_threshold,
            initial_cash=initial_cash,
        )

    async def get_latest_timestamp(
        self,
        *,
        provider: str,
        symbol: str,
        prefer_replay: bool = False,
    ) -> Optional[datetime]:
        """Return the most recent stored capture timestamp."""
        provider_name = provider.strip().lower()
        underlying = symbol.strip().upper()

        try:
            async with self._get_session_factory()() as session:
                if prefer_replay:
                    records = self._filter_replay_eligible_records(
                        await self._load_latest_replay_snapshot_records(
                            provider=provider_name,
                            symbol=underlying,
                        )
                    )
                    return records[-1].captured_at if records else None

                result = await session.execute(
                    select(func.max(GEXSnapshotRecord.captured_at)).where(
                        GEXSnapshotRecord.provider == provider_name,
                        GEXSnapshotRecord.symbol == underlying,
                    )
                )
                return result.scalar_one_or_none()
        except Exception as exc:
            logger.warning("Latest timestamp lookup failed for %s/%s: %s", provider_name, underlying, exc)
            return None

    async def get_latest_snapshot(
        self,
        *,
        provider: str,
        symbol: str,
        prefer_replay: bool = False,
        replay_eligible_only: bool = False,
    ) -> Optional[GEXSnapshot]:
        """Return the newest stored snapshot for a provider/symbol."""
        provider_name = provider.strip().lower()
        underlying = symbol.strip().upper()

        try:
            if prefer_replay:
                replay_records = self._filter_replay_eligible_records(
                    await self._load_latest_replay_snapshot_records(
                        provider=provider_name,
                        symbol=underlying,
                    )
                )
                if not replay_records:
                    return None
                return self._record_to_snapshot(replay_records[-1])

            async with self._get_session_factory()() as session:
                if not replay_eligible_only:
                    result = await session.execute(
                        select(GEXSnapshotRecord)
                        .options(selectinload(GEXSnapshotRecord.strike_points))
                        .where(
                            GEXSnapshotRecord.provider == provider_name,
                            GEXSnapshotRecord.symbol == underlying,
                        )
                        .order_by(GEXSnapshotRecord.captured_at.desc())
                        .limit(1)
                    )
                    latest_record = result.scalar_one_or_none()
                    if latest_record is None:
                        return None
                    return self._record_to_snapshot(latest_record)

                result = await session.execute(
                    select(GEXSnapshotRecord)
                    .options(selectinload(GEXSnapshotRecord.strike_points))
                    .where(
                        GEXSnapshotRecord.provider == provider_name,
                        GEXSnapshotRecord.symbol == underlying,
                    )
                    .order_by(GEXSnapshotRecord.captured_at.desc())
                )
                for candidate in result.scalars():
                    if self._record_is_replay_eligible(candidate):
                        return self._record_to_snapshot(candidate)
                return None
        except Exception as exc:
            logger.warning(
                "Latest snapshot lookup failed for %s/%s: %s",
                provider_name,
                underlying,
                exc,
            )
            return None

    @classmethod
    def _filter_replay_eligible_records(
        cls,
        records: list[GEXSnapshotRecord],
    ) -> list[GEXSnapshotRecord]:
        return [record for record in records if cls._record_is_replay_eligible(record)]

    @classmethod
    def _record_is_replay_eligible(cls, record: GEXSnapshotRecord) -> bool:
        metrics = dict(record.metrics or {})

        explicit_eligibility = metrics.get("is_replay_eligible")
        if isinstance(explicit_eligibility, bool):
            return explicit_eligibility
        if isinstance(explicit_eligibility, (int, float)):
            return bool(explicit_eligibility)

        quality_flags = metrics.get("quality_flags")
        if isinstance(quality_flags, list) and quality_flags:
            return False

        capture_quality = metrics.get("capture_quality")
        if isinstance(capture_quality, (int, float)):
            return float(capture_quality) > 0

        return is_snapshot_replay_eligible(cls._record_to_snapshot(record))

    async def _get_or_create_market_session(
        self,
        *,
        session: AsyncSession,
        provider: str,
        symbol: str,
        trading_date: date,
    ) -> MarketSessionRecord:
        result = await session.execute(
            select(MarketSessionRecord).where(
                MarketSessionRecord.provider == provider,
                MarketSessionRecord.symbol == symbol,
                MarketSessionRecord.trading_date == trading_date,
            )
        )
        market_session = result.scalar_one_or_none()
        if market_session is not None:
            return market_session

        market_session = MarketSessionRecord(
            provider=provider,
            symbol=symbol,
            trading_date=trading_date,
            status="in_progress",
            completeness_ratio=0.0,
            snapshot_count=0,
            raw_snapshot_count=0,
            capture_metadata={"storage_version": 1},
        )
        session.add(market_session)
        await session.flush()
        return market_session

    async def _persist_raw_options_snapshot(
        self,
        *,
        session: AsyncSession,
        market_session: MarketSessionRecord,
        provider: str,
        symbol: str,
        captured_at: datetime,
        spot_price: float,
        options_df: pd.DataFrame,
    ) -> Optional[RawOptionsSnapshotRecord]:
        expiration_date = None
        if not options_df.empty and "expiration" in options_df.columns:
            expiration_series = pd.to_datetime(options_df["expiration"], errors="coerce")
            if expiration_series.notna().any():
                expiration_date = expiration_series.dropna().iloc[0].date()

        payload = self._serialize_options_payload(options_df)
        raw_record = RawOptionsSnapshotRecord(
            session_id=market_session.id,
            provider=provider,
            symbol=symbol,
            captured_at=captured_at,
            spot_price=spot_price,
            expiration_date=expiration_date,
            contract_count=len(payload),
            payload=payload,
            source_metadata={
                "storage_format": "normalized_options_chain",
                "columns": list(options_df.columns),
            },
        )
        session.add(raw_record)
        await session.flush()
        return raw_record

    async def _should_persist_raw_snapshot(
        self,
        *,
        session: AsyncSession,
        provider: str,
        symbol: str,
        captured_at: datetime,
    ) -> bool:
        result = await session.execute(
            select(RawOptionsSnapshotRecord)
            .where(
                RawOptionsSnapshotRecord.provider == provider,
                RawOptionsSnapshotRecord.symbol == symbol,
            )
            .order_by(RawOptionsSnapshotRecord.captured_at.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        if latest is None:
            return True
        latest_captured_at = self._normalize_timestamp(latest.captured_at)
        elapsed = (captured_at - latest_captured_at).total_seconds()
        return elapsed >= RAW_SNAPSHOT_INTERVAL_SECONDS

    async def _load_snapshot_records(
        self,
        *,
        provider: str,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> list[GEXSnapshotRecord]:
        provider_name = provider.strip().lower()
        underlying = symbol.strip().upper()
        start_dt = datetime.combine(start_date, time.min, tzinfo=ET)
        end_dt = datetime.combine(end_date, time.max, tzinfo=ET)

        try:
            async with self._get_session_factory()() as session:
                result = await session.execute(
                    select(GEXSnapshotRecord)
                    .options(selectinload(GEXSnapshotRecord.strike_points))
                    .where(
                        GEXSnapshotRecord.provider == provider_name,
                        GEXSnapshotRecord.symbol == underlying,
                        GEXSnapshotRecord.captured_at >= start_dt,
                        GEXSnapshotRecord.captured_at <= end_dt,
                    )
                    .order_by(GEXSnapshotRecord.captured_at.asc())
                )
                return result.scalars().all()
        except Exception as exc:
            logger.warning(
                "Historical snapshot lookup failed for %s/%s: %s",
                provider_name,
                underlying,
                exc,
            )
            return []

    async def _load_latest_replay_snapshot_records(
        self,
        *,
        provider: str,
        symbol: str,
    ) -> list[GEXSnapshotRecord]:
        provider_name = provider.strip().lower()
        underlying = symbol.strip().upper()
        await self.finalize_stale_sessions()

        try:
            async with self._get_session_factory()() as session:
                session_result = await session.execute(
                    select(MarketSessionRecord)
                    .where(
                        MarketSessionRecord.provider == provider_name,
                        MarketSessionRecord.symbol == underlying,
                    )
                    .order_by(
                        (MarketSessionRecord.status == "complete").desc(),
                        MarketSessionRecord.trading_date.desc(),
                        MarketSessionRecord.last_captured_at.desc(),
                    )
                    .limit(1)
                )
                latest_session = session_result.scalar_one_or_none()
                if latest_session is None:
                    return []

                records_result = await session.execute(
                    select(GEXSnapshotRecord)
                    .options(selectinload(GEXSnapshotRecord.strike_points))
                    .where(GEXSnapshotRecord.session_id == latest_session.id)
                    .order_by(GEXSnapshotRecord.captured_at.asc())
                )
                return records_result.scalars().all()
        except Exception as exc:
            logger.warning("Replay lookup failed for %s/%s: %s", provider_name, underlying, exc)
            return []

    async def _get_latest_raw_snapshot(
        self,
        *,
        session: AsyncSession,
        provider: str,
        symbol: str,
        prefer_replay: bool,
    ) -> Optional[RawOptionsSnapshotRecord]:
        if not prefer_replay:
            result = await session.execute(
                select(RawOptionsSnapshotRecord)
                .where(
                    RawOptionsSnapshotRecord.provider == provider,
                    RawOptionsSnapshotRecord.symbol == symbol,
                )
                .order_by(RawOptionsSnapshotRecord.captured_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

        await self.finalize_stale_sessions()
        session_result = await session.execute(
            select(MarketSessionRecord)
            .where(
                MarketSessionRecord.provider == provider,
                MarketSessionRecord.symbol == symbol,
            )
            .order_by(
                (MarketSessionRecord.status == "complete").desc(),
                MarketSessionRecord.trading_date.desc(),
                MarketSessionRecord.last_captured_at.desc(),
            )
            .limit(1)
        )
        latest_session = session_result.scalar_one_or_none()
        if latest_session is None:
            return None

        raw_result = await session.execute(
            select(RawOptionsSnapshotRecord)
            .where(RawOptionsSnapshotRecord.session_id == latest_session.id)
            .order_by(RawOptionsSnapshotRecord.captured_at.desc())
            .limit(1)
        )
        return raw_result.scalar_one_or_none()

    async def _apply_retention(self, session: AsyncSession, *, reference_date: date) -> None:
        cutoff = reference_date - timedelta(days=RETENTION_DAYS)
        stale_session_ids = (
            await session.execute(
                select(MarketSessionRecord.id).where(MarketSessionRecord.trading_date < cutoff)
            )
        ).scalars().all()

        if not stale_session_ids:
            return

        await session.execute(
            delete(MarketSessionRecord).where(MarketSessionRecord.id.in_(stale_session_ids))
        )

    @staticmethod
    def _normalize_snapshot(snapshot: GEXSnapshot | dict[str, Any]) -> dict[str, Any]:
        if hasattr(snapshot, "model_dump"):
            return snapshot.model_dump()
        return dict(snapshot)

    @staticmethod
    def _normalize_options_df(options_df: Optional[pd.DataFrame]) -> pd.DataFrame:
        if options_df is None:
            return pd.DataFrame()
        return options_df.copy()

    @staticmethod
    def _normalize_timestamp(timestamp: Any) -> datetime:
        if isinstance(timestamp, str):
            normalized = datetime.fromisoformat(timestamp)
        elif isinstance(timestamp, pd.Timestamp):
            normalized = timestamp.to_pydatetime()
        elif isinstance(timestamp, datetime):
            normalized = timestamp
        else:
            normalized = datetime.now(ET)

        if normalized.tzinfo is None:
            return normalized.replace(tzinfo=ET)
        return normalized.astimezone(ET)

    @staticmethod
    def _calculate_completeness_ratio(
        *,
        trading_date: date,
        first_captured_at: Optional[datetime],
        last_captured_at: Optional[datetime],
    ) -> float:
        if first_captured_at is None or last_captured_at is None:
            return 0.0

        session_open = datetime.combine(trading_date, SESSION_OPEN, tzinfo=ET)
        session_close = datetime.combine(trading_date, SESSION_CLOSE, tzinfo=ET)
        normalized_first = HistoricalDataService._normalize_timestamp(first_captured_at)
        normalized_last = HistoricalDataService._normalize_timestamp(last_captured_at)
        active_start = max(normalized_first, session_open)
        active_end = min(normalized_last, session_close)
        if active_end <= active_start:
            return 0.0

        captured_span = (active_end - active_start).total_seconds()
        session_span = (session_close - session_open).total_seconds()
        return max(0.0, min(1.0, captured_span / session_span))

    @staticmethod
    def _determine_session_status(
        *,
        trading_date: date,
        last_captured_at: Optional[datetime],
    ) -> str:
        if last_captured_at is None:
            return "in_progress"

        last_time = HistoricalDataService._normalize_timestamp(last_captured_at)
        if last_time.date() > trading_date or last_time.time() >= REPLAY_COMPLETE_AFTER:
            return "complete"
        return "in_progress"

    @staticmethod
    def _serialize_options_payload(options_df: pd.DataFrame) -> list[dict[str, Any]]:
        if options_df.empty:
            return []

        serializable = options_df.copy()
        for column in serializable.columns:
            if pd.api.types.is_datetime64_any_dtype(serializable[column]):
                serializable[column] = serializable[column].astype(str)
            elif serializable[column].dtype == object:
                serializable[column] = serializable[column].map(
                    lambda value: value.isoformat()
                    if hasattr(value, "isoformat")
                    else value
                )

        return serializable.fillna(value=pd.NA).replace({pd.NA: None}).to_dict(orient="records")

    @staticmethod
    def _build_iv_surface_points(
        *,
        raw_snapshot_id: int,
        provider: str,
        symbol: str,
        captured_at: datetime,
        spot_price: float,
        options_df: pd.DataFrame,
    ) -> list[IVSurfacePointRecord]:
        if options_df.empty or "strike" not in options_df.columns:
            return []

        rows: list[IVSurfacePointRecord] = []
        for _, option_row in options_df.iterrows():
            option_type = str(option_row.get("type", "")).lower()
            if option_type not in {"call", "put"}:
                continue

            strike = float(option_row.get("strike", 0.0) or 0.0)
            mid_price = float(option_row.get("mid", 0.0) or 0.0)
            implied_vol = option_row.get("implied_vol")
            if implied_vol is None or pd.isna(implied_vol):
                continue

            rows.append(
                IVSurfacePointRecord(
                    raw_snapshot_id=raw_snapshot_id,
                    provider=provider,
                    symbol=symbol,
                    captured_at=captured_at,
                    strike=strike,
                    option_type=option_type,
                    iv=float(implied_vol),
                    mid_price=mid_price,
                    moneyness=float((strike - spot_price) / max(spot_price, 1.0)),
                )
            )
        return rows

    @staticmethod
    def _build_skew_points(iv_rows: Iterable[IVSurfacePointRecord]) -> list[dict[str, float]]:
        grouped: dict[float, dict[str, float]] = {}
        for row in iv_rows:
            bucket = grouped.setdefault(row.strike, {"moneyness": row.moneyness})
            bucket[f"{row.option_type}_iv"] = row.iv

        skew_points: list[dict[str, float]] = []
        for strike, values in sorted(grouped.items()):
            call_iv = float(values.get("call_iv", 0.0))
            put_iv = float(values.get("put_iv", 0.0))
            if call_iv == 0.0 and put_iv == 0.0:
                continue
            skew_points.append(
                {
                    "strike": float(strike),
                    "call_iv": call_iv,
                    "put_iv": put_iv,
                    "skew": float(put_iv - call_iv),
                    "moneyness": float(values.get("moneyness", 0.0)),
                }
            )
        return skew_points

    @classmethod
    def _records_to_snapshots(
        cls,
        records: list[GEXSnapshotRecord],
        *,
        interval: str,
    ) -> list[GEXSnapshot]:
        if not records:
            return []

        rule = cls._get_resample_rule(interval)
        if rule is None:
            return [cls._record_to_snapshot(record) for record in records]

        frame = pd.DataFrame(
            [
                {
                    "captured_at": record.captured_at,
                    "snapshot_id": record.id,
                    "spot_price": record.spot_price,
                    "total_call_gex": record.total_call_gex,
                    "total_put_gex": record.total_put_gex,
                    "net_gex": record.net_gex,
                    "zero_gamma_level": record.zero_gamma_level,
                    "dominant_strike": record.dominant_strike,
                }
                for record in records
            ]
        )
        frame["captured_at"] = pd.to_datetime(frame["captured_at"], utc=True).dt.tz_convert(ET)
        frame = frame.set_index("captured_at").sort_index()
        aggregated = (
            frame.resample(rule)
            .agg(
                {
                    "snapshot_id": "last",
                    "spot_price": "last",
                    "total_call_gex": "last",
                    "total_put_gex": "last",
                    "net_gex": "last",
                    "zero_gamma_level": "last",
                    "dominant_strike": "last",
                }
            )
            .dropna(subset=["snapshot_id"])
        )

        record_by_id = {record.id: record for record in records}
        snapshots: list[GEXSnapshot] = []
        for timestamp, row in aggregated.iterrows():
            source_record = record_by_id[int(row["snapshot_id"])]
            snapshots.append(
                GEXSnapshot(
                    timestamp=timestamp.to_pydatetime(),
                    spot_price=float(row["spot_price"]),
                    total_call_gex=float(row["total_call_gex"]),
                    total_put_gex=float(row["total_put_gex"]),
                    net_gex=float(row["net_gex"]),
                    zero_gamma_level=float(row["zero_gamma_level"]),
                    gex_by_strike={
                        float(point.strike): float(point.gex_value)
                        for point in source_record.strike_points
                    },
                    dominant_strike=float(row["dominant_strike"]),
                    metrics=dict(source_record.metrics or {}),
                )
            )
        return snapshots

    @staticmethod
    def _record_to_snapshot(record: GEXSnapshotRecord) -> GEXSnapshot:
        return GEXSnapshot(
            timestamp=record.captured_at,
            spot_price=record.spot_price,
            total_call_gex=record.total_call_gex,
            total_put_gex=record.total_put_gex,
            net_gex=record.net_gex,
            zero_gamma_level=record.zero_gamma_level,
            gex_by_strike={
                float(point.strike): float(point.gex_value)
                for point in record.strike_points
            },
            dominant_strike=record.dominant_strike,
            metrics=dict(record.metrics or {}),
        )

    @staticmethod
    def _get_resample_rule(interval: str) -> Optional[str]:
        return INTERVAL_RULES.get(interval, INTERVAL_RULES["1m"])

    @staticmethod
    def _days_for_period(period: str) -> int:
        normalized = period.strip().lower()
        if normalized.isdigit():
            return max(1, int(normalized))
        return PERIOD_TO_DAYS.get(normalized, 30)
