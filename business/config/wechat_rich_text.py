# encoding:utf-8
"""Helpers for WeChat Official Account rich-text quick actions."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any
from html import escape
from urllib.parse import quote


ACTION_TOKEN_PATTERN = re.compile(r"\{\{\s*action:([A-Za-z0-9_-]+)\s*\}\}")


@dataclass(frozen=True)
class RichTextAction:
    action_id: str
    label: str
    kind: str
    display_text: str | None = None
    trigger_text: str | None = None
    component_key: str | None = None
    target: str = ""
    msgmenuid: str | None = None
    editable: bool = True
    dynamic: bool = False
    description: str = ""


RICH_TEXT_ACTIONS: dict[str, RichTextAction] = {
    "get_result": RichTextAction(
        "get_result",
        "领取结果",
        "wechat_menu",
        display_text="回复1获取",
        trigger_text="1",
        msgmenuid="get_result",
        description="发送 1，领取当前待领取结果。",
    ),
    "get_result_short": RichTextAction(
        "get_result_short",
        "领取结果（短文本）",
        "wechat_menu",
        display_text="回复1",
        trigger_text="1",
        msgmenuid="get_result",
        description="发送 1，领取当前待领取结果。",
    ),
    "technical_analysis_example": RichTextAction(
        "technical_analysis_example",
        "技术分析示例",
        "component",
        component_key="technical-analysis",
        target="000300.SH",
        dynamic=True,
        description="使用当前技术分析组件触发词和示例标的。",
    ),
    "stock_not_found_example": RichTextAction(
        "stock_not_found_example",
        "未找到标的示例",
        "component",
        component_key="technical-analysis",
        target="300502.SZ",
        dynamic=True,
        description="使用当前技术分析组件触发词和股票代码示例。",
    ),
    "rate_tracking": RichTextAction(
        "rate_tracking",
        "利率择时跟踪",
        "component",
        display_text="利率择时跟踪",
        component_key="rate",
        msgmenuid="rate",
        dynamic=True,
        description="使用当前利率组件触发词。",
    ),
    "convertible_bond_tracking": RichTextAction(
        "convertible_bond_tracking",
        "转债量化日度跟踪",
        "component",
        display_text="转债量化日度跟踪",
        component_key="convertible-bond",
        msgmenuid="convertible_bond",
        dynamic=True,
        description="使用当前转债组件触发词。",
    ),
}

CUSTOM_RICH_ACTIONS_CONFIG_KEY = "reply.rich_actions"


def wechat_bizmsgmenu_link(content: str, label: str | None = None, msgmenuid: str | None = None) -> str:
    text = str(content or "").strip()
    display = str(label if label is not None else text).strip() or text
    menu_id = str(msgmenuid or _menu_id_from_content(text)).strip()
    return (
        '<a href="weixin://bizmsgmenu?msgmenucontent='
        f'{quote(text, safe="._-")}&msgmenuid={quote(menu_id, safe="._-")}">'
        f"{escape(display)}</a>"
    )


def technical_analysis_command(target: str) -> str:
    text = str(target or "").strip()
    if text.startswith("#"):
        text = text[1:].strip()
    return f"#{text}" if text else "#"


def technical_analysis_link(target: str, label: str | None = None) -> str:
    text = str(target or "").strip()
    command = technical_analysis_command(text)
    display = label if label is not None else command
    return wechat_bizmsgmenu_link(command, display, f"ta_{_safe_menu_segment(text)}")


def component_command(component_key: str, target: str = "") -> str:
    try:
        from business.components.registry import get_business_definition, resolve_match_type, resolve_triggers

        definition = get_business_definition(component_key)
        trigger = next(iter(resolve_triggers(definition)), "")
        match_type = resolve_match_type(definition)
    except Exception:
        trigger = ""
        match_type = "exact"
    text = str(target or "").strip()
    if not trigger:
        return text
    if not text:
        return trigger
    if match_type == "prefix":
        separator = "" if trigger.endswith("#") or trigger in {"#"} else " "
        return f"{trigger}{separator}{text}".strip()
    if match_type == "suffix":
        return f"{text} {trigger}".strip()
    return trigger


def component_link(component_key: str, target: str = "", label: str | None = None, msgmenuid: str | None = None) -> str:
    command = component_command(component_key, target)
    display = label if label is not None else command
    default_prefix = "ta" if component_key == "technical-analysis" else component_key
    menu_id = msgmenuid or f"{default_prefix}_{_safe_menu_segment(command)}"
    return wechat_bizmsgmenu_link(command, display, menu_id)


def render_rich_text_action(action_id: str) -> str:
    action = get_rich_text_actions().get(str(action_id or ""))
    if not action:
        return f"{{{{action:{action_id}}}}}"
    if action.kind == "component" and action.component_key:
        return component_link(action.component_key, action.target, label=action.display_text, msgmenuid=action.msgmenuid)
    return wechat_bizmsgmenu_link(action.trigger_text or "", action.display_text, action.msgmenuid or action.action_id)


def render_rich_text_template(template: str) -> str:
    text = str(template or "")
    if "{{" not in text:
        return text
    return ACTION_TOKEN_PATTERN.sub(lambda match: render_rich_text_action(match.group(1)), text)


def normalize_rich_text_template(template: str) -> str:
    text = str(template or "")
    if "weixin://bizmsgmenu?" not in text:
        return text
    for action_id, action in get_rich_text_actions().items():
        rendered = _rich_action_metadata(action)["rendered"]
        if rendered in text:
            text = text.replace(rendered, f"{{{{action:{action_id}}}}}")
    return text


def rich_text_template_action_ids(template: str) -> list[str]:
    seen: set[str] = set()
    action_ids: list[str] = []
    for match in ACTION_TOKEN_PATTERN.finditer(str(template or "")):
        action_id = match.group(1)
        if action_id not in seen:
            seen.add(action_id)
            action_ids.append(action_id)
    return action_ids


def reply_rich_action_metadata(action_ids: list[str] | tuple[str, ...] | None = None) -> dict[str, dict[str, Any]]:
    actions = get_rich_text_actions()
    selected = action_ids if action_ids is not None else list(actions)
    return {
        action_id: _rich_action_metadata(actions[action_id])
        for action_id in selected
        if action_id in actions
    }


def get_rich_text_actions() -> dict[str, RichTextAction]:
    actions = dict(RICH_TEXT_ACTIONS)
    actions.update(_custom_rich_text_actions())
    return actions


def _custom_rich_text_actions() -> dict[str, RichTextAction]:
    try:
        from business.config.config_service import get_config

        raw = get_config(CUSTOM_RICH_ACTIONS_CONFIG_KEY, {})
    except Exception:
        raw = {}
    if not isinstance(raw, dict):
        return {}
    actions: dict[str, RichTextAction] = {}
    for raw_id, payload in raw.items():
        action_id = _safe_custom_action_id(raw_id)
        if not action_id or not isinstance(payload, dict):
            continue
        trigger_text = str(payload.get("trigger_text") or payload.get("content") or "").strip()
        display_text = str(payload.get("display_text") or payload.get("label") or trigger_text).strip()
        if not trigger_text or not display_text:
            continue
        actions[action_id] = RichTextAction(
            action_id=action_id,
            label=str(payload.get("label") or display_text).strip() or action_id,
            kind="wechat_menu",
            display_text=display_text,
            trigger_text=trigger_text,
            msgmenuid=str(payload.get("msgmenuid") or action_id).strip() or action_id,
            editable=True,
            dynamic=False,
            description=str(payload.get("description") or "自定义富文本标签").strip(),
        )
    return actions


def _safe_custom_action_id(value: Any) -> str:
    text = re.sub(r"[^0-9A-Za-z_-]+", "_", str(value or "").strip()).strip("_")
    return text[:64]


def _rich_action_metadata(action: RichTextAction) -> dict[str, Any]:
    if action.kind == "component" and action.component_key:
        trigger_text = component_command(action.component_key, action.target)
        display_text = action.display_text or trigger_text
        rendered = component_link(action.component_key, action.target, label=action.display_text, msgmenuid=action.msgmenuid)
    else:
        trigger_text = action.trigger_text or ""
        display_text = action.display_text or trigger_text
        rendered = wechat_bizmsgmenu_link(trigger_text, display_text, action.msgmenuid or action.action_id)
    return {
        "id": action.action_id,
        "label": action.label,
        "kind": action.kind,
        "display_text": display_text,
        "trigger_text": trigger_text,
        "component_key": action.component_key or "",
        "target": action.target,
        "msgmenuid": action.msgmenuid or action.action_id,
        "editable": action.editable,
        "dynamic": action.dynamic,
        "description": action.description,
        "token": f"{{{{action:{action.action_id}}}}}",
        "rendered": rendered,
        "source": "builtin" if action.action_id in RICH_TEXT_ACTIONS else "custom",
    }


def _menu_id_from_content(content: str) -> str:
    return f"menu_{_safe_menu_segment(content)}"


def _safe_menu_segment(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z]+", "_", str(value or "").strip()).strip("_")
    if normalized:
        return normalized[:48]
    digest = hashlib.sha1(str(value or "").encode("utf-8")).hexdigest()[:12]
    return digest or "empty"
