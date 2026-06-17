# encoding:utf-8
"""Simplify investment table names.

Revision ID: 20260609_0015
Revises: 20260605_0014
Create Date: 2026-06-09
"""

from alembic import op

revision = "20260609_0015"
down_revision = "20260605_0014"
branch_labels = None
depends_on = None


TABLE_RENAMES = (
    ("investment_users", "customers"),
    ("investment_admin_users", "admins"),
    ("investment_admin_sessions", "admin_sessions"),
    ("investment_request_records", "request_records"),
    ("investment_daily_contents", "content_records"),
    ("investment_output_files", "artifacts"),
    ("investment_cache_entries", "cache_entries"),
    ("investment_configs", "configs"),
    ("investment_operation_audits", "operation_audits"),
    ("investment_stock_symbols", "stock_symbols"),
)

INDEX_RENAMES = (
    ("idx_investment_users_openid", "idx_customers_openid"),
    ("idx_investment_admin_users_username", "idx_admins_username"),
    ("idx_investment_admin_sessions_token", "idx_admin_sessions_token"),
    ("idx_investment_admin_sessions_user", "idx_admin_sessions_user"),
    ("idx_investment_request_records_created", "idx_request_records_created"),
    ("idx_investment_request_records_service_status", "idx_request_records_service_status"),
    ("idx_investment_daily_contents_service_status", "idx_content_records_service_status"),
    ("idx_investment_daily_contents_effective", "idx_content_records_effective"),
    ("idx_investment_daily_contents_effective_date", "idx_content_records_effective_date"),
    ("idx_investment_output_files_owner", "idx_artifacts_owner"),
    ("idx_investment_cache_lookup", "idx_cache_entries_lookup"),
    ("idx_investment_cache_service_date", "idx_cache_entries_service_date"),
    ("idx_investment_operation_audits_created", "idx_operation_audits_created"),
    ("idx_investment_operation_audits_target", "idx_operation_audits_target"),
    ("idx_investment_stock_symbols_name", "idx_stock_symbols_name"),
    ("idx_investment_stock_symbols_updated", "idx_stock_symbols_updated"),
)


def _rename_index(old_name: str, new_name: str) -> None:
    op.execute(f'ALTER INDEX IF EXISTS "{old_name}" RENAME TO "{new_name}"')


def upgrade() -> None:
    for old_name, new_name in TABLE_RENAMES:
        op.rename_table(old_name, new_name)
    for old_name, new_name in INDEX_RENAMES:
        _rename_index(old_name, new_name)


def downgrade() -> None:
    for old_name, new_name in reversed(INDEX_RENAMES):
        _rename_index(new_name, old_name)
    for old_name, new_name in reversed(TABLE_RENAMES):
        op.rename_table(new_name, old_name)
