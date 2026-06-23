# encoding:utf-8
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree
from zipfile import ZipFile

from sqlalchemy import func, or_, insert, select, update

from business.constants import CUSTOMER_SERVICE_TYPES, ErrorCode, SERVICE_LABELS, ServiceType, normalize_service, user_message
from business.db import connect, row_to_dict
from business.schema import investment_users


@dataclass
class User:
    id: int | None
    openid: str
    name: str = ""
    institution: str = ""
    mobile: str = ""
    enabled: bool = True
    allowed_services: list[ServiceType] | None = None
    auth_start_at: datetime | None = None
    auth_end_at: datetime | None = None
    remark: str = ""


@dataclass
class PermissionResult:
    allowed: bool
    error_code: ErrorCode | None = None
    user_prompt: str = ""
    detail: str = ""


@dataclass
class ImportUserRow:
    openid: str
    name: str = ""
    institution: str = ""
    mobile: str = ""
    enabled: bool = True
    allowed_services: str = "全部"
    auth_start_at: datetime | None = None
    auth_end_at: datetime | None = None
    remark: str = ""
    openid_generated: bool = False


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _admin_actor_values(actor: Any | None, *, prefix: str) -> dict[str, Any]:
    if actor is None:
        return {}
    return {
        f"{prefix}_by_admin_id": getattr(actor, "id", None),
        f"{prefix}_by_username": str(getattr(actor, "username", "") or ""),
    }


def _to_iso(value: datetime | str | None) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value)


def _from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return _to_naive_utc(parsed)


def _to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _to_naive_utc(value)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return _to_naive_utc(datetime.fromisoformat(text))
    except ValueError:
        pass
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        serial = float(text)
    except ValueError:
        return None
    return datetime(1899, 12, 30) + timedelta(days=serial)


def _beijing_start_to_utc_naive(day_text: str) -> datetime:
    text = str(day_text).strip().replace("/", "-")
    day = datetime.strptime(text[:10], "%Y-%m-%d").date()
    return datetime.combine(day, datetime.min.time()) - timedelta(hours=8)


def _beijing_today_start_utc_naive() -> datetime:
    beijing_now = datetime.now(UTC) + timedelta(hours=8)
    return datetime.combine(beijing_now.date(), datetime.min.time()) - timedelta(hours=8)


_IMPORT_DATE_RE = re.compile(r"^\s*(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})(?:日)?(?:[ T].*)?\s*$")


