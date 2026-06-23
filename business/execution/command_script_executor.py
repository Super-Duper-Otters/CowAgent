# encoding:utf-8
"""Command-array executor for imported investment script components."""

import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from business.config.constants import ErrorCode
from business.schema.storage import get_storage_dirs


@dataclass(frozen=True)
class CommandOutput:
    name: str
    type: str
    path: str
    text: str = ""


@dataclass
class CommandScriptRunResult:
    success: bool
    reply_text: str = ""
    reply_files: list[str] = field(default_factory=list)
    archive_files: list[str] = field(default_factory=list)
    outputs: dict[str, CommandOutput] = field(default_factory=dict)
    artifact_roles: dict[str, str] = field(default_factory=dict)
    error_code: ErrorCode | None = None
    user_prompt: str = ""
    detail: str = ""


def _run_root() -> Path:
    root = get_storage_dirs()["tmp"] / "component-runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _new_work_dir(component_key: str) -> Path:
    safe_component = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in component_key) or "component"
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    work_dir = _run_root() / safe_component / f"run-{stamp}-{uuid.uuid4().hex[:8]}"
    work_dir.mkdir(parents=True, exist_ok=False)
    return work_dir


def _configured_entry(definition: Any) -> Path:
    config_key = str(getattr(definition, "config_key", "") or "")
    configured = ""
    if config_key:
        from business.config.config_service import get_config

        configured = str(get_config(config_key, "") or "")
    raw_entry = configured or str(getattr(definition, "default_script_path", "") or getattr(definition, "entry", "") or "")
    entry = Path(raw_entry)
    if not entry.is_absolute():
        base_dir = str(getattr(definition, "base_dir", "") or "")
        entry = (Path(base_dir) / entry) if base_dir else (Path.cwd() / entry)
    return entry.resolve()


def _render_token(token: str, variables: dict[str, str]) -> str:
    rendered = str(token)
    for key, value in variables.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def _render_command(command: list[Any], variables: dict[str, str]) -> list[str]:
    rendered = [_render_token(str(token), variables) for token in command]
    if rendered and rendered[0].lower() in {"python", "python3"}:
        rendered[0] = sys.executable
    return rendered


def _run_command(entry: Path, command_template: list[Any], variables: dict[str, str]) -> subprocess.CompletedProcess:
    command = _render_command(command_template, variables | {"entry": str(entry)})
    return subprocess.run(command, cwd=str(entry.parent), capture_output=True, text=True, check=False)


def _read_output_text(path: Path, output_type: str) -> str:
    if output_type in {"text", "markdown"}:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    return ""


def _collect_outputs(work_dir: Path, execution: dict) -> dict[str, CommandOutput]:
    outputs: dict[str, CommandOutput] = {}
    specs = execution.get("outputs") if isinstance(execution.get("outputs"), dict) else {}
    for name, spec in specs.items():
        if not isinstance(spec, dict):
            continue
        pattern = str(spec.get("pattern") or "").strip()
        if not pattern:
            continue
        matches = sorted(path for path in work_dir.glob(pattern) if path.is_file())
        if not matches:
            continue
        path = matches[0]
        output_type = str(spec.get("type") or "file")
        outputs[str(name)] = CommandOutput(
            name=str(name),
            type=output_type,
            path=str(path),
            text=_read_output_text(path, output_type),
        )
    return outputs


def _run_postprocess(
    definition: Any,
    work_dir: Path,
    outputs: dict[str, CommandOutput],
    raw_input: str,
    target_text: str,
    openid: str,
) -> tuple[CommandOutput | None, str]:
    postprocess = getattr(definition, "postprocess", {}) if isinstance(getattr(definition, "postprocess", {}), dict) else {}
    if not postprocess.get("enabled"):
        return None, ""
    input_name = str(postprocess.get("input") or "").strip()
    output_name = str(postprocess.get("output") or "processed").strip()
    component_key = str(postprocess.get("component_key") or "").strip()
    source = outputs.get(input_name)
    if not component_key or source is None:
        return None, "postprocess component or input is missing"
    input_text = source.text
    if not input_text and source.path:
        input_text = Path(source.path).read_text(encoding="utf-8", errors="replace")

    from business.components.registry import get_business_definition

    passive = get_business_definition(component_key)
    if getattr(passive, "routable", True):
        return None, "postprocess component must be passive"
    execution = getattr(passive, "execution", {}) if isinstance(getattr(passive, "execution", {}), dict) else {}
    command_template = execution.get("command")
    if not isinstance(command_template, list) or not command_template:
        return None, "postprocess component requires command array"
    entry = _configured_entry(passive)
    if not entry.is_file():
        return None, f"postprocess entry script not found: {entry}"

    passive_work_dir = work_dir / output_name
    passive_work_dir.mkdir(parents=True, exist_ok=True)
    output_file = passive_work_dir / f"{output_name}.png"
    completed = _run_command(
        entry,
        command_template,
        {
            "raw_input": raw_input,
            "target_text": target_text,
            "openid": openid,
            "work_dir": str(passive_work_dir),
            "input_text": input_text,
            "output_file": str(output_file),
        },
    )
    if completed.returncode != 0:
        return None, (completed.stderr or completed.stdout or f"postprocess exited with {completed.returncode}").strip()
    passive_outputs = _collect_outputs(passive_work_dir, execution)
    produced = next(iter(passive_outputs.values()), None)
    if produced is None and output_file.is_file():
        produced = CommandOutput(output_name, "image", str(output_file))
    if produced is None:
        return None, f"postprocess output missing: {output_name}"
    return CommandOutput(output_name, produced.type, produced.path, produced.text), ""


