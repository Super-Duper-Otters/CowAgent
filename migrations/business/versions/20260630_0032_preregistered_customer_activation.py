# encoding:utf-8
"""add preregistered customer activation fields"""

from alembic import op
import sqlalchemy as sa


revision = "20260630_0032"
down_revision = "20260630_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("customers", "openid", existing_type=sa.Text(), nullable=True)
    op.execute("update customers set openid = null where openid = ''")
    op.add_column("customers", sa.Column("bind_status", sa.Text(), nullable=False, server_default="bound"))
    op.add_column("customers", sa.Column("bound_at", sa.Text()))
    op.add_column("customers", sa.Column("unbound_at", sa.Text()))
    op.add_column("customers", sa.Column("last_unbound_by_admin_id", sa.Integer()))
    op.add_column("customers", sa.Column("last_unbound_by_username", sa.Text()))
    op.add_column("customers", sa.Column("last_unbound_reason", sa.Text()))

    op.add_column("activation_codes", sa.Column("activation_mode", sa.Text(), nullable=False, server_default="generic"))
    op.add_column("activation_codes", sa.Column("customer_id", sa.Integer()))
    op.add_column("activation_codes", sa.Column("subscription_start_at", sa.Text()))
    op.add_column("activation_codes", sa.Column("subscription_end_at", sa.Text()))
    op.create_index("idx_activation_codes_customer", "activation_codes", ["customer_id", "status"])
    op.create_index("idx_activation_codes_mode", "activation_codes", ["activation_mode", "status"])


def downgrade() -> None:
    op.drop_index("idx_activation_codes_mode", table_name="activation_codes")
    op.drop_index("idx_activation_codes_customer", table_name="activation_codes")
    op.drop_column("activation_codes", "subscription_end_at")
    op.drop_column("activation_codes", "subscription_start_at")
    op.drop_column("activation_codes", "customer_id")
    op.drop_column("activation_codes", "activation_mode")

    op.drop_column("customers", "last_unbound_reason")
    op.drop_column("customers", "last_unbound_by_username")
    op.drop_column("customers", "last_unbound_by_admin_id")
    op.drop_column("customers", "unbound_at")
    op.drop_column("customers", "bound_at")
    op.drop_column("customers", "bind_status")
    op.execute("update customers set openid = '__downgrade_unbound_customer_' || id where openid is null")
    op.alter_column("customers", "openid", existing_type=sa.Text(), nullable=False)
