# encoding:utf-8
import importlib
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from business.constants import ErrorCode
from business.config_service import get_config, mask_sensitive_value
from business.db import connect, row_to_dict, upsert_stock_symbols
from business.schema import investment_stock_symbols


_A_SHARE_CODE_RE = re.compile(r"\d{6}\.(SZ|SH)", re.IGNORECASE)
_BARE_CODE_RE = re.compile(r"\d{6}")
_HK_CODE_RE = re.compile(r"\d{5}\.HK", re.IGNORECASE)
_HK_PREFIX_RE = re.compile(r"HK(\d{5})", re.IGNORECASE)
_US_CODE_RE = re.compile(r"[A-Z0-9_.-]+\.US", re.IGNORECASE)
_US_PREFIX_RE = re.compile(r"US:([A-Z0-9_.-]+)", re.IGNORECASE)


def _standardize_code(value: str) -> str:
    code = str(value or "").strip().upper()
    if _A_SHARE_CODE_RE.fullmatch(code):
        return code
    if _BARE_CODE_RE.fullmatch(code):
        suffix = ".SH" if code.startswith("6") else ".SZ"
        return f"{code}{suffix}"
    if _HK_CODE_RE.fullmatch(code):
        return code
    hk_prefix_match = _HK_PREFIX_RE.fullmatch(code)
    if hk_prefix_match:
        return f"{hk_prefix_match.group(1)}.HK"
    us_prefix_match = _US_PREFIX_RE.fullmatch(code)
    if us_prefix_match:
        return f"{us_prefix_match.group(1).upper()}.US"
    if _US_CODE_RE.fullmatch(code):
        ticker = code.rsplit(".", 1)[0].upper()
        return f"{ticker}.US"
    return code


def _infer_market(code: str, row_market: str = "") -> str:
    market = str(row_market or "").strip().upper()
    if market:
        return market
    if "." in code:
        return code.rsplit(".", 1)[1]
    return "SH" if code.startswith("6") else "SZ"


def _tushare_client():
    token = get_tushare_token()
    if not token:
        raise RuntimeError("tushare token not configured")
    tushare = importlib.import_module("tushare")
    return tushare.pro_api(token)


def _records_from_frame(frame: Any) -> list[dict[str, Any]]:
    if hasattr(frame, "to_dict"):
        records = frame.to_dict("records")
        return [dict(row) for row in records]
    return [dict(row) for row in frame]


