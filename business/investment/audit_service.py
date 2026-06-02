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
class AdminActor:
    admin_id: int | None = None
    username: str = ""
    role: str = ""


@dataclass
class OperationAudit:
    audit_id: str
    operator: str
    operator_admin_id: int | None
    operator_username: str
    operator_role: str
    operation_category: str
    result_status: str
    error_code: str
    error_message: str
    elapsed_ms: int | None
    before_state: dict[str, Any]
    after_state: dict[str, Any]
    action: str
    target_type: str
    target_id: str
    detail: dict[str, Any]
    request_ip: str
    user_agent: str
    created_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _json_detail(detail: dict[str, Any] | None) -> str:
    return json.dumps(detail or {}, ensure_ascii=False, default=str)


def _json_state(state: dict[str, Any] | None) -> str:
    return json.dumps(state or {}, ensure_ascii=False, default=str)


def _load_json_object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def actor_from_admin(admin: Any | None) -> AdminActor | None:
    if admin is None:
        return None
    return AdminActor(
        admin_id=getattr(admin, "id", None),
        username=str(getattr(admin, "username", "") or ""),
        role=str(getattr(admin, "role", "") or ""),
    )


def _infer_operation_category(action: str, target_type: str) -> str:
    action_text = str(action or "")
    target_text = str(target_type or "")
    if target_text == "customer" or action_text.startswith("customer."):
        return "customer"
    if target_text == "daily_content" or action_text.startswith("content."):
        return "content"
    return "backoffice"


def record_operation_audit(
    action: str,
    target_type: str,
    target_id: str = "",
    *,
    operator: str = "",
    actor: AdminActor | None = None,
    operator_admin_id: int | None = None,
    operator_username: str = "",
    operator_role: str = "",
    operation_category: str = "",
    result_status: str = "success",
    error_code: str = "",
    error_message: str = "",
    elapsed_ms: int | None = None,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    request_ip: str = "",
    user_agent: str = "",
    detail: dict[str, Any] | None = None,
) -> str:
    audit_id = str(uuid.uuid4())
    actor = actor or AdminActor(
        admin_id=operator_admin_id,
        username=operator_username or operator,
        role=operator_role,
    )
    operator_text = actor.username or operator
    category = operation_category or _infer_operation_category(action, target_type)
    with connect() as conn:
        conn.execute(
            insert(investment_operation_audits).values(
                audit_id=audit_id,
                operator=operator_text,
                operator_admin_id=actor.admin_id,
                operator_username=actor.username or operator_text,
                operator_role=actor.role,
                operation_category=category,
                result_status=result_status,
                error_code=error_code,
                error_message=error_message,
                elapsed_ms=elapsed_ms,
                before_state=_json_state(before_state),
                after_state=_json_state(after_state),
                action=action,
                target_type=target_type,
                target_id=target_id,
                detail=_json_detail(detail),
                request_ip=request_ip,
                user_agent=user_agent,
                created_at=_now(),
            )
        )
    return audit_id


def _row_to_audit(row) -> OperationAudit:
    item = row_to_dict(row)
    detail = _load_json_object(item.get("detail"))
    return OperationAudit(
        audit_id=item["audit_id"],
        operator=item.get("operator") or "",
        operator_admin_id=item.get("operator_admin_id"),
        operator_username=item.get("operator_username") or item.get("operator") or "",
        operator_role=item.get("operator_role") or "",
        operation_category=item.get("operation_category") or _infer_operation_category(item["action"], item["target_type"]),
        result_status=item.get("result_status") or "success",
        error_code=item.get("error_code") or "",
        error_message=item.get("error_message") or "",
        elapsed_ms=item.get("elapsed_ms"),
        before_state=_load_json_object(item.get("before_state")),
        after_state=_load_json_object(item.get("after_state")),
        action=item["action"],
        target_type=item["target_type"],
        target_id=item.get("target_id") or "",
        detail=detail,
        request_ip=item.get("request_ip") or "",
        user_agent=item.get("user_agent") or "",
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
        conditions.append(or_(table.c.operator == operator, table.c.operator_username == operator))
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
                table.c.operator_username.ilike(pattern),
                table.c.operator_role.ilike(pattern),
                table.c.operation_category.ilike(pattern),
                table.c.result_status.ilike(pattern),
                table.c.error_code.ilike(pattern),
                table.c.error_message.ilike(pattern),
                table.c.action.ilike(pattern),
                table.c.target_type.ilike(pattern),
                table.c.target_id.ilike(pattern),
                table.c.detail.ilike(pattern),
                table.c.before_state.ilike(pattern),
                table.c.after_state.ilike(pattern),
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
