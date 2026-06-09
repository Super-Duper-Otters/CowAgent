# encoding:utf-8
"""Simplify investment constraint names.

Revision ID: 20260609_0016
Revises: 20260609_0015
Create Date: 2026-06-09
"""

from alembic import op

revision = "20260609_0016"
down_revision = "20260609_0015"
branch_labels = None
depends_on = None


CONSTRAINT_RENAMES = (
    ("customers", "investment_users_pkey", "customers_pkey"),
    ("admins", "investment_admin_users_pkey", "admins_pkey"),
    ("admin_sessions", "investment_admin_sessions_pkey", "admin_sessions_pkey"),
    ("request_records", "investment_request_records_pkey", "request_records_pkey"),
    ("content_records", "investment_daily_contents_pkey", "content_records_pkey"),
    ("artifacts", "investment_output_files_pkey", "artifacts_pkey"),
    ("cache_entries", "investment_cache_entries_pkey", "cache_entries_pkey"),
    ("configs", "investment_configs_pkey", "configs_pkey"),
    ("operation_audits", "investment_operation_audits_pkey", "operation_audits_pkey"),
    ("stock_symbols", "investment_stock_symbols_pkey", "stock_symbols_pkey"),
)

INDEX_RENAMES = (
    ("idx_investment_stock_symbols_code", "idx_stock_symbols_code"),
)


def _rename_constraint(table_name: str, old_name: str, new_name: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = '{table_name}'::regclass
                  AND conname = '{old_name}'
            ) AND NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = '{table_name}'::regclass
                  AND conname = '{new_name}'
            ) THEN
                ALTER TABLE "{table_name}" RENAME CONSTRAINT "{old_name}" TO "{new_name}";
            END IF;
        END $$;
        """
    )


def _rename_index(old_name: str, new_name: str) -> None:
    op.execute(f'ALTER INDEX IF EXISTS "{old_name}" RENAME TO "{new_name}"')


def upgrade() -> None:
    for table_name, old_name, new_name in CONSTRAINT_RENAMES:
        _rename_constraint(table_name, old_name, new_name)
    for old_name, new_name in INDEX_RENAMES:
        _rename_index(old_name, new_name)


def downgrade() -> None:
    for old_name, new_name in reversed(INDEX_RENAMES):
        _rename_index(new_name, old_name)
    for table_name, old_name, new_name in reversed(CONSTRAINT_RENAMES):
        _rename_constraint(table_name, new_name, old_name)
