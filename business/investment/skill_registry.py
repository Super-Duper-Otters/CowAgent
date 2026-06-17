# encoding:utf-8
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config_service import get_config
from business.constants import ServiceType
from .render_service import DEFAULT_RENDERER_PATH


SAFE_SKILL_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class InvestmentSkillDefinition:
    skill_key: str
    label: str
    description: str
    service_type: ServiceType
    match_type: str
    default_triggers: tuple[str, ...]
    handler_type: str
    entry: str = ""
    output_mode: str = "images"
    routable: bool = True
    base_dir: str = ""
    config_key: str = ""
    default_script_path: str = ""
    script_name: str = ""
    storage_name: str = ""
    copy_assets_from: str = ""
    component_type: str = ""
    prompt_key: str = ""
    renderer_component_key: str = ""
    template_key: str = ""

    @property
    def enabled_config_key(self) -> str:
        return f"skill.{self.skill_key}.enabled"

    @property
    def triggers_config_key(self) -> str:
        return f"skill.{self.skill_key}.triggers"

    @property
    def script_relative_path(self) -> Path:
        return Path("scripts") / self.script_name

    @property
    def uses_triggers(self) -> bool:
        return self.component_type in {"active_script", "active_prompt"}

    @property
    def versioned(self) -> bool:
        return bool(self.script_name and self.config_key)

    def as_dict(self) -> dict:
        return {
            "skill_key": self.skill_key,
            "label": self.label,
            "description": self.description,
            "service_type": str(self.service_type),
            "match_type": self.match_type,
            "triggers": list(resolve_triggers(self)),
            "enabled": is_skill_enabled(self),
            "handler_type": self.handler_type,
            "entry": self.entry,
            "output_mode": self.output_mode,
            "routable": self.routable,
            "config_key": self.config_key,
            "default_script_path": self.default_script_path,
            "script_name": self.script_name,
            "storage_name": self.storage_name,
            "base_dir": self.base_dir,
            "component_type": self.component_type,
            "prompt_key": self.prompt_key,
            "renderer_component_key": self.renderer_component_key,
            "template_key": self.template_key,
            "uses_triggers": self.uses_triggers,
            "versioned": self.versioned,
        }


@dataclass(frozen=True)
class InvestmentSkillMatch:
    skill_key: str
    service_type: ServiceType
    raw_input: str
    target_text: str = ""


BUILTIN_DEFINITIONS: tuple[InvestmentSkillDefinition, ...] = (
    InvestmentSkillDefinition(
        skill_key="technical-analysis",
        label="技术分析组件",
        description="根据股票代码或名称生成技术分析报告、图表和信号卡片。",
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        match_type="suffix",
        default_triggers=("技术分析",),
        handler_type="builtin_technical_analysis",
        entry="builtin/components/technical-analysis/scripts/analyze_universal.py",
        config_key="technical_analysis.skill_path",
        default_script_path="builtin/components/technical-analysis/scripts/analyze_universal.py",
        script_name="analyze_universal.py",
        storage_name="technical-analysis",
        component_type="active_script",
        prompt_key="prompt.technical_analysis",
        renderer_component_key="signal-card-renderer",
        template_key="technical_analysis",
    ),
    InvestmentSkillDefinition(
        skill_key="rate",
        label="利率组件",
        description="返回当前生效的利率投研内容图片。",
        service_type=ServiceType.RATE,
        match_type="exact",
        default_triggers=("利率",),
        handler_type="daily_content",
        storage_name="rate",
        component_type="active_prompt",
        prompt_key="prompt.rate",
        renderer_component_key="signal-card-renderer",
        template_key="rate",
    ),
    InvestmentSkillDefinition(
        skill_key="convertible-bond",
        label="转债组件",
        description="返回当前生效的可转债投研内容图片。",
        service_type=ServiceType.CONVERTIBLE_BOND,
        match_type="exact",
        default_triggers=("转债",),
        handler_type="daily_content",
        storage_name="convertible-bond",
        component_type="active_prompt",
        prompt_key="prompt.convertible_bond",
        renderer_component_key="signal-card-renderer",
        template_key="convertible_bond",
    ),
    InvestmentSkillDefinition(
        skill_key="signal-card-renderer",
        label="图片生成组件",
        description="把标准投研文本渲染为信号卡片图片，作为投资业务内部组件使用。",
        service_type=ServiceType.UNMATCHED,
        match_type="exact",
        default_triggers=(),
        handler_type="renderer",
        entry=DEFAULT_RENDERER_PATH,
        output_mode="image",
        routable=False,
        config_key="render.renderer_path",
        default_script_path=DEFAULT_RENDERER_PATH,
        script_name="render_card.py",
        storage_name="signal-card-renderer",
        copy_assets_from="builtin/components/signal-card-renderer/assets",
        component_type="passive_script",
    ),
)


