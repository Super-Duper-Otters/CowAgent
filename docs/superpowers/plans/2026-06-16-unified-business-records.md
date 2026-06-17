# Unified Business Records Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make公众号 and后台 web share one business workflow record table while preserving entry distinctions and improving backend web links.

**Architecture:** `request_records` becomes the single business-record table for公众号,后台 web, and system-triggered work. `entry_type`, `actor_type`, and `action_type` identify where the workflow entered and what it did; `internal_call_records` becomes legacy-only and no new code writes to it. Backend web APIs and UI use the unified records endpoint with entry filters and deep links.

**Tech Stack:** Python, SQLAlchemy table metadata, web.py handlers, vanilla JavaScript console UI, pytest.

---

### Task 1: Regression Tests for Unified Records

**Files:**
- Modify: `tests/test_investment_business.py`
- Modify: `tests/test_investment_web_ui.py`

- [ ] **Step 1: Write failing backend-generation business-record test**

Add a test proving后台 content generation writes a `request_records` row with `entry_type=internal_call`, does not require `internal_call_records`, and links AI audit to the new request id.

Run: `pytest tests/test_investment_business.py::test_daily_content_generation_records_backend_entry_in_business_records -q`

Expected before implementation: FAIL because generation currently writes only `internal_call_records`.

- [ ] **Step 2: Write failing unified records API/UI test**

Add tests proving `/api/investment/records/requests?entry_type=internal_call` returns后台 records, the legacy `/api/investment/records/internal-calls` redirects or aliases to unified records, and the frontend has direct links for both公众号入口 and后台入口 filters.

Run: `pytest tests/test_investment_business.py::test_business_records_api_filters_entry_type_and_internal_calls_alias -q tests/test_investment_web_ui.py::test_investment_records_page_links_to_entry_filtered_business_records -q`

Expected before implementation: FAIL because request-record filtering has no `entry_type` filter and frontend still uses `backendRequests`.

### Task 2: Backend Record Writer

**Files:**
- Modify: `business/investment/records.py`
- Modify: `business/investment/business_records.py`
- Modify: `business/investment/daily_content.py`
- Modify: `business/investment/ai_generation_audit.py`

- [ ] **Step 1: Add backend business-record creation helper**

Add a helper that inserts into `request_records` with `entry_type=internal_call`, empty `openid`, `actor_type=admin/system`, `raw_input=input_text`, and supports `input_prompt` through AI audit.

- [ ] **Step 2: Use the helper in daily content generation**

Replace `start_internal_call_record` / `finish_internal_call_record` writes in `generate_content()` with unified business-record start/finish calls. Keep `content_records` status behavior unchanged.

- [ ] **Step 3: Link AI audits to unified request ids**

When daily content starts AI audit, write `business_record_type="request"` and `business_record_id=<request_id>`.

### Task 3: Query and API Unification

**Files:**
- Modify: `business/investment/records.py`
- Modify: `channel/web/web_channel.py`

- [ ] **Step 1: Add `entry_type` filtering to business-record queries**

Extend `list_request_records_page()` and condition builder with `entry_type`. Preserve existing filters.

- [ ] **Step 2: Update request records API**

Accept `entry_type` query param and return records for both external and internal entries from `request_records`.

- [ ] **Step 3: Make internal-calls API a compatibility alias**

Keep `/api/investment/records/internal-calls` usable, but serve it from `request_records?entry_type=internal_call` so old links keep working.

### Task 4: Backend Web Links and UI

**Files:**
- Modify: `channel/web/static/js/console.js`

- [ ] **Step 1: Rename the records workspace**

Show a unified “业务请求” records area with entry-specific tabs or links for “公众号入口” and “后台入口”.

- [ ] **Step 2: Update API calls**

Use `/api/investment/records/requests?entry_type=external_request` for公众号入口 and `/api/investment/records/requests?entry_type=internal_call` for后台入口. Keep old internal-calls endpoint only as compatibility.

- [ ] **Step 3: Improve detail links**

Backend records should open the same drawer via `request_id`, display `entry_type`, `actor_type`, `actor_name`, `action_type`, source content id when present, outputs, and AI audit status where already available.

### Task 5: Legacy Table Compatibility and Verification

**Files:**
- Modify: `tests/test_investment_business.py`
- Optional migration follow-up: new Alembic migration only if the codebase needs physical table removal now.

- [ ] **Step 1: Do not physically drop `internal_call_records` in this pass**

Stop new writes first. Leave the table as legacy storage to avoid a destructive migration while current worktree has broad pending changes.

- [ ] **Step 2: Run targeted tests**

Run:

```powershell
pytest tests/test_investment_business.py::test_daily_content_generation_records_backend_entry_in_business_records -q
pytest tests/test_investment_business.py::test_business_records_api_filters_entry_type_and_internal_calls_alias -q
pytest tests/test_investment_web_ui.py::test_investment_records_page_links_to_entry_filtered_business_records -q
pytest tests/test_wechatmp_investment_reply.py::test_wechatmp_investment_success_returns_image_reply -q
```

- [ ] **Step 3: Run focused regression file if time permits**

Run:

```powershell
pytest tests/test_investment_business.py tests/test_investment_web_ui.py -q
```

