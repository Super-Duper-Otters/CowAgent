# Product-Only History UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make historical generated content use the new unified product model end-to-end, restore the original category + artifact-tree history UI, and remove legacy cache/content history display from the Web path.

**Architecture:** Keep `products` as the only read model for generated history. Convert legacy cache/content rows into product rows through an explicit backfill path, then make Web history and artifact browsing consume product-backed APIs only. Business request/content records remain immutable audit/workflow records, but they are not used to render generated history.

**Tech Stack:** Python, SQLAlchemy, Alembic, web.py handlers, vanilla JavaScript console UI, pytest backend and static frontend tests.

---

## Current Problem

- `channel/web/static/js/console.js::loadInvestmentProducts()` was temporarily changed to read `/api/investment/cache`, which reintroduced old cache/content history into the UI.
- The history UI was also flattened into a product table, while the expected interaction is the previous category view with artifact folder tree and right-side file preview.
- Existing historical rows may still exist only in `cache_entries` or `daily_contents`, so a product-only UI will be empty unless those rows are backfilled into `products`.

## Target Behavior

- Historical generated content reads only from product-backed APIs.
- Old generated outputs are visible because they are backfilled into `products`, not because Web UI reads legacy cache/content tables.
- Historical generated content opens with category cards for 技术分析、利率、转债.
- Selecting a category shows the artifact browser: left folder tree, right preview pane.
- Product validity is shown through `products.status`/`expires_at`; invalidated products remain archived and visible when history view includes archived rows.
- Legacy cache/content history APIs are either removed from the Web UI path or kept only as non-UI compatibility shims during the same deployment.

---

## File Map

**Backfill and product read model**
- Modify `business/products/product_service.py`: add idempotent legacy backfill helpers and product artifact package helpers.
- Modify `business/schema/tables.py`: only if additional indexes are needed for source ids or generated history queries.
- Create migration under `migrations/business/versions/`: run one-time product backfill for existing legacy cache/content rows.
- Modify `tests/test_business.py`: backend tests for backfill, product-only history, and artifact package rendering.

**Web API**
- Modify `channel/web/web_channel.py`: make generated history endpoint product-only or add a product-backed endpoint used by history UI.
- Remove Web history reliance on `_investment_list_legacy_history_without_product_sources()` once tests prove backfill covers old rows.

**Web UI**
- Modify `channel/web/static/js/console.js`: restore category + artifact browser flow and route data through product-backed APIs.
- Modify `tests/test_business_web_ui.py`: static tests for product-only history loading and restored tree UI.

---

### Task 1: Backfill Legacy Generated Outputs Into Products

**Files:**
- Modify: `business/products/product_service.py`
- Modify: `tests/test_business.py`

- [ ] **Step 1: Write failing backfill test for legacy technical-analysis cache**

Add to `tests/test_business.py`:

```python
def test_backfill_products_from_legacy_cache_entries_is_idempotent(business_env, tmp_path):
    from business.cache.cache_service import build_cache_key, write_cache_entry
    from business.config.constants import ServiceType
    from business.products.product_service import backfill_products_from_legacy_sources, list_products_page

    card = tmp_path / "legacy-card.png"
    report = tmp_path / "legacy-report.md"
    card.write_text("card", encoding="utf-8")
    report.write_text("report", encoding="utf-8")
    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-06-20", "v1")
    write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-06-20",
        version_fingerprint="v1",
        output_files=[str(card), str(report)],
        artifact_owner_id="req-legacy-cache",
    )

    first = backfill_products_from_legacy_sources()
    second = backfill_products_from_legacy_sources()

    rows, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.TECHNICAL_ANALYSIS))
    assert first["cache_created"] == 1
    assert second["cache_created"] == 0
    assert total == 1
    assert rows[0]["source_type"] == "cache"
    assert rows[0]["source_cache_key"] == cache_key
    assert rows[0]["output_files"] == [str(card), str(report)]
```

- [ ] **Step 2: Write failing backfill test for legacy daily content**

Add to `tests/test_business.py`:

```python
def test_backfill_products_from_legacy_daily_content_preserves_status_and_text(business_env, tmp_path):
    from business.config.constants import ServiceType
    from business.content.daily_content import create_content_draft, update_generation_success, set_content_effective
    from business.products.product_service import backfill_products_from_legacy_sources, list_products_page

    image = tmp_path / "rate.png"
    image.write_text("rate image", encoding="utf-8")
    content_id = create_content_draft(
        ServiceType.RATE,
        source_text="公开市场操作",
        effective_date="2026-06-20",
        operator="ops",
    )
    update_generation_success(content_id, "生成后的利率内容", str(image))
    set_content_effective(content_id, operator="ops")

    result = backfill_products_from_legacy_sources()

    rows, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.RATE))
    assert result["content_created"] == 1
    assert total == 1
    assert rows[0]["source_type"] == "content"
    assert rows[0]["source_content_id"] == content_id
    assert rows[0]["business_date"] == "2026-06-20"
    assert rows[0]["text_content"] == "生成后的利率内容"
    assert rows[0]["output_files"] == [str(image)]
    assert rows[0]["status"] == "active"
```

