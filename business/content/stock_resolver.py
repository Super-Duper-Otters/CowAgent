# encoding:utf-8
import importlib
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select, text

from business.config.constants import ErrorCode
from business.config.config_service import get_config, mask_sensitive_value
from business.market.akshare_process_pool import call_akshare
from business.schema.db import connect, row_to_dict, upsert_stock_symbols
from business.schema.tables import investment_stock_symbols


_A_SHARE_CODE_RE = re.compile(r"\d{6}\.(SZ|SH|BJ)", re.IGNORECASE)
_BARE_CODE_RE = re.compile(r"\d{6}")
_BAOSTOCK_CODE_RE = re.compile(r"(sh|sz|bj)\.(\d{6})", re.IGNORECASE)
_HK_CODE_RE = re.compile(r"\d{5}\.HK", re.IGNORECASE)
_HK_PREFIX_RE = re.compile(r"HK(\d{5})", re.IGNORECASE)
_US_CODE_RE = re.compile(r"[A-Z0-9_.-]+\.US", re.IGNORECASE)
_US_PREFIX_RE = re.compile(r"US:([A-Z0-9_.-]+)", re.IGNORECASE)
_INDEX_PREFIX_RE = re.compile(r"(sh|sz|bj)(\d{6})", re.IGNORECASE)
_MARKET_ALIASES = {
    "SSE": "SH",
    "SHSE": "SH",
    "SZSE": "SZ",
    "BSE": "BJ",
}

_CORE_INDEX_SYMBOLS = [
    {"code": "sh000001", "name": "上证指数", "market": "SH", "asset_type": "index", "source": "akshare_index_core", "ts_code": "000001.SH"},
    {"code": "sz399001", "name": "深证成指", "market": "SZ", "asset_type": "index", "source": "akshare_index_core", "ts_code": "399001.SZ"},
    {"code": "sz399006", "name": "创业板指", "market": "SZ", "asset_type": "index", "source": "akshare_index_core", "ts_code": "399006.SZ"},
    {"code": "sh000300", "name": "沪深300", "market": "CSI", "asset_type": "index", "source": "akshare_index_core", "ts_code": "000300.SH"},
    {"code": "sh000905", "name": "中证500", "market": "CSI", "asset_type": "index", "source": "akshare_index_core", "ts_code": "000905.SH"},
    {"code": "sh000852", "name": "中证1000", "market": "CSI", "asset_type": "index", "source": "akshare_index_core", "ts_code": "000852.SH"},
    {"code": "sh000016", "name": "上证50", "market": "SH", "asset_type": "index", "source": "akshare_index_core", "ts_code": "000016.SH"},
]


def _canonical_market(value: str) -> str:
    market = str(value or "").strip().upper()
    return _MARKET_ALIASES.get(market, market)


def _infer_market_for_bare_code(code: str, asset_type: str = "") -> str:
    asset_type_value = str(asset_type or "").strip().lower()
    if asset_type_value == "convertible_bond":
        if code.startswith("11"):
            return "SH"
        if code.startswith("12"):
            return "SZ"
    if asset_type_value in {"etf", "fund"}:
        return "SZ" if code.startswith(("15", "16", "18")) else "SH"
    if code.startswith(("4", "8")) or code.startswith("920"):
        return "BJ"
    return "SH" if code.startswith("6") else "SZ"


