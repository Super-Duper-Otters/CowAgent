# encoding:utf-8
"""CowAgent business constants facade."""

from business.investment.constants import (
    CUSTOMER_SERVICE_TYPES,
    SERVICE_ALIASES,
    SERVICE_LABELS,
    USER_MESSAGE_CONFIG_KEYS,
    USER_MESSAGES,
    ErrorCode,
    ServiceType,
    Status,
    normalize_service,
)


def user_message(error_code: ErrorCode) -> str:
    default = USER_MESSAGES.get(error_code, USER_MESSAGES[ErrorCode.SYSTEM_ERROR])
    key = USER_MESSAGE_CONFIG_KEYS.get(error_code, USER_MESSAGE_CONFIG_KEYS[ErrorCode.SYSTEM_ERROR])
    try:
        from business.reply_config import get_reply_text

        return get_reply_text(key, default)
    except Exception:
        return default