def _bool_value(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "启用", "是"}
    return bool(value)


def _normalize_triggers(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        items = value.replace("，", ",").split(",")
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        items = []
    return tuple(str(item).strip() for item in items if str(item).strip())


def validate_skill_key(skill_key: str) -> str:
    from business.business_registry import validate_business_key

    return validate_business_key(skill_key)


def _read_uploaded_definition(skill_dir: Path) -> InvestmentSkillDefinition | None:
    from business.business_registry import read_uploaded_business_definition

    definition = read_uploaded_business_definition(skill_dir)
    if definition is None:
        return None
    return _from_business_definition(definition)


def _from_business_definition(definition) -> InvestmentSkillDefinition:
    return InvestmentSkillDefinition(
        skill_key=str(getattr(definition, "skill_key", "") or getattr(definition, "business_key", "")),
        label=str(getattr(definition, "label", "")),
        description=str(getattr(definition, "description", "")),
        service_type=getattr(definition, "service_type", ServiceType.UNMATCHED),
        match_type=str(getattr(definition, "match_type", "exact") or "exact"),
        default_triggers=tuple(getattr(definition, "default_triggers", ()) or ()),
        handler_type=str(getattr(definition, "handler_type", "") or ""),
        entry=str(getattr(definition, "entry", "") or ""),
        output_mode=str(getattr(definition, "output_mode", "images") or "images"),
        routable=bool(getattr(definition, "routable", True)),
        base_dir=str(getattr(definition, "base_dir", "") or ""),
        config_key=str(getattr(definition, "config_key", "") or ""),
        default_script_path=str(getattr(definition, "default_script_path", "") or ""),
        script_name=str(getattr(definition, "script_name", "") or ""),
        storage_name=str(getattr(definition, "storage_name", "") or ""),
        copy_assets_from=str(getattr(definition, "copy_assets_from", "") or ""),
        component_type=str(getattr(definition, "component_type", "") or ""),
        prompt_key=str(getattr(definition, "prompt_key", "") or ""),
        renderer_component_key=str(getattr(definition, "renderer_component_key", "") or ""),
        template_key=str(getattr(definition, "template_key", "") or ""),
    )


def list_definitions() -> list[InvestmentSkillDefinition]:
    from business.business_registry import list_business_definitions

    return [_from_business_definition(definition) for definition in list_business_definitions()]


def get_skill_definition(skill_key: str) -> InvestmentSkillDefinition:
    for definition in list_definitions():
        if definition.skill_key == skill_key:
            return definition
    raise ValueError(f"unsupported investment skill: {skill_key}")


def list_investment_skills() -> list[dict]:
    return [definition.as_dict() for definition in list_definitions()]


def is_skill_enabled(definition: InvestmentSkillDefinition) -> bool:
    return _bool_value(get_config(definition.enabled_config_key, True), True)


def resolve_triggers(definition: InvestmentSkillDefinition) -> tuple[str, ...]:
    raw = get_config(definition.triggers_config_key, list(definition.default_triggers))
    return _normalize_triggers(raw)


def match_investment_skill(raw_input: str) -> InvestmentSkillMatch | None:
    from business.business_registry import match_business

    matched = match_business(raw_input)
    if matched is None:
        return None
    return InvestmentSkillMatch(matched.skill_key or matched.business_key, matched.service_type, raw_input, matched.target_text)
