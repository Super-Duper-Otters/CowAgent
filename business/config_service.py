# encoding:utf-8
"""CowAgent business configuration facade.

The backing store is still the existing investment config table during this
migration stage. Runtime business code should import configuration helpers from
this module so the storage implementation can be replaced later without
touching channel or handler code.
"""

from business.investment.config_service import (
    ADMIN_ONLY_CONFIG_KEYS,
    API_CONFIG_PREFIXES,
    CONFIG_FALLBACK_KEYS,
    SENSITIVE_MARKERS,
    can_modify_config,
    get_config,
    get_configs,
    is_sensitive_key,
    mask_sensitive_value,
    safe_log_value,
    sanitize_sensitive_text,
    save_config,
    save_configs,
)