def _standardize_code(value: str, market: str = "", asset_type: str = "") -> str:
    raw_code = str(value or "").strip()
    raw_asset_type = str(asset_type or "").strip().lower()
    index_prefix_match = _INDEX_PREFIX_RE.fullmatch(raw_code)
    if raw_asset_type == "index" and index_prefix_match:
        return f"{index_prefix_match.group(1).lower()}{index_prefix_match.group(2)}"
    code = raw_code.upper()
    market_value = _canonical_market(market)
    if not code:
        return ""
    if raw_asset_type == "index":
        if _A_SHARE_CODE_RE.fullmatch(code):
            bare, suffix = code.split(".", 1)
            return f"{suffix.lower()}{bare}"
        if _BARE_CODE_RE.fullmatch(code):
            market_prefix = "sh" if market_value in {"SH", "SSE", "CSI"} else "sz" if market_value in {"SZ", "SZSE"} else ""
            if market_prefix:
                return f"{market_prefix}{code}"
    baostock_match = _BAOSTOCK_CODE_RE.fullmatch(code)
    if baostock_match:
        exchange = baostock_match.group(1).upper()
        return f"{baostock_match.group(2)}.{exchange}"
    if market_value == "HK" and re.fullmatch(r"\d{1,5}", code):
        return f"{code.zfill(5)}.HK"
    if market_value == "US" and "." not in code:
        return f"{code}.US"
    if str(asset_type or "").strip().lower() == "futures" and market_value in {"SHFE", "DCE", "CZCE", "CFFEX", "GFEX", "INE"}:
        return code
    if market_value and "." not in code and market_value not in {"SH", "SZ", "BJ"}:
        return f"{code}.{market_value}"
    if _A_SHARE_CODE_RE.fullmatch(code):
        return code
    if market_value in {"SH", "SZ", "BJ"} and _BARE_CODE_RE.fullmatch(code):
        return f"{code}.{market_value}"
    if _BARE_CODE_RE.fullmatch(code):
        return f"{code}.{_infer_market_for_bare_code(code, asset_type)}"
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


def _infer_market(code: str, row_market: str = "", asset_type: str = "") -> str:
    if str(asset_type or "").strip().lower() == "index":
        market = _canonical_market(row_market)
        if market:
            return market
        index_match = _INDEX_PREFIX_RE.fullmatch(code)
        if index_match:
            return index_match.group(1).upper()
    if "." in code:
        suffix = code.rsplit(".", 1)[1].upper()
        if suffix in {"SH", "SZ", "BJ", "HK", "US"}:
            return suffix
    market = _canonical_market(row_market)
    if market:
        return market
    if "." in code:
        return code.rsplit(".", 1)[1].upper()
    return _infer_market_for_bare_code(code, asset_type)


def _infer_asset_type(code: str, market: str = "", row_asset_type: str = "") -> str:
    asset_type = str(row_asset_type or "").strip().lower()
    if asset_type:
        return asset_type
    market_value = str(market or "").strip().upper()
    if _INDEX_PREFIX_RE.fullmatch(str(code or "")):
        return "index"
    if market_value == "HK":
        return "hk_stock"
    if market_value == "US":
        return "us_stock"
    if market_value in {"SGE", "COMEX"}:
        return "gold"
    if market_value in {"SHFE", "DCE", "CZCE", "CFFEX", "GFEX", "INE"}:
        return "futures"
    return "a_share"


def _tushare_client():
    token = get_tushare_token()
    if not token:
        raise RuntimeError("tushare token not configured")
    tushare = importlib.import_module("tushare")
    return tushare.pro_api(token)


class _AkShareProcessClient:
    def __getattr__(self, function_name: str):
        def _call(*args: Any, **kwargs: Any) -> Any:
            return call_akshare(function_name, *args, **kwargs)

        return _call


def _akshare_client():
    return _AkShareProcessClient()


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


def _normalize_symbol_records(rows: list[dict[str, Any]], require_name: bool = True) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        raw_market = _first_text(row, ("market", "exchange", "交易所"))
        raw_code = _first_text(row, ("code", "ts_code", "symbol", "证券代码", "代码"))
        raw_asset_type = _first_text(row, ("asset_type",))
        code = _standardize_code(raw_code, raw_market, raw_asset_type)
        market = _infer_market(code, raw_market, raw_asset_type)
        name = _first_text(row, ("name", "code_name", "名称", "证券简称", "品种名称", "中文名称"))
        asset_type = _infer_asset_type(code, market, raw_asset_type)
        source = _first_text(row, ("source",))
        ts_code = _first_text(row, ("ts_code",)) or code
        if not code or (require_name and not name) or not market or not asset_type or not source:
            continue
        normalized.append(
            {
                "code": code,
                "name": name,
                "market": market,
                "asset_type": asset_type,
                "ts_code": ts_code,
                "source": source,
            }
        )
    return normalized


