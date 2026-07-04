# Preregistered Customer Activation Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a preregistered-customer import flow where customers can be created before their WeChat `openid` is known, each valid unbound customer receives a customer-specific activation code, and redeeming that code binds the sender's `openid` to that customer.

**Architecture:** Keep generic activation codes and preregistered customer activation codes in the existing `activation_codes` table, separated by explicit mode and customer linkage fields. Preregistered codes carry the imported subscription end date and bind to a customer row; generic codes continue to use `subscription_days` from redemption time. The WebUI supports single-customer preregistration, batch import preview/commit, result Excel download, and openid unbinding.

**Tech Stack:** Python, web.py, SQLAlchemy Core, Alembic migrations, openpyxl, existing investment WebUI JavaScript/CSS, pytest.

---

## Current Code Map

- `business/schema/tables.py`: Add nullable customer binding fields and activation-code mode/linkage fields.
- `migrations/business/versions/20260630_0031_preregistered_customer_activation.py`: Migrate schema.
- `business/accounts/user_service.py`: Parse/import preregistered customers, create/update customers without fake openids, bind/unbind openids.
- `business/accounts/activation_service.py`: Generate customer-bound activation codes and redeem them through the preregistration path.
- `business/records/export_service.py`: Export import templates and committed import result workbooks with activation codes.
- `channel/web/investment_handlers.py`: Register new unbind and import-result routes.
- `channel/web/web_channel.py`: Extend customer API, import API, activation payloads, and unbind handler.
- `channel/web/static/js/console.js`: Update customer dialogs, import flow, table columns, activation-code displays, and unbind actions.
- `channel/web/static/css/console.css`: Add only small layout rules if current table/modal classes are insufficient.
- `channel/wechatmp/passive_reply.py`: Keep using existing activation-code redemption entrypoint; behavior changes should live in `activation_service`.
- `tests/test_business.py`: Unit/integration tests for import, customer-bound code generation, binding, and unbinding.
- `tests/test_business_web_ui.py`: Route and UI wiring tests.
- `tests/test_wechatmp_business_reply.py`: Passive-reply regression tests for preregistered redemption.

## Business Rules

- Preregistered customers are customers whose business identity is known but whose WeChat `openid` is not yet bound.
- Batch import and single-customer creation may create customers with empty `openid`.
- Do not generate `pending-mobile-*` openid values anymore.
- For preregistered customers, the activation code carries the imported subscription end date. Redemption sets the customer `auth_end_at` to that value.
- For generic activation codes, current behavior remains: redemption adds `subscription_days` from now or the current active end date.
- A preregistered activation code is bound to exactly one customer.
- A preregistered activation code can bind only if the linked customer has no current `openid`.
- If the linked customer already has the same `openid`, return an already-activated style success message without changing ownership.
- If the linked customer already has a different `openid`, reject redemption and ask the user to contact an administrator.
- Unbinding clears `openid` only; customer identity fields, service permissions, enabled state, and subscription dates remain.
- Used activation codes are never reused. Rebinding after unbind requires generating a new customer-bound code.
- Import result Excel must include plaintext codes for newly generated customer-bound codes, because sales need to distribute them.

---

### Task 1: Schema for Preregistered Customers and Customer-Bound Codes

**Files:**
- Modify: `business/schema/tables.py`
- Create: `migrations/business/versions/20260630_0031_preregistered_customer_activation.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Add failing schema tests**

Append to `tests/test_business.py`:

```python
def test_preregistered_customer_schema_fields_exist():
    from business.schema.tables import metadata

    customer_columns = metadata.tables["customers"].columns.keys()
    activation_columns = metadata.tables["activation_codes"].columns.keys()

    assert "bind_status" in customer_columns
    assert "bound_at" in customer_columns
    assert "unbound_at" in customer_columns
    assert "last_unbound_reason" in customer_columns
    assert "activation_mode" in activation_columns
    assert "customer_id" in activation_columns
    assert "subscription_start_at" in activation_columns
    assert "subscription_end_at" in activation_columns
