# encoding:utf-8
import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from .config_service import get_config, save_config
from .render_service import DEFAULT_RENDERER_PATH
from .storage import get_storage_dirs


BUILTIN_VERSION_ID = "builtin-default"
MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True)
class InvestmentSkillDefinition:
    skill_key: str
    label: str
    description: str
    config_key: str
    default_script_path: str
    script_name: str
    storage_name: str
    copy_assets_from: str = ""

    @property
    def script_relative_path(self) -> Path:
        return Path("scripts") / self.script_name

    def as_dict(self) -> dict:
        return {
            "skill_key": self.skill_key,
            "label": self.label,
            "description": self.description,
            "config_key": self.config_key,
            "default_script_path": self.default_script_path,
            "script_name": self.script_name,
            "storage_name": self.storage_name,
        }


SKILL_REGISTRY: dict[str, InvestmentSkillDefinition] = {
    "technical-analysis": InvestmentSkillDefinition(
        skill_key="technical-analysis",
        label="技术分析 Skill",
        description="拉取行情并生成技术分析报告、图表和标准信号文本。",
        config_key="technical_analysis.skill_path",
        default_script_path="skills/技术分析/scripts/analyze_universal.py",
        script_name="analyze_universal.py",
        storage_name="technical-analysis",
    ),
    "signal-card-renderer": InvestmentSkillDefinition(
        skill_key="signal-card-renderer",
        label="图片生成 Skill",
        description="把技术分析、利率、转债标准文本渲染为信号卡片图片。",
        config_key="render.renderer_path",
        default_script_path=DEFAULT_RENDERER_PATH,
        script_name="render_card.py",
        storage_name="signal-card-renderer",
        copy_assets_from="skills/signal-card-renderer/assets",
    ),
}


def _definition(skill_key: str) -> InvestmentSkillDefinition:
    try:
        return SKILL_REGISTRY[skill_key]
    except KeyError:
        raise ValueError(f"unsupported investment skill: {skill_key}") from None


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _version_root(definition: InvestmentSkillDefinition) -> Path:
    return get_storage_dirs()["root"] / "skills" / definition.storage_name


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


def list_skill_definitions() -> list[dict]:
    return [definition.as_dict() for definition in SKILL_REGISTRY.values()]


def save_upload(skill_key: str, filename: str, content: bytes, *, operator: str = "web-console") -> dict:
    definition = _definition(skill_key)
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
    root = _version_root(definition)
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
    return [
        {
            "skill": definition.as_dict(),
            "versions": list_versions(definition.skill_key),
        }
        for definition in SKILL_REGISTRY.values()
    ]


def activate_version(skill_key: str, version_id: str, *, operator: str = "web-console") -> dict:
    definition = _definition(skill_key)
    if version_id == BUILTIN_VERSION_ID:
        save_config(definition.config_key, "", operator_role="admin", operator=operator)
        return [item for item in list_versions(definition.skill_key) if item["version_id"] == BUILTIN_VERSION_ID][0]

    version_dir = _version_root(definition) / Path(version_id or "").name
    manifest = _read_manifest(version_dir)
    if not manifest:
        raise ValueError(f"{definition.label} version not found: {version_id}")
    script_path = Path(str(manifest.get("script_path", "")))
    if not script_path.is_file():
        raise ValueError(f"{definition.label} script missing: {script_path}")
    save_config(definition.config_key, str(script_path), operator_role="admin", operator=operator)
    return manifest | {"skill_key": definition.skill_key, "storage_path": str(version_dir), "active": True}


def delete_version(skill_key: str, version_id: str, *, operator: str = "web-console") -> dict:
    definition = _definition(skill_key)
    if version_id == BUILTIN_VERSION_ID:
        raise ValueError("builtin skill version cannot be deleted")

    version_dir = _version_root(definition) / Path(version_id or "").name
    manifest = _read_manifest(version_dir)
    if not manifest:
        raise ValueError(f"{definition.label} version not found: {version_id}")
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
