# encoding:utf-8
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import insert, select, update

from business.constants import ServiceType
from business.db import connect, row_to_dict
from business.schema import investment_daily_contents, investment_output_files, investment_request_records
from business.storage import get_storage_dirs
from business.versioning import file_fingerprint


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


def _date_from_text(value: str | None) -> str:
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value or ""))
    return match.group(0) if match else ""


def _owner_date(owner_id: str, owner_type: str) -> str:
    try:
        with connect() as conn:
            if owner_type == "content":
                row = conn.execute(
                    select(
                        investment_daily_contents.c.effective_date,
                        investment_daily_contents.c.created_at,
                    ).where(investment_daily_contents.c.content_id == owner_id)
                ).fetchone()
                item = row_to_dict(row)
                return _date_from_text(item.get("effective_date")) or _date_from_text(item.get("created_at"))
            row = conn.execute(
                select(
                    investment_request_records.c.market_date,
                    investment_request_records.c.created_at,
                ).where(investment_request_records.c.request_id == owner_id)
            ).fetchone()
            item = row_to_dict(row)
            return _date_from_text(item.get("market_date")) or _date_from_text(item.get("created_at"))
    except Exception:
        return ""
    return ""


def _is_path_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _remove_empty_parents(start: Path, stop: Path) -> None:
    current = start.resolve()
    stop = stop.resolve()
    while current != stop:
        try:
            current.relative_to(stop)
        except ValueError:
            return
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def archive_artifact_file(
    owner_id: str,
    file_path: str,
    artifact_role: str,
    service_type: ServiceType,
    *,
    owner_type: str = "request",
    storage_date: str = "",
    force_rehome: bool = False,
    storage_namespace: str = "",
) -> str:
    path = Path(file_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        return file_path

    from business.config_service import get_config

    files_root = Path(str(get_config("storage.files_dir") or get_storage_dirs()["files"]))
    if not files_root.is_absolute():
        files_root = Path.cwd() / files_root
    if _is_path_under(path, files_root) and not force_rehome:
        return str(path)

    role = _safe_segment(artifact_role or _file_type(str(path)), "artifact")
    digest = file_fingerprint(str(path)).split(":", 1)[-1][:16] or "file"
    suffix = path.suffix or ".bin"
    stem = _safe_segment(path.stem, "file")
    storage_date = _safe_segment(
        _date_from_text(storage_date) or _owner_date(owner_id, owner_type) or datetime.now(UTC).date().isoformat(),
        "unknown-date",
    )
    namespace_parts = [
        _safe_segment(part, "")
        for part in str(storage_namespace or "").replace("\\", "/").split("/")
        if _safe_segment(part, "")
    ]
    category_parts = namespace_parts or [_safe_segment(str(service_type), "service")]
    target_dir = (
        files_root
        .joinpath(*category_parts)
        / storage_date
        / _safe_segment(owner_type, "owner")
        / _safe_segment(owner_id, "id")
        / role
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{role}_{stem}_{digest}{suffix}"
    if target.exists() and file_fingerprint(str(target)) == file_fingerprint(str(path)):
        storage_root = get_storage_dirs()["root"]
        if _is_path_under(path, storage_root) and path.resolve() != target.resolve():
            path.unlink(missing_ok=True)
            _remove_empty_parents(path.parent, storage_root)
        return str(target)

    storage_root = get_storage_dirs()["root"]
    if _is_path_under(path, storage_root):
        shutil.move(str(path), str(target))
        _remove_empty_parents(path.parent, storage_root)
    else:
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
    storage_date: str = "",
    storage_namespace: str = "",
) -> tuple[list[str], dict[str, str], dict[str, str], dict[str, str]]:
    archived_files: list[str] = []
    archived_roles: dict[str, str] = {}
    archived_versions: dict[str, str] = {}
    path_map: dict[str, str] = {}
    for file_path in output_files:
        role = (artifact_roles or {}).get(file_path, _file_type(file_path))
        version = (artifact_versions or {}).get(file_path, "")
        archived = archive_artifact_file(
            owner_id,
            file_path,
            role,
            service_type,
            owner_type=owner_type,
            storage_date=storage_date,
            storage_namespace=storage_namespace,
        )
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
    role = artifact_role or _file_type(file_path)
    resolved_file_type = file_type or _file_type(file_path)
    size = _file_size(file_path)
    digest = file_fingerprint(file_path)
    now = _now()
    with connect() as conn:
        existing = conn.execute(
            select(investment_output_files.c.id).where(
                investment_output_files.c.owner_id == owner_id,
                investment_output_files.c.owner_type == owner_type,
                investment_output_files.c.file_path == file_path,
                investment_output_files.c.artifact_role == role,
            )
        ).fetchone()
        if existing is not None:
            conn.execute(
                update(investment_output_files)
                .where(investment_output_files.c.id == existing.id)
                .values(
                    file_type=resolved_file_type,
                    service_type=str(service_type),
                    file_size=size,
                    file_hash=digest,
                    version_tag=version_tag,
                )
            )
            return
        conn.execute(
            insert(investment_output_files).values(
                owner_id=owner_id,
                owner_type=owner_type,
                file_path=file_path,
                file_type=resolved_file_type,
                service_type=str(service_type),
                artifact_role=role,
                file_size=size,
                file_hash=digest,
                version_tag=version_tag,
                created_at=now,
            )
        )
