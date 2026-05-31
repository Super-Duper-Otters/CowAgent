# Investment Record Export Audit Timezone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make investment request records exportable by service, user OpenID/mobile, and Beijing-time ranges, ensure WeChat permission-denied attempts are recorded as business records, and present customer delivery status in a way administrators can act on.

**Architecture:** Centralize request-record filtering so list and export endpoints normalize service types, user filters, and Beijing-time date bounds consistently. Add a dedicated service type for permission-denied requests and record those attempts at the WeChat pre-check boundary before returning permission prompts. Keep technical warning details in record detail, but expose a simple delivery status for day-based operations.

**Tech Stack:** Python, web.py handlers in `channel/web/web_channel.py`, SQLAlchemy query builders in `business/investment/records.py` and `business/investment/export_service.py`, frontend JavaScript in `channel/web/static/js/console.js`, pytest.

---

## Implementation Status

Status: implemented and verified on 2026-05-31.

- Backend request listing/export now share safe service-type handling; unknown service types return empty results instead of widening to all records.
- Export supports full export, service type, customer/OpenID/mobile/name/institution, keyword/status, and Beijing-time date bounds.
- WeChat passive and active permission pre-check denials are recorded as `unauthorized_request`; retry dedupe keeps successful records idempotent and releases the key after write failures.
- Active reply pre-check exceptions now return a system-busy prompt and do not start generation.
- Admin record defaults use Beijing calendar dates; cache empty-date submission falls back to the Beijing current day.
- Request records expose business-facing generation and delivery states; detailed errors, warnings, audit fields, output files, and artifact audit stay in the drawer.
- Internal delivery marker is hidden from API-facing record fields and export.
- Verification passed:
  - `pytest tests/test_investment_business.py -q` -> `208 passed`
  - `pytest tests/test_wechatmp_investment_reply.py -q` -> `62 passed`
  - `pytest tests/test_investment_web_ui.py -q` -> `36 passed`

Subagent review findings were addressed before final verification:

- Added full-export UI and current/full export customer support.
- Added frontend `unauthorized_request` label and Beijing-time today helper.
- Fixed active permission/pre-check exception bypasses.
- Prevented internal delivery marker leakage in export.
- Kept table summaries business-friendly while preserving technical details in the drawer.

---

## Scope

- Fix export behavior for unknown `service_type`; unknown values must not broaden to full export.
- Support export combinations:
  - full export with no filters
  - by service type
  - by OpenID or mobile
  - by Beijing-time date range
  - any combination of service, user, and date range
- Record WeChat permission pre-check failures as failed request records with service type `unauthorized_request`.
- Interpret backend admin date filters as Beijing dates.
- Show administrators a business-level delivery state instead of low-level technical warnings:
  - `生成中`
  - `生成失败`
  - `待客户领取`
  - `已交付客户`
  - `交付失败`
  - `已生成，有提示`
- Default business-record views to the current Beijing date and treat record lists as daily work views.
- Do not change cache hit/write/invalidation logic.
- Do not change permission names: `records.read`, `records.export`, `cache.read`, `cache.write`.

## File Map

- Modify: `business/investment/constants.py`
  - Add `ServiceType.UNAUTHORIZED_REQUEST`, label `无权限请求`, and aliases.
- Modify: `business/investment/records.py`
  - Add reusable request-record filter construction for service/user/status/keyword/time filters.
  - Allow explicit `customer` filter against `openid`, `investment_users.mobile`, user name, and institution.
  - Add helpers to append delivery warnings and mark customer delivery success.
- Modify: `business/investment/export_service.py`
  - Reuse the same filter semantics as request listing.
  - Unknown `service_type` returns an empty workbook instead of full export.
- Modify: `channel/wechatmp/passive_reply_cache.py`
  - Preserve `request_id` with cached replies so customer delivery can be marked when the cached reply is actually returned.
- Modify: `channel/web/web_channel.py`
  - Add Beijing-time date bound helper.
  - Accept export `customer` parameter.
  - Use the same Beijing-time bounds for list and export.
- Modify: `channel/wechatmp/passive_reply.py`
  - Record permission pre-check failures before returning permission prompt.
- Modify: `channel/wechatmp/active_reply.py`
  - Record permission pre-check failures before returning permission prompt.
- Modify: `channel/web/static/js/console.js`
  - Add `无权限请求` service option where request records and export filters list services.
  - Add explicit OpenID/手机号 export field for range/month/quarter export modes.
  - Default request, cache, and audit daily filters to the current Beijing date.
  - Display delivery status as the primary success/failure signal for request records.
  - Keep full error details in the request detail drawer under administrator-facing sections.
- Test: `tests/test_investment_business.py`
  - Cover export filter combinations, unknown service safety, Beijing-time bounds, permission-denied record creation, and delivery status derivation.
- Test: `tests/test_investment_web_ui.py`
  - Cover frontend service/customer export controls, daily defaults, and delivery-status columns.
- Test: `tests/test_wechatmp_investment_reply.py`
  - Cover passive/active permission pre-check recording and passive customer delivery marking.

