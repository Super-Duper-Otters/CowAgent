# Unified Business Products Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify technical-analysis, rate, convertible-bond, and component-generated outputs into one durable business product model with one validity field, one history view, and one cache/re-generate decision path.

**Architecture:** Add a canonical `products` table and `business.products.product_service` as the only new write path for generated outputs. Keep `request_records` as immutable business workflow records; treat existing `cache_entries`, `content_records`, and `artifacts` as legacy compatibility sources until their Web/API consumers are moved to the unified product API.

**Tech Stack:** Python, SQLAlchemy table metadata, Alembic migrations, PostgreSQL, web.py handlers, vanilla JavaScript console UI, pytest static and backend tests.

---

## Current Code Map

**Canonical workflow record**
- `business/schema/tables.py`: defines `request_records`, `content_records`, `artifacts`, `cache_entries`.
- `business/records/records.py`: creates and updates request records, lists request/content/artifact packages, exposes `list_output_files()`.
- `business/records/cleanup.py`: currently only deletes runtime test data and expired admin sessions.

**Generated output sources today**
- `business/cache/cache_service.py`: technical-analysis cache records, history merge for cache/content, cache invalidation.
- `business/content/technical_analysis.py`: finds active technical-analysis cache entries and generates new output files.
- `business/content/technical_analysis_handler.py`: writes technical-analysis cache and request success/failure records.
- `business/content/daily_content.py`: creates, generates, publishes, archives, invalidates, and expires rate/convertible-bond content records.
- `business/content/daily_content_handler.py`: returns active daily content and writes request records.
- `business/artifacts/artifact_service.py`: archives files and records file index rows in `artifacts`.

**Web/API display surfaces that must be reviewed and migrated**
- `channel/web/web_channel.py`
  - `InvestmentRequestRecordsHandler`
  - `InvestmentContentRecordsHandler`
  - `InvestmentCacheHandler`
  - `InvestmentCacheEntryInvalidateHandler`
  - `InvestmentCacheClearHandler`
  - `InvestmentArtifactPackagesHandler`
  - `InvestmentArtifactFoldersHandler`
- `channel/web/static/js/console.js`
  - records tabs: requests, backend requests, contents, cache, audits
  - generated content view: `renderInvestmentDailyGeneratedContent()`
  - cache/category rows: `renderInvestmentCacheCompactRows()`
  - record drawers: `renderInvestmentRequestDrawer()`, `renderInvestmentContentDrawer()`, `renderInvestmentCacheDrawer()`
  - artifact browser: `renderInvestmentArtifactLazyTree()`, `openInvestmentArtifactFile()`

## Target Model

`request_records` remains the audit trail for "who asked for what and what happened".

`products` becomes the durable source of truth for generated outputs:

```text
product_id
business_type          technical_analysis | rate | convertible_bond | component:<key>
target_key             stock code, module key, or component target
target_label           display label
business_date          market/effective date used for validity lookup
logical_key            stable lookup key: business_type + target_key + business_date + version_fingerprint
version_fingerprint    generator/template/data version
status                 active | invalidated | archived | failed
source_request_id      request_records.request_id when product came from a request
source_content_id      legacy content_records.content_id while content_records is still present
source_cache_key       legacy cache_entries.cache_key while cache_entries is still present
source_type            request | content | cache | component
source_files           JSON list
output_files           JSON list
text_content           generated text/markdown when applicable
metadata               JSON object for business-specific details
hit_count
expires_at
effective_at
invalidated_at
archived_at
created_at
updated_at
```

Unified rules:

- Product records are append-only for successful generations.
- Validity is determined only by `products.status`, `products.expires_at`, and file availability.
- Re-generation creates a new product row and marks the old active row invalidated or archived.
- Clearing cache means invalidating active products for the selected business scope.
- History shows products by default with active/effective rows; "include invalidated" shows inactive product history.
- File links are read from `products.output_files`; `artifacts` remains a temporary compatibility index only while old drawers and `/api/file?id=` still need it.

---

### Task 1: Schema and Product Service Skeleton

**Files:**
- Modify: `business/schema/tables.py`
- Create: `migrations/business/versions/20260624_0025_unified_products.py`
- Create: `business/products/__init__.py`
- Create: `business/products/product_service.py`
- Test: `tests/integration/test_business_postgres.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Add failing schema test**

Add assertions to `tests/integration/test_business_postgres.py::test_postgres_runs_critical_business_flows`:

```python
assert inspector.has_table("products")
product_columns = {column["name"] for column in inspector.get_columns("products")}
assert {
    "product_id",
    "business_type",
    "target_key",
    "target_label",
    "business_date",
    "logical_key",
    "version_fingerprint",
    "status",
    "source_request_id",
    "source_content_id",
    "source_cache_key",
    "source_type",
    "source_files",
    "output_files",
    "text_content",
    "metadata",
    "hit_count",
    "expires_at",
    "effective_at",
    "invalidated_at",
    "archived_at",
    "created_at",
    "updated_at",
}.issubset(product_columns)
```

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/integration/test_business_postgres.py::test_postgres_runs_critical_business_flows -q
```

