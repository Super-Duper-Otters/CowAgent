# encoding:utf-8
"""dedupe stock symbol codes"""

from alembic import op


revision = "20260630_0033"
down_revision = "20260630_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("delete from stock_symbols where code is null or btrim(code) = ''")
    op.execute(
        """
        delete from stock_symbols target
        using (
            select
                ctid,
                row_number() over (
                    partition by code
                    order by
                        case
                            when source like 'tushare%' then 100
                            when source like 'baostock%' then 80
                            when source like 'akshare%' then 60
                            else 10
                        end desc,
                        updated_at desc,
                        name asc,
                        market asc
                ) as duplicate_rank
            from stock_symbols
            where code is not null and btrim(code) <> ''
        ) ranked
        where target.ctid = ranked.ctid
          and ranked.duplicate_rank > 1
        """
    )


def downgrade() -> None:
    pass
