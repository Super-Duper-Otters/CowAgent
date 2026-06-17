# encoding:utf-8
"""Add entry isolation and common AI audit records.

Revision ID: 20260610_0019
Revises: 20260609_0018
Create Date: 2026-06-10
"""

import sqlalchemy as sa
from alembic import op

revision = "20260610_0019"
down_revision = "20260609_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in (
        sa.Column("entry_type", sa.Text(), nullable=True),
        sa.Column("action_type", sa.Text(), nullable=True),
        sa.Column("actor_type", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.Text(), nullable=True),
        sa.Column("actor_name", sa.Text(), nullable=True),
        sa.Column("actor_role", sa.Text(), nullable=True),
    ):
        op.add_column("request_records", column)
    op.create_index("idx_request_records_entry_created", "request_records", ["entry_type", "created_at"])
    op.execute(
        """
        UPDATE request_records
        SET
            entry_type = COALESCE(NULLIF(entry_type, ''), 'external_request'),
            actor_type = COALESCE(NULLIF(actor_type, ''), 'customer'),
            actor_id = COALESCE(NULLIF(actor_id, ''), openid),
            action_type = COALESCE(
                NULLIF(action_type, ''),
                CASE
                    WHEN service IN ('rate', 'convertible_bond') THEN 'deliver_effective_content'
                    ELSE 'generate'
                END
            )
        """
    )
    op.create_table(
        "ai_generation_audits",
        sa.Column("audit_id", sa.Text(), primary_key=True),
        sa.Column("entry_type", sa.Text(), nullable=False),
        sa.Column("service", sa.Text(), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=True),
        sa.Column("actor_name", sa.Text(), nullable=True),
        sa.Column("actor_role", sa.Text(), nullable=True),
        sa.Column("business_record_type", sa.Text(), nullable=True),
        sa.Column("business_record_id", sa.Text(), nullable=True),
        sa.Column("input_text", sa.Text(), nullable=True),
        sa.Column("sources", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column("outputs", sa.Text(), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_ai_generation_audits_business", "ai_generation_audits", ["business_record_type", "business_record_id"])
    op.create_index("idx_ai_generation_audits_service_created", "ai_generation_audits", ["service", "created_at"])
    op.create_index("idx_ai_generation_audits_actor_created", "ai_generation_audits", ["actor_name", "created_at"])
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("generation_records"):
        op.execute(
            """
            INSERT INTO request_records (
                request_id, openid, raw_input, service,
                entry_type, action_type, actor_type, actor_id, actor_name, actor_role,
                status, error_code, user_prompt, error, outputs,
                normalized_target, stock_code, stock_name, customer_name, institution,
                market_date, cache_key, cache_hit, program_version, ta_version,
                renderer_version, template_version, created_at, updated_at, elapsed_ms
            )
            SELECT
                generation_id,
                COALESCE(NULLIF(CAST(operator_id AS TEXT), ''), NULLIF(operator_name, ''), 'internal'),
                COALESCE(input_text, ''),
                service,
                'internal_call',
                'generate',
                CASE WHEN COALESCE(operator_name, '') = '' THEN 'system' ELSE 'admin' END,
                COALESCE(CAST(operator_id AS TEXT), ''),
                COALESCE(operator_name, ''),
                COALESCE(operator_role, ''),
                CASE WHEN result = 'success' THEN 'success' ELSE 'failed' END,
                COALESCE(error_code, ''),
                '',
                COALESCE(error, ''),
                COALESCE(outputs, '[]'),
                COALESCE(input_text, ''),
                '',
                '',
                '',
                '',
                '',
                '',
                0,
                '',
                '',
                '',
                '',
                created_at,
                updated_at,
                elapsed_ms
            FROM generation_records
            WHERE NOT EXISTS (
                SELECT 1 FROM request_records current
                WHERE current.request_id = generation_records.generation_id
            )
            """
        )
        op.execute(
            """
            INSERT INTO ai_generation_audits (
                audit_id, entry_type, service, action_type, actor_type, actor_id, actor_name, actor_role,
                business_record_type, business_record_id, input_text, sources, provider, model, result,
                error_code, error, output_text, outputs, elapsed_ms, created_at, updated_at
            )
            SELECT
                generation_id || '-ai',
                'internal_call',
                service,
                'generate',
                CASE WHEN COALESCE(operator_name, '') = '' THEN 'system' ELSE 'admin' END,
                COALESCE(CAST(operator_id AS TEXT), ''),
                COALESCE(operator_name, ''),
                COALESCE(operator_role, ''),
                'request',
                generation_id,
                COALESCE(input_text, ''),
                COALESCE(sources, '[]'),
                '',
                '',
                COALESCE(result, ''),
                COALESCE(error_code, ''),
                COALESCE(error, ''),
                COALESCE(output_text, ''),
                COALESCE(outputs, '[]'),
                elapsed_ms,
                created_at,
                updated_at
            FROM generation_records
            """
        )
        existing_indexes = {item["name"] for item in inspector.get_indexes("generation_records")}
        for index_name in (
            "idx_generation_records_operator_created",
            "idx_generation_records_service_created",
            "idx_generation_records_content_created",
        ):
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name="generation_records")
        op.drop_table("generation_records")


def downgrade() -> None:
    op.drop_index("idx_ai_generation_audits_actor_created", table_name="ai_generation_audits")
    op.drop_index("idx_ai_generation_audits_service_created", table_name="ai_generation_audits")
    op.drop_index("idx_ai_generation_audits_business", table_name="ai_generation_audits")
    op.drop_table("ai_generation_audits")
    op.drop_index("idx_request_records_entry_created", table_name="request_records")
    for column_name in ("actor_role", "actor_name", "actor_id", "actor_type", "action_type", "entry_type"):
        op.drop_column("request_records", column_name)
