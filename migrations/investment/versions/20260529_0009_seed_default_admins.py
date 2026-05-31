# encoding:utf-8
"""Reserved migration slot; no default admin seeding.

Revision ID: 20260529_0009
Revises: 20260527_0008
Create Date: 2026-05-29
"""

revision = "20260529_0009"
down_revision = "20260527_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Intentionally no-op. Admin accounts must be created explicitly through
    # the admin API or test fixtures; migrations must not seed fixed passwords.
    pass


def downgrade() -> None:
    # Account rows may be used or modified after deployment; do not delete them
    # automatically on migration rollback.
    pass
