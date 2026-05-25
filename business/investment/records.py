# encoding:utf-8
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import insert, select, update

from .config_service import sanitize_sensitive_text
from .constants import ErrorCode, ServiceType, Status, user_message
from .db import connect, row_to_dict
from .schema import investment_daily_contents, investment_output_files, investment_request_records


GENERATING_TIMEOUT_WARNING = "未完成/可能超时"
GENERATING_TIMEOUT_MINUTES = 30


@dataclass
class RequestRecord:
    request_id: str
    openid: str
    raw_input: str
    service_type: ServiceType | None
    status: Status
    error_code: ErrorCode | None = None
    user_prompt: str = ""
    error_message: str = ""
    output_files: list[str] | None = None
    created_at: str = ""
    elapsed_ms: int | None = None
    status_warning: str = ""


@dataclass
class ContentRecord:
    content_id: str
    service_type: ServiceType
    status: Status
    source_files: list[str] | None = None
    source_text: str = ""
    generated_text: str = ""
    output_image: str = ""
    error_message: str = ""
    operator: str = ""
    created_at: str = ""
    effective_at: str | None = None
    status_warning: str = ""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _json_list(values: list[str] | None) -> str:
    return json.dumps(values or [], ensure_ascii=False)


def _load_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        return list(json.loads(value))
    except Exception:
        return []


def _status_warning(status: Status, created_at: str) -> str:
    if status != Status.GENERATING or not created_at:
        return ""
    try:
        parsed = datetime.fromisoformat(created_at)
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    if datetime.now(UTC) - parsed >= timedelta(minutes=GENERATING_TIMEOUT_MINUTES):
        return GENERATING_TIMEOUT_WARNING
    return ""


def create_request_record(openid: str, raw_input: str, service_type: ServiceType | None) -> str:
    request_id = str(uuid.uuid4())
    now = _now()
    with connect() as conn:
        conn.execute(
            insert(investment_request_records).values(
                request_id=request_id,
                openid=openid,
                raw_input=raw_input,
                service_type=str(service_type) if service_type else None,
                status=str(Status.GENERATING),
                output_files="[]",
                created_at=now,
                updated_at=now,
            )
        )
    return request_id


def succeed_request_record(request_id: str, *, output_files: list[str], elapsed_ms: int) -> None:
    service_type: ServiceType | None = None
    with connect() as conn:
        conn.execute(
            update(investment_request_records)
            .where(investment_request_records.c.request_id == request_id)
            .values(
                status=str(Status.SUCCESS),
                error_code=None,
                user_prompt="",
                error_message="",
                output_files=_json_list(output_files),
                elapsed_ms=elapsed_ms,
                updated_at=_now(),
            )
        )
        row = conn.execute(
            select(investment_request_records.c.service_type).where(investment_request_records.c.request_id == request_id)
        ).fetchone()
        item = row_to_dict(row)
        if item.get("service_type"):
            service_type = ServiceType(item["service_type"])
    if service_type is not None:
        for file_path in output_files:
            record_output_file(request_id, file_path, "image", service_type)


def fail_request_record(
    request_id: str,
    error_code: ErrorCode,
    user_prompt: str | None = None,
    detail: str = "",
    elapsed_ms: int = 0,
) -> None:
    safe_detail = sanitize_sensitive_text(detail)
    with connect() as conn:
        conn.execute(
            update(investment_request_records)
            .where(investment_request_records.c.request_id == request_id)
            .values(
                status=str(Status.FAILED),
                error_code=str(error_code),
                user_prompt=user_prompt or user_message(error_code),
                error_message=safe_detail,
                elapsed_ms=elapsed_ms,
                updated_at=_now(),
            )
        )


def record_success_request(openid: str, raw_input: str, service_type: ServiceType, output_files: list[str], elapsed_ms: int) -> str:
    request_id = create_request_record(openid, raw_input, service_type)
    succeed_request_record(request_id, output_files=output_files, elapsed_ms=elapsed_ms)
    return request_id


def record_failed_request(
    openid: str,
    raw_input: str,
    service_type: ServiceType | None,
    error_code: ErrorCode,
    detail: str,
    elapsed_ms: int,
) -> str:
    request_id = create_request_record(openid, raw_input, service_type)
    fail_request_record(request_id, error_code, detail=detail, elapsed_ms=elapsed_ms)
    return request_id


def set_output_files(request_id: str, output_files: list[str]) -> None:
    with connect() as conn:
        conn.execute(
            update(investment_request_records)
            .where(investment_request_records.c.request_id == request_id)
            .values(output_files=_json_list(output_files), updated_at=_now())
        )


def _row_to_request(row) -> RequestRecord:
    item = row_to_dict(row)
    status = Status(item["status"])
    created_at = item["created_at"]
    return RequestRecord(
        request_id=item["request_id"],
        openid=item["openid"],
        raw_input=item["raw_input"],
        service_type=ServiceType(item["service_type"]) if item["service_type"] else None,
        status=status,
        error_code=ErrorCode(item["error_code"]) if item["error_code"] else None,
        user_prompt=item["user_prompt"] or "",
        error_message=item["error_message"] or "",
        output_files=_load_list(item["output_files"]),
        created_at=created_at,
        elapsed_ms=item["elapsed_ms"],
        status_warning=_status_warning(status, created_at),
    )


def get_request_record(request_id: str) -> RequestRecord:
    with connect() as conn:
        row = conn.execute(
            select(investment_request_records).where(investment_request_records.c.request_id == request_id)
        ).fetchone()
    if row is None:
        raise KeyError(request_id)
    return _row_to_request(row)


def list_request_records(limit: int = 50) -> list[RequestRecord]:
    with connect() as conn:
        rows = conn.execute(
            select(investment_request_records)
            .order_by(investment_request_records.c.created_at.desc())
            .limit(limit)
        ).fetchall()
    return [_row_to_request(row) for row in rows]


def record_output_file(owner_id: str, file_path: str, file_type: str, service_type: ServiceType) -> None:
    with connect() as conn:
        conn.execute(
            insert(investment_output_files).values(
                owner_id=owner_id,
                file_path=file_path,
                file_type=file_type,
                service_type=str(service_type),
                created_at=_now(),
            )
        )


def _row_to_content(row) -> ContentRecord:
    item = row_to_dict(row)
    status = Status(item["status"])
    created_at = item["created_at"]
    return ContentRecord(
        content_id=item["content_id"],
        service_type=ServiceType(item["service_type"]),
        status=status,
        source_files=_load_list(item["source_files"]),
        source_text=item["source_text"] or "",
        generated_text=item["generated_text"] or "",
        output_image=item["output_image"] or "",
        error_message=item["error_message"] or "",
        operator=item["operator"] or "",
        created_at=created_at,
        effective_at=item["effective_at"],
        status_warning=_status_warning(status, created_at),
    )


def list_content_records(limit: int = 50, service_type: ServiceType | None = None) -> list[ContentRecord]:
    stmt = select(investment_daily_contents)
    if service_type is not None:
        stmt = stmt.where(investment_daily_contents.c.service_type == str(service_type))
    stmt = stmt.order_by(investment_daily_contents.c.created_at.desc()).limit(limit)
    with connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [_row_to_content(row) for row in rows]


def get_content_record(content_id: str) -> ContentRecord:
    with connect() as conn:
        row = conn.execute(
            select(investment_daily_contents).where(investment_daily_contents.c.content_id == content_id)
        ).fetchone()
    if row is None:
        raise KeyError(content_id)
    return _row_to_content(row)