```

- [ ] **Step 2: Run the schema test red**

Run:

```powershell
python -m pytest tests/test_business.py::test_preregistered_customer_schema_fields_exist -q
```

Expected: fail because the new fields do not exist.

- [ ] **Step 3: Extend SQLAlchemy table declarations**

In `business/schema/tables.py`, add these `customers` columns after `openid` or near subscription fields:

```python
Column("bind_status", Text, nullable=False, server_default="bound"),
Column("bound_at", Text),
Column("unbound_at", Text),
Column("last_unbound_by_admin_id", Integer),
Column("last_unbound_by_username", Text),
Column("last_unbound_reason", Text),
```

Add these `activation_codes` columns:

```python
Column("activation_mode", Text, nullable=False, server_default="generic"),
Column("customer_id", Integer),
Column("subscription_start_at", Text),
Column("subscription_end_at", Text),
Index("idx_activation_codes_customer", "customer_id", "status"),
Index("idx_activation_codes_mode", "activation_mode", "status"),
```

- [ ] **Step 4: Create migration**

Create `migrations/business/versions/20260630_0031_preregistered_customer_activation.py`:

```python
# encoding:utf-8
"""add preregistered customer activation fields"""

from alembic import op
import sqlalchemy as sa


revision = "20260630_0031"
down_revision = "20260630_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("bind_status", sa.Text(), nullable=False, server_default="bound"))
    op.add_column("customers", sa.Column("bound_at", sa.Text()))
    op.add_column("customers", sa.Column("unbound_at", sa.Text()))
    op.add_column("customers", sa.Column("last_unbound_by_admin_id", sa.Integer()))
    op.add_column("customers", sa.Column("last_unbound_by_username", sa.Text()))
    op.add_column("customers", sa.Column("last_unbound_reason", sa.Text()))

    op.add_column("activation_codes", sa.Column("activation_mode", sa.Text(), nullable=False, server_default="generic"))
    op.add_column("activation_codes", sa.Column("customer_id", sa.Integer()))
    op.add_column("activation_codes", sa.Column("subscription_start_at", sa.Text()))
    op.add_column("activation_codes", sa.Column("subscription_end_at", sa.Text()))
    op.create_index("idx_activation_codes_customer", "activation_codes", ["customer_id", "status"])
    op.create_index("idx_activation_codes_mode", "activation_codes", ["activation_mode", "status"])


def downgrade() -> None:
    op.drop_index("idx_activation_codes_mode", table_name="activation_codes")
    op.drop_index("idx_activation_codes_customer", table_name="activation_codes")
    op.drop_column("activation_codes", "subscription_end_at")
    op.drop_column("activation_codes", "subscription_start_at")
    op.drop_column("activation_codes", "customer_id")
    op.drop_column("activation_codes", "activation_mode")

    op.drop_column("customers", "last_unbound_reason")
    op.drop_column("customers", "last_unbound_by_username")
    op.drop_column("customers", "last_unbound_by_admin_id")
    op.drop_column("customers", "unbound_at")
    op.drop_column("customers", "bound_at")
    op.drop_column("customers", "bind_status")
```

- [ ] **Step 5: Run schema test green**

Run:

```powershell
python -m pytest tests/test_business.py::test_preregistered_customer_schema_fields_exist -q
```

Expected: pass.

---

### Task 2: Customer Service Supports Empty OpenID and Unbinding

**Files:**
- Modify: `business/accounts/user_service.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Add failing tests for preregistered create and unbind**

Append:

```python
def test_create_preregistered_customer_without_openid_and_unbind(business_env):
    from datetime import datetime, timedelta, UTC
    from business.accounts.user_service import (
        bind_customer_openid,
        create_user,
        get_user_by_openid,
        get_user_by_id,
        unbind_customer_openid,
    )
    from business.config.constants import ServiceType

    customer_id = create_user(
        "",
        name="张三",
        institution="示例机构",
        mobile="13800000000",
        allowed_services=[ServiceType.ALL],
        auth_start_at=datetime.now(UTC).replace(tzinfo=None),
        auth_end_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=180),
    )

    customer = get_user_by_id(customer_id)
    assert customer is not None
    assert customer.openid == ""
    assert customer.bind_status == "unbound"

    bind_customer_openid(customer_id, "openid-real")
    assert get_user_by_openid("openid-real").id == customer_id

    unbind_customer_openid(customer_id, reason="换绑")
    unbound = get_user_by_id(customer_id)
    assert unbound.openid == ""
    assert unbound.bind_status == "unbound"
    assert get_user_by_openid("openid-real") is None
```

- [ ] **Step 2: Run test red**

Run:

```powershell
python -m pytest tests/test_business.py::test_create_preregistered_customer_without_openid_and_unbind -q
```