- [ ] **Step 3: Run tests and verify red**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business.py::test_backfill_products_from_legacy_cache_entries_is_idempotent tests/test_business.py::test_backfill_products_from_legacy_daily_content_preserves_status_and_text -q
```

Expected: FAIL because `backfill_products_from_legacy_sources` does not exist.

- [ ] **Step 4: Implement idempotent backfill helpers**

In `business/products/product_service.py`, add:

```python
def product_exists_for_source(*, source_cache_key: str = "", source_content_id: str = "", conn=None) -> bool:
    conditions = []
    if source_cache_key:
        conditions.append(investment_products.c.source_cache_key == _text(source_cache_key))
    if source_content_id:
        conditions.append(investment_products.c.source_content_id == _text(source_content_id))
    if not conditions:
        return False
    stmt = select(func.count()).select_from(investment_products).where(or_(*conditions))
    active_conn = conn or connect()
    close_conn = conn is None
    try:
        return int(active_conn.execute(stmt).scalar_one() or 0) > 0
    finally:
        if close_conn:
            active_conn.close()
```

Then add:

```python
def backfill_products_from_legacy_sources() -> dict[str, int]:
    from business.schema.tables import investment_cache_entries, investment_daily_contents

    created_cache = 0
    created_content = 0
    with connect() as conn:
        cache_rows = conn.execute(select(investment_cache_entries)).fetchall()
        for row in cache_rows:
            item = dict(row._mapping)
            cache_key = str(item.get("cache_key") or "")
            if not cache_key or product_exists_for_source(source_cache_key=cache_key, conn=conn):
                continue
            _create_product_on_connection(
                conn,
                business_type=str(item.get("service_type") or ""),
                target_key=str(item.get("normalized_target") or ""),
                target_label=str(item.get("normalized_target") or ""),
                business_date=str(item.get("market_date") or ""),
                version_fingerprint=str(item.get("version_fingerprint") or ""),
                source_type="cache",
                source_cache_key=cache_key,
                source_request_id=str(item.get("artifact_owner_id") or ""),
                output_files=_load_list(item.get("output_files")),
                status=str(item.get("status") or PRODUCT_STATUS_ACTIVE),
                effective_at=str(item.get("created_at") or ""),
                created_at=str(item.get("created_at") or ""),
                updated_at=str(item.get("updated_at") or ""),
            )
            created_cache += 1

        content_rows = conn.execute(select(investment_daily_contents)).fetchall()
        for row in content_rows:
            item = dict(row._mapping)
            content_id = str(item.get("content_id") or "")
            if not content_id or product_exists_for_source(source_content_id=content_id, conn=conn):
                continue
            status = str(item.get("status") or "")
            product_status = PRODUCT_STATUS_ACTIVE if status in {"generated", "effective"} else PRODUCT_STATUS_INVALIDATED
            _create_product_on_connection(
                conn,
                business_type=str(item.get("service_type") or ""),
                target_key=str(item.get("service_type") or ""),
                target_label=str(item.get("service_type") or ""),
                business_date=str(item.get("effective_date") or ""),
                version_fingerprint=f"v{item.get('content_version') or 1}",
                source_type="content",
                source_content_id=content_id,
                output_files=[str(item.get("output_image") or "")] if item.get("output_image") else [],
                text_content=str(item.get("generated_text") or ""),
                status=product_status,
                expires_at=str(item.get("expires_at") or ""),
                effective_at=str(item.get("created_at") or ""),
                created_at=str(item.get("created_at") or ""),
                updated_at=str(item.get("updated_at") or ""),
            )
            created_content += 1
    return {"cache_created": created_cache, "content_created": created_content}
```

If `_create_product_on_connection()` does not accept explicit `status`, `created_at`, or `updated_at`, extend it so backfilled products preserve legacy timestamps and validity.

- [ ] **Step 5: Run tests and verify green**

Run the same command from Step 3.

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add business/products/product_service.py tests/test_business.py
git commit -m "Backfill legacy generated outputs into products"
```

---

### Task 2: Add Migration for Product Backfill

