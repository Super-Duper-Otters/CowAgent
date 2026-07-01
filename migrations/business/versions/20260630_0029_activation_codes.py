# encoding:utf-8
"""add activation codes"""

from alembic import op
import sqlalchemy as sa


revision = "20260630_0029"
down_revision = "20260625_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activation_codes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("batch_id", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("code_prefix", sa.Text(), nullable=False),
        sa.Column("allowed_services", sa.Text(), nullable=False),
        sa.Column("subscription_days", sa.Integer(), nullable=False),
        sa.Column("code_expires_at", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("used_by_openid", sa.Text()),
        sa.Column("used_at", sa.Text()),
        sa.Column("created_by_admin_id", sa.Integer()),
        sa.Column("created_by_username", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("remark", sa.Text()),
    )
    op.create_index("idx_activation_codes_hash", "activation_codes", ["code_hash"], unique=True)
    op.create_index("idx_activation_codes_batch", "activation_codes", ["batch_id"])
    op.create_index("idx_activation_codes_status", "activation_codes", ["status", "code_expires_at"])
    op.create_index("idx_activation_codes_used_by", "activation_codes", ["used_by_openid", "used_at"])


def downgrade() -> None:
    op.drop_index("idx_activation_codes_used_by", table_name="activation_codes")
    op.drop_index("idx_activation_codes_status", table_name="activation_codes")
    op.drop_index("idx_activation_codes_batch", table_name="activation_codes")
    op.drop_index("idx_activation_codes_hash", table_name="activation_codes")
    op.drop_table("activation_codes")
