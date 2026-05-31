# encoding:utf-8
from calendar import monthrange
from io import BytesIO
from typing import Iterable

from openpyxl import Workbook
from sqlalchemy import or_, select

from .constants import ServiceType, Status
from .db import connect, row_to_dict
from .records import _visible_delivery_message, _service_condition
from .schema import investment_request_records, investment_users
from .user_service import _decode_services


REQUEST_HEADERS = [
    "请求时间",
    "OpenID",
    "客户姓名",
    "机构",
    "原始输入",
    "服务类型",
    "股票代码",
    "股票名称",
    "状态",
    "错误码",
    "错误原因",
    "缓存命中",
    "输出文件",
    "耗时毫秒",
    "程序版本",
    "模板版本",
]

USER_HEADERS = ["OpenID", "姓名", "机构", "手机号", "状态", "服务权限", "授权开始", "授权结束", "备注"]


def month_range(year: int, month: int) -> tuple[str, str]:
    last_day = monthrange(int(year), int(month))[1]
    return (f"{int(year):04d}-{int(month):02d}-01T00:00:00", f"{int(year):04d}-{int(month):02d}-{last_day:02d}T23:59:59")


def quarter_range(year: int, quarter: int) -> tuple[str, str]:
    quarter_value = int(quarter)
    if quarter_value < 1 or quarter_value > 4:
        raise ValueError("quarter must be between 1 and 4")
    start_month = (quarter_value - 1) * 3 + 1
    end_month = start_month + 2
    return month_range(int(year), start_month)[0], month_range(int(year), end_month)[1]


def _workbook_bytes(headers: list[str], rows: Iterable[list[object]], title: str) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def export_request_records_xlsx(
    start_date: str,
    end_date: str,
    service_type: str | ServiceType | None = None,
    status: str | Status | None = None,
    keyword: str = "",
    customer: str = "",
) -> bytes:
    table = investment_request_records
    users = investment_users
    stmt = select(table).select_from(table.outerjoin(users, table.c.openid == users.c.openid))
    if start_date:
        stmt = stmt.where(table.c.created_at >= str(start_date))
    if end_date:
        stmt = stmt.where(table.c.created_at <= str(end_date))
    service_condition, impossible = _service_condition(table, service_type)
    if impossible:
        return _workbook_bytes(REQUEST_HEADERS, [], "RequestRecords")
    if service_condition is not None:
        stmt = stmt.where(service_condition)
    if status:
        try:
            normalized_status = Status(status)
        except ValueError:
            return _workbook_bytes(REQUEST_HEADERS, [], "RequestRecords")
        stmt = stmt.where(table.c.status == str(normalized_status))
    keyword_text = str(keyword or "").strip()
    if keyword_text:
        pattern = f"%{keyword_text}%"
        stmt = stmt.where(
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
        stmt = stmt.where(
            or_(
                table.c.openid.ilike(customer_pattern),
                users.c.mobile.ilike(customer_pattern),
                users.c.name.ilike(customer_pattern),
                users.c.institution.ilike(customer_pattern),
            )
        )
    stmt = stmt.order_by(table.c.created_at.asc())

    with connect() as conn:
        rows = [row_to_dict(row) for row in conn.execute(stmt).fetchall()]

    export_rows = [
        [
            item.get("created_at") or "",
            item.get("openid") or "",
            item.get("customer_name") or "",
            item.get("institution") or "",
            item.get("raw_input") or "",
            item.get("service_type") or "",
            item.get("stock_code") or "",
            item.get("stock_name") or "",
            item.get("status") or "",
            item.get("error_code") or None,
            _visible_delivery_message(item.get("error_message") or "") or None,
            "是" if item.get("cache_hit") else "否",
            "\n".join(_load_output_files(item.get("output_files"))),
            item.get("elapsed_ms"),
            item.get("program_version") or "",
            item.get("template_version") or "",
        ]
        for item in rows
    ]
    return _workbook_bytes(REQUEST_HEADERS, export_rows, "RequestRecords")


def export_users_xlsx(enabled: bool | None = None) -> bytes:
    table = investment_users
    stmt = select(table)
    if enabled is not None:
        stmt = stmt.where(table.c.enabled == (1 if enabled else 0))
    stmt = stmt.order_by(table.c.id.asc())

    with connect() as conn:
        rows = [row_to_dict(row) for row in conn.execute(stmt).fetchall()]

    export_rows = [
        [
            item.get("openid") or "",
            item.get("name") or "",
            item.get("institution") or "",
            item.get("mobile") or "",
            "启用" if item.get("enabled") else "停用",
            ",".join(str(service) for service in _decode_services(item.get("allowed_services") or "")),
            item.get("auth_start_at") or "",
            item.get("auth_end_at") or "",
            item.get("remark") or "",
        ]
        for item in rows
    ]
    return _workbook_bytes(USER_HEADERS, export_rows, "Users")


def _load_output_files(value: str | None) -> list[str]:
    if not value:
        return []
    import json

    try:
        parsed = json.loads(value)
    except Exception:
        return []
    return [str(item) for item in parsed if item]
