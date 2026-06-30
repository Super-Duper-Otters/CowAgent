# Stock Dictionary Asset Type And Multisource Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `asset_type` to the stock dictionary and evolve the refresh pipeline so Tushare, AkShare, and Baostock records normalize, deduplicate, and merge into one usable dictionary.

**Architecture:** Keep `market` as the real exchange/market (`SH`, `SZ`, `HK`, `US`, `SGE`, `SHFE`) and add `asset_type` for the instrument category (`a_share`, `hk_stock`, `us_stock`, `bond`, `convertible_bond`, `gold`, `futures`, `etf`, `index`). The provider-specific fetchers return normalized records, a shared merge function chooses the best row per canonical code, and the existing `stock_symbols` table remains the final lookup table.

**Tech Stack:** Python 3.12, SQLAlchemy 2, Alembic, PostgreSQL, pytest, Tushare, AkShare, Baostock.

---

## File Structure

- Modify: `business/schema/tables.py`
  - Add `asset_type` to `stock_symbols`.
  - Add an index for `asset_type`.
- Modify: `business/schema/db.py`
  - Make `upsert_stock_symbols()` write `asset_type`.
- Create: `migrations/business/versions/20260630_0031_stock_symbol_asset_type.py`
  - Add the database column, backfill existing rows, and create/drop the index.
- Modify: `business/content/stock_resolver.py`
  - Add canonical asset-type constants.
  - Infer `asset_type` for existing code paths.
  - Include `asset_type` in list/get/match APIs.
  - Add provider-normalized refresh and merge helpers.
- Modify: `scripts/refresh_business_stocks.py`
  - Extend source choices to provider and category level.
- Modify: `tests/test_business.py`
  - Add focused unit tests for schema-aware refresh, merge, provider dispatch, and ambiguity.
- Modify: `tests/integration/test_business_postgres.py`
  - Assert the PostgreSQL table includes `asset_type`.

## Asset Type Rules

Use these canonical values:

```python
ASSET_TYPE_A_SHARE = "a_share"
ASSET_TYPE_HK_STOCK = "hk_stock"
ASSET_TYPE_US_STOCK = "us_stock"
ASSET_TYPE_INDEX = "index"
ASSET_TYPE_ETF = "etf"
ASSET_TYPE_FUND = "fund"
ASSET_TYPE_BOND = "bond"
ASSET_TYPE_CONVERTIBLE_BOND = "convertible_bond"
ASSET_TYPE_GOLD = "gold"
ASSET_TYPE_FUTURES = "futures"
ASSET_TYPE_OPTION = "option"
ASSET_TYPE_FX = "fx"
```

`market` remains the exchange/market:

```text
600519.SH   market=SH    asset_type=a_share
510300.SH   market=SH    asset_type=etf
113000.SH   market=SH    asset_type=convertible_bond
019547.SH   market=SH    asset_type=bond
AU9999.SGE  market=SGE   asset_type=gold
rb2410.SHFE market=SHFE  asset_type=futures
00700.HK    market=HK    asset_type=hk_stock
AAPL.US     market=US    asset_type=us_stock
```

## Source Priority

Use deterministic source priority during merge:

```python
SOURCE_PRIORITY = {
    "tushare": 100,
    "baostock": 80,
    "akshare": 60,
}
```

When two records share the same canonical `code`, keep the higher priority record. If the higher priority name is empty and a lower priority name is present, use the lower priority name. Do not merge two rows with the same display name but different codes; name collisions must remain ambiguous at lookup time.

---

### Task 1: Add `asset_type` To The Schema

**Files:**
- Modify: `business/schema/tables.py`
- Modify: `business/schema/db.py`
- Create: `migrations/business/versions/20260630_0031_stock_symbol_asset_type.py`
- Test: `tests/test_business.py`
- Test: `tests/integration/test_business_postgres.py`

- [ ] **Step 1: Write the failing unit test for asset_type persistence**

Add this test near the existing stock resolver tests in `tests/test_business.py`:

