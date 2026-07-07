# encoding:utf-8
import threading
from datetime import datetime, timedelta

from common.log import logger

_SCHEDULER_LOCK = threading.Lock()
_SCHEDULER_THREAD: threading.Thread | None = None
_STOP_EVENT = threading.Event()


def _previous_trading_date(value: str) -> str:
    parsed = datetime.fromisoformat(value).date()
    return (parsed - timedelta(days=1)).isoformat()


def run_technical_analysis_cache_update_probe(*, force: bool = False) -> dict:
    from business.cache.cache_policy import cached_market_update_dates, probe_market_update_dates
    from business.config.constants import ServiceType
    from business.products.product_service import invalidate_products_by_scope

    previous = cached_market_update_dates()
    previous_latest = str(previous.get("latest_market_date") or "")
    payload = probe_market_update_dates(force=force)
    latest = str(payload.get("latest_market_date") or "")
    products_invalidated = 0
    if latest:
        if previous_latest and latest > previous_latest:
            products_invalidated = invalidate_products_by_scope(
                business_type=str(ServiceType.TECHNICAL_ANALYSIS),
                business_date="",
            )
        elif not previous_latest:
            try:
                stale_end = _previous_trading_date(latest)
            except ValueError:
                stale_end = ""
            if stale_end:
                products_invalidated = invalidate_products_by_scope(
                    business_type=str(ServiceType.TECHNICAL_ANALYSIS),
                    end_date=stale_end,
                )
    return {
        **payload,
        "previous_latest_market_date": previous_latest,
        "products_invalidated": products_invalidated,
    }


def _sleep_seconds_from_config(default_seconds: int = 60) -> int:
    try:
        from business.cache.cache_policy import technical_analysis_cache_update_config

        interval = int(technical_analysis_cache_update_config().get("probe_interval_minutes") or 15)
        return max(30, min(interval * 60, 3600))
    except Exception:
        return default_seconds


def _probe_loop() -> None:
    logger.info("[Investment] technical analysis cache update probe scheduler started")
    while not _STOP_EVENT.is_set():
        try:
            from business.cache.cache_policy import technical_analysis_cache_update_probe_allowed

            if technical_analysis_cache_update_probe_allowed():
                result = run_technical_analysis_cache_update_probe(force=False)
                logger.info(
                    "[Investment] cache update auto probe latest=%s previous=%s invalidated=%s",
                    result.get("latest_market_date") or "",
                    result.get("previous_latest_market_date") or "",
                    result.get("products_invalidated") or 0,
                )
        except Exception as exc:
            logger.warning(f"[Investment] cache update auto probe failed: {exc}")
        _STOP_EVENT.wait(_sleep_seconds_from_config())


def start_technical_analysis_cache_update_scheduler() -> bool:
    global _SCHEDULER_THREAD
    with _SCHEDULER_LOCK:
        if _SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive():
            return False
        _STOP_EVENT.clear()
        _SCHEDULER_THREAD = threading.Thread(
            target=_probe_loop,
            name="investment-cache-update-probe",
            daemon=True,
        )
        _SCHEDULER_THREAD.start()
        return True


def stop_technical_analysis_cache_update_scheduler() -> None:
    _STOP_EVENT.set()
