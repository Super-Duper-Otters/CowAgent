# encoding:utf-8
"""CowAgent built-in business definitions and intent matching."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.skills.frontmatter import parse_frontmatter

from business.config.config_service import get_config
from business.config.constants import ServiceType, normalize_service
from business.components.paths import builtin_components_root, runtime_components_root
from business.content.render_service import DEFAULT_RENDERER_PATH


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
    component_type: str = ""
    prompt_key: str = ""
    renderer_component_key: str = ""
    template_key: str = ""
    generation_mode: str = ""
    delivery_mode: str = "direct"
    content_enabled: bool = False
    creation_method: str = "builtin"
    execution: dict[str, Any] = field(default_factory=dict)
    postprocess: dict[str, Any] = field(default_factory=dict)
    reply: dict[str, Any] = field(default_factory=dict)
    archive: dict[str, Any] = field(default_factory=dict)
    prompt: dict[str, Any] = field(default_factory=dict)

    @property
    def enabled_config_key(self) -> str:
        return f"skill.{self.business_key}.enabled"

    @property
    def triggers_config_key(self) -> str:
        return f"skill.{self.business_key}.triggers"

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
            "component_type": self.component_type,
            "prompt_key": self.prompt_key,
            "renderer_component_key": self.renderer_component_key,
            "template_key": self.template_key,
            "generation_mode": self.generation_mode,
            "delivery_mode": self.delivery_mode,
            "content_enabled": self.content_enabled,
            "creation_method": self.creation_method,
            "execution": self.execution,
            "postprocess": self.postprocess,
            "reply": self.reply,
            "archive": self.archive,
            "prompt": self.prompt,
            "uses_triggers": self.uses_triggers,
            "versioned": self.versioned,
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


def _generation_mode_for_handler(handler_type: str) -> str:
    if handler_type == "daily_content":
        return "pre_generated"
    if handler_type in {"technical_analysis", "builtin_technical_analysis", "prompt_to_image"}:
        return "on_demand"
    return ""


def _delivery_mode_for_handler(handler_type: str) -> str:
    if handler_type in {"technical_analysis", "builtin_technical_analysis", "prompt_to_image"}:
        return "deferred"
    return "direct"


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
    component_type: str = "",
    prompt_key: str = "",
    renderer_component_key: str = "",
    template_key: str = "",
    generation_mode: str | None = None,
    delivery_mode: str | None = None,
    content_enabled: bool | None = None,
    creation_method: str = "builtin",
    execution: dict[str, Any] | None = None,
    postprocess: dict[str, Any] | None = None,
    reply: dict[str, Any] | None = None,
    archive: dict[str, Any] | None = None,
    prompt: dict[str, Any] | None = None,
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
        component_type=component_type,
        prompt_key=prompt_key,
        renderer_component_key=renderer_component_key,
        template_key=template_key,
        generation_mode=generation_mode if generation_mode is not None else _generation_mode_for_handler(handler_type),
        delivery_mode=delivery_mode if delivery_mode is not None else _delivery_mode_for_handler(handler_type),
        content_enabled=content_enabled if content_enabled is not None else handler_type == "daily_content",
        creation_method=creation_method,
        execution=execution or {},
        postprocess=postprocess or {},
        reply=reply or {},
        archive=archive or {},
        prompt=prompt or {},
    )


BUILTIN_DEFINITIONS: tuple[BusinessDefinition, ...] = (
    _definition(
        business_key="technical-analysis",
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
    _definition(
        business_key="rate",
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
    _definition(
        business_key="convertible-bond",
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
    _definition(
        business_key="signal-card-renderer",
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


def _optional_str_value(data: dict, key: str) -> str | None:
    if key not in data:
        return None
    value = data.get(key)
    if value is None:
        return None
    return str(value)


def _default_creation_method(component_dir: Path) -> str:
    try:
        if component_dir.resolve().is_relative_to(builtin_components_root().resolve()):
            return "builtin"
    except ValueError:
        pass
    return "runtime"


def _contains_markdown_link(raw_input: str) -> bool:
    return bool(re.search(r"\[[^\]]+\]\([^)]+\)", raw_input or ""))


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
    routable = _bool_value(investment.get("routable"), True)
    component_type = str(investment.get("component_type") or "").strip()
    if not component_type and handler_type == "script":
        component_type = "active_script" if routable else "passive_script"
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
        routable=routable,
        base_dir=str(skill_dir),
        config_key=str(investment.get("config_key") or ""),
        default_script_path=str((skill_dir / entry).resolve()) if entry else "",
        script_name=Path(entry).name if entry else "",
        storage_name=business_key,
        component_type=component_type,
        generation_mode=_optional_str_value(investment, "generation_mode"),
        delivery_mode=_optional_str_value(investment, "delivery_mode"),
        content_enabled=_bool_value(investment.get("content_enabled"), False) if "content_enabled" in investment else None,
    )


def read_component_definition(component_dir: Path) -> BusinessDefinition | None:
    manifest_path = component_dir / "component.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(manifest, dict):
        return None

    business_key = validate_business_key(str(manifest.get("component_key") or component_dir.name))
    entry = str(manifest.get("entry") or "").strip()
    handler_type = str(manifest.get("handler_type") or "script")
    routable = _bool_value(manifest.get("routable"), True)
    component_type = str(manifest.get("component_type") or "").strip()
    if not component_type and handler_type == "script":
        component_type = "active_script" if routable else "passive_script"

    script_name = str(manifest.get("script_name") or (Path(entry).name if entry else ""))
    default_script_path = str((component_dir / entry).resolve()) if entry else ""
    return _definition(
        business_key=business_key,
        label=str(manifest.get("label") or business_key),
        description=str(manifest.get("description") or ""),
        service_type=normalize_service(str(manifest.get("service_type") or "unmatched")),
        match_type=str(manifest.get("match_type") or "exact"),
        default_triggers=_normalize_triggers(manifest.get("default_triggers") or manifest.get("triggers")),
        handler_type=handler_type,
        entry=entry,
        output_mode=str(manifest.get("output_mode") or "mixed"),
        routable=routable,
        base_dir=str(component_dir),
        config_key=str(manifest.get("config_key") or ""),
        default_script_path=default_script_path,
        script_name=script_name,
        storage_name=str(manifest.get("storage_name") or business_key),
        copy_assets_from=str(manifest.get("copy_assets_from") or ""),
        component_type=component_type,
        prompt_key=str(manifest.get("prompt_key") or ""),
        renderer_component_key=str(manifest.get("renderer_component_key") or ""),
        template_key=str(manifest.get("template_key") or ""),
        generation_mode=_optional_str_value(manifest, "generation_mode"),
        delivery_mode=_optional_str_value(manifest, "delivery_mode"),
        content_enabled=_bool_value(manifest.get("content_enabled"), False) if "content_enabled" in manifest else None,
        creation_method=str(manifest.get("creation_method") or _default_creation_method(component_dir)),
        execution=manifest.get("execution") if isinstance(manifest.get("execution"), dict) else None,
        postprocess=manifest.get("postprocess") if isinstance(manifest.get("postprocess"), dict) else None,
        reply=manifest.get("reply") if isinstance(manifest.get("reply"), dict) else None,
        archive=manifest.get("archive") if isinstance(manifest.get("archive"), dict) else None,
        prompt=manifest.get("prompt") if isinstance(manifest.get("prompt"), dict) else None,
    )


def _merge_component_definitions(definitions: dict[str, BusinessDefinition], root: Path) -> None:
    if not root.is_dir():
        return
    for component_dir in sorted(item for item in root.iterdir() if item.is_dir() and not item.name.startswith(".")):
        definition = read_component_definition(component_dir)
        if definition is None:
            definition = _read_active_version_component_definition(component_dir)
        if definition is not None:
            definitions[definition.business_key] = definition


def _read_active_version_component_definition(component_dir: Path) -> BusinessDefinition | None:
    versions_dir = component_dir / "versions"
    if not versions_dir.is_dir():
        return None
    for version_dir in sorted(item for item in versions_dir.iterdir() if item.is_dir()):
        definition = read_component_definition(version_dir)
        if definition is None:
            continue
        if definition.config_key and definition.entry:
            configured = str(get_config(definition.config_key, "") or "")
            configured_path = Path(configured) if configured else Path("")
            active_script = version_dir / definition.entry
            if configured_path and configured_path == active_script:
                return definition
    return None


def list_business_definitions() -> list[BusinessDefinition]:
    definitions = {definition.business_key: definition for definition in BUILTIN_DEFINITIONS}
    _merge_component_definitions(definitions, builtin_components_root())
    _merge_component_definitions(definitions, runtime_components_root())
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
    if _contains_markdown_link(raw_input):
        return None
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
        if definition.match_type == "prefix":
            for trigger in triggers:
                if not trigger or not text.startswith(trigger):
                    continue
                target = text[len(trigger):].strip()
                return BusinessMatch(
                    definition.business_key,
                    definition.service_type,
                    raw_input,
                    target,
                    definition.skill_key or definition.business_key,
                )
    return None