def _parse_excel_serial_date(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        serial = float(value)
    else:
        text = str(value).strip()
        if not re.fullmatch(r"\d+(?:\.\d+)?", text):
            return None
        serial = float(text)
    if serial < 20000 or serial > 60000:
        return None
    return datetime(1899, 12, 30) + timedelta(days=serial)


def _parse_beijing_date_start(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _beijing_start_to_utc_naive(value.date().isoformat())
    text = str(value).strip()
    if not text:
        return None
    serial_date = _parse_excel_serial_date(value)
    if serial_date is not None:
        return _beijing_start_to_utc_naive(serial_date.date().isoformat())
    match = _IMPORT_DATE_RE.match(text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        return _beijing_start_to_utc_naive(datetime(year, month, day).date().isoformat())
    return None


def _parse_required_import_date(value: Any, row_number: int, field: str) -> datetime:
    try:
        parsed = _parse_beijing_date_start(value)
    except ValueError as exc:
        raise ValueError(f"Excel row {row_number} invalid date field: {field}; expected YYYY-MM-DD") from exc
    if parsed is None:
        raise ValueError(f"Excel row {row_number} invalid date field: {field}; expected YYYY-MM-DD")
    return parsed


def _parse_optional_import_date(value: Any, row_number: int, field: str) -> datetime | None:
    if str(value or "").strip() == "":
        return None
    return _parse_required_import_date(value, row_number, field)


def _parse_enabled(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return True
    if text in {"1", "true", "yes", "y", "on", "enabled", "enable", "是", "启用"}:
        return True
    if text in {"0", "false", "no", "n", "off", "disabled", "disable", "否", "停用"}:
        return False
    return bool(value)


def _encode_services(values: Iterable[str | ServiceType] | str) -> str:
    if isinstance(values, str):
        raw = [item.strip() for item in values.replace("，", ",").split(",") if item.strip()]
    else:
        raw = list(values)
    services = []
    for value in raw:
        service = normalize_service(value)
        if service not in services:
            services.append(service)
    if not services:
        services = [ServiceType.ALL]
    customer_services = set(CUSTOMER_SERVICE_TYPES)
    if ServiceType.ALL in services or customer_services.issubset(set(services)):
        services = [ServiceType.ALL]
    return json.dumps([str(service) for service in services], ensure_ascii=False)


def _decode_services(value: str) -> list[ServiceType]:
    try:
        return [normalize_service(item) for item in json.loads(value)]
    except Exception:
        return [normalize_service(item) for item in value.split(",")]


def _read_excel_source(source: bytes | str | Path) -> bytes:
    if isinstance(source, bytes):
        return source
    return Path(source).read_bytes()


def _xml_text(element: ElementTree.Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext())


def _column_index(cell_ref: str) -> int:
    letters = ""
    for char in cell_ref:
        if char.isalpha():
            letters += char.upper()
        else:
            break
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - 64)
    return max(index - 1, 0)


def _xlsx_rows(content: bytes) -> list[list[str]]:
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(BytesIO(content)) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = [_xml_text(item) for item in shared_root.findall("x:si", ns)]

        sheet_name = "xl/worksheets/sheet1.xml"
        if sheet_name not in archive.namelist():
            sheet_name = next(name for name in archive.namelist() if name.startswith("xl/worksheets/") and name.endswith(".xml"))
        root = ElementTree.fromstring(archive.read(sheet_name))

    rows: list[list[str]] = []
    for row in root.findall(".//x:sheetData/x:row", ns):
        cells: list[str] = []
        for cell in row.findall("x:c", ns):
            index = _column_index(cell.attrib.get("r", ""))
            while len(cells) <= index:
                cells.append("")
            cell_type = cell.attrib.get("t", "")
            if cell_type == "s":
                raw_value = _xml_text(cell.find("x:v", ns))
                value = shared_strings[int(raw_value)] if raw_value else ""
            elif cell_type == "inlineStr":
                value = _xml_text(cell.find("x:is", ns))
            else:
                value = _xml_text(cell.find("x:v", ns))
                if cell_type == "b":
                    value = "true" if value == "1" else "false"
            cells[index] = value.strip()
        if any(cells):
            rows.append(cells)
    return rows


_IMPORT_HEADER_ALIASES = {
    "openid": "openid",
    "open id": "openid",
    "姓名": "name",
    "客户姓名": "name",
    "name": "name",
    "机构": "institution",
    "institution": "institution",
    "手机号": "mobile",
    "手机": "mobile",
    "mobile": "mobile",
    "状态": "enabled",
    "enabled": "enabled",
    "服务权限": "allowed_services",
    "服务": "allowed_services",
    "allowed_services": "allowed_services",
    "授权开始": "auth_start_at",
    "授权开始日期": "auth_start_at",
    "auth_start_at": "auth_start_at",
    "授权结束": "auth_end_at",
    "授权结束日期": "auth_end_at",
    "auth_end_at": "auth_end_at",
    "备注": "remark",
    "remark": "remark",
}


def _normalize_header(value: str) -> str:
    normalized = value.strip().lower()
    return _IMPORT_HEADER_ALIASES.get(normalized, normalized)


def _cell(row: list[str], indexes: dict[str, int], key: str) -> str:
    index = indexes.get(key)
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def _generated_pending_openid(mobile: str, row_number: int) -> str:
    digits = "".join(char for char in str(mobile) if char.isdigit()) or "unknown"
    return f"pending-mobile-{digits}-{row_number}"



def _row_to_user(row) -> User | None:
    if row is None:
        return None
    item = row_to_dict(row)
    return User(
        id=item["id"],
        openid=item["openid"],
        name=item["name"] or "",
        institution=item["institution"] or "",
        mobile=item["mobile"] or "",
        enabled=bool(item["enabled"]),
        allowed_services=_decode_services(item["allowed_services"]),
        auth_start_at=_from_iso(item["auth_start_at"]),
        auth_end_at=_from_iso(item["auth_end_at"]),
        remark=item["remark"] or "",
    )


def create_user(
    openid: str,
    *,
    name: str = "",
    institution: str = "",
    mobile: str = "",
    enabled: bool = True,
    allowed_services: Iterable[str | ServiceType] | str = (ServiceType.ALL,),
    auth_start_at: datetime | str | None = None,
    auth_end_at: datetime | str | None = None,
    remark: str = "",
    actor: Any | None = None,
) -> int:
    now = _now()
    values = {
        "openid": openid,
        "name": name,
        "institution": institution,
        "mobile": mobile,
        "enabled": 1 if enabled else 0,
        "allowed_services": _encode_services(allowed_services),
        "auth_start_at": _to_iso(auth_start_at),
        "auth_end_at": _to_iso(auth_end_at),
        "remark": remark,
        "created_at": now,
        "updated_at": now,
    }
    values.update(_admin_actor_values(actor, prefix="created"))
    values.update(_admin_actor_values(actor, prefix="updated"))
    with connect() as conn:
        result = conn.execute(insert(investment_users).values(**values))
        if result.inserted_primary_key:
            user_id = result.inserted_primary_key[0]
            if user_id is not None:
                return int(user_id)
        row = conn.execute(
            select(investment_users.c.id).where(investment_users.c.openid == openid),
        )
        return int(row.scalar_one())


def get_user_by_openid(openid: str) -> User | None:
    with connect() as conn:
        row = conn.execute(select(investment_users).where(investment_users.c.openid == openid)).fetchone()
    return _row_to_user(row)


def update_user(openid: str, actor: Any | None = None, **fields) -> None:
    allowed = {"name", "institution", "mobile", "enabled", "allowed_services", "auth_start_at", "auth_end_at", "remark"}
    values = {}
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "allowed_services":
            value = _encode_services(value)
        elif key in ("auth_start_at", "auth_end_at"):
            value = _to_iso(value)
        elif key == "enabled":
            value = 1 if value else 0
        values[key] = value
    if not values:
        return
    values["updated_at"] = _now()
    values.update(_admin_actor_values(actor, prefix="updated"))
    with connect() as conn:
        conn.execute(update(investment_users).where(investment_users.c.openid == openid).values(**values))


def disable_user(openid: str, *, actor: Any | None = None) -> None:
    update_user(openid, actor=actor, enabled=False)


def enable_user(openid: str, *, actor: Any | None = None) -> None:
    update_user(openid, actor=actor, enabled=True)


def delete_user(openid: str, *, actor: Any | None = None, reason: str = "") -> None:
    now = _now()
    values = {
        "enabled": 0,
        "deleted_at": now,
        "delete_reason": reason,
        "updated_at": now,
    }
    values.update(_admin_actor_values(actor, prefix="deleted"))
    values.update(_admin_actor_values(actor, prefix="updated"))
    with connect() as conn:
        conn.execute(update(investment_users).where(investment_users.c.openid == openid).values(**values))


def _service_keyword_conditions(keyword: str):
    keyword_text = str(keyword or "").strip()
    if not keyword_text:
        return None
    lowered = keyword_text.lower()
    conditions = [investment_users.c.allowed_services.like(f"%{keyword_text}%")]
    for service, label in SERVICE_LABELS.items():
        service_value = str(service)
        if lowered in service_value.lower() or keyword_text in str(label):
            conditions.append(investment_users.c.allowed_services.like(f"%{service_value}%"))
    return or_(*conditions)


def _user_conditions(enabled: bool | None = None, openid: str | None = None, keyword: str | None = None, keyword_field: str | None = None) -> list:
    conditions = []
    if enabled is not None:
        conditions.append(investment_users.c.enabled == (1 if enabled else 0))
    if openid:
        conditions.append(investment_users.c.openid.like(f"%{openid}%"))
    keyword_text = str(keyword or "").strip()
    if keyword_text:
        pattern = f"%{keyword_text}%"
        field = str(keyword_field or "all").strip().lower()
        field_map = {
            "openid": investment_users.c.openid,
            "name": investment_users.c.name,
            "institution": investment_users.c.institution,
            "mobile": investment_users.c.mobile,
        }
        if field in field_map:
            conditions.append(field_map[field].like(pattern))
        elif field == "service":
            conditions.append(_service_keyword_conditions(keyword_text))
        else:
            service_condition = _service_keyword_conditions(keyword_text)
            conditions.append(
                or_(
                    investment_users.c.openid.like(pattern),
                    investment_users.c.name.like(pattern),
                    investment_users.c.institution.like(pattern),
                    investment_users.c.mobile.like(pattern),
                    service_condition,
                )
            )
    return conditions


def count_users(enabled: bool | None = None, openid: str | None = None, keyword: str | None = None, keyword_field: str | None = None) -> int:
    stmt = select(func.count()).select_from(investment_users)
    conditions = _user_conditions(enabled=enabled, openid=openid, keyword=keyword, keyword_field=keyword_field)
    if conditions:
        stmt = stmt.where(*conditions)
    with connect() as conn:
        return int(conn.execute(stmt).scalar_one() or 0)


def list_users(
    enabled: bool | None = None,
    openid: str | None = None,
    keyword: str | None = None,
    keyword_field: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> list[User]:
    stmt = select(investment_users)
    conditions = _user_conditions(enabled=enabled, openid=openid, keyword=keyword, keyword_field=keyword_field)
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.order_by(investment_users.c.id.desc())
    if page is not None and page_size is not None:
        page = max(1, int(page or 1))
        page_size = max(1, int(page_size or 1))
        stmt = stmt.limit(page_size).offset((page - 1) * page_size)
    with connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [user for row in rows if (user := _row_to_user(row))]


def verify_permission(openid: str, service_type: ServiceType) -> PermissionResult:
    user = get_user_by_openid(openid)
    base_permission = _verify_existing_user(user)
    if not base_permission.allowed:
        return base_permission
    services = user.allowed_services or []
    if ServiceType.ALL not in services and service_type not in services:
        return PermissionResult(False, ErrorCode.UNAUTHORIZED, user_message(ErrorCode.UNAUTHORIZED), "service not allowed")
    return PermissionResult(True)


def verify_user_access(openid: str) -> PermissionResult:
    return _verify_existing_user(get_user_by_openid(openid))


def _verify_existing_user(user: User | None) -> PermissionResult:
    if user is None:
        return PermissionResult(False, ErrorCode.UNAUTHORIZED, user_message(ErrorCode.UNAUTHORIZED), "user not found")
    if not user.enabled:
        return PermissionResult(False, ErrorCode.USER_DISABLED, user_message(ErrorCode.USER_DISABLED), "user disabled")
    now = datetime.now(UTC).replace(tzinfo=None)
    if user.auth_start_at and now < user.auth_start_at:
        return PermissionResult(False, ErrorCode.UNAUTHORIZED, user_message(ErrorCode.UNAUTHORIZED), "auth not started")
    if user.auth_end_at and now > user.auth_end_at:
        return PermissionResult(False, ErrorCode.AUTH_EXPIRED, user_message(ErrorCode.AUTH_EXPIRED), "auth expired")
    return PermissionResult(True)


def import_users(rows: Iterable[ImportUserRow]) -> ImportResult:
    result = ImportResult()
    for row in rows:
        existing = get_user_by_openid(row.openid)
        if existing:
            update_user(
                row.openid,
                name=row.name,
                institution=row.institution,
                mobile=row.mobile,
                enabled=row.enabled,
                allowed_services=row.allowed_services,
                auth_start_at=row.auth_start_at,
                auth_end_at=row.auth_end_at,
                remark=row.remark,
            )
            result.updated += 1
        else:
            create_user(
                row.openid,
                name=row.name,
                institution=row.institution,
                mobile=row.mobile,
                enabled=row.enabled,
                allowed_services=row.allowed_services,
                auth_start_at=row.auth_start_at,
                auth_end_at=row.auth_end_at,
                remark=row.remark,
            )
            result.created += 1
    return result


def parse_users_excel(source: bytes | str | Path) -> list[ImportUserRow]:
    rows = _xlsx_rows(_read_excel_source(source))
    if not rows:
        return []

    headers = [_normalize_header(value) for value in rows[0]]
    indexes = {header: index for index, header in enumerate(headers) if header}
    missing_headers = [key for key in ("mobile", "allowed_services", "auth_start_at", "auth_end_at") if key not in indexes]
    if missing_headers:
        raise ValueError(f"Excel missing required field: {', '.join(missing_headers)}")

    parsed_rows: list[ImportUserRow] = []
    for row_number, row in enumerate(rows[1:], start=2):
        openid = _cell(row, indexes, "openid")
        mobile = _cell(row, indexes, "mobile")
        allowed_services = _cell(row, indexes, "allowed_services")
        auth_start_at = _cell(row, indexes, "auth_start_at")
        auth_end_at = _cell(row, indexes, "auth_end_at")
        if not mobile:
            raise ValueError(f"Excel row {row_number} missing required field: mobile")
        if not allowed_services:
            raise ValueError(f"Excel row {row_number} missing required field: allowed_services")
        if not auth_end_at:
            raise ValueError(f"Excel row {row_number} missing required field: auth_end_at")
        openid_generated = not bool(openid)
        if openid_generated:
            openid = _generated_pending_openid(mobile, row_number)
        parsed_rows.append(
            ImportUserRow(
                openid=openid,
                name=_cell(row, indexes, "name"),
                institution=_cell(row, indexes, "institution"),
                mobile=mobile,
                enabled=_parse_enabled(_cell(row, indexes, "enabled")),
                allowed_services=allowed_services,
                auth_start_at=_parse_required_import_date(auth_start_at, row_number, "auth_start_at") if auth_start_at else None,
                auth_end_at=_parse_required_import_date(auth_end_at, row_number, "auth_end_at"),
                remark=_cell(row, indexes, "remark"),
                openid_generated=openid_generated,
            )
        )
    return parsed_rows


def import_users_from_excel(source: bytes | str | Path) -> ImportResult:
    return import_users(parse_users_excel(source))