**Files:**
- Create: `migrations/business/versions/20260624_0027_backfill_products.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Add migration smoke test**

Add to `tests/test_business.py`:

```python
def test_product_backfill_migration_revision_exists():
    path = Path("migrations/business/versions/20260624_0027_backfill_products.py")
    text = path.read_text(encoding="utf-8")
    assert 'revision = "20260624_0027"' in text
    assert 'down_revision = "20260624_0026"' in text
    assert "backfill_products_from_legacy_sources" in text
```

- [ ] **Step 2: Run test and verify red**

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business.py::test_product_backfill_migration_revision_exists -q
```

Expected: FAIL because migration file does not exist.

- [ ] **Step 3: Create migration**

Create `migrations/business/versions/20260624_0027_backfill_products.py`:

```python
# encoding:utf-8
"""backfill legacy generated outputs into products"""

from alembic import op


revision = "20260624_0027"
down_revision = "20260624_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from business.products.product_service import backfill_products_from_legacy_sources

    bind = op.get_bind()
    backfill_products_from_legacy_sources(conn=bind)


def downgrade() -> None:
    pass
```

Adjust `backfill_products_from_legacy_sources(conn=None)` in Task 1 so migration can pass the Alembic connection.

- [ ] **Step 4: Run migration smoke test**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add migrations/business/versions/20260624_0027_backfill_products.py business/products/product_service.py tests/test_business.py
git commit -m "Backfill products during business migration"
```

---

### Task 3: Make Generated History API Product-Only

**Files:**
- Modify: `channel/web/web_channel.py`
- Modify: `tests/test_business.py`

- [ ] **Step 1: Write failing API test**

Add to `tests/test_business.py`:

```python
def test_generated_history_api_reads_backfilled_products_not_legacy_sources(business_env, monkeypatch, tmp_path):
    from business.cache.cache_service import build_cache_key, write_cache_entry
    from business.config.constants import ServiceType
    from business.products.product_service import backfill_products_from_legacy_sources
    from channel.web.web_channel import InvestmentProductsHandler

    output = tmp_path / "legacy.png"
    output.write_text("legacy", encoding="utf-8")
    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-06-20", "v1")
    write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-06-20",
        version_fingerprint="v1",
        output_files=[str(output)],
        artifact_owner_id="req-backfilled",
    )
    backfill_products_from_legacy_sources()

    payload = _call_investment_json_handler(
        monkeypatch,
        InvestmentProductsHandler().GET,
        params={"include_invalidated": "1", "page_size": "20"},
    )

    assert payload["status"] == "success"
    assert payload["pagination"]["total"] == 1
    assert payload["entries"][0]["source_type"] == "cache"
    assert payload["entries"][0]["source_cache_key"] == cache_key
```

- [ ] **Step 2: Run test and verify red/green depending on Task 1**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business.py::test_generated_history_api_reads_backfilled_products_not_legacy_sources -q
```

Expected before implementation: FAIL if products API cannot see backfilled rows. Expected after Task 1: PASS.

- [ ] **Step 3: Remove legacy merge from history path**

In `channel/web/web_channel.py`:

- Stop using `_investment_list_merged_cache_history()` for the generated history page.
- Keep `InvestmentProductsHandler.GET` as the generated-history API.
- If `InvestmentCacheHandler.GET` remains, make it return an error or a product-backed alias, not direct legacy rows:

```python
class InvestmentCacheHandler:
    def GET(self):
        return InvestmentProductsHandler().GET()
```

If method reuse is awkward, extract a helper:

```python
def _investment_products_payload(params) -> dict:
    ...
```

Then both handlers can call the helper while still reading only `products`.

- [ ] **Step 4: Remove legacy dedupe helper usage**

Delete or stop calling:

- `_investment_list_legacy_history_without_product_sources`
- `_investment_product_exists_for_source_condition`
- `_investment_visible_product_conditions`
- `_investment_list_merged_cache_history`

Only remove the functions if no route or test imports them.