---

## Subagent Execution Strategy

Use `superpowers:subagent-driven-development` when implementing this plan. Dispatch one fresh implementation subagent per work package, then run a spec-compliance review and a code-quality review before moving to the next package. Do not run implementation subagents in parallel against overlapping files.

Suggested work packages:

1. **Backend filter/export package**
   - Owns: `business/investment/constants.py`, `business/investment/records.py`, `business/investment/export_service.py`, request/export portions of `channel/web/web_channel.py`, related tests in `tests/test_investment_business.py`.
   - Implements Tasks 1-4.

2. **WeChat permission and delivery package**
   - Owns: `channel/wechatmp/passive_reply.py`, `channel/wechatmp/active_reply.py`, `channel/wechatmp/passive_reply_cache.py`, `channel/wechatmp/wechatmp_channel.py`, related tests in `tests/test_wechatmp_investment_reply.py`.
   - Implements Task 5 and the WeChat/cache portions of Task 7.

3. **Frontend records/export daily-view package**
   - Owns: `channel/web/static/js/console.js`, optional styling in `channel/web/static/css/console.css`, related tests in `tests/test_investment_web_ui.py`.
   - Implements Task 6 and Task 8.

4. **Request delivery status integration package**
   - Owns: `business/investment/records.py`, request-detail rendering in `channel/web/static/js/console.js`, related business/UI tests.
   - Implements the record model and drawer portions of Task 7 after packages 2 and 3 are complete.

Coordination rule: package 4 depends on package 2 preserving `request_id` in passive cached replies and package 3 having the records drawer structure in place. Run it after those packages land.

---

## Task 1: Add Unauthorized Request Service Type

**Files:**
- Modify: `business/investment/constants.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing test**

Add:

```python
def test_unauthorized_request_service_type_is_normalized_and_labeled():
    from business.investment.constants import SERVICE_LABELS, ServiceType, normalize_service

    assert ServiceType.UNAUTHORIZED_REQUEST == "unauthorized_request"
    assert SERVICE_LABELS[ServiceType.UNAUTHORIZED_REQUEST] == "无权限请求"
    assert normalize_service("unauthorized_request") == ServiceType.UNAUTHORIZED_REQUEST
    assert normalize_service("无权限请求") == ServiceType.UNAUTHORIZED_REQUEST
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
$env:PYTHONPATH='C:\Users\Administrator\Documents\GitHub\CowAgent'
pytest tests/test_investment_business.py::test_unauthorized_request_service_type_is_normalized_and_labeled -q
```

Expected: fail because `ServiceType.UNAUTHORIZED_REQUEST` does not exist.

- [ ] **Step 3: Implement service type**

In `business/investment/constants.py`, update `ServiceType`:

```python
class ServiceType(StrEnum):
    TECHNICAL_ANALYSIS = "technical_analysis"
    RATE = "rate"
    CONVERTIBLE_BOND = "convertible_bond"
    UNAUTHORIZED_REQUEST = "unauthorized_request"
    UNMATCHED = "unmatched"
    ALL = "all"
```

Update `SERVICE_LABELS`:

```python
SERVICE_LABELS = {
    ServiceType.TECHNICAL_ANALYSIS: "技术分析",
    ServiceType.RATE: "利率",
    ServiceType.CONVERTIBLE_BOND: "转债",
    ServiceType.UNAUTHORIZED_REQUEST: "无权限请求",
    ServiceType.ALL: "全部",
}
```

Update `SERVICE_ALIASES`:

```python
SERVICE_ALIASES = {
    "technical_analysis": ServiceType.TECHNICAL_ANALYSIS,
    "技术分析": ServiceType.TECHNICAL_ANALYSIS,
    "rate": ServiceType.RATE,
    "利率": ServiceType.RATE,
    "convertible_bond": ServiceType.CONVERTIBLE_BOND,
    "转债": ServiceType.CONVERTIBLE_BOND,
    "cb": ServiceType.CONVERTIBLE_BOND,
    "unauthorized_request": ServiceType.UNAUTHORIZED_REQUEST,
    "无权限请求": ServiceType.UNAUTHORIZED_REQUEST,
    "all": ServiceType.ALL,
    "全部": ServiceType.ALL,
}
```

- [ ] **Step 4: Verify**

Run:

```powershell
$env:PYTHONPATH='C:\Users\Administrator\Documents\GitHub\CowAgent'
pytest tests/test_investment_business.py::test_unauthorized_request_service_type_is_normalized_and_labeled -q
```

Expected: pass.

---

## Task 2: Centralize Request Record Filtering

**Files:**
- Modify: `business/investment/records.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing user filter test**

Add:

