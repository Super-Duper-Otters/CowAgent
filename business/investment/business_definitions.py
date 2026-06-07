# encoding:utf-8
from dataclasses import dataclass, field

from .constants import ServiceType


@dataclass(frozen=True)
class BusinessDefinition:
    business_key: str
    service_type: ServiceType
    label: str
    input_types: tuple[str, ...] = ("text",)
    handler_type: str = ""
    cache_mode: str = "none"
    artifact_roles: tuple[str, ...] = field(default_factory=tuple)
    skill_key: str = ""


def _cache_mode_for_handler(handler_type: str) -> str:
    if handler_type == "builtin_technical_analysis":
        return "business_result"
    if handler_type == "daily_content":
        return "effective_content"
    return "none"


def _artifact_roles_for_handler(handler_type: str) -> tuple[str, ...]:
    if handler_type == "builtin_technical_analysis":
        return ("signal_card", "main_chart", "markdown_report")
    if handler_type == "daily_content":
        return ("output_image",)
    return ("output",)


def from_skill_definition(definition) -> BusinessDefinition:
    handler_type = str(getattr(definition, "handler_type", "") or "")
    skill_key = str(getattr(definition, "skill_key", "") or "")
    return BusinessDefinition(
        business_key=skill_key,
        skill_key=skill_key,
        service_type=getattr(definition, "service_type", ServiceType.UNMATCHED),
        label=str(getattr(definition, "label", "") or skill_key),
        input_types=("text",),
        handler_type=handler_type,
        cache_mode=_cache_mode_for_handler(handler_type),
        artifact_roles=_artifact_roles_for_handler(handler_type),
    )


def list_builtin_business_definitions() -> list[BusinessDefinition]:
    from .skill_registry import list_definitions

    return [from_skill_definition(definition) for definition in list_definitions()]
