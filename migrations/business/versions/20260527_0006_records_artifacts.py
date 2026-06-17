# encoding:utf-8
"""Records and artifact audit metadata.

Revision ID: 20260527_0006
Revises: 20260527_0005
Create Date: 2026-05-27
"""

from alembic import op
import sqlalchemy as sa

revision = "20260527_0006"
down_revision = "20260527_0005"
branch_labels = None
depends_on = None


REQUEST_COLUMNS = (
    "normalized_target",
    "stock_code",
    "stock_name",
    "customer_name",
    "institution",
    "market_date",
    "cache_key",
    "program_version",
    "ta_version",
    "renderer_version",
    "template_version",
)


def upgrade() -> None:
    for column_name in REQUEST_COLUMNS:
        op.add_column("investment_request_records", sa.Column(column_name, sa.Text(), nullable=True))
    op.add_column("investment_request_records", sa.Column("cache_hit", sa.Integer(), nullable=True))

    op.add_column("investment_output_files", sa.Column("artifact_role", sa.Text(), nullable=True))
    op.add_column("investment_output_files", sa.Column("file_size", sa.Integer(), nullable=True))
    op.add_column("investment_output_files", sa.Column("file_hash", sa.Text(), nullable=True))
    op.add_column("investment_output_files", sa.Column("version_tag", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("investment_output_files", "version_tag")
    op.drop_column("investment_output_files", "file_hash")
    op.drop_column("investment_output_files", "file_size")
    op.drop_column("investment_output_files", "artifact_role")

    op.drop_column("investment_request_records", "cache_hit")
    for column_name in reversed(REQUEST_COLUMNS):
        op.drop_column("investment_request_records", column_name)
