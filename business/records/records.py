# encoding:utf-8
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, exists, func, insert, or_, select, update

from business.config.config_service import sanitize_sensitive_text
from business.config.constants import ActionType, ActorType, EntryType, ErrorCode, ServiceType, Status, normalize_service, user_message
from business.products.product_service import (
    PRODUCT_STATUS_ACTIVE,
    PRODUCT_STATUS_ARCHIVED,
    PRODUCT_STATUS_FAILED,
    PRODUCT_STATUS_INVALIDATED,
    _expires_at_condition as _product_expires_at_condition,
    product_display_status,
)
from business.schema.db import connect, row_to_dict
from business.schema.tables import (
    investment_daily_contents,
    investment_output_files,
    investment_products,
    investment_request_records,
    investment_users,
    request_events,
)


logger = logging.getLogger(__name__)
GENERATING_TIMEOUT_WARNING = "未完成/可能超时"
GENERATING_TIMEOUT_MINUTES = 30
DELIVERY_DELIVERED_MARKER = "[delivery:delivered]"
DELIVERY_FAILURE_KEYWORDS = (
    "上传失败",
    "发送失败",
    "send failed",
    "upload failed",
    "media upload failed",
)


@dataclass
class RequestRecord:
    request_id: str
    openid: str
    raw_input: str
    service_type: ServiceType | None
    status: Status
    module_key: str = ""
    entry_type: EntryType = EntryType.EXTERNAL_REQUEST
    action_type: ActionType = ActionType.GENERATE
    actor_type: ActorType = ActorType.CUSTOMER
    actor_id: str = ""
    actor_name: str = ""
    actor_role: str = ""
    error_code: ErrorCode | None = None
    user_prompt: str = ""
    error_message: str = ""
    output_files: list[str] | None = None
    output_artifacts: list[dict] | None = None
    normalized_target: str = ""
    stock_code: str = ""
    stock_name: str = ""
    customer_name: str = ""
    institution: str = ""
    market_date: str = ""
    cache_key: str = ""
    cache_hit: bool = False
    program_version: str = ""
    ta_version: str = ""
    renderer_version: str = ""
    template_version: str = ""
    created_at: str = ""
    elapsed_ms: int | None = None
    status_warning: str = ""
    customer_mobile: str = ""
    customer_display: str = ""
    delivery_status: str = ""
    delivery_detail: str = ""


@dataclass
class ContentRecord:
    content_id: str
    service_type: ServiceType
    status: Status
    module_key: str = ""
    source_files: list[str] | None = None
    source_text: str = ""
    input_prompt: str = ""
    generated_text: str = ""
    output_image: str = ""
    error_message: str = ""
    operator: str = ""
    created_by_admin_id: int | None = None
    created_by_username: str = ""
    created_by_role: str = ""
    updated_by_admin_id: int | None = None
    updated_by_username: str = ""
    updated_by_role: str = ""
    published_by_admin_id: int | None = None
    published_by_username: str = ""
    published_by_role: str = ""
    created_at: str = ""
    effective_at: str | None = None
    effective_date: str = ""
    expires_at: str = ""
    content_version: int = 1
    direct_output_mode: bool = False
    auto_effective_after_generate: bool = False
    archived_at: str | None = None
    status_warning: str = ""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _json_list(values: list[str] | None) -> str:
    return json.dumps(values or [], ensure_ascii=False)


def _load_list(value: str | None) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
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


def _request_status_warning(status: Status, created_at: str, error_message: str = "") -> str:
    visible_message = _visible_delivery_message(error_message)
    if status == Status.SUCCESS and visible_message:
        return visible_message
    return _status_warning(status, created_at)


def _visible_delivery_message(error_message: str = "") -> str:
    lines = [
        line.strip()
        for line in str(error_message or "").splitlines()
        if line.strip() and line.strip() != DELIVERY_DELIVERED_MARKER
    ]
    return "\n".join(lines)


def _has_delivery_failure(detail: str = "") -> bool:
    lowered = str(detail or "").lower()
    return any(keyword.lower() in lowered for keyword in DELIVERY_FAILURE_KEYWORDS)


def _delivery_status(status: Status, error_message: str = "", output_files: list[str] | None = None) -> tuple[str, str]:
    visible_message = _visible_delivery_message(error_message)
    if status == Status.FAILED:
        return "未交付", visible_message or "生成失败，未向客户交付结果"
    if status == Status.GENERATING:
        return "待生成", "内容仍在生成中，尚未进入交付"
    if status != Status.SUCCESS:
        return "未知", visible_message or "记录状态暂无法判断"
    if _has_delivery_failure(visible_message):
        return "交付异常", visible_message
    if DELIVERY_DELIVERED_MARKER in str(error_message or ""):
        return "已交付", visible_message or "客户已收到结果"
    if output_files:
        return "待客户领取", visible_message or "内容已生成，等待客户在公众号领取结果"
    return "已交付", visible_message or "已返回客户可读内容"


def _service_condition(table, service_type: ServiceType | str | None):
    if service_type is None or str(service_type or "").strip() == "":
        return None, False
    normalized_service = normalize_service(service_type)
    valid_unmatched_inputs = {str(ServiceType.UNMATCHED), "unmatched"}
    if normalized_service == ServiceType.UNMATCHED and str(service_type) not in valid_unmatched_inputs:
        return None, True
    return table.c.service_type == str(normalized_service), False


def _component_filter_key(service_type: ServiceType | str | None) -> str:
    value = str(service_type or "").strip()
    prefix = "component:"
    if not value.startswith(prefix):
        return ""
    return value[len(prefix):].strip()


def _component_service_key(module_key: str) -> str:
    key = str(module_key or "").strip()
    return f"component:{key}" if key else str(ServiceType.UNMATCHED)


def _component_label(module_key: str) -> str:
    key = str(module_key or "").strip()
    if not key:
        return str(ServiceType.UNMATCHED)
    try:
        from business.components.service import list_components

        for component in list_components():
            if str(component.get("component_key") or component.get("skill_key") or "") == key:
                return str(component.get("label") or key)
    except Exception:
        pass
    return key


def _service_or_component_label(value: str) -> str:
    component_key = _component_filter_key(value)
    if component_key:
        return _component_label(component_key)
    return _artifact_service_label(value)


def _audit_values(**metadata) -> dict[str, object]:
    values: dict[str, object] = {}
    text_fields = (
        "normalized_target",
        "stock_code",
        "stock_name",
        "customer_name",
        "institution",
        "market_date",
        "cache_key",
        "program_version",
        "ta_version",
        "renderer_version",
        "template_version",
    )
    for field in text_fields:
        if field in metadata:
            values[field] = str(metadata.get(field) or "")
    if "cache_hit" in metadata:
        values["cache_hit"] = 1 if metadata.get("cache_hit") else 0
    return values


def _external_action_type(service_type: ServiceType | None) -> ActionType:
    if service_type in (ServiceType.RATE, ServiceType.CONVERTIBLE_BOND):
        return ActionType.DELIVER_EFFECTIVE_CONTENT
    if service_type == ServiceType.TECHNICAL_ANALYSIS:
        return ActionType.GENERATE
    return ActionType.GENERATE


def external_request_identity_values(openid: str, service_type: ServiceType | None) -> dict[str, str]:
    return {
        "entry_type": str(EntryType.EXTERNAL_REQUEST),
        "action_type": str(_external_action_type(service_type)),
        "actor_type": str(ActorType.CUSTOMER),
        "actor_id": str(openid or ""),
        "actor_name": "",
        "actor_role": "",
    }


def business_record_identity_values(
    *,
    entry_type: EntryType,
    action_type: ActionType,
    actor_type: ActorType,
    actor_id: str = "",
    actor_name: str = "",
    actor_role: str = "",
) -> dict[str, str]:
    return {
        "entry_type": str(entry_type),
        "action_type": str(action_type),
        "actor_type": str(actor_type),
        "actor_id": str(actor_id or ""),
        "actor_name": str(actor_name or ""),
        "actor_role": str(actor_role or ""),
    }


def _request_action_type(item: dict) -> ActionType:
    if item.get("action_type"):
        return ActionType(item["action_type"])
    if item.get("service_type"):
        return _external_action_type(ServiceType(item["service_type"]))
    return ActionType.GENERATE


def _record_request_event_safe(
    *,
    request_id: str,
    openid: str = "",
    channel: str = "business",
    event_type: str,
    message_type: str = "",
    content: str = "",
    file_path: str = "",
    source_type: str = "request",
    source_id: str = "",
    result: str = "",
    error: str = "",
) -> None:
    try:
        from business.audit.event_service import record_request_event

        record_request_event(
            request_id=request_id,
            openid=openid,
            channel=channel,
            event_type=event_type,
            message_type=message_type,
            content=content,
            file_path=file_path,
            source_type=source_type,
            source_id=source_id or request_id,
            result=result,
            error=error,
        )
    except Exception as exc:
        logger.warning("[investment] record request event failed: %s", exc)


