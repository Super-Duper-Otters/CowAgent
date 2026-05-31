# encoding:utf-8
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.skills.frontmatter import parse_frontmatter

from .config_service import get_config
from .constants import ServiceType, normalize_service
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

    @property
    def enabled_config_key(self) -> str:
        return f"skill.{self.skill_key}.enabled"

    @property
    def triggers_config_key(self) -> str:
        return f"skill.{self.skill_key}.triggers"

    @property
    def script_relative_path(self) -> Path:
        return Path("scripts") / self.script_name

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
    InvestmentSkillDefinition(
        skill_key="rate",
        label="利率 Skill",
        description="返回当前生效的利率投研内容图片。",
        service_type=ServiceType.RATE,
        match_type="exact",
        default_triggers=("利率",),
        handler_type="daily_content",
        storage_name="rate",
    ),
    InvestmentSkillDefinition(
        skill_key="convertible-bond",
        label="转债 Skill",
        description="返回当前生效的可转债投研内容图片。",
        service_type=ServiceType.CONVERTIBLE_BOND,
        match_type="exact",
        default_triggers=("转债",),
        handler_type="daily_content",
        storage_name="convertible-bond",
    ),
    InvestmentSkillDefinition(
        skill_key="signal-card-renderer",
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


def _uploaded_skill_root() -> Path:
    from .storage import get_storage_dirs

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


def validate_skill_key(skill_key: str) -> str:
    normalized = str(skill_key or "").strip()
    if not SAFE_SKILL_KEY_RE.fullmatch(normalized):
        raise ValueError(f"unsafe investment skill key: {skill_key}")
    return normalized


def _read_uploaded_definition(skill_dir: Path) -> InvestmentSkillDefinition | None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return None
    frontmatter = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    investment = frontmatter.get("investment") or {}
    if not isinstance(investment, dict):
        return None
    skill_key = validate_skill_key(frontmatter.get("name") or skill_dir.name)
    if not skill_key:
        return None
    entry = str(investment.get("entry") or "").strip()
    return InvestmentSkillDefinition(
        skill_key=skill_key,
        label=str(investment.get("label") or skill_key),
        description=str(frontmatter.get("description") or ""),
        service_type=normalize_service(str(investment.get("service_type") or "unmatched")),
        match_type=str(investment.get("match_type") or "exact"),
        default_triggers=_normalize_triggers(investment.get("triggers")),
        handler_type=str(investment.get("handler_type") or "script"),
        entry=entry,
        output_mode=str(investment.get("output_mode") or "mixed"),
        routable=_bool_value(investment.get("routable"), True),
        base_dir=str(skill_dir),
        config_key=str(investment.get("config_key") or ""),
        default_script_path=str((skill_dir / entry).resolve()) if entry else "",
        script_name=Path(entry).name if entry else "",
        storage_name=skill_key,
    )


def list_definitions() -> list[InvestmentSkillDefinition]:
    definitions = {definition.skill_key: definition for definition in BUILTIN_DEFINITIONS}
    root = _uploaded_skill_root()
    if root.is_dir():
        for skill_dir in sorted(item for item in root.iterdir() if item.is_dir() and not item.name.startswith(".")):
            definition = _read_uploaded_definition(skill_dir)
            if definition is not None:
                definitions[definition.skill_key] = definition
    return list(definitions.values())


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
    text = (raw_input or "").strip()
    if not text:
        return None
    for definition in list_definitions():
        if not definition.routable or not is_skill_enabled(definition):
            continue
        triggers = resolve_triggers(definition)
        if definition.match_type == "exact" and text in triggers:
            return InvestmentSkillMatch(definition.skill_key, definition.service_type, raw_input)
        if definition.match_type == "suffix":
            for trigger in triggers:
                if not trigger or not text.endswith(trigger):
                    continue
                target = text[: -len(trigger)].strip()
                if target:
                    return InvestmentSkillMatch(definition.skill_key, definition.service_type, raw_input, target)
    return None
