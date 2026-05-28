# encoding:utf-8
"""Daily content versioning and operation audits.

Revision ID: 20260527_0005
Revises: 20260525_0001
Create Date: 2026-05-27
"""

from alembic import op
import sqlalchemy as sa

revision = "20260527_0005"
down_revision = "20260525_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("investment_daily_contents", sa.Column("effective_date", sa.Text(), nullable=True))
    op.add_column(
        "investment_daily_contents",
        sa.Column("content_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "investment_daily_contents",
        sa.Column("direct_output_mode", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("investment_daily_contents", sa.Column("archived_at", sa.Text(), nullable=True))
    op.execute(
        "update investment_daily_contents "
        "set effective_date = substring(coalesce(effective_at, created_at) from 1 for 10) "
        "where effective_date is null"
    )
    op.create_index(
        "idx_investment_daily_contents_effective_date",
        "investment_daily_contents",
        ["service_type", "effective_date", "status"],
        unique=False,
    )

    op.create_table(
        "investment_operation_audits",
        sa.Column("audit_id", sa.Text(), nullable=False),
        sa.Column("operator", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("audit_id"),
    )
    op.create_index(
        "idx_investment_operation_audits_created",
        "investment_operation_audits",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "idx_investment_operation_audits_target",
        "investment_operation_audits",
        ["target_type", "target_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_investment_operation_audits_target", table_name="investment_operation_audits")
    op.drop_index("idx_investment_operation_audits_created", table_name="investment_operation_audits")
    op.drop_table("investment_operation_audits")

    op.drop_index("idx_investment_daily_contents_effective_date", table_name="investment_daily_contents")
    op.drop_column("investment_daily_contents", "archived_at")
    op.drop_column("investment_daily_contents", "direct_output_mode")
    op.drop_column("investment_daily_contents", "content_version")
    op.drop_column("investment_daily_contents", "effective_date")
