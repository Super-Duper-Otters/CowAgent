# encoding:utf-8
import importlib
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from business.content.stock_resolver import get_tushare_token


@dataclass(frozen=True)
class MarketDateResolution:
    market_date: str = ""
    known: bool = False
    source: str = "unknown"


class MarketDateResolver:
    def resolve(self, symbol: str, requested_market_date: str = "") -> MarketDateResolution:
        requested_text = str(requested_market_date or "").strip()
        explicit_date = normalize_market_date(requested_text)
        if explicit_date:
            return MarketDateResolution(market_date=explicit_date, known=True, source="explicit")
        if requested_text:
            return MarketDateResolution()
        return self._latest_market_date(symbol)

    def _latest_market_date(self, symbol: str) -> MarketDateResolution:
        source_loaders = [("akshare", self._latest_from_akshare)]
        if _asset_type_from_symbol(symbol) == "a_share":
            source_loaders.append(("tushare", self._latest_from_tushare))
        for source_name, loader in source_loaders:
            try:
                market_date = loader(symbol)
            except Exception:  # noqa: BLE001 - optional market data providers must not break analysis flow.
                market_date = ""
            if market_date:
                return MarketDateResolution(market_date=market_date, known=True, source=source_name)
        return MarketDateResolution()

    def _latest_from_tushare(self, symbol: str) -> str:
        if _asset_type_from_symbol(symbol) != "a_share":
            return ""
        token = get_tushare_token()
        if not token:
            return ""
        tushare = importlib.import_module("tushare")
        end_date = date.today().strftime("%Y%m%d")
        start_date = (date.today() - timedelta(days=30)).strftime("%Y%m%d")
        frame = tushare.pro_api(token).daily(ts_code=symbol.upper(), start_date=start_date, end_date=end_date)
        return _latest_date_from_records(_records_from_frame(frame), ("trade_date", "date", "日期"))

    def _latest_from_akshare(self, symbol: str) -> str:
        akshare = importlib.import_module("akshare")
        asset_type = _asset_type_from_symbol(symbol)
        if asset_type == "index":
            frame = akshare.stock_zh_index_daily(symbol=_prefixed_cn_symbol(symbol).lower())
        elif asset_type == "etf":
            frame = akshare.fund_etf_hist_sina(symbol=_prefixed_cn_symbol(symbol).lower())
        elif asset_type == "convertible_bond":
            frame = akshare.bond_zh_hs_cov_daily(symbol=_prefixed_cn_symbol(symbol).lower())
        elif asset_type == "futures":
            frame = akshare.futures_zh_daily_sina(symbol=str(symbol or "").strip().upper())
        elif asset_type == "hk_stock":
            frame = akshare.stock_hk_daily(symbol=_bare_symbol(symbol).zfill(5))
        elif asset_type == "us_stock":
            frame = akshare.stock_us_daily(symbol=_bare_symbol(symbol).upper())
        else:
            frame = akshare.stock_zh_a_hist(symbol=_bare_symbol(symbol), period="daily", adjust="")
        return _latest_date_from_records(_records_from_frame(frame), ("日期", "date", "trade_date"))


def _bare_symbol(symbol: str) -> str:
    text = str(symbol or "").strip()
    if text.upper().startswith("HK") and text[2:].isdigit():
        return text[2:]
    if "." in text:
        return text.split(".", 1)[0]
    return re.sub(r"^(sh|sz|bj)", "", text, flags=re.IGNORECASE)


def _prefixed_cn_symbol(symbol: str) -> str:
    text = str(symbol or "").strip()
    if re.fullmatch(r"(sh|sz|bj)\d{6}", text, flags=re.IGNORECASE):
        return text
    bare = _bare_symbol(text)
    upper = text.upper()
    if upper.endswith(".SZ") or bare.startswith(("12", "15")):
        return f"sz{bare}"
    return f"sh{bare}"


def _asset_type_from_symbol(symbol: str) -> str:
    text = str(symbol or "").strip()
    upper = text.upper()
    lower = text.lower()
    bare = _bare_symbol(text)
    if re.fullmatch(r"(sh|sz|bj)\d{6}", lower):
        return "index"
    if upper.endswith(".HK") or re.fullmatch(r"HK\d{5}", upper):
        return "hk_stock"
    if upper.endswith(".US"):
        return "us_stock"
    if upper in {"T0", "TL0", "TF0", "TS0", "T", "TL", "TF", "TS"}:
        return "futures"
    if bare.startswith(("11", "12")) and len(bare) == 6:
        return "convertible_bond"
    if bare.startswith(("51", "15")) and len(bare) == 6:
        return "etf"
    return "a_share" if len(bare) == 6 and bare.isdigit() else ""


def _records_from_frame(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        return [dict(row) for row in frame.to_dict("records")]
    return [dict(row) for row in frame]


def _latest_date_from_records(records: list[dict[str, Any]], keys: tuple[str, ...]) -> str:
    dates = []
    for row in records:
        for key in keys:
            market_date = _normalize_date(row.get(key))
            if market_date:
                dates.append(market_date)
                break
    return max(dates) if dates else ""


def normalize_market_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"(\d{4})[-/]?(\d{2})[-/]?(\d{2})", text)
    if not match:
        return ""
    normalized = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    try:
        date.fromisoformat(normalized)
    except ValueError:
        return ""
    return normalized


_normalize_date = normalize_market_date