```python
def test_request_records_page_filters_by_openid_or_mobile(investment_env):
    from business.investment.constants import ServiceType
    from business.investment.records import create_request_record, list_request_records_page, succeed_request_record
    from business.investment.user_service import create_user

    create_user("openid-a", name="Alice", mobile="13800000000", enabled=True, allowed_services=[ServiceType.ALL])
    create_user("openid-b", name="Bob", mobile="13900000000", enabled=True, allowed_services=[ServiceType.ALL])
    first = create_request_record("openid-a", "新易盛 技术分析", ServiceType.TECHNICAL_ANALYSIS)
    second = create_request_record("openid-b", "利率", ServiceType.RATE)
    succeed_request_record(first, output_files=["/tmp/a.png"], elapsed_ms=1)
    succeed_request_record(second, output_files=["/tmp/b.png"], elapsed_ms=1)

    by_openid, total_openid = list_request_records_page(page=1, page_size=20, customer="openid-a")
    by_mobile, total_mobile = list_request_records_page(page=1, page_size=20, customer="13900000000")

    assert total_openid == 1
    assert [record.openid for record in by_openid] == ["openid-a"]
    assert total_mobile == 1
    assert [record.openid for record in by_mobile] == ["openid-b"]
```

- [ ] **Step 2: Write failing unknown service test**

Add:

```python
def test_request_records_page_unknown_service_returns_empty(investment_env):
    from business.investment.constants import ServiceType
    from business.investment.records import create_request_record, list_request_records_page, succeed_request_record

    request_id = create_request_record("openid", "利率", ServiceType.RATE)
    succeed_request_record(request_id, output_files=["/tmp/rate.png"], elapsed_ms=1)

    records, total = list_request_records_page(page=1, page_size=20, service_type="unknown-service")

    assert records == []
    assert total == 0
```

- [ ] **Step 3: Run tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH='C:\Users\Administrator\Documents\GitHub\CowAgent'
pytest tests/test_investment_business.py -q -k "request_records_page_filters_by_openid_or_mobile or request_records_page_unknown_service_returns_empty"
```

Expected: the `customer` argument test fails before implementation.

- [ ] **Step 4: Add helper for service normalization**

In `business/investment/records.py`, add:

```python
def _service_condition(table, service_type: ServiceType | str | None):
    if service_type is None or str(service_type or "").strip() == "":
        return None, False
    normalized_service = normalize_service(service_type)
    valid_unmatched_inputs = {str(ServiceType.UNMATCHED), "unmatched"}
    if normalized_service == ServiceType.UNMATCHED and str(service_type) not in valid_unmatched_inputs:
        return None, True
    return table.c.service_type == str(normalized_service), False
```

- [ ] **Step 5: Add customer filter to request listing**

Change `list_request_records()` and `list_request_records_page()` signatures to accept `customer: str = ""`.

Inside `list_request_records_page()`, replace the service block with:

```python
    service_condition, impossible = _service_condition(table, service_type)
    if impossible:
        return [], 0
    if service_condition is not None:
        conditions.append(service_condition)
```

Add customer filtering after keyword filtering setup:

```python
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
```

- [ ] **Step 6: Verify**

Run:

```powershell
$env:PYTHONPATH='C:\Users\Administrator\Documents\GitHub\CowAgent'
pytest tests/test_investment_business.py -q -k "request_records_page_filters_by_openid_or_mobile or request_records_page_unknown_service_returns_empty"
```

Expected: pass.

---

## Task 3: Make Export Filters Safe and Composable

**Files:**
- Modify: `business/investment/export_service.py`
- Modify: `channel/web/web_channel.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing export composition tests**

Add:

```python
def test_export_request_records_xlsx_filters_by_service_customer_and_range(investment_env):
    from business.investment.constants import ServiceType
    from business.investment.db import connect
    from business.investment.export_service import export_request_records_xlsx
    from business.investment.records import create_request_record, succeed_request_record
    from business.investment.user_service import create_user

    create_user("openid-a", name="Alice", mobile="13800000000", enabled=True, allowed_services=[ServiceType.ALL])
    create_user("openid-b", name="Bob", mobile="13900000000", enabled=True, allowed_services=[ServiceType.ALL])
    included = create_request_record("openid-a", "新易盛 技术分析", ServiceType.TECHNICAL_ANALYSIS, stock_name="新易盛")
    wrong_service = create_request_record("openid-a", "利率", ServiceType.RATE)
    wrong_user = create_request_record("openid-b", "贵州茅台 技术分析", ServiceType.TECHNICAL_ANALYSIS)
    succeed_request_record(included, output_files=["/tmp/card.png"], elapsed_ms=1)
    succeed_request_record(wrong_service, output_files=["/tmp/rate.png"], elapsed_ms=1)
    succeed_request_record(wrong_user, output_files=["/tmp/other.png"], elapsed_ms=1)
    with connect() as conn:
        for request_id in [included, wrong_service, wrong_user]:
            conn.execute(
                text("update investment_request_records set created_at = '2026-05-10T08:00:00' where request_id = :request_id"),
                {"request_id": request_id},
            )

    rows = _xlsx_sheet_rows(
        export_request_records_xlsx(
            "2026-05-01T00:00:00",
            "2026-05-31T23:59:59",
            service_type=ServiceType.TECHNICAL_ANALYSIS,
            customer="13800000000",
        )
    )

    assert len(rows) == 2
    assert rows[1][1] == "openid-a"
    assert rows[1][4] == "新易盛 技术分析"
```

