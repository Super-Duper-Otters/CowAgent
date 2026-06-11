# encoding:utf-8
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import insert, select, update

from .config_service import sanitize_sensitive_text
from .constants import ActionType, ActorType, EntryType, ServiceType
from .db import connect, row_to_dict
from .schema import ai_generation_audits


@dataclass
class AIGenerationAudit:
    audit_id: str
    entry_type: EntryType
    service_type: ServiceType
    action_type: ActionType
    actor_type: ActorType
    actor_id: str = ""
    actor_name: str = ""
    actor_role: str = ""
    business_record_type: str = ""
    business_record_id: str = ""
    input_text: str = ""
    sources: list[str] | None = None
    provider: str = ""
    model: str = ""
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


def start_ai_generation_audit(
    *,
    entry_type: EntryType,
    service_type: ServiceType,
    action_type: ActionType,
    actor_type: ActorType,
    actor_id: str = "",
    actor_name: str = "",
    actor_role: str = "",
    business_record_type: str = "",
    business_record_id: str = "",
    input_text: str = "",
    sources: list[str] | None = None,
    provider: str = "",
    model: str = "",
) -> str:
    audit_id = str(uuid.uuid4())
    now = _now()
    with connect() as conn:
        conn.execute(
            insert(ai_generation_audits).values(
                audit_id=audit_id,
                entry_type=str(entry_type),
                service_type=str(service_type),
                action_type=str(action_type),
                actor_type=str(actor_type),
                actor_id=str(actor_id or ""),
                actor_name=str(actor_name or ""),
                actor_role=str(actor_role or ""),
                business_record_type=str(business_record_type or ""),
                business_record_id=str(business_record_id or ""),
                input_text=str(input_text or ""),
                sources=_json_list(sources),
                provider=str(provider or ""),
                model=str(model or ""),
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
    return audit_id


def finish_ai_generation_audit(
    audit_id: str,
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
            update(ai_generation_audits)
            .where(ai_generation_audits.c.audit_id == audit_id)
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


def _row_to_record(row) -> AIGenerationAudit | None:
    item = row_to_dict(row)
    if not item:
        return None
    return AIGenerationAudit(
        audit_id=item["audit_id"],
        entry_type=EntryType(item.get("entry_type") or EntryType.EXTERNAL_REQUEST),
        service_type=ServiceType(item.get("service_type") or ""),
        action_type=ActionType(item.get("action_type") or ActionType.GENERATE),
        actor_type=ActorType(item.get("actor_type") or ActorType.SYSTEM),
        actor_id=item.get("actor_id") or "",
        actor_name=item.get("actor_name") or "",
        actor_role=item.get("actor_role") or "",
        business_record_type=item.get("business_record_type") or "",
        business_record_id=item.get("business_record_id") or "",
        input_text=item.get("input_text") or "",
        sources=_load_list(item.get("sources")),
        provider=item.get("provider") or "",
        model=item.get("model") or "",
        result=item.get("result") or "",
        error_code=item.get("error_code") or "",
        error=item.get("error") or "",
        output_text=item.get("output_text") or "",
        outputs=_load_list(item.get("outputs")),
        elapsed_ms=item.get("elapsed_ms"),
        created_at=item.get("created_at") or "",
        updated_at=item.get("updated_at") or "",
    )


def get_ai_generation_audit(audit_id: str) -> AIGenerationAudit | None:
    with connect() as conn:
        row = conn.execute(
            select(ai_generation_audits).where(ai_generation_audits.c.audit_id == audit_id)
        ).fetchone()
    return _row_to_record(row)


def list_ai_generation_audits_for_business(business_record_type: str, business_record_id: str) -> list[AIGenerationAudit]:
    with connect() as conn:
        rows = conn.execute(
            select(ai_generation_audits)
            .where(
                ai_generation_audits.c.business_record_type == business_record_type,
                ai_generation_audits.c.business_record_id == business_record_id,
            )
            .order_by(ai_generation_audits.c.created_at.desc())
        ).fetchall()
    return [record for row in rows if (record := _row_to_record(row))]
