# encoding:utf-8
"""Investment component view and settings helpers."""

import json
import shutil
from pathlib import Path

from business.components.registry import (
    get_business_definition,
    is_business_enabled,
    list_business_definitions,
    resolve_triggers,
)

from business.config.config_service import get_config, save_config
from business.components.paths import runtime_component_root, runtime_components_root
from business.components.skill_versions import list_versions
from business.content.technical_analysis_card_config import (
    TECHNICAL_ANALYSIS_CARD_FOOTER_CONFIG_KEYS,
    technical_analysis_card_footer_config,
)

TECHNICAL_ANALYSIS_PROMPT_BLOCKS_CONFIG_KEY = "prompt.technical_analysis.blocks"


def _is_runtime_component(definition) -> bool:
    base_dir = str(getattr(definition, "base_dir", "") or "")
    if not base_dir:
        return False
    try:
        return Path(base_dir).resolve().is_relative_to(runtime_components_root().resolve())
    except ValueError:
        return False


def _component_settings(definition) -> dict:
    settings = {"enabled": is_business_enabled(definition)}
    if definition.business_key == "technical-analysis":
        settings["allow_unresolved_bare_code_analysis"] = bool(
            get_config("technical_analysis.allow_unresolved_bare_code_analysis", False)
        )
        settings["card_footer"] = technical_analysis_card_footer_config()
    if definition.uses_triggers:
        settings["triggers"] = list(resolve_triggers(definition))
    if definition.prompt_key:
        from business.audit.ai_generation import TECHNICAL_ANALYSIS_PROMPT_BLOCKS, default_prompt_for_service

        configured_prompt = get_config(definition.prompt_key, None)
        default_prompt = ""
        try:
            default_prompt = default_prompt_for_service(definition.service_type)
        except (KeyError, ValueError):
            default_prompt = ""
        effective_prompt = configured_prompt if isinstance(configured_prompt, str) and configured_prompt.strip() else default_prompt
        settings["prompt_key"] = definition.prompt_key
        settings["prompt"] = effective_prompt if isinstance(effective_prompt, str) else str(effective_prompt or "")
        settings["prompt_configured"] = bool(isinstance(configured_prompt, str) and configured_prompt.strip())
        if default_prompt:
            settings["default_prompt"] = default_prompt
        if definition.business_key == "technical-analysis":
            configured_blocks = get_config(TECHNICAL_ANALYSIS_PROMPT_BLOCKS_CONFIG_KEY, None)
            block_values = configured_blocks if isinstance(configured_blocks, dict) else {}
            settings["prompt_blocks"] = [
                {
                    "key": key,
                    "label": block["label"],
                    "text": str(block_values.get(key) or block["text"]),
                }
                for key, block in TECHNICAL_ANALYSIS_PROMPT_BLOCKS.items()
            ]
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
        item["generation_mode"] = definition.generation_mode
        item["delivery_mode"] = definition.delivery_mode
        item["content_enabled"] = definition.content_enabled
        item["creation_method"] = definition.creation_method
        item["prompt"] = definition.prompt
        item["runtime"] = _is_runtime_component(definition)
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


def _read_component_manifest(component_key: str) -> dict:
    path = runtime_component_root(component_key) / "component.json"
    if not path.is_file():
        raise ValueError("component config can only be edited for runtime command components")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("runtime component manifest is invalid") from exc
    if not isinstance(data, dict):
        raise ValueError("runtime component manifest is invalid")
    return data


def _write_component_manifest(component_key: str, manifest: dict) -> None:
    path = runtime_component_root(component_key) / "component.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_outputs(value) -> list[str]:
    if isinstance(value, str):
        items = value.replace("，", ",").split(",")
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        items = []
    return [str(item).strip() for item in items if str(item).strip()]


