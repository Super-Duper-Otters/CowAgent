# encoding:utf-8
import importlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from business.config.config_service import get_config
from business.market.akshare_process_pool import call_akshare


TRADING_CALENDAR_ENABLED_KEY = "investment.trading_calendar.enabled"
TRADING_CALENDAR_SOURCES_KEY = "investment.trading_calendar.sources"
TRADING_CALENDAR_REFRESH_TIME_KEY = "investment.trading_calendar.refresh_time"
TRADING_CALENDAR_MARKET_DATA_READY_TIME_KEY = "investment.trading_calendar.market_data_ready_time"
TRADING_CALENDAR_CACHE_DAYS_KEY = "investment.trading_calendar.cache_days"
TRADING_CALENDAR_MAX_LAG_KEY = "investment.trading_calendar.max_lag_trade_days"
TRADING_CALENDAR_MAX_STALE_DAYS_KEY = "investment.trading_calendar.max_stale_market_days"
MAINLAND_TRADING_CALENDAR_ASSET_TYPES = {"a_share", "index", "etf", "convertible_bond", "futures"}


@dataclass(frozen=True)
class TradingCalendar:
    enabled: bool = True
    refresh_time: str = "06:00"
    market_data_ready_time: str = "15:30"
    cache_days: int = 7
    max_lag_trade_days: int = 0
    max_stale_market_days: int = 15
    source_order: tuple[str, ...] = ("baostock", "tushare", "akshare")
    cache_path: Path | None = None

    def expected_market_date(self, *, today: date | None = None, now: datetime | None = None) -> str:
        trade_dates = self._trade_dates(today=today, now=now)
        if not trade_dates:
            return ""
        if now is not None:
            current_dt = now
        else:
            current_day = today or date.today()
            current_dt = datetime.combine(current_day, time.max)
        current = today or current_dt.date()
        current_text = current.isoformat()
        if current_text in trade_dates and current_dt.time() >= _parse_time(self.market_data_ready_time):
            return current_text
        previous = [item for item in trade_dates if item < current_text]
        return previous[-1] if previous else ""

    def accept_market_date(
        self,
        market_date: str,
        *,
        today: date | None = None,
        now: datetime | None = None,
        asset_type: str = "",
    ) -> bool:
        if not self.enabled:
            return True
        if not self.applies_to_asset_type(asset_type):
            return True
        normalized = _normalize_date(market_date)
        if not normalized:
            return False
        accepted_dates = self.accepted_market_dates(today=today, now=now)
        if not accepted_dates:
            return True
        return normalized in set(accepted_dates)

    def accept_stale_market_date(
        self,
        market_date: str,
        *,
        today: date | None = None,
        now: datetime | None = None,
        asset_type: str = "",
    ) -> bool:
        if not self.applies_to_asset_type(asset_type):
            return True
        normalized = _normalize_date(market_date)
        if not normalized:
            return False
        expected = self.expected_market_date(today=today, now=now)
        reference_text = expected or (today or (now.date() if now is not None else date.today())).isoformat()
        try:
            market_day = date.fromisoformat(normalized)
            reference_day = date.fromisoformat(reference_text)
        except ValueError:
            return False
        age_days = (reference_day - market_day).days
        return 0 <= age_days <= max(0, int(self.max_stale_market_days))

    def accepted_market_dates(self, *, today: date | None = None, now: datetime | None = None) -> list[str]:
        if not self.enabled:
            return []
        trade_dates = self._trade_dates(today=today, now=now)
        if not trade_dates:
            return []
        expected = self.expected_market_date(today=today, now=now)
        if not expected or expected not in trade_dates:
            return []
        expected_index = trade_dates.index(expected)
        accepted_from = max(0, expected_index - max(0, int(self.max_lag_trade_days)))
        return trade_dates[accepted_from : expected_index + 1]

    def applies_to_asset_type(self, asset_type: str) -> bool:
        if not str(asset_type or "").strip():
            return True
        return str(asset_type or "").strip().lower() in MAINLAND_TRADING_CALENDAR_ASSET_TYPES

    def is_trading_day(
        self,
        *,
        today: date | None = None,
        now: datetime | None = None,
        asset_type: str = "",
    ) -> bool:
        if not self.enabled:
            return True
        if not self.applies_to_asset_type(asset_type):
            return True
        current = today or (now.date() if now is not None else date.today())
        trade_dates = self._trade_dates(today=today, now=now)
        if not trade_dates:
            return True
        return current.isoformat() in set(trade_dates)

    def refresh(self, *, today: date | None = None, now: datetime | None = None) -> dict[str, Any]:
        current = today or (now.date() if now is not None else date.today())
        start = date(current.year, 1, 1)
        # Include the previous year tail so early-January runs can still find
        # the previous trading day without a second provider call.
        start = start - timedelta(days=14)
        trade_dates = _load_calendar_from_sources(start, current, self.source_order)
        payload = {
            "trade_dates": sorted(set(trade_dates)),
            "source_order": list(self.source_order),
            "refreshed_at": datetime.now().isoformat(timespec="seconds"),
        }
        path = self._cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def status(self, *, today: date | None = None, now: datetime | None = None) -> dict[str, Any]:
        current = now or datetime.now()
        payload = self._read_cache()
        trade_dates = self._trade_dates(today=today, now=now)
        payload = self._read_cache()
        expected = self.expected_market_date(today=today, now=now)
        refreshed_at = str(payload.get("refreshed_at") or "")
        stale = self._should_refresh(payload, now=current)
        if not self.enabled:
            state = "disabled"
            message = "交易日历未启用"
        elif not trade_dates:
            state = "missing"
            message = "本地交易日历未构建"
        elif stale:
            state = "stale"
            message = "本地交易日历需要刷新"
        elif not expected:
            state = "unknown"
            message = "无法判断预期最新交易日"
        else:
            state = "ok"
            message = "交易日历正常"
        return {
            "enabled": self.enabled,
            "state": state,
            "message": message,
            "system_date": (today or current.date()).isoformat(),
            "expected_market_date": expected,
            "max_lag_trade_days": max(0, int(self.max_lag_trade_days)),
            "max_stale_market_days": max(0, int(self.max_stale_market_days)),
            "cache_exists": bool(payload.get("trade_dates")),
            "cache_stale": stale,
            "cache_path": str(self._cache_path()),
            "refreshed_at": refreshed_at,
            "trade_dates_count": len(trade_dates),
            "source_order": list(self.source_order),
            "refresh_time": self.refresh_time,
            "market_data_ready_time": self.market_data_ready_time,
            "cache_days": self.cache_days,
        }

    def _trade_dates(self, *, today: date | None = None, now: datetime | None = None) -> list[str]:
        payload = self._read_cache()
        if self._should_refresh(payload, now=now):
            try:
                payload = self.refresh(today=today, now=now)
            except Exception:
                if not payload:
                    return []
        dates = payload.get("trade_dates") if isinstance(payload, dict) else []
        return sorted(_normalize_date(item) for item in dates if _normalize_date(item))

    def _should_refresh(self, payload: dict[str, Any], *, now: datetime | None = None) -> bool:
        if not payload.get("trade_dates"):
            return True
        current = _naive_datetime(now or datetime.now())
        refreshed = _parse_datetime(payload.get("refreshed_at"))
        if refreshed is None:
            return True
        refreshed = _naive_datetime(refreshed)
        if current - refreshed > timedelta(days=max(1, int(self.cache_days))):
            return True
        refresh_at = _parse_time(self.refresh_time)
        if current.time() >= refresh_at and refreshed.date() < current.date():
            return True
        return False

    def _read_cache(self) -> dict[str, Any]:
        path = self._cache_path()
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _cache_path(self) -> Path:
        if self.cache_path is not None:
            return self.cache_path
        return Path("business_storage") / "tmp" / "trading_calendar.json"


