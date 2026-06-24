# encoding:utf-8
"""Unified business products.

Revision ID: 20260624_0025
Revises: 20260616_0024
Create Date: 2026-06-24
"""

from alembic import op
import sqlalchemy as sa

revision = "20260624_0025"
down_revision = "20260616_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("product_id", sa.Text(), primary_key=True),
        sa.Column("business_type", sa.Text(), nullable=False),
        sa.Column("target_key", sa.Text(), nullable=False),
        sa.Column("target_label", sa.Text(), nullable=True),
        sa.Column("business_date", sa.Text(), nullable=True),
        sa.Column("logical_key", sa.Text(), nullable=False),
        sa.Column("version_fingerprint", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("source_request_id", sa.Text(), nullable=True),
        sa.Column("source_content_id", sa.Text(), nullable=True),
        sa.Column("source_cache_key", sa.Text(), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=True),
        sa.Column("source_files", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("output_files", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.Text(), nullable=True),
        sa.Column("effective_at", sa.Text(), nullable=True),
        sa.Column("invalidated_at", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "idx_products_lookup",
        "products",
        ["business_type", "target_key", "business_date", "version_fingerprint", "status"],
    )
    op.create_index(
        "idx_products_logical_status",
        "products",
        ["logical_key", "status"],
    )
    op.create_index(
        "idx_products_business_date",
        "products",
        ["business_type", "business_date", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_products_business_date", table_name="products")
    op.drop_index("idx_products_logical_status", table_name="products")
    op.drop_index("idx_products_lookup", table_name="products")
    op.drop_table("products")