Expected: skipped when `COWAGENT_TEST_POSTGRES_URL` is absent; fails in configured PostgreSQL because `products` does not exist.

- [ ] **Step 2: Add product table metadata**

In `business/schema/tables.py`, add `investment_products = Table(...)` after `investment_cache_entries`:

```python
investment_products = Table(
    "products",
    metadata,
    Column("product_id", Text, primary_key=True),
    Column("business_type", Text, nullable=False),
    Column("target_key", Text, nullable=False),
    Column("target_label", Text),
    Column("business_date", Text),
    Column("logical_key", Text, nullable=False),
    Column("version_fingerprint", Text),
    Column("status", Text, nullable=False),
    Column("source_request_id", Text),
    Column("source_content_id", Text),
    Column("source_cache_key", Text),
    Column("source_type", Text),
    Column("source_files", Text, nullable=False, server_default="[]"),
    Column("output_files", Text, nullable=False, server_default="[]"),
    Column("text_content", Text),
    Column("metadata", Text, key="product_metadata"),
    Column("hit_count", Integer, nullable=False, server_default="0"),
    Column("expires_at", Text),
    Column("effective_at", Text),
    Column("invalidated_at", Text),
    Column("archived_at", Text),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Index("idx_products_lookup", "business_type", "target_key", "business_date", "version_fingerprint", "status"),
    Index("idx_products_logical_status", "logical_key", "status"),
    Index("idx_products_business_date", "business_type", "business_date", "status"),
)
products = investment_products
```

- [ ] **Step 3: Add Alembic migration**

Create `migrations/business/versions/20260624_0025_unified_products.py`:

```python
# encoding:utf-8
"""unified business products"""

from alembic import op
import sqlalchemy as sa


revision = "20260624_0025"
down_revision = "20260616_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("product_id", sa.Text(), primary_key=True),
        sa.Column("business_type", sa.Text(), nullable=False),
        sa.Column("target_key", sa.Text(), nullable=False),
        sa.Column("target_label", sa.Text()),
        sa.Column("business_date", sa.Text()),
        sa.Column("logical_key", sa.Text(), nullable=False),
        sa.Column("version_fingerprint", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("source_request_id", sa.Text()),
        sa.Column("source_content_id", sa.Text()),
        sa.Column("source_cache_key", sa.Text()),
        sa.Column("source_type", sa.Text()),
        sa.Column("source_files", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("output_files", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("text_content", sa.Text()),
        sa.Column("metadata", sa.Text()),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.Text()),
        sa.Column("effective_at", sa.Text()),
        sa.Column("invalidated_at", sa.Text()),
        sa.Column("archived_at", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "idx_products_lookup",
        "products",
        ["business_type", "target_key", "business_date", "version_fingerprint", "status"],
    )
    op.create_index("idx_products_logical_status", "products", ["logical_key", "status"])
    op.create_index("idx_products_business_date", "products", ["business_type", "business_date", "status"])


def downgrade() -> None:
    op.drop_index("idx_products_business_date", table_name="products")
    op.drop_index("idx_products_logical_status", table_name="products")
    op.drop_index("idx_products_lookup", table_name="products")
    op.drop_table("products")
```

- [ ] **Step 4: Add service tests**

Add to `tests/test_business.py`:

```python
def test_product_service_appends_and_invalidates_active_product(business_env, tmp_path):
    from business.products.product_service import create_product, find_active_product, invalidate_active_products, list_products_page

    first_file = tmp_path / "first.png"
    second_file = tmp_path / "second.png"
    first_file.write_text("first", encoding="utf-8")
    second_file.write_text("second", encoding="utf-8")

    first = create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="300502 新易盛",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(first_file)],
        source_type="request",
        source_request_id="req-first",
    )
    active = find_active_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        business_date="2026-06-24",
        version_fingerprint="v1",
    )
    assert active and active.product_id == first.product_id

    assert invalidate_active_products(
        business_type="technical_analysis",
        target_key="300502.SZ",
        business_date="2026-06-24",
        version_fingerprint="v1",
    ) == 1
    second = create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="300502 新易盛",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(second_file)],
        source_type="request",
        source_request_id="req-second",
    )

    active = find_active_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        business_date="2026-06-24",
        version_fingerprint="v1",
    )
    assert active and active.product_id == second.product_id
    rows, total = list_products_page(include_invalidated=True, business_type="technical_analysis")
    assert total == 2
    assert {row.product_id for row in rows} == {first.product_id, second.product_id}
    assert {row.status for row in rows} == {"active", "invalidated"}
```