```python
def test_stock_resolver_persists_asset_type(business_env):
    from business.content import stock_resolver as stock_resolver

    assert stock_resolver.refresh_stock_symbols(
        [
            {
                "code": "510300.SH",
                "name": "沪深300ETF",
                "market": "SH",
                "asset_type": "etf",
                "source": "akshare_etf",
            },
            {
                "code": "600519.SH",
                "name": "贵州茅台",
                "market": "SH",
                "source": "tushare_a",
            },
        ],
        source="mixed-test",
    ) == 2

    rows = {row["code"]: row for row in stock_resolver.list_stock_symbols(limit=10)}
    assert rows["510300.SH"]["asset_type"] == "etf"
    assert rows["600519.SH"]["asset_type"] == "a_share"
```

- [ ] **Step 2: Write the failing PostgreSQL schema test**

Update the stock table assertion in `tests/integration/test_business_postgres.py`:

```python
stock_columns = {column["name"] for column in inspector.get_columns("stock_symbols")}
assert {
    "code",
    "name",
    "market",
    "asset_type",
    "ts_code",
    "source",
    "updated_at",
}.issubset(stock_columns)
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
py -m pytest tests/test_business.py -k "persists_asset_type" -q
```

Expected: FAIL because `asset_type` is not returned by `list_stock_symbols()`.

- [ ] **Step 4: Add the SQLAlchemy column and index**

In `business/schema/tables.py`, update `investment_stock_symbols`:

```python
investment_stock_symbols = Table(
    "stock_symbols",
    metadata,
    Column("code", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("market", Text, nullable=False),
    Column("asset_type", Text, nullable=False, server_default="a_share"),
    Column("ts_code", Text),
    Column("source", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Index("idx_stock_symbols_name", "name"),
    Index("idx_stock_symbols_asset_type", "asset_type"),
    Index("idx_stock_symbols_updated", "updated_at"),
)
```

- [ ] **Step 5: Add the Alembic migration**

Create `migrations/business/versions/20260630_0031_stock_symbol_asset_type.py`:

```python
# encoding:utf-8
"""add stock symbol asset type"""

from alembic import op
import sqlalchemy as sa


revision = "20260630_0031"
down_revision = "20260630_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stock_symbols", sa.Column("asset_type", sa.Text(), nullable=True))
    op.execute(
        """
        update stock_symbols
        set asset_type = case
            when market = 'HK' then 'hk_stock'
            when market = 'US' then 'us_stock'
            else 'a_share'
        end
        where asset_type is null or asset_type = ''
        """
    )
    op.alter_column("stock_symbols", "asset_type", nullable=False, server_default="a_share")
    op.create_index("idx_stock_symbols_asset_type", "stock_symbols", ["asset_type"])


def downgrade() -> None:
    op.drop_index("idx_stock_symbols_asset_type", table_name="stock_symbols")
    op.drop_column("stock_symbols", "asset_type")
```

- [ ] **Step 6: Update upsert to write `asset_type`**

In `business/schema/db.py`, update the `set_` dict inside `upsert_stock_symbols()`:

```python
set_={
    "name": stmt.excluded.name,
    "market": stmt.excluded.market,
    "asset_type": stmt.excluded.asset_type,
    "ts_code": stmt.excluded.ts_code,
    "source": stmt.excluded.source,
    "updated_at": stmt.excluded.updated_at,
},
```

- [ ] **Step 7: Update stock resolver write and read paths**

In `business/content/stock_resolver.py`, add:

```python
def _infer_asset_type(code: str, market: str = "", row_asset_type: str = "") -> str:
    asset_type = str(row_asset_type or "").strip().lower()
    if asset_type:
        return asset_type
    market_value = str(market or "").strip().upper()
    if market_value == "HK":
        return "hk_stock"
    if market_value == "US":
        return "us_stock"
    if market_value in {"SGE", "COMEX"}:
        return "gold"
    if market_value in {"SHFE", "DCE", "CZCE", "CFFEX", "GFEX", "INE"}:
        return "futures"
    return "a_share"
```

Update `refresh_stock_symbols()` normalized row creation:

```python
asset_type = _infer_asset_type(code, market, str(row.get("asset_type", "")))
normalized_rows.append(
    {
        "code": code,
        "name": name,
        "market": market,
        "asset_type": asset_type,
        "ts_code": ts_code,
        "source": row_source,
        "updated_at": updated_at,
    }
)
```

Update all selects that return stock symbol rows to include `table.c.asset_type`.

- [ ] **Step 8: Run asset_type tests**

Run:

```bash
py -m pytest tests/test_business.py -k "stock_resolver and asset_type" -q
```

Expected: PASS.

- [ ] **Step 9: Commit schema work**

```bash
git add business/schema/tables.py business/schema/db.py business/content/stock_resolver.py migrations/business/versions/20260630_0031_stock_symbol_asset_type.py tests/test_business.py tests/integration/test_business_postgres.py
git commit -m "feat: add stock symbol asset type"
```

---

### Task 2: Normalize Provider Records Before Writing

**Files:**
- Modify: `business/content/stock_resolver.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Write failing tests for canonical records**

Add:

```python
def test_stock_resolver_normalizes_provider_records():
    from business.content import stock_resolver as stock_resolver

    rows = stock_resolver.normalize_symbol_records(
        [
            {"code": "sh.600519", "name": "贵州茅台", "source": "baostock", "asset_type": "a_share"},
            {"code": "00700", "name": "腾讯控股", "market": "HK", "source": "akshare", "asset_type": "hk_stock"},
            {"code": "AAPL", "name": "苹果", "market": "US", "source": "tushare", "asset_type": "us_stock"},
            {"code": "AU9999", "name": "Au99.99", "market": "SGE", "source": "akshare", "asset_type": "gold"},
        ]
    )

    by_name = {row["name"]: row for row in rows}
    assert by_name["贵州茅台"]["code"] == "600519.SH"
    assert by_name["贵州茅台"]["market"] == "SH"
    assert by_name["贵州茅台"]["asset_type"] == "a_share"
    assert by_name["腾讯控股"]["code"] == "00700.HK"
    assert by_name["苹果"]["code"] == "AAPL.US"
    assert by_name["Au99.99"]["code"] == "AU9999.SGE"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
py -m pytest tests/test_business.py -k "normalizes_provider_records" -q
```

Expected: FAIL because `normalize_symbol_records()` does not exist.

- [ ] **Step 3: Implement canonical code helpers**

In `business/content/stock_resolver.py`, extend `_standardize_code()` with source formats:

```python
_BAOSTOCK_CODE_RE = re.compile(r"(sh|sz|bj)\.(\d{6})", re.IGNORECASE)


def _standardize_code(value: str, market: str = "") -> str:
    code = str(value or "").strip().upper()
    market_value = str(market or "").strip().upper()
    baostock_match = _BAOSTOCK_CODE_RE.fullmatch(code)
    if baostock_match:
        exchange = baostock_match.group(1).upper()
        suffix = {"SH": "SH", "SZ": "SZ", "BJ": "BJ"}[exchange]
        return f"{baostock_match.group(2)}.{suffix}"
    if market_value == "HK" and re.fullmatch(r"\d{1,5}", code):
        return f"{code.zfill(5)}.HK"
    if market_value == "US" and "." not in code:
        return f"{code}.US"
    if market_value and "." not in code and market_value not in {"SH", "SZ", "BJ"}:
        return f"{code}.{market_value}"
    # keep the existing cases below this block
```

Keep the existing A-share, HK, US, and bare six-digit logic after this new block.

- [ ] **Step 4: Implement `normalize_symbol_records()`**

Add:

```python
def normalize_symbol_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        raw_market = _first_text(row, ("market", "exchange", "交易所"))
        raw_code = _first_text(row, ("code", "ts_code", "symbol", "证券代码", "代码"))
        code = _standardize_code(raw_code, raw_market)
        market = _infer_market(code, raw_market)
        name = _first_text(row, ("name", "名称", "证券简称", "品种名称", "中文名称"))
        asset_type = _infer_asset_type(code, market, _first_text(row, ("asset_type",)))
        source = _first_text(row, ("source",))
        ts_code = _first_text(row, ("ts_code",)) or code
        if not code or not name or not market or not asset_type or not source:
            continue
        normalized.append(
            {
                "code": code,
                "name": name,
                "market": market,
                "asset_type": asset_type,
                "ts_code": ts_code,
                "source": source,
            }
        )
    return normalized
