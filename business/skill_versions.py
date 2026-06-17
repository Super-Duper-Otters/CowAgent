# encoding:utf-8
import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from business.config_service import get_config, save_config
from business.investment.component_paths import runtime_component_root, runtime_versions_root
from business.skill_registry import InvestmentSkillDefinition, get_skill_definition, list_definitions


BUILTIN_VERSION_ID = "builtin-default"
MANIFEST_NAME = "manifest.json"


def _definition(skill_key: str) -> InvestmentSkillDefinition:
    return get_skill_definition(skill_key)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _version_root(definition: InvestmentSkillDefinition) -> Path:
    return runtime_versions_root(definition.storage_name)


def _version_roots(definition: InvestmentSkillDefinition) -> list[Path]:
    return [_version_root(definition)]


def _new_version_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"skill-{stamp}-{uuid.uuid4().hex[:8]}"


def _safe_member_path(name: str) -> Path:
    normalized = str(name or "").replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise ValueError(f"unsafe zip member path: {name}")
    return Path(*pure.parts)


def _write_manifest(version_dir: Path, manifest: dict) -> None:
    (version_dir / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_manifest(version_dir: Path) -> dict | None:
    path = version_dir / MANIFEST_NAME
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _find_version_dir(definition: InvestmentSkillDefinition, version_id: str) -> Path | None:
    safe_id = Path(version_id or "").name
    if not safe_id:
        return None
    for root in _version_roots(definition):
        version_dir = root / safe_id
        if _read_manifest(version_dir):
            return version_dir
    return None


def _absolute(path: str | Path) -> str:
    return str(Path(path).resolve())


def _configured_script_path(definition: InvestmentSkillDefinition) -> str:
    raw = str(get_config(definition.config_key, "") or "")
    if not raw:
        return ""
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    return _absolute(path)


def _builtin_script_path(definition: InvestmentSkillDefinition) -> str:
    return _absolute(Path.cwd() / definition.default_script_path)


def _is_active(definition: InvestmentSkillDefinition, script_path: str) -> bool:
    current = _configured_script_path(definition)
    if not script_path:
        return not current or current == _builtin_script_path(definition)
    return current == _absolute(script_path)


def _find_script(definition: InvestmentSkillDefinition, version_dir: Path) -> Path:
    direct = version_dir / definition.script_relative_path
    if direct.is_file():
        return direct
    root_script = version_dir / definition.script_name
    if root_script.is_file():
        target = version_dir / definition.script_relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root_script, target)
        return target
    matches = sorted(version_dir.glob(f"**/{definition.script_name}"))
    for match in matches:
        parts = {part.lower() for part in match.parts}
        if "scripts" in parts:
            return match
    raise ValueError(f"uploaded {definition.label} must contain scripts/{definition.script_name}")


def _copy_builtin_assets(definition: InvestmentSkillDefinition, version_dir: Path) -> None:
    if not definition.copy_assets_from:
        return
    source_assets = Path.cwd() / definition.copy_assets_from
    target_assets = version_dir / "assets"
    if source_assets.is_dir() and not target_assets.exists():
        shutil.copytree(source_assets, target_assets)


def _component_manifest_from_definition(definition: InvestmentSkillDefinition) -> dict:
    config_key = definition.config_key
    if not config_key and definition.handler_type == "script" and definition.entry:
        config_key = f"skill.{definition.skill_key}.script_path"
    component_type = definition.component_type
    if not component_type and definition.handler_type == "script":
        component_type = "active_script" if definition.routable else "passive_script"
    return {
        "component_key": definition.skill_key,
        "label": definition.label,
        "description": definition.description,
        "service_type": str(definition.service_type),
        "match_type": definition.match_type,
        "default_triggers": list(definition.default_triggers),
        "handler_type": definition.handler_type,
        "entry": definition.entry,
        "output_mode": definition.output_mode,
        "routable": definition.routable,
        "config_key": config_key,
        "script_name": definition.script_name or (Path(definition.entry).name if definition.entry else ""),
        "storage_name": definition.storage_name or definition.skill_key,
        "copy_assets_from": definition.copy_assets_from,
        "component_type": component_type,
        "prompt_key": definition.prompt_key,
        "renderer_component_key": definition.renderer_component_key,
        "template_key": definition.template_key,
    }