- [ ] **Step 5: Implement `product_service.py`**

Create a focused service with these public functions:

```python
PRODUCT_STATUS_ACTIVE = "active"
PRODUCT_STATUS_INVALIDATED = "invalidated"
PRODUCT_STATUS_ARCHIVED = "archived"
PRODUCT_STATUS_FAILED = "failed"

def product_logical_key(*, business_type: str, target_key: str, business_date: str, version_fingerprint: str) -> str:
    ...

def create_product(...):
    ...

def find_active_product(...):
    ...

def invalidate_active_products(...):
    ...

def increment_product_hit(product_id: str) -> None:
    ...

def list_products_page(...):
    ...
```

Implementation requirements:

- `create_product()` always inserts a new `product_id`.
- `find_active_product()` filters `status = active`, `expires_at` empty or future, and checks every `output_files` path exists.
- If a selected active product has missing files, mark it `invalidated` and return `None`.
- `invalidate_active_products()` only updates active rows to invalidated and sets `invalidated_at`.
- No function physically deletes product rows.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business.py::test_product_service_appends_and_invalidates_active_product -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add business/schema/tables.py migrations/business/versions/20260624_0025_unified_products.py business/products/__init__.py business/products/product_service.py tests/test_business.py tests/integration/test_business_postgres.py
git commit -m "Add unified business product model"
```

---

### Task 2: Technical Analysis Uses Products for Validity and Reuse

**Files:**
- Modify: `business/content/technical_analysis.py`
- Modify: `business/content/technical_analysis_handler.py`
- Modify: `business/cache/cache_service.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Add failing product-backed technical-analysis test**

Add to `tests/test_business.py`:

```python
def test_technical_analysis_product_reuse_invalidates_old_product_without_overwriting(business_env, tmp_path, monkeypatch):
    from business.config.constants import ServiceType
    from business.products.product_service import find_active_product, list_products_page
    from business.content.technical_analysis_handler import handle_technical_analysis
    from business.routing.router import RouteResult

    output_one = tmp_path / "one.png"
    chart_one = tmp_path / "chart-one.png"
    report_one = tmp_path / "one.md"
    output_two = tmp_path / "two.png"
    chart_two = tmp_path / "chart-two.png"
    report_two = tmp_path / "two.md"
    for path in [output_one, chart_one, report_one, output_two, chart_two, report_two]:
        path.write_text(path.name, encoding="utf-8")

    calls = iter([
        (str(output_one), str(chart_one), str(report_one)),
        (str(output_two), str(chart_two), str(report_two)),
    ])

    def fake_runner(openid, raw_input, target_text, *, cache_context=None):
        from business.content.technical_analysis import TechnicalAnalysisResult
        card, chart, report = next(calls)
        return TechnicalAnalysisResult(
            True,
            card,
            chart,
            report,
            output_files=[card, chart, report],
            normalized_target="300502.SZ",
            stock_code="300502.SZ",
            stock_name="新易盛",
            market_date="2026-06-24",
            version_fingerprint="v1",
            cache_key="legacy-cache-key",
            cache_hit=False,
        )

    route = RouteResult(True, ServiceType.TECHNICAL_ANALYSIS, "300502", raw_input="技术分析 300502")
    first = handle_technical_analysis("web", "技术分析 300502", route, technical_analysis_handler=fake_runner, skip_permission=True)
    assert first.success is True
    assert find_active_product(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="300502.SZ",
        business_date="2026-06-24",
        version_fingerprint="v1",
    )

    from business.products.product_service import invalidate_active_products
    invalidate_active_products(
        business_type=str(ServiceType.TECHNICAL_ANALYSIS),
        target_key="300502.SZ",
        business_date="2026-06-24",
        version_fingerprint="v1",
    )
    second = handle_technical_analysis("web", "技术分析 300502", route, technical_analysis_handler=fake_runner, skip_permission=True)
    assert second.success is True
    products, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.TECHNICAL_ANALYSIS))
    assert total == 2
    assert [item.status for item in products].count("active") == 1
    assert [item.status for item in products].count("invalidated") == 1
```

- [ ] **Step 2: Add product lookup in technical analysis**

In `business/content/technical_analysis.py`, replace direct cache lookup for technical-analysis reuse with product lookup first:

```python
from business.products.product_service import find_active_product, increment_product_hit

product = find_active_product(
    business_type=str(ServiceType.TECHNICAL_ANALYSIS),
    target_key=symbol,
    business_date=resolved_market_date.market_date,
    version_fingerprint=cache_lookup_version,
)
if product is not None:
    increment_product_hit(product.product_id)
    output_files = product.output_files
    return TechnicalAnalysisResult(
        True,
        output_files[0] if output_files else "",
        output_files[1] if len(output_files) > 1 else "",
        output_files[2] if len(output_files) > 2 else "",
        output_files=output_files,
        normalized_target=symbol,
        stock_code=symbol,
        stock_name=target_info.stock_name,
        market_date=product.business_date,
        version_fingerprint=product.version_fingerprint,
        cache_key=product.product_id,
        cache_hit=True,
    )
```

Keep legacy `cache_entries` lookup as a fallback for old data until migration is complete.

- [ ] **Step 3: Write product on successful generation**

In `business/content/technical_analysis_handler.py`, after output files are archived and before request success is returned:

```python
from business.products.product_service import create_product, invalidate_active_products

invalidate_active_products(
    business_type=str(ServiceType.TECHNICAL_ANALYSIS),
    target_key=result.normalized_target,
    business_date=result.market_date,
    version_fingerprint=result.version_fingerprint,
)
product = create_product(
    business_type=str(ServiceType.TECHNICAL_ANALYSIS),
    target_key=result.normalized_target,
    target_label=" ".join(part for part in [result.stock_code, result.stock_name] if part),
    business_date=result.market_date,
    version_fingerprint=result.version_fingerprint,
    output_files=record_output_files,
    source_type="request",
    source_request_id=request_id,
    source_cache_key=result.cache_key,
    metadata={
        "program_version": result.program_version,
        "ta_version": result.ta_version,
        "renderer_version": result.renderer_version,
        "template_version": result.template_version,
    },
)
```

Set the reply `source_type` to `"product"` and `source_id` to `product.product_id`.

- [ ] **Step 4: Keep legacy cache write as compatibility only**

Leave `write_business_cache()` in place in this task so old Web cache pages keep working, but mark it as compatibility in code comments and tests. Do not rely on `cache_entries` for new active-product decisions after product lookup is added.

- [ ] **Step 5: Run targeted tests**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business.py::test_technical_analysis_product_reuse_invalidates_old_product_without_overwriting -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add business/content/technical_analysis.py business/content/technical_analysis_handler.py business/cache/cache_service.py tests/test_business.py
git commit -m "Use unified products for technical analysis reuse"
```

---

### Task 3: Rate and Convertible-Bond Content Writes Products

**Files:**
- Modify: `business/content/daily_content.py`
- Modify: `business/content/daily_content_handler.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Add failing daily-content product test**

Add to `tests/test_business.py`:

```python
def test_daily_content_publish_creates_active_product_and_archives_previous_product(business_env, tmp_path):
    from business.config.constants import ServiceType, Status
    from business.content.daily_content import create_content_draft, set_content_effective
    from business.products.product_service import list_products_page

    first_image = tmp_path / "first-rate.png"
    second_image = tmp_path / "second-rate.png"
    first_image.write_text("first", encoding="utf-8")
    second_image.write_text("second", encoding="utf-8")

    first_id = create_content_draft(ServiceType.RATE, source_text="first source")
    second_id = create_content_draft(ServiceType.RATE, source_text="second source")
    set_content_effective(first_id, str(first_image), effective_date="2026-06-24")
    set_content_effective(second_id, str(second_image), effective_date="2026-06-24")

    products, total = list_products_page(include_invalidated=True, business_type=str(ServiceType.RATE))
    assert total == 2
    by_content = {item.source_content_id: item for item in products}
    assert by_content[first_id].status == "archived"
    assert by_content[second_id].status == "active"
    assert by_content[second_id].business_date == "2026-06-24"
    assert by_content[second_id].output_files
```

- [ ] **Step 2: Create product on publish**

In `set_content_effective()`, after final image is archived and the content row is marked effective:

```python
from business.products.product_service import archive_active_products, create_product

archive_active_products(
    business_type=str(final_service_type),
    target_key=module_key or str(final_service_type),
    business_date=normalized_effective_date,
)
create_product(
    business_type=str(final_service_type),
    target_key=module_key or str(final_service_type),
    target_label=module_key or str(final_service_type),
    business_date=normalized_effective_date,
    version_fingerprint=f"content-v{content_version}",
    output_files=[final_image] if final_image else [],
    source_type="content",
    source_content_id=content_id,
    text_content=item.get("generated_text") or "",
    expires_at=normalized_expires_at,
    effective_at=now,
    metadata={"module_key": module_key},
)
```

Add `archive_active_products()` to `product_service.py`; it updates matching active rows to `archived` and sets `archived_at`.

