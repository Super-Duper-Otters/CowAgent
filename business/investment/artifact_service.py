# encoding:utf-8
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import insert

from .constants import ServiceType
from .db import connect
from .schema import investment_output_files
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
