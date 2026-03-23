"""ORM models for historical market persistence."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

JSONType = JSON().with_variant(JSONB(astext_type=Text()), "postgresql")


class MarketSessionRecord(Base):
    """One provider-symbol trading session used for replay selection."""

    __tablename__ = "market_sessions"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "symbol",
            "trading_date",
            name="uq_market_sessions_provider_symbol_trading_date",
        ),
        Index(
            "ix_market_sessions_trading_date_provider_symbol",
            "trading_date",
            "provider",
            "symbol",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="in_progress", nullable=False)
    completeness_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    snapshot_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    raw_snapshot_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    capture_metadata: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)

    gex_snapshots: Mapped[list["GEXSnapshotRecord"]] = relationship(
        back_populates="market_session",
        cascade="all, delete-orphan",
    )
    raw_options_snapshots: Mapped[list["RawOptionsSnapshotRecord"]] = relationship(
        back_populates="market_session",
        cascade="all, delete-orphan",
    )


class GEXSnapshotRecord(Base):
    """Derived 5-second GEX snapshot used by dashboard and analytics."""

    __tablename__ = "gex_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "symbol",
            "captured_at",
            name="uq_gex_snapshots_provider_symbol_captured_at",
        ),
        Index(
            "ix_gex_snapshots_provider_symbol_captured_at",
            "provider",
            "symbol",
            "captured_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("market_sessions.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    spot_price: Mapped[float] = mapped_column(Float, nullable=False)
    total_call_gex: Mapped[float] = mapped_column(Float, nullable=False)
    total_put_gex: Mapped[float] = mapped_column(Float, nullable=False)
    net_gex: Mapped[float] = mapped_column(Float, nullable=False)
    zero_gamma_level: Mapped[float] = mapped_column(Float, nullable=False)
    dominant_strike: Mapped[float] = mapped_column(Float, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)

    market_session: Mapped[MarketSessionRecord] = relationship(back_populates="gex_snapshots")
    strike_points: Mapped[list["GEXByStrikePointRecord"]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
        order_by="GEXByStrikePointRecord.strike",
    )


class GEXByStrikePointRecord(Base):
    """Per-strike breakdown for one captured GEX snapshot."""

    __tablename__ = "gex_by_strike_points"
    __table_args__ = (
        Index("ix_gex_by_strike_points_snapshot_id_strike", "snapshot_id", "strike"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("gex_snapshots.id", ondelete="CASCADE"), nullable=False)
    strike: Mapped[float] = mapped_column(Float, nullable=False)
    gex_value: Mapped[float] = mapped_column(Float, nullable=False)

    snapshot: Mapped[GEXSnapshotRecord] = relationship(back_populates="strike_points")


class RawOptionsSnapshotRecord(Base):
    """Provider-specific raw or normalized sidecar snapshot stored each minute."""

    __tablename__ = "raw_options_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "symbol",
            "captured_at",
            name="uq_raw_options_snapshots_provider_symbol_captured_at",
        ),
        Index(
            "ix_raw_options_snapshots_provider_symbol_captured_at",
            "provider",
            "symbol",
            "captured_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("market_sessions.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    spot_price: Mapped[float] = mapped_column(Float, nullable=False)
    expiration_date: Mapped[Optional[date]] = mapped_column(Date)
    contract_count: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)

    market_session: Mapped[MarketSessionRecord] = relationship(back_populates="raw_options_snapshots")
    iv_surface_points: Mapped[list["IVSurfacePointRecord"]] = relationship(
        back_populates="raw_snapshot",
        cascade="all, delete-orphan",
        order_by="IVSurfacePointRecord.strike",
    )


class IVSurfacePointRecord(Base):
    """Normalized IV surface points derived from raw option snapshots."""

    __tablename__ = "iv_surface_points"
    __table_args__ = (
        Index(
            "ix_iv_surface_points_provider_symbol_captured_at",
            "provider",
            "symbol",
            "captured_at",
        ),
        Index("ix_iv_surface_points_raw_snapshot_id_strike", "raw_snapshot_id", "strike"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("raw_options_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    strike: Mapped[float] = mapped_column(Float, nullable=False)
    option_type: Mapped[str] = mapped_column(String(8), nullable=False)
    iv: Mapped[float] = mapped_column(Float, nullable=False)
    mid_price: Mapped[float] = mapped_column(Float, nullable=False)
    moneyness: Mapped[float] = mapped_column(Float, nullable=False)

    raw_snapshot: Mapped[RawOptionsSnapshotRecord] = relationship(back_populates="iv_surface_points")
