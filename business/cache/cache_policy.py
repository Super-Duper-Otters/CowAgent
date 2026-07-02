# encoding:utf-8
import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from business.config.config_service import get_config
from business.content.market_date_resolver import MarketDateResolver
from business.market.provider_adapter import classify_asset_target


BEIJING_TZ = ZoneInfo("Asia/Shanghai")
TECHNICAL_ANALYSIS_PROBE_START = time(15, 30)
TECHNICAL_ANALYSIS_PROBE_END = time(18, 0)
TECHNICAL_ANALYSIS_AFTER_CLOSE_CUTOFF = time(17, 30)
TECHNICAL_ANALYSIS_CACHE_CLOSE_INVALIDATE_TIME_CONFIG = "investment.technical_analysis.cache_close_invalidate_time"
TECHNICAL_ANALYSIS_CACHE_CLOSE_INVALIDATE_TIME_DEFAULT = "17:30"
TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_START_CONFIG = "investment.technical_analysis.cache_update_probe_start"
TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_END_CONFIG = "investment.technical_analysis.cache_update_probe_end"
TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_INTERVAL_CONFIG = "investment.technical_analysis.cache_update_probe_interval_minutes"
TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_START_DEFAULT = "15:30"
TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_END_DEFAULT = "18:00"
TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_INTERVAL_DEFAULT = 15
MARKET_UPDATE_PROBE_INTERVAL = timedelta(minutes=15)
MARKET_PROBE_SYMBOLS = {
    "a_share": "600519.SH",
    "hk": "00700.HK",
    "us": "AAPL.US",
    "index": "sh000300",
    "etf": "510300.SH",
    "convertible_bond": "111009.SH",
    "futures": "T0",
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


def _configured_probe_start_time() -> time:
    try:
        value = get_config(
            TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_START_CONFIG,
            TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_START_DEFAULT,
        )
    except Exception:
        value = TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_START_DEFAULT
    return _parse_close_invalidate_time(value)


def _configured_probe_end_time() -> time:
    try:
        value = get_config(
            TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_END_CONFIG,
            TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_END_DEFAULT,
        )
    except Exception:
        value = TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_END_DEFAULT
    return _parse_close_invalidate_time(value)


def _configured_probe_interval() -> timedelta:
    try:
        value = int(get_config(
            TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_INTERVAL_CONFIG,
            TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_INTERVAL_DEFAULT,
        ) or TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_INTERVAL_DEFAULT)
    except Exception:
        value = TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_INTERVAL_DEFAULT
    return timedelta(minutes=max(1, min(value, 240)))


def technical_analysis_cache_update_config() -> dict:
    start = _configured_probe_start_time()
    end = _configured_probe_end_time()
    interval = _configured_probe_interval()
    return {
        "probe_start": start.strftime("%H:%M"),
        "probe_end": end.strftime("%H:%M"),
        "probe_interval_minutes": int(interval.total_seconds() // 60),
    }


def reset_market_update_probe_cache() -> None:
    _MARKET_UPDATE_PROBE_CACHE.clear()


def market_from_symbol(symbol: str) -> str:
    asset_type = classify_asset_target(symbol).asset_type
    aliases = {
        "hk_stock": "hk",
        "us_stock": "us",
    }
    return aliases.get(asset_type, asset_type)


def _probe_allowed(now: datetime) -> bool:
    return _configured_probe_start_time() <= now.time() <= _configured_probe_end_time()


def technical_analysis_cache_update_probe_allowed(now: datetime | str | None = None) -> bool:
    current = _as_beijing_datetime(now) if now is not None else beijing_now()
    return _probe_allowed(current)


def probe_symbols() -> list[dict]:
    labels = {
        "a_share": "A股",
        "hk": "港股",
        "us": "美股",
        "index": "指数",
        "etf": "ETF",
        "convertible_bond": "可转债",
        "futures": "国债期货",
    }
    return [
        {"asset_type": asset_type, "label": labels.get(asset_type, asset_type), "symbol": symbol}
        for asset_type, symbol in MARKET_PROBE_SYMBOLS.items()
    ]


def _probe_market_date(asset_type: str, symbol: str, current: datetime, *, force: bool = False) -> dict:
    cached = _MARKET_UPDATE_PROBE_CACHE.get(asset_type)
    if not force and cached and current - cached["checked_at"] < _configured_probe_interval():
        return {
            "asset_type": asset_type,
            "symbol": symbol,
            "market_date": cached["market_date"],
            "known": bool(cached["market_date"]),
            "source": cached.get("source", ""),
            "checked_at": cached["checked_at"].isoformat(),
            "cached": True,
            "error": cached.get("error", ""),
        }
    try:
        resolved = MarketDateResolver().resolve(symbol)
    except Exception as exc:
        market_date = ""
        source = ""
        error = str(exc)
    else:
        market_date = str(resolved.market_date or "") if getattr(resolved, "known", False) else ""
        source = str(getattr(resolved, "source", "") or "")
        error = ""
    _MARKET_UPDATE_PROBE_CACHE[asset_type] = {
        "checked_at": current,
        "market_date": market_date,
        "source": source,
        "error": error,
    }
    return {
        "asset_type": asset_type,
        "symbol": symbol,
        "market_date": market_date,
        "known": bool(market_date),
        "source": source,
        "checked_at": current.isoformat(),
        "cached": False,
        "error": error,
    }


def latest_market_date_for_symbol(symbol: str, now: datetime | str | None = None) -> str:
    current = _as_beijing_datetime(now) if now is not None else beijing_now()
    if not _probe_allowed(current):
        return ""
    market = market_from_symbol(symbol)
    probe_symbol = MARKET_PROBE_SYMBOLS.get(market)
    if not probe_symbol:
        return ""
    return str(_probe_market_date(market, probe_symbol, current).get("market_date") or "")


def probe_market_update_dates(now: datetime | str | None = None, *, force: bool = False) -> dict:
    current = _as_beijing_datetime(now) if now is not None else beijing_now()
    if not force and not _probe_allowed(current):
        targets = [
            {
                **target,
                "market_date": "",
                "known": False,
                "source": "",
                "checked_at": "",
                "cached": False,
                "error": "outside probe window",
            }
            for target in probe_symbols()
        ]
    else:
        targets = [
            {**target, **_probe_market_date(target["asset_type"], target["symbol"], current, force=force)}
            for target in probe_symbols()
        ]
    latest = max((target.get("market_date") or "" for target in targets), default="")
    return {
        "config": technical_analysis_cache_update_config(),
        "targets": targets,
        "latest_market_date": latest,
        "checked_at": current.isoformat(),
    }


def cached_market_update_dates(now: datetime | str | None = None) -> dict:
    current = _as_beijing_datetime(now) if now is not None else beijing_now()
    targets = []
    for target in probe_symbols():
        cached = _MARKET_UPDATE_PROBE_CACHE.get(target["asset_type"]) or {}
        market_date = str(cached.get("market_date") or "")
        checked_at = cached.get("checked_at")
        targets.append({
            **target,
            "market_date": market_date,
            "known": bool(market_date),
            "source": str(cached.get("source") or ""),
            "checked_at": checked_at.isoformat() if hasattr(checked_at, "isoformat") else "",
            "cached": bool(cached),
            "error": str(cached.get("error") or ""),
        })
    latest = max((target.get("market_date") or "" for target in targets), default="")
    return {
        "config": technical_analysis_cache_update_config(),
        "targets": targets,
        "latest_market_date": latest,
        "checked_at": current.isoformat(),
    }


def latest_market_date_from_probe_symbols(now: datetime | str | None = None) -> str:
    current = _as_beijing_datetime(now) if now is not None else beijing_now()
    if not _probe_allowed(current):
        return ""
    return str(probe_market_update_dates(now=current).get("latest_market_date") or "")


def technical_analysis_cache_expired_after_close(
    market_date: str,
    updated_at: datetime | str,
    now: datetime | str | None = None,
    normalized_target: str = "",
) -> bool:
    current = _as_beijing_datetime(now) if now is not None else beijing_now()
    latest_market_date = (
        latest_market_date_from_probe_symbols(now=current)
        if normalized_target and market_from_symbol(normalized_target)
        else ""
    )
    if latest_market_date and str(market_date or "") < latest_market_date:
        return True
    cutoff = datetime.combine(current.date(), _configured_close_invalidate_time(), tzinfo=BEIJING_TZ)
    if normalized_target and market_from_symbol(normalized_target):
        return False
    if current < cutoff:
        return False
    if str(market_date or "") != current.date().isoformat():
        return False
    return _as_beijing_datetime(updated_at) < cutoff