def normalize_symbol_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _normalize_symbol_records(rows, require_name=True)


def _source_priority(source: str) -> int:
    source_value = str(source or "").strip().lower()
    if source_value.startswith("tushare"):
        return 100
    if source_value.startswith("baostock"):
        return 80
    if source_value.startswith("akshare"):
        return 60
    return 10


def merge_symbol_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    priorities: dict[str, int] = {}
    for row in _normalize_symbol_records(rows, require_name=False):
        code = row["code"]
        priority = _source_priority(row.get("source", ""))
        current = merged.get(code)
        if current is None:
            merged[code] = dict(row)
            priorities[code] = priority
            continue

        if priority > priorities[code]:
            replacement = dict(row)
            if not replacement.get("name") and current.get("name"):
                replacement["name"] = current["name"]
            merged[code] = replacement
            priorities[code] = priority
        elif not current.get("name") and row.get("name"):
            current["name"] = row["name"]

    return sorted(
        merged.values(),
        key=lambda row: (
            str(row.get("asset_type", "")),
            str(row.get("market", "")),
            str(row.get("code", "")),
        ),
    )


def _trusted_dictionary_source_condition(table):
    return table.c.source.like("tushare%") | table.c.source.like("akshare%") | table.c.source.like("baostock%")


def _resolve_name_from_local(value: str) -> tuple[str | None, ErrorCode | None]:
    table = investment_stock_symbols
    stmt = (
        select(table.c.code)
        .where(table.c.name == value, _trusted_dictionary_source_condition(table))
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
        select(table.c.code, table.c.name, table.c.market, table.c.ts_code, table.c.asset_type, table.c.source)
        .where(table.c.name == str(value or "").strip(), _trusted_dictionary_source_condition(table))
        .order_by(table.c.code)
        .limit(limit_value)
    )
    with connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [row_to_dict(row) for row in rows]


def get_stock_symbol_by_code(value: str) -> dict[str, str]:
    raw_value = str(value or "").strip()
    code = _standardize_code(raw_value)
    candidates = [code] if code else []
    index_match = _INDEX_PREFIX_RE.fullmatch(raw_value)
    if index_match:
        candidates.insert(0, f"{index_match.group(1).lower()}{index_match.group(2)}")
    if not candidates:
        return {}
    table = investment_stock_symbols
    stmt = (
        select(table.c.code, table.c.name, table.c.market, table.c.ts_code, table.c.asset_type, table.c.source)
        .where(table.c.code.in_(dict.fromkeys(candidates)), _trusted_dictionary_source_condition(table))
        .order_by(table.c.source)
        .limit(1)
    )
    with connect() as conn:
        row = conn.execute(stmt).fetchone()
    return row_to_dict(row) if row else {}


def list_index_symbol_matches_for_bare_code(value: str, limit: int = 3) -> list[dict[str, str]]:
    bare_code = str(value or "").strip()
    if not _BARE_CODE_RE.fullmatch(bare_code):
        return []
    candidates = [f"sh{bare_code}", f"sz{bare_code}", f"bj{bare_code}"]
    table = investment_stock_symbols
    stmt = (
        select(table.c.code, table.c.name, table.c.market, table.c.ts_code, table.c.asset_type, table.c.source)
        .where(
            table.c.code.in_(candidates),
            table.c.asset_type == "index",
            _trusted_dictionary_source_condition(table),
        )
    )
    with connect() as conn:
        rows = conn.execute(stmt).fetchall()
    by_code = {str(row_to_dict(row).get("code") or ""): row_to_dict(row) for row in rows}
    return [by_code[code] for code in candidates if code in by_code][: max(1, min(int(limit or 3), 10))]


