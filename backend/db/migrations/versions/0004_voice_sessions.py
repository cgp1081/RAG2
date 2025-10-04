"""Create voice call session tables.

Revision ID: 0004_voice_sessions
Revises: 0003_structured_tables
Create Date: 2025-10-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_voice_sessions"
down_revision = "0003_structured_tables"
branch_labels = None
depends_on = None

_UUID_DEFAULT = sa.text("gen_random_uuid()")
_STATUS_ENUM = sa.Enum(
    "initiated",
    "running",
    "completed",
    "failed",
    name="call_session_status",
)
_SPEAKER_ENUM = sa.Enum("caller", "assistant", name="call_turn_speaker")


def upgrade() -> None:
    _STATUS_ENUM.create(op.get_bind(), checkfirst=True)
    _SPEAKER_ENUM.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "call_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=_UUID_DEFAULT,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("twilio_call_sid", sa.String(length=64), nullable=False, unique=True),
        sa.Column("status", _STATUS_ENUM, nullable=False, server_default="initiated"),
        sa.Column("caller_number", sa.String(length=32), nullable=True),
        sa.Column("callee_number", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_call_sessions_tenant_sid",
        "call_sessions",
        ["tenant_id", "twilio_call_sid"],
        unique=True,
    )

    op.create_table(
        "call_turns",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=_UUID_DEFAULT,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("call_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("speaker", _SPEAKER_ENUM, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ended_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_call_turns_session_sequence",
        "call_turns",
        ["session_id", "sequence"],
        unique=True,
    )

    op.create_table(
        "call_recordings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=_UUID_DEFAULT,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("call_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("media_uri", sa.Text(), nullable=True),
        sa.Column("content_type", sa.String(length=64), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )



def downgrade() -> None:
    op.drop_table("call_recordings")
    op.drop_index("ix_call_turns_session_sequence", table_name="call_turns")
    op.drop_table("call_turns")
    op.drop_index("ix_call_sessions_tenant_sid", table_name="call_sessions")
    op.drop_table("call_sessions")
    _SPEAKER_ENUM.drop(op.get_bind(), checkfirst=True)
    _STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
