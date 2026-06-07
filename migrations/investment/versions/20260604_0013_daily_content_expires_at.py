# encoding:utf-8
"""Add daily content expiration time.

Revision ID: 20260604_0013
Revises: 20260602_0012
Create Date: 2026-06-04
"""

from alembic import op
import sqlalchemy as sa

revision = "20260604_0013"
down_revision = "20260602_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("investment_daily_contents", sa.Column("expires_at", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("investment_daily_contents", "expires_at")
