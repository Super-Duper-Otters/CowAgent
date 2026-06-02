# Business Records Refactor Plan

## Goal

Keep the investment backend record model simple by exposing only three business-facing record categories:

- Customer records
- Content records
- Backoffice operation records

Supporting tables may remain in the database, but they should not appear as independent business record types in the admin console.

## Verified Current State

The current investment schema defines these tables:

| Table | Current role | Business category |
| --- | --- | --- |
| `investment_users` | Customer master data | Customer support table |
| `investment_admin_users` | Backoffice login accounts | Backoffice support table |
| `investment_admin_sessions` | Backoffice login sessions | Internal system table |
| `investment_request_records` | Customer service request records | Customer records |
| `investment_daily_contents` | Generated/published content records | Content records |
| `investment_output_files` | Output artifacts and attachments | Internal attachment table |
| `investment_cache_entries` | Technical analysis cache entries | Internal cache table |
| `investment_configs` | Current configuration values | Backoffice support table |
| `investment_operation_audits` | Backoffice operation audit log | Backoffice operation records |
| `investment_stock_symbols` | Stock symbol dictionary | Internal dictionary table |

Current database counts checked on 2026-06-02:

| Table | Count |
| --- | ---: |
| `investment_users` | 4 |
| `investment_admin_users` | 4 |
| `investment_admin_sessions` | 6 |
| `investment_request_records` | 331 |
| `investment_daily_contents` | 1 |
| `investment_output_files` | 224 |
| `investment_cache_entries` | 11 |
| `investment_configs` | 6 |
| `investment_operation_audits` | 6 |
| `investment_stock_symbols` | 5526 |

Known current gaps:

- `investment_operation_audits` only stores a free-text `operator`, not a stable admin user id or role.
- Several backend handlers still trust `operator` from request body/query params.
- Customer create/update/enable/disable/import/export is partly audited, but customer view, customer service-history view, and request-record export are not consistently audited.
- Content records only store a free-text `operator`.
- Config records only store a free-text `updated_by`.
- Cache, skill, config, and stock refresh operations are not consistently bound to the logged-in admin account.
- Old admin role `poster` still exists in the live database until the role cleanup migration is applied.
- Test/runtime residues exist: one `runtime.pg.test.*` config row and one `runtime-test` stock symbol row.

## Target Record Categories

### Customer Records

Main table: `investment_request_records`

Purpose:

- Customer service requests.
- Customer-generated analysis records.
- Success, failure, and timeout states related to customer service.

Support tables:

- `investment_users` for customer profile data.
- `investment_output_files` for generated files attached to a request.

Rule:

- Customer records are customer-owned records.
- Backoffice viewing/exporting/modifying customer data is recorded in backoffice operation records, not inside the customer request record itself.

### Content Records

Main table: `investment_daily_contents`

Purpose:

- Backoffice content drafts.
- Content generation.
- Content publishing/effective changes.
- Content archive/delete lifecycle.

Support tables:

- `investment_output_files` for generated images/files.
- `investment_cache_entries` only as cache support, not as a business record list.

Rule:

- Content records must bind the backoffice admin who created, updated/generated, and published them.
- The existing free-text `operator` remains only for compatibility during migration.

### Backoffice Operation Records

Main table: `investment_operation_audits`

Purpose:

- Any backoffice action that changes, exports, or inspects sensitive business data.
- Customer CRUD.
- Config and AI API changes.
- Skill upload/settings/version changes.
- Cache operations.
- Stock dictionary refresh.
- Admin account management.

Rule:

- Identity must come from the logged-in admin session.
- The frontend must not provide or override the operator identity.

## Target Field Changes

### `investment_users`

Add:

| Field | Purpose |
| --- | --- |
| `created_by_admin_id` | Admin id that created the customer |
| `created_by_username` | Username snapshot at creation |
| `updated_by_admin_id` | Admin id that last updated the customer |
| `updated_by_username` | Username snapshot at last update |
| `deleted_at` | Soft deletion timestamp |
| `deleted_by_admin_id` | Admin id that deleted the customer |
| `deleted_by_username` | Username snapshot at deletion |
| `delete_reason` | Deletion reason |

### `investment_daily_contents`

Add:

| Field | Purpose |
| --- | --- |
| `created_by_admin_id` | Admin id that created the content draft |
| `created_by_username` | Username snapshot at creation |
| `created_by_role` | Role snapshot at creation |
| `updated_by_admin_id` | Admin id that last updated/generated the content |
| `updated_by_username` | Username snapshot at update |
| `updated_by_role` | Role snapshot at update |
| `published_by_admin_id` | Admin id that published/effected the content |
| `published_by_username` | Username snapshot at publish |
| `published_by_role` | Role snapshot at publish |

### `investment_operation_audits`

Add:

| Field | Purpose |
| --- | --- |
| `operator_admin_id` | Stable admin user id |
| `operator_username` | Username snapshot |
| `operator_role` | Role snapshot |
| `operation_category` | `customer`, `content`, or `backoffice` |
| `request_ip` | Optional source IP |
| `user_agent` | Optional browser/client user-agent |

Keep `operator` temporarily for compatibility and filtering.

### `investment_configs`

Add:

| Field | Purpose |
| --- | --- |
| `updated_by_admin_id` | Admin id that last changed this config |
| `updated_by_username` | Username snapshot |
| `updated_by_role` | Role snapshot |

### `investment_output_files`

Add:

| Field | Purpose |
| --- | --- |
| `owner_type` | `request`, `content`, or `cache` |

## Audit Action Standard

Customer actions:

| Action | Target type |
| --- | --- |
| `customer.create` | `customer` |
| `customer.update` | `customer` |
| `customer.enable` | `customer` |
| `customer.disable` | `customer` |
| `customer.delete` | `customer` |
| `customer.import` | `customer` |
| `customer.export` | `customer` |
| `customer.view` | `customer` |
| `customer.records.view` | `customer` |

Content actions:

| Action | Target type |
| --- | --- |
| `content.create` | `daily_content` |
| `content.generate` | `daily_content` |
| `content.publish` | `daily_content` |
| `content.archive` | `daily_content` |
| `content.delete` | `daily_content` |

Backoffice actions:

| Action | Target type |
| --- | --- |
| `config.update` | `investment_config` |
| `config.ai_api.update` | `investment_config` |
| `skill.settings.update` | `investment_skill` |
| `skill.upload` | `investment_skill` |
| `skill.activate` | `investment_skill` |
| `skill.delete` | `investment_skill` |
| `cache.clear` | `investment_cache_entry` |
| `cache.invalidate` | `investment_cache_entry` |
| `stock.refresh` | `investment_stock_symbol` |
| `request_record.export` | `investment_request_record` |
| `admin_user.create` | `admin_user` |
| `admin_user.update` | `admin_user` |
| `admin_user.enable` | `admin_user` |
| `admin_user.disable` | `admin_user` |
| `admin_user.reset_password` | `admin_user` |

## Cleanup Policy

Run cleanup in dry-run mode first, then execute after review.

| Data | Cleanup rule |
| --- | --- |
| Old admin roles | Migrate `technical_admin` to `admin`; migrate `uploader`, `poster`, `operator`, `readonly` to `content_operator` |
| `runtime.pg.test.*` configs | Delete |
| `runtime-test` stock symbols | Delete |
| `unmatched` / `unauthorized_request` request records | Hide from normal customer records; delete after 30 days by default |
| `generate_failed` content with no output | Delete after 30 days by default |
| Expired admin sessions | Delete |
| Orphan output files | Delete rows whose owner no longer exists or whose file is missing |
| Invalidated/stale cache entries | Delete after 30 to 60 days |

## Execution Order

1. Add database fields and migration.
2. Add an `AdminActor` value object and update audit writing to accept session-derived admin identity.
3. Update web handlers so operator identity is taken from the current admin session.
4. Add customer CRUD actor fields and soft delete support.
5. Add content actor fields for create/update/publish.
6. Add config actor fields.
7. Standardize audit actions for customer, content, config, skill, cache, stock, request export, and admin-user management.
8. Add cleanup service with dry-run and execute modes.
9. Update admin UI to expose only customer records, content records, and backoffice operation records as business record groups.
10. Add and run focused tests for schema fields, audit identity binding, customer CRUD audits, content actor binding, config/skill/cache audit binding, and cleanup dry-run behavior.