def list_bare_code_symbol_matches(value: str, limit: int = 10) -> list[dict[str, str]]:
    bare_code = str(value or "").strip()
    if not _BARE_CODE_RE.fullmatch(bare_code):
        return []
    candidates = [
        f"{bare_code}.SH",
        f"{bare_code}.SZ",
        f"{bare_code}.BJ",
        f"sh{bare_code}",
        f"sz{bare_code}",
        f"bj{bare_code}",
        f"{bare_code}.CSI",
    ]
    table = investment_stock_symbols
    stmt = (
        select(table.c.code, table.c.name, table.c.market, table.c.ts_code, table.c.asset_type, table.c.source)
        .where(
            table.c.code.in_(candidates),
            _trusted_dictionary_source_condition(table),
        )
    )
    with connect() as conn:
        rows = conn.execute(stmt).fetchall()
    by_code = {str(row_to_dict(row).get("code") or ""): row_to_dict(row) for row in rows}
    ordered = [by_code[code] for code in candidates if code in by_code]
    return ordered[: max(1, min(int(limit or 10), 50))]


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
                "asset_type": "a_share",
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
                "asset_type": "hk_stock",
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
                "asset_type": "us_stock",
                "name": name,
                "ts_code": ts_code or None,
                "source": "tushare_us",
            }
        )
    return refresh_stock_symbols(rows, source="tushare_us")


def refresh_index_symbols_from_tushare() -> int:
    pro = _tushare_client()
    rows = []
    for market in ("SSE", "SZSE", "CSI"):
        frame = pro.index_basic(market=market, fields="ts_code,name,market,publisher,category")
        for row in _records_from_frame(frame):
            ts_code = _first_text(row, ("ts_code", "code"))
            name = _first_text(row, ("name", "名称"))
            if not ts_code or not name:
                continue
            rows.append(
                {
                    "code": _standardize_code(ts_code, market, "index"),
                    "market": market,
                    "asset_type": "index",
                    "name": name,
                    "ts_code": ts_code,
                    "source": "tushare_index",
                }
            )
    return refresh_stock_symbols(rows, source="tushare_index")


def refresh_all_symbols_from_tushare() -> dict[str, object]:
    result: dict[str, object] = {}
    for market_key, refresher in (
        ("a_share", refresh_a_share_symbols_from_tushare),
        ("hk", refresh_hk_symbols_from_tushare),
        ("us", refresh_us_symbols_from_tushare),
        ("index", refresh_index_symbols_from_tushare),
    ):
        try:
            result[market_key] = {"count": refresher()}
        except Exception as exc:  # noqa: BLE001 - each Tushare market refresh is reported independently.
            result[market_key] = {"error": str(exc)}
    return result


def _refresh_akshare_frame(frame: Any, source: str, market: str, asset_type: str) -> int:
    rows = []
    for row in _records_from_frame(frame):
        item = dict(row)
        item["source"] = source
        item["market"] = market
        item["asset_type"] = asset_type
        rows.append(item)
    return refresh_stock_symbols(merge_symbol_records(rows), source=source)


def refresh_a_share_symbols_from_akshare() -> int:
    akshare = _akshare_client()
    return _refresh_akshare_frame(akshare.stock_zh_a_spot_em(), "akshare_a", "", "a_share")


def refresh_hk_symbols_from_akshare() -> int:
    akshare = _akshare_client()
    return _refresh_akshare_frame(akshare.stock_hk_spot_em(), "akshare_hk", "HK", "hk_stock")


def refresh_us_symbols_from_akshare() -> int:
    akshare = _akshare_client()
    return _refresh_akshare_frame(akshare.stock_us_spot_em(), "akshare_us", "US", "us_stock")