def trading_calendar_from_config() -> TradingCalendar:
    sources = str(_safe_config_value(TRADING_CALENDAR_SOURCES_KEY, "baostock,tushare,akshare") or "")
    source_order = tuple(item.strip().lower() for item in sources.split(",") if item.strip())
    return TradingCalendar(
        enabled=_parse_bool(_safe_config_value(TRADING_CALENDAR_ENABLED_KEY, True), True),
        refresh_time=str(_safe_config_value(TRADING_CALENDAR_REFRESH_TIME_KEY, "06:00") or "06:00"),
        market_data_ready_time=str(_safe_config_value(TRADING_CALENDAR_MARKET_DATA_READY_TIME_KEY, "15:30") or "15:30"),
        cache_days=int(_safe_config_value(TRADING_CALENDAR_CACHE_DAYS_KEY, 7) or 7),
        max_lag_trade_days=int(_safe_config_value(TRADING_CALENDAR_MAX_LAG_KEY, 0) or 0),
        max_stale_market_days=int(_safe_config_value(TRADING_CALENDAR_MAX_STALE_DAYS_KEY, 15) or 15),
        source_order=source_order or ("baostock", "tushare", "akshare"),
    )


def refresh_trading_calendar_from_config() -> dict[str, Any]:
    return trading_calendar_from_config().refresh()