Add:

```python
def test_export_request_records_xlsx_unknown_service_returns_only_header(investment_env):
    from business.investment.constants import ServiceType
    from business.investment.export_service import export_request_records_xlsx
    from business.investment.records import create_request_record, succeed_request_record

    request_id = create_request_record("openid", "利率", ServiceType.RATE)
    succeed_request_record(request_id, output_files=["/tmp/rate.png"], elapsed_ms=1)

    rows = _xlsx_sheet_rows(export_request_records_xlsx("", "", service_type="unknown-service"))

    assert rows == [["请求时间", "OpenID", "客户姓名", "机构", "原始输入", "服务类型", "股票代码", "股票名称", "状态", "错误码", "错误原因", "缓存命中", "输出文件", "耗时毫秒", "程序版本", "模板版本"]]
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
$env:PYTHONPATH='C:\Users\Administrator\Documents\GitHub\CowAgent'
pytest tests/test_investment_business.py -q -k "export_request_records_xlsx_filters_by_service_customer_and_range or export_request_records_xlsx_unknown_service_returns_only_header"
```

Expected: customer argument and unknown-service behavior fail.

- [ ] **Step 3: Add `customer` to export service**

Change `export_request_records_xlsx()` signature:

```python
def export_request_records_xlsx(
    start_date: str,
    end_date: str,
    service_type: str | ServiceType | None = None,
    status: str | Status | None = None,
    keyword: str = "",
    customer: str = "",
) -> bytes:
```

Update service filtering:

```python
    if service_type:
        normalized = normalize_service(service_type)
        valid_unmatched_inputs = {str(ServiceType.UNMATCHED), "unmatched"}
        if normalized == ServiceType.UNMATCHED and str(service_type) not in valid_unmatched_inputs:
            return _workbook_bytes(REQUEST_HEADERS, [], "RequestRecords")
        stmt = stmt.where(table.c.service_type == str(normalized))
```

Add customer filtering:

```python
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
```

- [ ] **Step 4: Pass customer through export handler**

In `InvestmentRequestRecordsExportHandler.GET`, include `customer=''` in `web.input(...)`, then call:

```python
            data = export_request_records_xlsx(
                start_date,
                end_date,
                service_type=params.service_type or None,
                status=getattr(params, "status", "") or None,
                keyword=getattr(params, "keyword", "") or "",
                customer=getattr(params, "customer", "") or "",
            )
```

- [ ] **Step 5: Verify**

Run:

```powershell
$env:PYTHONPATH='C:\Users\Administrator\Documents\GitHub\CowAgent'
pytest tests/test_investment_business.py -q -k "export_request_records_xlsx_filters_by_service_customer_and_range or export_request_records_xlsx_unknown_service_returns_only_header or export_request_records_xlsx_filters_and_includes_audit_fields"
```

Expected: pass.

---

## Task 4: Interpret Admin Dates as Beijing Time

**Files:**
- Modify: `channel/web/web_channel.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing date-bound test**

Add:

```python
def test_investment_date_bound_treats_plain_dates_as_beijing_days():
    from channel.web.web_channel import _investment_date_bound

    assert _investment_date_bound("2026-05-31") == "2026-05-30T16:00:00"
    assert _investment_date_bound("2026-05-31", end=True) == "2026-05-31T15:59:59.999999"
    assert _investment_date_bound("2026-05-31T12:30:00") == "2026-05-31T12:30:00"
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
$env:PYTHONPATH='C:\Users\Administrator\Documents\GitHub\CowAgent'
pytest tests/test_investment_business.py::test_investment_date_bound_treats_plain_dates_as_beijing_days -q
```

Expected: fail because current helper returns local-looking `2026-05-31T00:00:00`.

- [ ] **Step 3: Implement Beijing conversion**

In `channel/web/web_channel.py`, import:

```python
from datetime import datetime, time
from zoneinfo import ZoneInfo
```

Replace `_investment_date_bound()` with:

```python
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def _investment_date_bound(value: str, end: bool = False) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "T" in text or " " in text:
        return text
    day = datetime.strptime(text, "%Y-%m-%d").date()
    local_time = time.max if end else time.min
    local_dt = datetime.combine(day, local_time, tzinfo=BEIJING_TZ)
    utc_dt = local_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return utc_dt.isoformat(timespec="microseconds" if end else "seconds")
