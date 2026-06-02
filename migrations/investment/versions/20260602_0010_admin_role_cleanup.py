# encoding:utf-8
"""Clean up investment admin roles.

Revision ID: 20260602_0010
Revises: 20260529_0009
Create Date: 2026-06-02
"""

from alembic import op

revision = "20260602_0010"
down_revision = "20260529_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE investment_admin_users
        SET role = CASE
            WHEN role = 'technical_admin' THEN 'admin'
            WHEN role IN ('uploader', 'poster', 'operator', 'readonly') THEN 'content_operator'
            ELSE role
        END
        WHERE role IN ('technical_admin', 'uploader', 'poster', 'operator', 'readonly')
        """
    )


def downgrade() -> None:
    # Role cleanup is intentionally one-way: the old roles no longer have
    # distinct meanings after migration.
    pass
