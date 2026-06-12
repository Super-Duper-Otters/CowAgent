# encoding:utf-8
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, or_, insert, select, update

from .config_service import sanitize_sensitive_text
from .constants import ActionType, ActorType, EntryType, ServiceType, Status
from .db import connect, row_to_dict
from .schema import internal_call_records


@dataclass
class InternalCallRecord:
    call_id: str
    entry_type: EntryType
    service_type: ServiceType
    action_type: ActionType
    actor_type: ActorType
    actor_id: str = ""
    actor_name: str = ""
    actor_role: str = ""
    input_text: str = ""
    input_prompt: str = ""
    sources: list[str] | None = None
    status: Status = Status.GENERATING
    error_code: str = ""
    error: str = ""
    output_text: str = ""
    outputs: list[str] | None = None
    elapsed_ms: int | None = None
    created_at: str = ""
    updated_at: str = ""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _json_list(values: list[str] | None) -> str:
    return json.dumps([str(value) for value in values or []], ensure_ascii=False)


def _load_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def start_internal_call_record(
    *,
    service_type: ServiceType,
    action_type: ActionType,
    actor_type: ActorType,
    actor_id: str = "",
    actor_name: str = "",
    actor_role: str = "",
    input_text: str = "",
    input_prompt: str = "",
    sources: list[str] | None = None,
) -> str:
    call_id = str(uuid.uuid4())
    now = _now()
    with connect() as conn:
        conn.execute(
            insert(internal_call_records).values(
                call_id=call_id,
                entry_type=str(EntryType.INTERNAL_CALL),
                service_type=str(service_type),
                action_type=str(action_type),
                actor_type=str(actor_type),
                actor_id=str(actor_id or ""),
                actor_name=str(actor_name or ""),
                actor_role=str(actor_role or ""),
                input_text=str(input_text or ""),
                input_prompt=str(input_prompt or ""),
                sources=_json_list(sources),
                status=str(Status.GENERATING),
                error_code="",
                error="",
                output_text="",
                outputs=_json_list([]),
                elapsed_ms=None,
                created_at=now,
                updated_at=now,
            )
        )
    return call_id


def finish_internal_call_record(
    call_id: str,
    *,
    status: Status,
    error_code: str = "",
    error: str = "",
    output_text: str = "",
    input_prompt: str = "",
    outputs: list[str] | None = None,
    elapsed_ms: int | None = None,
) -> None:
    values = {
        "status": str(status),
        "error_code": str(error_code or ""),
        "error": sanitize_sensitive_text(error),
        "output_text": str(output_text or ""),
        "outputs": _json_list(outputs),
        "elapsed_ms": elapsed_ms,
        "updated_at": _now(),
    }
    if input_prompt:
        values["input_prompt"] = str(input_prompt or "")
    with connect() as conn:
        conn.execute(
            update(internal_call_records)
            .where(internal_call_records.c.call_id == call_id)
            .values(**values)
        )


def _row_to_record(row) -> InternalCallRecord | None:
    item = row_to_dict(row)
    if not item:
        return None
    return InternalCallRecord(
        call_id=item["call_id"],
        entry_type=EntryType(item.get("entry_type") or EntryType.INTERNAL_CALL),
        service_type=ServiceType(item.get("service_type") or ""),
        action_type=ActionType(item.get("action_type") or ActionType.GENERATE),
        actor_type=ActorType(item.get("actor_type") or ActorType.SYSTEM),
        actor_id=item.get("actor_id") or "",
        actor_name=item.get("actor_name") or "",
        actor_role=item.get("actor_role") or "",
        input_text=item.get("input_text") or "",
        input_prompt=item.get("input_prompt") or "",
        sources=_load_list(item.get("sources")),
        status=Status(item.get("status") or Status.GENERATING),
        error_code=item.get("error_code") or "",
        error=item.get("error") or "",
        output_text=item.get("output_text") or "",
        outputs=_load_list(item.get("outputs")),
        elapsed_ms=item.get("elapsed_ms"),
        created_at=item.get("created_at") or "",
        updated_at=item.get("updated_at") or "",
    )


def get_internal_call_record(call_id: str) -> InternalCallRecord:
    with connect() as conn:
        row = conn.execute(
            select(internal_call_records).where(internal_call_records.c.call_id == call_id)
        ).fetchone()
    record = _row_to_record(row)
    if record is None:
        raise KeyError(call_id)
    return record


def _conditions(
    *,
    service_type: ServiceType | str | None = None,
    status: Status | str | None = None,
    keyword: str = "",
    start_date: str = "",
    end_date: str = "",
):
    conditions = []
    if service_type is not None and str(service_type or "").strip():
        conditions.append(internal_call_records.c.service_type == str(ServiceType(service_type)))
    if status is not None and str(status or "").strip():
        conditions.append(internal_call_records.c.status == str(Status(status)))
    if start_date:
        conditions.append(internal_call_records.c.created_at >= str(start_date))
    if end_date:
        conditions.append(internal_call_records.c.created_at <= str(end_date))
    keyword_text = str(keyword or "").strip()
    if keyword_text:
        pattern = f"%{keyword_text}%"
        conditions.append(
            or_(
                internal_call_records.c.call_id.ilike(pattern),
                internal_call_records.c.service_type.ilike(pattern),
                internal_call_records.c.action_type.ilike(pattern),
                internal_call_records.c.actor_name.ilike(pattern),
                internal_call_records.c.actor_role.ilike(pattern),
                internal_call_records.c.input_text.ilike(pattern),
                internal_call_records.c.input_prompt.ilike(pattern),
                internal_call_records.c.sources.ilike(pattern),
                internal_call_records.c.status.ilike(pattern),
                internal_call_records.c.error_code.ilike(pattern),
                internal_call_records.c.error.ilike(pattern),
                internal_call_records.c.output_text.ilike(pattern),
                internal_call_records.c.outputs.ilike(pattern),
            )
        )
    return conditions


def list_internal_call_records_page(
    *,
    page: int = 1,
    page_size: int = 50,
    service_type: ServiceType | str | None = None,
    status: Status | str | None = None,
    keyword: str = "",
    start_date: str = "",
    end_date: str = "",
) -> tuple[list[InternalCallRecord], int]:
    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 50))
    conditions = _conditions(
        service_type=service_type,
        status=status,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
    )
    stmt = select(internal_call_records)
    count_stmt = select(func.count()).select_from(internal_call_records)
    if conditions:
        stmt = stmt.where(*conditions)
        count_stmt = count_stmt.where(*conditions)
    stmt = stmt.order_by(internal_call_records.c.created_at.desc()).limit(page_size).offset((page - 1) * page_size)
    with connect() as conn:
        total = int(conn.execute(count_stmt).scalar_one() or 0)
        rows = conn.execute(stmt).fetchall()
    return [record for row in rows if (record := _row_to_record(row))], total