def _read_package_component_manifest(package_dir: Path) -> dict:
    component_json = package_dir / "component.json"
    if component_json.is_file():
        from business.business_registry import read_component_definition

        definition = read_component_definition(package_dir)
        if definition is None:
            raise ValueError("component.json must contain a valid investment component definition")
        return _component_manifest_from_definition(InvestmentSkillDefinition(
            skill_key=definition.business_key,
            label=definition.label,
            description=definition.description,
            service_type=definition.service_type,
            match_type=definition.match_type,
            default_triggers=definition.default_triggers,
            handler_type=definition.handler_type,
            entry=definition.entry,
            output_mode=definition.output_mode,
            routable=definition.routable,
            base_dir=definition.base_dir,
            config_key=definition.config_key,
            default_script_path=definition.default_script_path,
            script_name=definition.script_name,
            storage_name=definition.storage_name,
            copy_assets_from=definition.copy_assets_from,
            component_type=definition.component_type,
            prompt_key=definition.prompt_key,
            renderer_component_key=definition.renderer_component_key,
            template_key=definition.template_key,
        ))

    if not (package_dir / "SKILL.md").is_file():
        raise ValueError("investment component package must contain component.json or SKILL.md at package root")

    from business.skill_registry import _read_uploaded_definition

    definition = _read_uploaded_definition(package_dir)
    if definition is None:
        raise ValueError("SKILL.md must contain investment frontmatter")
    return _component_manifest_from_definition(definition)


def list_skill_definitions() -> list[dict]:
    return [definition.as_dict() for definition in list_definitions()]


def _ensure_versioned(definition: InvestmentSkillDefinition) -> None:
    if not definition.script_name or not definition.config_key:
        raise ValueError(f"{definition.label} does not support script version management")


def save_upload(skill_key: str, filename: str, content: bytes, *, operator: str = "web-console") -> dict:
    definition = _definition(skill_key)
    _ensure_versioned(definition)
    safe_name = Path(filename or "").name
    suffix = Path(safe_name).suffix.lower()
    if suffix not in {".py", ".zip"}:
        raise ValueError("investment skill upload only accepts .py or .zip files")
    if suffix == ".py" and safe_name != definition.script_name:
        raise ValueError(f"{definition.label} upload must be named {definition.script_name}")
    if not content:
        raise ValueError("uploaded skill file is empty")

    version_id = _new_version_id()
    version_dir = _version_root(definition) / version_id
    version_dir.mkdir(parents=True, exist_ok=False)

    try:
        if suffix == ".py":
            script_path = version_dir / definition.script_relative_path
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_bytes(content)
            _copy_builtin_assets(definition, version_dir)
        else:
            archive_path = version_dir / safe_name
            archive_path.write_bytes(content)
            with ZipFile(archive_path) as archive:
                members = [item for item in archive.infolist() if not item.is_dir()]
                for member in members:
                    target = version_dir / _safe_member_path(member.filename)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(member))
            script_path = _find_script(definition, version_dir)
            _copy_builtin_assets(definition, version_dir)

        manifest = {
            "skill_key": definition.skill_key,
            "version_id": version_id,
            "source": "upload",
            "original_filename": safe_name,
            "uploaded_at": _now(),
            "operator": operator,
            "script_path": str(script_path),
            "storage_path": str(version_dir),
        }
        _write_manifest(version_dir, manifest)
        save_config(definition.config_key, str(script_path), operator_role="admin", operator=operator)
        return manifest | {"active": True}
    except Exception:
        shutil.rmtree(version_dir, ignore_errors=True)
        raise


def list_versions(skill_key: str) -> list[dict]:
    definition = _definition(skill_key)
    _ensure_versioned(definition)
    versions = [
        {
            "skill_key": definition.skill_key,
            "version_id": BUILTIN_VERSION_ID,
            "source": "builtin",
            "original_filename": f"内置默认{definition.label}",
            "uploaded_at": "",
            "operator": "",
            "script_path": definition.default_script_path,
            "storage_path": "",
            "active": _is_active(definition, ""),
        }
    ]
    for root in _version_roots(definition):
        if root.is_dir():
            for version_dir in sorted((item for item in root.iterdir() if item.is_dir()), reverse=True):
                manifest = _read_manifest(version_dir)
                if not manifest:
                    continue
                script_path = str(manifest.get("script_path", ""))
                versions.append(manifest | {
                    "skill_key": definition.skill_key,
                    "storage_path": str(version_dir),
                    "active": _is_active(definition, script_path),
                })
    return versions


