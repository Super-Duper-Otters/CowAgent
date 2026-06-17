# encoding:utf-8
"""Add business record actor fields.

Revision ID: 20260602_0011
Revises: 20260602_0010
Create Date: 2026-06-02
"""

from alembic import op
import sqlalchemy as sa

revision = "20260602_0011"
down_revision = "20260602_0010"
branch_labels = None
depends_on = None


USER_COLUMNS = (
    ("created_by_admin_id", sa.Integer()),
    ("created_by_username", sa.Text()),
    ("updated_by_admin_id", sa.Integer()),
    ("updated_by_username", sa.Text()),
    ("deleted_at", sa.Text()),
    ("deleted_by_admin_id", sa.Integer()),
    ("deleted_by_username", sa.Text()),
    ("delete_reason", sa.Text()),
)

CONTENT_COLUMNS = (
    ("created_by_admin_id", sa.Integer()),
    ("created_by_username", sa.Text()),
    ("created_by_role", sa.Text()),
    ("updated_by_admin_id", sa.Integer()),
    ("updated_by_username", sa.Text()),
    ("updated_by_role", sa.Text()),
    ("published_by_admin_id", sa.Integer()),
    ("published_by_username", sa.Text()),
    ("published_by_role", sa.Text()),
)

AUDIT_COLUMNS = (
    ("operator_admin_id", sa.Integer()),
    ("operator_username", sa.Text()),
    ("operator_role", sa.Text()),
    ("operation_category", sa.Text()),
    ("request_ip", sa.Text()),
    ("user_agent", sa.Text()),
)

CONFIG_COLUMNS = (
    ("updated_by_admin_id", sa.Integer()),
    ("updated_by_username", sa.Text()),
    ("updated_by_role", sa.Text()),
)


def _add_columns(table_name: str, columns: tuple[tuple[str, object], ...]) -> None:
    for name, column_type in columns:
        op.add_column(table_name, sa.Column(name, column_type, nullable=True))


def _drop_columns(table_name: str, columns: tuple[tuple[str, object], ...]) -> None:
    for name, _column_type in reversed(columns):
        op.drop_column(table_name, name)


def upgrade() -> None:
    _add_columns("investment_users", USER_COLUMNS)
    _add_columns("investment_daily_contents", CONTENT_COLUMNS)
    _add_columns("investment_operation_audits", AUDIT_COLUMNS)
    _add_columns("investment_configs", CONFIG_COLUMNS)
    op.add_column("investment_output_files", sa.Column("owner_type", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE investment_operation_audits
        SET operator_username = operator,
            operation_category = CASE
                WHEN target_type = 'customer' OR action LIKE 'customer.%' THEN 'customer'
                WHEN target_type = 'daily_content' OR action LIKE 'content.%' THEN 'content'
                ELSE 'backoffice'
            END
        WHERE operator_username IS NULL
        """
    )
    op.execute("UPDATE investment_configs SET updated_by_username = updated_by WHERE updated_by_username IS NULL")
    op.execute("UPDATE investment_output_files SET owner_type = 'request' WHERE owner_type IS NULL")


def downgrade() -> None:
    op.drop_column("investment_output_files", "owner_type")
    _drop_columns("investment_configs", CONFIG_COLUMNS)
    _drop_columns("investment_operation_audits", AUDIT_COLUMNS)
    _drop_columns("investment_daily_contents", CONTENT_COLUMNS)
    _drop_columns("investment_users", USER_COLUMNS)