```

- [ ] **Step 4: Verify list/export date behavior**

Run:

```powershell
$env:PYTHONPATH='C:\Users\Administrator\Documents\GitHub\CowAgent'
pytest tests/test_investment_business.py -q -k "investment_date_bound or export_request_records_xlsx_filters_and_includes_audit_fields"
```

Expected: pass. If existing export tests use UTC-style explicit timestamps, they continue to pass because explicit timestamps are returned unchanged.

---

## Task 5: Record WeChat Permission Pre-Check Failures

**Files:**
- Modify: `channel/wechatmp/passive_reply.py`
- Modify: `channel/wechatmp/active_reply.py`
- Test: `tests/test_wechatmp_investment_reply.py`

- [ ] **Step 1: Write failing helper tests**

Add:

```python
def test_passive_investment_permission_prompt_records_failed_precheck(monkeypatch):
    from business.investment.constants import ErrorCode, ServiceType
    from channel.wechatmp import passive_reply

    calls = []

    class Permission:
        allowed = False
        user_prompt = "无权限"
        detail = "missing service permission"
        error_code = ErrorCode.UNAUTHORIZED

    monkeypatch.setattr(passive_reply, "parse_route", None, raising=False)
    monkeypatch.setattr("business.investment.router.parse_route", lambda _content: type("Route", (), {"matched": True, "service_type": ServiceType.TECHNICAL_ANALYSIS})())
    monkeypatch.setattr("business.investment.user_service.verify_permission", lambda _openid, _service_type: Permission())
    monkeypatch.setattr("business.investment.records.create_request_record", lambda *args, **kwargs: calls.append((args, kwargs)) or "request-id")
    monkeypatch.setattr("business.investment.records.fail_request_record", lambda *args, **kwargs: calls.append((args, kwargs)))

    prompt = passive_reply._investment_permission_prompt("openid", "300502.SZ 技术分析")

    assert prompt == "无权限"
    assert calls[0][0][2] == ServiceType.UNAUTHORIZED_REQUEST
    assert calls[1][0][0] == "request-id"
    assert calls[1][0][1] == ErrorCode.UNAUTHORIZED
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
$env:PYTHONPATH='C:\Users\Administrator\Documents\GitHub\CowAgent'
pytest tests/test_wechatmp_investment_reply.py -q -k "permission_prompt_records_failed_precheck"
```

Expected: fail because no request record is created at pre-check.

- [ ] **Step 3: Add shared recorder helper in passive reply**

In `channel/wechatmp/passive_reply.py`, add:

```python
def _record_permission_denied_request(openid: str, content: str, permission) -> None:
    try:
        from business.investment.constants import ErrorCode, ServiceType
        from business.investment.records import create_request_record, fail_request_record

        request_id = create_request_record(openid, content, ServiceType.UNAUTHORIZED_REQUEST)
        fail_request_record(
            request_id,
            getattr(permission, "error_code", None) or ErrorCode.UNAUTHORIZED,
            getattr(permission, "user_prompt", "") or "",
            getattr(permission, "detail", "") or "permission denied before investment router",
            0,
        )
    except Exception as exc:
        logger.debug("[wechatmp] record permission denied request failed: {}".format(exc))
```

In `_investment_permission_prompt()`, before returning `permission.user_prompt`:

```python
        _record_permission_denied_request(openid, content, permission)
        return permission.user_prompt
```

In `_investment_user_access_prompt()`, before returning `permission.user_prompt`:

```python
        _record_permission_denied_request(openid, "", permission)
        return permission.user_prompt
