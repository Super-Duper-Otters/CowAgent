# encoding:utf-8
"""Preview and create runtime investment components from standard Skill packages."""

import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from agent.skills.frontmatter import parse_frontmatter

from business.component_paths import runtime_component_root, runtime_versions_root
from business.config_service import save_config
from business.business_registry import validate_business_key
from business.storage import get_storage_dirs


MANIFEST_NAME = "manifest.json"
PREVIEW_NAME = "preview.json"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _new_import_id() -> str:
    return f"import-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _new_version_id() -> str:
    return f"skill-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _imports_root() -> Path:
    return get_storage_dirs()["root"] / "component_imports"


def _safe_member_path(name: str) -> Path:
    normalized = str(name or "").replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise ValueError(f"unsafe zip member path: {name}")
    return Path(*pure.parts)


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path, limit: int = 1200) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return text[:limit]


def _read_skill_summary(path: Path, limit: int = 1200) -> str:
    text = _read_text(path, limit=limit * 2)
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            text = parts[2].strip()
    return text[:limit]


def _detect_root_dir(files: list[Path]) -> str:
    first_parts = {path.parts[0] for path in files if path.parts}
    return next(iter(first_parts)) if len(first_parts) == 1 else ""


def _relative_posix(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def _build_preview(import_id: str, filename: str, extracted_dir: Path) -> dict:
    files = [path.relative_to(extracted_dir) for path in extracted_dir.rglob("*") if path.is_file()]
    root_dir = _detect_root_dir(files)
    skill_matches = sorted(extracted_dir.glob("**/SKILL.md"))
    if not skill_matches:
        raise ValueError("uploaded Skill ZIP must contain SKILL.md")
    skill_md = skill_matches[0]
    package_root = skill_md.parent
    readme_matches = [package_root / "README.md", package_root / "readme.md"]
    readme = next((path for path in readme_matches if path.is_file()), None)

    frontmatter = parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
    scripts = sorted(_relative_posix(path, extracted_dir) for path in package_root.glob("scripts/*.py") if path.is_file())
    preview = {
        "import_id": import_id,
        "original_filename": Path(filename or "skill.zip").name,
        "root_dir": root_dir,
        "package_root": _relative_posix(package_root, extracted_dir),
        "skill_name": str(frontmatter.get("name") or package_root.name),
        "description": str(frontmatter.get("description") or ""),
        "scripts": scripts,
        "skill_summary": _read_skill_summary(skill_md),
        "readme_summary": _read_text(readme) if readme else "",
        "created_at": _now(),
    }
    return preview


def preview_skill_zip(filename: str, content: bytes, *, operator: str = "web-console") -> dict:
    safe_name = Path(filename or "skill.zip").name
    if Path(safe_name).suffix.lower() != ".zip":
        raise ValueError("component import only accepts .zip files")
    if not content:
        raise ValueError("uploaded Skill ZIP is empty")

    import_id = _new_import_id()
    import_root = _imports_root() / import_id
    extracted_dir = import_root / "extracted"
    import_root.mkdir(parents=True, exist_ok=False)
    extracted_dir.mkdir(parents=True, exist_ok=False)
    try:
        (import_root / "source.zip").write_bytes(content)
        with ZipFile(import_root / "source.zip") as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                target = extracted_dir / _safe_member_path(member.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))
        preview = _build_preview(import_id, safe_name, extracted_dir)
        preview["operator"] = operator
        _write_json(import_root / PREVIEW_NAME, preview)
        return {"status": "success", "import": preview}
    except Exception:
        shutil.rmtree(import_root, ignore_errors=True)
        raise


def _normalize_triggers(value) -> list[str]:
    if isinstance(value, str):
        items = value.replace("，", ",").split(",")
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        items = []
    return [str(item).strip() for item in items if str(item).strip()]


def _clean_entry(entry: str) -> str:
    path = _safe_member_path(entry)
    return path.as_posix()


