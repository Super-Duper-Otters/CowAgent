# encoding:utf-8
"""Seed default investment admin accounts.

Revision ID: 20260529_0009
Revises: 20260527_0008
Create Date: 2026-05-29
"""

revision = "20260529_0009"
down_revision = "20260527_0008"
branch_labels = None
depends_on = None


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="microseconds")


def upgrade() -> None:
    import sqlalchemy as sa

    from alembic import op
    from business.accounts.auth_service import hash_password

    bind = op.get_bind()
    table = sa.table(
        "investment_admin_users",
        sa.column("username", sa.Text()),
        sa.column("password_hash", sa.Text()),
        sa.column("role", sa.Text()),
        sa.column("enabled", sa.Integer()),
        sa.column("created_at", sa.Text()),
        sa.column("updated_at", sa.Text()),
    )
    now = _now()
    accounts = [
        ("admin", "admin"),
        ("poster1", "content_operator"),
        ("poster2", "content_operator"),
        ("poster3", "content_operator"),
    ]
    for username, role in accounts:
        exists = bind.execute(sa.select(table.c.username).where(table.c.username == username)).scalar_one_or_none()
        if exists:
            continue
        bind.execute(
            table.insert().values(
                username=username,
                password_hash=hash_password("password"),
                role=role,
                enabled=1,
                created_at=now,
                updated_at=now,
            )
        )


def downgrade() -> None:
    # Account rows may be used or modified after deployment; do not delete them
    # automatically on migration rollback.
    pass
