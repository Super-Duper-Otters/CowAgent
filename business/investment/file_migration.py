# encoding:utf-8
import json
import re
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from .artifact_service import archive_artifact_file
from business.constants import ServiceType
from .db import connect, row_to_dict
from .schema import investment_cache_entries, investment_daily_contents, investment_output_files, investment_request_records
from business.storage import get_storage_dirs


def _load_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if str(item).strip()]


def _json_list(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)


def _service_type(value: str | None) -> ServiceType | None:
    try:
        return ServiceType(value or "")
    except ValueError:
        return None


def _is_path_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _has_business_date_content_layout(path: Path, files_root: Path) -> bool:
    try:
        relative_parts = path.resolve().relative_to(files_root.resolve()).parts
    except ValueError:
        return False
    return len(relative_parts) >= 6 and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", relative_parts[1]))


def migrate_legacy_files_to_unified_storage() -> int:
    files_root = get_storage_dirs()["files"]
    moved: dict[str, str] = {}
    pending_artifacts: list[tuple[str, str, ServiceType, str, str]] = []
    changed = 0

    def migrate_path(owner_id: str, owner_type: str, service_type: ServiceType | None, role: str, file_path: str) -> str:
        nonlocal changed
        if not file_path:
            return file_path
        if file_path in moved:
            return moved[file_path]
        path = Path(file_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.is_file() or service_type is None:
            moved[file_path] = file_path
            return file_path
        is_in_files_root = _is_path_under(path, files_root)
        if is_in_files_root and _has_business_date_content_layout(path, files_root):
            moved[file_path] = file_path
            return file_path
        new_path = archive_artifact_file(
            owner_id,
            str(path),
            role,
            service_type,
            owner_type=owner_type,
            force_rehome=is_in_files_root,
        )
        if new_path != file_path:
            changed += 1
        moved[file_path] = new_path
        moved[str(path)] = new_path
        return new_path

    try:
        with connect() as conn:
            output_rows = conn.execute(select(investment_output_files)).mappings().all()
            role_by_owner_path = {
                (row["owner_id"], row["file_path"]): row.get("artifact_role") or row.get("file_type") or "artifact"
                for row in output_rows
            }
            existing_artifacts = {
                (row["owner_id"], row["file_path"], row.get("artifact_role") or "")
                for row in output_rows
            }

            for row in conn.execute(select(investment_request_records)).mappings().all():
                service_type = _service_type(row.get("service_type"))
                files = _load_list(row.get("output_files"))
                new_files = [
                    migrate_path(
                        row["request_id"],
                        "request",
                        service_type,
                        role_by_owner_path.get((row["request_id"], path), "artifact"),
                        path,
                    )
                    for path in files
                ]
                if new_files != files:
                    conn.execute(
                        update(investment_request_records)
                        .where(investment_request_records.c.request_id == row["request_id"])
                        .values(output_files=_json_list(new_files))
                    )

            for row in conn.execute(select(investment_daily_contents)).mappings().all():
                item = row_to_dict(row)
                service_type = _service_type(item.get("service_type"))
                source_files = _load_list(item.get("source_files"))
                new_source_files = [
                    migrate_path(item["content_id"], "content", service_type, "source_image", path)
                    for path in source_files
                ]
                output_image = item.get("output_image") or ""
                new_output_image = migrate_path(item["content_id"], "content", service_type, "output_image", output_image)
                values = {}
                if new_source_files != source_files:
                    values["source_files"] = _json_list(new_source_files)
                if new_output_image != output_image:
                    values["output_image"] = new_output_image
                if values:
                    conn.execute(
                        update(investment_daily_contents)
                        .where(investment_daily_contents.c.content_id == item["content_id"])
                        .values(**values)
                    )
                for source_path in new_source_files:
                    if service_type is not None and (item["content_id"], source_path, "source_image") not in existing_artifacts:
                        pending_artifacts.append((item["content_id"], source_path, service_type, "source_image", "content"))
                        existing_artifacts.add((item["content_id"], source_path, "source_image"))

            for row in conn.execute(select(investment_cache_entries)).mappings().all():
                service_type = _service_type(row.get("service_type"))
                owner_id = row.get("artifact_owner_id") or row.get("cache_key") or "cache"
                files = _load_list(row.get("output_files"))
                new_files = [
                    migrate_path(owner_id, "request", service_type, role_by_owner_path.get((owner_id, path), "artifact"), path)
                    for path in files
                ]
                if new_files != files:
                    conn.execute(
                        update(investment_cache_entries)
                        .where(investment_cache_entries.c.cache_key == row["cache_key"])
                        .values(output_files=_json_list(new_files))
                    )

            for old_path, new_path in moved.items():
                if old_path == new_path:
                    continue
                conn.execute(
                    update(investment_output_files)
                    .where(investment_output_files.c.file_path == old_path)
                    .values(file_path=new_path)
                )
    except SQLAlchemyError:
        return 0

    for owner_id, file_path, service_type, role, owner_type in pending_artifacts:
        from .artifact_service import record_artifact

        record_artifact(owner_id, file_path, role, service_type, owner_type=owner_type)

    return changed
