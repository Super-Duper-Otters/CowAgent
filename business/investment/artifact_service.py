# encoding:utf-8
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import insert

from .constants import ServiceType
from .db import connect
from .schema import investment_output_files
from .storage import get_storage_dirs
from .versioning import file_fingerprint


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _file_type(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return "image"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    return suffix.lstrip(".") or "file"


def _file_size(file_path: str) -> int | None:
    path = Path(file_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        return None
    return path.stat().st_size


def _safe_segment(value: str, fallback: str = "item") -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()).strip("._-")
    return text[:80] or fallback


def _is_path_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def archive_artifact_file(
    owner_id: str,
    file_path: str,
    artifact_role: str,
    service_type: ServiceType,
    *,
    owner_type: str = "request",
) -> str:
    path = Path(file_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        return file_path

    archive_root = get_storage_dirs()["generated"] / "archive"
    if _is_path_under(path, archive_root):
        return str(path)

    role = _safe_segment(artifact_role or _file_type(str(path)), "artifact")
    digest = file_fingerprint(str(path)).split(":", 1)[-1][:16] or "file"
    suffix = path.suffix or ".bin"
    stem = _safe_segment(path.stem, "file")
    target_dir = (
        archive_root
        / _safe_segment(str(service_type), "service")
        / _safe_segment(owner_type, "owner")
        / _safe_segment(owner_id, "id")
        / role
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{role}_{stem}_{digest}{suffix}"
    if not target.exists() or file_fingerprint(str(target)) != file_fingerprint(str(path)):
        shutil.copy2(path, target)
    return str(target)


def archive_output_files(
    owner_id: str,
    output_files: list[str],
    service_type: ServiceType,
    *,
    artifact_roles: dict[str, str] | None = None,
    artifact_versions: dict[str, str] | None = None,
    owner_type: str = "request",
) -> tuple[list[str], dict[str, str], dict[str, str], dict[str, str]]:
    archived_files: list[str] = []
    archived_roles: dict[str, str] = {}
    archived_versions: dict[str, str] = {}
    path_map: dict[str, str] = {}
    for file_path in output_files:
        role = (artifact_roles or {}).get(file_path, _file_type(file_path))
        version = (artifact_versions or {}).get(file_path, "")
        archived = archive_artifact_file(owner_id, file_path, role, service_type, owner_type=owner_type)
        archived_files.append(archived)
        archived_roles[archived] = role
        if version:
            archived_versions[archived] = version
        path_map[file_path] = archived
    return archived_files, archived_roles, archived_versions, path_map


def record_artifact(
    owner_id: str,
    file_path: str,
    artifact_role: str,
    service_type: ServiceType,
    *,
    file_type: str | None = None,
    version_tag: str = "",
    owner_type: str = "request",
) -> None:
    with connect() as conn:
        conn.execute(
            insert(investment_output_files).values(
                owner_id=owner_id,
                owner_type=owner_type,
                file_path=file_path,
                file_type=file_type or _file_type(file_path),
                service_type=str(service_type),
                artifact_role=artifact_role,
                file_size=_file_size(file_path),
                file_hash=file_fingerprint(file_path),
                version_tag=version_tag,
                created_at=_now(),
            )
        )
