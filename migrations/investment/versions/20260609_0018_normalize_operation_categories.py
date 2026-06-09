# encoding:utf-8
"""Normalize existing operation audit categories.

Revision ID: 20260609_0018
Revises: 20260609_0017
Create Date: 2026-06-09
"""

from alembic import op

revision = "20260609_0018"
down_revision = "20260609_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE operation_audits
        SET category = CASE
            WHEN action LIKE 'customer.%' OR target_type = 'customer' THEN 'customer'
            WHEN action LIKE 'admin.%' OR target_type = 'admin' THEN 'admin'
            WHEN action LIKE 'skill.%' OR target_type IN ('skill', 'investment_skill') THEN 'skill'
            WHEN action LIKE 'content.%' OR target_type IN ('content', 'daily_content') THEN 'content'
            WHEN action LIKE 'generation.%' OR target_type = 'generation' THEN 'generation'
            WHEN action LIKE 'config.%' OR target_type IN ('config', 'investment_config') THEN 'config'
            WHEN action LIKE 'cache.%' OR target_type = 'cache' THEN 'cache'
            WHEN action LIKE 'stock.%' OR target_type IN ('stock', 'investment_stock_symbol') THEN 'stock'
            WHEN action LIKE 'export.%' OR target_type = 'export' THEN 'export'
            WHEN action LIKE 'health.%' OR target_type = 'health' THEN 'health'
            ELSE 'system'
        END
        WHERE category IS NULL OR category = '' OR category = 'backoffice'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE operation_audits
        SET category = 'backoffice'
        WHERE target_type IN ('investment_skill', 'investment_config', 'investment_stock_symbol')
        """
    )
