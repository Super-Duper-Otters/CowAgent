# encoding:utf-8
"""add stock symbol asset type"""

from alembic import op
import sqlalchemy as sa


revision = "20260630_0031"
down_revision = "20260630_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stock_symbols", sa.Column("asset_type", sa.Text(), nullable=True))
    op.execute(
        """
        update stock_symbols
        set asset_type = case
            when market = 'HK' then 'hk_stock'
            when market = 'US' then 'us_stock'
            when market in ('SGE', 'COMEX') then 'gold'
            when market in ('SHFE', 'DCE', 'CZCE', 'CFFEX', 'GFEX', 'INE') then 'futures'
            else 'a_share'
        end
        """
    )
    op.alter_column(
        "stock_symbols",
        "asset_type",
        existing_type=sa.Text(),
        nullable=False,
        server_default="a_share",
    )
    op.create_index("idx_stock_symbols_asset_type", "stock_symbols", ["asset_type"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_stock_symbols_asset_type", table_name="stock_symbols")
    op.drop_column("stock_symbols", "asset_type")
