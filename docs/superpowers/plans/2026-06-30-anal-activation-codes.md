# ANAL Activation Codes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `ANAL-` activation-code system that lets unauthorized WeChat Official Account users activate service permissions and subscription time through passive replies, with generation and management in the investment WebUI.

**Architecture:** Store activation codes as HMAC-SHA256 hashes, never plaintext, and reuse the existing `customers` permission model for the activated subscription. The WeChat passive-reply entrypoint only enters activation flow for normalized text beginning with `ANAL-`; all other unauthorized input keeps the existing unauthorized prompt. Admin WebUI exposes generation, listing, disabling, and export of newly generated plaintext codes.

**Tech Stack:** Python, web.py, SQLAlchemy Core, Alembic migrations, existing investment WebUI JavaScript, pytest.

---

## Current Code Map

- `business/schema/tables.py`: SQLAlchemy table declarations. Add `activation_codes`.
- `migrations/business/versions/20260630_0029_activation_codes.py`: Create/drop activation-code table and indexes.
- `business/accounts/activation_service.py`: New service for code normalization, generation, HMAC hashing, listing, disabling, and redemption.
- `business/accounts/user_service.py`: Reuse `create_user`, `update_user`, `get_user_by_openid`; add small helper only if needed for transaction-safe updates.
- `business/config/reply_config.py`: Add configurable activation success/failure texts.
- `channel/wechatmp/passive_reply.py`: Detect `ANAL-` before business routing and enforce permission before cached-result delivery and new business replies.
- `channel/web/investment_handlers.py`: Register activation-code API routes.
- `channel/web/web_channel.py`: Add activation-code handlers and payload helpers.
- `channel/web/static/js/console.js`: Add activation-code panel under user management.
- `tests/test_business.py`: Unit tests for activation service and permissions.
- `tests/test_wechatmp_business_reply.py`: Passive-reply activation and permission-gate tests.
- `tests/test_business_web_ui.py`: API/JS route and UI wiring tests.

## Behavioral Requirements

- Only text whose normalized form starts with `ANAL-` enters activation-code verification.
- Non-`ANAL-` text from unauthorized users returns the existing unauthorized prompt.
- Valid activation code creates or updates the `customers` row for the sender `openid`.
- Used, disabled, expired, or unknown `ANAL-` codes return activation-failure prompts.
- Code validity and user subscription are separate:
  - `code_expires_at`: latest time the activation code may be redeemed.
  - `subscription_days`: number of days added to the user's subscription.
- If an existing user is active, redemption extends from current `auth_end_at`; otherwise it starts from now.
- Code permissions merge with existing user permissions. `all` remains canonical when all customer services are covered.
- Redemption is transaction-safe. Two concurrent redemptions of the same code cannot both succeed.
- Plaintext activation codes are returned only from the generation response/export for that generation request; the database stores only hashes and short display prefixes.

---

### Task 1: Database Schema and Activation Service

**Files:**
- Modify: `business/schema/tables.py`
- Create: `migrations/business/versions/20260630_0029_activation_codes.py`
- Create: `business/accounts/activation_service.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Write failing tests for code normalization, generation, and hash-only storage**

Append tests to `tests/test_business.py` near the existing account/permission tests:

```python
def test_activation_code_generation_uses_anal_prefix_and_hash_only_storage(business_env):
    from datetime import datetime, timedelta, UTC
    from business.accounts.activation_service import generate_activation_codes, list_activation_codes
    from business.config.constants import ServiceType

    expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
    result = generate_activation_codes(
        count=3,
        allowed_services=[ServiceType.TECHNICAL_ANALYSIS],
        subscription_days=30,
        code_expires_at=expires_at,
        remark="unit batch",
    )

    assert len(result.codes) == 3
    assert all(code.startswith("ANAL-") for code in result.codes)
    assert all(len(code.split("-")) == 5 for code in result.codes)

    rows = list_activation_codes()
    assert len(rows) == 3
    assert all(row.code_prefix.startswith("ANAL-") for row in rows)
    assert all(row.code_hash for row in rows)
    assert all(row.code_hash not in result.codes for row in rows)
    assert all(row.status == "unused" for row in rows)
