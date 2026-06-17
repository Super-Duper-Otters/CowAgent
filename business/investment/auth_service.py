# encoding:utf-8
import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, insert, select, update

from business.db import connect, row_to_dict
from business.schema import investment_admin_sessions, investment_admin_users

HASH_ALGORITHM = "pbkdf2_sha256"
HASH_ITERATIONS = 260_000
SESSION_DAYS = 30

ROLE_PERMISSIONS = {
    "admin": {
        "*",
        "customers.read",
        "customers.write",
        "customers.enable",
        "customers.import",
        "customers.export",
        "admin_users.read",
        "admin_users.write",
        "admin_users.reset_password",
        "content.read",
        "content.upload",
        "content.write",
        "content.generate",
        "content.publish",
        "content.effective",
        "content.delete",
        "records.read",
        "records.export",
        "audits.read",
        "cache.read",
        "cache.write",
        "config.read",
        "config.write",
        "health.read",
        "stocks.read",
        "stocks.write",
        "skills.read",
        "skills.write",
    },
    "content_operator": {
        "content.read",
        "content.upload",
        "content.write",
        "content.generate",
        "content.publish",
        "content.effective",
    },
    "technical_operator": {
        "config.read",
        "config.write",
    },
    "readonly": {
        "customers.read",
        "content.read",
        "records.read",
        "audits.read",
        "cache.read",
        "config.read",
        "health.read",
        "stocks.read",
        "skills.read",
    },
}


@dataclass
class AdminUser:
    id: int
    username: str
    role: str
    enabled: bool = True
    bootstrap: bool = False
    last_login_at: str = ""