def _request_identity(request_id: str) -> tuple[str, str]:
    with connect() as conn:
        row = conn.execute(
            select(investment_request_records.c.openid, investment_request_records.c.raw_input).where(
                investment_request_records.c.request_id == request_id
            )
        ).fetchone()
    item = row_to_dict(row)
    return item.get("openid") or "", item.get("raw_input") or ""


def create_request_record(
    openid: str,
    raw_input: str,
    service_type: ServiceType | None,
    *,
    normalized_target: str = "",
    stock_code: str = "",
    stock_name: str = "",
    customer_name: str = "",
    institution: str = "",
    market_date: str = "",
    cache_key: str = "",
    cache_hit: bool = False,
    program_version: str = "",
    ta_version: str = "",
    renderer_version: str = "",
    template_version: str = "",
    module_key: str = "",
) -> str:
    request_id = str(uuid.uuid4())
    now = _now()
    with connect() as conn:
        conn.execute(
            insert(investment_request_records).values(
                request_id=request_id,
                openid=openid,
                raw_input=raw_input,
                service_type=str(service_type) if service_type else None,
                module_key=str(module_key or "").strip(),
                **external_request_identity_values(openid, service_type),
                status=str(Status.GENERATING),
                output_files="[]",
                **_audit_values(
                    normalized_target=normalized_target,
                    stock_code=stock_code,
                    stock_name=stock_name,
                    customer_name=customer_name,
                    institution=institution,
                    market_date=market_date,
                    cache_key=cache_key,
                    cache_hit=cache_hit,
                    program_version=program_version,
                    ta_version=ta_version,
                    renderer_version=renderer_version,
                    template_version=template_version,
                ),
                created_at=now,
                updated_at=now,
            )
        )
    _record_request_event_safe(
        request_id=request_id,
        openid=openid,
        event_type="request_received",
        message_type="text",
        content=raw_input,
        result="accepted",
    )
    return request_id


def create_business_workflow_record(
    *,
    entry_type: EntryType,
    service_type: ServiceType | None,
    action_type: ActionType,
    actor_type: ActorType,
    actor_id: str = "",
    actor_name: str = "",
    actor_role: str = "",
    openid: str = "",
    raw_input: str = "",
    normalized_target: str = "",
    stock_code: str = "",
    stock_name: str = "",
    customer_name: str = "",
    institution: str = "",
    market_date: str = "",
    cache_key: str = "",
    cache_hit: bool = False,
    program_version: str = "",
    ta_version: str = "",
    renderer_version: str = "",
    template_version: str = "",
    module_key: str = "",
) -> str:
    request_id = str(uuid.uuid4())
    now = _now()
    effective_openid = str(openid or actor_id or "")
    with connect() as conn:
        conn.execute(
            insert(investment_request_records).values(
                request_id=request_id,
                openid=effective_openid,
                raw_input=str(raw_input or ""),
                service_type=str(service_type) if service_type else None,
                module_key=str(module_key or "").strip(),
                **business_record_identity_values(
                    entry_type=entry_type,
                    action_type=action_type,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    actor_name=actor_name,
                    actor_role=actor_role,
                ),
                status=str(Status.GENERATING),
                output_files="[]",
                **_audit_values(
                    normalized_target=normalized_target,
                    stock_code=stock_code,
                    stock_name=stock_name,
                    customer_name=customer_name,
                    institution=institution,
                    market_date=market_date,
                    cache_key=cache_key,
                    cache_hit=cache_hit,
                    program_version=program_version,
                    ta_version=ta_version,
                    renderer_version=renderer_version,
                    template_version=template_version,
                ),
                created_at=now,
                updated_at=now,
            )
        )
    return request_id


def finish_business_workflow_record(
    request_id: str,
    *,
    status: Status,
    output_files: list[str] | None = None,
    error_code: ErrorCode | str | None = None,
    user_prompt: str = "",
    error_message: str = "",
    elapsed_ms: int | None = None,
    normalized_target: str = "",
    stock_code: str = "",
    stock_name: str = "",
    customer_name: str = "",
    institution: str = "",
    market_date: str = "",
    cache_key: str = "",
    cache_hit: bool = False,
    program_version: str = "",
    ta_version: str = "",
    renderer_version: str = "",
    template_version: str = "",
) -> None:
    values: dict[str, object] = {
        "status": str(status),
        "error_code": str(error_code or "") if error_code else None,
        "user_prompt": str(user_prompt or ""),
        "error_message": sanitize_sensitive_text(error_message),
        "output_files": _json_list(output_files or []),
        "elapsed_ms": elapsed_ms,
        "updated_at": _now(),
    }
    values.update(
        _audit_values(
            **{
                key: value
                for key, value in {
                    "normalized_target": normalized_target,
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "customer_name": customer_name,
                    "institution": institution,
                    "market_date": market_date,
                    "cache_key": cache_key,
                    "program_version": program_version,
                    "ta_version": ta_version,
                    "renderer_version": renderer_version,
                    "template_version": template_version,
                }.items()
                if value
            }
        )
    )
    if cache_hit:
        values["cache_hit"] = 1
    with connect() as conn:
        conn.execute(
            update(investment_request_records)
            .where(investment_request_records.c.request_id == request_id)
            .values(**values)
        )


def succeed_request_record(
    request_id: str,
    *,
    output_files: list[str],
    elapsed_ms: int,
    artifact_roles: dict[str, str] | None = None,
    artifact_versions: dict[str, str] | None = None,
    normalized_target: str = "",
    stock_code: str = "",
    stock_name: str = "",
    customer_name: str = "",
    institution: str = "",
    market_date: str = "",
    cache_key: str = "",
    cache_hit: bool = False,
    program_version: str = "",
    ta_version: str = "",
    renderer_version: str = "",
    template_version: str = "",
    warning: str = "",
    storage_namespace: str = "",
) -> dict[str, str]:
    service_type: ServiceType | None = None
    path_map: dict[str, str] = {}
    stored_output_files = list(output_files or [])
    stored_artifact_roles = dict(artifact_roles or {})
    stored_artifact_versions = dict(artifact_versions or {})
    values: dict[str, object] = {
        "status": str(Status.SUCCESS),
        "error_code": None,
        "user_prompt": "",
        "error_message": sanitize_sensitive_text(warning),
        "output_files": _json_list(stored_output_files),
        "elapsed_ms": elapsed_ms,
        "updated_at": _now(),
    }
    success_metadata = {
        "normalized_target": normalized_target,
        "stock_code": stock_code,
        "stock_name": stock_name,
        "customer_name": customer_name,
        "institution": institution,
        "market_date": market_date,
        "cache_key": cache_key,
        "program_version": program_version,
        "ta_version": ta_version,
        "renderer_version": renderer_version,
        "template_version": template_version,
    }
    values.update(_audit_values(**{key: value for key, value in success_metadata.items() if value}))
    if cache_hit:
        values["cache_hit"] = 1
    with connect() as conn:
        conn.execute(
            update(investment_request_records)
            .where(investment_request_records.c.request_id == request_id)
            .values(**values)
        )
        row = conn.execute(
            select(
                investment_request_records.c.service_type,
                investment_request_records.c.created_at,
            ).where(investment_request_records.c.request_id == request_id)
        ).fetchone()
        item = row_to_dict(row)
        if item.get("service_type"):
            service_type = ServiceType(item["service_type"])
        storage_date = str(item.get("created_at") or "")[:10]
    if service_type is not None:
        from business.artifacts.artifact_service import archive_output_files

        stored_output_files, stored_artifact_roles, stored_artifact_versions, path_map = archive_output_files(
            request_id,
            stored_output_files,
            service_type,
            artifact_roles=stored_artifact_roles,
            artifact_versions=stored_artifact_versions,
            owner_type="request",
            storage_date=storage_date,
            storage_namespace=storage_namespace,
        )
        with connect() as conn:
            conn.execute(
                update(investment_request_records)
                .where(investment_request_records.c.request_id == request_id)
                .values(output_files=_json_list(stored_output_files), updated_at=_now())
            )
        for file_path in stored_output_files:
            role = stored_artifact_roles.get(file_path, "image")
            version_tag = stored_artifact_versions.get(file_path, "")
            record_output_file(request_id, file_path, None, service_type, artifact_role=role, version_tag=version_tag)
    openid, raw_input = _request_identity(request_id)
    _record_request_event_safe(
        request_id=request_id,
        openid=openid,
        event_type="generation_success",
        message_type="system",
        content=raw_input,
        result="success",
    )
    return path_map


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
                output_files=_json_list([]),
                market_date="",
                cache_key="",
                cache_hit=0,
                program_version="",
                ta_version="",
                renderer_version="",
                template_version="",
                elapsed_ms=elapsed_ms,
                updated_at=_now(),
            )
        )
    openid, raw_input = _request_identity(request_id)
    _record_request_event_safe(
        request_id=request_id,
        openid=openid,
        event_type="generation_failed",
        message_type="system",
        content=raw_input,
        result="failed",
        error=safe_detail,
    )


