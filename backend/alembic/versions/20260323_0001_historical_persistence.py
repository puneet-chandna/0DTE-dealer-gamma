"""Create historical persistence and replay tables."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260323_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="in_progress"),
        sa.Column("completeness_ratio", sa.Float(), nullable=False, server_default="0"),
        sa.Column("snapshot_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_snapshot_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("capture_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint(
            "provider",
            "symbol",
            "trading_date",
            name="uq_market_sessions_provider_symbol_trading_date",
        ),
    )
    op.create_index(
        "ix_market_sessions_trading_date_provider_symbol",
        "market_sessions",
        ["trading_date", "provider", "symbol"],
        unique=False,
    )

    op.create_table(
        "gex_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("market_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("spot_price", sa.Float(), nullable=False),
        sa.Column("total_call_gex", sa.Float(), nullable=False),
        sa.Column("total_put_gex", sa.Float(), nullable=False),
        sa.Column("net_gex", sa.Float(), nullable=False),
        sa.Column("zero_gamma_level", sa.Float(), nullable=False),
        sa.Column("dominant_strike", sa.Float(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint(
            "provider",
            "symbol",
            "captured_at",
            name="uq_gex_snapshots_provider_symbol_captured_at",
        ),
    )
    op.create_index(
        "ix_gex_snapshots_provider_symbol_captured_at",
        "gex_snapshots",
        ["provider", "symbol", "captured_at"],
        unique=False,
    )

    op.create_table(
        "gex_by_strike_points",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("gex_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("strike", sa.Float(), nullable=False),
        sa.Column("gex_value", sa.Float(), nullable=False),
    )
    op.create_index(
        "ix_gex_by_strike_points_snapshot_id_strike",
        "gex_by_strike_points",
        ["snapshot_id", "strike"],
        unique=False,
    )

    op.create_table(
        "raw_options_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("market_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("spot_price", sa.Float(), nullable=False),
        sa.Column("expiration_date", sa.Date(), nullable=True),
        sa.Column("contract_count", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint(
            "provider",
            "symbol",
            "captured_at",
            name="uq_raw_options_snapshots_provider_symbol_captured_at",
        ),
    )
    op.create_index(
        "ix_raw_options_snapshots_provider_symbol_captured_at",
        "raw_options_snapshots",
        ["provider", "symbol", "captured_at"],
        unique=False,
    )

    op.create_table(
        "iv_surface_points",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("raw_snapshot_id", sa.Integer(), sa.ForeignKey("raw_options_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strike", sa.Float(), nullable=False),
        sa.Column("option_type", sa.String(length=8), nullable=False),
        sa.Column("iv", sa.Float(), nullable=False),
        sa.Column("mid_price", sa.Float(), nullable=False),
        sa.Column("moneyness", sa.Float(), nullable=False),
    )
    op.create_index(
        "ix_iv_surface_points_provider_symbol_captured_at",
        "iv_surface_points",
        ["provider", "symbol", "captured_at"],
        unique=False,
    )
    op.create_index(
        "ix_iv_surface_points_raw_snapshot_id_strike",
        "iv_surface_points",
        ["raw_snapshot_id", "strike"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_iv_surface_points_raw_snapshot_id_strike", table_name="iv_surface_points")
    op.drop_index("ix_iv_surface_points_provider_symbol_captured_at", table_name="iv_surface_points")
    op.drop_table("iv_surface_points")

    op.drop_index("ix_raw_options_snapshots_provider_symbol_captured_at", table_name="raw_options_snapshots")
    op.drop_table("raw_options_snapshots")

    op.drop_index("ix_gex_by_strike_points_snapshot_id_strike", table_name="gex_by_strike_points")
    op.drop_table("gex_by_strike_points")

    op.drop_index("ix_gex_snapshots_provider_symbol_captured_at", table_name="gex_snapshots")
    op.drop_table("gex_snapshots")

    op.drop_index("ix_market_sessions_trading_date_provider_symbol", table_name="market_sessions")
    op.drop_table("market_sessions")
