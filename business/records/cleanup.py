# encoding:utf-8
from datetime import UTC, datetime

from sqlalchemy import delete, func, select

from business.schema.db import connect
from business.schema.tables import (
    investment_admin_sessions,
    investment_configs,
    investment_stock_symbols,
)


def _parse_now(value: str | datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _count(conn, table, *conditions) -> int:
    stmt = select(func.count()).select_from(table)
    if conditions:
        stmt = stmt.where(*conditions)
    return int(conn.execute(stmt).scalar_one() or 0)


def _delete(conn, table, *conditions) -> None:
    stmt = delete(table)
    if conditions:
        stmt = stmt.where(*conditions)
    conn.execute(stmt)


def cleanup_useless_business_records(
    *,
    now: str | datetime | None = None,
    dry_run: bool = True,
) -> dict[str, int]:
    current = _parse_now(now)
    current_iso = current.isoformat()

    runtime_config_condition = investment_configs.c.config_key.like("runtime.pg.test.%")
    runtime_stock_condition = investment_stock_symbols.c.source == "runtime-test"
    expired_session_condition = investment_admin_sessions.c.expires_at < current_iso

    with connect() as conn:
        result: dict[str, int] = {
            "runtime_test_configs": _count(conn, investment_configs, runtime_config_condition),
            "runtime_test_stocks": _count(conn, investment_stock_symbols, runtime_stock_condition),
            "expired_admin_sessions": _count(conn, investment_admin_sessions, expired_session_condition),
        }
        if dry_run:
            return result

        _delete(conn, investment_configs, runtime_config_condition)
        _delete(conn, investment_stock_symbols, runtime_stock_condition)
        _delete(conn, investment_admin_sessions, expired_session_condition)
        return result