- [ ] **Step 3: Invalidate product on content invalidation and expiration**

In `invalidate_content()` and `mark_expired_daily_contents_invalidated()`, also update products with matching `source_content_id` or business scope to `invalidated`.

Use this service call:

```python
from business.products.product_service import invalidate_products_by_source

invalidate_products_by_source(source_content_id=content_id)
```

- [ ] **Step 4: Read active product in daily-content handler**

In `business/content/daily_content_handler.py`, keep `get_daily_content_business()` for compatibility, but make the successful reply carry `source_type="product"` and `source_id=<product_id>` when an active product is found for the content. This step prevents Web/公众号 responses from continuing to identify content and cache differently.

- [ ] **Step 5: Run targeted tests**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business.py::test_daily_content_publish_creates_active_product_and_archives_previous_product tests/test_business.py::test_daily_content_expiration_persists_invalidated_status -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add business/content/daily_content.py business/content/daily_content_handler.py business/products/product_service.py tests/test_business.py
git commit -m "Write daily content as unified products"
```

---

### Task 4: Unified Product API for Web Records and History

**Files:**
- Modify: `channel/web/web_channel.py`
- Modify: `business/products/product_service.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Add API test**

Add to `tests/test_business.py`:

```python
def test_investment_products_api_lists_and_invalidates_products(business_env, tmp_path):
    from business.products.product_service import create_product
    from channel.web.web_channel import InvestmentProductsHandler, InvestmentProductInvalidateHandler

    output = tmp_path / "product.png"
    output.write_text("image", encoding="utf-8")
    product = create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="300502 新易盛",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(output)],
        source_type="request",
        source_request_id="req-1",
    )

    payload = _call_investment_json_handler(
        lambda: InvestmentProductsHandler().GET(),
        params={"business_type": "technical_analysis", "include_invalidated": "1"},
    )
    assert payload["status"] == "success"
    assert payload["entries"][0]["product_id"] == product.product_id
    assert payload["entries"][0]["status"] == "active"

    invalidated = _call_investment_json_handler(lambda: InvestmentProductInvalidateHandler().POST(product.product_id))
    assert invalidated["status"] == "success"
    assert invalidated["invalidated"] is True
```

- [ ] **Step 2: Add Web handlers**

In `channel/web/web_channel.py`, add:

```python
class InvestmentProductsHandler:
    def GET(self):
        _require_investment_permission("cache.read")
        from business.products.product_service import list_products_page, list_product_business_dates
        params = web.input(page="1", page_size="80", business_type="", business_date="", start_date="", end_date="", keyword="", include_invalidated="")
        include_invalidated = str(getattr(params, "include_invalidated", "")).lower() in {"1", "true", "yes"}
        page, page_size = _investment_safe_pagination(params, 120)
        entries, total = list_products_page(
            page=page,
            page_size=page_size,
            business_type=getattr(params, "business_type", "") or "",
            business_date=getattr(params, "business_date", "") or "",
            start_date=_investment_date_bound(getattr(params, "start_date", "")),
            end_date=_investment_date_bound(getattr(params, "end_date", ""), end=True),
            keyword=getattr(params, "keyword", "") or "",
            include_invalidated=include_invalidated,
        )
        return _investment_json_response({
            "status": "success",
            "entries": [item.to_dict() for item in entries],
            "business_dates": list_product_business_dates(
                business_type=getattr(params, "business_type", "") or "",
                include_invalidated=include_invalidated,
            ),
            "pagination": _investment_pagination_payload(page, page_size, total),
        })


class InvestmentProductInvalidateHandler:
    def POST(self, product_id):
        admin = _require_investment_permission("cache.write")
        from business.products.product_service import invalidate_product
        invalidated = invalidate_product(product_id)
        _record_investment_operation(
            "product.invalidate",
            "product",
            target_id=product_id,
            admin=admin,
            detail={"invalidated": invalidated},
        )
        return _investment_json_response({"status": "success", "invalidated": invalidated})
```

Register routes:

```python
"/api/investment/products", "InvestmentProductsHandler",
"/api/investment/products/(.*)/invalidate", "InvestmentProductInvalidateHandler",
```

- [ ] **Step 3: Keep legacy cache API as alias**

Make `InvestmentCacheHandler.GET` call the new product list for product-backed rows first. Continue to include legacy `cache_entries` and `content_records` only when no product row exists for the same legacy source id.