```

- [ ] **Step 2: Run the new test and verify it fails**

Run:

```powershell
python -m pytest tests/test_business.py::test_activation_code_generation_uses_anal_prefix_and_hash_only_storage -q
```

Expected: fail with `ModuleNotFoundError` or missing `activation_codes`.

- [ ] **Step 3: Add the table declaration and migration**

In `business/schema/tables.py`, add:

```python
activation_codes = Table(
    "activation_codes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("batch_id", Text, nullable=False),
    Column("code_hash", Text, nullable=False),
    Column("code_prefix", Text, nullable=False),
    Column("allowed_services", Text, nullable=False),
    Column("subscription_days", Integer, nullable=False),
    Column("code_expires_at", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("used_by_openid", Text),
    Column("used_at", Text),
    Column("created_by_admin_id", Integer),
    Column("created_by_username", Text),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Column("remark", Text),
    Index("idx_activation_codes_hash", "code_hash", unique=True),
    Index("idx_activation_codes_batch", "batch_id"),
    Index("idx_activation_codes_status", "status", "code_expires_at"),
    Index("idx_activation_codes_used_by", "used_by_openid", "used_at"),
)
```

Create migration `migrations/business/versions/20260630_0029_activation_codes.py`:

```python
# encoding:utf-8
"""add activation codes"""

from alembic import op
import sqlalchemy as sa


revision = "20260630_0029"
down_revision = "20260625_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activation_codes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("batch_id", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("code_prefix", sa.Text(), nullable=False),
        sa.Column("allowed_services", sa.Text(), nullable=False),
        sa.Column("subscription_days", sa.Integer(), nullable=False),
        sa.Column("code_expires_at", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("used_by_openid", sa.Text()),
        sa.Column("used_at", sa.Text()),
        sa.Column("created_by_admin_id", sa.Integer()),
        sa.Column("created_by_username", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("remark", sa.Text()),
    )
    op.create_index("idx_activation_codes_hash", "activation_codes", ["code_hash"], unique=True)
    op.create_index("idx_activation_codes_batch", "activation_codes", ["batch_id"])
    op.create_index("idx_activation_codes_status", "activation_codes", ["status", "code_expires_at"])
    op.create_index("idx_activation_codes_used_by", "activation_codes", ["used_by_openid", "used_at"])


def downgrade() -> None:
    op.drop_index("idx_activation_codes_used_by", table_name="activation_codes")
    op.drop_index("idx_activation_codes_status", table_name="activation_codes")
    op.drop_index("idx_activation_codes_batch", table_name="activation_codes")
    op.drop_index("idx_activation_codes_hash", table_name="activation_codes")
    op.drop_table("activation_codes")
```

- [ ] **Step 4: Implement generation and listing**

Create `business/accounts/activation_service.py`:

```python
# encoding:utf-8
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable
from uuid import uuid4

from sqlalchemy import func, insert, select, update

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
    allowed_services: list[ServiceType]
    subscription_days: int
    code_expires_at: str
    status: str
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


def normalize_activation_code(value: str) -> str:
    text = str(value or "").strip().upper()
    text = text.replace("－", "-").replace("—", "-").replace("–", "-")
    return text


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


def _random_code() -> str:
    groups = ["".join(secrets.choice(CODE_ALPHABET) for _ in range(4)) for _ in range(4)]
    return CODE_PREFIX + "-".join(groups)


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
    if ServiceType.ALL in services or set(CUSTOMER_SERVICE_TYPES).issubset(set(services)):
        services = [ServiceType.ALL]
    return json.dumps([str(item) for item in services], ensure_ascii=False)


def _decode_services(value: str) -> list[ServiceType]:
    try:
        return [normalize_service(item) for item in json.loads(value or "[]")]
    except Exception:
        return [normalize_service(item) for item in str(value or "").split(",") if item]


def _row_to_activation(row) -> ActivationCodeRow | None:
    if row is None:
        return None
    item = row_to_dict(row)
    return ActivationCodeRow(
        id=int(item["id"]),
        batch_id=item["batch_id"],
        code_hash=item["code_hash"],
        code_prefix=item["code_prefix"],
        allowed_services=_decode_services(item["allowed_services"]),
        subscription_days=int(item["subscription_days"]),
        code_expires_at=item["code_expires_at"],
        status=item["status"],
        used_by_openid=item.get("used_by_openid") or "",
        used_at=item.get("used_at") or "",
        created_at=item["created_at"],
        updated_at=item["updated_at"],
        remark=item.get("remark") or "",
    )


def _admin_values(actor: Any | None) -> dict[str, Any]:
    if actor is None:
        return {}
    return {
        "created_by_admin_id": getattr(actor, "id", None),
        "created_by_username": str(getattr(actor, "username", "") or ""),
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
    expires_text = code_expires_at.isoformat(timespec="seconds") if isinstance(code_expires_at, datetime) else str(code_expires_at)
    batch_id = f"act_{uuid4().hex}"
    now = _now()
    codes: list[str] = []
    values = []
    seen_hashes = set()
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
                "allowed_services": _encode_services(allowed_services),
                "subscription_days": subscription_days,
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


def list_activation_codes(status: str | None = None, batch_id: str | None = None, page: int | None = None, page_size: int | None = None) -> list[ActivationCodeRow]:
    stmt = select(activation_codes)
    conditions = []
    if status:
        conditions.append(activation_codes.c.status == status)
    if batch_id:
        conditions.append(activation_codes.c.batch_id == batch_id)
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
```

- [ ] **Step 5: Run the generation/listing test**

Run:

```powershell
python -m pytest tests/test_business.py::test_activation_code_generation_uses_anal_prefix_and_hash_only_storage -q
```

Expected: pass.

- [ ] **Step 6: Write failing tests for redemption**

Append:

```python
def test_activation_code_redeem_creates_customer_and_marks_code_used(business_env):
    from datetime import datetime, timedelta, UTC
    from business.accounts.activation_service import generate_activation_codes, list_activation_codes, redeem_activation_code
    from business.accounts.user_service import get_user_by_openid, verify_permission
    from business.config.constants import ServiceType

    batch = generate_activation_codes(
        count=1,
        allowed_services=[ServiceType.TECHNICAL_ANALYSIS],
        subscription_days=30,
        code_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
    )

    result = redeem_activation_code("openid-activation-new", batch.codes[0])

    assert result.success is True
    assert result.status == "activated"
    user = get_user_by_openid("openid-activation-new")
    assert user is not None
    assert verify_permission("openid-activation-new", ServiceType.TECHNICAL_ANALYSIS).allowed is True
    assert verify_permission("openid-activation-new", ServiceType.RATE).allowed is False
    row = list_activation_codes()[0]
    assert row.status == "used"
    assert row.used_by_openid == "openid-activation-new"


def test_activation_code_redeem_rejects_used_and_expired_codes(business_env):
    from datetime import datetime, timedelta, UTC
    from business.accounts.activation_service import generate_activation_codes, redeem_activation_code
    from business.config.constants import ServiceType

    batch = generate_activation_codes(
        count=1,
        allowed_services=[ServiceType.ALL],
        subscription_days=30,
        code_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
    )
    assert redeem_activation_code("openid-first", batch.codes[0]).success is True
    used = redeem_activation_code("openid-second", batch.codes[0])
    assert used.success is False
    assert used.status == "used"

    expired_batch = generate_activation_codes(
        count=1,
        allowed_services=[ServiceType.ALL],
        subscription_days=30,
        code_expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
    )
    expired = redeem_activation_code("openid-expired-code", expired_batch.codes[0])
    assert expired.success is False
    assert expired.status == "expired"
```

- [ ] **Step 7: Run redemption tests and verify failure**

Run:

```powershell
python -m pytest tests/test_business.py::test_activation_code_redeem_creates_customer_and_marks_code_used tests/test_business.py::test_activation_code_redeem_rejects_used_and_expired_codes -q
```

Expected: fail with missing `redeem_activation_code`.

- [ ] **Step 8: Implement redemption and disabling/counting helpers**

Add to `business/accounts/activation_service.py`:

```python
def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _merge_services(existing: str, added: str) -> str:
    merged = _decode_services(existing) + _decode_services(added)
    return _encode_services(merged)


def _activation_message(status: str, auth_end_at: datetime | None = None) -> str:
    if status == "activated":
        end_text = auth_end_at.strftime("%Y-%m-%d") if auth_end_at else ""
        return f"激活成功，服务有效期至 {end_text}。"
    messages = {
        "invalid": "激活失败：激活码不存在或格式不正确。",
        "used": "激活失败：该激活码已被使用。",
        "expired": "激活失败：该激活码已过期。",
        "disabled": "激活失败：该激活码已停用。",
    }
    return messages.get(status, "激活失败，请稍后重试。")


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
        if status == "used":
            return ActivationResult(False, "used", _activation_message("used"))
        if status == "disabled":
            return ActivationResult(False, "disabled", _activation_message("disabled"))
        expires_at = _parse_dt(item["code_expires_at"])
        if expires_at and now_dt > expires_at:
            return ActivationResult(False, "expired", _activation_message("expired"))

        updated = conn.execute(
            update(activation_codes)
            .where(activation_codes.c.id == item["id"])
            .where(activation_codes.c.status == "unused")
            .values(status="used", used_by_openid=openid, used_at=now, updated_at=now)
        )
        if getattr(updated, "rowcount", 0) != 1:
            return ActivationResult(False, "used", _activation_message("used"))

        user_row = conn.execute(select(investment_users).where(investment_users.c.openid == openid)).fetchone()
        user = row_to_dict(user_row) if user_row else {}
        current_end = _parse_dt(user.get("auth_end_at")) if user else None
        start_at = current_end if current_end and current_end > now_dt else now_dt
        next_end = start_at + timedelta(days=int(item["subscription_days"]))
        if user:
            conn.execute(
                update(investment_users)
                .where(investment_users.c.openid == openid)
                .values(
                    enabled=1,
                    allowed_services=_merge_services(user.get("allowed_services") or "[]", item["allowed_services"]),
                    auth_start_at=(user.get("auth_start_at") or now_dt.isoformat(timespec="seconds")),
                    auth_end_at=next_end.isoformat(timespec="seconds"),
                    updated_at=now,
                )
            )
        else:
            conn.execute(
                insert(investment_users).values(
                    openid=openid,
                    name="",
                    institution="",
                    mobile="",
                    enabled=1,
                    allowed_services=item["allowed_services"],
                    auth_start_at=now_dt.isoformat(timespec="seconds"),
                    auth_end_at=next_end.isoformat(timespec="seconds"),
                    remark="activation_code",
                    created_at=now,
                    updated_at=now,
                )
            )
    return ActivationResult(True, "activated", _activation_message("activated", next_end), next_end)


def disable_activation_code(code_id: int, *, actor: Any | None = None) -> bool:
    now = _now()
    with connect() as conn:
        result = conn.execute(
            update(activation_codes)
            .where(activation_codes.c.id == int(code_id))
            .where(activation_codes.c.status == "unused")
            .values(status="disabled", updated_at=now)
        )
    return getattr(result, "rowcount", 0) == 1


def count_activation_codes(status: str | None = None, batch_id: str | None = None) -> int:
    stmt = select(func.count()).select_from(activation_codes)
    conditions = []
    if status:
        conditions.append(activation_codes.c.status == status)
    if batch_id:
        conditions.append(activation_codes.c.batch_id == batch_id)
    if conditions:
        stmt = stmt.where(*conditions)
    with connect() as conn:
        return int(conn.execute(stmt).scalar_one() or 0)
```

- [ ] **Step 9: Run Task 1 tests**

Run:

```powershell
python -m pytest tests/test_business.py::test_activation_code_generation_uses_anal_prefix_and_hash_only_storage tests/test_business.py::test_activation_code_redeem_creates_customer_and_marks_code_used tests/test_business.py::test_activation_code_redeem_rejects_used_and_expired_codes -q
```

Expected: all pass.

---

### Task 2: Configurable Reply Texts and WeChat Passive-Reply Activation Flow

**Files:**
- Modify: `business/config/reply_config.py`
- Modify: `channel/wechatmp/passive_reply.py`
- Test: `tests/test_wechatmp_business_reply.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Write failing tests for reply config metadata**

Append to `tests/test_business.py`:

```python
def test_activation_reply_texts_are_configurable(business_env):
    from business.config.reply_config import reply_text_config_metadata

    definitions = reply_text_config_metadata()["definitions"]
    assert "reply.investment.activation_success" in definitions
    assert "reply.investment.activation_invalid" in definitions
    assert "reply.investment.activation_used" in definitions
    assert "reply.investment.activation_expired" in definitions
    assert "reply.investment.activation_disabled" in definitions
```

- [ ] **Step 2: Add reply definitions**

In `business/config/reply_config.py`, add to `INVESTMENT_REPLY_DEFINITIONS`:

```python
    ReplyTextDefinition("reply.investment.activation_success", "激活成功提示", "客户使用 ANAL 激活码成功后返回。保留 `{auth_end_at}`，系统会替换为授权结束日期。", "激活成功，服务有效期至 {auth_end_at}。", ("auth_end_at",)),
    ReplyTextDefinition("reply.investment.activation_invalid", "激活码无效提示", "客户输入 ANAL 开头但不存在或格式不正确时返回。", "激活失败：激活码不存在或格式不正确。"),
    ReplyTextDefinition("reply.investment.activation_used", "激活码已使用提示", "客户输入已被兑换的激活码时返回。", "激活失败：该激活码已被使用。"),
    ReplyTextDefinition("reply.investment.activation_expired", "激活码过期提示", "客户输入已超过激活码有效期的激活码时返回。", "激活失败：该激活码已过期。"),
    ReplyTextDefinition("reply.investment.activation_disabled", "激活码停用提示", "客户输入后台已停用的激活码时返回。", "激活失败：该激活码已停用。"),
```

- [ ] **Step 3: Run reply config test**

Run:

```powershell
python -m pytest tests/test_business.py::test_activation_reply_texts_are_configurable -q
```

Expected: pass.

- [ ] **Step 4: Write failing passive-reply tests**

Add tests to `tests/test_wechatmp_business_reply.py` using the existing `_fake_passive_post` pattern:

```python
def test_passive_reply_redeems_anal_activation_code(monkeypatch):
    from types import SimpleNamespace
    from channel.wechatmp import passive_reply

    channel = SimpleNamespace(cache_dict={}, running=set(), request_cnt={})
    current_message = {"content": "anal-abcd-efgh-jklm-npqr", "msg_id": "msg-activation"}
    produced = []
    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced)

    calls = []
    monkeypatch.setattr(passive_reply, "_is_activation_code_text", lambda text: str(text).upper().startswith("ANAL-"))
    monkeypatch.setattr(
        passive_reply,
        "_redeem_activation_code_text",
        lambda openid, text: calls.append((openid, text)) or "激活成功，服务有效期至 2099-01-01。",
    )

    response = passive_reply.Query().POST()

    assert response == "激活成功，服务有效期至 2099-01-01。"
    assert calls == [("openid", "anal-abcd-efgh-jklm-npqr")]
    assert produced == []


def test_passive_reply_non_anal_unauthorized_keeps_default_prompt(monkeypatch):
    from types import SimpleNamespace
    from business.config.constants import ErrorCode
    from channel.wechatmp import passive_reply

    channel = SimpleNamespace(cache_dict={}, running=set(), request_cnt={})
    current_message = {"content": "利率", "msg_id": "msg-denied"}
    produced = []
    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced)
    monkeypatch.setattr(passive_reply, "_is_activation_code_text", lambda _text: False)
    monkeypatch.setattr(
        passive_reply,
        "_verify_wechatmp_text_access",
        lambda _openid, _content: SimpleNamespace(allowed=False, user_prompt="您暂未开通该服务，如需开通请联系服务人员。", error_code=ErrorCode.UNAUTHORIZED),
    )

    response = passive_reply.Query().POST()

    assert response == "您暂未开通该服务，如需开通请联系服务人员。"
    assert produced == []
```

- [ ] **Step 5: Run passive-reply tests and verify failure**

Run:

```powershell
python -m pytest tests/test_wechatmp_business_reply.py::test_passive_reply_redeems_anal_activation_code tests/test_wechatmp_business_reply.py::test_passive_reply_non_anal_unauthorized_keeps_default_prompt -q
```

Expected: fail with missing helper functions.

- [ ] **Step 6: Implement passive-reply helpers**

Add near the existing reply helper functions in `channel/wechatmp/passive_reply.py`:

```python
def _is_activation_code_text(content: str) -> bool:
    try:
        from business.accounts.activation_service import is_activation_code_text

        return is_activation_code_text(content)
    except Exception:
        return False


def _activation_reply_for_result(result) -> str:
    key_map = {
        "activated": "reply.investment.activation_success",
        "invalid": "reply.investment.activation_invalid",
        "used": "reply.investment.activation_used",
        "expired": "reply.investment.activation_expired",
        "disabled": "reply.investment.activation_disabled",
    }
    status = str(getattr(result, "status", "") or "invalid")
    default = str(getattr(result, "message", "") or "激活失败，请稍后重试。")
    key = key_map.get(status, "reply.investment.activation_invalid")
    auth_end_at = getattr(result, "auth_end_at", None)
    auth_end_text = auth_end_at.strftime("%Y-%m-%d") if auth_end_at else ""
    return _reply_format(key, auth_end_at=auth_end_text, default=default)


def _redeem_activation_code_text(openid: str, content: str) -> str:
    try:
        from business.accounts.activation_service import redeem_activation_code

        return _activation_reply_for_result(redeem_activation_code(openid, content))
    except Exception as exc:
        logger.warning("[wechatmp] activation redeem failed: {}".format(exc))
        return _reply_text("reply.investment.activation_invalid", "激活失败：激活码不存在或格式不正确。")


def _verify_wechatmp_text_access(openid: str, content: str):
    try:
        from business.routing.router import parse_route
        from business.accounts.permission_service import verify_customer_access, verify_customer_business_access

        route = parse_route(content)
        if getattr(route, "matched", False):
            return verify_customer_business_access(openid, getattr(route, "service_type", None))
        return verify_customer_access(openid)
    except Exception as exc:
        logger.debug("[wechatmp] permission precheck failed: {}".format(exc))
        return None
```

- [ ] **Step 7: Wire helpers into `Query.POST`**

In `Query.POST`, immediately after:

```python
from_user = wechatmp_msg.from_user_id
content = wechatmp_msg.content
message_id = wechatmp_msg.msg_id
```

add:

```python
                if _is_activation_code_text(content):
                    replyPost = create_reply(_redeem_activation_code_text(from_user, content), msg)
                    return encrypt_func(replyPost.render())

                permission = _verify_wechatmp_text_access(from_user, content)
                if permission is not None and not getattr(permission, "allowed", False):
                    replyPost = create_reply(getattr(permission, "user_prompt", "") or _reply_text("reply.investment.unauthorized", "您暂未开通该服务，如需开通请联系服务人员。"), msg)
                    return encrypt_func(replyPost.render())
```

This intentionally runs before cached-result delivery so expired users cannot claim old results.

- [ ] **Step 8: Run passive-reply tests**

Run:

```powershell
python -m pytest tests/test_wechatmp_business_reply.py::test_passive_reply_redeems_anal_activation_code tests/test_wechatmp_business_reply.py::test_passive_reply_non_anal_unauthorized_keeps_default_prompt -q
```

Expected: pass.

---

### Task 3: Admin API for Generation, Listing, Disable, and Export

**Files:**
- Modify: `business/accounts/auth_service.py`
- Modify: `channel/web/investment_handlers.py`
- Modify: `channel/web/web_channel.py`
- Test: `tests/test_business_web_ui.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Write failing permission/API route tests**

Add to `tests/test_business.py`:

```python
def test_activation_code_permissions_are_available_to_admin_and_readonly(business_env):
    from business.accounts.auth_service import permissions_for_role

    assert "activation_codes.read" in permissions_for_role("admin")
    assert "activation_codes.write" in permissions_for_role("admin")
    assert "activation_codes.export" in permissions_for_role("admin")
    assert "activation_codes.read" in permissions_for_role("readonly")
    assert "activation_codes.write" not in permissions_for_role("readonly")
```

Add to `tests/test_business_web_ui.py`:

```python
def test_activation_code_api_routes_are_registered():
    from channel.web.investment_handlers import INVESTMENT_API_URLS

    urls = "\n".join(INVESTMENT_API_URLS)
    assert "/api/investment/activation-codes" in urls
    assert "/api/investment/activation-codes/(.*)/disable" in urls
    assert "/api/investment/export/activation-codes.xlsx" in urls
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_business.py::test_activation_code_permissions_are_available_to_admin_and_readonly tests/test_business_web_ui.py::test_activation_code_api_routes_are_registered -q
```

Expected: fail because permissions/routes do not exist.

- [ ] **Step 3: Add permissions and routes**

In `business/accounts/auth_service.py`, add to `ROLE_PERMISSIONS["admin"]`:

```python
        "activation_codes.read",
        "activation_codes.write",
        "activation_codes.export",
```

Add to `ROLE_PERMISSIONS["readonly"]`:

```python
        "activation_codes.read",
```

In `channel/web/investment_handlers.py`, add routes:

```python
    '/api/investment/export/activation-codes.xlsx', 'InvestmentActivationCodesExportHandler',
    '/api/investment/activation-codes/(.*)/disable', 'InvestmentActivationCodeDisableHandler',
    '/api/investment/activation-codes', 'InvestmentActivationCodesHandler',
```

- [ ] **Step 4: Add API handlers**

In `channel/web/web_channel.py`, add helper:

```python
def _activation_code_payload(row):
    return {
        "id": row.id,
        "batch_id": row.batch_id,
        "code_prefix": row.code_prefix,
        "allowed_services": [str(item) for item in (row.allowed_services or [])],
        "subscription_days": row.subscription_days,
        "code_expires_at": row.code_expires_at,
        "status": row.status,
        "used_by_openid": row.used_by_openid,
        "used_at": row.used_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "remark": row.remark,
    }
```

Add handler classes near `InvestmentUsersHandler`:

```python
class InvestmentActivationCodesHandler:
    def GET(self):
        _require_investment_permission("activation_codes.read")
        try:
            from business.accounts.activation_service import count_activation_codes, list_activation_codes

            params = web.input(status='', batch_id='', page='1', page_size='20')
            page, page_size = _investment_safe_pagination(params, 20)
            status = getattr(params, "status", "") or None
            batch_id = getattr(params, "batch_id", "") or None
            total = count_activation_codes(status=status, batch_id=batch_id)
            rows = list_activation_codes(status=status, batch_id=batch_id, page=page, page_size=page_size)
            return _investment_json_response({
                "status": "success",
                "codes": [_activation_code_payload(row) for row in rows],
                "pagination": _investment_pagination_payload(page, page_size, total),
            })
        except Exception as e:
            logger.error(f"[Investment] activation codes GET error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})

    def POST(self):
        admin = _require_investment_permission("activation_codes.write")
        try:
            from datetime import datetime
            from business.accounts.activation_service import generate_activation_codes

            body = _investment_json_body()
            count = int(body.get("count", 1) or 1)
            subscription_days = int(body.get("subscription_days", 30) or 30)
            code_expires_at = str(body.get("code_expires_at", "") or "").strip()
            if not code_expires_at:
                return _investment_json_response({"status": "error", "message": "code_expires_at required"})
            datetime.fromisoformat(code_expires_at)
            result = generate_activation_codes(
                count=count,
                allowed_services=body.get("allowed_services", ["全部"]),
                subscription_days=subscription_days,
                code_expires_at=code_expires_at,
                remark=str(body.get("remark", "") or ""),
                actor=admin,
            )
            _record_investment_operation(
                "activation_code.generate",
                "activation_code",
                result.batch_id,
                admin=admin,
                detail={"count": len(result.codes), "subscription_days": subscription_days, "code_expires_at": code_expires_at},
            )
            return _investment_json_response({"status": "success", "batch_id": result.batch_id, "codes": result.codes})
        except Exception as e:
            logger.error(f"[Investment] activation codes POST error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentActivationCodeDisableHandler:
    def POST(self, code_id):
        admin = _require_investment_permission("activation_codes.write")
        try:
            from business.accounts.activation_service import disable_activation_code

            if not disable_activation_code(int(code_id), actor=admin):
                return _investment_json_response({"status": "error", "message": "activation code cannot be disabled"})
            _record_investment_operation("activation_code.disable", "activation_code", str(code_id), admin=admin)
            return _investment_json_response({"status": "success"})
        except Exception as e:
            logger.error(f"[Investment] activation code disable error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})
```

For export, either create a simple XLSX exporter in `business/records/export_service.py` or return CSV-like XLSX using existing helpers. Minimum required handler:

```python
class InvestmentActivationCodesExportHandler:
    def GET(self):
        _require_investment_permission("activation_codes.export")
        try:
            from business.records.export_service import export_activation_codes_xlsx

            params = web.input(status='', batch_id='')
            return _investment_xlsx_response(
                export_activation_codes_xlsx(status=getattr(params, "status", "") or None, batch_id=getattr(params, "batch_id", "") or None),
                "investment-activation-codes.xlsx",
            )
        except Exception as e:
            logger.error(f"[Investment] activation codes export error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})
```

- [ ] **Step 5: Add export helper test and implementation**

Test in `tests/test_business.py`:

```python
def test_export_activation_codes_xlsx_contains_metadata_not_plain_codes(business_env):
    from datetime import datetime, timedelta, UTC
    from business.accounts.activation_service import generate_activation_codes
    from business.config.constants import ServiceType
    from business.records.export_service import export_activation_codes_xlsx

    batch = generate_activation_codes(
        count=1,
        allowed_services=[ServiceType.ALL],
        subscription_days=365,
        code_expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
        remark="export",
    )

    content = export_activation_codes_xlsx(batch_id=batch.batch_id)

    assert isinstance(content, bytes)
    assert batch.codes[0].encode("utf-8") not in content
```

Implementation in `business/records/export_service.py` should use the repository's existing XLSX creation helper style and export metadata columns only: `batch_id`, `code_prefix`, `allowed_services`, `subscription_days`, `code_expires_at`, `status`, `used_by_openid`, `used_at`, `created_at`, `remark`.

- [ ] **Step 6: Run Task 3 tests**

Run:

```powershell
python -m pytest tests/test_business.py::test_activation_code_permissions_are_available_to_admin_and_readonly tests/test_business.py::test_export_activation_codes_xlsx_contains_metadata_not_plain_codes tests/test_business_web_ui.py::test_activation_code_api_routes_are_registered -q
```

Expected: pass.

---

### Task 4: WebUI Activation-Code Panel

**Files:**
- Modify: `channel/web/static/js/console.js`
- Modify: `channel/web/static/css/console.css` only if existing classes are insufficient.
- Test: `tests/test_business_web_ui.py`

- [ ] **Step 1: Write failing UI wiring tests**

Add to `tests/test_business_web_ui.py`:

```python
def test_activation_codes_panel_is_available_in_user_management():
    js = open("channel/web/static/js/console.js", encoding="utf-8").read()

    assert "activation_codes.read" in js
    assert "activation-codes" in js
    assert "renderInvestmentActivationCodes" in js
    assert "openInvestmentActivationCodeDialog" in js
    assert "/api/investment/activation-codes" in js
    assert "ANAL-" in js
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
python -m pytest tests/test_business_web_ui.py::test_activation_codes_panel_is_available_in_user_management -q
```

Expected: fail because UI does not reference activation codes.

- [ ] **Step 3: Add panel state and navigation**

In `channel/web/static/js/console.js`:

- Extend `currentInvestmentUserPanel` valid values to include `activation-codes`.
- Add `activation_codes: {status: '', batch_id: '', page: '1', page_size: '20'}` to `investmentUserState.filters`.
- Add `activation_codes` pagination state.
- Add `activation_codes.read` to the `invest-users` view permissions.
- In `renderInvestmentUsers`, add a tab:

```javascript
${investmentCan('activation_codes.read') ? `<button class="investment-tab ${currentInvestmentUserPanel === 'activation-codes' ? 'active' : ''}" onclick="switchInvestmentUserPanel('activation-codes')">
    <i class="fas fa-ticket"></i><span>激活码</span>
</button>` : ''}
```

Route `currentInvestmentUserPanel === 'activation-codes'` to `renderInvestmentActivationCodes()`.

- [ ] **Step 4: Add list and generation dialog functions**

Add functions near the customer/admin user functions:

```javascript
async function renderInvestmentActivationCodes() {
    const root = investmentContentEl('investment-users-content');
    if (!root) return;
    investmentLoading(root);
    try {
        const filters = investmentUserState.filters.activation_codes;
        const query = new URLSearchParams(filters).toString();
        const data = await investmentFetchJson(`/api/investment/activation-codes?${query}`);
        investmentUserApplyPagination('activation_codes', data.pagination);
        const rows = data.codes || [];
        root.innerHTML = investmentTailwindHtml(`
            <div class="investment-panel">
                <div class="investment-toolbar">
                    <div class="investment-search-row">
                        ${investmentDropdown('invest-activation-status', [['', '全部状态'], ['unused', '未使用'], ['used', '已使用'], ['disabled', '已停用']], filters.status || '', '', 'value => { investmentUserState.filters.activation_codes.status = value; investmentUserState.filters.activation_codes.page = 1; renderInvestmentActivationCodes(); }')}
                        <label class="investment-field investment-search-field"><span>批次</span><input id="invest-activation-batch" type="text" value="${escapeHtml(filters.batch_id || '')}" placeholder="batch_id"></label>
                        ${investmentButton('fa-magnifying-glass', '查询', 'applyInvestmentActivationCodeSearch()', 'primary')}
                        ${investmentButton('fa-rotate-left', '清除搜索', 'clearInvestmentActivationCodeSearch()')}
                    </div>
                    <div class="investment-toolbar-actions">
                        ${investmentButtonIfCan('activation_codes.write', 'fa-plus', '生成激活码', 'openInvestmentActivationCodeDialog()', 'primary')}
                        ${investmentButtonIfCan('activation_codes.export', 'fa-download', '导出', 'exportInvestmentActivationCodes()', 'primary')}
                    </div>
                </div>
                ${renderInvestmentActivationCodesTable(rows)}
                ${renderInvestmentUserPagination('activation_codes', data.pagination)}
            </div>
        `);
    } catch (error) {
        investmentError(root, error);
    }
}

function renderInvestmentActivationCodesTable(rows = []) {
    return investmentTableWrap(`
        <table class="investment-table">
            <thead><tr><th>批次</th><th>码段</th><th>权限</th><th>订阅天数</th><th>激活码有效期</th><th>状态</th><th>使用用户</th><th>创建时间</th><th>操作</th></tr></thead>
            <tbody>
                ${rows.map(row => `
                    <tr>
                        <td>${escapeHtml(investmentMiddleEllipsis(row.batch_id || '', 10, 8))}</td>
                        <td><code>${escapeHtml(row.code_prefix || 'ANAL-')}</code></td>
                        <td>${escapeHtml(investmentCustomerServicesDisplay(row.allowed_services || []))}</td>
                        <td>${escapeHtml(row.subscription_days || '')}</td>
                        <td>${escapeHtml(investmentFormatBeijingTime(row.code_expires_at || ''))}</td>
                        <td>${escapeHtml(row.status || '')}</td>
                        <td>${escapeHtml(row.used_by_openid || '')}</td>
                        <td>${escapeHtml(investmentFormatBeijingTime(row.created_at || ''))}</td>
                        <td>${row.status === 'unused' ? investmentButtonIfCan('activation_codes.write', 'fa-ban', '停用', `disableInvestmentActivationCode(${Number(row.id)})`, 'danger') : ''}</td>
                    </tr>
                `).join('') || '<tr><td colspan="9" class="investment-empty">暂无激活码</td></tr>'}
            </tbody>
        </table>
    `);
}
```

Add modal, save, disable, export, and window bindings:

```javascript
function openInvestmentActivationCodeDialog() {
    const body = investmentTailwindHtml(`
        <div class="investment-form-grid">
            <label class="investment-field"><span>生成数量</span><input id="invest-activation-count" type="number" min="1" max="1000" value="10"></label>
            <label class="investment-field"><span>激活码有效期</span><input id="invest-activation-expires" type="datetime-local" value="${escapeHtml(investmentUtcToBeijingDatetimeLocal(investmentAddDays(investmentTodayDate(), 30)))}"></label>
            <label class="investment-field"><span>订阅天数</span><input id="invest-activation-days" type="number" min="1" value="30"></label>
            <label class="investment-field md:col-span-2"><span>备注</span><input id="invest-activation-remark" placeholder="批次说明"></label>
            <div class="investment-field md:col-span-2"><span>服务权限</span><div class="investment-check-grid">${investmentUserServiceChecks('invest-activation', {allowed_services: ['all']})}</div></div>
        </div>
        <div id="invest-activation-generated" class="investment-generated-codes hidden"></div>
        <div class="investment-modal-actions">
            ${investmentButtonIfCan('activation_codes.write', 'fa-ticket', '生成', 'generateInvestmentActivationCodes()', 'primary')}
            ${investmentButton('fa-xmark', '关闭', 'hideInvestmentModal()')}
        </div>
    `);
    showInvestmentModal('生成 ANAL- 激活码', body);
}

async function generateInvestmentActivationCodes() {
    const services = new Set();
    document.querySelectorAll('#invest-activation-services input[type="checkbox"], [id^="invest-activation-service-"]').forEach(input => {
        if (input.checked) services.add(input.dataset.serviceValue || input.value);
    });
    const payload = {
        count: Number(document.getElementById('invest-activation-count')?.value || 1),
        code_expires_at: investmentBeijingDatetimeLocalToUtc(document.getElementById('invest-activation-expires')?.value || ''),
        subscription_days: Number(document.getElementById('invest-activation-days')?.value || 30),
        allowed_services: Array.from(services),
        remark: document.getElementById('invest-activation-remark')?.value || '',
    };
    const data = await investmentFetchJson('/api/investment/activation-codes', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
    });
    const resultEl = document.getElementById('invest-activation-generated');
    if (resultEl) {
        resultEl.classList.remove('hidden');
        resultEl.innerHTML = `<textarea readonly rows="10">${escapeHtml((data.codes || []).join('\\n'))}</textarea>`;
    }
    showInvestmentToast('激活码已生成');
    await renderInvestmentActivationCodes();
}

async function disableInvestmentActivationCode(id) {
    const confirmed = await showInvestmentConfirmDialog({title: '停用激活码', message: '停用后该激活码不能再被使用。', confirmText: '停用', variant: 'danger'});
    if (!confirmed) return;
    await investmentFetchJson(`/api/investment/activation-codes/${encodeURIComponent(id)}/disable`, {method: 'POST'});
    showInvestmentToast('激活码已停用');
    await renderInvestmentActivationCodes();
}

function applyInvestmentActivationCodeSearch() {
    investmentUserState.filters.activation_codes.batch_id = document.getElementById('invest-activation-batch')?.value || '';
    investmentUserState.filters.activation_codes.page = 1;
    renderInvestmentActivationCodes();
}

function clearInvestmentActivationCodeSearch() {
    investmentUserState.filters.activation_codes = {status: '', batch_id: '', page: '1', page_size: '20'};
    renderInvestmentActivationCodes();
}

function exportInvestmentActivationCodes() {
    investmentDownload('/api/investment/export/activation-codes.xlsx', investmentUserState.filters.activation_codes);
}
```

- [ ] **Step 5: Run UI wiring test**

Run:

```powershell
python -m pytest tests/test_business_web_ui.py::test_activation_codes_panel_is_available_in_user_management -q
```

Expected: pass.

---

### Task 5: Integration Verification and Regression Coverage

**Files:**
- Modify tests only unless failures reveal defects.

- [ ] **Step 1: Run focused account tests**

Run:

```powershell
python -m pytest tests/test_business.py -q
```

Expected: pass. If existing unrelated failures appear, record them and run focused activation tests to isolate.

- [ ] **Step 2: Run focused WeChat passive-reply tests**

Run:

```powershell
python -m pytest tests/test_wechatmp_business_reply.py -q
```

Expected: pass.

- [ ] **Step 3: Run focused WebUI tests**

Run:

```powershell
python -m pytest tests/test_business_web_ui.py -q
```

Expected: pass.

- [ ] **Step 4: Run chain check if available**

Run:

```powershell
python -m pytest tests/test_wechatmp_chain_check.py -q
```

Expected: pass.

- [ ] **Step 5: Manual smoke sequence**

Use a local test database or existing business test harness:

1. Generate one `ANAL-` code from WebUI.
2. Send non-`ANAL-` text as an unknown `openid`; expect unauthorized prompt.
3. Send generated `ANAL-` code as same `openid`; expect success and new `customers` row.
4. Send `利率` or `转债` depending on code permissions; expect normal business flow or service-specific unauthorized.
5. Send same `ANAL-` code again from another `openid`; expect used-code failure.

---

## Execution Notes

- Follow TDD. Write the test, run it red, then implement.
- Do not revert existing working-tree edits. There are current changes in `business/config/reply_config.py`, `channel/web/chat.html`, `channel/web/static/css/console.css`, `channel/web/static/js/console.js`, `channel/wechatmp/passive_reply.py`, `tests/test_business_web_ui.py`, and `tests/test_wechatmp_business_reply.py`; work with them.
- Keep activation-code plaintext out of persistent storage and metadata exports.
- Use `ANAL-` as the only activation-code trigger. Do not support `COW-`.
- For passive replies, return WeChat text XML via `create_reply`; do not enqueue activation work.
