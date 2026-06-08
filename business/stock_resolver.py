# encoding:utf-8
"""CowAgent business stock dictionary facade."""

from sqlalchemy import select

from business.investment.stock_resolver import (
    list_stock_symbols,
    refresh_from_akshare,
    refresh_from_auto,
    refresh_from_tushare,
    stock_dictionary_stats,
)
from business.db import connect, row_to_dict
from business.schema import investment_stock_symbols


def stock_dictionary_stats_with_latest_source() -> dict[str, object]:
    stats = stock_dictionary_stats()
    table = investment_stock_symbols
    latest_updated_at = select(table.c.updated_at).order_by(table.c.updated_at.desc()).limit(1).scalar_subquery()
    stmt = select(table.c.source).where(table.c.updated_at == latest_updated_at).order_by(table.c.source).limit(1)
    with connect() as conn:
        row = conn.execute(stmt).fetchone()
    stats["latest_source"] = row_to_dict(row).get("source", "") if row else ""
    return stats