```

- [ ] **Step 5: Run normalization tests**

Run:

```bash
py -m pytest tests/test_business.py -k "normalizes_provider_records" -q
```

Expected: PASS.

- [ ] **Step 6: Commit normalization**

```bash
git add business/content/stock_resolver.py tests/test_business.py
git commit -m "feat: normalize stock symbol provider records"
```

---

### Task 3: Add Merge And Deduplication

**Files:**
- Modify: `business/content/stock_resolver.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Write failing merge tests**

Add:

```python
def test_stock_resolver_merges_sources_by_priority_and_code():
    from business.content import stock_resolver as stock_resolver

    merged = stock_resolver.merge_symbol_records(
        [
            {"code": "600519.SH", "name": "贵州茅台-AK", "market": "SH", "asset_type": "a_share", "source": "akshare_a", "ts_code": "600519.SH"},
            {"code": "600519.SH", "name": "贵州茅台", "market": "SH", "asset_type": "a_share", "source": "tushare_a", "ts_code": "600519.SH"},
            {"code": "113000.SH", "name": "可转债样例", "market": "SH", "asset_type": "convertible_bond", "source": "akshare_convertible_bond", "ts_code": "113000.SH"},
        ]
    )

    rows = {row["code"]: row for row in merged}
    assert len(rows) == 2
    assert rows["600519.SH"]["name"] == "贵州茅台"
    assert rows["600519.SH"]["source"] == "tushare_a"
    assert rows["113000.SH"]["asset_type"] == "convertible_bond"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
py -m pytest tests/test_business.py -k "merges_sources_by_priority" -q
```

Expected: FAIL because `merge_symbol_records()` does not exist.

- [ ] **Step 3: Implement source priority**

Add to `business/content/stock_resolver.py`:

```python
def _source_priority(source: str) -> int:
    value = str(source or "").strip().lower()
    if value.startswith("tushare"):
        return 100
    if value.startswith("baostock"):
        return 80
    if value.startswith("akshare"):
        return 60
    return 10
```

- [ ] **Step 4: Implement merge**

Add:

```python
def merge_symbol_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in normalize_symbol_records(rows):
        code = row["code"]
        current = merged.get(code)
        if current is None:
            merged[code] = row
            continue
        row_priority = _source_priority(row.get("source", ""))
        current_priority = _source_priority(current.get("source", ""))
        if row_priority > current_priority:
            if not row.get("name") and current.get("name"):
                row["name"] = current["name"]
            merged[code] = row
        elif not current.get("name") and row.get("name"):
            current["name"] = row["name"]
    return sorted(merged.values(), key=lambda item: (item["asset_type"], item["market"], item["code"]))
```

- [ ] **Step 5: Run merge tests**

Run:

```bash
py -m pytest tests/test_business.py -k "merges_sources_by_priority" -q
```

Expected: PASS.

- [ ] **Step 6: Commit merge logic**

```bash
git add business/content/stock_resolver.py tests/test_business.py
git commit -m "feat: merge stock symbol sources"
```

---

### Task 4: Refactor Existing Tushare Refresh To Use Asset Types