def list_all_skills() -> list[dict]:
    items = []
    for definition in list_definitions():
        versions = []
        if definition.script_name and definition.config_key:
            versions = list_versions(definition.skill_key)
        items.append({"skill": definition.as_dict(), "versions": versions})
    return items


def activate_version(skill_key: str, version_id: str, *, operator: str = "web-console") -> dict:
    definition = _definition(skill_key)
    _ensure_versioned(definition)
    component_manifest_path = runtime_component_root(definition.skill_key) / "component.json"
    if version_id == BUILTIN_VERSION_ID:
        save_config(definition.config_key, "", operator_role="admin", operator=operator)
        component_manifest_path.unlink(missing_ok=True)
        return [item for item in list_versions(definition.skill_key) if item["version_id"] == BUILTIN_VERSION_ID][0]

    version_dir = _find_version_dir(definition, version_id)
    if version_dir is None:
        raise ValueError(f"{definition.label} version not found: {version_id}")
    manifest = _read_manifest(version_dir) or {}
    script_path = Path(str(manifest.get("script_path", "")))
    if not script_path.is_file():
        raise ValueError(f"{definition.label} script missing: {script_path}")
    save_config(definition.config_key, str(script_path), operator_role="admin", operator=operator)
    version_component_manifest = version_dir / "component.json"
    if version_component_manifest.is_file():
        component_manifest_path.write_text(
            version_component_manifest.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    return manifest | {"skill_key": definition.skill_key, "storage_path": str(version_dir), "active": True}


def delete_version(skill_key: str, version_id: str, *, operator: str = "web-console") -> dict:
    definition = _definition(skill_key)
    _ensure_versioned(definition)
    if version_id == BUILTIN_VERSION_ID:
        raise ValueError("builtin skill version cannot be deleted")

    version_dir = _find_version_dir(definition, version_id)
    if version_dir is None:
        raise ValueError(f"{definition.label} version not found: {version_id}")
    manifest = _read_manifest(version_dir) or {}
    script_path = str(manifest.get("script_path", ""))
    was_active = _is_active(definition, script_path)
    if was_active:
        save_config(definition.config_key, "", operator_role="admin", operator=operator)
    shutil.rmtree(version_dir, ignore_errors=False)
    return manifest | {
        "skill_key": definition.skill_key,
        "storage_path": str(version_dir),
        "active": False,
        "was_active": was_active,
    }


def save_package_upload(filename: str, content: bytes, *, operator: str = "web-console") -> dict:
    safe_name = Path(filename or "").name
    if Path(safe_name).suffix.lower() != ".zip":
        raise ValueError("investment component package upload only accepts .zip files")
    if not content:
        raise ValueError("uploaded component package is empty")

    tmp_dir = runtime_component_root(f".upload-{uuid.uuid4().hex}")
    tmp_dir.mkdir(parents=True, exist_ok=False)
    try:
        archive_path = tmp_dir / safe_name
        archive_path.write_bytes(content)
        with ZipFile(archive_path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                target = tmp_dir / _safe_member_path(member.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))

        component_manifest = _read_package_component_manifest(tmp_dir)
        component_key = str(component_manifest["component_key"])
        target_root = runtime_component_root(component_key)
        version_id = _new_version_id()
        version_dir = runtime_versions_root(component_key) / version_id
        target_root.mkdir(parents=True, exist_ok=True)
        version_dir.parent.mkdir(parents=True, exist_ok=True)
        if version_dir.exists():
            shutil.rmtree(version_dir)
        tmp_dir.rename(version_dir)

        (target_root / "component.json").write_text(
            json.dumps(component_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        entry = str(component_manifest.get("entry") or "").strip()
        script_path = version_dir / entry if entry else Path("")
        upload_manifest = {
            "skill_key": component_key,
            "version_id": version_id,
            "source": "upload",
            "original_filename": safe_name,
            "uploaded_at": _now(),
            "operator": operator,
            "script_path": str(script_path) if entry else "",
            "storage_path": str(version_dir),
        }
        _write_manifest(version_dir, upload_manifest)

        config_key = str(component_manifest.get("config_key") or "")
        if config_key and entry:
            save_config(config_key, str(script_path), operator_role="admin", operator=operator)

        return upload_manifest | {
            "component_key": component_key,
            "skill_key": component_key,
            "active": bool(config_key and entry),
        }
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
