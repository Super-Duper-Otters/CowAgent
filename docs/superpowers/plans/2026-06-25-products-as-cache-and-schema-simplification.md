# Products-As-Cache And Schema Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `products` the single runtime cache/read model for generated artifacts, retire `cache_entries` safely, and simplify redundant product source fields only after compatibility is preserved.

**Architecture:** Move cache lookup, cache writes, hit counting, and artifact package lookup from `cache_entries` to `products` behind compatibility APIs first. Backfill and preserve all existing rows before dropping `cache_entries`; do not delete business records, products, archived files, or generated outputs. Keep workflow/audit tables (`request_records`, `content_records`, `artifacts`, `request_events`, `operation_audits`) because they serve different responsibilities from product caching.

**Tech Stack:** Python, SQLAlchemy Core, Alembic, web.py handlers, pytest backend tests, vanilla JavaScript static UI tests.

---

## Non-Negotiable Safety Rules

- Do not delete business records.
- Do not delete product rows.
- Do not delete archived files.
- Do not delete generated output files.
- Do not make Web history read old `cache_entries` or `content_records` paths again.
- Every task must follow: failing test -> implementation -> verification -> commit -> review.
- After each task, run a code review pass and fix Critical/Important issues before continuing.

---

## Current State

`products` already contains the fields needed to act as the product cache:

- `business_type`
- `target_key`
- `business_date`
- `version_fingerprint`
- `status`
- `source_cache_key`
- `source_request_id`
- `source_content_id`
- `output_files`
- `hit_count`
- `expires_at`
- `created_at`
- `updated_at`

`cache_entries` is still coupled to runtime code:

- `business/cache/cache_service.py`
  - `find_cache_entry`
  - `find_cache_entry_by_key`
  - `find_latest_cache_entry`
  - `write_cache_entry`
  - `increment_cache_hit`
  - `invalidate_cache_entry`
  - `clear_cache_entries`
  - `list_cache_entries_page`
- `business/cache/business_cache.py`
  - public compatibility wrapper for the cache service.
- `business/content/technical_analysis.py`
  - direct query over `investment_cache_entries` for compatible old technical-analysis cache.
- `business/content/technical_analysis_handler.py`
  - cache lookup by cache key and invalidation.
- `business/records/records.py`
  - legacy artifact-package compatibility paths that still reference cache source ids.
- `business/schema/file_migration.py`
  - legacy file migration touches `cache_entries`.
- Tests still assert `cache_entries` existence and cache behavior in `tests/test_business.py` and `tests/integration/test_business_postgres.py`.

---

## Target State

- New generated reusable outputs write `products`, not `cache_entries`.
- Runtime cache reads hit `products`.
- Cache compatibility functions still exist temporarily, but return `CacheEntry`-shaped objects mapped from product rows.
- Technical-analysis compatible-cache lookup reads `products`.
- Artifact package browser reads product-backed packages only.
- Old `cache_entries` rows are backfilled into `products` before the table is removed.
- A final migration drops `cache_entries` only after tests prove no runtime code imports or queries it.

---

## File Map

**Cache compatibility**
- Modify `business/cache/cache_service.py`: map legacy cache APIs onto `products`.
- Modify `business/cache/business_cache.py`: keep wrapper signatures stable.
- Modify `tests/test_business.py`: cache API behavior now asserts product rows.

**Technical-analysis runtime**
- Modify `business/content/technical_analysis.py`: replace direct `investment_cache_entries` query with product-backed lookup.
- Modify `business/content/technical_analysis_handler.py`: invalidate products instead of cache rows.
- Modify `tests/test_business.py`: technical-analysis cache reuse tests should use products.

**Artifact packages and cleanup**
- Modify `business/records/records.py`: remove `cache_entries` artifact source fallback.
- Modify cleanup logic file if found by `rg "stale_invalid_cache_entries|cache_entries"`: stop deleting cache rows and preserve product/file data.
- Modify `tests/test_business.py`: artifact package tests should prove product-only behavior.

**Schema**
- Modify `business/schema/tables.py`: remove `investment_cache_entries` only in the final schema task.
- Create Alembic migration under `migrations/business/versions/`: backfill verification and drop `cache_entries`.
- Modify `tests/integration/test_business_postgres.py`: remove table-existence assertions for `cache_entries` and add product cache indexes assertions.

**Web/static tests**
- Modify `tests/test_business_web_ui.py` only if static tests still reference legacy cache endpoints.
- Do not change Web UI unless tests prove a stale cache endpoint remains in the history path.