- [ ] **Step 4: Run targeted API tests**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business.py::test_investment_products_api_lists_and_invalidates_products -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add channel/web/web_channel.py business/products/product_service.py tests/test_business.py
git commit -m "Expose unified products API"
```

---

### Task 5: Web Records UI Uses Products Instead of Cache/Content Split

**Files:**
- Modify: `channel/web/static/js/console.js`
- Test: `tests/test_business_web_ui.py`

- [ ] **Step 1: Add static UI tests**

Add to `tests/test_business_web_ui.py`:

```python
def test_investment_records_use_unified_products_api():
    js = Path("channel/web/static/js/console.js").read_text(encoding="utf-8")
    assert "/api/investment/products" in js
    assert "renderInvestmentProductsTable" in js
    assert "renderInvestmentCacheTableLegacy" in js
    assert "renderInvestmentContentRecordsTable" in js
    assert "renderInvestmentProductDrawer" in js
    assert "产物" in js
```

- [ ] **Step 2: Rename cache tab state to products**

In `investmentRecordsState`, add a `products` filter/data section and keep `cache` as compatibility only:

```javascript
products: {page: '1', page_size: '120', period_mode: 'day', business_date: investmentTodayDate()},
```

Use `products` for the generated output tab label and API calls.

- [ ] **Step 3: Add product table renderer**

Add:

```javascript
function renderInvestmentProductsTable(entries = []) {
    const rows = (Array.isArray(entries) ? entries : []).map(entry => `
        <tr>
            <td>${investmentServiceLabel(entry.business_type || entry.service_type)}</td>
            <td>${investmentRecordClamp(entry.target_label || entry.target_key || '-', 2, 46)}</td>
            <td>${escapeHtml(entry.business_date || '-')}</td>
            <td><span class="investment-badge ${investmentStatusClass(entry.status)}">${investmentStatusLabel(entry.status)}</span></td>
            <td>${investmentRecordFileSummary(entry.output_files || [], '未生成')}</td>
            <td>${escapeHtml(investmentFormatBeijingTime(entry.created_at || entry.updated_at) || '-')}</td>
            <td class="investment-row-actions">
                ${investmentIconButton('fa-circle-info', '详情', `openInvestmentRecordDrawer('product', '${investmentEncodedRecord(entry)}')`)}
                ${entry.status === 'active' ? investmentIconButtonIfCan('cache.write', 'fa-ban', '失效', `invalidateInvestmentProduct('${encodeURIComponent(entry.product_id || '')}')`, 'danger') : ''}
            </td>
        </tr>
    `).join('');
    return investmentRecordTableShell(`<table class="investment-table investment-records-table">
        <thead><tr><th>业务</th><th>对象</th><th>业务日期</th><th>有效性</th><th>产物</th><th>生成时间</th><th>操作</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="7" class="investment-empty">暂无产物</td></tr>'}</tbody>
    </table>`);
}
```

- [ ] **Step 4: Add product drawer**

Add:

```javascript
function renderInvestmentProductDrawer(record) {
    return `
        ${investmentDrawerSection('产物信息', investmentDrawerMeta([
            ['业务', investmentServiceLabel(record.business_type || record.service_type)],
            ['对象', escapeHtml(record.target_label || record.target_key || '-')],
            ['业务日期', escapeHtml(record.business_date || '-')],
            ['有效性', investmentStatusLabel(record.status)],
            ['版本', escapeHtml(record.version_fingerprint || '-')],
            ['命中次数', escapeHtml(String(record.hit_count || 0))],
            ['来源请求', escapeHtml(record.source_request_id || '-')],
        ]))}
        ${investmentDrawerSection('输出文件', `<div class="investment-detail-links">${investmentFileLinks(record.output_files || [])}</div>`)}
        ${investmentDrawerPre('生成文本', record.text_content || '')}
    `;
}
```

Update `renderInvestmentRecordDrawerBody()` so `type === 'product'` renders this drawer.

- [ ] **Step 5: Add product load/invalidate functions**

Add:

```javascript
async function loadInvestmentProducts() {
    const query = investmentRecordsQueryParams('products');
    const data = await investmentFetchJson(query.toString() ? `/api/investment/products?${query.toString()}` : '/api/investment/products');
    investmentRecordsState.data.products = {entries: data.entries || [], business_dates: data.business_dates || []};
    investmentRecordsApplyPagination('products', data.pagination);
    const list = document.getElementById('investment-records-list');
    if (list) list.innerHTML = renderInvestmentProductsTable(investmentRecordsState.data.products.entries);
}

async function invalidateInvestmentProduct(encodedProductId) {
    const productId = decodeURIComponent(encodedProductId || '');
    if (!productId) return;
    await investmentFetchJson(`/api/investment/products/${encodeURIComponent(productId)}/invalidate`, {method: 'POST'});
    await loadInvestmentProducts();
}
```

- [ ] **Step 6: Keep legacy displays visible only as compatibility**

Do not delete `renderInvestmentCacheTableLegacy()` or `renderInvestmentContentRecordsTable()` in this task. Stop using them for the main generated-content tab after product API integration.

- [ ] **Step 7: Run static UI tests**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business_web_ui.py::test_investment_records_use_unified_products_api -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add channel/web/static/js/console.js tests/test_business_web_ui.py
git commit -m "Show unified products in investment records UI"
```