**Files:**
- Modify: `business/content/stock_resolver.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Update existing Tushare tests**

In `test_stock_resolver_refreshes_all_markets_from_tushare_with_explicit_functions`, add:

```python
assert rows["300502.SZ"]["asset_type"] == "a_share"
assert rows["00700.HK"]["asset_type"] == "hk_stock"
assert rows["AAPL.US"]["asset_type"] == "us_stock"
```

- [ ] **Step 2: Run test to verify it fails before implementation if Task 1 was skipped**

Run:

```bash
py -m pytest tests/test_business.py -k "refreshes_all_markets_from_tushare" -q
```

Expected after Task 1: PASS. Expected without Task 1: FAIL due missing `asset_type`.

- [ ] **Step 3: Update Tushare row construction**

In `refresh_a_share_symbols_from_tushare()`, add:

```python
"asset_type": "a_share",
```

In `refresh_hk_symbols_from_tushare()`, add:

```python
"asset_type": "hk_stock",
```

In `refresh_us_symbols_from_tushare()`, add:

```python
"asset_type": "us_stock",
```

- [ ] **Step 4: Run Tushare refresh tests**

Run:

```bash
py -m pytest tests/test_business.py -k "tushare and stock_resolver" -q
```

Expected: PASS.

- [ ] **Step 5: Commit Tushare refactor**

```bash
git add business/content/stock_resolver.py tests/test_business.py
git commit -m "feat: tag tushare stock symbols with asset type"
```

---

### Task 5: Add AkShare Dictionary Adapter

**Files:**
- Modify: `business/content/stock_resolver.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Write failing AkShare adapter test**

Add:

```python
def test_stock_resolver_refreshes_from_akshare_adapter(business_env, monkeypatch):
    from business.content import stock_resolver as stock_resolver

    fake_akshare = SimpleNamespace(
        stock_zh_a_spot_em=lambda: _FakeDataFrame([{"代码": "600519", "名称": "贵州茅台"}]),
        stock_hk_spot_em=lambda: _FakeDataFrame([{"代码": "00700", "名称": "腾讯控股"}]),
        stock_us_spot_em=lambda: _FakeDataFrame([{"代码": "AAPL", "名称": "苹果"}]),
        fund_etf_spot_em=lambda: _FakeDataFrame([{"代码": "510300", "名称": "沪深300ETF"}]),
        bond_zh_hs_cov_spot=lambda: _FakeDataFrame([{"代码": "113000", "名称": "可转债样例"}]),
        spot_quotations_sge=lambda: _FakeDataFrame([{"代码": "AU9999", "名称": "Au99.99"}]),
    )
    monkeypatch.setitem(sys.modules, "akshare", fake_akshare)

    result = stock_resolver.refresh_all_symbols_from_akshare()

    assert result["a_share"]["count"] == 1
    assert result["hk"]["count"] == 1
    assert result["us"]["count"] == 1
    assert result["etf"]["count"] == 1
    assert result["convertible_bond"]["count"] == 1
    assert result["gold"]["count"] == 1
    rows = {row["code"]: row for row in stock_resolver.list_stock_symbols(limit=20)}
    assert rows["510300.SH"]["asset_type"] == "etf"
    assert rows["113000.SH"]["asset_type"] == "convertible_bond"
    assert rows["AU9999.SGE"]["asset_type"] == "gold"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
py -m pytest tests/test_business.py -k "refreshes_from_akshare_adapter" -q
```

Expected: FAIL because `refresh_all_symbols_from_akshare()` does not exist.

- [ ] **Step 3: Implement AkShare import helper**

Add:

```python
def _akshare_client():
    return importlib.import_module("akshare")
```

- [ ] **Step 4: Implement AkShare refresh helper**

Add:

```python
def _refresh_akshare_frame(frame: Any, source: str, market: str, asset_type: str) -> int:
    rows = []
    for row in _records_from_frame(frame):
        item = dict(row)
        item["source"] = source
        item["market"] = market
        item["asset_type"] = asset_type
        rows.append(item)
    return refresh_stock_symbols(merge_symbol_records(rows), source=source)
```

- [ ] **Step 5: Implement AkShare market functions**

Add:

```python
def refresh_a_share_symbols_from_akshare() -> int:
    ak = _akshare_client()
    return _refresh_akshare_frame(ak.stock_zh_a_spot_em(), "akshare_a", "", "a_share")


def refresh_hk_symbols_from_akshare() -> int:
    ak = _akshare_client()
    return _refresh_akshare_frame(ak.stock_hk_spot_em(), "akshare_hk", "HK", "hk_stock")


def refresh_us_symbols_from_akshare() -> int:
    ak = _akshare_client()
    return _refresh_akshare_frame(ak.stock_us_spot_em(), "akshare_us", "US", "us_stock")


def refresh_etf_symbols_from_akshare() -> int:
    ak = _akshare_client()
    return _refresh_akshare_frame(ak.fund_etf_spot_em(), "akshare_etf", "SH", "etf")


def refresh_convertible_bond_symbols_from_akshare() -> int:
    ak = _akshare_client()
    return _refresh_akshare_frame(ak.bond_zh_hs_cov_spot(), "akshare_convertible_bond", "SH", "convertible_bond")


def refresh_gold_symbols_from_akshare() -> int:
    ak = _akshare_client()
    return _refresh_akshare_frame(ak.spot_quotations_sge(), "akshare_gold", "SGE", "gold")
```

- [ ] **Step 6: Implement AkShare all refresh**

Add:

```python
def refresh_all_symbols_from_akshare() -> dict[str, object]:
    result: dict[str, object] = {}
    for key, refresher in (
        ("a_share", refresh_a_share_symbols_from_akshare),
        ("hk", refresh_hk_symbols_from_akshare),
        ("us", refresh_us_symbols_from_akshare),
        ("etf", refresh_etf_symbols_from_akshare),
        ("convertible_bond", refresh_convertible_bond_symbols_from_akshare),
        ("gold", refresh_gold_symbols_from_akshare),
    ):
        try:
            result[key] = {"count": refresher()}
        except Exception as exc:
            result[key] = {"error": str(exc)}
    return result
```

- [ ] **Step 7: Run AkShare tests**

Run:

```bash
py -m pytest tests/test_business.py -k "akshare_adapter" -q
```

Expected: PASS.

- [ ] **Step 8: Commit AkShare adapter**

```bash
git add business/content/stock_resolver.py tests/test_business.py
git commit -m "feat: add akshare stock dictionary adapter"
```

---

### Task 6: Add Baostock Dictionary Adapter

**Files:**
- Modify: `business/content/stock_resolver.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Write failing Baostock adapter test**

Add:

```python
class _FakeBaoResult:
    error_code = "0"
    error_msg = ""
    fields = ["code", "code_name", "type", "status"]

    def __init__(self):
        self._rows = iter([["sh.600519", "贵州茅台", "1", "1"]])

    def next(self):
        try:
            self._current = next(self._rows)
            return True
        except StopIteration:
            return False

    def get_row_data(self):
        return self._current


