# encoding:utf-8
"""Investment component view and settings helpers."""

from business.business_registry import (
    get_business_definition,
    is_business_enabled,
    list_business_definitions,
    resolve_triggers,
)

from .config_service import get_config, save_config
from .skill_versions import list_versions


def _component_settings(definition) -> dict:
    settings = {"enabled": is_business_enabled(definition)}
    if definition.uses_triggers:
        settings["triggers"] = list(resolve_triggers(definition))
    if definition.prompt_key:
        settings["prompt_key"] = definition.prompt_key
        settings["prompt"] = get_config(definition.prompt_key, "")
    return settings


def _component_versions(definition) -> list[dict]:
    if not definition.versioned:
        return []
    return list_versions(definition.business_key)


def list_components() -> list[dict]:
    items = []
    for definition in list_business_definitions():
        item = definition.as_dict()
        item["component_key"] = definition.business_key
        item["uses_triggers"] = definition.uses_triggers
        item["versioned"] = definition.versioned
        item["settings"] = _component_settings(definition)
        item["versions"] = _component_versions(definition)
        items.append(item)
    return items


def _normalize_triggers(value) -> list[str]:
    if isinstance(value, str):
        items = value.replace("，", ",").split(",")
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        items = []
    return [str(item).strip() for item in items if str(item).strip()]


def save_component_settings(
    component_key: str,
    values: dict,
    *,
    operator_role: str,
    operator: str,
    actor=None,
) -> dict:
    definition = get_business_definition(component_key)

    if "triggers" in values:
        if not definition.uses_triggers:
            raise ValueError("passive components do not accept triggers")
        triggers = _normalize_triggers(values.get("triggers"))
        if not triggers:
            raise ValueError("active component triggers cannot be empty")
        save_config(
            definition.triggers_config_key,
            triggers,
            operator_role=operator_role,
            operator=operator,
            actor=actor,
        )

    if "enabled" in values:
        save_config(
            definition.enabled_config_key,
            bool(values.get("enabled")),
            operator_role=operator_role,
            operator=operator,
            actor=actor,
        )

    if "prompt" in values:
        if not definition.prompt_key:
            raise ValueError("component does not accept prompt")
        save_config(
            definition.prompt_key,
            str(values.get("prompt") or ""),
            operator_role=operator_role,
            operator=operator,
            actor=actor,
        )

    return next(item for item in list_components() if item["component_key"] == component_key)