---

### Task 1: Add Product-Backed Cache Lookup Helpers

**Files:**
- Modify: `business/products/product_service.py`
- Modify: `tests/test_business.py`

- [ ] **Step 1: Write failing tests for product-backed cache lookup**

Add these tests to `tests/test_business.py` near existing cache/product tests:

```python
def test_product_cache_lookup_by_cache_key_returns_active_product(business_env, tmp_path):
    from business.config.constants import ServiceType
    from business.products.product_service import create_product, find_product_cache_entry_by_key

    output = tmp_path / "cache-product.png"
    output.write_text("image", encoding="utf-8")
    product = create_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="300502.SZ",
        target_label="300502.SZ",
        business_date="2026-06-25",
        version_fingerprint="vf-product-cache",
        status="active",
        source_cache_key="technical_analysis:300502.SZ:2026-06-25:vf-product-cache",
        source_type="cache",
        output_files=[str(output)],
    )

    entry = find_product_cache_entry_by_key("technical_analysis:300502.SZ:2026-06-25:vf-product-cache")

    assert entry is not None
    assert entry["product_id"] == product["product_id"]
    assert entry["cache_key"] == "technical_analysis:300502.SZ:2026-06-25:vf-product-cache"
    assert entry["service_type"] == str(ServiceType.TECHNICAL_ANALYSIS)
    assert entry["normalized_target"] == "300502.SZ"
    assert entry["market_date"] == "2026-06-25"
    assert entry["version_fingerprint"] == "vf-product-cache"
    assert entry["output_files"] == [str(output)]
    assert entry["status"] == "active"


def test_product_cache_lookup_invalidates_missing_files_without_deleting_product(business_env, tmp_path):
    from business.config.constants import ServiceType
    from business.products.product_service import (
        PRODUCT_STATUS_INVALIDATED,
        create_product,
        find_product_cache_entry,
        list_products_page,
    )

    missing = tmp_path / "missing.png"
    create_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="300502.SZ",
        target_label="300502.SZ",
        business_date="2026-06-25",
        version_fingerprint="vf-missing-product-cache",
        status="active",
        source_cache_key="technical_analysis:300502.SZ:2026-06-25:vf-missing-product-cache",
        source_type="cache",
        output_files=[str(missing)],
    )

    entry = find_product_cache_entry(
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        version_fingerprint="vf-missing-product-cache",
        market_date="2026-06-25",
    )

    assert entry is None
    products, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.TECHNICAL_ANALYSIS))
    assert total == 1
    assert products[0]["status"] == PRODUCT_STATUS_INVALIDATED
    assert products[0]["output_files"] == [str(missing)]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
pytest tests/test_business.py::test_product_cache_lookup_by_cache_key_returns_active_product tests/test_business.py::test_product_cache_lookup_invalidates_missing_files_without_deleting_product -q
```

Expected: fail because `find_product_cache_entry_by_key` and `find_product_cache_entry` do not exist.

- [ ] **Step 3: Implement product cache helpers**

In `business/products/product_service.py`, add helper functions near existing `find_active_product_by_id` helpers:

```python
def _product_to_cache_entry_dict(product: dict) -> dict:
    return {
        "product_id": str(product.get("product_id") or ""),
        "cache_key": str(product.get("source_cache_key") or ""),
        "service_type": str(product.get("business_type") or ""),
        "normalized_target": str(product.get("target_key") or ""),
        "market_date": str(product.get("business_date") or ""),
        "version_fingerprint": str(product.get("version_fingerprint") or ""),
        "output_files": list(product.get("output_files") or []),
        "artifact_owner_id": str(product.get("source_request_id") or ""),
        "status": str(product.get("status") or ""),
        "hit_count": int(product.get("hit_count") or 0),
        "created_at": str(product.get("created_at") or ""),
        "updated_at": str(product.get("updated_at") or ""),
    }


def find_product_cache_entry_by_key(cache_key: str, *, require_files: bool = True) -> dict | None:
    normalized_cache_key = _text(cache_key)
    if not normalized_cache_key:
        return None
    now = _now()
    stmt = (
        select(investment_products)
        .where(
            and_(
                investment_products.c.source_cache_key == normalized_cache_key,
                investment_products.c.status == PRODUCT_STATUS_ACTIVE,
                _expires_at_condition(now),
            )
        )
        .order_by(desc(investment_products.c.updated_at), desc(investment_products.c.created_at))
        .limit(1)
    )
    with connect() as conn:
        row = conn.execute(stmt).fetchone()
    if row is None:
        return None
    product = _row_to_product(row)
    if require_files and not _files_available(product["output_files"]):
        _invalidate_product_if_unchanged(product)
        return None
    return _product_to_cache_entry_dict(product)


def find_product_cache_entry(
    *,
    service_type,
    normalized_target: str,
    version_fingerprint: str,
    market_date: str = "",
    require_files: bool = True,
) -> dict | None:
    if not market_date:
        return None
    now = _now()
    stmt = (
        select(investment_products)
        .where(
            and_(
                investment_products.c.business_type == str(service_type),
                investment_products.c.target_key == _text(normalized_target),
                investment_products.c.business_date == _text(market_date),
                investment_products.c.version_fingerprint == _text(version_fingerprint),
                investment_products.c.status == PRODUCT_STATUS_ACTIVE,
                _expires_at_condition(now),
            )
        )
        .order_by(desc(investment_products.c.updated_at), desc(investment_products.c.created_at))
        .limit(1)
    )
    with connect() as conn:
        row = conn.execute(stmt).fetchone()
    if row is None:
        return None
    product = _row_to_product(row)
    if require_files and not _files_available(product["output_files"]):
        _invalidate_product_if_unchanged(product)
        return None
    return _product_to_cache_entry_dict(product)
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
pytest tests/test_business.py::test_product_cache_lookup_by_cache_key_returns_active_product tests/test_business.py::test_product_cache_lookup_invalidates_missing_files_without_deleting_product -q
```

Expected: 2 passed.

- [ ] **Step 5: Review and commit**

Review:

```powershell
git diff -- business/products/product_service.py tests/test_business.py
git diff --check
```

Fix Critical/Important issues. Then commit:

```powershell
git add business/products/product_service.py tests/test_business.py
git commit -m "Add product-backed cache lookup helpers"
```

---

### Task 2: Move Cache Service Compatibility APIs Onto Products

**Files:**
- Modify: `business/cache/cache_service.py`
- Modify: `tests/test_business.py`

- [ ] **Step 1: Write failing test proving `write_cache_entry` writes products only**

Add to `tests/test_business.py`:

```python
def test_write_cache_entry_creates_product_without_cache_row(business_env, tmp_path):
    from sqlalchemy import select

    from business.cache.cache_service import build_cache_key, find_cache_entry_by_key, write_cache_entry
    from business.config.constants import ServiceType
    from business.products.product_service import list_products_page
    from business.schema.db import connect
    from business.schema.tables import investment_cache_entries

    output = tmp_path / "product-cache-write.png"
    output.write_text("product-cache-write", encoding="utf-8")
    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-06-25", "vf-write-product")

    written = write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-06-25",
        version_fingerprint="vf-write-product",
        output_files=[str(output)],
        artifact_owner_id="req-product-cache-write",
    )

    found = find_cache_entry_by_key(cache_key)
    products, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.TECHNICAL_ANALYSIS))
    with connect() as conn:
        legacy_rows = conn.execute(select(investment_cache_entries)).fetchall()

    assert written.cache_key == cache_key
    assert found is not None
    assert found.cache_key == cache_key
    assert total == 1
    assert products[0]["source_cache_key"] == cache_key
    assert products[0]["source_request_id"] == "req-product-cache-write"
    assert products[0]["output_files"] == [str(output)]
    assert legacy_rows == []
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
pytest tests/test_business.py::test_write_cache_entry_creates_product_without_cache_row -q
```

Expected: fail because `write_cache_entry` still inserts into `cache_entries`.

- [ ] **Step 3: Implement product-backed compatibility**

In `business/cache/cache_service.py`:

1. Keep `CacheEntry` and `build_cache_key`.
2. Change `find_cache_entry`, `find_cache_entry_by_key`, `increment_cache_hit`, `write_cache_entry`, and `invalidate_cache_entry` to call `business.products.product_service`.
3. Keep `list_cache_entries_page` as a compatibility listing over products until all callers are migrated.

Use this mapping function:

```python
def _product_cache_dict_to_entry(item: dict | None) -> CacheEntry | None:
    if not item:
        return None
    return CacheEntry(
        cache_key=str(item.get("cache_key") or ""),
        service_type=ServiceType(item.get("service_type")),
        normalized_target=str(item.get("normalized_target") or ""),
        market_date=str(item.get("market_date") or ""),
        version_fingerprint=str(item.get("version_fingerprint") or ""),
        output_files=list(item.get("output_files") or []),
        artifact_owner_id=str(item.get("artifact_owner_id") or ""),
        status=str(item.get("status") or CACHE_STATUS_ACTIVE),
        hit_count=int(item.get("hit_count") or 0),
        created_at=str(item.get("created_at") or ""),
        updated_at=str(item.get("updated_at") or ""),
    )
```