def test_stock_resolver_refreshes_from_baostock_adapter(business_env, monkeypatch):
    from business.content import stock_resolver as stock_resolver

    calls = []
    fake_baostock = SimpleNamespace(
        login=lambda: SimpleNamespace(error_code="0", error_msg=""),
        logout=lambda: calls.append("logout"),
        query_stock_basic=lambda: _FakeBaoResult(),
    )
    monkeypatch.setitem(sys.modules, "baostock", fake_baostock)

    assert stock_resolver.refresh_a_share_symbols_from_baostock() == 1
    rows = {row["code"]: row for row in stock_resolver.list_stock_symbols(limit=10)}
    assert rows["600519.SH"]["name"] == "贵州茅台"
    assert rows["600519.SH"]["asset_type"] == "a_share"
    assert rows["600519.SH"]["source"] == "baostock_a"
    assert calls == ["logout"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
py -m pytest tests/test_business.py -k "baostock_adapter" -q
```

Expected: FAIL because `refresh_a_share_symbols_from_baostock()` does not exist.

- [ ] **Step 3: Implement Baostock ResultData conversion**

Add:

```python
def _baostock_result_to_records(result: Any) -> list[dict[str, Any]]:
    if result.error_code != "0":
        raise RuntimeError(result.error_msg)
    rows = []
    while result.next():
        rows.append(dict(zip(result.fields, result.get_row_data(), strict=False)))
    return rows
```

- [ ] **Step 4: Implement Baostock refresh**

Add:

```python
def refresh_a_share_symbols_from_baostock() -> int:
    baostock = importlib.import_module("baostock")
    login_result = baostock.login()
    if login_result.error_code != "0":
        raise RuntimeError(login_result.error_msg)
    try:
        records = []
        for row in _baostock_result_to_records(baostock.query_stock_basic()):
            records.append(
                {
                    "code": row.get("code", ""),
                    "name": row.get("code_name", ""),
                    "market": "",
                    "asset_type": "a_share",
                    "source": "baostock_a",
                    "ts_code": row.get("code", ""),
                }
            )
        return refresh_stock_symbols(merge_symbol_records(records), source="baostock_a")
    finally:
        baostock.logout()
```

- [ ] **Step 5: Implement Baostock all refresh**

Add:

```python
def refresh_all_symbols_from_baostock() -> dict[str, object]:
    try:
        return {"a_share": {"count": refresh_a_share_symbols_from_baostock()}}
    except Exception as exc:
        return {"a_share": {"error": str(exc)}}
```

- [ ] **Step 6: Run Baostock tests**

Run:

```bash
py -m pytest tests/test_business.py -k "baostock_adapter" -q
```

Expected: PASS.

- [ ] **Step 7: Commit Baostock adapter**

```bash
git add business/content/stock_resolver.py tests/test_business.py
git commit -m "feat: add baostock stock dictionary adapter"
```

---

### Task 7: Add Three-Source Refresh Orchestration

**Files:**
- Modify: `business/content/stock_resolver.py`
- Modify: `scripts/refresh_business_stocks.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Write failing orchestration test**

Add:

```python
def test_stock_resolver_refreshes_all_dictionary_sources(business_env, monkeypatch):
    from business.content import stock_resolver as stock_resolver

    monkeypatch.setattr(stock_resolver, "refresh_all_symbols_from_tushare", lambda: {"a_share": {"count": 2}})
    monkeypatch.setattr(stock_resolver, "refresh_all_symbols_from_akshare", lambda: {"etf": {"count": 3}})
    monkeypatch.setattr(stock_resolver, "refresh_all_symbols_from_baostock", lambda: {"a_share": {"count": 1}})

    assert stock_resolver.refresh_all_symbol_sources() == {
        "tushare": {"a_share": {"count": 2}},
        "akshare": {"etf": {"count": 3}},
        "baostock": {"a_share": {"count": 1}},
    }
```

- [ ] **Step 2: Implement orchestrator**

Add:

```python
def refresh_all_symbol_sources() -> dict[str, object]:
    result: dict[str, object] = {}
    for provider, refresher in (
        ("tushare", refresh_all_symbols_from_tushare),
        ("akshare", refresh_all_symbols_from_akshare),
        ("baostock", refresh_all_symbols_from_baostock),
    ):
        try:
            result[provider] = refresher()
        except Exception as exc:
            result[provider] = {"error": str(exc)}
    return result
```

- [ ] **Step 3: Update CLI source choices**

In `scripts/refresh_business_stocks.py`, change parser choices to:

```python
parser.add_argument(
    "--source",
    choices=("all", "tushare", "akshare", "baostock", "a_share", "hk", "us", "etf", "convertible_bond", "gold"),
    default="all",
)
```

Update `_build_auto_payload()` to call `stock_resolver.refresh_all_symbol_sources()`.

- [ ] **Step 4: Update CLI dispatch test**

In `test_refresh_business_stocks_script_dispatches_sources`, monkeypatch:

```python
monkeypatch.setattr(
    refresh_business_stocks.stock_resolver,
    "refresh_all_symbol_sources",
    lambda: calls.append("all") or {
        "tushare": {"a_share": {"count": 2}},
        "akshare": {"etf": {"count": 3}},
        "baostock": {"a_share": {"count": 1}},
    },
)
```

Adjust expected all count to `6`.

- [ ] **Step 5: Run CLI tests**

Run:

```bash
py -m pytest tests/test_business.py -k "refresh_business_stocks_script or refreshes_all_dictionary_sources" -q
```

Expected: PASS.

- [ ] **Step 6: Commit orchestration**

```bash
git add business/content/stock_resolver.py scripts/refresh_business_stocks.py tests/test_business.py
git commit -m "feat: orchestrate multisource stock dictionary refresh"
```

---

### Task 8: Update Name Resolution To Use All Trusted Sources

**Files:**
- Modify: `business/content/stock_resolver.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Write failing source-resolution test**

Replace `test_stock_resolver_ignores_non_tushare_rows_for_name_resolution` with:

```python
def test_stock_resolver_resolves_names_from_dictionary_sources(business_env):
    from business.content import stock_resolver as stock_resolver

    stock_resolver.refresh_stock_symbols(
        [{"code": "510300.SH", "name": "沪深300ETF", "market": "SH", "asset_type": "etf", "source": "akshare_etf"}],
        source="akshare_etf",
    )
    stock_resolver.refresh_stock_symbols(
        [{"code": "600519.SH", "name": "贵州茅台", "market": "SH", "asset_type": "a_share", "source": "baostock_a"}],
        source="baostock_a",
    )

    assert stock_resolver.resolve_stock("沪深300ETF") == ("510300.SH", None)
    assert stock_resolver.resolve_stock("贵州茅台") == ("600519.SH", None)
```

- [ ] **Step 2: Add trusted source predicate**

Add:

```python
def _trusted_dictionary_source_condition(table):
    return table.c.source.like("tushare%") | table.c.source.like("akshare%") | table.c.source.like("baostock%")
```

- [ ] **Step 3: Update name lookups**

In `_resolve_name_from_local()`, `list_exact_stock_name_matches()`, and `get_stock_symbol_by_code()`, replace the current Tushare-only condition:

```python
table.c.source.in_(("tushare_a", "tushare_hk", "tushare_us"))
```

with:

```python
_trusted_dictionary_source_condition(table)
```

- [ ] **Step 4: Run resolution tests**

Run:

```bash
py -m pytest tests/test_business.py -k "stock_resolver and resolves_names_from_dictionary_sources" -q
```

Expected: PASS.

- [ ] **Step 5: Commit resolution update**

```bash
git add business/content/stock_resolver.py tests/test_business.py
git commit -m "feat: resolve stock names from trusted dictionary sources"
```

---

### Task 9: Final Verification

**Files:**
- No source edits expected.

- [ ] **Step 1: Run focused stock dictionary tests**

Run:

```bash
py -m pytest tests/test_business.py -k "stock_resolver or refresh_business_stocks" -q
```

Expected: PASS.

- [ ] **Step 2: Run PostgreSQL integration test if PostgreSQL is configured**

Run:

```bash
py -m pytest tests/integration/test_business_postgres.py -q
```

Expected: PASS when the integration database is available. If the database is unavailable, record the exact skip or connection error in the final implementation notes.

- [ ] **Step 3: Run lint if configured for touched files**

Run:

```bash
py -m ruff check business/content/stock_resolver.py business/schema/tables.py business/schema/db.py scripts/refresh_business_stocks.py tests/test_business.py
```

Expected: PASS.

- [ ] **Step 4: Manual smoke test with mocked or configured providers**

Run:

```bash
py scripts/refresh_business_stocks.py --source all --json
```

Expected when dependencies and credentials are available: JSON with provider keys `tushare`, `akshare`, and `baostock`. Tushare may return an error when `tushare.token` is missing; AkShare and Baostock should still attempt independently.

- [ ] **Step 5: Commit final fixes**

```bash
git add business/content/stock_resolver.py business/schema/tables.py business/schema/db.py scripts/refresh_business_stocks.py tests/test_business.py tests/integration/test_business_postgres.py
git commit -m "test: verify multisource stock dictionary"
```

## Self-Review

- Spec coverage: The plan adds `asset_type`, preserves `market` as exchange, normalizes Tushare/AkShare/Baostock, deduplicates by canonical code, and updates lookup behavior.
- Placeholder scan: No task uses TBD/TODO or asks for unspecified tests.
- Type consistency: `asset_type`, `market`, `code`, `ts_code`, and `source` are used consistently across schema, resolver, and tests.