@dataclass
class PermissionResult:
    allowed: bool
    code: str = ""
    message: str = ""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def hash_password(password: str, *, salt: bytes | None = None, iterations: int = HASH_ITERATIONS) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(
        [
            HASH_ALGORITHM,
            str(iterations),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = password_hash.split("$", 3)
        if algorithm != HASH_ALGORITHM:
            return False
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(digest_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    except Exception:
        return False
    return hmac.compare_digest(actual, expected)


def _row_to_admin(row) -> AdminUser | None:
    if row is None:
        return None
    item = row_to_dict(row)
    return AdminUser(
        id=int(item["id"]),
        username=item["username"],
        role=normalize_role(item["role"]),
        enabled=bool(item["enabled"]),
        last_login_at=item.get("last_login_at") or "",
    )


def _admin_user_conditions(keyword: str | None = None) -> list:
    keyword_text = str(keyword or "").strip()
    if not keyword_text:
        return []
    pattern = f"%{keyword_text}%"
    return [
        or_(
            investment_admin_users.c.username.ilike(pattern),
            investment_admin_users.c.role.ilike(pattern),
        )
    ]


def count_admin_users(keyword: str | None = None) -> int:
    stmt = select(func.count()).select_from(investment_admin_users)
    conditions = _admin_user_conditions(keyword)
    if conditions:
        stmt = stmt.where(*conditions)
    with connect() as conn:
        return int(conn.execute(stmt).scalar_one())


def create_admin_user(username: str, password: str, *, role: str = "content_operator", enabled: bool = True) -> int:
    role = normalize_role(role)
    now = _now()
    with connect() as conn:
        result = conn.execute(
            insert(investment_admin_users).values(
                username=username,
                password_hash=hash_password(password),
                role=role,
                enabled=1 if enabled else 0,
                created_at=now,
                updated_at=now,
            )
        )
        if result.inserted_primary_key and result.inserted_primary_key[0] is not None:
            return int(result.inserted_primary_key[0])
        row = conn.execute(select(investment_admin_users.c.id).where(investment_admin_users.c.username == username)).fetchone()
    return int(row_to_dict(row)["id"])


def list_admin_users(keyword: str | None = None, page: int | None = None, page_size: int | None = None) -> list[AdminUser]:
    stmt = select(investment_admin_users)
    conditions = _admin_user_conditions(keyword)
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.order_by(investment_admin_users.c.username.asc())
    if page is not None and page_size is not None:
        page = max(1, int(page or 1))
        page_size = max(1, int(page_size or 1))
        stmt = stmt.limit(page_size).offset((page - 1) * page_size)
    with connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [admin for row in rows if (admin := _row_to_admin(row))]


def get_admin_user(username: str) -> AdminUser | None:
    with connect() as conn:
        row = conn.execute(select(investment_admin_users).where(investment_admin_users.c.username == username)).fetchone()
    return _row_to_admin(row)


def _enabled_admin_count(conn, *, exclude_username: str = "") -> int:
    stmt = select(func.count()).select_from(investment_admin_users).where(
        investment_admin_users.c.enabled == 1,
        investment_admin_users.c.role == "admin",
    )
    if exclude_username:
        stmt = stmt.where(investment_admin_users.c.username != exclude_username)
    return int(conn.execute(stmt).scalar_one() or 0)


def _assert_can_change_admin(conn, username: str, values: dict) -> None:
    row = conn.execute(select(investment_admin_users).where(investment_admin_users.c.username == username)).fetchone()
    if row is None:
        raise ValueError(f"admin user not found: {username}")
    item = row_to_dict(row)
    current_role = normalize_role(item["role"])
    current_enabled = bool(item["enabled"])
    next_role = values.get("role", current_role)
    next_enabled = bool(values.get("enabled", 1 if current_enabled else 0))
    if current_role == "admin" and current_enabled and (next_role != "admin" or not next_enabled):
        if _enabled_admin_count(conn, exclude_username=username) == 0:
            raise ValueError("cannot disable or demote the last enabled admin")


def update_admin_user(username: str, *, role: str | None = None, enabled: bool | None = None) -> None:
    values = {}
    if role is not None:
        values["role"] = normalize_role(role)
    if enabled is not None:
        values["enabled"] = 1 if enabled else 0
    if not values:
        return
    values["updated_at"] = _now()
    with connect() as conn:
        _assert_can_change_admin(conn, username, values)
        conn.execute(update(investment_admin_users).where(investment_admin_users.c.username == username).values(**values))


def reset_admin_password(username: str, password: str) -> None:
    with connect() as conn:
        row = conn.execute(select(investment_admin_users.c.id).where(investment_admin_users.c.username == username)).fetchone()
        if row is None:
            raise ValueError(f"admin user not found: {username}")
        conn.execute(
            update(investment_admin_users)
            .where(investment_admin_users.c.username == username)
            .values(password_hash=hash_password(password), updated_at=_now())
        )


def authenticate_admin(username: str, password: str) -> AdminUser | None:
    with connect() as conn:
        row = conn.execute(select(investment_admin_users).where(investment_admin_users.c.username == username)).fetchone()
        item = row_to_dict(row) if row else {}
        if not item or not bool(item["enabled"]) or not verify_password(password, item["password_hash"]):
            return None
        conn.execute(
            update(investment_admin_users)
            .where(investment_admin_users.c.id == item["id"])
            .values(last_login_at=_now(), updated_at=_now())
        )
    return _row_to_admin(item)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_admin_session(admin: AdminUser, *, days: int = SESSION_DAYS) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    with connect() as conn:
        conn.execute(
            insert(investment_admin_sessions).values(
                session_id=secrets.token_hex(16),
                user_id=admin.id,
                token_hash=_token_hash(token),
                created_at=now.isoformat(timespec="microseconds"),
                expires_at=(now + timedelta(days=days)).isoformat(timespec="microseconds"),
            )
        )
    return token


def get_admin_session(token: str | None) -> AdminUser | None:
    if not token:
        return None
    table = investment_admin_sessions
    users = investment_admin_users
    with connect() as conn:
        row = conn.execute(
            select(users)
            .select_from(table.join(users, table.c.user_id == users.c.id))
            .where(table.c.token_hash == _token_hash(token))
        ).fetchone()
    admin = _row_to_admin(row)
    if admin is None or not admin.enabled:
        return None
    with connect() as conn:
        expires_at = conn.execute(
            select(table.c.expires_at).where(table.c.token_hash == _token_hash(token))
        ).scalar_one_or_none()
    parsed_expires_at = _from_iso(expires_at)
    if parsed_expires_at and datetime.now(UTC) > parsed_expires_at:
        return None
    return admin


def normalize_role(role: str) -> str:
    value = str(role or "").strip()
    if value not in ROLE_PERMISSIONS:
        raise ValueError(f"unsupported admin role: {role}")
    return value


def permissions_for_role(role: str) -> set[str]:
    role = normalize_role(role)
    permissions = ROLE_PERMISSIONS[role]
    if "*" in permissions:
        expanded: set[str] = set()
        for values in ROLE_PERMISSIONS.values():
            expanded.update(item for item in values if item != "*")
        expanded.add("*")
        return expanded
    return set(permissions)


def require_permission(admin: AdminUser | None, permission: str) -> PermissionResult:
    if admin is None:
        return PermissionResult(False, "unauthorized", "未登录或登录已过期")
    if not admin.enabled:
        return PermissionResult(False, "unauthorized", "账号已停用")
    permissions = permissions_for_role(admin.role)
    if "*" in permissions or permission in permissions:
        return PermissionResult(True)
    return PermissionResult(False, "permission_denied", "权限不足")
