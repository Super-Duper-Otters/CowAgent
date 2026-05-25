# encoding:utf-8
import importlib
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from .constants import ErrorCode
from .config_service import get_config, mask_sensitive_value
from .db import connect, row_to_dict, upsert_stock_symbols
from .schema import investment_stock_symbols


_STANDARD_CODE_RE = re.compile(r"\d{6}\.(SZ|SH)", re.IGNORECASE)
_BARE_CODE_RE = re.compile(r"\d{6}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _standardize_code(value: str) -> str:
    code = str(value or "").strip().upper()
    if _STANDARD_CODE_RE.fullmatch(code):
        return code
    if _BARE_CODE_RE.fullmatch(code):
        suffix = ".SH" if code.startswith("6") else ".SZ"
        return f"{code}{suffix}"
    return code


def _infer_market(code: str, row_market: str = "") -> str:
    market = str(row_market or "").strip().upper()
    if market:
        return market
    if "." in code:
        return code.rsplit(".", 1)[1]
    return "SH" if code.startswith("6") else "SZ"


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
    stmt = select(table.c.code).where(table.c.name == value).order_by(table.c.code)
    with connect() as conn:
        rows = conn.execute(stmt).fetchall()

    if len(rows) == 1:
        return row_to_dict(rows[0])["code"], None
    if len(rows) > 1:
        return None, ErrorCode.STOCK_AMBIGUOUS
    return None, ErrorCode.STOCK_NOT_FOUND


def refresh_from_akshare() -> int:
    akshare = importlib.import_module("akshare")
    frame = akshare.stock_info_a_code_name()
    rows = []
    for row in _records_from_frame(frame):
        rows.append(
            {
                "code": _first_text(row, ("code", "代码")),
                "name": _first_text(row, ("name", "名称")),
                "source": "akshare",
            }
        )
    return refresh_stock_symbols(rows, source="akshare")


def get_tushare_token(masked: bool = False) -> str:
    token = str(get_config("tushare.token", "") or "").strip()
    if not token:
        token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        token_file = Path.home() / ".tushare_token"
        if token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
    return mask_sensitive_value(token) if masked else token


def refresh_from_tushare() -> int:
    token = get_tushare_token()
    if not token:
        raise RuntimeError("tushare token not configured")

    tushare = importlib.import_module("tushare")
    pro = tushare.pro_api(token)
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
                "source": "tushare",
            }
        )
    return refresh_stock_symbols(rows, source="tushare")


def refresh_from_auto() -> dict[str, object]:
    result: dict[str, object] = {}
    try:
        result["akshare"] = {"count": refresh_from_akshare()}
    except Exception as exc:  # noqa: BLE001 - report provider failure without touching old dictionary rows.
        result["akshare"] = {"error": str(exc)}

    if get_tushare_token():
        try:
            result["tushare"] = {"count": refresh_from_tushare()}
        except Exception as exc:  # noqa: BLE001 - keep sources isolated during manual refresh.
            result["tushare"] = {"error": str(exc)}
    return result


def resolve_stock(target: str, auto_refresh_on_miss: bool = True) -> tuple[str | None, ErrorCode | None]:
    value = str(target or "").strip()
    if _STANDARD_CODE_RE.fullmatch(value):
        return value.upper(), None
    if _BARE_CODE_RE.fullmatch(value):
        return _standardize_code(value), None

    if not value:
        return None, ErrorCode.STOCK_NOT_FOUND

    code, error_code = _resolve_name_from_local(value)
    if error_code != ErrorCode.STOCK_NOT_FOUND:
        return code, error_code

    if auto_refresh_on_miss and _CJK_RE.search(value):
        try:
            refresh_from_auto()
        except Exception:  # noqa: BLE001 - keep resolver failures as business-level stock miss.
            return None, ErrorCode.STOCK_NOT_FOUND
        return _resolve_name_from_local(value)

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
