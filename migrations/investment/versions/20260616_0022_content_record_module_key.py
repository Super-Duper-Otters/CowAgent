# encoding:utf-8
"""add daily content module key

Revision ID: 20260616_0022
Revises: 20260612_0021
Create Date: 2026-06-16
"""

from alembic import op
import sqlalchemy as sa


revision = "20260616_0022"
down_revision = "20260612_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_records", sa.Column("module_key", sa.Text(), nullable=True))
    op.create_index(
        "idx_content_records_module_effective_status",
        "content_records",
        ["module_key", "effective_date", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_content_records_module_effective_status", table_name="content_records")
    op.drop_column("content_records", "module_key")
