# encoding:utf-8
"""add agent conversation message tables

Revision ID: 20260612_0021
Revises: 20260612_0020
Create Date: 2026-06-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20260612_0021"
down_revision = "20260612_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("session_id", sa.Text(), primary_key=True),
        sa.Column("channel_type", sa.Text(), nullable=False, server_default=""),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("context_start_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("last_active", sa.Integer(), nullable=False),
        sa.Column("msg_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("idx_agent_sessions_last_active", "agent_sessions", ["last_active"])
    op.create_index("idx_agent_sessions_channel", "agent_sessions", ["channel_type"])

    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
    )
    op.create_index("idx_agent_messages_session", "agent_messages", ["session_id", "seq"])
    op.create_index("idx_agent_messages_session_seq_unique", "agent_messages", ["session_id", "seq"], unique=True)


def downgrade() -> None:
    op.drop_index("idx_agent_messages_session_seq_unique", table_name="agent_messages")
    op.drop_index("idx_agent_messages_session", table_name="agent_messages")
    op.drop_table("agent_messages")
    op.drop_index("idx_agent_sessions_channel", table_name="agent_sessions")
    op.drop_index("idx_agent_sessions_last_active", table_name="agent_sessions")
    op.drop_table("agent_sessions")
