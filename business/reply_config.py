# encoding:utf-8
"""CowAgent business reply text facade."""

from business.investment.reply_config import (
    INVESTMENT_REPLY_DEFINITIONS,
    REPLY_TEXT_DEFINITIONS,
    REPLY_TEXT_GROUPS,
    WECHATMP_REPLY_DEFINITIONS,
    ReplyTextDefinition,
    reply_config_fallback_keys,
)


def default_reply_text(key: str, default: str = "") -> str:
    definition = REPLY_TEXT_DEFINITIONS.get(key)
    return definition.default if definition else default


def get_reply_text(key: str, default: str = "") -> str:
    from business.config_service import get_config

    configured = get_config(key, None)
    if configured is None or str(configured) == "":
        return default_reply_text(key, default)
    return str(configured)


def format_reply_text(key: str, *args, default: str = "") -> str:
    text = get_reply_text(key, default)
    if not args:
        return text
    try:
        return text.format(*args)
    except Exception:
        return default_reply_text(key, default).format(*args)


def reply_text_config_metadata() -> dict:
    return {
        "groups": REPLY_TEXT_GROUPS,
        "definitions": {
            key: {
                "label": definition.label,
                "description": definition.description,
                "default": definition.default,
                "placeholders": list(definition.placeholders),
            }
            for key, definition in REPLY_TEXT_DEFINITIONS.items()
        },
    }