- [ ] **Step 5: Run API regression tests**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business.py::test_generated_history_api_reads_backfilled_products_not_legacy_sources tests/test_business.py::test_investment_products_api_lists_and_invalidates_products -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add channel/web/web_channel.py tests/test_business.py
git commit -m "Use products as generated history API"
```

---

### Task 4: Restore Category + Artifact Tree UI on Product API

**Files:**
- Modify: `channel/web/static/js/console.js`
- Modify: `tests/test_business_web_ui.py`

- [ ] **Step 1: Write failing static UI test**

Add to `tests/test_business_web_ui.py`:

```python
def test_generated_history_uses_product_api_with_category_and_artifact_tree():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    load_body = _js_function_body(js, "loadInvestmentProducts")
    render_body = _js_function_body(js, "renderInvestmentDailyGeneratedContent")
    detail_body = _js_function_body(js, "renderInvestmentGeneratedContentCategoryDetail")

    assert "investmentFetchJson(`/api/investment/products?${query.toString()}`)" in load_body
    assert "investmentFetchJson(`/api/investment/cache?${query.toString()}`)" not in load_body
    assert "renderInvestmentGeneratedContentHome(investmentGeneratedCategories(visibleEntries), visibleEntries)" in render_body
    assert "renderInvestmentProductsTable(visibleEntries)" not in render_body
    assert "investment-artifact-browser" in detail_body
    assert "renderInvestmentArtifactLazyTree(serviceType)" in detail_body
    assert "renderInvestmentArtifactViewer()" in detail_body
```

- [ ] **Step 2: Run test and verify red**

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business_web_ui.py::test_generated_history_uses_product_api_with_category_and_artifact_tree -q
```

Expected: FAIL because current loader uses `/api/investment/cache` and renders `renderInvestmentProductsTable()`.

- [ ] **Step 3: Change loader back to product API**

In `loadInvestmentProducts()`:

```javascript
const query = investmentRecordsQueryParams('products');
...
query.delete('business_date');
...
if (range.marketDate) {
    query.set('business_date', range.marketDate);
}
const data = await investmentFetchJson(`/api/investment/products?${query.toString()}`);
const entries = data.entries || [];
investmentRecordsState.data.products = {
    entries,
    business_dates: data.business_dates || investmentGeneratedDateValues([], entries),
};
investmentRecordsApplyPagination('products', data.pagination);
if (list) list.innerHTML = renderInvestmentDailyGeneratedContent(investmentRecordsState.data.products);
if (pagination) pagination.innerHTML = "";
```

- [ ] **Step 4: Restore category home rendering**

In `renderInvestmentDailyGeneratedContent(cacheData)` replace the table body with:

```javascript
const categories = investmentGeneratedCategories(visibleEntries);
const content = investmentRecordsState.cacheCategory
    ? renderInvestmentGeneratedContentCategoryDetail(
        investmentRecordsState.cacheCategory,
        visibleEntries.filter(entry => investmentProductBusinessType(entry) === investmentRecordsState.cacheCategory),
    )
    : renderInvestmentGeneratedContentHome(categories, visibleEntries);
...
${content}
```

Do not render `renderInvestmentProductsTable(visibleEntries)` in the history home view.

- [ ] **Step 5: Keep the product table only as drawer/debug helper**

Do not delete `renderInvestmentProductsTable()` in this task if product drawers or tests still use it, but ensure the history content page no longer calls it.

- [ ] **Step 6: Run focused UI test**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add channel/web/static/js/console.js tests/test_business_web_ui.py
git commit -m "Restore product history artifact browser UI"
```

---

### Task 5: Make Artifact Browser Product-Only

**Files:**
- Modify: `business/records/records.py`
- Modify: `tests/test_business.py`

- [ ] **Step 1: Write failing artifact test**

Add to `tests/test_business.py`:

```python
def test_artifact_browser_lists_only_product_packages_after_backfill(business_env, tmp_path):
    from business.cache.cache_service import build_cache_key, write_cache_entry
    from business.config.constants import ServiceType
    from business.products.product_service import backfill_products_from_legacy_sources
    from business.records.records import list_artifact_packages_page

    output = tmp_path / "legacy-card.png"
    output.write_text("legacy", encoding="utf-8")
    cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, "300502.SZ", "2026-06-20", "v1")
    write_cache_entry(
        cache_key=cache_key,
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target="300502.SZ",
        market_date="2026-06-20",
        version_fingerprint="v1",
        output_files=[str(output)],
    )
    backfill_products_from_legacy_sources()

    packages, total = list_artifact_packages_page(service_type="technical_analysis")

    assert total == 1
    assert packages[0]["source_type"] == "product"
    assert packages[0]["file_count"] == 1
```

- [ ] **Step 2: Run test and verify current behavior**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business.py::test_artifact_browser_lists_only_product_packages_after_backfill -q
```

Expected before cleanup: FAIL if both product and legacy cache package are returned.

- [ ] **Step 3: Remove legacy package sources**

In `business/records/records.py::_artifact_package_sources()`:

- Remove direct query blocks for `investment_cache_entries`.
- Remove direct query blocks for `investment_daily_contents`.
- Keep `investment_request_records` only if it represents non-generated internal call artifacts that cannot become products. If those are generated outputs, convert them in Task 1 and remove the direct internal call block as well.

Product-only source should be:

