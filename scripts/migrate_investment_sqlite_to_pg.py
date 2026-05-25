# encoding:utf-8
import argparse
import json
import re
import sqlite3
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Callable

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from business.investment import db as investment_db  # noqa: E402
from business.investment import schema  # noqa: E402

TABLE_NAMES = (
    "investment_users",
    "investment_request_records",
    "investment_daily_contents",
    "investment_output_files",
    "investment_configs",
    "investment_stock_symbols",
)

TABLES = {
    "investment_users": schema.investment_users,
    "investment_request_records": schema.investment_request_records,
    "investment_daily_contents": schema.investment_daily_contents,
    "investment_output_files": schema.investment_output_files,
}

CONFLICT_COLUMNS = {
    "investment_request_records": ["request_id"],
    "investment_daily_contents": ["content_id"],
    "investment_output_files": ["id"],
}

SEQUENCE_TABLES = (
    ("investment_users", "id"),
    ("investment_output_files", "id"),
)


def read_sqlite_tables(sqlite_path: str | Path) -> OrderedDict[str, list[dict]]:
    path = Path(sqlite_path)
    if not path.is_file():
        raise FileNotFoundError("SQLite source does not exist")

    rows_by_table: OrderedDict[str, list[dict]] = OrderedDict()
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        for table_name in TABLE_NAMES:
            rows = conn.execute(f"select * from {table_name}").fetchall()
            rows_by_table[table_name] = [dict(row) for row in rows]
    return rows_by_table


def _upsert_rows(conn, table_name: str, rows: list[dict]) -> None:
    if not rows:
        return

    table = TABLES[table_name]
    if table_name == "investment_users":
        conflict_columns = ["id"] if rows[0].get("id") is not None else ["openid"]
    else:
        conflict_columns = CONFLICT_COLUMNS[table_name]

    stmt = insert(table).values(rows)
    primary_key_columns = {column.name for column in table.primary_key.columns}
    excluded_columns = set(conflict_columns) | primary_key_columns
    set_mapping = {
        column.name: getattr(stmt.excluded, column.name)
        for column in table.columns
        if column.name not in excluded_columns and column.name in rows[0]
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c[name] for name in conflict_columns],
        set_=set_mapping,
    )
    conn.execute(stmt)


def _reset_postgres_sequences(conn) -> None:
    for table_name, column_name in SEQUENCE_TABLES:
        conn.execute(
            text(
                f"""
                select setval(
                    pg_get_serial_sequence('{table_name}', '{column_name}'),
                    coalesce((select max({column_name}) from {table_name}), 1),
                    (select count(*) from {table_name}) > 0
                )
                """
            )
        )


def copy_tables_to_postgres(
    pg_url: str,
    tables: OrderedDict[str, list[dict]] | dict[str, list[dict]],
    *,
    engine_factory: Callable = create_engine,
) -> dict[str, int]:
    if not investment_db.is_postgresql_url(pg_url):
        raise ValueError("target URL must be PostgreSQL")

    engine = engine_factory(pg_url, future=True)
    with engine.begin() as conn:
        schema.metadata.create_all(conn)
        for table_name in TABLE_NAMES:
            rows = tables.get(table_name, [])
            if table_name == "investment_configs":
                for row in rows:
                    investment_db.upsert_config(
                        conn,
                        row["config_key"],
                        row.get("config_value"),
                        row["updated_at"],
                        row.get("updated_by"),
                    )
            elif table_name == "investment_stock_symbols":
                if rows:
                    investment_db.upsert_stock_symbols(conn, rows)
            else:
                _upsert_rows(conn, table_name, rows)
        _reset_postgres_sequences(conn)
    return {table_name: len(tables.get(table_name, [])) for table_name in TABLE_NAMES}


def migrate_sqlite_to_postgres(sqlite_path: str | Path, pg_url: str) -> dict:
    if not investment_db.is_postgresql_url(pg_url):
        raise ValueError("target URL must be PostgreSQL")

    tables = read_sqlite_tables(sqlite_path)
    counts = copy_tables_to_postgres(pg_url, tables)
    return {"status": "success", "tables": counts}


def _sanitize_error_message(message: str, pg_url: str = "") -> str:
    sanitized = message
    if pg_url:
        sanitized = sanitized.replace(pg_url, "[redacted PostgreSQL URL]")
    sanitized = re.sub(r"postgresql(?:\+\w+)?://\S+", "[redacted PostgreSQL URL]", sanitized)
    return sanitized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate investment SQLite tables to PostgreSQL.")
    parser.add_argument("--sqlite", required=True, help="Source investment SQLite database file.")
    parser.add_argument("--pg", required=True, help="Target PostgreSQL SQLAlchemy URL.")
    args = parser.parse_args(argv)

    try:
        payload = migrate_sqlite_to_postgres(args.sqlite, args.pg)
    except Exception as exc:  # noqa: BLE001 - CLI reports scheduler-friendly JSON errors.
        payload = {
            "status": "error",
            "message": _sanitize_error_message(str(exc), args.pg),
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 1

    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