Expected: fail because `get_user_by_id`, `bind_customer_openid`, `unbind_customer_openid`, and `bind_status` handling do not exist.

- [ ] **Step 3: Extend `User` dataclass and row mapping**

Add fields to `User` in `business/accounts/user_service.py`:

```python
bind_status: str = "bound"
bound_at: datetime | None = None
unbound_at: datetime | None = None
last_unbound_reason: str = ""
```

Update `_row_to_user` to read these fields, defaulting old rows to `"bound"` when `openid` is non-empty and `"unbound"` when empty.

- [ ] **Step 4: Allow `create_user` with empty openid**

Update `create_user` so `openid` may be an empty string. Set:

```python
"bind_status": "bound" if openid else "unbound",
"bound_at": now if openid else None,
```

When `openid` is empty, do not do a fallback lookup by `openid`; return the inserted primary key.

- [ ] **Step 5: Add lookup and binding helpers**

Implement:

```python
def get_user_by_id(user_id: int) -> User | None:
    ...

def bind_customer_openid(customer_id: int, openid: str, *, actor: Any | None = None) -> None:
    ...

def unbind_customer_openid(customer_id: int, *, actor: Any | None = None, reason: str = "") -> None:
    ...
```

Rules:
- `bind_customer_openid` must reject empty openid.
- `bind_customer_openid` must reject binding if another customer already has that openid.
- `unbind_customer_openid` clears openid and sets `bind_status = "unbound"`.
- Both helpers update audit actor fields through existing `_admin_actor_values`.

- [ ] **Step 6: Run test green**

Run:

```powershell
python -m pytest tests/test_business.py::test_create_preregistered_customer_without_openid_and_unbind -q
```

Expected: pass.

---

### Task 3: Parse and Import Customers Without Fake OpenIDs

**Files:**
- Modify: `business/accounts/user_service.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Add failing parse/import tests**

Append:

```python
def test_parse_users_excel_does_not_generate_pending_openid_for_blank_openid(tmp_path):
    from openpyxl import Workbook
    from business.accounts.user_service import parse_users_excel

    path = tmp_path / "users.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["手机号", "服务权限", "授权结束日期", "OpenID", "姓名"])
    sheet.append(["13800000000", "全部", "2026-12-31", "", "张三"])
    workbook.save(path)

    rows = parse_users_excel(path)

    assert rows[0].openid == ""
    assert rows[0].openid_generated is False


def test_import_users_creates_preregistered_customer_for_blank_openid(business_env):
    from datetime import datetime
    from business.accounts.user_service import ImportUserRow, import_users, list_users

    result = import_users([
        ImportUserRow(
            openid="",
            name="张三",
            mobile="13800000000",
            allowed_services="全部",
            auth_start_at=datetime(2026, 1, 1),
            auth_end_at=datetime(2026, 12, 31),
        )
    ])

    users = list_users(keyword="13800000000", keyword_field="mobile")
    assert result.created == 1
    assert users[0].openid == ""
    assert users[0].bind_status == "unbound"
```

- [ ] **Step 2: Run tests red**

Run:

```powershell
python -m pytest tests/test_business.py::test_parse_users_excel_does_not_generate_pending_openid_for_blank_openid tests/test_business.py::test_import_users_creates_preregistered_customer_for_blank_openid -q
```

Expected: fail because blank openids become `pending-mobile-*`.

- [ ] **Step 3: Remove fake openid generation from parsing**

In `parse_users_excel`, delete the `_generated_pending_openid` path. Keep `openid=""` when the cell is empty.

- [ ] **Step 4: Update import identity matching**

In `import_users`, when `row.openid` is non-empty, match by openid. When `row.openid` is empty, match by mobile if a single unbound customer exists with that mobile; otherwise create a new preregistered customer.

Use a helper:

```python
def get_unbound_user_by_mobile(mobile: str) -> User | None:
    ...
```

- [ ] **Step 5: Run import tests green**

Run:

```powershell
python -m pytest tests/test_business.py::test_parse_users_excel_does_not_generate_pending_openid_for_blank_openid tests/test_business.py::test_import_users_creates_preregistered_customer_for_blank_openid -q
```

Expected: pass.

---

### Task 4: Customer-Bound Activation Code Generation

**Files:**
- Modify: `business/accounts/activation_service.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Add failing tests for customer-bound code generation**

