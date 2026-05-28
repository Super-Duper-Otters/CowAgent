# encoding:utf-8
"""Technical analysis cache entries.

Revision ID: 20260527_0007
Revises: 20260527_0006
Create Date: 2026-05-27
"""

from alembic import op
import sqlalchemy as sa

revision = "20260527_0007"
down_revision = "20260527_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investment_cache_entries",
        sa.Column("cache_key", sa.Text(), primary_key=True),
        sa.Column("service_type", sa.Text(), nullable=False),
        sa.Column("normalized_target", sa.Text(), nullable=False),
        sa.Column("market_date", sa.Text(), nullable=False),
        sa.Column("version_fingerprint", sa.Text(), nullable=False),
        sa.Column("output_files", sa.Text(), nullable=False),
        sa.Column("artifact_owner_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "idx_investment_cache_lookup",
        "investment_cache_entries",
        ["service_type", "normalized_target", "market_date", "version_fingerprint", "status"],
    )
    op.create_index(
        "idx_investment_cache_service_date",
        "investment_cache_entries",
        ["service_type", "market_date", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_investment_cache_service_date", table_name="investment_cache_entries")
    op.drop_index("idx_investment_cache_lookup", table_name="investment_cache_entries")
    op.drop_table("investment_cache_entries")
