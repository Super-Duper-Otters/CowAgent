# encoding:utf-8
"""Add daily content auto effective flag.

Revision ID: 20260605_0014
Revises: 20260604_0013
Create Date: 2026-06-05
"""

from alembic import op
import sqlalchemy as sa

revision = "20260605_0014"
down_revision = "20260604_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investment_daily_contents",
        sa.Column("auto_effective_after_generate", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("investment_daily_contents", "auto_effective_after_generate")