Append:

```python
def test_generate_customer_activation_code_carries_imported_subscription_end(business_env):
    from datetime import datetime, UTC
    from business.accounts.activation_service import generate_customer_activation_code, list_activation_codes
    from business.accounts.user_service import create_user
    from business.config.constants import ServiceType

    customer_id = create_user(
        "",
        name="张三",
        mobile="13800000000",
        allowed_services=[ServiceType.TECHNICAL_ANALYSIS],
        auth_start_at=datetime(2026, 1, 1),
        auth_end_at=datetime(2026, 12, 31),
    )

    result = generate_customer_activation_code(
        customer_id=customer_id,
        code_expires_at=datetime(2026, 12, 31),
    )

    rows = list_activation_codes(batch_id=result.batch_id)
    assert len(result.codes) == 1
    assert rows[0].activation_mode == "preregistered"
    assert rows[0].customer_id == customer_id
    assert rows[0].subscription_end_at.startswith("2026-12-31")
```

- [ ] **Step 2: Run test red**

Run:

```powershell
python -m pytest tests/test_business.py::test_generate_customer_activation_code_carries_imported_subscription_end -q
```

Expected: fail because the helper and payload fields do not exist.

- [ ] **Step 3: Extend activation row dataclass**

Add to `ActivationCodeRow`:

```python
activation_mode: str = "generic"
customer_id: int | None = None
subscription_start_at: str = ""
subscription_end_at: str = ""
```

Update `_row_to_activation`.

- [ ] **Step 4: Preserve generic generation behavior**

In `generate_activation_codes`, explicitly set:

```python
"activation_mode": "generic",
"customer_id": None,
"subscription_start_at": None,
"subscription_end_at": None,
```

- [ ] **Step 5: Implement customer-bound generation**

Add:

```python
def generate_customer_activation_code(
    *,
    customer_id: int,
    code_expires_at: datetime | str | None = None,
    remark: str = "",
    actor: Any | None = None,
) -> ActivationCodeBatch:
    ...
```

Rules:
- Load customer by id.
- Require `auth_end_at`.
- Use customer `allowed_services`.
- Store `activation_mode = "preregistered"`.
- Store `customer_id`.
- Store `subscription_start_at = customer.auth_start_at`.
- Store `subscription_end_at = customer.auth_end_at`.
- Set `subscription_days = 1` only as a compatibility value; preregistered redemption must not use it.
- If `code_expires_at` is omitted, use `customer.auth_end_at`.

- [ ] **Step 6: Run test green**

Run:

```powershell
python -m pytest tests/test_business.py::test_generate_customer_activation_code_carries_imported_subscription_end -q
```

Expected: pass.

---

### Task 5: Import Commit Generates Codes and Result Excel

**Files:**
- Modify: `business/accounts/user_service.py`
- Modify: `business/records/export_service.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Add failing service-level import-with-codes test**

Append:

```python
def test_import_users_with_activation_codes_returns_customer_codes(business_env):
    from datetime import datetime
    from business.accounts.user_service import ImportUserRow, import_users_with_activation_codes

    result = import_users_with_activation_codes([
        ImportUserRow(
            openid="",
            name="张三",
            mobile="13800000000",
            allowed_services="全部",
            auth_start_at=datetime(2026, 1, 1),
            auth_end_at=datetime(2026, 12, 31),
        )
    ])

    assert result.created == 1
    assert result.activation_created == 1
    assert result.rows[0].activation_code.startswith("ANAL-")
    assert result.rows[0].auth_end_at.date().isoformat() == "2026-12-31"
```

- [ ] **Step 2: Add failing Excel export test**

Append:

```python
def test_export_users_import_result_xlsx_contains_generated_activation_code(business_env):
    from datetime import datetime
    from openpyxl import load_workbook
    from io import BytesIO
    from business.accounts.user_service import ImportUserRow, import_users_with_activation_codes
    from business.records.export_service import export_users_import_result_xlsx

    result = import_users_with_activation_codes([
        ImportUserRow(
            openid="",
            name="张三",
            mobile="13800000000",
            allowed_services="全部",
            auth_start_at=datetime(2026, 1, 1),
            auth_end_at=datetime(2026, 12, 31),
        )
    ])

    workbook = load_workbook(BytesIO(export_users_import_result_xlsx(result.rows)))
    values = list(workbook.active.iter_rows(values_only=True))
    headers = values[0]
    data = values[1]

    assert "激活码" in headers
    assert data[headers.index("激活码")].startswith("ANAL-")