def _first_text(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _resolve_name_from_local(value: str) -> tuple[str | None, ErrorCode | None]:
    table = investment_stock_symbols
    stmt = (
        select(table.c.code)
        .where(table.c.name == value, table.c.source.in_(("tushare_a", "tushare_hk", "tushare_us")))
        .order_by(table.c.code)
    )
    with connect() as conn:
        rows = conn.execute(stmt).fetchall()

    if len(rows) == 1:
        return row_to_dict(rows[0])["code"], None
    if len(rows) > 1:
        return None, ErrorCode.STOCK_AMBIGUOUS
    return None, ErrorCode.STOCK_NOT_FOUND


def list_exact_stock_name_matches(value: str, limit: int = 10) -> list[dict[str, str]]:
    table = investment_stock_symbols
    limit_value = max(1, min(int(limit or 10), 50))
    stmt = (
        select(table.c.code, table.c.name, table.c.market, table.c.ts_code, table.c.source)
        .where(table.c.name == str(value or "").strip(), table.c.source.in_(("tushare_a", "tushare_hk", "tushare_us")))
        .order_by(table.c.code)
        .limit(limit_value)
    )
    with connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [row_to_dict(row) for row in rows]


def get_stock_symbol_by_code(value: str) -> dict[str, str]:
    code = _standardize_code(value)
    if not code:
        return {}
    table = investment_stock_symbols
    stmt = (
        select(table.c.code, table.c.name, table.c.market, table.c.ts_code, table.c.source)
        .where(table.c.code == code, table.c.source.in_(("tushare_a", "tushare_hk", "tushare_us")))
        .order_by(table.c.source)
        .limit(1)
    )
    with connect() as conn:
        row = conn.execute(stmt).fetchone()
    return row_to_dict(row) if row else {}


def get_tushare_token(masked: bool = False) -> str:
    token = str(get_config("tushare.token", "") or "").strip()
    if not token:
        token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        token_file = Path.home() / ".tushare_token"
        if token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
    return mask_sensitive_value(token) if masked else token


def refresh_a_share_symbols_from_tushare() -> int:
    pro = _tushare_client()
    frame = pro.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,exchange")
    rows = []
    for row in _records_from_frame(frame):
        ts_code = _first_text(row, ("ts_code",))
        symbol = _first_text(row, ("symbol", "code"))
        code = _standardize_code(ts_code or symbol)
        market = _infer_market(code)
        rows.append(
            {
                "code": code,
                "market": market,
                "name": _first_text(row, ("name", "名称")),
                "ts_code": ts_code or code,
                "source": "tushare_a",
            }
        )
    return refresh_stock_symbols(rows, source="tushare_a")


def refresh_hk_symbols_from_tushare() -> int:
    pro = _tushare_client()
    frame = pro.hk_basic(list_status="L")
    rows = []
    for row in _records_from_frame(frame):
        ts_code = _first_text(row, ("ts_code", "code"))
        name = _first_text(row, ("name", "名称"))
        if not name:
            continue
        rows.append(
            {
                "code": _standardize_code(ts_code),
                "market": "HK",
                "name": name,
                "ts_code": ts_code or None,
                "source": "tushare_hk",
            }
        )
    return refresh_stock_symbols(rows, source="tushare_hk")


def refresh_us_symbols_from_tushare() -> int:
    pro = _tushare_client()
    frame = pro.us_basic()
    rows = []
    for row in _records_from_frame(frame):
        ts_code = _first_text(row, ("ts_code", "code", "symbol"))
        name = _first_text(row, ("name", "名称"))
        if not name:
            continue
        rows.append(
            {
                "code": _standardize_code(f"{ts_code}.US" if "." not in str(ts_code or "") else ts_code),
                "market": "US",
                "name": name,
                "ts_code": ts_code or None,
                "source": "tushare_us",
            }
        )
    return refresh_stock_symbols(rows, source="tushare_us")


def refresh_all_symbols_from_tushare() -> dict[str, object]:
    result: dict[str, object] = {}
    for market_key, refresher in (
        ("a_share", refresh_a_share_symbols_from_tushare),
        ("hk", refresh_hk_symbols_from_tushare),
        ("us", refresh_us_symbols_from_tushare),
    ):
        try:
            result[market_key] = {"count": refresher()}
        except Exception as exc:  # noqa: BLE001 - each Tushare market refresh is reported independently.
            result[market_key] = {"error": str(exc)}
    return result


def resolve_stock(target: str, auto_refresh_on_miss: bool = True) -> tuple[str | None, ErrorCode | None]:
    value = str(target or "").strip()
    code = _standardize_code(value)
    if (
        _A_SHARE_CODE_RE.fullmatch(code)
        or _HK_CODE_RE.fullmatch(code)
        or _US_CODE_RE.fullmatch(code)
    ):
        return code, None
    if _BARE_CODE_RE.fullmatch(value):
        return code, None

    if not value:
        return None, ErrorCode.STOCK_NOT_FOUND

    code, error_code = _resolve_name_from_local(value)
    if error_code != ErrorCode.STOCK_NOT_FOUND:
        return code, error_code

    return None, ErrorCode.STOCK_NOT_FOUND


def refresh_stock_symbols(rows: list[dict[str, str]], source: str = "") -> int:
    updated_at = datetime.now(UTC).replace(tzinfo=None).isoformat()
    normalized_rows = []
    for row in rows:
        code = _standardize_code(row.get("code", ""))
        name = str(row.get("name", "")).strip()
        market = _infer_market(code, row.get("market", ""))
        row_source = str(row.get("source") or source or "").strip()
        ts_code = str(row.get("ts_code", "") or "").strip() or None
        if not code or not name or not market:
            continue
        normalized_rows.append(
            {
                "code": code,
                "name": name,
                "market": market,
                "ts_code": ts_code,
                "source": row_source,
                "updated_at": updated_at,
            }
        )

    if not normalized_rows:
        return 0

    with connect() as conn:
        upsert_stock_symbols(conn, normalized_rows)
    return len(normalized_rows)


def list_stock_symbols(name: str = "", limit: int = 20) -> list[dict[str, str]]:
    limit_value = max(1, min(int(limit or 20), 200))
    table = investment_stock_symbols
    stmt = (
        select(table.c.code, table.c.name, table.c.market, table.c.ts_code, table.c.source, table.c.updated_at)
        .order_by(table.c.name, table.c.code)
        .limit(limit_value)
    )
    value = str(name or "").strip()
    if value:
        stmt = stmt.where(table.c.name.like(f"%{value}%"))

    with connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [row_to_dict(row) for row in rows]


def stock_dictionary_stats() -> dict[str, object]:
    table = investment_stock_symbols
    stmt = select(
        func.count().label("total"),
        func.min(table.c.updated_at).label("oldest_updated_at"),
        func.max(table.c.updated_at).label("latest_updated_at"),
        func.count(func.distinct(table.c.source)).label("source_count"),
    )
    with connect() as conn:
        row = conn.execute(stmt).fetchone()
    return row_to_dict(row) if row else {"total": 0, "oldest_updated_at": None, "latest_updated_at": None, "source_count": 0}


def stock_dictionary_stats_with_latest_source() -> dict[str, object]:
    stats = stock_dictionary_stats()
    table = investment_stock_symbols
    latest_updated_at = select(table.c.updated_at).order_by(table.c.updated_at.desc()).limit(1).scalar_subquery()
    stmt = select(table.c.source).where(table.c.updated_at == latest_updated_at).order_by(table.c.source).limit(1)
    with connect() as conn:
        row = conn.execute(stmt).fetchone()
    stats["latest_source"] = row_to_dict(row).get("source", "") if row else ""
    return stats