def append_request_warning(request_id: str, detail: str) -> None:
    safe_detail = sanitize_sensitive_text(detail).strip()
    if not request_id or not safe_detail:
        return
    with connect() as conn:
        row = conn.execute(
            select(investment_request_records.c.error_message).where(
                investment_request_records.c.request_id == request_id
            )
        ).fetchone()
        if row is None:
            return
        existing = (row_to_dict(row).get("error_message") or "").strip()
        if existing and safe_detail in existing:
            next_detail = existing
        elif existing:
            next_detail = f"{existing}\n{safe_detail}"
        else:
            next_detail = safe_detail
        conn.execute(
            update(investment_request_records)
            .where(investment_request_records.c.request_id == request_id)
            .values(error_message=next_detail, updated_at=_now())
        )


def mark_request_delivered(request_id: str) -> None:
    append_request_warning(request_id, DELIVERY_DELIVERED_MARKER)
    openid, raw_input = _request_identity(request_id)
    _record_request_event_safe(
        request_id=request_id,
        openid=openid,
        event_type="delivery_success",
        message_type="system",
        content=raw_input,
        result="success",
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
    customer_mobile = item.get("customer_mobile") or ""
    customer_name = item.get("customer_name") or item.get("customer_user_name") or ""
    institution = item.get("institution") or item.get("customer_user_institution") or ""
    output_files = _load_list(item["output_files"])
    raw_error_message = item["error_message"] or ""
    visible_error_message = _visible_delivery_message(raw_error_message)
    delivery_status, delivery_detail = _delivery_status(status, raw_error_message, output_files)
    return RequestRecord(
        request_id=item["request_id"],
        openid=item["openid"],
        raw_input=item["raw_input"],
        service_type=ServiceType(item["service_type"]) if item["service_type"] else None,
        module_key=item.get("module_key") or "",
        entry_type=EntryType(item.get("entry_type") or EntryType.EXTERNAL_REQUEST),
        action_type=_request_action_type(item),
        actor_type=ActorType(item.get("actor_type") or ActorType.CUSTOMER),
        actor_id=item.get("actor_id") or item["openid"],
        actor_name=item.get("actor_name") or "",
        actor_role=item.get("actor_role") or "",
        status=status,
        error_code=ErrorCode(item["error_code"]) if item["error_code"] else None,
        user_prompt=item["user_prompt"] or "",
        error_message=visible_error_message,
        output_files=output_files,
        normalized_target=item.get("normalized_target") or "",
        stock_code=item.get("stock_code") or "",
        stock_name=item.get("stock_name") or "",
        customer_name=customer_name,
        institution=institution,
        market_date=item.get("market_date") or "",
        cache_key=item.get("cache_key") or "",
        cache_hit=bool(item.get("cache_hit")),
        program_version=item.get("program_version") or "",
        ta_version=item.get("ta_version") or "",
        renderer_version=item.get("renderer_version") or "",
        template_version=item.get("template_version") or "",
        created_at=created_at,
        elapsed_ms=item["elapsed_ms"],
        status_warning=_request_status_warning(status, created_at, raw_error_message),
        customer_mobile=customer_mobile,
        customer_display=customer_mobile or item["openid"],
        delivery_status=delivery_status,
        delivery_detail=delivery_detail,
    )


def get_request_record(request_id: str) -> RequestRecord:
    with connect() as conn:
        row = conn.execute(
            select(investment_request_records).where(investment_request_records.c.request_id == request_id)
        ).fetchone()
    if row is None:
        raise KeyError(request_id)
    return _row_to_request(row)


def list_request_records(
    limit: int = 50,
    *,
    service_type: ServiceType | str | None = None,
    module_key: str = "",
    entry_type: EntryType | str | None = None,
    status: Status | str | None = None,
    keyword: str = "",
    customer: str = "",
    start_date: str = "",
    end_date: str = "",
) -> list[RequestRecord]:
    records, _total = list_request_records_page(
        page=1,
        page_size=limit,
        service_type=service_type,
        module_key=module_key,
        entry_type=entry_type,
        status=status,
        keyword=keyword,
        customer=customer,
        start_date=start_date,
        end_date=end_date,
    )
    return records


def build_request_record_conditions(
    table,
    users,
    *,
    service_type: ServiceType | str | None = None,
    module_key: str = "",
    entry_type: EntryType | str | None = None,
    status: Status | str | None = None,
    keyword: str = "",
    customer: str = "",
    start_date: str = "",
    end_date: str = "",
) -> tuple[list, bool]:
    conditions = []
    service_condition, impossible = _service_condition(table, service_type)
    if impossible:
        return [], True
    if service_condition is not None:
        conditions.append(service_condition)
    normalized_module_key = str(module_key or "").strip()
    if normalized_module_key:
        conditions.append(table.c.module_key == normalized_module_key)
    if entry_type is not None and str(entry_type or "").strip():
        try:
            normalized_entry_type = EntryType(entry_type)
        except ValueError:
            return [], True
        conditions.append(table.c.entry_type == str(normalized_entry_type))
    if status is not None:
        try:
            normalized_status = Status(status)
        except ValueError:
            return [], True
        conditions.append(table.c.status == str(normalized_status))
    if start_date:
        conditions.append(table.c.created_at >= str(start_date))
    if end_date:
        conditions.append(table.c.created_at <= str(end_date))
    keyword_text = str(keyword or "").strip()
    if keyword_text:
        pattern = f"%{keyword_text}%"
        event_match = exists(
            select(1)
            .select_from(request_events)
            .where(request_events.c.request_id == table.c.request_id)
            .where(
                or_(
                    request_events.c.openid.ilike(pattern),
                    request_events.c.channel.ilike(pattern),
                    request_events.c.event_type.ilike(pattern),
                    request_events.c.message_type.ilike(pattern),
                    request_events.c.content.ilike(pattern),
                    request_events.c.media_id.ilike(pattern),
                    request_events.c.file_path.ilike(pattern),
                    request_events.c.source_type.ilike(pattern),
                    request_events.c.source_id.ilike(pattern),
                    request_events.c.result.ilike(pattern),
                    request_events.c.error.ilike(pattern),
                )
            )
        )
        conditions.append(
            or_(
                table.c.request_id.ilike(pattern),
                table.c.openid.ilike(pattern),
                table.c.raw_input.ilike(pattern),
                table.c.service_type.ilike(pattern),
                table.c.module_key.ilike(pattern),
                table.c.status.ilike(pattern),
                table.c.error_code.ilike(pattern),
                table.c.user_prompt.ilike(pattern),
                table.c.error_message.ilike(pattern),
                table.c.output_files.ilike(pattern),
                table.c.normalized_target.ilike(pattern),
                table.c.stock_code.ilike(pattern),
                table.c.stock_name.ilike(pattern),
                table.c.customer_name.ilike(pattern),
                table.c.institution.ilike(pattern),
                table.c.market_date.ilike(pattern),
                table.c.cache_key.ilike(pattern),
                table.c.program_version.ilike(pattern),
                table.c.ta_version.ilike(pattern),
                table.c.renderer_version.ilike(pattern),
                table.c.template_version.ilike(pattern),
                users.c.name.ilike(pattern),
                users.c.institution.ilike(pattern),
                users.c.mobile.ilike(pattern),
                event_match,
            )
        )
    customer_text = str(customer or "").strip()
    if customer_text:
        customer_pattern = f"%{customer_text}%"
        conditions.append(
            or_(
                table.c.openid.ilike(customer_pattern),
                users.c.mobile.ilike(customer_pattern),
                users.c.name.ilike(customer_pattern),
                users.c.institution.ilike(customer_pattern),
            )
        )
    return conditions, False


def list_request_records_page(
    *,
    page: int = 1,
    page_size: int = 50,
    service_type: ServiceType | str | None = None,
    module_key: str = "",
    entry_type: EntryType | str | None = None,
    status: Status | str | None = None,
    keyword: str = "",
    customer: str = "",
    start_date: str = "",
    end_date: str = "",
) -> tuple[list[RequestRecord], int]:
    table = investment_request_records
    users = investment_users
    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 50))
    offset = (page - 1) * page_size
    stmt = (
        select(
            table,
            users.c.mobile.label("customer_mobile"),
            users.c.name.label("customer_user_name"),
            users.c.institution.label("customer_user_institution"),
        )
        .select_from(table.outerjoin(users, table.c.openid == users.c.openid))
        .order_by(table.c.created_at.desc())
        .limit(page_size)
        .offset(offset)
    )
    conditions, impossible = build_request_record_conditions(
        table,
        users,
        service_type=service_type,
        module_key=module_key,
        entry_type=entry_type,
        status=status,
        keyword=keyword,
        customer=customer,
        start_date=start_date,
        end_date=end_date,
    )
    if impossible:
        return [], 0
    if conditions:
        stmt = stmt.where(*conditions)
    count_stmt = select(func.count()).select_from(table.outerjoin(users, table.c.openid == users.c.openid))
    if conditions:
        count_stmt = count_stmt.where(*conditions)
    with connect() as conn:
        total = int(conn.execute(count_stmt).scalar_one() or 0)
        rows = conn.execute(stmt).fetchall()
    return [_row_to_request(row) for row in rows], total