```

- [ ] **Step 3: Run tests red**

Run:

```powershell
python -m pytest tests/test_business.py::test_import_users_with_activation_codes_returns_customer_codes tests/test_business.py::test_export_users_import_result_xlsx_contains_generated_activation_code -q
```

Expected: fail because import result structures do not exist.

- [ ] **Step 4: Add import result dataclasses**

In `business/accounts/user_service.py` add:

```python
@dataclass
class ImportUserActivationRow:
    customer_id: int
    openid: str
    name: str
    institution: str
    mobile: str
    allowed_services: str
    auth_start_at: datetime | None
    auth_end_at: datetime | None
    activation_code: str = ""
    batch_id: str = ""
    action: str = ""
    error: str = ""


@dataclass
class ImportWithActivationResult:
    created: int = 0
    updated: int = 0
    activation_created: int = 0
    rows: list[ImportUserActivationRow] = field(default_factory=list)
```

- [ ] **Step 5: Implement `import_users_with_activation_codes`**

Rules:
- Reuse import validation/parsing.
- Create/update customers.
- For blank-openid or unbound customers, call `generate_customer_activation_code`.
- For rows with existing openid, do not create a preregistered activation code unless explicitly requested later.
- Include plaintext activation code in the returned row.
- Continue processing valid rows even if one row fails; put the error in that result row.

- [ ] **Step 6: Implement result workbook export**

In `business/records/export_service.py`, add headers:

```python
USER_IMPORT_RESULT_HEADERS = [
    "处理结果", "客户ID", "OpenID", "姓名", "机构", "手机号", "服务权限",
    "授权开始", "授权结束", "激活码", "激活码批次", "错误信息",
]
```

Add:

```python
def export_users_import_result_xlsx(rows) -> bytes:
    ...
```

- [ ] **Step 7: Run tests green**

Run:

```powershell
python -m pytest tests/test_business.py::test_import_users_with_activation_codes_returns_customer_codes tests/test_business.py::test_export_users_import_result_xlsx_contains_generated_activation_code -q
```

Expected: pass.

---

### Task 6: Redeem Customer-Bound Codes and Bind OpenID

**Files:**
- Modify: `business/accounts/activation_service.py`
- Test: `tests/test_business.py`
- Test: `tests/test_wechatmp_business_reply.py`

- [ ] **Step 1: Add failing service redemption tests**

Append:

```python
def test_redeem_preregistered_code_binds_openid_and_uses_imported_end_date(business_env):
    from datetime import datetime
    from business.accounts.activation_service import generate_customer_activation_code, redeem_activation_code
    from business.accounts.user_service import create_user, get_user_by_openid
    from business.config.constants import ServiceType

    customer_id = create_user(
        "",
        name="张三",
        mobile="13800000000",
        allowed_services=[ServiceType.ALL],
        auth_start_at=datetime(2026, 1, 1),
        auth_end_at=datetime(2026, 12, 31),
    )
    batch = generate_customer_activation_code(customer_id=customer_id, code_expires_at=datetime(2026, 12, 31))

    result = redeem_activation_code("openid-real", batch.codes[0])

    user = get_user_by_openid("openid-real")
    assert result.success is True
    assert user.id == customer_id
    assert user.auth_end_at.date().isoformat() == "2026-12-31"


def test_redeem_preregistered_code_rejects_second_openid_after_binding(business_env):
    from datetime import datetime
    from business.accounts.activation_service import generate_customer_activation_code, redeem_activation_code
    from business.accounts.user_service import create_user

    customer_id = create_user("", name="张三", mobile="13800000000", allowed_services="全部", auth_end_at=datetime(2026, 12, 31))
    batch = generate_customer_activation_code(customer_id=customer_id, code_expires_at=datetime(2026, 12, 31))

    assert redeem_activation_code("openid-a", batch.codes[0]).success is True
    second = redeem_activation_code("openid-b", batch.codes[0])

    assert second.success is False
    assert second.status in {"used", "already_bound"}
