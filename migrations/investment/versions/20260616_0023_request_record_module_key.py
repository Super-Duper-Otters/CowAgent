# encoding:utf-8
"""add request record module key

Revision ID: 20260616_0023
Revises: 20260616_0022
Create Date: 2026-06-16
"""

from alembic import op
import sqlalchemy as sa


revision = "20260616_0023"
down_revision = "20260616_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("request_records", sa.Column("module_key", sa.Text(), nullable=True))
    op.create_index("idx_request_records_module_created", "request_records", ["module_key", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_request_records_module_created", table_name="request_records")
    op.drop_column("request_records", "module_key")