def trading_calendar_status_from_config() -> dict[str, Any]:
    return trading_calendar_from_config().status()


def _load_calendar_from_sources(start: date, end: date, source_order: tuple[str, ...]) -> list[str]:
    for source in source_order:
        try:
            if source == "baostock":
                dates = _load_baostock_calendar(start, end)
            elif source == "tushare":
                dates = _load_tushare_calendar(start, end)
            elif source == "akshare":
                dates = _load_akshare_calendar(start, end)
            else:
                dates = []
        except Exception:
            dates = []
        if dates:
            return dates
    return []


def _safe_config_value(key: str, default):
    try:
        return get_config(key, default)
    except Exception:
        return default


def _parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _load_baostock_calendar(start: date, end: date) -> list[str]:
    baostock = importlib.import_module("baostock")
    login_result = baostock.login()
    if getattr(login_result, "error_code", "0") not in ("0", 0, ""):
        return []
    try:
        result = baostock.query_trade_dates(start_date=start.isoformat(), end_date=end.isoformat())
        fields = list(getattr(result, "fields", []) or [])
        rows = []
        while getattr(result, "error_code", "0") in ("0", 0, "") and result.next():
            rows.append(dict(zip(fields, result.get_row_data())))
        return [
            _normalize_date(row.get("calendar_date") or row.get("date"))
            for row in rows
            if str(row.get("is_trading_day") or row.get("is_open") or "").strip() in {"1", "true", "True"}
        ]
    finally:
        try:
            baostock.logout()
        except Exception:
            pass


def _load_tushare_calendar(start: date, end: date) -> list[str]:
    from business.content.stock_resolver import get_tushare_token

    token = get_tushare_token()
    if not token:
        return []
    tushare = importlib.import_module("tushare")
    pro = tushare.pro_api(token)
    frame = pro.trade_cal(
        exchange="",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        is_open="1",
    )
    return _dates_from_frame(frame, ("cal_date", "trade_date", "date"))


def _load_akshare_calendar(start: date, end: date) -> list[str]:
    frame = call_akshare("tool_trade_date_hist_sina")
    dates = _dates_from_frame(frame, ("trade_date", "date", "日期"))
    return [item for item in dates if start.isoformat() <= item <= end.isoformat()]


def _dates_from_frame(frame: Any, keys: tuple[str, ...]) -> list[str]:
    if frame is None:
        return []
    records = frame.to_dict("records") if hasattr(frame, "to_dict") else list(frame)
    dates = []
    for row in records:
        item = dict(row)
        for key in keys:
            normalized = _normalize_date(item.get(key))
            if normalized:
                dates.append(normalized)
                break
    return dates


def _normalize_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 8:
        candidate = f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    else:
        candidate = text[:10]
    try:
        return date.fromisoformat(candidate).isoformat()
    except ValueError:
        return ""


def _parse_datetime(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None


def _naive_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.replace(tzinfo=None)


def _parse_time(value: Any) -> time:
    try:
        hour, minute = str(value or "06:00").split(":", 1)
        return time(int(hour), int(minute[:2]))
    except Exception:
        return time(6, 0)