Replace `write_cache_entry` body with product creation through `replace_active_product`:

```python
def write_cache_entry(
    *,
    cache_key: str,
    service_type: ServiceType,
    normalized_target: str,
    market_date: str,
    version_fingerprint: str,
    output_files: list[str],
    artifact_owner_id: str = "",
) -> CacheEntry:
    from business.products.product_service import replace_active_product

    product = replace_active_product(
        business_type=str(service_type),
        target_key=normalized_target,
        target_label=normalized_target,
        business_date=market_date,
        version_fingerprint=version_fingerprint,
        status=CACHE_STATUS_ACTIVE,
        source_request_id=artifact_owner_id,
        source_cache_key=cache_key,
        source_type="cache",
        output_files=output_files,
    )
    return CacheEntry(
        cache_key=cache_key,
        service_type=service_type,
        normalized_target=normalized_target,
        market_date=market_date,
        version_fingerprint=version_fingerprint,
        output_files=list(output_files or []),
        artifact_owner_id=artifact_owner_id,
        status=str(product.get("status") or CACHE_STATUS_ACTIVE),
        hit_count=int(product.get("hit_count") or 0),
        created_at=str(product.get("created_at") or ""),
        updated_at=str(product.get("updated_at") or ""),
    )
```

Implement `find_cache_entry_by_key` by calling `find_product_cache_entry_by_key`, and `find_cache_entry` by calling `find_product_cache_entry`.

- [ ] **Step 4: Run targeted cache tests**

Run:

```powershell
pytest tests/test_business.py::test_write_cache_entry_creates_product_without_cache_row tests/test_business.py::test_write_cache_entry_rewrites_payload_without_resetting_hit_count tests/test_business.py::test_find_cache_entry_missing_cache_file_invalidates_active_entry -q
```

Expected: all pass. If hit count reset behavior differs because `replace_active_product` creates a new row, preserve prior hit count by looking up active product before replacing and copying `hit_count`.

- [ ] **Step 5: Review and commit**

Review:

```powershell
git diff -- business/cache/cache_service.py tests/test_business.py
git diff --check
```

Fix Critical/Important issues. Then commit:

```powershell
git add business/cache/cache_service.py tests/test_business.py
git commit -m "Move cache compatibility APIs onto products"
```

---

### Task 3: Move Technical-Analysis Compatible Cache Queries Onto Products

**Files:**
- Modify: `business/content/technical_analysis.py`
- Modify: `business/content/technical_analysis_handler.py`
- Modify: `tests/test_business.py`

- [ ] **Step 1: Write failing technical-analysis product-cache reuse test**

Add to `tests/test_business.py`:

```python
def test_technical_analysis_compatible_cache_reads_products_not_cache_entries(business_env, tmp_path):
    from sqlalchemy import select

    from business.cache.cache_service import build_cache_key, version_fingerprint
    from business.config.constants import ServiceType
    from business.content import technical_analysis
    from business.products.product_service import create_product
    from business.schema.db import connect
    from business.schema.tables import investment_cache_entries

    output = tmp_path / "compatible-product-cache.png"
    output.write_text("compatible", encoding="utf-8")
    vf = version_fingerprint("compatible-product-cache")
    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "002354.SZ", "2026-06-25", vf)
    create_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="002354.SZ",
        target_label="天娱数科",
        business_date="2026-06-25",
        version_fingerprint=vf,
        status="active",
        source_cache_key=cache_key,
        source_type="cache",
        output_files=[str(output)],
    )
    with connect() as conn:
        assert conn.execute(select(investment_cache_entries)).fetchall() == []

    cached = technical_analysis.find_compatible_cached_analysis(
        symbol="002354.SZ",
        market_date="2026-06-25",
        current_version_fingerprint="different-current-vf",
    )

    assert cached is not None
    assert cached.cache_key == cache_key
    assert cached.output_files == [str(output)]
```

If `find_compatible_cached_analysis` is not public, write the test against the existing public function that currently exercises `_compatible_cache_entries`.

- [ ] **Step 2: Run test and verify it fails**

Run:

```powershell
pytest tests/test_business.py::test_technical_analysis_compatible_cache_reads_products_not_cache_entries -q
```

Expected: fail because compatible query still reads `investment_cache_entries`.

