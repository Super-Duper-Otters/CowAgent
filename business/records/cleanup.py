# encoding:utf-8
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, func, or_, select

from business.schema.db import connect
from business.schema.tables import (
    investment_admin_sessions,
    investment_cache_entries,
    investment_configs,
    investment_daily_contents,
    investment_request_records,
    investment_stock_symbols,
)


DEFAULT_EXCEPTION_REQUEST_RETENTION_DAYS = 30
DEFAULT_FAILED_CONTENT_RETENTION_DAYS = 30
DEFAULT_INVALID_CACHE_RETENTION_DAYS = 60


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
    exception_request_retention_days: int = DEFAULT_EXCEPTION_REQUEST_RETENTION_DAYS,
    failed_content_retention_days: int = DEFAULT_FAILED_CONTENT_RETENTION_DAYS,
    invalid_cache_retention_days: int = DEFAULT_INVALID_CACHE_RETENTION_DAYS,
) -> dict[str, int]:
    current = _parse_now(now)
    current_iso = current.isoformat()
    exception_cutoff = (current - timedelta(days=exception_request_retention_days)).isoformat()
    failed_content_cutoff = (current - timedelta(days=failed_content_retention_days)).isoformat()
    invalid_cache_cutoff = (current - timedelta(days=invalid_cache_retention_days)).isoformat()

    runtime_config_condition = investment_configs.c.config_key.like("runtime.pg.test.%")
    runtime_stock_condition = investment_stock_symbols.c.source == "runtime-test"
    expired_session_condition = investment_admin_sessions.c.expires_at < current_iso
    old_exception_condition = and_(
        investment_request_records.c.service_type.in_(("unmatched", "unauthorized_request")),
        investment_request_records.c.status == "failed",
        investment_request_records.c.created_at < exception_cutoff,
    )
    old_failed_content_condition = and_(
        investment_daily_contents.c.status == "generate_failed",
        investment_daily_contents.c.created_at < failed_content_cutoff,
        or_(
            investment_daily_contents.c.output_image.is_(None),
            investment_daily_contents.c.output_image == "",
        ),
    )
    stale_cache_condition = and_(
        investment_cache_entries.c.status != "active",
        investment_cache_entries.c.updated_at < invalid_cache_cutoff,
    )

    with connect() as conn:
        result: dict[str, int] = {
            "runtime_test_configs": _count(conn, investment_configs, runtime_config_condition),
            "runtime_test_stocks": _count(conn, investment_stock_symbols, runtime_stock_condition),
            "expired_admin_sessions": _count(conn, investment_admin_sessions, expired_session_condition),
            "old_exception_requests": _count(conn, investment_request_records, old_exception_condition),
            "old_failed_contents": _count(conn, investment_daily_contents, old_failed_content_condition),
            "stale_invalid_cache_entries": _count(conn, investment_cache_entries, stale_cache_condition),
        }
        if dry_run:
            return result

        _delete(conn, investment_configs, runtime_config_condition)
        _delete(conn, investment_stock_symbols, runtime_stock_condition)
        _delete(conn, investment_admin_sessions, expired_session_condition)
        _delete(conn, investment_request_records, old_exception_condition)
        _delete(conn, investment_daily_contents, old_failed_content_condition)
        _delete(conn, investment_cache_entries, stale_cache_condition)
        return result