def _selected_outputs(config: dict, fallback: list[str]) -> list[str]:
    outputs = config.get("outputs") if isinstance(config, dict) else None
    if isinstance(outputs, str):
        outputs = [item.strip() for item in outputs.replace("，", ",").split(",")]
    if not isinstance(outputs, list):
        outputs = fallback
    return [str(item).strip() for item in outputs if str(item).strip()]


def run_command_script_component(
    definition: Any,
    openid: str,
    raw_input: str,
    target_text: str,
) -> CommandScriptRunResult:
    execution = getattr(definition, "execution", {}) if isinstance(getattr(definition, "execution", {}), dict) else {}
    command_template = execution.get("command")
    if not isinstance(command_template, list) or not command_template:
        return CommandScriptRunResult(False, error_code=ErrorCode.SYSTEM_ERROR, detail="command script execution requires command array")

    component_key = str(getattr(definition, "business_key", "") or getattr(definition, "skill_key", "") or "component")
    work_dir = _new_work_dir(component_key)
    entry = _configured_entry(definition)
    if not entry.is_file():
        return CommandScriptRunResult(False, error_code=ErrorCode.SYSTEM_ERROR, detail=f"entry script not found: {entry}")

    try:
        completed = _run_command(
            entry,
            command_template,
            {
                "raw_input": raw_input,
                "target_text": target_text,
                "openid": openid,
                "work_dir": str(work_dir),
            },
        )
    except Exception as exc:
        return CommandScriptRunResult(False, error_code=ErrorCode.SYSTEM_ERROR, detail=str(exc))
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or f"command exited with {completed.returncode}").strip()
        return CommandScriptRunResult(False, error_code=ErrorCode.SYSTEM_ERROR, detail=detail)

    outputs = _collect_outputs(work_dir, execution)
    default_name = str(execution.get("default_output") or "").strip()
    default_output = outputs.get(default_name)
    if not default_output:
        return CommandScriptRunResult(False, error_code=ErrorCode.SYSTEM_ERROR, detail=f"default output missing: {default_name}")

    processed_output, postprocess_error = _run_postprocess(definition, work_dir, outputs, raw_input, target_text, openid)
    if postprocess_error:
        return CommandScriptRunResult(False, error_code=ErrorCode.SYSTEM_ERROR, detail=postprocess_error)
    if processed_output is not None:
        outputs[processed_output.name] = processed_output

    reply_names = _selected_outputs(getattr(definition, "reply", {}) or {}, [default_name])
    archive_names = _selected_outputs(getattr(definition, "archive", {}) or {}, list(outputs.keys()))
    reply_text_parts: list[str] = []
    reply_files: list[str] = []
    archive_files: list[str] = []
    artifact_roles: dict[str, str] = {}

    for name in reply_names:
        output = outputs.get(name)
        if output is None:
            continue
        if output.type in {"text", "markdown"}:
            reply_text_parts.append(output.text)
        else:
            reply_files.append(output.path)

    for name in archive_names:
        output = outputs.get(name)
        if output is None:
            continue
        archive_files.append(output.path)
        artifact_roles[output.path] = name

    if not reply_text_parts and not reply_files:
        if default_output.type in {"text", "markdown"}:
            reply_text_parts.append(default_output.text)
        else:
            reply_files.append(default_output.path)

    return CommandScriptRunResult(
        True,
        reply_text="\n\n".join(part for part in reply_text_parts if part),
        reply_files=reply_files,
        archive_files=archive_files,
        outputs=outputs,
        artifact_roles=artifact_roles,
    )
