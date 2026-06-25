# encoding:utf-8
"""backfill legacy generated outputs into products"""

from alembic import op


revision = "20260624_0027"
down_revision = "20260624_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from business.products.product_service import backfill_products_from_legacy_sources

    bind = op.get_bind()
    backfill_products_from_legacy_sources(conn=bind)


def downgrade() -> None:
    pass
