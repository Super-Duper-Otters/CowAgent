# encoding:utf-8
import re
from datetime import datetime, time
from zoneinfo import ZoneInfo

from .config_service import get_config


BEIJING_TZ = ZoneInfo("Asia/Shanghai")
TECHNICAL_ANALYSIS_AFTER_CLOSE_CUTOFF = time(15, 30)
TECHNICAL_ANALYSIS_CACHE_CLOSE_INVALIDATE_TIME_CONFIG = "investment.technical_analysis.cache_close_invalidate_time"
TECHNICAL_ANALYSIS_CACHE_CLOSE_INVALIDATE_TIME_DEFAULT = "15:30"


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


def technical_analysis_cache_expired_after_close(
    market_date: str,
    updated_at: datetime | str,
    now: datetime | str | None = None,
) -> bool:
    current = _as_beijing_datetime(now) if now is not None else beijing_now()
    cutoff = datetime.combine(current.date(), _configured_close_invalidate_time(), tzinfo=BEIJING_TZ)
    if current < cutoff:
        return False
    if str(market_date or "") != current.date().isoformat():
        return False
    return _as_beijing_datetime(updated_at) < cutoff
