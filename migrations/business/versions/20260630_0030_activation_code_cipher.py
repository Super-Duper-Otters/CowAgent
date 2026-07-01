# encoding:utf-8
"""add encrypted activation code display value"""

from alembic import op
import sqlalchemy as sa


revision = "20260630_0030"
down_revision = "20260630_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("activation_codes", sa.Column("code_cipher", sa.Text()))


def downgrade() -> None:
    op.drop_column("activation_codes", "code_cipher")