```

- [ ] **Step 2: Run tests red**

Run:

```powershell
python -m pytest tests/test_business.py::test_redeem_preregistered_code_binds_openid_and_uses_imported_end_date tests/test_business.py::test_redeem_preregistered_code_rejects_second_openid_after_binding -q
```

Expected: fail because redemption always uses generic subscription logic.

- [ ] **Step 3: Split redemption paths**

In `redeem_activation_code`, after loading the activation row:

```python
if item.get("activation_mode") == "preregistered":
    auth_end_at = _redeem_preregistered_activation(conn, openid, item, now_dt, now)
else:
    auth_end_at = _upsert_customer_for_activation(conn, openid, item, now_dt, now)
```

- [ ] **Step 4: Implement preregistered redemption helper**

Add `_redeem_preregistered_activation`:

- Load linked customer by `customer_id`.
- Reject if customer does not exist.
- Reject if customer has a different non-empty openid.
- Bind the current openid if empty.
- Set `enabled = 1`.
- Set `allowed_services` from activation row or customer row.
- Set `auth_start_at` from `subscription_start_at` if present, otherwise customer value, otherwise now.
- Set `auth_end_at` from `subscription_end_at`. Do not calculate from `subscription_days`.
- Mark activation code used atomically as current code already does.

- [ ] **Step 5: Keep generic redemption unchanged**

Run the existing generic activation tests:

```powershell
python -m pytest tests/test_business.py -k "activation_code_redeem or activation_code_generation" -q
```

Expected: existing generic tests still pass.

- [ ] **Step 6: Add WeChat passive-reply regression test**

Append to `tests/test_wechatmp_business_reply.py`:

```python
def test_wechatmp_passive_preregistered_activation_binds_sender(business_env):
    from datetime import datetime
    from business.accounts.activation_service import generate_customer_activation_code
    from business.accounts.user_service import create_user, get_user_by_openid
    import channel.wechatmp.passive_reply as passive_reply

    customer_id = create_user("", name="张三", mobile="13800000000", allowed_services="全部", auth_end_at=datetime(2026, 12, 31))
    batch = generate_customer_activation_code(customer_id=customer_id, code_expires_at=datetime(2026, 12, 31))

    text = passive_reply._redeem_activation_code_text("openid-from-wechat", batch.codes[0])

    assert "激活成功" in text
    assert get_user_by_openid("openid-from-wechat").id == customer_id
```

- [ ] **Step 7: Run redemption tests green**

Run:

```powershell
python -m pytest tests/test_business.py::test_redeem_preregistered_code_binds_openid_and_uses_imported_end_date tests/test_business.py::test_redeem_preregistered_code_rejects_second_openid_after_binding tests/test_wechatmp_business_reply.py::test_wechatmp_passive_preregistered_activation_binds_sender -q
```

Expected: pass.

---

### Task 7: Web API for Single Create, Batch Import, Result Download, and Unbind

**Files:**
- Modify: `channel/web/investment_handlers.py`
- Modify: `channel/web/web_channel.py`
- Modify: `business/accounts/auth_service.py`
- Test: `tests/test_business_web_ui.py`

- [ ] **Step 1: Add failing route/permission tests**

Append to `tests/test_business_web_ui.py`:

```python
def test_preregistered_customer_routes_are_registered():
    from channel.web.investment_handlers import INVESTMENT_API_URLS

    urls = "\n".join(INVESTMENT_API_URLS)
    assert "/api/investment/users/(.*)/unbind-openid" in urls
    assert "/api/investment/users/import-result.xlsx" in urls