def list_output_files(owner_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            select(investment_output_files)
            .where(investment_output_files.c.owner_id == owner_id)
            .order_by(investment_output_files.c.id)
        ).fetchall()
    files = []
    for row in rows:
        item = row_to_dict(row)
        file_id = str(item.get("id") or "")
        item["file_id"] = file_id
        item["file_url"] = f"/api/file?id={file_id}" if file_id else ""
        files.append(item)
    return files


def _artifact_service_label(service_type: str) -> str:
    labels = {
        str(ServiceType.TECHNICAL_ANALYSIS): "技术分析",
        str(ServiceType.RATE): "利率",
        str(ServiceType.CONVERTIBLE_BOND): "转债",
    }
    return labels.get(str(service_type or ""), str(service_type or ""))


def _artifact_target_label(item: dict) -> str:
    target = str(item.get("normalized_target") or "").strip()
    stock_name = str(item.get("stock_name") or "").strip()
    if target and stock_name and stock_name != target:
        return f"{target} {stock_name}"
    return target or stock_name or "全市场"


def _content_target_label(service_type: ServiceType | str) -> str:
    normalized = normalize_service(service_type)
    if normalized == ServiceType.RATE:
        return "利率内容"
    if normalized == ServiceType.CONVERTIBLE_BOND:
        return "转债内容"
    return "后台内容"


def _date_part(value: str, length: int = 10) -> str:
    text = str(value or "")
    return text[:length] if len(text) >= length else ""


def _content_expires_at_expired(expires_at: str, *, now: str | None = None) -> bool:
    text = str(expires_at or "").strip()
    if not text:
        return False
    now_text = now or _now()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        parsed_now = datetime.fromisoformat(now_text.replace("Z", "+00:00"))
    except ValueError:
        return text <= now_text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    if parsed_now.tzinfo is None:
        parsed_now = parsed_now.replace(tzinfo=UTC)
    return parsed <= parsed_now


def _content_generated_at_expr():
    artifact_created_at = (
        select(func.min(investment_output_files.c.created_at))
        .where(
            investment_output_files.c.owner_id == investment_daily_contents.c.content_id,
            investment_output_files.c.owner_type == "content",
        )
        .scalar_subquery()
    )
    return func.coalesce(artifact_created_at, investment_daily_contents.c.updated_at, investment_daily_contents.c.created_at)


def _artifact_bucket(role: str, owner_type: str = "") -> str:
    role = str(role or "").strip()
    if role in {"signal_card", "output_image"}:
        return "output"
    if role in {"main_chart", "markdown_report", "generated_text"}:
        return "intermediate"
    if role.startswith("source") or owner_type == "input":
        return "input"
    if role in {"image", "markdown"}:
        return "output" if role == "image" else "intermediate"
    return "intermediate"


def _artifact_virtual_name(role: str, file_path: str) -> str:
    suffix = Path(file_path).suffix.lower() if file_path else ""
    if role == "signal_card":
        return f"signal_card{suffix or '.png'}"
    if role == "main_chart":
        return f"main_chart{suffix or '.png'}"
    if role == "markdown_report":
        return f"markdown_report{suffix or '.md'}"
    if role == "output_image":
        return f"output_image{suffix or '.png'}"
    if role == "source_image":
        return Path(file_path).name or f"source_image{suffix or '.png'}"
    return Path(file_path).name or f"{role or 'artifact'}{suffix or ''}"


def _file_payload(item: dict) -> dict:
    from urllib.parse import quote

    file_id = str(item.get("id") or item.get("file_id") or "")
    file_path = str(item.get("file_path") or "")
    payload = dict(item)
    payload["file_id"] = file_id
    payload["file_url"] = item.get("file_url") or (f"/api/file?id={file_id}" if file_id else f"/api/file?path={quote(file_path)}" if file_path else "")
    return payload


def _artifact_file_payload(item: dict) -> dict:
    role = str(item.get("artifact_role") or item.get("file_type") or "artifact")
    bucket = _artifact_bucket(role, str(item.get("owner_type") or ""))
    file_payload = _file_payload(item)
    file_payload.update(
        {
            "kind": "file",
            "group": bucket,
            "virtual_path": f"{bucket}/{_artifact_virtual_name(role, str(item.get('file_path') or ''))}",
        }
    )
    return file_payload


def _virtual_input_file(raw_input: str) -> dict:
    return {
        "kind": "virtual_text",
        "group": "input",
        "virtual_path": "input/raw_input.txt",
        "file_name": "raw_input.txt",
        "file_type": "text",
        "artifact_role": "raw_input",
        "content": raw_input or "",
    }


def _virtual_generated_text_file(generated_text: str) -> dict:
    return {
        "kind": "virtual_text",
        "group": "intermediate",
        "virtual_path": "intermediate/generated_text.txt",
        "file_name": "generated_text.txt",
        "file_type": "text",
        "artifact_role": "generated_text",
        "content": generated_text or "",
    }


def _dedupe_files(files: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for file in files:
        key = (file.get("virtual_path"), file.get("file_path") or file.get("content") or "")
        if key in seen:
            continue
        seen.add(key)
        result.append(file)
    order = {"input": 0, "output": 1, "intermediate": 2}
    return sorted(result, key=lambda item: (order.get(item.get("group"), 99), item.get("virtual_path") or ""))


def _request_row(request_id: str) -> dict:
    if not request_id:
        return {}
    with connect() as conn:
        row = conn.execute(
            select(investment_request_records).where(investment_request_records.c.request_id == request_id)
        ).fetchone()
    return row_to_dict(row)


def _artifact_files_for_owner(owner_id: str, output_files: list[str]) -> list[dict]:
    files = list_output_files(owner_id) if owner_id else []
    if files:
        return [_artifact_file_payload(file) for file in files]
    fallback = []
    for file_path in output_files:
        role = "markdown_report" if str(file_path).lower().endswith((".md", ".markdown")) else "image"
        fallback.append(
            _artifact_file_payload(
                {
                    "owner_id": owner_id,
                    "owner_type": "request",
                    "file_path": file_path,
                    "file_type": "markdown" if role == "markdown_report" else "image",
                    "artifact_role": role,
                }
            )
        )
    return fallback


def _display_status_for_content(item: dict) -> tuple[str, str]:
    status = str(item.get("status") or "")
    expires_at = str(item.get("expires_at") or "")
    if status == str(Status.EFFECTIVE) and not _content_expires_at_expired(expires_at):
        return "active", "有效"
    if status == str(Status.GENERATED) and not _content_expires_at_expired(expires_at):
        return "unused", "未使用"
    return "invalid", "失效"


def _status_category(value: str) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "all": "",
        "": "",
        "active": "active",
        "valid": "active",
        "effective": "active",
        "unused": "unused",
        "generated": "unused",
        "invalid": "invalid",
        "invalidated": "invalid",
        "archived": "invalid",
        "failed": "invalid",
        "expired": "invalid",
    }
    return aliases.get(normalized, normalized)


def _row_to_content_artifact_package(content_item: dict) -> dict:
    content_id = str(content_item.get("content_id") or "")
    service_type = str(content_item.get("service_type") or "")
    effective_date = str(content_item.get("effective_date") or "")
    output_image = str(content_item.get("output_image") or "")
    source_text = str(content_item.get("source_text") or "")
    generated_text = str(content_item.get("generated_text") or "")
    generated_at = str(content_item.get("generated_at") or content_item.get("updated_at") or content_item.get("created_at") or "")
    generated_date = _date_part(generated_at)
    output_files = [output_image] if output_image else []
    files = [_virtual_input_file(source_text)] if source_text else []
    files.extend(_artifact_files_for_owner(content_id, output_files))
    if generated_text:
        files.append(_virtual_generated_text_file(generated_text))
    display_name = _content_target_label(service_type)
    display_status, display_status_label = _display_status_for_content(content_item)
    return {
        "package_id": content_id,
        "source_type": "content",
        "service_type": service_type,
        "service_label": _artifact_service_label(service_type),
        "market_date": generated_date,
        "generated_at": generated_at,
        "generated_date": generated_date,
        "effective_date": effective_date,
        "normalized_target": display_name,
        "stock_name": "",
        "display_name": display_name,
        "display_path": [_artifact_service_label(service_type), effective_date, display_name],
        "version_fingerprint": f"v{int(content_item.get('content_version') or 1)}",
        "created_from_request_id": "",
        "content_id": content_id,
        "related_request_ids": [],
        "request_count": 0,
        "hit_count": 0,
        "created_at": content_item.get("created_at") or "",
        "updated_at": content_item.get("updated_at") or "",
        "status": content_item.get("status") or "",
        "display_status": display_status,
        "display_status_label": display_status_label,
        "files": _dedupe_files(files),
    }


