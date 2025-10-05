"""Add call analytics fields and metrics table.

Revision ID: 0005_call_analytics
Revises: 0004_voice_sessions
Create Date: 2025-10-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_call_analytics"
down_revision = "0004_voice_sessions"
branch_labels = None
depends_on = None

_UUID_DEFAULT = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.add_column(
        "call_sessions",
        sa.Column("escalated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "call_sessions",
        sa.Column("summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "call_sessions",
        sa.Column("recording_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "call_sessions",
        sa.Column("storage_object_key", sa.Text(), nullable=True),
    )
    op.add_column(
        "call_sessions",
        sa.Column("caller_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "call_sessions",
        sa.Column("avg_turn_latency_ms", sa.Numeric(precision=10, scale=2), nullable=True),
    )
    op.create_index(
        "ix_call_sessions_tenant_escalated",
        "call_sessions",
        ["tenant_id", "escalated"],
    )

    op.create_table(
        "call_metrics_daily",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=_UUID_DEFAULT),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("total_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("escalations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_confidence", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("avg_handle_seconds", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("tenant_id", "date", name="uq_call_metrics_daily_tenant_date"),
    )


def downgrade() -> None:
    op.drop_table("call_metrics_daily")
    op.drop_index("ix_call_sessions_tenant_escalated", table_name="call_sessions")
    op.drop_column("call_sessions", "avg_turn_latency_ms")
    op.drop_column("call_sessions", "caller_metadata")
    op.drop_column("call_sessions", "storage_object_key")
    op.drop_column("call_sessions", "recording_url")
    op.drop_column("call_sessions", "summary")
    op.drop_column("call_sessions", "escalated")
