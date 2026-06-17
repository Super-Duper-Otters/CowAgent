# encoding:utf-8
"""Initial investment schema.

Revision ID: 20260525_0001
Revises:
Create Date: 2026-05-25
"""

from alembic import op
import sqlalchemy as sa

revision = "20260525_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investment_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("openid", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("institution", sa.Text(), nullable=True),
        sa.Column("mobile", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Integer(), server_default="1", nullable=False),
        sa.Column("allowed_services", sa.Text(), nullable=False),
        sa.Column("auth_start_at", sa.Text(), nullable=True),
        sa.Column("auth_end_at", sa.Text(), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_investment_users_openid", "investment_users", ["openid"], unique=True)

    op.create_table(
        "investment_request_records",
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("openid", sa.Text(), nullable=False),
        sa.Column("raw_input", sa.Text(), nullable=False),
        sa.Column("service_type", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("user_prompt", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("output_files", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("request_id"),
    )
    op.create_index(
        "idx_investment_request_records_created",
        "investment_request_records",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "idx_investment_request_records_service_status",
        "investment_request_records",
        ["service_type", "status"],
        unique=False,
    )

    op.create_table(
        "investment_daily_contents",
        sa.Column("content_id", sa.Text(), nullable=False),
        sa.Column("service_type", sa.Text(), nullable=False),
        sa.Column("source_files", sa.Text(), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("generated_text", sa.Text(), nullable=True),
        sa.Column("output_image", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("operator", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("effective_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("content_id"),
    )
    op.create_index(
        "idx_investment_daily_contents_service_status",
        "investment_daily_contents",
        ["service_type", "status"],
        unique=False,
    )
    op.create_index(
        "idx_investment_daily_contents_effective",
        "investment_daily_contents",
        ["service_type", "effective_at"],
        unique=False,
    )

    op.create_table(
        "investment_output_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.Text(), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_type", sa.Text(), nullable=True),
        sa.Column("service_type", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_investment_output_files_owner", "investment_output_files", ["owner_id"], unique=False)

    op.create_table(
        "investment_configs",
        sa.Column("config_key", sa.Text(), nullable=False),
        sa.Column("config_value", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("config_key"),
    )

    op.create_table(
        "investment_stock_symbols",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("market", sa.Text(), nullable=False),
        sa.Column("ts_code", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_index("idx_investment_stock_symbols_name", "investment_stock_symbols", ["name"], unique=False)
    op.create_index("idx_investment_stock_symbols_updated", "investment_stock_symbols", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_investment_stock_symbols_updated", table_name="investment_stock_symbols")
    op.drop_index("idx_investment_stock_symbols_name", table_name="investment_stock_symbols")
    op.drop_table("investment_stock_symbols")

    op.drop_table("investment_configs")

    op.drop_index("idx_investment_output_files_owner", table_name="investment_output_files")
    op.drop_table("investment_output_files")

    op.drop_index("idx_investment_daily_contents_effective", table_name="investment_daily_contents")
    op.drop_index("idx_investment_daily_contents_service_status", table_name="investment_daily_contents")
    op.drop_table("investment_daily_contents")

    op.drop_index("idx_investment_request_records_service_status", table_name="investment_request_records")
    op.drop_index("idx_investment_request_records_created", table_name="investment_request_records")
    op.drop_table("investment_request_records")

    op.drop_index("idx_investment_users_openid", table_name="investment_users")
    op.drop_table("investment_users")
