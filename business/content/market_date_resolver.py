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
        for source_name, loader in (("tushare", self._latest_from_tushare), ("akshare", self._latest_from_akshare)):
            try:
                market_date = loader(symbol)
            except Exception:  # noqa: BLE001 - optional market data providers must not break analysis flow.
                market_date = ""
            if market_date:
                return MarketDateResolution(market_date=market_date, known=True, source=source_name)
        return MarketDateResolution()

    def _latest_from_tushare(self, symbol: str) -> str:
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
        bare_symbol = symbol.split(".", 1)[0]
        frame = akshare.stock_zh_a_hist(symbol=bare_symbol, period="daily", adjust="")
        return _latest_date_from_records(_records_from_frame(frame), ("日期", "date", "trade_date"))


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
