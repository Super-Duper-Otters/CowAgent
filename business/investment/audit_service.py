# encoding:utf-8
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, insert, select

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
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    operator: str | None = None,
    keyword: str = "",
    start_date: str = "",
    end_date: str = "",
) -> list[OperationAudit]:
    audits, _total = list_operation_audits_page(
        page=1,
        page_size=limit,
        action=action,
        target_type=target_type,
        target_id=target_id,
        operator=operator,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
    )
    return audits


def list_operation_audits_page(
    *,
    page: int = 1,
    page_size: int = 50,
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    operator: str | None = None,
    keyword: str = "",
    start_date: str = "",
    end_date: str = "",
) -> tuple[list[OperationAudit], int]:
    table = investment_operation_audits
    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 50))
    offset = (page - 1) * page_size
    stmt = select(table)
    count_stmt = select(func.count()).select_from(table)
    conditions = []
    if action:
        conditions.append(table.c.action == action)
    if target_type:
        conditions.append(table.c.target_type == target_type)
    if target_id:
        conditions.append(table.c.target_id == target_id)
    if operator:
        conditions.append(table.c.operator == operator)
    if start_date:
        conditions.append(table.c.created_at >= str(start_date))
    if end_date:
        conditions.append(table.c.created_at <= str(end_date))
    keyword_text = str(keyword or "").strip()
    if keyword_text:
        pattern = f"%{keyword_text}%"
        conditions.append(
            or_(
                table.c.audit_id.ilike(pattern),
                table.c.operator.ilike(pattern),
                table.c.action.ilike(pattern),
                table.c.target_type.ilike(pattern),
                table.c.target_id.ilike(pattern),
                table.c.detail.ilike(pattern),
            )
        )
    if conditions:
        stmt = stmt.where(*conditions)
        count_stmt = count_stmt.where(*conditions)
    stmt = stmt.order_by(table.c.created_at.desc()).limit(page_size).offset(offset)
    with connect() as conn:
        total = int(conn.execute(count_stmt).scalar_one() or 0)
        rows = conn.execute(stmt).fetchall()
    return [_row_to_audit(row) for row in rows], total
