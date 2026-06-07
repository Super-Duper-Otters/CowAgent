# encoding:utf-8
from dataclasses import dataclass

from .business_definitions import BusinessDefinition, from_skill_definition, list_builtin_business_definitions
from .constants import ServiceType


@dataclass(frozen=True)
class BusinessMatch:
    business_key: str
    service_type: ServiceType
    raw_input: str
    target_text: str = ""
    skill_key: str = ""


def list_business_definitions() -> list[BusinessDefinition]:
    return list_builtin_business_definitions()


def get_business_definition(business_key: str) -> BusinessDefinition:
    from .skill_registry import get_skill_definition

    return from_skill_definition(get_skill_definition(business_key))


def match_business(raw_input: str) -> BusinessMatch | None:
    from .skill_registry import match_investment_skill

    matched = match_investment_skill(raw_input)
    if matched is None:
        return None
    return BusinessMatch(
        business_key=matched.skill_key,
        skill_key=matched.skill_key,
        service_type=matched.service_type,
        raw_input=matched.raw_input,
        target_text=matched.target_text,
    )