def refresh_etf_symbols_from_akshare() -> int:
    akshare = _akshare_client()
    return _refresh_akshare_frame(akshare.fund_etf_spot_em(), "akshare_etf", "", "etf")


def refresh_convertible_bond_symbols_from_akshare() -> int:
    akshare = _akshare_client()
    return _refresh_akshare_frame(
        akshare.bond_zh_hs_cov_spot(),
        "akshare_convertible_bond",
        "",
        "convertible_bond",
    )


def refresh_gold_symbols_from_akshare() -> int:
    akshare = _akshare_client()
    return _refresh_akshare_frame(akshare.spot_quotations_sge(), "akshare_gold", "SGE", "gold")


def _index_market_from_akshare_code(code: str) -> str:
    match = _INDEX_PREFIX_RE.fullmatch(str(code or "").strip())
    if not match:
        return ""
    prefix = match.group(1).lower()
    if prefix == "sh":
        return "SH"
    if prefix == "sz":
        return "SZ"
    if prefix == "bj":
        return "BJ"
    return ""


def refresh_index_symbols_from_akshare() -> int:
    rows = [dict(row) for row in _CORE_INDEX_SYMBOLS]
    akshare = _akshare_client()
    for category, market in (("上证系列指数", "SH"), ("深证系列指数", "SZ"), ("中证系列指数", "CSI")):
        try:
            frame = akshare.stock_zh_index_spot_em(symbol=category)
        except Exception:  # noqa: BLE001 - core index fallback keeps common names available.
            continue
        for row in _records_from_frame(frame):
            raw_code = _first_text(row, ("代码", "code", "symbol"))
            name = _first_text(row, ("名称", "name", "指数名称"))
            if not raw_code or not name:
                continue
            code = _standardize_code(raw_code, market, "index")
            rows.append(
                {
                    "code": code,
                    "market": market or _index_market_from_akshare_code(code),
                    "asset_type": "index",
                    "name": name,
                    "ts_code": code,
                    "source": "akshare_index",
                }
            )
    return refresh_stock_symbols(merge_symbol_records(rows), source="akshare_index")


def refresh_bond_futures_symbols_from_akshare() -> int:
    rows = [
        {"code": "T0", "name": "10年期国债期货主力连续", "market": "CFFEX", "asset_type": "futures", "source": "akshare_futures", "ts_code": "T0"},
        {"code": "TF0", "name": "5年期国债期货主力连续", "market": "CFFEX", "asset_type": "futures", "source": "akshare_futures", "ts_code": "TF0"},
        {"code": "TS0", "name": "2年期国债期货主力连续", "market": "CFFEX", "asset_type": "futures", "source": "akshare_futures", "ts_code": "TS0"},
        {"code": "TL0", "name": "30年期国债期货主力连续", "market": "CFFEX", "asset_type": "futures", "source": "akshare_futures", "ts_code": "TL0"},
    ]
    return refresh_stock_symbols(rows, source="akshare_futures")


def refresh_all_symbols_from_akshare() -> dict[str, object]:
    result: dict[str, object] = {}
    for market_key, refresher in (
        ("a_share", refresh_a_share_symbols_from_akshare),
        ("hk", refresh_hk_symbols_from_akshare),
        ("us", refresh_us_symbols_from_akshare),
        ("etf", refresh_etf_symbols_from_akshare),
        ("convertible_bond", refresh_convertible_bond_symbols_from_akshare),
        ("gold", refresh_gold_symbols_from_akshare),
        ("index", refresh_index_symbols_from_akshare),
        ("futures", refresh_bond_futures_symbols_from_akshare),
    ):
        try:
            result[market_key] = {"count": refresher()}
        except Exception as exc:  # noqa: BLE001 - each AkShare category refresh is reported independently.
            result[market_key] = {"error": str(exc)}
    return result


