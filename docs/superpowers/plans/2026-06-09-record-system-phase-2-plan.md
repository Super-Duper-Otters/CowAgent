# Record System Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete concise field naming and add full business event records for WeChat requests, back-office generation, and operation audits.

**Architecture:** Keep `request_records` and `content_records` as the current state tables. Add append-only `request_events` and `generation_records` tables for replayable history. Rename fields with Alembic while keeping Python compatibility properties and API output stable until UI callers are migrated.

**Tech Stack:** Python 3.12, SQLAlchemy Core, Alembic, PostgreSQL, pytest, web.py, WeChat passive reply handlers.

---

## File Map

- Modify: `business/investment/schema.py` for new tables and concise column names.
- Create: `migrations/investment/versions/20260609_0017_record_system_phase_2.py` for column renames and new tables.
- Create: `business/investment/event_service.py` for request event writes and reads.
- Create: `business/investment/generation_records.py` for back-office generation call records.
- Modify: `business/investment/records.py` to emit core request lifecycle events.
- Modify: `business/investment/daily_content.py` to create generation records for back-office generation.
- Modify: `channel/wechatmp/passive_reply.py` and `channel/wechatmp/wechatmp_channel.py` to record customer confirmation, cancellation, text/image delivery and failures.
- Modify: `business/investment/audit_service.py` to use final operation categories.
- Modify: `tests/test_investment_business.py` and `tests/test_wechatmp_investment_reply.py` for TDD coverage.

## Task 1: Add Append-Only Request Events

**Files:**
- Modify: `business/investment/schema.py`
- Create: `business/investment/event_service.py`
- Create: `migrations/investment/versions/20260609_0017_record_system_phase_2.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing schema/service tests**

Add tests that assert `request_events` exists and `record_request_event()` stores one event with `request_id`, `openid`, `event_type`, `message_type`, `content`, `file_path`, `result`, and `created_at`.

- [ ] **Step 2: Run test to verify RED**

Run: `py -m pytest tests/test_investment_business.py::test_request_events_record_customer_request_lifecycle -q`

Expected: FAIL because `business.investment.event_service` or `request_events` does not exist.

- [ ] **Step 3: Add schema, migration, service**

Create `request_events` with columns:

`event_id, request_id, openid, channel, event_type, message_type, content, media_id, file_path, source_type, source_id, result, error, created_at`

Add indexes:

`idx_request_events_request_created`, `idx_request_events_openid_created`, `idx_request_events_type_created`

- [ ] **Step 4: Run test to verify GREEN**

Run the same test and expect PASS.

## Task 2: Emit Core Request Lifecycle Events

**Files:**
- Modify: `business/investment/records.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing lifecycle tests**

Assert:

- `create_request_record()` emits `request_received`.
- `succeed_request_record()` emits `generation_success`.
- `fail_request_record()` emits `generation_failed`.
- `mark_request_delivered()` emits `delivery_success`.

- [ ] **Step 2: Run RED**

Run the focused tests and confirm missing events.

- [ ] **Step 3: Implement lifecycle event writes**

Call `record_request_event()` after successful state changes. Do not let event write failure break the main business update.

- [ ] **Step 4: Run GREEN**

Run focused tests and `tests/test_investment_business.py`.

## Task 3: Add Back-Office Generation Records

**Files:**
- Modify: `business/investment/schema.py`
- Create: `business/investment/generation_records.py`
- Modify: `migrations/investment/versions/20260609_0017_record_system_phase_2.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing generation record tests**

Assert back-office generation stores:

`generation_id, content_id, service, operator_id, operator_name, operator_role, input_text, sources, result, error_code, error, output_text, outputs, elapsed_ms, created_at, updated_at`

- [ ] **Step 2: Run RED**

Run focused generation record tests and confirm failure.

- [ ] **Step 3: Add table and service**

Add `generation_records` with indexes:

`idx_generation_records_content_created`, `idx_generation_records_service_created`, `idx_generation_records_operator_created`

- [ ] **Step 4: Run GREEN**

Run focused tests and migration smoke test.

## Task 4: Connect Back-Office Generation Flow

**Files:**
- Modify: `business/investment/daily_content.py`
- Modify: `channel/web/web_channel.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing handler test**

