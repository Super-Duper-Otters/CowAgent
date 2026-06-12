# encoding:utf-8
"""Record effective AI input prompts.

Revision ID: 20260612_0020
Revises: 20260610_0019
Create Date: 2026-06-12
"""

import sqlalchemy as sa
from alembic import op

revision = "20260612_0020"
down_revision = "20260610_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_records", sa.Column("input_prompt", sa.Text(), nullable=True))
    op.add_column("internal_call_records", sa.Column("input_prompt", sa.Text(), nullable=True))
    op.add_column("ai_generation_audits", sa.Column("input_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_generation_audits", "input_prompt")
    op.drop_column("internal_call_records", "input_prompt")
    op.drop_column("content_records", "input_prompt")
