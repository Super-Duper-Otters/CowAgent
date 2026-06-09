# encoding:utf-8
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, insert, select, update

from .config_service import sanitize_sensitive_text
from .constants import ServiceType
from .db import connect, row_to_dict
from .schema import generation_records


@dataclass
class GenerationRecord:
    generation_id: str
    content_id: str
    service_type: ServiceType
    operator_id: int | None = None
    operator_name: str = ""
    operator_role: str = ""
    input_text: str = ""
    sources: list[str] | None = None
    result: str = ""
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


def start_generation_record(
    *,
    content_id: str,
    service_type: ServiceType,
    operator_id: int | None = None,
    operator_name: str = "",
    operator_role: str = "",
    input_text: str = "",
    sources: list[str] | None = None,
) -> str:
    generation_id = str(uuid.uuid4())
    now = _now()
    with connect() as conn:
        conn.execute(
            insert(generation_records).values(
                generation_id=generation_id,
                content_id=content_id,
                service=str(service_type),
                operator_id=operator_id,
                operator_name=operator_name,
                operator_role=operator_role,
                input_text=input_text,
                sources=_json_list(sources),
                result="running",
                error_code="",
                error="",
                output_text="",
                outputs=_json_list([]),
                elapsed_ms=None,
                created_at=now,
                updated_at=now,
            )
        )
    return generation_id


def finish_generation_record(
    generation_id: str,
    *,
    result: str,
    error_code: str = "",
    error: str = "",
    output_text: str = "",
    outputs: list[str] | None = None,
    elapsed_ms: int | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            update(generation_records)
            .where(generation_records.c.generation_id == generation_id)
            .values(
                result=str(result or ""),
                error_code=str(error_code or ""),
                error=sanitize_sensitive_text(error),
                output_text=str(output_text or ""),
                outputs=_json_list(outputs),
                elapsed_ms=elapsed_ms,
                updated_at=_now(),
            )
        )


def _row_to_record(row) -> GenerationRecord | None:
    item = row_to_dict(row)
    if not item:
        return None
    return GenerationRecord(
        generation_id=item["generation_id"],
        content_id=item.get("content_id") or "",
        service_type=ServiceType(item.get("service") or ""),
        operator_id=item.get("operator_id"),
        operator_name=item.get("operator_name") or "",
        operator_role=item.get("operator_role") or "",
        input_text=item.get("input_text") or "",
        sources=_load_list(item.get("sources")),
        result=item.get("result") or "",
        error_code=item.get("error_code") or "",
        error=item.get("error") or "",
        output_text=item.get("output_text") or "",
        outputs=_load_list(item.get("outputs")),
        elapsed_ms=item.get("elapsed_ms"),
        created_at=item.get("created_at") or "",
        updated_at=item.get("updated_at") or "",
    )


def get_generation_record(generation_id: str) -> GenerationRecord | None:
    with connect() as conn:
        row = conn.execute(
            select(generation_records).where(generation_records.c.generation_id == generation_id)
        ).fetchone()
    return _row_to_record(row)


def _generation_conditions(*, content_id: str = "", service_type: ServiceType | str | None = None, result: str = ""):
    conditions = []
    if content_id:
        conditions.append(generation_records.c.content_id == str(content_id))
    if service_type is not None and str(service_type or "").strip():
        conditions.append(generation_records.c.service == str(ServiceType(service_type)))
    if result:
        conditions.append(generation_records.c.result == str(result))
    return conditions


def list_generation_records(content_id: str = "", limit: int = 100) -> list[GenerationRecord]:
    stmt = select(generation_records)
    conditions = _generation_conditions(content_id=content_id)
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.order_by(generation_records.c.created_at.desc()).limit(max(1, int(limit or 100)))
    with connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [record for row in rows if (record := _row_to_record(row))]


def list_generation_records_page(
    *,
    page: int = 1,
    page_size: int = 50,
    content_id: str = "",
    service_type: ServiceType | str | None = None,
    result: str = "",
) -> tuple[list[GenerationRecord], int]:
    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 50))
    stmt = select(generation_records)
    count_stmt = select(func.count()).select_from(generation_records)
    conditions = _generation_conditions(content_id=content_id, service_type=service_type, result=result)
    if conditions:
        stmt = stmt.where(*conditions)
        count_stmt = count_stmt.where(*conditions)
    stmt = stmt.order_by(generation_records.c.created_at.desc()).limit(page_size).offset((page - 1) * page_size)
    with connect() as conn:
        total = int(conn.execute(count_stmt).scalar_one() or 0)
        rows = conn.execute(stmt).fetchall()
    return [record for row in rows if (record := _row_to_record(row))], total