---

### Task 6: Artifact Browser Reads Products as Packages

**Files:**
- Modify: `business/records/records.py`
- Modify: `channel/web/web_channel.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Add artifact package test**

Add to `tests/test_business.py`:

```python
def test_artifact_packages_include_unified_products_without_legacy_cache_or_content(business_env, tmp_path):
    from business.products.product_service import create_product
    from business.records.records import list_artifact_packages_page

    image = tmp_path / "card.png"
    report = tmp_path / "report.md"
    image.write_text("image", encoding="utf-8")
    report.write_text("report", encoding="utf-8")
    product = create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="300502 新易盛",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(image), str(report)],
        source_type="request",
        source_request_id="req-product",
    )

    packages, total = list_artifact_packages_page(service_type="technical_analysis", start_date="2026-06-24", end_date="2026-06-24")
    assert total == 1
    assert packages[0]["package_id"] == product.product_id
    assert packages[0]["source_type"] == "product"
    assert packages[0]["file_count"] == 2
```

- [ ] **Step 2: Add products as first package source**

In `business/records/records.py`, update `_artifact_package_sources()`:

```python
from business.products.product_service import list_products_page

product_rows, product_total = list_products_page(
    page=1,
    page_size=1000,
    business_type=str(service_type or ""),
    start_date=start_date,
    end_date=end_date,
    keyword=keyword,
    include_invalidated=True,
)
total += product_total
rows.extend({"kind": "product", "item": item.to_dict()} for item in product_rows)
```

Sort products with existing package rows by generated date. Deduplicate legacy cache/content rows when their source id matches a product source id.

- [ ] **Step 3: Render product package details**

Add `_row_to_product_artifact_package(item)` and make `list_artifact_packages_page()` dispatch `kind == "product"` to it:

```python
def _row_to_product_artifact_package(item: dict) -> dict:
    output_files = _load_list(item.get("output_files"))
    return {
        "level": "package",
        "key": item["product_id"],
        "package_id": item["product_id"],
        "source_type": "product",
        "label": item.get("target_label") or item.get("target_key") or "产物",
        "service_type": item.get("business_type") or "",
        "market_date": _date_part(item.get("created_at") or ""),
        "generated_at": item.get("created_at") or "",
        "generated_date": _date_part(item.get("created_at") or ""),
        "business_date": item.get("business_date") or "",
        "normalized_target": item.get("target_key") or "",
        "version_fingerprint": item.get("version_fingerprint") or "",
        "product_id": item["product_id"],
        "file_count": len(output_files),
        "hit_count": int(item.get("hit_count") or 0),
        "updated_at": item.get("updated_at") or "",
    }
```

- [ ] **Step 4: Serve product package files**

Update the artifact package file loader so when `package_id` is a product id, it returns virtual file payloads from `products.output_files` without requiring `artifacts` rows.

- [ ] **Step 5: Run tests**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business.py::test_artifact_packages_include_unified_products_without_legacy_cache_or_content -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add business/records/records.py channel/web/web_channel.py tests/test_business.py
git commit -m "Read artifact packages from unified products"
```

---

### Task 7: Stop Deleting Artifact Index Rows on Request Failure

**Files:**
- Modify: `business/records/records.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Add failing preservation test**

Add to `tests/test_business.py`:

```python
def test_fail_request_record_preserves_artifact_index_rows(business_env, tmp_path):
    from business.config.constants import ErrorCode, ServiceType
    from business.records.records import create_request_record, fail_request_record, list_output_files, record_output_file

    output = tmp_path / "old.png"
    output.write_text("old", encoding="utf-8")
    request_id = create_request_record("openid-artifact", "技术分析 300502", ServiceType.TECHNICAL_ANALYSIS)
    record_output_file(request_id, str(output), "image", ServiceType.TECHNICAL_ANALYSIS, artifact_role="signal_card")

    fail_request_record(request_id, ErrorCode.SYSTEM_ERROR, detail="late failure", elapsed_ms=9)

    files = list_output_files(request_id)
    assert len(files) == 1
    assert files[0]["file_path"] == str(output)