```

- [ ] **Step 4: Mirror helper in active reply**

In `channel/wechatmp/active_reply.py`, add the same `_record_permission_denied_request()` helper and call it before returning permission prompts in `_investment_permission_prompt(openid, route)`.

- [ ] **Step 5: Verify**

Run:

```powershell
$env:PYTHONPATH='C:\Users\Administrator\Documents\GitHub\CowAgent'
pytest tests/test_wechatmp_investment_reply.py -q -k "permission_prompt_records_failed_precheck"
```

Expected: pass.

---

## Task 6: Update Web Export Controls

**Files:**
- Modify: `channel/web/static/js/console.js`
- Test: `tests/test_investment_web_ui.py`

- [ ] **Step 1: Write failing UI test**

Add:

```python
def test_investment_request_export_exposes_unauthorized_and_customer_filter():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    filters_body = _js_function_body(js, "renderInvestmentRecordsFilters")
    export_body = _js_function_body(js, "renderInvestmentRequestExportPanel")
    range_body = _js_function_body(js, "exportInvestmentRequestRecordsByRange")
    month_body = _js_function_body(js, "exportInvestmentRequestRecordsByMonth")
    quarter_body = _js_function_body(js, "exportInvestmentRequestRecordsByQuarter")

    assert "unauthorized_request" in filters_body
    assert "无权限请求" in filters_body
    assert "invest-export-customer" in export_body
    assert "customer: investmentExportCustomer()" in range_body
    assert "customer: investmentExportCustomer()" in month_body
    assert "customer: investmentExportCustomer()" in quarter_body
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
$env:PYTHONPATH='C:\Users\Administrator\Documents\GitHub\CowAgent'
pytest tests/test_investment_web_ui.py::test_investment_request_export_exposes_unauthorized_and_customer_filter -q
```

Expected: fail because UI does not yet expose the new service/customer export controls.

- [ ] **Step 3: Add export customer helper**

In `channel/web/static/js/console.js`, add after `investmentExportServiceType()`:

```javascript
function investmentExportCustomer() {
    return document.getElementById('invest-export-customer')?.value || '';
}
```

- [ ] **Step 4: Add service option and customer field**

In `renderInvestmentRequestExportPanel()`, add service option:

```javascript
<option value="unauthorized_request">无权限请求</option>
```

Add customer field:

```javascript
const customerField = investmentField('OpenID/手机号', 'invest-export-customer', '', 'text');
```

Include `${customerField}` in `range`, `month`, and `quarter` modes next to `${serviceField}`.

- [ ] **Step 5: Pass customer in export calls**

Update range/month/quarter export payloads:

```javascript
customer: investmentExportCustomer(),
```

Add unauthorized service option to request-record list filters:

```javascript
['unauthorized_request', '无权限请求']
```

- [ ] **Step 6: Verify**

Run:

```powershell
$env:PYTHONPATH='C:\Users\Administrator\Documents\GitHub\CowAgent'
pytest tests/test_investment_web_ui.py -q -k "request_export_exposes_unauthorized_and_customer_filter or request_export_panel"
```

Expected: pass.

---

## Task 7: Add Business-Level Delivery Status

**Files:**
- Modify: `business/investment/records.py`
- Modify: `channel/wechatmp/passive_reply_cache.py`
- Modify: `channel/wechatmp/wechatmp_channel.py`
- Modify: `channel/wechatmp/passive_reply.py`
- Modify: `channel/web/static/js/console.js`
- Test: `tests/test_investment_business.py`
- Test: `tests/test_wechatmp_investment_reply.py`
- Test: `tests/test_investment_web_ui.py`

- [ ] **Step 1: Write failing delivery status tests**

Add to `tests/test_investment_business.py`:

```python
def test_request_record_delivery_status_is_business_facing(investment_env):
    from business.investment.constants import ServiceType
    from business.investment.records import append_request_warning, create_request_record, get_request_record, mark_request_delivered, succeed_request_record

    pending = create_request_record("openid", "300502.SZ 技术分析", ServiceType.TECHNICAL_ANALYSIS)
    succeed_request_record(pending, output_files=["/tmp/card.png"], elapsed_ms=1)
    assert get_request_record(pending).delivery_status == "待客户领取"

    delivered = create_request_record("openid", "利率", ServiceType.RATE)
    succeed_request_record(delivered, output_files=["/tmp/rate.png"], elapsed_ms=1)
    mark_request_delivered(delivered)
    assert get_request_record(delivered).delivery_status == "已交付客户"

    failed = create_request_record("openid", "转债", ServiceType.CONVERTIBLE_BOND)
    succeed_request_record(failed, output_files=["/tmp/cb.png"], elapsed_ms=1)
    append_request_warning(failed, "图片上传失败：微信接口未授权")
    assert get_request_record(failed).delivery_status == "交付失败"
```

- [ ] **Step 2: Add delivery fields to `RequestRecord`**

In `business/investment/records.py`, extend `RequestRecord`:

```python
    delivery_status: str = ""
    delivery_detail: str = ""
```

Add helpers:

```python
DELIVERY_DELIVERED_MARKER = "[delivery:delivered]"
DELIVERY_FAILURE_KEYWORDS = ("图片上传失败", "图片发送失败", "图片读取失败", "微信接口未授权", "api unauthorized")


def mark_request_delivered(request_id: str) -> None:
    append_request_warning(request_id, DELIVERY_DELIVERED_MARKER)


def _delivery_status(status: Status, error_message: str, output_files: list[str]) -> tuple[str, str]:
    detail = (error_message or "").strip()
    if status == Status.GENERATING:
        return "生成中", ""
    if status == Status.FAILED:
        return "生成失败", detail
    if any(keyword in detail for keyword in DELIVERY_FAILURE_KEYWORDS):
        return "交付失败", detail
    if DELIVERY_DELIVERED_MARKER in detail:
        return "已交付客户", ""
    if output_files:
        clean_detail = detail.replace(DELIVERY_DELIVERED_MARKER, "").strip()
        if clean_detail:
            return "已生成，有提示", clean_detail
        return "待客户领取", ""
    return "已生成，有提示" if detail else "已交付客户", detail
```

In `_row_to_request()`, compute output files once and set delivery fields:

```python
    output_files = _load_list(item["output_files"])
    delivery_status, delivery_detail = _delivery_status(status, item["error_message"] or "", output_files)
```

Use `output_files=output_files`, `delivery_status=delivery_status`, and `delivery_detail=delivery_detail`.

- [ ] **Step 3: Preserve request ID in passive reply cache**

In `channel/wechatmp/passive_reply_cache.py`, extend `PassiveReplyResult`:

```python
    request_id: str = ""
