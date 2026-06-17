# encoding:utf-8
import os
import tempfile
from dataclasses import dataclass
import importlib
from pathlib import Path

from sqlalchemy import inspect, select

from . import config_service
from .config_service import get_config
from business.constants import SERVICE_LABELS, ServiceType
from .db import connect, get_engine, row_to_dict
from .render_service import (
    DEFAULT_RENDERER_PATH,
    DEFAULT_TEMPLATE_BOND_PATH,
    DEFAULT_TEMPLATE_CB_PATH,
    DEFAULT_TEMPLATE_TA_PATH,
)
from .schema import stock_symbols
from business.storage import get_storage_dirs
from .stock_resolver import get_tushare_token, stock_dictionary_stats


@dataclass
class HealthItem:
    name: str
    ok: bool
    detail: str = ""
    level: str = ""

    def __post_init__(self):
        if not self.level:
            self.level = "ok" if self.ok else "error"
        if self.level not in {"ok", "warning", "error"}:
            raise ValueError(f"unsupported health level: {self.level}")
        self.ok = self.level != "error"


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
    from .ai_generation import _global_model_config

    model_config = _global_model_config()
    missing = [
        key
        for key, value in (
            ("model.provider", model_config["provider"]),
            ("model.name", model_config["model"]),
            ("model.api_base", model_config["api_base"]),
            ("model.api_key", model_config["api_key"]),
        )
        if not value
    ]
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


def _dependency_available(module_name: str) -> tuple[bool, str]:
    try:
        importlib.import_module(module_name)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _check_dependency(name: str, module_name: str, *, required: bool) -> HealthItem:
    available, detail = _dependency_available(module_name)
    if available:
        return HealthItem(name, True, f"{module_name} package available", level="ok")
    level = "error" if required else "warning"
    required_text = "required" if required else "optional"
    reason = f": {detail}" if detail else ""
    return HealthItem(name, level != "error", f"{module_name} package import failed ({required_text}){reason}", level=level)


def _dependency_health_items() -> list[HealthItem]:
    return [
        _check_dependency("dependency_pandas", "pandas", required=True),
        _check_dependency("dependency_talib", "talib", required=True),
        _check_dependency("dependency_scipy", "scipy", required=True),
        _check_dependency("dependency_akshare", "akshare", required=False),
        _check_dependency("dependency_tushare", "tushare", required=False),
        _check_dependency("dependency_baostock", "baostock", required=False),
    ]


def _has_chinese_font() -> bool:
    try:
        from matplotlib import font_manager

        candidates = ("SimHei", "Microsoft YaHei", "Noto Sans CJK", "Source Han Sans", "WenQuanYi")
        for font in font_manager.fontManager.ttflist:
            name = getattr(font, "name", "")
            if any(candidate.lower() in name.lower() for candidate in candidates):
                return True
    except Exception:
        return False
    return False


def _check_chinese_font() -> HealthItem:
    if _has_chinese_font():
        return HealthItem("chinese_font", True, "Chinese font available", level="ok")
    return HealthItem("chinese_font", True, "Chinese font not detected; rendered Chinese text may use fallback glyphs", level="warning")


def _enabled_channels(value) -> set[str]:
    if isinstance(value, str):
        return {part.strip() for part in value.split(",") if part.strip()}
    if isinstance(value, (list, tuple, set)):
        return {str(part).strip() for part in value if str(part).strip()}
    return set()


def _wechatmp_health_items() -> list[HealthItem]:
    config = config_service.conf()
    channels = _enabled_channels(config.get("channel_type"))
    subscribe_channels = _enabled_channels(config.get("subscribe_msg"))
    enabled = bool({"wechatmp", "wechatmp_service"} & (channels | subscribe_channels))
    items = [
        HealthItem(
            "wechatmp_channel_enabled",
            True,
            "enabled" if enabled else "not enabled",
            level="ok" if enabled else "warning",
        )
    ]

    required_level = "error" if enabled else "warning"
    for key, label in (
        ("wechatmp_app_id", "app id"),
        ("wechatmp_app_secret", "app secret"),
        ("wechatmp_token", "token"),
    ):
        configured = bool(str(config.get(key) or "").strip())
        items.append(
            HealthItem(
                key,
                configured or not enabled,
                f"{label} configured" if configured else f"{label} missing",
                level="ok" if configured else required_level,
            )
        )

    aes_configured = bool(str(config.get("wechatmp_aes_key") or "").strip())
    items.append(
        HealthItem(
            "wechatmp_aes_key",
            True,
            "aes key configured" if aes_configured else "aes key missing; required when WeChat encryption mode is enabled",
            level="ok" if aes_configured else "warning",
        )
    )
    return items