def _component_manifest(form: dict, preview: dict) -> dict:
    component_key = validate_business_key(str(form.get("component_key") or "").strip())
    component_type = str(form.get("component_type") or "active_script").strip()
    if component_type not in {"active_script", "passive_script"}:
        raise ValueError("only active_script, passive_script, and active_prompt imports are supported")
    routable = component_type == "active_script"
    entry = _clean_entry(str(form.get("entry") or "").strip())
    execution = form.get("execution") if isinstance(form.get("execution"), dict) else {}
    if not execution:
        raise ValueError("command script component requires execution config")
    if component_type == "active_script" and not execution.get("default_output"):
        raise ValueError("active component requires default output")
    triggers = _normalize_triggers(form.get("default_triggers") or form.get("triggers"))
    if routable and not triggers:
        raise ValueError("active component triggers cannot be empty")

    return {
        "component_key": component_key,
        "label": str(form.get("label") or preview.get("skill_name") or component_key),
        "description": str(form.get("description") or preview.get("description") or ""),
        "creation_method": "zip",
        "service_type": str(form.get("service_type") or "unmatched"),
        "match_type": str(form.get("match_type") or "exact"),
        "default_triggers": triggers,
        "handler_type": "command_script",
        "entry": entry,
        "output_mode": str(form.get("output_mode") or "mixed"),
        "routable": routable,
        "config_key": str(form.get("config_key") or f"skill.{component_key}.script_path"),
        "script_name": Path(entry).name,
        "storage_name": component_key,
        "component_type": component_type,
        "execution": execution,
        "postprocess": form.get("postprocess") if isinstance(form.get("postprocess"), dict) else {"enabled": False},
        "reply": form.get("reply") if isinstance(form.get("reply"), dict) else {"outputs": [execution.get("default_output", "")]},
        "archive": form.get("archive") if isinstance(form.get("archive"), dict) else {"outputs": list((execution.get("outputs") or {}).keys())},
    }


def _create_prompt_component_from_import(import_id: str, form: dict, preview: dict, *, operator: str) -> dict:
    from business.component_service import create_prompt_component

    component = create_prompt_component(
        {
            "component_key": form.get("component_key"),
            "label": form.get("label") or preview.get("skill_name"),
            "description": form.get("description") or preview.get("description") or preview.get("skill_summary") or "",
            "service_type": form.get("service_type") or "unmatched",
            "match_type": form.get("match_type") or "suffix",
            "default_triggers": form.get("default_triggers") or form.get("triggers"),
            "prompt": form.get("prompt"),
            "enabled": form.get("enabled", True),
        },
        operator_role="admin",
        operator=operator,
        creation_method="zip",
    )
    return {
        "component_key": component["component_key"],
        "version_id": "",
        "source": "component_import",
        "original_filename": preview.get("original_filename", ""),
        "uploaded_at": _now(),
        "operator": operator,
        "script_path": "",
        "storage_path": str(runtime_component_root(component["component_key"])),
        "import_id": import_id,
        "active": True,
    }


def create_component_from_import(import_id: str, form: dict, *, operator: str = "web-console") -> dict:
    safe_import_id = Path(str(import_id or "").strip()).name
    import_root = _imports_root() / safe_import_id
    extracted_dir = import_root / "extracted"
    preview_path = import_root / PREVIEW_NAME
    if not extracted_dir.is_dir() or not preview_path.is_file():
        raise ValueError(f"component import not found: {import_id}")

    preview = _read_json(preview_path)
    component_type = str((form or {}).get("component_type") or "active_script").strip()
    if component_type == "active_prompt":
        return _create_prompt_component_from_import(safe_import_id, form or {}, preview, operator=operator)

    component_manifest = _component_manifest(form or {}, preview)
    component_key = component_manifest["component_key"]
    entry = component_manifest["entry"]
    source_entry = extracted_dir / Path(*PurePosixPath(entry).parts)
    if not source_entry.is_file():
        raise ValueError(f"entry script not found in import: {entry}")

    component_root = runtime_component_root(component_key)
    version_id = _new_version_id()
    version_dir = runtime_versions_root(component_key) / version_id
    component_root.mkdir(parents=True, exist_ok=True)
    version_dir.parent.mkdir(parents=True, exist_ok=True)
    if version_dir.exists():
        shutil.rmtree(version_dir)
    try:
        shutil.copytree(extracted_dir, version_dir)
        _write_json(component_root / "component.json", component_manifest)
        script_path = version_dir / Path(*PurePosixPath(entry).parts)
        version_manifest = {
            "component_key": component_key,
            "skill_key": component_key,
            "version_id": version_id,
            "source": "component_import",
            "original_filename": preview.get("original_filename", ""),
            "uploaded_at": _now(),
            "operator": operator,
            "script_path": str(script_path),
            "storage_path": str(version_dir),
            "import_id": safe_import_id,
        }
        _write_json(version_dir / MANIFEST_NAME, version_manifest)
        save_config(component_manifest["config_key"], str(script_path), operator_role="admin", operator=operator)
        return version_manifest | {"component_key": component_key, "active": True}
    except Exception:
        shutil.rmtree(version_dir, ignore_errors=True)
        if not any(component_root.iterdir()):
            shutil.rmtree(component_root, ignore_errors=True)
        raise