def _baostock_result_to_records(result: Any) -> list[dict[str, Any]]:
    if result.error_code != "0":
        raise RuntimeError(result.error_msg)
    rows = []
    while result.next():
        rows.append(dict(zip(result.fields, result.get_row_data(), strict=False)))
    return rows


def refresh_a_share_symbols_from_baostock() -> int:
    baostock = importlib.import_module("baostock")
    login_result = baostock.login()
    if login_result.error_code != "0":
        raise RuntimeError(login_result.error_msg)
    try:
        records = []
        for row in _baostock_result_to_records(baostock.query_stock_basic()):
            status = str(row.get("status", "") or "").strip()
            stock_type = str(row.get("type", "") or "").strip()
            if status and status != "1":
                continue
            if stock_type and stock_type != "1":
                continue
            records.append(
                {
                    "code": row.get("code", ""),
                    "name": row.get("code_name", ""),
                    "market": "",
                    "asset_type": "a_share",
                    "source": "baostock_a",
                    "ts_code": row.get("code", ""),
                }
            )
        return refresh_stock_symbols(merge_symbol_records(records), source="baostock_a")
    finally:
        baostock.logout()


def refresh_all_symbols_from_baostock() -> dict[str, object]:
    try:
        return {"a_share": {"count": refresh_a_share_symbols_from_baostock()}}
    except Exception as exc:  # noqa: BLE001 - Baostock adapter errors are reported in the refresh payload.
        return {"a_share": {"error": str(exc)}}


def refresh_all_symbol_sources() -> dict[str, object]:
    result: dict[str, object] = {}
    for provider, refresher in (
        ("tushare", refresh_all_symbols_from_tushare),
        ("akshare", refresh_all_symbols_from_akshare),
        ("baostock", refresh_all_symbols_from_baostock),
    ):
        try:
            result[provider] = refresher()
        except Exception as exc:  # noqa: BLE001 - provider failures should not stop other dictionary refreshes.
            result[provider] = {"error": str(exc)}
    return result


def resolve_stock(target: str, auto_refresh_on_miss: bool = True) -> tuple[str | None, ErrorCode | None]:
    value = str(target or "").strip()
    index_match = _INDEX_PREFIX_RE.fullmatch(value)
    if index_match:
        return f"{index_match.group(1).lower()}{index_match.group(2)}", None
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


def deduplicate_stock_symbol_codes(conn) -> int:
    result = conn.execute(
        text(
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
    )
    return int(getattr(result, "rowcount", 0) or 0)


def refresh_stock_symbols(rows: list[dict[str, str]], source: str = "") -> int:
    updated_at = datetime.now(UTC).replace(tzinfo=None).isoformat()
    normalized_rows = []
    for row in rows:
        code = _standardize_code(row.get("code", ""), row.get("market", ""), row.get("asset_type", ""))
        name = str(row.get("name", "")).strip()
        market = _infer_market(code, row.get("market", ""), row.get("asset_type", ""))
        asset_type = _infer_asset_type(code, market, row.get("asset_type", ""))
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
                "asset_type": asset_type,
                "source": row_source,
                "updated_at": updated_at,
            }
        )

    if not normalized_rows:
        return 0

    with connect() as conn:
        deduplicate_stock_symbol_codes(conn)
        return upsert_stock_symbols(conn, normalized_rows)


def list_stock_symbols(name: str = "", limit: int = 20) -> list[dict[str, str]]:
    limit_value = max(1, min(int(limit or 20), 200))
    table = investment_stock_symbols
    stmt = (
        select(table.c.code, table.c.name, table.c.market, table.c.ts_code, table.c.asset_type, table.c.source, table.c.updated_at)
        .order_by(table.c.name, table.c.code)
        .limit(limit_value)
    )
    value = str(name or "").strip()
    if value:
        pattern = f"%{value}%"
        stmt = stmt.where(or_(table.c.name.like(pattern), table.c.code.like(pattern), table.c.ts_code.like(pattern)))

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
