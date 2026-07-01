# encoding:utf-8
import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable
from uuid import uuid4

from Crypto.Cipher import AES
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

from business.config.constants import CUSTOMER_SERVICE_TYPES, ServiceType, normalize_service
from business.schema.db import connect, row_to_dict
from business.schema.tables import activation_codes, investment_users

CODE_PREFIX = "ANAL-"
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
DEFAULT_HMAC_SECRET = "cowagent-activation-code-secret"


@dataclass
class ActivationCodeBatch:
    batch_id: str
    codes: list[str]


@dataclass
class ActivationCodeRow:
    id: int
    batch_id: str
    code_hash: str
    code_prefix: str
    code_cipher: str
    code: str
    allowed_services: list[ServiceType]
    subscription_days: int
    code_expires_at: str
    status: str
    activation_mode: str = "generic"
    customer_id: int | None = None
    subscription_start_at: str = ""
    subscription_end_at: str = ""
    used_by_openid: str = ""
    used_at: str = ""
    created_at: str = ""
    updated_at: str = ""
    remark: str = ""


@dataclass
class ActivationResult:
    success: bool
    status: str
    message: str
    auth_end_at: datetime | None = None


def _now_dt() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _now() -> str:
    return _now_dt().isoformat(timespec="microseconds")


def _to_iso(value: datetime | str | None) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value
        return parsed.isoformat(timespec="seconds")
    return str(value)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def normalize_activation_code(value: str) -> str:
    text = str(value or "").strip().upper()
    return text.replace("－", "-").replace("—", "-").replace("–", "-")


def is_activation_code_text(value: str) -> bool:
    return normalize_activation_code(value).startswith(CODE_PREFIX)


def _secret() -> str:
    try:
        from business.config.config_service import get_config

        configured = str(get_config("activation.code_secret", "") or "").strip()
        if configured:
            return configured
    except Exception:
        pass
    try:
        from config import conf

        configured = str(conf().get("activation_code_secret", "") or "").strip()
        if configured:
            return configured
    except Exception:
        pass
    return DEFAULT_HMAC_SECRET