```

- [ ] **Step 2: Run test red**

Run:

```powershell
python -m pytest tests/test_business_web_ui.py::test_preregistered_customer_routes_are_registered -q
```

Expected: fail because routes do not exist.

- [ ] **Step 3: Add route declarations**

In `channel/web/investment_handlers.py`, add before generic user routes:

```python
'/api/investment/users/import-result.xlsx', 'InvestmentUsersImportResultHandler',
'/api/investment/users/(.*)/unbind-openid', 'InvestmentUserUnbindOpenidHandler',
```

- [ ] **Step 4: Add customer payload fields**

In `InvestmentUsersHandler.GET`, include:

```python
"bind_status": user.bind_status,
"bound_at": user.bound_at.isoformat() if user.bound_at else "",
"unbound_at": user.unbound_at.isoformat() if user.unbound_at else "",
```

- [ ] **Step 5: Let `InvestmentUsersHandler.POST` create preregistered users**

Change validation:
- `openid` is optional.
- `mobile`, `allowed_services`, and `auth_end_at` are required.
- If openid is empty, create preregistered customer and call `generate_customer_activation_code`.
- Return `activation_code` and `activation_batch_id` in the response for preregistered creation.

- [ ] **Step 6: Update import handler to generate codes on commit**

In `InvestmentUsersImportHandler.POST`:
- Preview mode continues to parse rows and count valid rows.
- Commit mode calls `import_users_with_activation_codes`.
- Store the latest import result rows in a server-side short-lived file under business storage or `tmp`.
- Return `result_download_url`.
- Return counts: `parsed`, `created`, `updated`, `activation_created`, `failed`.

- [ ] **Step 7: Add import result download handler**

Implement `InvestmentUsersImportResultHandler.GET`:
- Require `customers.import`.
- Read `batch_id` or `result_id` from query.
- Return `export_users_import_result_xlsx(...)`.

- [ ] **Step 8: Add unbind handler**

Implement `InvestmentUserUnbindOpenidHandler.POST`:
- Require `customers.write` or a new `customers.unbind` permission.
- Parse `customer_id` or route id.
- Call `unbind_customer_openid`.
- Record operation audit with before/after customer snapshots.

- [ ] **Step 9: Run route/API tests**

Run:

```powershell
python -m pytest tests/test_business_web_ui.py::test_preregistered_customer_routes_are_registered -q
```

Expected: pass.

---

### Task 8: WebUI Customer Import and Binding Controls

**Files:**
- Modify: `channel/web/static/js/console.js`
- Modify: `channel/web/static/css/console.css`
- Test: `tests/test_business_web_ui.py`

- [ ] **Step 1: Add failing UI wiring test**

Append:

```python
def test_preregistered_customer_ui_wiring_exists():
    js = open("channel/web/static/js/console.js", encoding="utf-8").read()

    assert "bind_status" in js
    assert "待绑定" in js
    assert "unbindInvestmentUserOpenid" in js
    assert "import-result.xlsx" in js
    assert "activation_code" in js
    assert "OpenID 可空" in js
```

- [ ] **Step 2: Run UI test red**

Run:

```powershell
python -m pytest tests/test_business_web_ui.py::test_preregistered_customer_ui_wiring_exists -q
```

Expected: fail until UI is updated.

- [ ] **Step 3: Update customer list**

In `renderInvestmentUsersTable`:
- Add a `绑定状态` column.
- Show `待绑定` when `bind_status === "unbound"` or openid is empty.
- Show full/openid-short display only for bound users.
- Add `解除绑定` button for bound users with non-empty openid.

- [ ] **Step 4: Update single-customer dialog**

In `openInvestmentUserDialog`:
- Label OpenID as `OpenID（可空）`.
- Add helper text: blank openid will create a preregistered customer and return an activation code.
- Keep service/date controls unchanged.

In `saveInvestmentUser`:
- Do not block blank openid.
- Require mobile and auth end date.
- If response has `activation_code`, show it in a readonly textarea and do not close modal immediately.

- [ ] **Step 5: Update batch import dialog**

In `renderInvestmentUserImportSection`:
- Update template description: `OpenID 可空，空值会生成客户专属激活码`.
- Preview should include a `激活码处理` or `绑定方式` column.

In `renderInvestmentImportResult`:
- Show `activation_created`.
- After committed import, render a download button using `result_download_url`.
- Preview table includes `激活码` when committed.

- [ ] **Step 6: Add unbind function**

Add:

```javascript
async function unbindInvestmentUserOpenid(customerId) {
    const confirmed = await showInvestmentConfirmDialog({
        title: '解除 OpenID 绑定',
        message: '解除后该微信用户将立即失去客户权限，客户资料和订阅日期会保留。',
        confirmText: '解除绑定',
        variant: 'danger',
    });
    if (!confirmed) return;
    await investmentFetchJson(`/api/investment/users/${encodeURIComponent(customerId)}/unbind-openid`, {method: 'POST'});
    showInvestmentToast('OpenID 绑定已解除');
    await renderInvestmentUsers();
}
```

Bind it on `window`.

- [ ] **Step 7: Run UI wiring test green**

Run:

```powershell
python -m pytest tests/test_business_web_ui.py::test_preregistered_customer_ui_wiring_exists -q
```

Expected: pass.

---

### Task 9: Activation-Code List and Export Clarity

**Files:**
- Modify: `channel/web/web_channel.py`
- Modify: `business/records/export_service.py`
- Modify: `channel/web/static/js/console.js`
- Test: `tests/test_business.py`
- Test: `tests/test_business_web_ui.py`

- [ ] **Step 1: Add failing export/payload tests**

Append:

```python
def test_activation_code_export_marks_preregistered_customer_codes(business_env):
    from datetime import datetime
    from openpyxl import load_workbook
    from io import BytesIO
    from business.accounts.activation_service import generate_customer_activation_code
    from business.accounts.user_service import create_user
    from business.records.export_service import export_activation_codes_xlsx

    customer_id = create_user("", name="张三", mobile="13800000000", allowed_services="全部", auth_end_at=datetime(2026, 12, 31))
    generate_customer_activation_code(customer_id=customer_id, code_expires_at=datetime(2026, 12, 31))

    workbook = load_workbook(BytesIO(export_activation_codes_xlsx()))
    values = list(workbook.active.iter_rows(values_only=True))

    assert "activation_mode" in values[0]
    assert "customer_id" in values[0]
    assert "subscription_end_at" in values[0]
    assert values[1][values[0].index("activation_mode")] == "preregistered"
