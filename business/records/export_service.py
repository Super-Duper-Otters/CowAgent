# encoding:utf-8
from calendar import monthrange
from datetime import timedelta
from io import BytesIO
from typing import Iterable

from openpyxl import Workbook
from sqlalchemy import select

from business.config.constants import EntryType, ServiceType, Status
from business.schema.db import connect, row_to_dict
from business.records.records import _visible_delivery_message, build_request_record_conditions
from business.schema.tables import investment_request_records, investment_users
from business.accounts.user_service import _decode_services


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
ACTIVATION_CODE_HEADERS = [
    "batch_id",
    "code",
    "activation_mode",
    "customer_id",
    "allowed_services",
    "subscription_days",
    "subscription_start_at",
    "subscription_end_at",
    "code_expires_at",
    "status",
    "used_by_openid",
    "used_at",
    "created_at",
    "remark",
]
USER_IMPORT_HEADERS = ["手机号", "服务权限", "授权结束日期", "OpenID", "姓名", "机构", "状态", "授权开始日期", "备注"]
USER_IMPORT_TEMPLATE_ROWS = [
    ["13800000000", "全部", "2026-12-31", "", "张三", "示例机构", "启用", "", "示例客户"],
]
USER_IMPORT_RESULT_HEADERS = [
    "处理结果",
    "客户ID",
    "OpenID",
    "姓名",
    "机构",
    "手机号",
    "服务权限",
    "授权开始",
    "授权结束",
    "激活码",
    "激活码批次",
    "错误信息",
]


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
    entry_type: str | EntryType | None = EntryType.EXTERNAL_REQUEST,
    status: str | Status | None = None,
    keyword: str = "",
    customer: str = "",
) -> bytes:
    table = investment_request_records
    users = investment_users
    stmt = select(table).select_from(table.outerjoin(users, table.c.openid == users.c.openid))
    conditions, impossible = build_request_record_conditions(
        table,
        users,
        service_type=service_type,
        entry_type=entry_type,
        status=status,
        keyword=keyword,
        customer=customer,
        start_date=start_date,
        end_date=end_date,
    )
    if impossible:
        return _workbook_bytes(REQUEST_HEADERS, [], "RequestRecords")
    if conditions:
        stmt = stmt.where(*conditions)
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


def export_activation_codes_xlsx(status: str | None = None, batch_id: str | None = None) -> bytes:
    from business.accounts.activation_service import list_activation_codes

    rows = list_activation_codes(status=status, batch_id=batch_id)

    export_rows = [
        [
            row.batch_id,
            row.code,
            row.activation_mode,
            row.customer_id or "",
            ",".join(str(service) for service in (row.allowed_services or [])),
            row.subscription_days,
            row.subscription_start_at or "",
            row.subscription_end_at or "",
            row.code_expires_at or "",
            row.status or "",
            row.used_by_openid or "",
            row.used_at or "",
            row.created_at or "",
            row.remark or "",
        ]
        for row in reversed(rows)
    ]
    return _workbook_bytes(ACTIVATION_CODE_HEADERS, export_rows, "ActivationCodes")


def export_users_import_template_xlsx() -> bytes:
    return _workbook_bytes(USER_IMPORT_HEADERS, USER_IMPORT_TEMPLATE_ROWS, "ImportTemplate")


def _date_display(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return (value + timedelta(hours=8)).date().isoformat()
    return str(value)


def export_users_import_result_xlsx(rows) -> bytes:
    export_rows = [
        [
            getattr(row, "action", "") or "",
            getattr(row, "customer_id", "") or "",
            getattr(row, "openid", "") or "",
            getattr(row, "name", "") or "",
            getattr(row, "institution", "") or "",
            getattr(row, "mobile", "") or "",
            getattr(row, "allowed_services", "") or "",
            _date_display(getattr(row, "auth_start_at", None)),
            _date_display(getattr(row, "auth_end_at", None)),
            getattr(row, "activation_code", "") or "",
            getattr(row, "batch_id", "") or "",
            getattr(row, "error", "") or "",
        ]
        for row in rows
    ]
    return _workbook_bytes(USER_IMPORT_RESULT_HEADERS, export_rows, "ImportResult")


def _load_output_files(value: str | None) -> list[str]:
    if not value:
        return []
    import json

    try:
        parsed = json.loads(value)
    except Exception:
        return []
    return [str(item) for item in parsed if item]