- [ ] **Step 3: Replace direct cache table query**

In `business/content/technical_analysis.py`:

- Remove `investment_cache_entries` from imports.
- Replace `_compatible_cache_entries` query with a product-backed query over `investment_products`.
- Convert product rows into `cache_service.CacheEntry`.
- Preserve existing expiration policy by continuing to call `_technical_analysis_cache_entry_allowed`.

Implementation shape:

```python
def _compatible_cache_entries(symbol: str, market_date: str, current_version_fingerprint: str) -> list[cache_service.CacheEntry]:
    from business.products.product_service import PRODUCT_STATUS_ACTIVE, _expires_at_condition
    from business.schema.tables import investment_products

    conditions = [
        investment_products.c.business_type == str(ServiceType.TECHNICAL_ANALYSIS),
        investment_products.c.target_key == symbol,
        investment_products.c.status == PRODUCT_STATUS_ACTIVE,
        investment_products.c.version_fingerprint != current_version_fingerprint,
        _expires_at_condition(_now()),
    ]
    if market_date:
        conditions.append(investment_products.c.business_date == market_date)
    stmt = (
        select(investment_products)
        .where(and_(*conditions))
        .order_by(desc(investment_products.c.business_date), desc(investment_products.c.updated_at))
    )
    with connect() as conn:
        rows = [row_to_dict(row) for row in conn.execute(stmt).fetchall()]
    return [
        cache_service.CacheEntry(
            cache_key=str(row.get("source_cache_key") or row.get("product_id") or ""),
            service_type=ServiceType.TECHNICAL_ANALYSIS,
            normalized_target=str(row.get("target_key") or ""),
            market_date=str(row.get("business_date") or ""),
            version_fingerprint=str(row.get("version_fingerprint") or ""),
            output_files=_load_list(row.get("output_files")),
            artifact_owner_id=str(row.get("source_request_id") or ""),
            status=str(row.get("status") or "active"),
            hit_count=int(row.get("hit_count") or 0),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
        )
        for row in rows
    ]
```

In `business/content/technical_analysis_handler.py`, replace `invalidate_cache_entry(cache_context.cache_key)` with product invalidation by source cache key.

- [ ] **Step 4: Run technical-analysis cache tests**

Run:

```powershell
pytest tests/test_business.py -k "technical_analysis and cache" -q
```

Expected: pass. If tests still rely on `list_cache_entries`, keep compatibility return values product-backed.

- [ ] **Step 5: Review and commit**

Review:

```powershell
git diff -- business/content/technical_analysis.py business/content/technical_analysis_handler.py tests/test_business.py
git diff --check
```

Fix Critical/Important issues. Then commit:

```powershell
git add business/content/technical_analysis.py business/content/technical_analysis_handler.py tests/test_business.py
git commit -m "Use products for technical-analysis cache reuse"
```

---

### Task 4: Remove Cache Table From Artifact Package Runtime Paths

**Files:**
- Modify: `business/records/records.py`
- Modify: `tests/test_business.py`

- [ ] **Step 1: Write failing artifact package test with no cache row**

Add to `tests/test_business.py`:

```python
def test_artifact_packages_do_not_query_cache_entries_for_product_sources(business_env, tmp_path, monkeypatch):
    from sqlalchemy import select

    from business.config.constants import ServiceType
    from business.products.product_service import create_product
    from business.records import records
    from business.schema.db import connect
    from business.schema.tables import investment_cache_entries

    output = tmp_path / "artifact-product-only.png"
    output.write_text("artifact", encoding="utf-8")
    create_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="300502.SZ",
        target_label="300502.SZ",
        business_date="2026-06-25",
        version_fingerprint="vf-artifact-product-only",
        status="active",
        source_cache_key="legacy-cache-key-for-display-only",
        source_type="cache",
        output_files=[str(output)],
    )
    with connect() as conn:
        assert conn.execute(select(investment_cache_entries)).fetchall() == []

    packages, total = records.list_artifact_packages_page(service_type=ServiceType.TECHNICAL_ANALYSIS)

    assert total == 1
    assert packages[0]["source_type"] == "product"
    assert packages[0]["source_cache_key"] == "legacy-cache-key-for-display-only"
    assert packages[0]["file_count"] == 1
```

- [ ] **Step 2: Run test and verify behavior**

Run:

```powershell
pytest tests/test_business.py::test_artifact_packages_do_not_query_cache_entries_for_product_sources -q
```

Expected: pass if current product path is already dominant, or fail if legacy cache fallback is still required.