```

- [ ] **Step 2: Remove destructive delete**

In `fail_request_record()`, remove:

```python
conn.execute(delete(investment_output_files).where(investment_output_files.c.owner_id == request_id))
```

Keep the request status update. The failed status is enough to indicate the request failed.

- [ ] **Step 3: Run test**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business.py::test_fail_request_record_preserves_artifact_index_rows -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add business/records/records.py tests/test_business.py
git commit -m "Preserve artifact indexes on request failure"
```

---

### Task 8: Legacy Compatibility and Cleanup Boundaries

**Files:**
- Modify: `business/cache/cache_service.py`
- Modify: `business/content/daily_content.py`
- Modify: `business/records/cleanup.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Add cleanup boundary test**

Add to `tests/test_business.py`:

```python
def test_cleanup_does_not_delete_products_or_legacy_product_sources(business_env, tmp_path):
    from business.products.product_service import create_product, list_products_page
    from business.records.cleanup import cleanup_useless_business_records

    output = tmp_path / "product.png"
    output.write_text("image", encoding="utf-8")
    create_product(
        business_type="technical_analysis",
        target_key="300502.SZ",
        target_label="300502 新易盛",
        business_date="2026-06-24",
        version_fingerprint="v1",
        output_files=[str(output)],
        source_type="request",
        source_request_id="req-cleanup",
    )

    cleanup_useless_business_records(now="2026-06-25T00:00:00+00:00", dry_run=False)
    products, total = list_products_page(include_invalidated=True)
    assert total == 1
    assert products[0].target_key == "300502.SZ"
```

- [ ] **Step 2: Mark legacy write functions**

Add short comments to legacy write paths:

```python
# Compatibility path: new product validity decisions use business.products.product_service.
```

Apply to:

- `write_cache_entry()`
- `set_content_effective()` legacy content update block
- `record_artifact()`

- [ ] **Step 3: Confirm cleanup stays non-destructive**

Ensure `cleanup_useless_business_records()` does not import or delete:

- `investment_products`
- `investment_cache_entries`
- `investment_daily_contents`
- `investment_request_records`
- `investment_output_files`

- [ ] **Step 4: Run focused regression tests**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business.py::test_cleanup_does_not_delete_products_or_legacy_product_sources tests/test_business.py::test_business_record_cleanup_dry_run_and_execute_remove_useless_records -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add business/cache/cache_service.py business/content/daily_content.py business/records/cleanup.py tests/test_business.py
git commit -m "Document product compatibility cleanup boundaries"
```

---

### Task 9: Focused Regression and Manual Web Review

**Files:**
- No code changes unless regressions are found.

- [ ] **Step 1: Run backend product tests**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business.py::test_product_service_appends_and_invalidates_active_product tests/test_business.py::test_technical_analysis_product_reuse_invalidates_old_product_without_overwriting tests/test_business.py::test_daily_content_publish_creates_active_product_and_archives_previous_product tests/test_business.py::test_investment_products_api_lists_and_invalidates_products tests/test_business.py::test_artifact_packages_include_unified_products_without_legacy_cache_or_content tests/test_business.py::test_fail_request_record_preserves_artifact_index_rows -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run Web UI static tests**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business_web_ui.py -q
```

Expected: PASS.

- [ ] **Step 3: Run business regression subset**

Run:

```powershell
$env:PYTHONPATH=(Get-Location).Path; pytest tests/test_business.py::test_web_channel_routes_business_commands_from_admin_chat tests/test_business.py::test_generated_content_history_treats_expired_daily_content_as_invalidated tests/test_business.py::test_daily_content_expiration_persists_invalidated_status -q
```

Expected: PASS.

- [ ] **Step 4: Manual Web review checklist**

Start the Web app using the project’s existing command for local manual review, then check:

- Records page has a unified "产物" view.
- Technical-analysis generated products appear in the product list.
- Rate and convertible-bond generated products appear in the same product list.
- Product detail drawer shows business type, target, business date, validity, version, files, and source request.
- "失效" changes product status and the product remains visible when including invalidated rows.
- Artifact browser can open files from product-backed packages.
- Request records still show external and backend request history.
- Content management page can still create/generate/publish rate and convertible-bond content during the compatibility phase.

- [ ] **Step 5: Commit manual-review fixes if needed**

If manual review requires fixes:

```powershell
git add <changed-files>
git commit -m "Fix unified products web review issues"
```

---

## Completion Criteria

- All new generated outputs have a `products` row.
- Active/reusable output lookup uses `products.status = active`, expiration, and file availability.
- Re-generation never overwrites historical product rows.
- Cache clearing and content expiration only invalidate/archive products.
- Business records remain complete and are not used as the product validity source.
- Web records expose one product list for technical-analysis, rate, convertible-bond, and component products.
- Legacy cache/content/artifact APIs remain compatible during migration but are no longer the conceptual source of truth.
- No cleanup path deletes products, product source records, or business records.