def _row_to_internal_call_artifact_package(call_item: dict) -> dict:
    call_id = str(call_item.get("call_id") or call_item.get("request_id") or "")
    service_type = str(call_item.get("service_type") or ServiceType.TECHNICAL_ANALYSIS)
    module_key = str(call_item.get("module_key") or "")
    service_key = _component_service_key(module_key) if service_type == str(ServiceType.UNMATCHED) and module_key else service_type
    service_label = _service_or_component_label(service_key)
    generated_at = str(call_item.get("created_at") or call_item.get("updated_at") or "")
    generated_date = _date_part(generated_at)
    output_files = _load_list(call_item.get("outputs") or call_item.get("output_files"))
    raw_input = str(call_item.get("input_text") or call_item.get("raw_input") or "")
    output_text = str(call_item.get("output_text") or call_item.get("user_prompt") or "")
    files = [_virtual_input_file(raw_input)] if raw_input else []
    files.extend(_artifact_files_for_owner(call_id, output_files))
    if output_text:
        files.append(_virtual_generated_text_file(output_text))
    display_name = raw_input or _artifact_service_label(service_type)
    return {
        "package_id": call_id,
        "source_type": "internal_call",
        "service_type": service_key,
        "service_label": service_label,
        "module_key": module_key,
        "market_date": generated_date,
        "generated_at": generated_at,
        "generated_date": generated_date,
        "normalized_target": display_name,
        "stock_name": "",
        "display_name": display_name,
        "display_path": [service_label, generated_date, display_name],
        "version_fingerprint": "",
        "created_from_request_id": call_id,
        "related_request_ids": [],
        "request_count": 0,
        "hit_count": 0,
        "created_at": call_item.get("created_at") or "",
        "updated_at": call_item.get("updated_at") or "",
        "status": call_item.get("status") or "",
        "files": _dedupe_files(files),
    }


def _row_to_product_artifact_package(item: dict) -> dict:
    product_id = str(item.get("product_id") or "")
    service_type = str(item.get("business_type") or "")
    module_key = _component_filter_key(service_type)
    output_files = _load_list(item.get("output_files"))
    generated_at = str(item.get("created_at") or item.get("effective_at") or item.get("updated_at") or "")
    generated_date = _date_part(generated_at)
    business_date = str(item.get("business_date") or "")
    folder_date = generated_date or business_date
    target = str(item.get("target_key") or "")
    display_name = str(item.get("target_label") or target or "产物")
    source_request_id = str(item.get("source_request_id") or "")
    files = []
    files.extend(_artifact_files_for_owner(product_id, output_files))
    text_content = str(item.get("text_content") or "")
    if text_content:
        files.append(_virtual_generated_text_file(text_content))
    service_label = _service_or_component_label(service_type)
    display_status, display_status_label = product_display_status(item)
    return {
        "level": "package",
        "key": product_id,
        "package_id": product_id,
        "source_type": "product",
        "label": display_name,
        "service_type": service_type,
        "module_key": module_key,
        "service_label": service_label,
        "market_date": folder_date,
        "generated_at": generated_at,
        "generated_date": generated_date,
        "business_date": business_date,
        "normalized_target": target,
        "stock_name": "",
        "display_name": display_name,
        "display_path": [service_label, folder_date, display_name],
        "version_fingerprint": str(item.get("version_fingerprint") or ""),
        "product_id": product_id,
        "source_request_id": source_request_id,
        "source_content_id": str(item.get("source_content_id") or ""),
        "source_cache_key": str(item.get("source_cache_key") or ""),
        "created_from_request_id": source_request_id,
        "related_request_ids": [source_request_id] if source_request_id else [],
        "request_count": 1 if source_request_id else 0,
        "file_count": len(output_files),
        "hit_count": int(item.get("hit_count") or 0),
        "created_at": str(item.get("created_at") or ""),
        "updated_at": str(item.get("updated_at") or ""),
        "status": str(item.get("status") or ""),
        "display_status": display_status,
        "display_status_label": display_status_label,
        "files": _dedupe_files(files),
    }


def _content_artifact_conditions(
    service_type: ServiceType | str | None,
    start_date: str = "",
    end_date: str = "",
    keyword: str = "",
    status_category: str = "",
):
    conditions = []
    if _component_filter_key(service_type):
        return None
    if service_type is not None and str(service_type or "").strip():
        normalized_service = normalize_service(service_type)
        valid_unmatched_inputs = {str(ServiceType.UNMATCHED), "unmatched"}
        if normalized_service == ServiceType.UNMATCHED and str(service_type) not in valid_unmatched_inputs:
            return None
        if normalized_service == ServiceType.TECHNICAL_ANALYSIS:
            return None
        conditions.append(investment_daily_contents.c.service_type == str(normalized_service))
    else:
        conditions.append(
            investment_daily_contents.c.service_type.in_(
                [str(ServiceType.RATE), str(ServiceType.CONVERTIBLE_BOND)]
            )
        )
    generated_at = _content_generated_at_expr()
    if start_date:
        conditions.append(func.substr(generated_at, 1, 10) >= str(start_date))
    if end_date:
        conditions.append(func.substr(generated_at, 1, 10) <= str(end_date))
    conditions.append(investment_daily_contents.c.effective_date != "")
    conditions.append(
        or_(
            investment_daily_contents.c.output_image != "",
            investment_daily_contents.c.generated_text != "",
        )
    )
    category = _status_category(status_category)
    if category == "active":
        conditions.append(investment_daily_contents.c.status == str(Status.EFFECTIVE))
        now = _now()
        conditions.append(
            investment_daily_contents.c.expires_at.is_(None)
            | (investment_daily_contents.c.expires_at == "")
            | (investment_daily_contents.c.expires_at > now)
        )
    elif category == "unused":
        conditions.append(investment_daily_contents.c.status == str(Status.GENERATED))
        now = _now()
        conditions.append(
            investment_daily_contents.c.expires_at.is_(None)
            | (investment_daily_contents.c.expires_at == "")
            | (investment_daily_contents.c.expires_at > now)
        )
    elif category == "invalid":
        now = _now()
        conditions.append(
            or_(
                investment_daily_contents.c.status.in_(
                    [str(Status.ARCHIVED), str(Status.INVALIDATED), str(Status.GENERATE_FAILED)]
                ),
                (
                    (investment_daily_contents.c.expires_at.is_not(None))
                    & (investment_daily_contents.c.expires_at != "")
                    & (investment_daily_contents.c.expires_at <= now)
                ),
            )
        )
    else:
        conditions.append(
            investment_daily_contents.c.status.in_(
                [
                    str(Status.GENERATED),
                    str(Status.EFFECTIVE),
                    str(Status.ARCHIVED),
                    str(Status.INVALIDATED),
                    str(Status.GENERATE_FAILED),
                ]
            )
        )
    keyword_text = str(keyword or "").strip()
    if keyword_text:
        pattern = f"%{keyword_text}%"
        conditions.append(
            or_(
                investment_daily_contents.c.content_id.ilike(pattern),
                investment_daily_contents.c.service_type.ilike(pattern),
                investment_daily_contents.c.source_text.ilike(pattern),
                investment_daily_contents.c.generated_text.ilike(pattern),
                investment_daily_contents.c.output_image.ilike(pattern),
                investment_daily_contents.c.effective_date.ilike(pattern),
            )
        )
    return conditions


def _internal_call_artifact_conditions(service_type: ServiceType | str | None, start_date: str = "", end_date: str = "", keyword: str = ""):
    conditions = []
    component_key = _component_filter_key(service_type)
    if component_key:
        conditions.append(investment_request_records.c.entry_type == str(EntryType.INTERNAL_CALL))
        conditions.append(investment_request_records.c.service_type == str(ServiceType.UNMATCHED))
        conditions.append(investment_request_records.c.module_key == component_key)
    elif service_type is not None and str(service_type or "").strip():
        normalized_service = normalize_service(service_type)
        valid_unmatched_inputs = {str(ServiceType.UNMATCHED), "unmatched"}
        if normalized_service == ServiceType.UNMATCHED and str(service_type) not in valid_unmatched_inputs:
            return None
        if normalized_service != ServiceType.TECHNICAL_ANALYSIS:
            return None
        conditions.append(investment_request_records.c.entry_type == str(EntryType.INTERNAL_CALL))
        conditions.append(investment_request_records.c.service_type == str(ServiceType.TECHNICAL_ANALYSIS))
    else:
        conditions.append(investment_request_records.c.entry_type == str(EntryType.INTERNAL_CALL))
        conditions.append(
            or_(
                investment_request_records.c.service_type == str(ServiceType.TECHNICAL_ANALYSIS),
                (
                    (investment_request_records.c.service_type == str(ServiceType.UNMATCHED))
                    & (investment_request_records.c.module_key != "")
                ),
            )
        )
    conditions.append(investment_request_records.c.status == str(Status.SUCCESS))
    if start_date:
        conditions.append(func.substr(investment_request_records.c.created_at, 1, 10) >= str(start_date))
    if end_date:
        conditions.append(func.substr(investment_request_records.c.created_at, 1, 10) <= str(end_date))
    keyword_text = str(keyword or "").strip()
    if keyword_text:
        pattern = f"%{keyword_text}%"
        conditions.append(
            or_(
                investment_request_records.c.request_id.ilike(pattern),
                investment_request_records.c.service_type.ilike(pattern),
                investment_request_records.c.raw_input.ilike(pattern),
                investment_request_records.c.error_message.ilike(pattern),
                investment_request_records.c.output_files.ilike(pattern),
            )
        )
    return conditions