Assert `InvestmentDailyContentGenerateHandler.POST()` creates a generation record with the session admin identity before the background task, and updates it to success/failure when the task completes.

- [ ] **Step 2: Run RED**

Run focused handler test and confirm missing generation record.

- [ ] **Step 3: Pass actor through generation**

Allow `generate_content(content_id, actor=admin)` and store the generation record from `mark_generation_started` through success/failure.

- [ ] **Step 4: Run GREEN**

Run focused handler tests and daily content generation tests.

## Task 5: Connect WeChat Multi-Reply Events

**Files:**
- Modify: `channel/wechatmp/passive_reply.py`
- Modify: `channel/wechatmp/wechatmp_channel.py`
- Test: `tests/test_wechatmp_investment_reply.py`

- [ ] **Step 1: Write failing WeChat event tests**

Assert:

- Customer reply `1` emits `customer_confirm`.
- Customer reply `0` emits `customer_cancel`.
- Pending prompt emits `pending_prompt_sent`.
- Text reply emits `reply_text_sent`.
- Image reply emits one `reply_image_sent` event per image.
- Delivery warning emits `delivery_failed`.

- [ ] **Step 2: Run RED**

Run focused WeChat tests and confirm missing events.

- [ ] **Step 3: Add event calls**

Use existing pending cached result `request_id` to bind all events to the original `request_records` row.

- [ ] **Step 4: Run GREEN**

Run `tests/test_wechatmp_investment_reply.py`.

## Task 6: Operation Audit Category Cleanup

**Files:**
- Modify: `business/investment/audit_service.py`
- Modify callers where needed
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing category tests**

Assert inferred categories are one of:

`customer, admin, skill, content, generation, config, cache, stock, export, health, system`

- [ ] **Step 2: Run RED**

Existing `backoffice` category should fail the new test.

- [ ] **Step 3: Implement category mapping**

Map action/target prefixes to final categories and keep explicit caller category if supplied.

- [ ] **Step 4: Run GREEN**

Run audit tests and record API filter tests.

## Task 7: Field Name Simplification With Compatibility

**Files:**
- Modify: `business/investment/schema.py`
- Modify: `migrations/investment/versions/20260609_0017_record_system_phase_2.py`
- Modify impacted service modules
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing field-name tests**

Assert physical columns exist:

- `request_records.service`, `request_records.outputs`, `request_records.error`
- `content_records.service`, `content_records.sources`, `content_records.input_text`, `content_records.output_text`, `content_records.output_image_path`, `content_records.error`
- `cache_entries.service`, `cache_entries.outputs`
- `artifacts.service`
- `operation_audits.category`, `operation_audits.result`, `operation_audits.error`

- [ ] **Step 2: Run RED**

Run schema test and confirm old names remain.

- [ ] **Step 3: Rename columns in migration and schema**

Use `op.alter_column(..., new_column_name=...)` for PostgreSQL. Update SQLAlchemy table definitions to new names.

- [ ] **Step 4: Add compatibility constants**

Keep dataclass fields and API response keys stable where external callers still use old names. Use helper functions so service code reads/writes new physical columns.

- [ ] **Step 5: Run GREEN**

Run focused schema tests and all business tests.

## Task 8: Final Verification

**Files:**
- Update plan checkboxes if execution is tracked manually.

- [ ] **Step 1: Run migration smoke**

Run: `py -m pytest tests/test_investment_business.py::test_investment_migration_smoke_creates_schema -q`

- [ ] **Step 2: Run business regression**

Run: `py -m pytest tests/test_investment_business.py -q`

- [ ] **Step 3: Run WeChat regression**

Run: `py -m pytest tests/test_wechatmp_investment_reply.py -q`

- [ ] **Step 4: Run database object verification**

Query production-like PostgreSQL and confirm no old table or column names remain except compatibility API fields.
