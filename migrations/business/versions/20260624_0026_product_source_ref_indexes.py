# encoding:utf-8
"""Index product source references.

Revision ID: 20260624_0026
Revises: 20260624_0025
Create Date: 2026-06-24
"""

from alembic import op

revision = "20260624_0026"
down_revision = "20260624_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("idx_products_source_cache_key", "products", ["source_cache_key"])
    op.create_index("idx_products_source_content_id", "products", ["source_content_id"])


def downgrade() -> None:
    op.drop_index("idx_products_source_content_id", table_name="products")
    op.drop_index("idx_products_source_cache_key", table_name="products")