def _product_matches_package_id(item: dict, normalized_package_id: str) -> bool:
    return normalized_package_id in {
        str(item.get("product_id") or ""),
        str(item.get("source_cache_key") or ""),
        str(item.get("source_content_id") or ""),
        str(item.get("source_request_id") or ""),
    }


def _artifact_keyword_like_pattern(keyword: str) -> str:
    text = str(keyword or "").strip().lower()
    text = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{text}%"


def _product_artifact_date_expr():
    return func.substr(
        func.coalesce(
            func.nullif(investment_products.c.created_at, ""),
            func.nullif(investment_products.c.effective_at, ""),
            func.nullif(investment_products.c.updated_at, ""),
            investment_products.c.business_date,
        ),
        1,
        10,
    )


def _product_artifact_conditions(
    service_type: ServiceType | str | None,
    start_date: str = "",
    end_date: str = "",
    keyword: str = "",
    include_invalidated: bool = False,
    status_category: str = "",
):
    conditions = []
    if service_type is not None and str(service_type or "").strip():
        component_key = _component_filter_key(service_type)
        if component_key:
            conditions.append(investment_products.c.business_type == _component_service_key(component_key))
        else:
            normalized_service = normalize_service(service_type)
            valid_unmatched_inputs = {str(ServiceType.UNMATCHED), "unmatched"}
            if normalized_service == ServiceType.UNMATCHED and str(service_type) not in valid_unmatched_inputs:
                conditions.append(investment_products.c.business_type == "__none__")
            else:
                conditions.append(investment_products.c.business_type == str(normalized_service))
    category = _status_category(status_category)
    if category == "active":
        conditions.append(investment_products.c.status == PRODUCT_STATUS_ACTIVE)
        conditions.append(_product_expires_at_condition(_now()))
    elif category == "unused":
        conditions.append(investment_products.c.product_id == "__none__")
    elif category == "invalid":
        now = _now()
        conditions.append(
            or_(
                investment_products.c.status.in_(
                    [PRODUCT_STATUS_INVALIDATED, PRODUCT_STATUS_ARCHIVED, PRODUCT_STATUS_FAILED]
                ),
                (
                    (investment_products.c.expires_at.is_not(None))
                    & (investment_products.c.expires_at != "")
                    & (investment_products.c.expires_at <= now)
                ),
            )
        )
    product_artifact_date = _product_artifact_date_expr()
    if start_date:
        conditions.append(product_artifact_date >= str(start_date))
    if end_date:
        conditions.append(product_artifact_date <= str(end_date))
    keyword_text = str(keyword or "").strip().lower()
    if keyword_text:
        pattern = _artifact_keyword_like_pattern(keyword_text)
        conditions.append(
            or_(
                func.lower(investment_products.c.product_id).like(pattern, escape="\\"),
                func.lower(investment_products.c.business_type).like(pattern, escape="\\"),
                func.lower(investment_products.c.target_key).like(pattern, escape="\\"),
                func.lower(investment_products.c.target_label).like(pattern, escape="\\"),
                func.lower(investment_products.c.business_date).like(pattern, escape="\\"),
                func.lower(investment_products.c.version_fingerprint).like(pattern, escape="\\"),
                func.lower(investment_products.c.source_request_id).like(pattern, escape="\\"),
                func.lower(investment_products.c.source_content_id).like(pattern, escape="\\"),
                func.lower(investment_products.c.source_cache_key).like(pattern, escape="\\"),
                func.lower(investment_products.c.source_type).like(pattern, escape="\\"),
                func.lower(investment_products.c.output_files).like(pattern, escape="\\"),
                func.lower(investment_products.c.text_content).like(pattern, escape="\\"),
            )
        )
    return conditions


def _product_source_dedupe_keys(
    *,
    service_type: ServiceType | str | None,
    start_date: str = "",
    end_date: str = "",
    package_id: str = "",
    include_invalidated: bool = False,
    status_category: str = "",
) -> tuple[set[str], set[str], set[str]]:
    conditions = _product_artifact_conditions(
        service_type,
        start_date,
        end_date,
        keyword="",
        include_invalidated=include_invalidated,
        status_category=status_category,
    )
    if package_id:
        normalized_package_id = str(package_id)
        conditions.append(
            or_(
                investment_products.c.product_id == normalized_package_id,
                investment_products.c.source_cache_key == normalized_package_id,
                investment_products.c.source_content_id == normalized_package_id,
                investment_products.c.source_request_id == normalized_package_id,
            )
        )
    stmt = select(
        investment_products.c.source_cache_key,
        investment_products.c.source_content_id,
        investment_products.c.source_request_id,
    )
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.distinct()
    with connect() as conn:
        rows = [row_to_dict(row) for row in conn.execute(stmt).fetchall()]
    return (
        {str(item.get("source_cache_key") or "") for item in rows if item.get("source_cache_key")},
        {str(item.get("source_content_id") or "") for item in rows if item.get("source_content_id")},
        {str(item.get("source_request_id") or "") for item in rows if item.get("source_request_id")},
    )


def _product_source_dedupe_keys_from_rows(rows: list[dict]) -> tuple[set[str], set[str], set[str]]:
    return (
        {str(item.get("source_cache_key") or "") for item in rows if item.get("source_cache_key")},
        {str(item.get("source_content_id") or "") for item in rows if item.get("source_content_id")},
        {str(item.get("source_request_id") or "") for item in rows if item.get("source_request_id")},
    )


def _artifact_package_sources(
    *,
    service_type: ServiceType | str | None,
    start_date: str = "",
    end_date: str = "",
    keyword: str = "",
    package_id: str = "",
    include_invalidated: bool = False,
    status_category: str = "",
) -> tuple[list[dict], int]:
    category = _status_category(status_category)
    product_status_category = "" if category in {"active", "invalid"} else status_category
    product_conditions = _product_artifact_conditions(
        service_type,
        start_date,
        end_date,
        keyword,
        include_invalidated=include_invalidated,
        status_category=product_status_category,
    )
    if package_id:
        normalized_package_id = str(package_id)
        product_conditions.append(
            or_(
                investment_products.c.product_id == normalized_package_id,
                investment_products.c.source_cache_key == normalized_package_id,
                investment_products.c.source_content_id == normalized_package_id,
                investment_products.c.source_request_id == normalized_package_id,
            )
        )
    product_stmt = select(investment_products)
    product_count = select(func.count()).select_from(investment_products)
    if product_conditions:
        product_stmt = product_stmt.where(*product_conditions)
        product_count = product_count.where(*product_conditions)
    product_stmt = product_stmt.order_by(investment_products.c.created_at.desc(), investment_products.c.product_id.desc())
    with connect() as conn:
        product_rows = [row_to_dict(row) for row in conn.execute(product_stmt).fetchall()]
    if category in {"active", "invalid"}:
        product_rows = [
            row
            for row in product_rows
            if product_display_status(row)[0] == category
        ]
    total = len(product_rows)
    source_cache_keys, source_content_ids, source_request_ids = _product_source_dedupe_keys_from_rows(product_rows)
    content_conditions = _content_artifact_conditions(
        service_type,
        start_date,
        end_date,
        keyword,
        status_category=status_category,
    )
    content_rows: list[dict] = []
    if content_conditions is not None:
        if package_id:
            content_conditions.append(investment_daily_contents.c.content_id == str(package_id))
        if source_content_ids:
            content_conditions.append(~investment_daily_contents.c.content_id.in_(source_content_ids))
        content_stmt = select(
            investment_daily_contents,
            _content_generated_at_expr().label("generated_at"),
        ).where(*content_conditions)
        with connect() as conn:
            content_rows = [row_to_dict(row) for row in conn.execute(content_stmt).fetchall()]
    total += len(content_rows)
    rows = [{"kind": "product", "item": row} for row in product_rows]
    rows.extend({"kind": "content", "item": row} for row in content_rows)
    return rows, total


def list_artifact_packages_page(
    *,
    page: int = 1,
    page_size: int = 50,
    service_type: ServiceType | str | None = None,
    start_date: str = "",
    end_date: str = "",
    keyword: str = "",
    package_id: str = "",
    include_invalidated: bool = False,
    status_category: str = "",
) -> tuple[list[dict], int]:
    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 50))
    source_rows, total = _artifact_package_sources(
        service_type=service_type,
        start_date=start_date,
        end_date=end_date,
        keyword=keyword,
        package_id=package_id,
        include_invalidated=include_invalidated,
        status_category=status_category,
    )
    packages = [
        _row_to_product_artifact_package(item["item"])
        if item["kind"] == "product"
        else _row_to_content_artifact_package(item["item"])
        for item in source_rows
    ]
    packages.sort(key=lambda item: (str(item.get("generated_date") or item.get("market_date") or ""), str(item.get("updated_at") or "")), reverse=True)
    offset = (page - 1) * page_size
    return packages[offset : offset + page_size], total


