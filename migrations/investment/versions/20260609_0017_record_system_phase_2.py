# encoding:utf-8
"""Add record system phase 2 tables.

Revision ID: 20260609_0017
Revises: 20260609_0016
Create Date: 2026-06-09
"""

import sqlalchemy as sa
from alembic import op

revision = "20260609_0017"
down_revision = "20260609_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("request_records", "service_type", new_column_name="service", existing_type=sa.Text())
    op.alter_column("request_records", "output_files", new_column_name="outputs", existing_type=sa.Text())
    op.alter_column("request_records", "error_message", new_column_name="error", existing_type=sa.Text())
    op.alter_column("content_records", "service_type", new_column_name="service", existing_type=sa.Text())
    op.alter_column("content_records", "source_files", new_column_name="sources", existing_type=sa.Text())
    op.alter_column("content_records", "source_text", new_column_name="input_text", existing_type=sa.Text())
    op.alter_column("content_records", "generated_text", new_column_name="output_text", existing_type=sa.Text())
    op.alter_column("content_records", "output_image", new_column_name="output_image_path", existing_type=sa.Text())
    op.alter_column("content_records", "error_message", new_column_name="error", existing_type=sa.Text())
    op.alter_column("artifacts", "service_type", new_column_name="service", existing_type=sa.Text())
    op.alter_column("cache_entries", "service_type", new_column_name="service", existing_type=sa.Text())
    op.alter_column("cache_entries", "output_files", new_column_name="outputs", existing_type=sa.Text())
    op.alter_column("operation_audits", "operation_category", new_column_name="category", existing_type=sa.Text())
    op.alter_column("operation_audits", "result_status", new_column_name="result", existing_type=sa.Text())
    op.alter_column("operation_audits", "error_message", new_column_name="error", existing_type=sa.Text())
    op.create_table(
        "request_events",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("openid", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("message_type", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("media_id", sa.Text(), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=True),
        sa.Column("source_id", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_request_events_request_created", "request_events", ["request_id", "created_at"])
    op.create_index("idx_request_events_openid_created", "request_events", ["openid", "created_at"])
    op.create_index("idx_request_events_type_created", "request_events", ["event_type", "created_at"])
    op.create_table(
        "generation_records",
        sa.Column("generation_id", sa.Text(), primary_key=True),
        sa.Column("content_id", sa.Text(), nullable=False),
        sa.Column("service", sa.Text(), nullable=False),
        sa.Column("operator_id", sa.Integer(), nullable=True),
        sa.Column("operator_name", sa.Text(), nullable=True),
        sa.Column("operator_role", sa.Text(), nullable=True),
        sa.Column("input_text", sa.Text(), nullable=True),
        sa.Column("sources", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column("outputs", sa.Text(), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_generation_records_content_created", "generation_records", ["content_id", "created_at"])
    op.create_index("idx_generation_records_service_created", "generation_records", ["service", "created_at"])
    op.create_index("idx_generation_records_operator_created", "generation_records", ["operator_name", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_generation_records_operator_created", table_name="generation_records")
    op.drop_index("idx_generation_records_service_created", table_name="generation_records")
    op.drop_index("idx_generation_records_content_created", table_name="generation_records")
    op.drop_table("generation_records")
    op.drop_index("idx_request_events_type_created", table_name="request_events")
    op.drop_index("idx_request_events_openid_created", table_name="request_events")
    op.drop_index("idx_request_events_request_created", table_name="request_events")
    op.drop_table("request_events")
    op.alter_column("operation_audits", "error", new_column_name="error_message", existing_type=sa.Text())
    op.alter_column("operation_audits", "result", new_column_name="result_status", existing_type=sa.Text())
    op.alter_column("operation_audits", "category", new_column_name="operation_category", existing_type=sa.Text())
    op.alter_column("cache_entries", "outputs", new_column_name="output_files", existing_type=sa.Text())
    op.alter_column("cache_entries", "service", new_column_name="service_type", existing_type=sa.Text())
    op.alter_column("artifacts", "service", new_column_name="service_type", existing_type=sa.Text())
    op.alter_column("content_records", "error", new_column_name="error_message", existing_type=sa.Text())
    op.alter_column("content_records", "output_image_path", new_column_name="output_image", existing_type=sa.Text())
    op.alter_column("content_records", "output_text", new_column_name="generated_text", existing_type=sa.Text())
    op.alter_column("content_records", "input_text", new_column_name="source_text", existing_type=sa.Text())
    op.alter_column("content_records", "sources", new_column_name="source_files", existing_type=sa.Text())
    op.alter_column("content_records", "service", new_column_name="service_type", existing_type=sa.Text())
    op.alter_column("request_records", "error", new_column_name="error_message", existing_type=sa.Text())
    op.alter_column("request_records", "outputs", new_column_name="output_files", existing_type=sa.Text())
    op.alter_column("request_records", "service", new_column_name="service_type", existing_type=sa.Text())
