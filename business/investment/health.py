# encoding:utf-8
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import inspect, select

from .config_service import get_config
from .db import connect, get_engine, row_to_dict
from .render_service import (
    DEFAULT_RENDERER_PATH,
    DEFAULT_TEMPLATE_BOND_PATH,
    DEFAULT_TEMPLATE_CB_PATH,
    DEFAULT_TEMPLATE_TA_PATH,
)
from .schema import investment_stock_symbols
from .storage import get_storage_dirs
from .stock_resolver import get_tushare_token, stock_dictionary_stats


@dataclass
class HealthItem:
    name: str
    ok: bool
    detail: str = ""


def _check_writable_dir(name: str, path: Path) -> HealthItem:
    if not path.exists():
        return HealthItem(name, False, f"directory does not exist: {path}")
    if not path.is_dir():
        return HealthItem(name, False, f"not a directory: {path}")
    try:
        fd, tmp = tempfile.mkstemp(dir=path)
        os.close(fd)
        os.remove(tmp)
        return HealthItem(name, True, str(path))
    except Exception as exc:
        return HealthItem(name, False, f"directory not writable: {path}, {exc}")


def _check_file(name: str, value: str | None) -> HealthItem:
    path = Path(str(value or ""))
    if value and not path.is_absolute():
        path = Path.cwd() / path
    if not value or not path.exists():
        return HealthItem(name, False, f"file does not exist: {path}")
    return HealthItem(name, True, str(path))


def _check_model_config() -> HealthItem:
    required = (
        "model.provider",
        "model.name",
        "model.api_base",
        "model.api_key",
    )
    missing = [key for key in required if not get_config(key)]
    if missing:
        return HealthItem("model_config", False, "model config incomplete: " + ", ".join(f"{key} missing" for key in missing))
    return HealthItem("model_config", True, "model provider/name/api base/api key configured")


def _check_playwright_package() -> HealthItem:
    try:
        import playwright  # noqa: F401

        return HealthItem("playwright", True, "python package available")
    except Exception as exc:
        return HealthItem("playwright", False, f"playwright package unavailable: {exc}")


def _check_playwright_chromium() -> HealthItem:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return HealthItem("playwright_chromium", False, f"playwright package unavailable: {exc}")
    try:
        with sync_playwright() as playwright:
            executable_path = Path(playwright.chromium.executable_path)
        if not executable_path.exists():
            return HealthItem(
                "playwright_chromium",
                False,
                f"chromium executable missing: {executable_path}; run `py -m playwright install chromium`",
            )
        return HealthItem("playwright_chromium", True, str(executable_path))
    except Exception as exc:
        return HealthItem(
            "playwright_chromium",
            False,
            f"playwright chromium unavailable: {exc}; run `py -m playwright install chromium`",
        )


def _check_stock_dictionary_table() -> HealthItem:
    try:
        exists = inspect(get_engine()).has_table("investment_stock_symbols")
        return HealthItem("stock_dictionary_table", exists, "exists" if exists else "missing")
    except Exception as exc:
        return HealthItem("stock_dictionary_table", False, str(exc))


def _stock_dictionary_health_items() -> list[HealthItem]:
    table_item = _check_stock_dictionary_table()
    if not table_item.ok:
        return [
            table_item,
            HealthItem("stock_dictionary_count", False, "unavailable"),
            HealthItem("stock_dictionary_latest", False, "unavailable"),
            HealthItem("stock_dictionary_latest_source", False, "unavailable"),
        ]

    try:
        stats = stock_dictionary_stats()
        symbol_table = investment_stock_symbols
        latest_updated_at = select(symbol_table.c.updated_at).order_by(symbol_table.c.updated_at.desc()).limit(1).scalar_subquery()
        stmt = (
            select(symbol_table.c.source)
            .where(symbol_table.c.updated_at == latest_updated_at)
            .order_by(symbol_table.c.source)
            .limit(1)
        )
        with connect() as conn:
            source_row = conn.execute(stmt).fetchone()
        total_value = stats.get("total")
        total = int(total_value) if isinstance(total_value, int | str | float) else 0
        latest = str(stats.get("latest_updated_at") or "")
        latest_source = row_to_dict(source_row).get("source", "") if source_row else ""
        return [
            table_item,
            HealthItem("stock_dictionary_count", total > 0, str(total)),
            HealthItem("stock_dictionary_latest", bool(latest), latest or "none"),
            HealthItem("stock_dictionary_latest_source", bool(latest_source), latest_source or "none"),
        ]
    except Exception as exc:
        return [
            table_item,
            HealthItem("stock_dictionary_count", False, str(exc)),
            HealthItem("stock_dictionary_latest", False, str(exc)),
            HealthItem("stock_dictionary_latest_source", False, str(exc)),
        ]


def _check_tushare_token() -> HealthItem:
    configured = bool(get_tushare_token())
    return HealthItem("tushare_token", configured, "configured" if configured else "unconfigured")


def run_health_checks() -> list[HealthItem]:
    items = []
    try:
        with connect() as conn:
            conn.execute(select(1)).fetchone()
        items.append(HealthItem("business_database", True, "ok"))
    except Exception as exc:
        items.append(HealthItem("business_database", False, str(exc)))

    dirs = get_storage_dirs()
    items.append(_check_writable_dir("upload_dir", Path(str(get_config("storage.upload_dir") or dirs["uploads"]))))
    items.append(_check_writable_dir("generated_dir", Path(str(get_config("storage.generated_dir") or dirs["generated"]))))
    items.append(_check_file("technical_analysis_skill", get_config("technical_analysis.skill_path") or "skills/技术分析/scripts/analyze_universal.py"))
    items.append(_check_file("signal_card_renderer", get_config("render.renderer_path") or DEFAULT_RENDERER_PATH))
    items.append(_check_file("template_ta", get_config("render.template_ta_path") or DEFAULT_TEMPLATE_TA_PATH))
    items.append(_check_file("template_bond", get_config("render.template_rate_path") or DEFAULT_TEMPLATE_BOND_PATH))
    items.append(_check_file("template_cb", get_config("render.template_cb_path") or DEFAULT_TEMPLATE_CB_PATH))
    items.extend(_stock_dictionary_health_items())
    items.append(_check_tushare_token())
    items.append(_check_model_config())
    wechat_ok = bool(get_config("wechatmp.app_id")) and bool(get_config("wechatmp.token"))
    items.append(HealthItem("wechatmp_config", wechat_ok, "wechatmp configured" if wechat_ok else "wechatmp app_id or token missing"))
    items.append(_check_playwright_package())
    items.append(_check_playwright_chromium())
    return items