```

Update `append_result()` and `append_reply()` signatures:

```python
def append_result(self, receiver, title, replies, service_type="", request_id=""):
def append_reply(self, receiver, reply_type, reply_content, title="", service_type="", request_id=""):
```

Persist `request_id` when creating/updating cached results and include it in `peek_result()`.

- [ ] **Step 4: Store request ID when caching WeChat replies**

In `channel/wechatmp/wechatmp_channel.py`, pass `investment_request_id` into every passive `append_reply()` call:

```python
self.cache_dict.append_reply(receiver, "image", media_id, cache_title, service_type=investment_service_type, request_id=investment_request_id)
```

Apply the same argument for text, voice, and video passive cached replies.

- [ ] **Step 5: Mark delivered when passive reply is actually returned**

In `channel/wechatmp/passive_reply.py`, add:

```python
def _mark_cached_result_delivered(cached_result):
    request_id = getattr(cached_result, "request_id", "")
    if not request_id:
        return
    try:
        from business.investment.records import mark_request_delivered

        mark_request_delivered(request_id)
    except Exception as exc:
        logger.debug("[wechatmp] mark investment request delivered failed: {}".format(exc))
```

Call `_mark_cached_result_delivered(pending_result)` immediately after `_render_cached_reply(...)` returns a non-`success` passive reply for image/text/voice/video.

- [ ] **Step 6: Replace record table warning wording with delivery status**

In `channel/web/static/js/console.js`, update `renderInvestmentRequestRecordsTable()` so the list uses `delivery_status` and `delivery_detail` instead of raw warning text:

```javascript
<td><span class="investment-badge ${investmentDeliveryStatusClass(record.delivery_status || record.status)}">${escapeHtml(record.delivery_status || investmentStatusLabel(record.status))}</span></td>
<td>${investmentRecordClamp(record.delivery_detail || record.user_prompt || record.error_code || '正常', 2, 54)}</td>
```

Add:

```javascript
function investmentDeliveryStatusClass(status) {
    if (status === '已交付客户') return 'ok';
    if (status === '交付失败' || status === '生成失败') return 'fail';
    if (status === '生成中' || status === '待客户领取') return 'warn';
    return '';
}
```

- [ ] **Step 7: Keep detailed errors in the request drawer**

Update `renderInvestmentRequestDrawer(record)` so the detail drawer keeps full troubleshooting detail but presents it as administrator-facing sections:

```javascript
function renderInvestmentRequestDrawer(record) {
    return `
        ${investmentDrawerSection('基础信息', investmentDrawerFacts([
            ['请求 ID', escapeHtml(record.request_id || '-')],
            ['客户', escapeHtml(record.customer_display || record.openid || '-')],
            ['OpenID', escapeHtml(record.openid || '-')],
            ['手机号', escapeHtml(record.customer_mobile || '-')],
            ['服务', investmentServiceLabel(record.service_type)],
            ['生成状态', investmentStatusLabel(record.status)],
            ['交付状态', escapeHtml(record.delivery_status || '-')],
            ['耗时', escapeHtml(record.elapsed_ms == null ? '-' : `${record.elapsed_ms} ms`)],
            ['北京时间', escapeHtml(investmentFormatBeijingTime(record.created_at) || '-')],
        ]))}
        ${investmentDrawerPre('原始输入', record.raw_input || '')}
        ${investmentDrawerPre('用户提示', record.user_prompt || '')}
        ${investmentDrawerPre('错误/警告详情', record.delivery_detail || record.status_warning || record.error_message || '')}
        ${investmentDrawerSection('审计字段', `<pre>${escapeHtml(JSON.stringify({
            customer_name: record.customer_name || '',
            institution: record.institution || '',
            normalized_target: record.normalized_target || '',
            stock_code: record.stock_code || '',
            stock_name: record.stock_name || '',
            market_date: record.market_date || '',
            cache_key: record.cache_key || '',
            cache_hit: Boolean(record.cache_hit),
            program_version: record.program_version || '',
            ta_version: record.ta_version || '',
            renderer_version: record.renderer_version || '',
            template_version: record.template_version || ''
        }, null, 2))}</pre>`)}
        ${investmentDrawerSection('输出文件', `<div class="investment-detail-links">${investmentFileLinks(record.output_files || [])}</div>`)}
        ${investmentDrawerSection('产物审计', investmentArtifactTable(record.output_artifacts || []))}
    `;
}
```

The list remains business-facing; the drawer is where technical details such as market-date inference, renderer details, or WeChat upload failures remain visible.

- [ ] **Step 8: Add UI test for drawer detail sections**

Add to `tests/test_investment_web_ui.py`:

```python
def test_investment_request_drawer_keeps_error_details_and_audit_fields():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    drawer_body = _js_function_body(js, "renderInvestmentRequestDrawer")

    assert "交付状态" in drawer_body
    assert "用户提示" in drawer_body
    assert "错误/警告详情" in drawer_body
    assert "审计字段" in drawer_body
    assert "产物审计" in drawer_body
    assert "record.delivery_detail || record.status_warning || record.error_message" in drawer_body
