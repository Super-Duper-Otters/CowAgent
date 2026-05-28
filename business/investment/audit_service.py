# encoding:utf-8
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import insert, select

from .db import connect, row_to_dict
from .schema import investment_operation_audits


@dataclass
class OperationAudit:
    audit_id: str
    operator: str
    action: str
    target_type: str
    target_id: str
    detail: dict[str, Any]
    created_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _json_detail(detail: dict[str, Any] | None) -> str:
    return json.dumps(detail or {}, ensure_ascii=False, default=str)


def record_operation_audit(
    action: str,
    target_type: str,
    target_id: str = "",
    *,
    operator: str = "",
    detail: dict[str, Any] | None = None,
) -> str:
    audit_id = str(uuid.uuid4())
    with connect() as conn:
        conn.execute(
            insert(investment_operation_audits).values(
                audit_id=audit_id,
                operator=operator,
                action=action,
                target_type=target_type,
                target_id=target_id,
                detail=_json_detail(detail),
                created_at=_now(),
            )
        )
    return audit_id


def _row_to_audit(row) -> OperationAudit:
    item = row_to_dict(row)
    try:
        detail = json.loads(item.get("detail") or "{}")
    except json.JSONDecodeError:
        detail = {}
    if not isinstance(detail, dict):
        detail = {}
    return OperationAudit(
        audit_id=item["audit_id"],
        operator=item.get("operator") or "",
        action=item["action"],
        target_type=item["target_type"],
        target_id=item.get("target_id") or "",
        detail=detail,
        created_at=item["created_at"],
    )


def list_operation_audits(
    *,
    limit: int = 50,
    target_type: str | None = None,
    target_id: str | None = None,
) -> list[OperationAudit]:
    stmt = select(investment_operation_audits)
    if target_type:
        stmt = stmt.where(investment_operation_audits.c.target_type == target_type)
    if target_id:
        stmt = stmt.where(investment_operation_audits.c.target_id == target_id)
    stmt = stmt.order_by(investment_operation_audits.c.created_at.desc()).limit(limit)
    with connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [_row_to_audit(row) for row in rows]