def _artifact_period_bounds(*, year: str = "", month: str = "", date: str = "", start_date: str = "", end_date: str = "") -> tuple[str, str]:
    if date:
        return str(date), str(date)
    if month and len(str(month)) == 7:
        year_value, month_value = str(month).split("-", 1)
        try:
            month_number = int(month_value)
            if month_number < 1 or month_number > 12:
                return str(start_date or ""), str(end_date or "")
            last_day = (datetime(int(year_value), month_number + 1, 1) - timedelta(days=1)).day if month_number < 12 else 31
        except ValueError:
            return str(start_date or ""), str(end_date or "")
        return f"{year_value}-{month_value}-01", f"{year_value}-{month_value}-{last_day:02d}"
    if year and len(str(year)) == 4:
        return f"{year}-01-01", f"{year}-12-31"
    return str(start_date or ""), str(end_date or "")


def _product_artifact_package_summary(item: dict) -> dict:
    product_id = str(item.get("product_id") or "")
    service_type = str(item.get("business_type") or "")
    module_key = _component_filter_key(service_type)
    output_files = _load_list(item.get("output_files"))
    generated_at = str(item.get("created_at") or item.get("effective_at") or item.get("updated_at") or "")
    generated_date = _date_part(generated_at)
    business_date = str(item.get("business_date") or "")
    folder_date = generated_date or business_date
    display_name = str(item.get("target_label") or item.get("target_key") or "产物")
    service_label = _service_or_component_label(service_type)
    display_status, display_status_label = product_display_status(item)
    return {
        "level": "package",
        "key": product_id,
        "package_id": product_id,
        "source_type": "product",
        "label": display_name,
        "service_type": service_type,
        "module_key": module_key,
        "service_label": service_label,
        "market_date": folder_date,
        "generated_at": generated_at,
        "generated_date": generated_date,
        "business_date": business_date,
        "normalized_target": str(item.get("target_key") or ""),
        "display_name": display_name,
        "display_path": [service_label, folder_date, display_name],
        "version_fingerprint": str(item.get("version_fingerprint") or ""),
        "product_id": product_id,
        "source_content_id": str(item.get("source_content_id") or ""),
        "source_request_id": str(item.get("source_request_id") or ""),
        "source_cache_key": str(item.get("source_cache_key") or ""),
        "file_count": len(output_files),
        "hit_count": int(item.get("hit_count") or 0),
        "updated_at": str(item.get("updated_at") or ""),
        "status": str(item.get("status") or ""),
        "display_status": display_status,
        "display_status_label": display_status_label,
    }


def _content_artifact_package_summary(item: dict) -> dict:
    content_id = str(item.get("content_id") or "")
    output_image = str(item.get("output_image") or "")
    label = _content_target_label(item.get("service_type") or "")
    generated_at = str(item.get("generated_at") or item.get("updated_at") or item.get("created_at") or "")
    generated_date = _date_part(generated_at)
    display_status, display_status_label = _display_status_for_content(item)
    return {
        "level": "package",
        "key": content_id,
        "package_id": content_id,
        "source_type": "content",
        "label": label,
        "service_type": str(item.get("service_type") or ""),
        "market_date": generated_date,
        "generated_at": generated_at,
        "generated_date": generated_date,
        "effective_date": str(item.get("effective_date") or ""),
        "normalized_target": label,
        "version_fingerprint": f"v{int(item.get('content_version') or 1)}",
        "artifact_owner_id": content_id,
        "content_id": content_id,
        "source_content_id": content_id,
        "file_count": 1 if output_image else 0,
        "hit_count": 0,
        "updated_at": str(item.get("updated_at") or ""),
        "status": str(item.get("status") or ""),
        "display_status": display_status,
        "display_status_label": display_status_label,
    }


def _internal_call_artifact_package_summary(item: dict) -> dict:
    request_id = str(item.get("request_id") or "")
    raw_service_type = str(item.get("service_type") or ServiceType.TECHNICAL_ANALYSIS)
    module_key = str(item.get("module_key") or "")
    service_key = _component_service_key(module_key) if raw_service_type == str(ServiceType.UNMATCHED) and module_key else raw_service_type
    generated_at = str(item.get("created_at") or item.get("updated_at") or "")
    generated_date = _date_part(generated_at)
    output_files = _load_list(item.get("output_files"))
    return {
        "level": "package",
        "key": request_id,
        "package_id": request_id,
        "source_type": "internal_call",
        "label": str(item.get("raw_input") or "技术分析内容"),
        "service_type": service_key,
        "module_key": module_key,
        "market_date": generated_date,
        "generated_at": generated_at,
        "generated_date": generated_date,
        "normalized_target": str(item.get("normalized_target") or item.get("raw_input") or "技术分析内容"),
        "version_fingerprint": "",
        "artifact_owner_id": request_id,
        "file_count": len(output_files),
        "hit_count": 0,
        "updated_at": str(item.get("updated_at") or ""),
    }


def list_artifact_folder_nodes(
    *,
    level: str,
    page: int = 1,
    page_size: int = 100,
    service_type: ServiceType | str | None = None,
    year: str = "",
    month: str = "",
    date: str = "",
    start_date: str = "",
    end_date: str = "",
    keyword: str = "",
    include_invalidated: bool = False,
    status_category: str = "",
) -> tuple[list[dict], int]:
    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 100))
    normalized_level = str(level or "").strip().lower()
    bounded_start, bounded_end = _artifact_period_bounds(year=year, month=month, date=date, start_date=start_date, end_date=end_date)
    if normalized_level == "package":
        source_rows, total = _artifact_package_sources(
            service_type=service_type,
            start_date=bounded_start,
            end_date=bounded_end,
            keyword=keyword,
            include_invalidated=include_invalidated,
            status_category=status_category,
        )
        nodes = [
            _product_artifact_package_summary(item["item"])
            if item["kind"] == "product"
            else _content_artifact_package_summary(item["item"])
            for item in source_rows
        ]
        nodes.sort(
            key=lambda item: (
                str(item.get("generated_date") or item.get("market_date") or ""),
                str(item.get("normalized_target") or ""),
                str(item.get("updated_at") or ""),
            ),
            reverse=True,
        )
        offset = (page - 1) * page_size
        return nodes[offset : offset + page_size], total

    category = _status_category(status_category)
    if category in {"active", "invalid"}:
        source_rows, _total = _artifact_package_sources(
            service_type=service_type,
            start_date=bounded_start,
            end_date=bounded_end,
            keyword=keyword,
            include_invalidated=include_invalidated,
            status_category=status_category,
        )
        grouped_by_key: dict[str, dict] = {}
        for source in source_rows:
            item = source["item"]
            summary = (
                _product_artifact_package_summary(item)
                if source["kind"] == "product"
                else _content_artifact_package_summary(item)
            )
            if normalized_level == "service":
                key = str(summary.get("service_type") or "")
            else:
                slices = {"year": 4, "month": 7, "date": 10, "day": 10}
                length = slices.get(normalized_level)
                if not length:
                    return [], 0
                key = _date_part(str(summary.get("market_date") or summary.get("generated_date") or ""), length)
            if not key:
                continue
            current = grouped_by_key.setdefault(key, {"key": key, "count": 0, "updated_at": ""})
            current["count"] += 1
            current["updated_at"] = max(str(current.get("updated_at") or ""), str(summary.get("updated_at") or ""))
        rows = sorted(grouped_by_key.values(), key=lambda item: str(item.get("key") or ""), reverse=True)
        total = len(rows)
        offset = (page - 1) * page_size
        node_level = "date" if normalized_level == "day" else normalized_level
        return [
            {
                "level": node_level,
                "key": str(row.get("key") or ""),
                "label": _service_or_component_label(str(row.get("key") or "")) if node_level == "service" else str(row.get("key") or ""),
                "count": int(row.get("count") or 0),
                "updated_at": str(row.get("updated_at") or ""),
            }
            for row in rows[offset : offset + page_size]
        ], total

    if normalized_level == "service":
        product_key_expr = investment_products.c.business_type
    else:
        slices = {"year": 4, "month": 7, "date": 10, "day": 10}
        length = slices.get(normalized_level)
        if not length:
            return [], 0
        product_key_expr = func.substr(_product_artifact_date_expr(), 1, length)
    product_conditions = _product_artifact_conditions(
        service_type,
        bounded_start,
        bounded_end,
        keyword,
        include_invalidated=include_invalidated,
        status_category=status_category,
    )
    if normalized_level != "service":
        product_conditions.append(_product_artifact_date_expr() != "")
    content_conditions = _content_artifact_conditions(
        service_type,
        bounded_start,
        bounded_end,
        keyword,
        status_category=status_category,
    )
    product_grouped = (
        select(
            product_key_expr.label("key"),
            func.count().label("count"),
            func.max(investment_products.c.updated_at).label("updated_at"),
        )
        .where(*product_conditions)
        .group_by(product_key_expr)
    )
    with connect() as conn:
        grouped = []
        for row in conn.execute(product_grouped).fetchall():
            item = row_to_dict(row)
            key = str(item.get("key") or "")
            if not key:
                continue
            grouped.append(
                {
                    "key": key,
                    "count": int(item.get("count") or 0),
                    "updated_at": str(item.get("updated_at") or ""),
                }
            )
        if content_conditions is not None:
            if normalized_level == "service":
                content_key_expr = investment_daily_contents.c.service_type
            else:
                content_key_expr = func.substr(_content_generated_at_expr(), 1, length)
                content_conditions.append(_content_generated_at_expr() != "")
            existing_content_ids = select(investment_products.c.source_content_id).where(
                investment_products.c.source_content_id != ""
            )
            content_grouped = (
                select(
                    content_key_expr.label("key"),
                    func.count().label("count"),
                    func.max(investment_daily_contents.c.updated_at).label("updated_at"),
                )
                .where(*content_conditions)
                .where(~investment_daily_contents.c.content_id.in_(existing_content_ids))
                .group_by(content_key_expr)
            )
            for row in conn.execute(content_grouped).fetchall():
                item = row_to_dict(row)
                key = str(item.get("key") or "")
                if not key:
                    continue
                grouped.append(
                    {
                        "key": key,
                        "count": int(item.get("count") or 0),
                        "updated_at": str(item.get("updated_at") or ""),
                    }
                )

    rows = sorted(grouped, key=lambda item: str(item.get("key") or ""), reverse=True)
    total = len(rows)
    offset = (page - 1) * page_size
    rows = rows[offset : offset + page_size]
    node_level = "date" if normalized_level == "day" else normalized_level
    return [
        {
            "level": node_level,
            "key": str(row.get("key") or ""),
            "label": _service_or_component_label(str(row.get("key") or "")) if node_level == "service" else str(row.get("key") or ""),
            "count": int(row.get("count") or 0),
            "updated_at": str(row.get("updated_at") or ""),
        }
        for row in rows
    ], total


