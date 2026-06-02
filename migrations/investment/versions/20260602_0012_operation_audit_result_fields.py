# encoding:utf-8
"""Add operation audit result fields.

Revision ID: 20260602_0012
Revises: 20260602_0011
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa

revision = "20260602_0012"
down_revision = "20260602_0011"
branch_labels = None
depends_on = None


COLUMNS = (
    ("result_status", sa.Text()),
    ("error_code", sa.Text()),
    ("error_message", sa.Text()),
    ("elapsed_ms", sa.Integer()),
    ("before_state", sa.Text()),
    ("after_state", sa.Text()),
)


def upgrade() -> None:
    for name, column_type in COLUMNS:
        op.add_column("investment_operation_audits", sa.Column(name, column_type, nullable=True))
    op.execute("UPDATE investment_operation_audits SET result_status = 'success' WHERE result_status IS NULL")


def downgrade() -> None:
    for name, _column_type in reversed(COLUMNS):
        op.drop_column("investment_operation_audits", name)