def activation_code_hash(value: str) -> str:
    normalized = normalize_activation_code(value)
    return hmac.new(_secret().encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def _cipher_key() -> bytes:
    return hashlib.sha256(f"{_secret()}:activation-code-cipher".encode("utf-8")).digest()


def _encrypt_activation_code(value: str) -> str:
    normalized = normalize_activation_code(value)
    cipher = AES.new(_cipher_key(), AES.MODE_GCM)
    ciphertext, tag = cipher.encrypt_and_digest(normalized.encode("utf-8"))
    payload = cipher.nonce + tag + ciphertext
    return base64.urlsafe_b64encode(payload).decode("ascii")


def _decrypt_activation_code(value: str | None) -> str:
    if not value:
        return ""
    try:
        payload = base64.urlsafe_b64decode(str(value).encode("ascii"))
        nonce, tag, ciphertext = payload[:16], payload[16:32], payload[32:]
        cipher = AES.new(_cipher_key(), AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")
    except Exception:
        return ""


def _random_code() -> str:
    groups = ["".join(secrets.choice(CODE_ALPHABET) for _ in range(4)) for _ in range(4)]
    return CODE_PREFIX + "-".join(groups)


def _encode_services(values: Iterable[str | ServiceType] | str) -> str:
    if isinstance(values, str):
        raw = [item.strip() for item in values.replace("，", ",").split(",") if item.strip()]
    else:
        raw = list(values)
    services: list[ServiceType] = []
    for value in raw:
        service = normalize_service(value)
        if service not in services and service != ServiceType.UNMATCHED:
            services.append(service)
    if not services:
        services = [ServiceType.ALL]
    customer_services = set(CUSTOMER_SERVICE_TYPES)
    if ServiceType.ALL in services or customer_services.issubset(set(services)):
        services = [ServiceType.ALL]
    return json.dumps([str(item) for item in services], ensure_ascii=False)


def _decode_services(value: str) -> list[ServiceType]:
    try:
        raw = json.loads(value or "[]")
    except Exception:
        raw = [item for item in str(value or "").split(",") if item]
    return [normalize_service(item) for item in raw if normalize_service(item) != ServiceType.UNMATCHED]


def _merge_services(existing: str, added: str) -> str:
    return _encode_services(_decode_services(existing) + _decode_services(added))


def _row_to_activation(row) -> ActivationCodeRow | None:
    if row is None:
        return None
    item = row_to_dict(row)
    code_cipher = item.get("code_cipher") or ""
    code = _decrypt_activation_code(code_cipher) or item["code_prefix"]
    return ActivationCodeRow(
        id=int(item["id"]),
        batch_id=item["batch_id"],
        code_hash=item["code_hash"],
        code_prefix=item["code_prefix"],
        code_cipher=code_cipher,
        code=code,
        allowed_services=_decode_services(item["allowed_services"]),
        subscription_days=int(item["subscription_days"]),
        code_expires_at=item["code_expires_at"],
        status=item["status"],
        activation_mode=item.get("activation_mode") or "generic",
        customer_id=int(item["customer_id"]) if item.get("customer_id") is not None else None,
        subscription_start_at=item.get("subscription_start_at") or "",
        subscription_end_at=item.get("subscription_end_at") or "",
        used_by_openid=item.get("used_by_openid") or "",
        used_at=item.get("used_at") or "",
        created_at=item["created_at"],
        updated_at=item["updated_at"],
        remark=item.get("remark") or "",
    )


def _admin_values(actor: Any | None, *, prefix: str = "created") -> dict[str, Any]:
    if actor is None:
        return {}
    return {
        f"{prefix}_by_admin_id": getattr(actor, "id", None),
        f"{prefix}_by_username": str(getattr(actor, "username", "") or ""),
    }


def generate_activation_codes(
    *,
    count: int,
    allowed_services: Iterable[str | ServiceType] | str,
    subscription_days: int,
    code_expires_at: datetime | str,
    remark: str = "",
    actor: Any | None = None,
) -> ActivationCodeBatch:
    count = max(1, min(int(count or 1), 1000))
    subscription_days = max(1, int(subscription_days or 1))
    expires_text = _to_iso(code_expires_at)
    batch_id = f"act_{uuid4().hex}"
    now = _now()
    codes: list[str] = []
    values: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    encoded_services = _encode_services(allowed_services)
    while len(codes) < count:
        code = _random_code()
        code_hash = activation_code_hash(code)
        if code_hash in seen_hashes:
            continue
        seen_hashes.add(code_hash)
        codes.append(code)
        values.append(
            {
                "batch_id": batch_id,
                "code_hash": code_hash,
                "code_prefix": code[:10],
                "code_cipher": _encrypt_activation_code(code),
                "allowed_services": encoded_services,
                "subscription_days": subscription_days,
                "activation_mode": "generic",
                "customer_id": None,
                "subscription_start_at": None,
                "subscription_end_at": None,
                "code_expires_at": expires_text,
                "status": "unused",
                "created_at": now,
                "updated_at": now,
                "remark": remark,
                **_admin_values(actor),
            }
        )
    with connect() as conn:
        conn.execute(insert(activation_codes), values)
    return ActivationCodeBatch(batch_id=batch_id, codes=codes)


def generate_customer_activation_code(
    *,
    customer_id: int,
    code_expires_at: datetime | str | None = None,
    remark: str = "",
    actor: Any | None = None,
) -> ActivationCodeBatch:
    from business.accounts.user_service import get_user_by_id

    customer = get_user_by_id(int(customer_id))
    if customer is None:
        raise ValueError("customer not found")
    if customer.auth_end_at is None:
        raise ValueError("customer auth_end_at is required")

    expires_text = _to_iso(code_expires_at or customer.auth_end_at)
    batch_id = f"act_{uuid4().hex}"
    encoded_services = _encode_services(customer.allowed_services or [ServiceType.ALL])
    for _attempt in range(10):
        now = _now()
        code = _random_code()
        code_hash = activation_code_hash(code)
        values = {
            "batch_id": batch_id,
            "code_hash": code_hash,
            "code_prefix": code[:10],
            "code_cipher": _encrypt_activation_code(code),
            "allowed_services": encoded_services,
            "subscription_days": 1,
            "activation_mode": "preregistered",
            "customer_id": int(customer_id),
            "subscription_start_at": _to_iso(customer.auth_start_at),
            "subscription_end_at": _to_iso(customer.auth_end_at),
            "code_expires_at": expires_text,
            "status": "unused",
            "created_at": now,
            "updated_at": now,
            "remark": remark,
            **_admin_values(actor),
        }
        try:
            with connect() as conn:
                existing = conn.execute(select(activation_codes.c.id).where(activation_codes.c.code_hash == code_hash)).fetchone()
                if existing:
                    continue
                conn.execute(insert(activation_codes), values)
            return ActivationCodeBatch(batch_id=batch_id, codes=[code])
        except IntegrityError:
            continue
    raise RuntimeError("failed to generate unique customer activation code")


def _activation_conditions(status: str | None = None, batch_id: str | None = None) -> list:
    conditions = []
    if status:
        conditions.append(activation_codes.c.status == status)
    if batch_id:
        conditions.append(activation_codes.c.batch_id == batch_id)
    return conditions


def list_activation_codes(
    status: str | None = None,
    batch_id: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> list[ActivationCodeRow]:
    stmt = select(activation_codes)
    conditions = _activation_conditions(status=status, batch_id=batch_id)
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.order_by(activation_codes.c.id.desc())
    if page is not None and page_size is not None:
        page = max(1, int(page or 1))
        page_size = max(1, int(page_size or 20))
        stmt = stmt.limit(page_size).offset((page - 1) * page_size)
    with connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [item for row in rows if (item := _row_to_activation(row))]


def count_activation_codes(status: str | None = None, batch_id: str | None = None) -> int:
    stmt = select(func.count()).select_from(activation_codes)
    conditions = _activation_conditions(status=status, batch_id=batch_id)
    if conditions:
        stmt = stmt.where(*conditions)
    with connect() as conn:
        return int(conn.execute(stmt).scalar_one() or 0)


def get_unused_customer_activation_code(customer_id: int) -> ActivationCodeRow | None:
    stmt = (
        select(activation_codes)
        .where(
            activation_codes.c.activation_mode == "preregistered",
            activation_codes.c.customer_id == int(customer_id),
            activation_codes.c.status == "unused",
        )
        .order_by(activation_codes.c.id.desc())
        .limit(1)
    )
    with connect() as conn:
        row = conn.execute(stmt).fetchone()
    return _row_to_activation(row)


def _activation_message(status: str, auth_end_at: datetime | None = None) -> str:
    if status == "activated":
        end_text = auth_end_at.strftime("%Y-%m-%d") if auth_end_at else ""
        return f"激活成功，服务有效期至 {end_text}。"
    messages = {
        "invalid": "激活失败：激活码不存在或格式不正确。",
        "used": "激活失败：该激活码已被使用。",
        "expired": "激活失败：该激活码已过期。",
        "disabled": "激活失败：该激活码已停用。",
        "already_bound": "激活失败：该客户已绑定其他微信，请联系管理员处理。",
    }
    return messages.get(status, "激活失败，请稍后重试。")


def _current_code_status(conn, code_id: int) -> str:
    row = conn.execute(select(activation_codes.c.status).where(activation_codes.c.id == code_id)).fetchone()
    return str(row_to_dict(row).get("status") or "invalid") if row else "invalid"


def _upsert_customer_for_activation(conn, openid: str, code_item: dict[str, Any], now_dt: datetime, now: str) -> datetime:
    user_row = conn.execute(select(investment_users).where(investment_users.c.openid == openid)).fetchone()
    existing = row_to_dict(user_row) if user_row else {}
    existing_end = _parse_dt(existing.get("auth_end_at")) if existing else None
    starts_from = existing_end if existing_end and existing_end > now_dt else now_dt
    auth_end_at = starts_from + timedelta(days=int(code_item["subscription_days"]))
    auth_start_at = _parse_dt(existing.get("auth_start_at")) if existing else None
    auth_start_at = auth_start_at or now_dt

    values = {
        "enabled": 1,
        "allowed_services": _merge_services(existing.get("allowed_services") or "[]", code_item["allowed_services"]),
        "auth_start_at": _to_iso(auth_start_at),
        "auth_end_at": _to_iso(auth_end_at),
        "updated_at": now,
    }
    if existing:
        conn.execute(update(investment_users).where(investment_users.c.openid == openid).values(**values))
    else:
        conn.execute(
            insert(investment_users).values(
                openid=openid,
                name="",
                institution="",
                mobile="",
                remark="",
                created_at=now,
                **values,
            )
        )
    return auth_end_at


class _PreregisteredActivationError(Exception):
    def __init__(self, status: str):
        self.status = status
        super().__init__(status)


def _prepare_preregistered_activation(
    conn,
    openid: str,
    code_item: dict[str, Any],
    now_dt: datetime,
    now: str,
) -> tuple[int, dict[str, Any], datetime | None]:
    customer_id = code_item.get("customer_id")
    if customer_id is None:
        raise _PreregisteredActivationError("invalid")

    customer_id = int(customer_id)
    row = (
        conn.execute(
            select(investment_users)
            .where(investment_users.c.id == customer_id)
            .with_for_update()
        )
        .fetchone()
    )
    customer = row_to_dict(row) if row else {}
    if not customer:
        raise _PreregisteredActivationError("invalid")

    customer_openid = str(customer.get("openid") or "").strip()
    if customer_openid and customer_openid != openid:
        raise _PreregisteredActivationError("already_bound")
    if not customer_openid:
        conflict = (
            conn.execute(
                select(investment_users.c.id)
                .where(investment_users.c.openid == openid)
                .where(investment_users.c.id != customer_id)
                .limit(1)
            )
            .fetchone()
        )
        if conflict:
            raise _PreregisteredActivationError("already_bound")

    allowed_services = code_item.get("allowed_services") or customer.get("allowed_services") or _encode_services([ServiceType.ALL])
    auth_start_at = (
        _parse_dt(code_item.get("subscription_start_at"))
        or _parse_dt(customer.get("auth_start_at"))
        or now_dt
    )
    auth_end_at = _parse_dt(code_item.get("subscription_end_at")) or _parse_dt(customer.get("auth_end_at"))

    values = {
        "enabled": 1,
        "allowed_services": allowed_services,
        "auth_start_at": _to_iso(auth_start_at),
        "auth_end_at": _to_iso(auth_end_at),
        "bind_status": "bound",
        "updated_at": now,
    }
    if not customer_openid:
        values.update(
            {
                "openid": openid,
                "bound_at": now,
                "unbound_at": None,
            }
        )

    return customer_id, values, auth_end_at


def redeem_activation_code(openid: str, code: str) -> ActivationResult:
    normalized = normalize_activation_code(code)
    if not normalized.startswith(CODE_PREFIX):
        return ActivationResult(False, "invalid", _activation_message("invalid"))

    code_hash = activation_code_hash(normalized)
    now_dt = _now_dt()
    now = now_dt.isoformat(timespec="microseconds")
    with connect() as conn:
        row = conn.execute(select(activation_codes).where(activation_codes.c.code_hash == code_hash)).fetchone()
        item = row_to_dict(row) if row else {}
        if not item:
            return ActivationResult(False, "invalid", _activation_message("invalid"))

        status = str(item["status"] or "")
        if status != "unused":
            result_status = "used" if status == "used" else "disabled" if status == "disabled" else "invalid"
            return ActivationResult(False, result_status, _activation_message(result_status))

        expires_at = _parse_dt(item.get("code_expires_at"))
        if expires_at and now_dt > expires_at:
            return ActivationResult(False, "expired", _activation_message("expired"))

        if item.get("activation_mode") == "preregistered":
            try:
                customer_id, customer_values, auth_end_at = _prepare_preregistered_activation(conn, openid, item, now_dt, now)
            except _PreregisteredActivationError as exc:
                return ActivationResult(False, exc.status, _activation_message(exc.status))
            result = conn.execute(
                update(activation_codes)
                .where(activation_codes.c.id == item["id"])
                .where(activation_codes.c.status == "unused")
                .values(status="used", used_by_openid=openid, used_at=now, updated_at=now)
            )
            if result.rowcount != 1:
                current_status = _current_code_status(conn, int(item["id"]))
                result_status = "used" if current_status == "used" else "disabled" if current_status == "disabled" else "invalid"
                return ActivationResult(False, result_status, _activation_message(result_status))
            conn.execute(update(investment_users).where(investment_users.c.id == customer_id).values(**customer_values))
        else:
            result = conn.execute(
                update(activation_codes)
                .where(activation_codes.c.id == item["id"])
                .where(activation_codes.c.status == "unused")
                .values(status="used", used_by_openid=openid, used_at=now, updated_at=now)
            )
            if result.rowcount != 1:
                current_status = _current_code_status(conn, int(item["id"]))
                result_status = "used" if current_status == "used" else "disabled" if current_status == "disabled" else "invalid"
                return ActivationResult(False, result_status, _activation_message(result_status))
            auth_end_at = _upsert_customer_for_activation(conn, openid, item, now_dt, now)
    return ActivationResult(True, "activated", _activation_message("activated", auth_end_at), auth_end_at)


def disable_activation_code(code_id: int, *, actor: Any | None = None) -> bool:
    now = _now()
    with connect() as conn:
        result = conn.execute(
            update(activation_codes)
            .where(activation_codes.c.id == int(code_id))
            .where(activation_codes.c.status == "unused")
            .values(status="disabled", updated_at=now)
        )
    return result.rowcount == 1