- [ ] **Step 3: Remove runtime cache table references from artifact package path**

In `business/records/records.py`:

- Keep product package path.
- Remove or quarantine `_row_to_artifact_package`, `_artifact_package_conditions`, and cache-source query branches if they are no longer called.
- Remove `exists(select(investment_cache_entries...))` filters from internal-call package paths if products already dedupe request sources.
- Keep request/content/artifact records intact.

After editing, this command should show no runtime reference in `records.py`:

```powershell
rg -n "investment_cache_entries|cache_entries" business/records/records.py
```

Expected: no matches.

- [ ] **Step 4: Run artifact package tests**

Run:

```powershell
pytest tests/test_business.py -k "artifact_package or artifact_folder" -q
```

Expected: pass.

- [ ] **Step 5: Review and commit**

Review:

```powershell
git diff -- business/records/records.py tests/test_business.py
git diff --check
```

Fix Critical/Important issues. Then commit:

```powershell
git add business/records/records.py tests/test_business.py
git commit -m "Remove cache table from artifact package paths"
```

---

### Task 5: Stop Exposing Cache Entries As A First-Class History API

**Files:**
- Modify: `channel/web/web_channel.py`
- Modify: `channel/web/static/js/console.js`
- Modify: `tests/test_business.py`
- Modify: `tests/test_business_web_ui.py`

- [ ] **Step 1: Write failing static test that Web history does not call cache endpoint**

Add to `tests/test_business_web_ui.py`:

```python
def test_generated_history_does_not_call_legacy_cache_endpoint():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    load_products_body = _js_function_body(js, "loadInvestmentProducts")
    assert "/api/investment/products" in load_products_body
    assert "/api/investment/cache" not in load_products_body
    assert "loadInvestmentCacheEntries" not in _js_function_body(js, "loadInvestmentRecordsTab")
```

- [ ] **Step 2: Write failing backend test that cache endpoint is not used for generated history**

If `/api/investment/cache` remains for admin compatibility, do not delete it yet. Instead add this test near generated history tests:

```python
def test_generated_history_api_reads_products_not_cache_entries_after_cache_retirement(business_env, tmp_path):
    from business.config.constants import ServiceType
    from business.products.product_service import create_product
    from business.records.records import list_artifact_packages_page

    output = tmp_path / "history-product-only.png"
    output.write_text("history", encoding="utf-8")
    create_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="300502.SZ",
        target_label="300502.SZ",
        business_date="2026-06-25",
        version_fingerprint="vf-history-product-only",
        status="active",
        source_type="request",
        source_request_id="req-history-product-only",
        output_files=[str(output)],
    )

    packages, total = list_artifact_packages_page(service_type=ServiceType.TECHNICAL_ANALYSIS)

    assert total == 1
    assert packages[0]["source_type"] == "product"
    assert packages[0]["product_id"]
```

- [ ] **Step 3: Run tests and verify failures or current pass**

Run:

```powershell
pytest tests/test_business_web_ui.py::test_generated_history_does_not_call_legacy_cache_endpoint tests/test_business.py::test_generated_history_api_reads_products_not_cache_entries_after_cache_retirement -q
```

Expected: pass if previous product-only UI work already covered this; otherwise fail on stale cache references.

- [ ] **Step 4: Remove stale Web cache history references**

In `channel/web/static/js/console.js`, ensure generated history uses:

```javascript
investmentFetchJson(`/api/investment/products?${query.toString()}`)
investmentFetchJson(`/api/investment/artifacts?${query.toString()}`)
```

and not:

```javascript
/api/investment/cache
```

In `channel/web/web_channel.py`, keep `/api/investment/cache` only if tests still require a backward-compatible admin endpoint. It must not be called from generated history UI.

- [ ] **Step 5: Run Web tests**

Run:

```powershell
pytest tests/test_business_web_ui.py -q
```

Expected: pass.

- [ ] **Step 6: Review and commit**

Review:

```powershell
git diff -- channel/web/web_channel.py channel/web/static/js/console.js tests/test_business.py tests/test_business_web_ui.py
git diff --check
```

Fix Critical/Important issues. Then commit:

```powershell
git add channel/web/web_channel.py channel/web/static/js/console.js tests/test_business.py tests/test_business_web_ui.py
git commit -m "Keep generated history product-only after cache retirement"
```

---

### Task 6: Backfill Guard And Drop `cache_entries`

**Files:**
- Modify: `business/schema/tables.py`
- Modify: `business/schema/file_migration.py`
- Create: `migrations/business/versions/20260625_0028_drop_cache_entries.py`
- Modify: `tests/test_business.py`
- Modify: `tests/integration/test_business_postgres.py`

