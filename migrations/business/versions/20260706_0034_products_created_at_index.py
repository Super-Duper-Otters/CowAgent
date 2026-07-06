# encoding:utf-8
"""Add product generated-time lookup index."""

from alembic import op


revision = "20260706_0034"
down_revision = "20260630_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_products_business_type_created_status",
        "products",
        ["business_type", "created_at", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_products_business_type_created_status", table_name="products")
