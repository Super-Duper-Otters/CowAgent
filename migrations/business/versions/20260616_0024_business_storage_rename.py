# encoding:utf-8
"""Record business storage rename.

Revision ID: 20260616_0024
Revises: 20260616_0023
Create Date: 2026-06-16
"""
revision = "20260616_0024"
down_revision = "20260616_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Runtime storage directory naming changed outside the database schema.
    pass


def downgrade() -> None:
    pass