def build_artifact_package_tree(packages: list[dict]) -> list[dict]:
    tree_by_date: dict[str, dict] = {}
    for package in packages:
        date_key = package.get("market_date") or "unknown-date"
        target_key = package.get("display_name") or package.get("package_id") or "artifact"
        date_node = tree_by_date.setdefault(date_key, {"dir": date_key, "children": []})
        target_node = {"dir": target_key, "package_id": package.get("package_id"), "children": []}
        groups: dict[str, list[dict]] = {"input": [], "output": [], "intermediate": []}
        for file in package.get("files") or []:
            groups.setdefault(file.get("group") or "intermediate", []).append(file)
        for group_name in ("input", "output", "intermediate"):
            files = groups.get(group_name) or []
            if files:
                target_node["children"].append({"dir": group_name, "files": files})
        date_node["children"].append(target_node)
    return list(tree_by_date.values())


def get_file_record(file_id: int | str) -> dict | None:
    try:
        normalized_id = int(file_id)
    except (TypeError, ValueError):
        return None
    with connect() as conn:
        row = conn.execute(
            select(investment_output_files).where(investment_output_files.c.id == normalized_id)
        ).fetchone()
    if row is None:
        return None
    item = row_to_dict(row)
    item["file_id"] = str(item.get("id") or "")
    item["file_url"] = f"/api/file?id={item['file_id']}" if item["file_id"] else ""
    return item


def get_file_record_by_path(file_path: str) -> dict | None:
    if not file_path:
        return None
    with connect() as conn:
        row = conn.execute(
            select(investment_output_files)
            .where(investment_output_files.c.file_path == file_path)
            .order_by(investment_output_files.c.id.desc())
        ).fetchone()
    if row is None:
        return None
    item = row_to_dict(row)
    item["file_id"] = str(item.get("id") or "")
    item["file_url"] = f"/api/file?id={item['file_id']}" if item["file_id"] else ""
    return item


def record_output_file(
    owner_id: str,
    file_path: str,
    file_type: str | None,
    service_type: ServiceType,
    *,
    artifact_role: str = "",
    version_tag: str = "",
    owner_type: str = "request",
) -> None:
    from business.artifacts.artifact_service import record_artifact

    record_artifact(
        owner_id,
        file_path,
        artifact_role or file_type,
        service_type,
        file_type=file_type,
        version_tag=version_tag,
        owner_type=owner_type,
    )


def _row_to_content(row) -> ContentRecord:
    item = row_to_dict(row)
    status = Status(item["status"])
    created_at = item["created_at"]
    return ContentRecord(
        content_id=item["content_id"],
        service_type=ServiceType(item["service_type"]),
        status=status,
        module_key=item.get("module_key") or "",
        source_files=_load_list(item["source_files"]),
        source_text=item["source_text"] or "",
        input_prompt=item.get("input_prompt") or "",
        generated_text=item["generated_text"] or "",
        output_image=item["output_image"] or "",
        error_message=item["error_message"] or "",
        operator=item["operator"] or "",
        created_by_admin_id=item.get("created_by_admin_id"),
        created_by_username=item.get("created_by_username") or "",
        created_by_role=item.get("created_by_role") or "",
        updated_by_admin_id=item.get("updated_by_admin_id"),
        updated_by_username=item.get("updated_by_username") or "",
        updated_by_role=item.get("updated_by_role") or "",
        published_by_admin_id=item.get("published_by_admin_id"),
        published_by_username=item.get("published_by_username") or "",
        published_by_role=item.get("published_by_role") or "",
        created_at=created_at,
        effective_at=item["effective_at"],
        effective_date=item.get("effective_date") or "",
        expires_at=item.get("expires_at") or "",
        content_version=int(item.get("content_version") or 1),
        direct_output_mode=bool(item.get("direct_output_mode")),
        auto_effective_after_generate=bool(item.get("auto_effective_after_generate")),
        archived_at=item.get("archived_at"),
        status_warning=_status_warning(status, created_at),
    )


def list_content_records(
    limit: int = 50,
    service_type: ServiceType | None = None,
    module_key: str = "",
    effective_date: str | None = None,
    status: Status | str | None = None,
    keyword: str = "",
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[ContentRecord]:
    records, _total = list_content_records_page(
        page=1,
        page_size=limit,
        service_type=service_type,
        module_key=module_key,
        effective_date=effective_date,
        status=status,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
    )
    return records


def list_content_records_page(
    *,
    page: int = 1,
    page_size: int = 50,
    service_type: ServiceType | None = None,
    module_key: str = "",
    effective_date: str | None = None,
    status: Status | str | None = None,
    keyword: str = "",
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[ContentRecord], int]:
    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 50))
    offset = (page - 1) * page_size
    stmt = select(investment_daily_contents)
    count_stmt = select(func.count()).select_from(investment_daily_contents)
    conditions = []
    if service_type is not None:
        conditions.append(investment_daily_contents.c.service_type == str(service_type))
    normalized_module_key = str(module_key or "").strip()
    if normalized_module_key:
        conditions.append(investment_daily_contents.c.module_key == normalized_module_key)
    if effective_date:
        conditions.append(investment_daily_contents.c.effective_date == effective_date)
    if start_date:
        conditions.append(investment_daily_contents.c.created_at >= str(start_date))
    if end_date:
        conditions.append(investment_daily_contents.c.created_at <= str(end_date))
    if status is not None:
        try:
            normalized_status = Status(status)
        except ValueError:
            return [], 0
        conditions.append(investment_daily_contents.c.status == str(normalized_status))
    keyword_text = str(keyword or "").strip()
    if keyword_text:
        pattern = f"%{keyword_text}%"
        conditions.append(
            or_(
                investment_daily_contents.c.content_id.ilike(pattern),
                investment_daily_contents.c.service_type.ilike(pattern),
                investment_daily_contents.c.module_key.ilike(pattern),
                investment_daily_contents.c.source_text.ilike(pattern),
                investment_daily_contents.c.input_prompt.ilike(pattern),
                investment_daily_contents.c.generated_text.ilike(pattern),
                investment_daily_contents.c.output_image.ilike(pattern),
                investment_daily_contents.c.status.ilike(pattern),
                investment_daily_contents.c.error_message.ilike(pattern),
                investment_daily_contents.c.operator.ilike(pattern),
                investment_daily_contents.c.created_by_username.ilike(pattern),
                investment_daily_contents.c.updated_by_username.ilike(pattern),
                investment_daily_contents.c.effective_date.ilike(pattern),
            )
        )
    if conditions:
        stmt = stmt.where(*conditions)
        count_stmt = count_stmt.where(*conditions)
    stmt = stmt.order_by(investment_daily_contents.c.created_at.desc()).limit(page_size).offset(offset)
    with connect() as conn:
        total = int(conn.execute(count_stmt).scalar_one() or 0)
        rows = conn.execute(stmt).fetchall()
    return [_row_to_content(row) for row in rows], total


def get_content_record(content_id: str) -> ContentRecord:
    with connect() as conn:
        row = conn.execute(
            select(investment_daily_contents).where(investment_daily_contents.c.content_id == content_id)
        ).fetchone()
    if row is None:
        raise KeyError(content_id)
    return _row_to_content(row)