def _validate_execution_config(component_type: str, execution: dict) -> dict:
    if not isinstance(execution, dict):
        raise ValueError("execution config must be an object")
    command = execution.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(item, str) and item.strip() for item in command):
        raise ValueError("execution.command must be a non-empty string array")
    outputs = execution.get("outputs")
    if not isinstance(outputs, dict) or not outputs:
        raise ValueError("execution.outputs must be a non-empty object")
    normalized_outputs = {}
    for name, spec in outputs.items():
        output_name = str(name or "").strip()
        if not output_name or not isinstance(spec, dict):
            raise ValueError("execution output definitions are invalid")
        output_type = str(spec.get("type") or "").strip()
        pattern = str(spec.get("pattern") or "").strip()
        if not output_type or not pattern:
            raise ValueError("execution output type and pattern are required")
        normalized_outputs[output_name] = {"type": output_type, "pattern": pattern}
    default_output = str(execution.get("default_output") or "").strip()
    if component_type == "active_script" and default_output not in normalized_outputs:
        raise ValueError("active command component requires a default output")
    return {
        "command": [str(item).strip() for item in command],
        "outputs": normalized_outputs,
        "default_output": default_output,
    }


def _validate_prompt_config(prompt: dict) -> dict:
    if not isinstance(prompt, dict):
        raise ValueError("prompt config must be an object")
    template = str(prompt.get("template") or "").strip()
    if not template:
        raise ValueError("prompt.template is required")
    output_type = str(prompt.get("output_type") or "markdown").strip() or "markdown"
    if output_type not in {"text", "markdown"}:
        raise ValueError("prompt.output_type must be text or markdown")
    return {"template": template, "output_type": output_type}


def _update_runtime_command_component_manifest(definition, values: dict) -> None:
    updates = values.get("component_config")
    if updates is None:
        return
    if not isinstance(updates, dict):
        raise ValueError("component_config must be an object")
    if not _is_runtime_component(definition) or definition.handler_type != "command_script":
        raise ValueError("component config can only be edited for runtime command components")

    manifest = _read_component_manifest(definition.business_key)
    component_type = str(manifest.get("component_type") or definition.component_type or "")
    if "label" in updates:
        manifest["label"] = str(updates.get("label") or "").strip() or manifest.get("label") or definition.business_key
    if "description" in updates:
        manifest["description"] = str(updates.get("description") or "")
    if "match_type" in updates:
        match_type = str(updates.get("match_type") or "").strip()
        if match_type not in {"exact", "prefix", "suffix"}:
            raise ValueError("match_type must be exact, prefix, or suffix")
        manifest["match_type"] = match_type
    if "execution" in updates:
        manifest["execution"] = _validate_execution_config(component_type, updates.get("execution"))
    for key in ("postprocess", "reply", "archive"):
        if key not in updates:
            continue
        value = updates.get(key)
        if not isinstance(value, dict):
            raise ValueError(f"{key} config must be an object")
        if key in {"reply", "archive"}:
            manifest[key] = {"outputs": _normalize_outputs(value.get("outputs"))}
        else:
            manifest[key] = {
                "enabled": bool(value.get("enabled")),
                "component_key": str(value.get("component_key") or "").strip(),
                "input": str(value.get("input") or "").strip(),
                "output": str(value.get("output") or "").strip(),
            }
    _write_component_manifest(definition.business_key, manifest)