- [ ] **Step 1: Write failing schema tests**

Update `tests/test_business.py` schema assertions:

```python
def test_business_schema_no_longer_defines_cache_entries_table():
    from business.schema.tables import metadata

    assert "products" in metadata.tables
    assert "cache_entries" not in metadata.tables
```

Update `tests/integration/test_business_postgres.py`:

```python
def test_business_postgres_schema_uses_products_for_cache(postgres_business_engine):
    from sqlalchemy import inspect

    inspector = inspect(postgres_business_engine)
    assert inspector.has_table("products")
    assert not inspector.has_table("cache_entries")
    product_columns = {column["name"] for column in inspector.get_columns("products")}
    assert {
        "business_type",
        "target_key",
        "business_date",
        "version_fingerprint",
        "source_cache_key",
        "output_files",
        "hit_count",
        "status",
    }.issubset(product_columns)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
pytest tests/test_business.py::test_business_schema_no_longer_defines_cache_entries_table tests/integration/test_business_postgres.py::test_business_postgres_schema_uses_products_for_cache -q
```

Expected: fail because `cache_entries` still exists.

- [ ] **Step 3: Add drop migration**

Create `migrations/business/versions/20260625_0028_drop_cache_entries.py`:

```python
"""Drop legacy cache entries after product cache migration."""

from alembic import op
import sqlalchemy as sa


revision = "20260625_0028"
down_revision = "20260624_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        existing = bind.execute(
            sa.text(
                """
                select count(*)
                from information_schema.tables
                where table_schema = current_schema()
                  and table_name = 'cache_entries'
                """
            )
        ).scalar_one()
        if not existing:
            return
    op.drop_table("cache_entries")


def downgrade() -> None:
    op.create_table(
        "cache_entries",
        sa.Column("cache_key", sa.Text(), primary_key=True),
        sa.Column("service", sa.Text(), nullable=False),
        sa.Column("normalized_target", sa.Text(), nullable=False),
        sa.Column("market_date", sa.Text(), nullable=False),
        sa.Column("version_fingerprint", sa.Text(), nullable=False),
        sa.Column("outputs", sa.Text(), nullable=False),
        sa.Column("artifact_owner_id", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "idx_cache_entries_lookup",
        "cache_entries",
        ["service", "normalized_target", "market_date", "version_fingerprint", "status"],
    )
    op.create_index("idx_cache_entries_service_date", "cache_entries", ["service", "market_date", "status"])
```

Before this migration is accepted, verify `20260624_0027_backfill_products.py` runs before it and backfills old cache rows.

- [ ] **Step 4: Remove table definition and imports**

In `business/schema/tables.py`:

- Delete `investment_cache_entries = Table(...)`.
- Delete alias `cache_entries = investment_cache_entries`.
- Ensure no import still needs it.

In `business/schema/file_migration.py`:

- Remove cache row migration branch.
- Keep request/content/artifact migration logic.

Run:

```powershell
rg -n "investment_cache_entries|cache_entries" business migrations tests
```

Expected: only migration history files and explicit legacy-drop migration references remain. Runtime `business/` files should have no references.

- [ ] **Step 5: Run schema tests**

Run:

```powershell
pytest tests/test_business.py::test_business_schema_no_longer_defines_cache_entries_table tests/integration/test_business_postgres.py::test_business_postgres_schema_uses_products_for_cache -q
```

Expected: pass.

- [ ] **Step 6: Review and commit**

Review:

```powershell
git diff -- business/schema/tables.py business/schema/file_migration.py migrations/business/versions/20260625_0028_drop_cache_entries.py tests/test_business.py tests/integration/test_business_postgres.py
git diff --check
```

Fix Critical/Important issues. Then commit:

```powershell
git add business/schema/tables.py business/schema/file_migration.py migrations/business/versions/20260625_0028_drop_cache_entries.py tests/test_business.py tests/integration/test_business_postgres.py
git commit -m "Drop legacy cache entries table"
```

---

### Task 7: Evaluate Product Source Field Simplification Without Risky Migration

**Files:**
- Modify: `docs/superpowers/specs/products-cache-schema-simplification-notes.md`
- Modify: `tests/test_business.py`

- [ ] **Step 1: Write characterization test for current source fields**

Add to `tests/test_business.py`:

```python
def test_product_source_fields_support_request_content_and_legacy_cache_sources(business_env, tmp_path):
    from business.products.product_service import create_product, list_products_page

    output = tmp_path / "source-fields.png"
    output.write_text("source", encoding="utf-8")
    create_product(
        business_type="component:testcomponent",
        target_key="testcomponent",
        target_label="testcomponent",
        business_date="2026-06-25",
        version_fingerprint="vf-source-fields-request",
        status="active",
        source_type="request",
        source_request_id="req-source-fields",
        output_files=[str(output)],
    )
    create_product(
        business_type="rate",
        target_key="利率内容",
        target_label="利率内容",
        business_date="2026-06-25",
        version_fingerprint="vf-source-fields-content",
        status="active",
        source_type="content",
        source_content_id="content-source-fields",
        output_files=[str(output)],
    )
    create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="300502.SZ",
        business_date="2026-06-25",
        version_fingerprint="vf-source-fields-cache",
        status="active",
        source_type="cache",
        source_cache_key="cache-source-fields",
        output_files=[str(output)],
    )

    products, total = list_products_page(include_invalidated=True)

    assert total == 3
    assert {item["source_type"] for item in products} == {"request", "content", "cache"}
    assert any(item["source_request_id"] == "req-source-fields" for item in products)
    assert any(item["source_content_id"] == "content-source-fields" for item in products)
    assert any(item["source_cache_key"] == "cache-source-fields" for item in products)
```

- [ ] **Step 2: Run characterization test**

Run:

```powershell
pytest tests/test_business.py::test_product_source_fields_support_request_content_and_legacy_cache_sources -q
```

Expected: pass. This test protects current behavior before any future source-field migration.

- [ ] **Step 3: Document field simplification decision**

Create `docs/superpowers/specs/products-cache-schema-simplification-notes.md`:

```markdown
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
```

- [ ] **Step 4: Review and commit**

Review:

```powershell
git diff -- tests/test_business.py docs/superpowers/specs/products-cache-schema-simplification-notes.md
git diff --check
```

Fix Critical/Important issues. Then commit:

```powershell
git add tests/test_business.py docs/superpowers/specs/products-cache-schema-simplification-notes.md
git commit -m "Document product source field simplification decision"
```

---

### Task 8: Final Verification

**Files:**
- No code changes unless verification reveals defects.

- [ ] **Step 1: Confirm no runtime cache table references**

Run:

```powershell
rg -n "investment_cache_entries|cache_entries" business channel tests
```

Expected:

- No matches in `business/` runtime files.
- Tests may mention `cache_entries` only if testing old migrations; prefer no matches after Task 6.
- Migration history files may still mention old table.

- [ ] **Step 2: Run backend tests from the product/history area**

Run:

```powershell
pytest tests/test_business.py -k "product or cache or artifact_package or artifact_folder or technical_analysis" -q
```

Expected: pass.

- [ ] **Step 3: Run Web UI static tests**

Run:

```powershell
pytest tests/test_business_web_ui.py -q
```

Expected: pass.

- [ ] **Step 4: Run JS syntax check**

Run:

```powershell
node --check channel/web/static/js/console.js
```

Expected: no syntax errors.

- [ ] **Step 5: Run migration/schema tests**

Run:

```powershell
pytest tests/integration/test_business_postgres.py -q
```

Expected: pass, or document if Docker/Postgres is unavailable.

- [ ] **Step 6: Final code review**

Run:

```powershell
git status --short
git log --oneline -8
git diff --check
```

Do a final review for:

- accidental file deletion
- business record deletion
- generated artifact deletion
- Web UI reading `/api/investment/cache` for generated history
- new writes to `cache_entries`
- stale imports of `investment_cache_entries`

Fix Critical/Important issues before final response.

---

## Expected Commit Sequence

1. `Add product-backed cache lookup helpers`
2. `Move cache compatibility APIs onto products`
3. `Use products for technical-analysis cache reuse`
4. `Remove cache table from artifact package paths`
5. `Keep generated history product-only after cache retirement`
6. `Drop legacy cache entries table`
7. `Document product source field simplification decision`

---

## Review Checklist

- Product rows are never deleted to invalidate cache.
- Missing output files invalidate product status instead of deleting files.
- `cache_entries` is dropped only after backfill and compatibility migration.
- `request_records`, `content_records`, `artifacts`, `request_events`, and `operation_audits` remain intact.
- UI history remains “分类卡片 + 左侧文件树 + 右侧预览”.
- Component products still store under component namespaces and are viewable through product/artifact APIs.
- Existing old `cache_entries` data is represented in `products` before dropping the table.

