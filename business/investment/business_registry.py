# encoding:utf-8
from dataclasses import dataclass

from business.business_registry import (
    get_business_definition as get_cowagent_business_definition,
    list_business_definitions as list_cowagent_business_definitions,
    match_business as match_cowagent_business,
)

from .business_definitions import BusinessDefinition, from_cowagent_definition
from business.constants import ServiceType


@dataclass(frozen=True)
class BusinessMatch:
    business_key: str
    service_type: ServiceType
    raw_input: str
    target_text: str = ""
    skill_key: str = ""


def list_business_definitions() -> list[BusinessDefinition]:
    return [from_cowagent_definition(definition) for definition in list_cowagent_business_definitions()]


def get_business_definition(business_key: str) -> BusinessDefinition:
    return from_cowagent_definition(get_cowagent_business_definition(business_key))


def match_business(raw_input: str) -> BusinessMatch | None:
    matched = match_cowagent_business(raw_input)
    if matched is None:
        return None
    return BusinessMatch(
        business_key=matched.business_key,
        skill_key=matched.skill_key or matched.business_key,
        service_type=matched.service_type,
        raw_input=matched.raw_input,
        target_text=matched.target_text,
    )