def _update_runtime_prompt_component_manifest(definition, values: dict) -> None:
    updates = values.get("component_config")
    if updates is None:
        return
    if not isinstance(updates, dict):
        raise ValueError("component_config must be an object")
    if not _is_runtime_component(definition) or definition.handler_type != "prompt_component":
        raise ValueError("component config can only be edited for runtime prompt components")

    manifest = _read_component_manifest(definition.business_key)
    if "label" in updates:
        manifest["label"] = str(updates.get("label") or "").strip() or manifest.get("label") or definition.business_key
    if "description" in updates:
        manifest["description"] = str(updates.get("description") or "")
    if "match_type" in updates:
        match_type = str(updates.get("match_type") or "").strip()
        if match_type not in {"exact", "prefix", "suffix"}:
            raise ValueError("match_type must be exact, prefix, or suffix")
        manifest["match_type"] = match_type
    if "prompt" in updates:
        manifest["prompt"] = _validate_prompt_config(updates.get("prompt"))
    if "reply" in updates:
        value = updates.get("reply")
        if not isinstance(value, dict):
            raise ValueError("reply config must be an object")
        manifest["reply"] = {"outputs": _normalize_outputs(value.get("outputs")) or ["text"]}
    if "archive" in updates:
        value = updates.get("archive")
        if not isinstance(value, dict):
            raise ValueError("archive config must be an object")
        manifest["archive"] = {"outputs": _normalize_outputs(value.get("outputs")) or ["text"]}
    _write_component_manifest(definition.business_key, manifest)


def create_prompt_component(
    values: dict,
    *,
    operator_role: str = "admin",
    operator: str = "web-console",
    actor=None,
    creation_method: str = "manual_prompt",
) -> dict:
    from business.components.registry import validate_business_key

    if not isinstance(values, dict):
        raise ValueError("component payload must be an object")
    component_key = validate_business_key(str(values.get("component_key") or "").strip())
    triggers = _normalize_triggers(values.get("default_triggers") or values.get("triggers"))
    if not triggers:
        raise ValueError("active prompt component triggers cannot be empty")
    match_type = str(values.get("match_type") or "suffix").strip()
    if match_type not in {"exact", "prefix", "suffix"}:
        raise ValueError("match_type must be exact, prefix, or suffix")
    prompt = _validate_prompt_config(values.get("prompt") if isinstance(values.get("prompt"), dict) else {})

    component_dir = runtime_component_root(component_key)
    component_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "component_key": component_key,
        "label": str(values.get("label") or component_key).strip() or component_key,
        "description": str(values.get("description") or ""),
        "creation_method": creation_method,
        "service_type": str(values.get("service_type") or "unmatched"),
        "component_type": "active_prompt",
        "handler_type": "prompt_component",
        "routable": True,
        "match_type": match_type,
        "default_triggers": triggers,
        "prompt": prompt,
        "reply": {"outputs": ["text"]},
        "archive": {"outputs": ["text"]},
    }
    _write_component_manifest(component_key, manifest)
    save_config(
        f"skill.{component_key}.enabled",
        bool(values.get("enabled", True)),
        operator_role=operator_role,
        operator=operator,
        actor=actor,
    )
    save_config(
        f"skill.{component_key}.triggers",
        triggers,
        operator_role=operator_role,
        operator=operator,
        actor=actor,
    )
    return next(item for item in list_components() if item["component_key"] == component_key)


