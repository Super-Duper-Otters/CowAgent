# encoding:utf-8
import importlib
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from business.config.config_service import get_config
from business.content.stock_resolver import get_tushare_token
from business.market.provider_adapter import (
    classify_asset_target,
    to_akshare_symbol,
    to_baostock_symbol,
    to_tushare_symbol,
)
from business.market.akshare_process_pool import call_akshare
from business.market.trading_calendar import trading_calendar_from_config


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
        target = classify_asset_target(symbol)
        source_loaders = [("akshare", self._latest_from_akshare)]
        if target.asset_type in {"a_share", "index"}:
            source_loaders.append(("tushare", self._latest_from_tushare))
        if target.asset_type in {"a_share", "index", "etf", "convertible_bond"}:
            source_loaders.append(("baostock", self._latest_from_baostock))
        calendar = trading_calendar_from_config()
        source_results = _probe_sources_concurrently(symbol, source_loaders)
        if _ranking_enabled():
            candidates = []
            stale_candidates = []
            for source_name, market_date in source_results:
                if not market_date:
                    continue
                resolution = MarketDateResolution(market_date=market_date, known=True, source=source_name)
                if calendar.accept_market_date(market_date, asset_type=target.asset_type):
                    candidates.append(resolution)
                else:
                    stale_candidates.append(resolution)
            if candidates:
                return max(candidates, key=lambda candidate: candidate.market_date)
            stale_candidates = _filter_stale_candidates_with_calendar(stale_candidates, calendar, asset_type=target.asset_type)
            return max(stale_candidates, key=lambda candidate: candidate.market_date) if stale_candidates else MarketDateResolution()
        stale_candidates = []
        for source_name, market_date in source_results:
            if not market_date:
                continue
            if calendar.accept_market_date(market_date, asset_type=target.asset_type):
                return MarketDateResolution(market_date=market_date, known=True, source=source_name)
            stale_candidates.append(MarketDateResolution(market_date=market_date, known=True, source=source_name))
        stale_candidates = _filter_stale_candidates_with_calendar(stale_candidates, calendar, asset_type=target.asset_type)
        return max(stale_candidates, key=lambda candidate: candidate.market_date) if stale_candidates else MarketDateResolution()

    def _latest_from_tushare(self, symbol: str) -> str:
        target = classify_asset_target(symbol)
        if target.asset_type not in {"a_share", "index"}:
            return ""
        token = get_tushare_token()
        if not token:
            return ""
        tushare = importlib.import_module("tushare")
        end_date = date.today().strftime("%Y%m%d")
        start_date = (date.today() - timedelta(days=30)).strftime("%Y%m%d")
        pro = tushare.pro_api(token)
        ts_code = to_tushare_symbol(target)
        if target.asset_type == "index":
            frame = pro.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        else:
            frame = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        return _latest_date_from_records(_records_from_frame(frame), ("trade_date", "date", "日期"))

    def _latest_from_baostock(self, symbol: str) -> str:
        target = classify_asset_target(symbol)
        baostock_symbol = to_baostock_symbol(target)
        if not baostock_symbol:
            return ""
        baostock = importlib.import_module("baostock")
        login_result = baostock.login()
        if getattr(login_result, "error_code", "0") not in ("0", 0, ""):
            return ""
        try:
            end_date = date.today().isoformat()
            start_date = (date.today() - timedelta(days=30)).isoformat()
            result = baostock.query_history_k_data_plus(
                baostock_symbol,
                "date,open,high,low,close,volume",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="3",
            )
            records = []
            fields = list(getattr(result, "fields", []) or [])
            while getattr(result, "error_code", "0") in ("0", 0, "") and result.next():
                row = result.get_row_data()
                records.append(dict(zip(fields, row)))
            return _latest_date_from_records(records, ("date", "trade_date", "日期"))
        finally:
            try:
                baostock.logout()
            except Exception:  # noqa: BLE001 - optional provider cleanup must not hide resolved dates.
                pass

    def _latest_from_akshare(self, symbol: str) -> str:
        target = classify_asset_target(symbol)
        akshare_symbol = to_akshare_symbol(target)
        timeout = _probe_timeout_seconds()
        if target.asset_type == "index":
            frame = call_akshare("stock_zh_index_daily", symbol=akshare_symbol, timeout=timeout)
        elif target.asset_type == "etf":
            frame = call_akshare("fund_etf_hist_sina", symbol=akshare_symbol, timeout=timeout)
        elif target.asset_type == "convertible_bond":
            frame = call_akshare("bond_zh_hs_cov_daily", symbol=akshare_symbol, timeout=timeout)
        elif target.asset_type == "futures":
            frame = call_akshare("futures_zh_daily_sina", symbol=akshare_symbol, timeout=timeout)
        elif target.asset_type == "hk_stock":
            frame = call_akshare("stock_hk_daily", symbol=akshare_symbol, timeout=timeout)
        elif target.asset_type == "us_stock":
            frame = call_akshare("stock_us_daily", symbol=akshare_symbol, timeout=timeout)
        else:
            frame = call_akshare("stock_zh_a_hist", symbol=akshare_symbol, period="daily", adjust="", timeout=timeout)
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


