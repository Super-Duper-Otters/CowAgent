# encoding:utf-8
import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .config_service import get_config
from .market_date_resolver import MarketDateResolver


BEIJING_TZ = ZoneInfo("Asia/Shanghai")
TECHNICAL_ANALYSIS_PROBE_START = time(15, 30)
TECHNICAL_ANALYSIS_AFTER_CLOSE_CUTOFF = time(17, 30)
TECHNICAL_ANALYSIS_CACHE_CLOSE_INVALIDATE_TIME_CONFIG = "investment.technical_analysis.cache_close_invalidate_time"
TECHNICAL_ANALYSIS_CACHE_CLOSE_INVALIDATE_TIME_DEFAULT = "17:30"
MARKET_UPDATE_PROBE_INTERVAL = timedelta(minutes=15)
MARKET_PROBE_SYMBOLS = {
    "a_share": "600519.SH",
    "hk": "00700.HK",
    "us": "AAPL.US",
}
_MARKET_UPDATE_PROBE_CACHE = {}


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ)


def _as_beijing_datetime(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        return value.replace(tzinfo=BEIJING_TZ)
    return value.astimezone(BEIJING_TZ)


def _parse_close_invalidate_time(value) -> time:
    if isinstance(value, time):
        return value
    if not isinstance(value, str):
        return TECHNICAL_ANALYSIS_AFTER_CLOSE_CUTOFF
    match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", value)
    if not match:
        return TECHNICAL_ANALYSIS_AFTER_CLOSE_CUTOFF
    return time(int(match.group(1)), int(match.group(2)))


def _configured_close_invalidate_time() -> time:
    try:
        value = get_config(
            TECHNICAL_ANALYSIS_CACHE_CLOSE_INVALIDATE_TIME_CONFIG,
            TECHNICAL_ANALYSIS_CACHE_CLOSE_INVALIDATE_TIME_DEFAULT,
        )
    except Exception:
        value = TECHNICAL_ANALYSIS_CACHE_CLOSE_INVALIDATE_TIME_DEFAULT
    return _parse_close_invalidate_time(value)


def reset_market_update_probe_cache() -> None:
    _MARKET_UPDATE_PROBE_CACHE.clear()


def market_from_symbol(symbol: str) -> str:
    text = str(symbol or "").strip().upper()
    if text.endswith(".SH") or text.endswith(".SZ"):
        return "a_share"
    if text.endswith(".HK"):
        return "hk"
    if text.endswith(".US"):
        return "us"
    return ""


def _probe_allowed(now: datetime) -> bool:
    return now.time() >= TECHNICAL_ANALYSIS_PROBE_START


def latest_market_date_for_symbol(symbol: str, now: datetime | str | None = None) -> str:
    current = _as_beijing_datetime(now) if now is not None else beijing_now()
    if not _probe_allowed(current):
        return ""
    market = market_from_symbol(symbol)
    probe_symbol = MARKET_PROBE_SYMBOLS.get(market)
    if not probe_symbol:
        return ""
    cached = _MARKET_UPDATE_PROBE_CACHE.get(market)
    if cached and current - cached["checked_at"] < MARKET_UPDATE_PROBE_INTERVAL:
        return cached["market_date"]
    try:
        resolved = MarketDateResolver().resolve(probe_symbol)
    except Exception:
        market_date = ""
    else:
        market_date = resolved.market_date if getattr(resolved, "known", False) else ""
    _MARKET_UPDATE_PROBE_CACHE[market] = {
        "checked_at": current,
        "market_date": str(market_date or ""),
    }
    return str(market_date or "")


def technical_analysis_cache_expired_after_close(
    market_date: str,
    updated_at: datetime | str,
    now: datetime | str | None = None,
    normalized_target: str = "",
) -> bool:
    current = _as_beijing_datetime(now) if now is not None else beijing_now()
    latest_market_date = latest_market_date_for_symbol(normalized_target, now=current) if normalized_target else ""
    if latest_market_date and str(market_date or "") < latest_market_date:
        return True
    cutoff = datetime.combine(current.date(), _configured_close_invalidate_time(), tzinfo=BEIJING_TZ)
    if normalized_target and market_from_symbol(normalized_target) and current >= cutoff and str(market_date or "") < current.date().isoformat():
        return True
    if current < cutoff:
        return False
    if str(market_date or "") != current.date().isoformat():
        return False
    return _as_beijing_datetime(updated_at) < cutoff