```

- [ ] **Step 2: Run test red**

Run:

```powershell
python -m pytest tests/test_business.py::test_activation_code_export_marks_preregistered_customer_codes -q
```

Expected: fail until export includes new fields.

- [ ] **Step 3: Extend activation code payload**

In `_activation_code_payload`, include:

```python
"activation_mode": row.activation_mode,
"customer_id": row.customer_id,
"subscription_start_at": row.subscription_start_at,
"subscription_end_at": row.subscription_end_at,
```

- [ ] **Step 4: Extend activation-code Excel export**

Add export columns:
- `activation_mode`
- `customer_id`
- `subscription_start_at`
- `subscription_end_at`

Keep plaintext code export behavior as currently intended for admin sales distribution.

- [ ] **Step 5: Update activation-code UI table**

In `renderInvestmentActivationCodesTable`:
- Add `类型` column: `通用码` or `客户码`.
- Add `客户ID` or linked customer display.
- For preregistered rows, show `subscription_end_at` as subscription end.
- For generic rows, keep `subscription_days`.

- [ ] **Step 6: Run export test green**

Run:

```powershell
python -m pytest tests/test_business.py::test_activation_code_export_marks_preregistered_customer_codes -q
```

Expected: pass.

---

### Task 10: Focused Verification

**Files:**
- Modify tests only if defects are found.

- [ ] **Step 1: Run account and activation tests**

Run:

```powershell
python -m pytest tests/test_business.py -k "user or activation or import" -q
```

Expected: pass.

- [ ] **Step 2: Run WeChat passive reply tests**

Run:

```powershell
python -m pytest tests/test_wechatmp_business_reply.py -k "activation or permission" -q
```

Expected: pass.

- [ ] **Step 3: Run WebUI tests**

Run:

```powershell
python -m pytest tests/test_business_web_ui.py -q
```

Expected: pass.

- [ ] **Step 4: Run migration check**

Run:

```powershell
python -m pytest tests/test_business.py -k "migration or schema" -q
```

Expected: pass.

- [ ] **Step 5: Manual smoke test**

Use a local admin session and WeChat passive-reply test path:

1. Create one customer with mobile, services, and `auth_end_at = 2026-12-31`, leaving OpenID blank.
2. Confirm the API/UI returns an `ANAL-` activation code.
3. Send the code from `openid-a`.
4. Confirm the customer row now has `openid-a` and `auth_end_at = 2026-12-31`.
5. Try the same code from `openid-b`; expect used/already-bound failure.
6. Unbind the customer in WebUI.
7. Confirm `openid-a` no longer has access.
8. Generate a new customer-bound code and activate from `openid-b`.
9. Confirm the same customer is now bound to `openid-b`.

---

## Execution Notes

- Keep generic activation code behavior backward-compatible.
- Treat blank `openid` as the only preregistration signal.
- Do not write fake openids such as `pending-mobile-*`.
- Do not reuse used activation codes for rebinding.
- Customer-bound activation code redemption must use `subscription_end_at`, not `subscription_days`.
- Prefer adding focused helpers in `user_service.py` and `activation_service.py` over duplicating binding logic in web handlers.
- Keep operation audit records for import, single preregistration, activation-code generation, and unbinding.
