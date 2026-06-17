# encoding:utf-8
"""Investment admin users and sessions.

Revision ID: 20260527_0008
Revises: 20260527_0007
Create Date: 2026-05-27
"""

from alembic import op
import sqlalchemy as sa

revision = "20260527_0008"
down_revision = "20260527_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investment_admin_users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("last_login_at", sa.Text(), nullable=True),
    )
    op.create_index("idx_investment_admin_users_username", "investment_admin_users", ["username"], unique=True)

    op.create_table(
        "investment_admin_sessions",
        sa.Column("session_id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_investment_admin_sessions_token", "investment_admin_sessions", ["token_hash"], unique=True)
    op.create_index("idx_investment_admin_sessions_user", "investment_admin_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_investment_admin_sessions_user", table_name="investment_admin_sessions")
    op.drop_index("idx_investment_admin_sessions_token", table_name="investment_admin_sessions")
    op.drop_table("investment_admin_sessions")
    op.drop_index("idx_investment_admin_users_username", table_name="investment_admin_users")
    op.drop_table("investment_admin_users")