def save_component_settings(
    component_key: str,
    values: dict,
    *,
    operator_role: str,
    operator: str,
    actor=None,
) -> dict:
    definition = get_business_definition(component_key)

    if values.get("reset_defaults") is True:
        save_config(
            definition.enabled_config_key,
            True,
            operator_role=operator_role,
            operator=operator,
            actor=actor,
        )
        if definition.uses_triggers:
            save_config(
                definition.triggers_config_key,
                list(definition.default_triggers),
                operator_role=operator_role,
                operator=operator,
                actor=actor,
            )
        if definition.prompt_key:
            from business.audit.ai_generation import TECHNICAL_ANALYSIS_PROMPT_BLOCKS, default_prompt_for_service

            default_prompt = default_prompt_for_service(definition.service_type)
            save_config(
                definition.prompt_key,
                default_prompt,
                operator_role=operator_role,
                operator=operator,
                actor=actor,
            )
            if definition.business_key == "technical-analysis":
                save_config(
                    TECHNICAL_ANALYSIS_PROMPT_BLOCKS_CONFIG_KEY,
                    {key: block["text"] for key, block in TECHNICAL_ANALYSIS_PROMPT_BLOCKS.items()},
                    operator_role=operator_role,
                    operator=operator,
                    actor=actor,
                )
        if definition.business_key == "technical-analysis":
            save_config(
                "technical_analysis.allow_unresolved_bare_code_analysis",
                False,
                operator_role=operator_role,
                operator=operator,
                actor=actor,
            )
            from business.content.technical_analysis_card_config import TECHNICAL_ANALYSIS_CARD_FOOTER_DEFAULTS

            for field, config_key in TECHNICAL_ANALYSIS_CARD_FOOTER_CONFIG_KEYS.items():
                save_config(
                    config_key,
                    TECHNICAL_ANALYSIS_CARD_FOOTER_DEFAULTS[field],
                    operator_role=operator_role,
                    operator=operator,
                    actor=actor,
                )
        return next(item for item in list_components() if item["component_key"] == component_key)

    if values.get("component_config") is not None:
        if definition.handler_type == "command_script":
            _update_runtime_command_component_manifest(definition, values)
        elif definition.handler_type == "prompt_component":
            _update_runtime_prompt_component_manifest(definition, values)
        else:
            raise ValueError("component config can only be edited for runtime command components or runtime prompt components")

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

    if "prompt_blocks" in values:
        if definition.business_key != "technical-analysis" or not definition.prompt_key:
            raise ValueError("component does not accept prompt blocks")
        from business.audit.ai_generation import TECHNICAL_ANALYSIS_PROMPT_BLOCKS

        raw_blocks = values.get("prompt_blocks")
        if not isinstance(raw_blocks, dict):
            raise ValueError("prompt_blocks must be an object")
        block_values = {}
        prompt_parts = []
        for key, block in TECHNICAL_ANALYSIS_PROMPT_BLOCKS.items():
            value = str(raw_blocks.get(key) or block["text"])
            block_values[key] = value
            prompt_parts.append(value)
        save_config(
            TECHNICAL_ANALYSIS_PROMPT_BLOCKS_CONFIG_KEY,
            block_values,
            operator_role=operator_role,
            operator=operator,
            actor=actor,
        )
        save_config(
            definition.prompt_key,
            "".join(prompt_parts),
            operator_role=operator_role,
            operator=operator,
            actor=actor,
        )

    if "allow_unresolved_bare_code_analysis" in values:
        if definition.business_key != "technical-analysis":
            raise ValueError("component does not accept unresolved bare code analysis setting")
        save_config(
            "technical_analysis.allow_unresolved_bare_code_analysis",
            bool(values.get("allow_unresolved_bare_code_analysis")),
            operator_role=operator_role,
            operator=operator,
            actor=actor,
        )

    if "card_footer" in values:
        if definition.business_key != "technical-analysis":
            raise ValueError("component does not accept card footer setting")
        footer = values.get("card_footer")
        if not isinstance(footer, dict):
            raise ValueError("card_footer must be an object")
        for field, config_key in TECHNICAL_ANALYSIS_CARD_FOOTER_CONFIG_KEYS.items():
            if field not in footer:
                continue
            save_config(
                config_key,
                str(footer.get(field) or "").strip(),
                operator_role=operator_role,
                operator=operator,
                actor=actor,
            )

    return next(item for item in list_components() if item["component_key"] == component_key)


def delete_runtime_component(
    component_key: str,
    *,
    operator_role: str = "admin",
    operator: str = "web-console",
    actor=None,
) -> dict:
    definition = get_business_definition(component_key)
    target = runtime_component_root(component_key)
    if not target.is_dir() or not _is_runtime_component(definition):
        raise ValueError("builtin component cannot be deleted")

    shutil.rmtree(target, ignore_errors=False)
    return {
        "component_key": component_key,
        "storage_path": str(target),
        "deleted": True,
    }