```python
product_conditions = _product_artifact_conditions(service_type, start_date, end_date, keyword)
...
rows.extend({"kind": "product", "item": row} for row in product_rows)
return rows, total
```

- [ ] **Step 4: Make folder aggregation product-only**

In `list_artifact_folder_nodes()`, remove cache/content grouping blocks. Group only `investment_products` rows:

```python
product_grouped = (
    select(
        product_key_expr.label("key"),
        func.count().label("count"),
        func.max(investment_products.c.updated_at).label("updated_at"),
    )
    .where(*product_conditions)
    .group_by(product_key_expr)
)
```

- [ ] **Step 5: Run artifact tests**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business.py::test_artifact_browser_lists_only_product_packages_after_backfill tests/test_business.py::test_artifact_packages_include_unified_products_without_legacy_cache_or_content tests/test_business.py::test_artifact_product_package_output_files_have_path_file_urls_without_artifact_rows -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add business/records/records.py tests/test_business.py
git commit -m "Make artifact browser product only"
```

---

### Task 6: Remove Legacy Generated-History UI Paths

**Files:**
- Modify: `channel/web/static/js/console.js`
- Modify: `tests/test_business_web_ui.py`

- [ ] **Step 1: Write failing removal test**

Add to `tests/test_business_web_ui.py`:

```python
def test_generated_history_ui_has_no_legacy_cache_loader():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    assert "renderInvestmentCacheTableLegacy" not in js
    assert "renderInvestmentRecordsCacheTab" not in js
    assert "investmentFetchJson(`/api/investment/cache?${query.toString()}`)" not in js
```

- [ ] **Step 2: Run test and verify red**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business_web_ui.py::test_generated_history_ui_has_no_legacy_cache_loader -q
```

Expected: FAIL while legacy UI helpers remain.

- [ ] **Step 3: Remove unused legacy UI helpers**

Delete functions only if `rg` shows no remaining runtime references:

```powershell
rg -n "renderInvestmentCacheTableLegacy|renderInvestmentRecordsCacheTab|renderInvestmentCacheTable\\(" channel/web/static/js/console.js tests
```

Remove:

- `renderInvestmentCacheTableLegacy`
- `renderInvestmentCacheTable`
- `renderInvestmentRecordsCacheTab`
- old generated cache row helpers if no artifact tree path uses them

- [ ] **Step 4: Run removal test**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add channel/web/static/js/console.js tests/test_business_web_ui.py
git commit -m "Remove legacy generated history UI paths"
```

---

### Task 7: Focused Regression and Manual Review

**Files:**
- No code changes unless regressions are found.

- [ ] **Step 1: Run backend tests**

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business.py::test_backfill_products_from_legacy_cache_entries_is_idempotent tests/test_business.py::test_backfill_products_from_legacy_daily_content_preserves_status_and_text tests/test_business.py::test_generated_history_api_reads_backfilled_products_not_legacy_sources tests/test_business.py::test_artifact_browser_lists_only_product_packages_after_backfill -q
```

Expected: PASS.

- [ ] **Step 2: Run Web UI tests**

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business_web_ui.py -q
```

Expected: PASS.

- [ ] **Step 3: Run existing product regressions**

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business.py::test_investment_products_api_lists_and_invalidates_products tests/test_business.py::test_daily_content_publish_creates_active_product_and_archives_previous_product tests/test_business.py::test_technical_analysis_product_reuse_invalidates_old_product_without_overwriting -q
```

Expected: PASS.

- [ ] **Step 4: Manual Web checklist**

Open the Web console and verify:

- 历史内容 first screen shows category cards, not a raw table.
- 技术分析 category opens artifact tree and preview pane.
- 利率 category opens artifact tree and preview pane.
- 转债 category opens artifact tree and preview pane.
- Backfilled old technical-analysis cache appears as a product package.
- Backfilled old rate/convertible content appears as a product package.
- Invalidated product remains visible in history.
- 业务记录 page has no duplicate product tab.

- [ ] **Step 5: Commit manual-review fixes if any**

```powershell
git add <changed-files>
git commit -m "Fix product-only history web review issues"
```

---

## Completion Criteria

- `/api/investment/products` can show old and new generated outputs because old rows are backfilled into `products`.
- Historical generated content UI does not call `/api/investment/cache`.
- Artifact browser package/folder APIs do not read `cache_entries` or `daily_contents` directly for generated output history.
- The history page uses category cards plus artifact tree and preview pane.
- Legacy cache/content rows may remain in the database as archival source records, but they are not the Web history read model.
- Tests prove backfill idempotency, product-only API reads, product-only artifact browser reads, and restored UI structure.
