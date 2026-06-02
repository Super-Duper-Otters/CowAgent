# encoding:utf-8
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from config import conf

from .db import connect, row_to_dict, upsert_config
from .schema import investment_configs


SENSITIVE_MARKERS = ("api_key", "secret", "token", "aes_key", "password")
API_CONFIG_PREFIXES = ("model.", "wechatmp.")
ADMIN_ONLY_CONFIG_KEYS = {"router.enable_web_open_chat"}

CONFIG_FALLBACK_KEYS = {
    "tushare.token": "tushare_token",
    "router.enable_agent_fallback": "investment_enable_agent_fallback",
    "router.enable_web_open_chat": "investment_enable_web_open_chat",
    "technical_analysis.skill_path": "investment_ta_skill_path",
    "technical_analysis.output_dir": "investment_ta_output_dir",
    "technical_analysis.default_chart_days": "investment_ta_default_chart_days",
    "render.renderer_path": "investment_renderer_path",
    "render.template_ta_path": "investment_template_ta_path",
    "render.template_rate_path": "investment_template_rate_path",
    "render.template_cb_path": "investment_template_cb_path",
    "render.output_dir": "investment_render_output_dir",
    "storage.upload_dir": "investment_upload_dir",
    "storage.generated_dir": "investment_generated_dir",
    "prompt.technical_analysis": "investment_prompt_ta",
    "prompt.rate": "investment_prompt_rate",
    "prompt.convertible_bond": "investment_prompt_cb",
}

try:
    from .reply_config import reply_config_fallback_keys

    CONFIG_FALLBACK_KEYS.update(reply_config_fallback_keys())
except Exception:
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _serialize(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _deserialize(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def is_sensitive_key(key: str) -> bool:
    key_lower = key.lower()
    return any(marker in key_lower for marker in SENSITIVE_MARKERS)


def mask_sensitive_value(value: Any) -> str:
    text = "" if value is None else str(value)
    if not text:
        return ""
    if len(text) <= 6:
        return "***"
    return f"{text[:4]}{'*' * 10}{text[-4:]}"


def safe_log_value(key: str, value: Any) -> str:
    return mask_sensitive_value(value) if is_sensitive_key(key) else str(value)


def sanitize_sensitive_text(text: Any) -> str:
    safe_text = "" if text is None else str(text)
    configured_values: list[tuple[str, Any]] = []
    with connect() as conn:
        rows = conn.execute(select(investment_configs.c.config_key, investment_configs.c.config_value)).fetchall()
    for row in rows:
        item = row_to_dict(row)
        if is_sensitive_key(item["config_key"]):
            configured_values.append((item["config_key"], _deserialize(item["config_value"])))
    app_config = conf()
    for key, fallback_key in CONFIG_FALLBACK_KEYS.items():
        if is_sensitive_key(key):
            configured_values.append((key, app_config.get(fallback_key)))
    for key, value in app_config.items():
        if is_sensitive_key(str(key)):
            configured_values.append((str(key), value))
    for key, value in configured_values:
        raw = "" if value is None else str(value)
        if raw:
            safe_text = safe_text.replace(raw, safe_log_value(key, raw))
    return safe_text


def _forbidden_config_keys(keys: list[str] | tuple[str, ...] | set[str]) -> list[str]:
    return sorted(key for key in keys if key.startswith(API_CONFIG_PREFIXES))


def _validate_investment_config_keys(keys: list[str] | tuple[str, ...] | set[str]) -> None:
    forbidden = _forbidden_config_keys(keys)
    if forbidden:
        raise ValueError(
            "Investment config does not accept global config keys: "
            + ", ".join(forbidden)
            + ". Use config.json/global config for model and wechatmp settings."
        )


def can_modify_config(key: str, operator_role: str) -> bool:
    if key.startswith(API_CONFIG_PREFIXES):
        return False
    if key in ADMIN_ONLY_CONFIG_KEYS:
        return operator_role == "admin"
    if operator_role in ("admin", "technical_admin"):
        return True
    if is_sensitive_key(key):
        return False
    return operator_role in ("uploader", "operator")


def get_config(key: str, default: Any = None, *, masked: bool = False) -> Any:
    with connect() as conn:
        row = conn.execute(
            select(investment_configs.c.config_value).where(investment_configs.c.config_key == key),
        ).fetchone()
    value = _deserialize(row_to_dict(row)["config_value"]) if row else None
    if value is None:
        fallback_key = CONFIG_FALLBACK_KEYS.get(key, key)
        value = conf().get(fallback_key, default)
        if value is None and key.startswith("reply."):
            try:
                from .reply_config import default_reply_text

                value = default_reply_text(key, default)
            except Exception:
                value = default
    if masked and is_sensitive_key(key):
        return mask_sensitive_value(value)
    return value if value is not None else default


def save_config(
    key: str,
    value: Any,
    *,
    operator_role: str = "admin",
    operator: str = "",
    sync_project: bool = False,
) -> None:
    _validate_investment_config_keys((key,))
    if not can_modify_config(key, operator_role):
        raise PermissionError(f"role {operator_role} cannot modify {key}")
    if is_sensitive_key(key) and isinstance(value, str) and "*" in value:
        with connect() as conn:
            existing = conn.execute(
                select(investment_configs.c.config_value).where(investment_configs.c.config_key == key),
            ).fetchone()
        if existing is not None:
            existing_value = _deserialize(row_to_dict(existing)["config_value"])
            if value == mask_sensitive_value(existing_value):
                return
        else:
            fallback_key = CONFIG_FALLBACK_KEYS.get(key, key)
            fallback_value = conf().get(fallback_key)
            if fallback_value is not None and value == mask_sensitive_value(fallback_value):
                return
    with connect() as conn:
        upsert_config(conn, key, _serialize(value), _now(), operator)


def get_configs(keys: list[str], *, masked: bool = False) -> dict[str, Any]:
    return {key: get_config(key, masked=masked) for key in keys}


def save_configs(
    values: dict[str, Any],
    *,
    operator_role: str = "admin",
    operator: str = "",
    sync_project: bool = False,
) -> None:
    _validate_investment_config_keys(tuple(values.keys()))
    for key, value in values.items():
        save_config(
            key,
            value,
            operator_role=operator_role,
            operator=operator,
            sync_project=sync_project,
        )