```

- [ ] **Step 9: Verify delivery behavior**

Run:

```powershell
$env:PYTHONPATH='C:\Users\Administrator\Documents\GitHub\CowAgent'
pytest tests/test_investment_business.py tests/test_wechatmp_investment_reply.py tests/test_investment_web_ui.py -q -k "delivery_status or delivered or request_records"
```

Expected: pass.

---

## Task 8: Default Record Lists to the Current Beijing Day

**Files:**
- Modify: `channel/web/static/js/console.js`
- Test: `tests/test_investment_web_ui.py`

- [ ] **Step 1: Write failing daily default UI test**

Add:

```python
def test_investment_records_default_to_beijing_today_filters():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    default_filters_body = _js_function_body(js, "investmentRecordsDefaultFilters")
    load_body = _js_function_body(js, "loadInvestmentRecordsTab")

    assert "investmentTodayDate()" in default_filters_body
    assert "start_date: today" in default_filters_body
    assert "end_date: today" in default_filters_body
    assert "market_date: today" in default_filters_body
    assert "investmentRecordsState.filters.cache.market_date = data.market_dates[0]" not in load_body
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
$env:PYTHONPATH='C:\Users\Administrator\Documents\GitHub\CowAgent'
pytest tests/test_investment_web_ui.py::test_investment_records_default_to_beijing_today_filters -q
```

Expected: fail because request/audit defaults do not include today and cache date is set after loading.

- [ ] **Step 3: Default request/cache/audit filters to today before API calls**

In `channel/web/static/js/console.js`, replace `investmentRecordsDefaultFilters(tab)` with:

```javascript
function investmentRecordsDefaultFilters(tab) {
    const today = investmentTodayDate();
    if (tab === 'cache') {
        return {page: '1', page_size: investmentRecordsDefaultPageSize(tab), market_date: today};
    }
    if (tab === 'requests' || tab === 'audits') {
        return {page: '1', page_size: investmentRecordsDefaultPageSize(tab), start_date: today, end_date: today};
    }
    return {page: '1', page_size: investmentRecordsDefaultPageSize(tab)};
}
```

Update the initial `investmentRecordsState.filters` object to call defaults after the helper is defined, or initialize it with `investmentTodayDate()` at startup:

```javascript
const investmentRecordsToday = investmentTodayDate();
```

Then:

```javascript
requests: {page: '1', page_size: '80', start_date: investmentRecordsToday, end_date: investmentRecordsToday},
cache: {page: '1', page_size: '120', market_date: investmentRecordsToday},
audits: {page: '1', page_size: '80', start_date: investmentRecordsToday, end_date: investmentRecordsToday},
```

- [ ] **Step 4: Remove post-load cache date mutation**

In `loadInvestmentRecordsTab()`, remove:

```javascript
if (!investmentRecordsState.filters.cache.market_date && data.market_dates?.[0]) {
    investmentRecordsState.filters.cache.market_date = data.market_dates[0];
}
```

The cache request must include `market_date` before the first API call.

- [ ] **Step 5: Verify daily defaults**

Run:

```powershell
$env:PYTHONPATH='C:\Users\Administrator\Documents\GitHub\CowAgent'
pytest tests/test_investment_web_ui.py -q -k "default_to_beijing_today_filters or cache_category_selection or records_filters"
```

Expected: pass.

---

## Final Verification

- [ ] **Step 1: Run focused business tests**

```powershell
$env:PYTHONPATH='C:\Users\Administrator\Documents\GitHub\CowAgent'
pytest tests/test_investment_business.py tests/test_wechatmp_investment_reply.py tests/test_investment_web_ui.py -q
```

Expected: all relevant tests pass.

- [ ] **Step 2: Manual API checks**

Use an authenticated admin session and verify these requests:

```text
GET /api/investment/export/requests.xlsx
GET /api/investment/export/requests.xlsx?service_type=technical_analysis
GET /api/investment/export/requests.xlsx?service_type=technical_analysis&customer=13800000000
GET /api/investment/export/requests.xlsx?customer=openid-a&start_date=2026-05-31&end_date=2026-05-31
GET /api/investment/export/requests.xlsx?service_type=unknown-service
GET /api/investment/records/requests?start_date=<today>&end_date=<today>
GET /api/investment/cache?market_date=<today>
```

Expected:

- No filters exports all request records.
- Service/customer/date filters compose by AND.
- Unknown service returns an Excel file with only the header row.
- Date-only filters match Beijing calendar days.
- Default record views request the current Beijing day before the first API call.

## Acceptance Criteria

- Export never broadens unknown `service_type` to full export.
- Request listing and request export use compatible service/customer/date semantics.
- Admin-selected dates are treated as Beijing calendar days.
- Request records show a business-facing delivery status, not raw market-date or renderer warning details.
- Request record details retain full troubleshooting fields: user prompt, delivery status, error/warning details, audit fields, and output artifact audit.
- Successful generation with customer delivery failure is visible as `交付失败`.
- Cache and request record pages default to the current Beijing day before loading data.
- WeChat permission pre-check denials appear in request records as `service_type=unauthorized_request`, `status=failed`, and `error_code=unauthorized` or the specific permission failure code.
- Full export remains possible by omitting all filters.
- Existing cache read/write/hit/invalidation behavior is unchanged.