def _check_stock_dictionary_table() -> HealthItem:
    try:
        exists = inspect(get_engine()).has_table("stock_symbols")
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
        symbol_table = stock_symbols
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
    return HealthItem("tushare_token", True, "configured" if configured else "unconfigured", level="ok" if configured else "warning")


def _run_technical_analysis_smoke() -> HealthItem:
    try:
        from .technical_analysis import run_technical_analysis

        result = run_technical_analysis("health-smoke", "300502.SZ 技术分析", "300502.SZ")
        if result.success:
            detail = ", ".join(path for path in result.output_files if path) or "ok"
            return HealthItem("smoke_technical_analysis", True, detail, level="ok")
        return HealthItem("smoke_technical_analysis", False, result.detail or result.user_prompt or "failed", level="error")
    except Exception as exc:
        return HealthItem("smoke_technical_analysis", False, str(exc), level="error")


def _run_renderer_smoke_checks() -> list[HealthItem]:
    from .render_service import RenderRequest, render_card

    samples = (
        (ServiceType.TECHNICAL_ANALYSIS, "smoke_renderer_ta", "技术分析\n信号：中性\n风险：样例"),
        (ServiceType.RATE, "smoke_renderer_rate", "利率债市场：样例\n关注久期与流动性。"),
        (ServiceType.CONVERTIBLE_BOND, "smoke_renderer_cb", "转债市场：样例\n关注估值与正股弹性。"),
    )
    output_dir = Path(str(get_config("storage.tmp_dir") or get_storage_dirs()["tmp"])) / "health_smoke"
    items: list[HealthItem] = []
    for service_type, name, text in samples:
        try:
            output_path = output_dir / f"{service_type.value}.png"
            result = render_card(RenderRequest(service_type, text, str(output_path)))
            label = SERVICE_LABELS.get(service_type, service_type.value)
            if result.success:
                items.append(HealthItem(name, True, f"{label}: {result.image_path}", level="ok"))
            else:
                items.append(HealthItem(name, False, f"{label}: {result.detail or result.user_prompt}", level="error"))
        except Exception as exc:
            items.append(HealthItem(name, False, str(exc), level="error"))
    return items


def run_health_checks(run_smoke: bool = False) -> list[HealthItem]:
    items = []
    try:
        with connect() as conn:
            conn.execute(select(1)).fetchone()
        items.append(HealthItem("business_database", True, "ok"))
    except Exception as exc:
        items.append(HealthItem("business_database", False, str(exc)))

    dirs = get_storage_dirs()
    items.append(_check_writable_dir("files_dir", Path(str(get_config("storage.files_dir") or dirs["files"]))))
    items.append(_check_writable_dir("tmp_dir", Path(str(get_config("storage.tmp_dir") or dirs["tmp"]))))
    from .technical_analysis import DEFAULT_TECHNICAL_ANALYSIS_PATH

    items.append(_check_file("technical_analysis_skill", get_config("technical_analysis.skill_path") or DEFAULT_TECHNICAL_ANALYSIS_PATH))
    items.append(_check_file("signal_card_renderer", get_config("render.renderer_path") or DEFAULT_RENDERER_PATH))
    items.append(_check_file("template_ta", DEFAULT_TEMPLATE_TA_PATH))
    items.append(_check_file("template_bond", DEFAULT_TEMPLATE_BOND_PATH))
    items.append(_check_file("template_cb", DEFAULT_TEMPLATE_CB_PATH))
    items.extend(_stock_dictionary_health_items())
    items.append(_check_tushare_token())
    items.append(_check_model_config())
    items.extend(_dependency_health_items())
    items.append(_check_playwright_package())
    items.append(_check_playwright_chromium())
    items.append(_check_chinese_font())
    items.extend(_wechatmp_health_items())
    if run_smoke:
        items.append(_run_technical_analysis_smoke())
        items.extend(_run_renderer_smoke_checks())
    return items
