# encoding:utf-8
from sqlalchemy import Column, Index, Integer, MetaData, Table, Text

metadata = MetaData()

investment_users = Table(
    "investment_users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("openid", Text, nullable=False),
    Column("name", Text),
    Column("institution", Text),
    Column("mobile", Text),
    Column("enabled", Integer, nullable=False, server_default="1"),
    Column("allowed_services", Text, nullable=False),
    Column("auth_start_at", Text),
    Column("auth_end_at", Text),
    Column("remark", Text),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Index("idx_investment_users_openid", "openid", unique=True),
)

investment_request_records = Table(
    "investment_request_records",
    metadata,
    Column("request_id", Text, primary_key=True),
    Column("openid", Text, nullable=False),
    Column("raw_input", Text, nullable=False),
    Column("service_type", Text),
    Column("status", Text, nullable=False),
    Column("error_code", Text),
    Column("user_prompt", Text),
    Column("error_message", Text),
    Column("output_files", Text),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Column("elapsed_ms", Integer),
    Index("idx_investment_request_records_created", "created_at"),
    Index("idx_investment_request_records_service_status", "service_type", "status"),
)

investment_daily_contents = Table(
    "investment_daily_contents",
    metadata,
    Column("content_id", Text, primary_key=True),
    Column("service_type", Text, nullable=False),
    Column("source_files", Text),
    Column("source_text", Text),
    Column("generated_text", Text),
    Column("output_image", Text),
    Column("status", Text, nullable=False),
    Column("error_message", Text),
    Column("operator", Text),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Column("effective_at", Text),
    Index("idx_investment_daily_contents_service_status", "service_type", "status"),
    Index("idx_investment_daily_contents_effective", "service_type", "effective_at"),
)

investment_output_files = Table(
    "investment_output_files",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("owner_id", Text),
    Column("file_path", Text, nullable=False),
    Column("file_type", Text),
    Column("service_type", Text),
    Column("created_at", Text, nullable=False),
    Index("idx_investment_output_files_owner", "owner_id"),
)

investment_configs = Table(
    "investment_configs",
    metadata,
    Column("config_key", Text, primary_key=True),
    Column("config_value", Text),
    Column("updated_at", Text, nullable=False),
    Column("updated_by", Text),
)

investment_stock_symbols = Table(
    "investment_stock_symbols",
    metadata,
    Column("code", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("market", Text, nullable=False),
    Column("ts_code", Text),
    Column("source", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Index("idx_investment_stock_symbols_code", "code", unique=True),
    Index("idx_investment_stock_symbols_name", "name"),
    Index("idx_investment_stock_symbols_updated", "updated_at"),
)
