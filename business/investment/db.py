# encoding:utf-8
import os
from collections.abc import Mapping
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine

from . import storage

DEFAULT_DATABASE_URL = "postgresql+psycopg://cowagent:cowagent@127.0.0.1:55432/cowagent_investment"
_ENGINE: Engine | None = None
_ENGINE_URL: str | None = None
_STOCK_SYMBOL_UPSERT_BATCH_SIZE = 1000


def _validate_postgresql_url(url: str) -> str:
    if not is_postgresql_url(url):
        raise ValueError("Investment database URL must be a PostgreSQL URL")
    return url


def get_database_url() -> str:
    env_url = os.environ.get("COWAGENT_INVESTMENT_DATABASE_URL", "").strip()
    if env_url:
        return _validate_postgresql_url(env_url)
    try:
        from config import conf

        config_url = str(conf().get("investment_database_url", "") or "").strip()
    except Exception:
        config_url = ""
    if config_url:
        return _validate_postgresql_url(config_url)
    return DEFAULT_DATABASE_URL


def is_postgresql_url(url: str | None = None) -> bool:
    value = (url or "").lower()
    return value.startswith("postgresql://") or value.startswith("postgresql+")


def get_engine() -> Engine:
    global _ENGINE, _ENGINE_URL
    url = get_database_url()
    if _ENGINE is None or _ENGINE_URL != url:
        _ENGINE = create_engine(url, future=True)
        _ENGINE_URL = url
    return _ENGINE


@contextmanager
def connect() -> Iterator[Connection]:
    storage.initialize_storage()
    engine = get_engine()
    with engine.begin() as conn:
        yield conn


def row_to_dict(row) -> dict:
    if row is None:
        return {}
    if isinstance(row, Mapping):
        return dict(row)
    return dict(row._mapping)


def upsert_config(conn, key: str, value: str, updated_at: str, updated_by: str) -> None:
    from .schema import investment_configs

    table = investment_configs
    if conn.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert

    stmt = insert(table).values(
        config_key=key,
        config_value=value,
        updated_at=updated_at,
        updated_by=updated_by,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.config_key],
        set_={
            "config_value": stmt.excluded.config_value,
            "updated_at": stmt.excluded.updated_at,
            "updated_by": stmt.excluded.updated_by,
        },
    )
    conn.execute(stmt)


def upsert_stock_symbols(conn, rows: list[dict]) -> None:
    from .schema import investment_stock_symbols

    if not rows:
        return

    table = investment_stock_symbols
    if conn.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert

    for start in range(0, len(rows), _STOCK_SYMBOL_UPSERT_BATCH_SIZE):
        batch = rows[start : start + _STOCK_SYMBOL_UPSERT_BATCH_SIZE]
        stmt = insert(table).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=[table.c.code],
            set_={
                "name": stmt.excluded.name,
                "market": stmt.excluded.market,
                "ts_code": stmt.excluded.ts_code,
                "source": stmt.excluded.source,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        conn.execute(stmt)


def reset_engine_for_tests() -> None:
    global _ENGINE, _ENGINE_URL
    if _ENGINE is not None:
        _ENGINE.dispose()
    _ENGINE = None
    _ENGINE_URL = None