def _baostock_symbol(symbol: str) -> str:
    text = str(symbol or "").strip()
    if re.fullmatch(r"(sh|sz|bj)\.\d{6}", text, flags=re.IGNORECASE):
        return text.lower()
    bare = _bare_symbol(text)
    upper = text.upper()
    exchange = "sh" if upper.endswith(".SH") or bare.startswith(("5", "6", "9")) else "sz"
    return f"{exchange}.{bare}"


def _ranking_enabled() -> bool:
    try:
        from business.cache.cache_policy import technical_analysis_cache_update_probe_allowed

        return technical_analysis_cache_update_probe_allowed()
    except Exception:
        return False


def _probe_timeout_seconds() -> float:
    try:
        value = float(get_config("investment.technical_analysis.market_date_probe_timeout_seconds", 2.0) or 2.0)
    except Exception:
        value = 2.0
    return max(0.2, min(value, 10.0))


def _probe_sources_concurrently(symbol: str, source_loaders: list[tuple[str, Any]]) -> list[tuple[str, str]]:
    if len(source_loaders) <= 1:
        source_name, loader = source_loaders[0]
        try:
            return [(source_name, str(loader(symbol) or ""))]
        except Exception:  # noqa: BLE001 - optional market data providers must not break analysis flow.
            return [(source_name, "")]

    timeout_seconds = _probe_timeout_seconds()
    started = time.monotonic()
    executor = ThreadPoolExecutor(max_workers=len(source_loaders))
    futures = {
        executor.submit(loader, symbol): source_name
        for source_name, loader in source_loaders
    }
    values: dict[str, str] = {source_name: "" for source_name, _loader in source_loaders}
    try:
        for future in as_completed(futures, timeout=timeout_seconds):
            source_name = futures[future]
            try:
                values[source_name] = str(future.result(timeout=0) or "")
            except Exception:  # noqa: BLE001 - optional market data providers must not break analysis flow.
                values[source_name] = ""
            if time.monotonic() - started >= timeout_seconds:
                break
    except TimeoutError:
        pass
    finally:
        for future in futures:
            if not future.done():
                future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
    return [(source_name, values.get(source_name, "")) for source_name, _loader in source_loaders]


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


def _filter_stale_candidates_with_calendar(
    candidates: list[MarketDateResolution],
    calendar: Any,
    *,
    asset_type: str = "",
) -> list[MarketDateResolution]:
    accept_stale = getattr(calendar, "accept_stale_market_date", None)
    if not callable(accept_stale):
        return candidates
    accepted = []
    for candidate in candidates:
        try:
            keep = accept_stale(candidate.market_date, asset_type=asset_type)
        except TypeError:
            keep = accept_stale(candidate.market_date)
        if keep:
            accepted.append(candidate)
    return accepted


_normalize_date = normalize_market_date
