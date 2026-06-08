# encoding:utf-8
"""CowAgent built-in business definitions and intent matching."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.skills.frontmatter import parse_frontmatter

from business.config_service import get_config
from business.constants import ServiceType, normalize_service
from business.investment.render_service import DEFAULT_RENDERER_PATH


SAFE_BUSINESS_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


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
    description: str = ""
    match_type: str = "exact"
    default_triggers: tuple[str, ...] = field(default_factory=tuple)
    entry: str = ""
    output_mode: str = "images"
    routable: bool = True
    base_dir: str = ""
    config_key: str = ""
    default_script_path: str = ""
    script_name: str = ""
    storage_name: str = ""
    copy_assets_from: str = ""

    @property
    def enabled_config_key(self) -> str:
        return f"skill.{self.business_key}.enabled"

    @property
    def triggers_config_key(self) -> str:
        return f"skill.{self.business_key}.triggers"

    @property
    def script_relative_path(self) -> Path:
        return Path("scripts") / self.script_name

    def as_dict(self) -> dict:
        return {
            "skill_key": self.skill_key or self.business_key,
            "business_key": self.business_key,
            "label": self.label,
            "description": self.description,
            "service_type": str(self.service_type),
            "match_type": self.match_type,
            "triggers": list(resolve_triggers(self)),
            "enabled": is_business_enabled(self),
            "handler_type": self.handler_type,
            "entry": self.entry,
            "output_mode": self.output_mode,
            "routable": self.routable,
            "config_key": self.config_key,
            "default_script_path": self.default_script_path,
            "script_name": self.script_name,
            "storage_name": self.storage_name,
            "base_dir": self.base_dir,
        }


@dataclass(frozen=True)
class BusinessMatch:
    business_key: str
    service_type: ServiceType
    raw_input: str
    target_text: str = ""
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


def _definition(
    *,
    business_key: str,
    label: str,
    description: str,
    service_type: ServiceType,
    match_type: str,
    default_triggers: tuple[str, ...],
    handler_type: str,
    entry: str = "",
    output_mode: str = "images",
    routable: bool = True,
    base_dir: str = "",
    config_key: str = "",
    default_script_path: str = "",
    script_name: str = "",
    storage_name: str = "",
    copy_assets_from: str = "",
) -> BusinessDefinition:
    return BusinessDefinition(
        business_key=business_key,
        skill_key=business_key,
        service_type=service_type,
        label=label,
        description=description,
        match_type=match_type,
        default_triggers=default_triggers,
        handler_type=handler_type,
        cache_mode=_cache_mode_for_handler(handler_type),
        artifact_roles=_artifact_roles_for_handler(handler_type),
        entry=entry,
        output_mode=output_mode,
        routable=routable,
        base_dir=base_dir,
        config_key=config_key,
        default_script_path=default_script_path,
        script_name=script_name,
        storage_name=storage_name,
        copy_assets_from=copy_assets_from,
    )


BUILTIN_DEFINITIONS: tuple[BusinessDefinition, ...] = (
    _definition(
        business_key="technical-analysis",
        label="技术分析 Skill",
        description="根据股票代码或名称生成技术分析报告、图表和信号卡片。",
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        match_type="suffix",
        default_triggers=("技术分析",),
        handler_type="builtin_technical_analysis",
        entry="skills/技术分析/scripts/analyze_universal.py",
        config_key="technical_analysis.skill_path",
        default_script_path="skills/技术分析/scripts/analyze_universal.py",
        script_name="analyze_universal.py",
        storage_name="technical-analysis",
    ),
    _definition(
        business_key="rate",
        label="利率 Skill",
        description="返回当前生效的利率投研内容图片。",
        service_type=ServiceType.RATE,
        match_type="exact",
        default_triggers=("利率",),
        handler_type="daily_content",
        storage_name="rate",
    ),
    _definition(
        business_key="convertible-bond",
        label="转债 Skill",
        description="返回当前生效的可转债投研内容图片。",
        service_type=ServiceType.CONVERTIBLE_BOND,
        match_type="exact",
        default_triggers=("转债",),
        handler_type="daily_content",
        storage_name="convertible-bond",
    ),
    _definition(
        business_key="signal-card-renderer",
        label="图片生成 Skill",
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
        copy_assets_from="skills/signal-card-renderer/assets",
    ),
)


def uploaded_business_root() -> Path:
    from business.investment.storage import get_storage_dirs

    return get_storage_dirs()["root"] / "investment-skills"


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


def validate_business_key(business_key: str) -> str:
    normalized = str(business_key or "").strip()
    if not SAFE_BUSINESS_KEY_RE.fullmatch(normalized):
        raise ValueError(f"unsafe investment skill key: {business_key}")
    return normalized


def read_uploaded_business_definition(skill_dir: Path) -> BusinessDefinition | None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return None
    frontmatter = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    investment = frontmatter.get("investment") or {}
    if not isinstance(investment, dict):
        return None
    business_key = validate_business_key(frontmatter.get("name") or skill_dir.name)
    entry = str(investment.get("entry") or "").strip()
    handler_type = str(investment.get("handler_type") or "script")
    return _definition(
        business_key=business_key,
        label=str(investment.get("label") or business_key),
        description=str(frontmatter.get("description") or ""),
        service_type=normalize_service(str(investment.get("service_type") or "unmatched")),
        match_type=str(investment.get("match_type") or "exact"),
        default_triggers=_normalize_triggers(investment.get("triggers")),
        handler_type=handler_type,
        entry=entry,
        output_mode=str(investment.get("output_mode") or "mixed"),
        routable=_bool_value(investment.get("routable"), True),
        base_dir=str(skill_dir),
        config_key=str(investment.get("config_key") or ""),
        default_script_path=str((skill_dir / entry).resolve()) if entry else "",
        script_name=Path(entry).name if entry else "",
        storage_name=business_key,
    )


def list_business_definitions() -> list[BusinessDefinition]:
    definitions = {definition.business_key: definition for definition in BUILTIN_DEFINITIONS}
    root = uploaded_business_root()
    if root.is_dir():
        for skill_dir in sorted(item for item in root.iterdir() if item.is_dir() and not item.name.startswith(".")):
            definition = read_uploaded_business_definition(skill_dir)
            if definition is not None:
                definitions[definition.business_key] = definition
    return list(definitions.values())


def get_business_definition(business_key: str) -> BusinessDefinition:
    for definition in list_business_definitions():
        if definition.business_key == business_key:
            return definition
    raise ValueError(f"unsupported business: {business_key}")


def is_business_enabled(definition: BusinessDefinition) -> bool:
    return _bool_value(get_config(definition.enabled_config_key, True), True)


def resolve_triggers(definition: BusinessDefinition) -> tuple[str, ...]:
    raw = get_config(definition.triggers_config_key, list(definition.default_triggers))
    return _normalize_triggers(raw)


def match_business(raw_input: str) -> BusinessMatch | None:
    text = (raw_input or "").strip()
    if not text:
        return None
    for definition in list_business_definitions():
        if not definition.routable or not is_business_enabled(definition):
            continue
        triggers = resolve_triggers(definition)
        if definition.match_type == "exact" and text in triggers:
            return BusinessMatch(
                definition.business_key,
                definition.service_type,
                raw_input,
                skill_key=definition.skill_key or definition.business_key,
            )
        if definition.match_type == "suffix":
            for trigger in triggers:
                if not trigger or not text.endswith(trigger):
                    continue
                target = text[: -len(trigger)].strip()
                if target:
                    return BusinessMatch(
                        definition.business_key,
                        definition.service_type,
                        raw_input,
                        target,
                        definition.skill_key or definition.business_key,
                    )
    return None
