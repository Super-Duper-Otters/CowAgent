# encoding:utf-8
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, insert, or_, select, update

from .config_service import sanitize_sensitive_text
from .constants import ErrorCode, ServiceType, Status, normalize_service, user_message
from .db import connect, row_to_dict
from .schema import investment_daily_contents, investment_output_files, investment_request_records, investment_users


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
    source_files: list[str] | None = None
    source_text: str = ""
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
    content_version: int = 1
    direct_output_mode: bool = False
    archived_at: str | None = None
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
) -> None:
    service_type: ServiceType | None = None
    values: dict[str, object] = {
        "status": str(Status.SUCCESS),
        "error_code": None,
        "user_prompt": "",
        "error_message": sanitize_sensitive_text(warning),
        "output_files": _json_list(output_files),
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
            select(investment_request_records.c.service_type).where(investment_request_records.c.request_id == request_id)
        ).fetchone()
        item = row_to_dict(row)
        if item.get("service_type"):
            service_type = ServiceType(item["service_type"])
    if service_type is not None:
        for file_path in output_files:
            role = (artifact_roles or {}).get(file_path, "image")
            version_tag = (artifact_versions or {}).get(file_path, "")
            record_output_file(request_id, file_path, "image", service_type, artifact_role=role, version_tag=version_tag)


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
        conn.execute(delete(investment_output_files).where(investment_output_files.c.owner_id == request_id))


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
        status=status,
        keyword=keyword,
        customer=customer,
        start_date=start_date,
        end_date=end_date,
    )
    return records


def list_request_records_page(
    *,
    page: int = 1,
    page_size: int = 50,
    service_type: ServiceType | str | None = None,
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
    conditions = []
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
    service_condition, impossible = _service_condition(table, service_type)
    if impossible:
        return [], 0
    if service_condition is not None:
        conditions.append(service_condition)
    if status is not None:
        try:
            normalized_status = Status(status)
        except ValueError:
            return [], 0
        conditions.append(table.c.status == str(normalized_status))
    if start_date:
        conditions.append(table.c.created_at >= str(start_date))
    if end_date:
        conditions.append(table.c.created_at <= str(end_date))
    keyword_text = str(keyword or "").strip()
    if keyword_text:
        pattern = f"%{keyword_text}%"
        conditions.append(
            or_(
                table.c.request_id.ilike(pattern),
                table.c.openid.ilike(pattern),
                table.c.raw_input.ilike(pattern),
                table.c.service_type.ilike(pattern),
                table.c.status.ilike(pattern),
                table.c.error_code.ilike(pattern),
                table.c.user_prompt.ilike(pattern),
                table.c.error_message.ilike(pattern),
                table.c.normalized_target.ilike(pattern),
                table.c.stock_code.ilike(pattern),
                table.c.stock_name.ilike(pattern),
                table.c.customer_name.ilike(pattern),
                table.c.institution.ilike(pattern),
                users.c.name.ilike(pattern),
                users.c.institution.ilike(pattern),
                users.c.mobile.ilike(pattern),
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
    return [row_to_dict(row) for row in rows]


def record_output_file(
    owner_id: str,
    file_path: str,
    file_type: str,
    service_type: ServiceType,
    *,
    artifact_role: str = "",
    version_tag: str = "",
    owner_type: str = "request",
) -> None:
    from .artifact_service import record_artifact

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
        source_files=_load_list(item["source_files"]),
        source_text=item["source_text"] or "",
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
        content_version=int(item.get("content_version") or 1),
        direct_output_mode=bool(item.get("direct_output_mode")),
        archived_at=item.get("archived_at"),
        status_warning=_status_warning(status, created_at),
    )


def list_content_records(
    limit: int = 50,
    service_type: ServiceType | None = None,
    effective_date: str | None = None,
    status: Status | str | None = None,
) -> list[ContentRecord]:
    records, _total = list_content_records_page(
        page=1,
        page_size=limit,
        service_type=service_type,
        effective_date=effective_date,
        status=status,
    )
    return records


def list_content_records_page(
    *,
    page: int = 1,
    page_size: int = 50,
    service_type: ServiceType | None = None,
    effective_date: str | None = None,
    status: Status | str | None = None,
) -> tuple[list[ContentRecord], int]:
    page = max(1, int(page or 1))
    page_size = max(1, int(page_size or 50))
    offset = (page - 1) * page_size
    stmt = select(investment_daily_contents)
    count_stmt = select(func.count()).select_from(investment_daily_contents)
    conditions = []
    if service_type is not None:
        conditions.append(investment_daily_contents.c.service_type == str(service_type))
    if effective_date:
        conditions.append(investment_daily_contents.c.effective_date == effective_date)
    if status is not None:
        try:
            normalized_status = Status(status)
        except ValueError:
            return [], 0
        conditions.append(investment_daily_contents.c.status == str(normalized_status))
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
