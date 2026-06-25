# Products Cache Schema Simplification Notes

## Decision

Do not collapse `source_request_id`, `source_content_id`, and `source_cache_key` in this migration.

## Reason

The fields are partially redundant with `source_type + source_id`, but current runtime code and UI filtering query them independently. Collapsing them now would add a broad migration and API compatibility risk while the main goal is retiring `cache_entries`.

## Follow-Up Option

A later migration can add:

- `source_id`
- `source_kind`

Then backfill:

- `source_id = source_request_id` when `source_type = 'request'`
- `source_id = source_content_id` when `source_type = 'content'`
- `source_id = source_cache_key` when `source_type = 'cache'`

After all code reads `source_id/source_kind`, the three source-specific columns can be removed.

## Fields Kept

- `products.source_request_id`: links component/request products to `request_records`.
- `products.source_content_id`: links backend content products to `content_records`.
- `products.source_cache_key`: preserves legacy cache identity and old URL/package references after `cache_entries` is dropped.
