# Investment PostgreSQL Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the investment business module run on either SQLite or PostgreSQL while keeping SQLite as the default local deployment mode.

**Architecture:** Introduce a database access layer for `business.investment` that hides driver differences, then migrate table creation to versioned migrations. Existing services continue to expose the same business APIs, but direct `sqlite3` usage and SQLite-specific SQL are moved behind adapters or replaced with portable SQLAlchemy Core statements.

**Tech Stack:** Python 3.12, SQLite, PostgreSQL, SQLAlchemy Core, Alembic, pytest, optional Docker PostgreSQL for integration tests.

---

## Scope

This plan covers only the investment business module:

- `business/investment/*`
- investment Web APIs in `channel/web/web_channel.py`
- refresh scripts under `scripts/`
- tests in `tests/test_investment_business.py`
- deployment/config docs

This plan does not migrate the global agent memory/session stores under `agent/memory/*`. Those modules also use SQLite, but they are separate subsystems and should not be changed in this work.

## Non-Negotiable Compatibility Rules

- SQLite remains the default when no database URL is configured.
- Existing local file database `investment/investment.db` must continue to work.
- PostgreSQL is opt-in through config/env.
- Existing Web/公众号 investment behavior must not change.
- Existing tests must pass on SQLite.
- PostgreSQL integration tests may be opt-in if Docker or a PG URL is available.
- File/image paths remain local filesystem paths in this phase. PostgreSQL support does not solve multi-machine file storage.

## Subagent Execution Rules

- Every task below must be implemented by a fresh subagent.
- The main conversation must dispatch only one implementation subagent at a time unless the tasks have fully disjoint write sets.
- After each subagent finishes, the main conversation must perform two reviews before starting the next task:
  - Specification review: verify the task's acceptance criteria and scope were met.
  - Code quality review: inspect changed files, run the task verification commands, and check for unintended rewrites.
- Do not let two subagents write the same file concurrently.
- Each subagent must use TDD for its task: add/adjust failing tests first, run them to confirm failure, implement, then run the specified verification commands.
- Each subagent final report must list changed files, RED/GREEN evidence, verification commands, and any risks.
- The main conversation owns final integration and full quality gates.

## Target Configuration

Supported configuration priority:

1. Environment variable: `COWAGENT_INVESTMENT_DATABASE_URL`
2. `config.json` key: `investment_database_url`
3. Existing SQLite fallback: `sqlite:///<storage_root>/investment.db`

Do not store the active database URL in `investment_configs`. That table lives inside the database being selected, so using it for initial connection selection creates a circular dependency.

Example URLs:

```text
sqlite:///C:/Users/Administrator/Documents/GitHub/CowAgent/investment/investment.db
postgresql+psycopg://cowagent:password@127.0.0.1:5432/cowagent
```

Recommended dependency additions:

```text
SQLAlchemy>=2.0
alembic>=1.13
psycopg[binary]>=3.2
```

## File Map

Create:

- `business/investment/db.py`
  - Owns engine creation, database URL resolution, connection context helpers, backend detection, row conversion helpers.
- `business/investment/schema.py`
  - Defines SQLAlchemy table metadata for all investment tables.
- `business/investment/migrations.py`
  - Thin programmatic migration runner used by app startup/tests.
- `migrations/investment/alembic.ini`
  - Investment-specific Alembic config.
- `migrations/investment/env.py`
  - Alembic environment using `business.investment.schema.metadata`.
- `migrations/investment/versions/20260525_0001_initial_investment_schema.py`
  - Initial schema migration.
- `scripts/migrate_investment_sqlite_to_pg.py`
  - One-way copy script from SQLite file to PostgreSQL.
- `docs/deployment/investment-postgresql.md`
  - Deployment, migration, rollback, and Navicat connection notes.

Modify:

- `business/investment/storage.py`
  - Keep storage directory helpers.
  - Replace direct schema creation with migration runner.
  - Keep `get_db_path()` for SQLite compatibility.
- `business/investment/user_service.py`
- `business/investment/daily_content.py`
- `business/investment/records.py`
- `business/investment/config_service.py`
- `business/investment/stock_resolver.py`
- `business/investment/health.py`
- `channel/web/web_channel.py`
- `scripts/refresh_investment_stocks.py`
- `tests/test_investment_business.py`
- `pyproject.toml`

## Data Model

Preserve current logical tables:

- `investment_users`
- `investment_request_records`
- `investment_daily_contents`
- `investment_output_files`
- `investment_configs`
- `investment_stock_symbols`

PostgreSQL type mapping:

- IDs and enum-like fields remain `Text`.
- JSON list fields (`allowed_services`, `source_files`, `output_files`) stay `Text` in phase 1 to minimize behavior changes.
- Timestamp fields stay ISO `Text` in phase 1 to avoid broad date parsing changes.
- Autoincrement `id` maps to SQLAlchemy `Integer primary_key=True autoincrement=True`.

Phase 2 may convert JSON text fields to JSONB and timestamp text fields to timestamptz, but that is intentionally out of scope here.

## Task 1: Add Dependencies and DB URL Resolution

**Subagent assignment:** Dispatch one fresh subagent for this task only. Scope is `pyproject.toml`, `business/investment/db.py`, and database URL tests. Main session must review before Task 2.

**Files:**

- Modify: `pyproject.toml`
- Create: `business/investment/db.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing tests for database URL resolution**

Add tests that verify:

```python
def test_investment_database_url_defaults_to_sqlite(investment_env, monkeypatch):
    from business.investment import db

    monkeypatch.delenv("COWAGENT_INVESTMENT_DATABASE_URL", raising=False)

    url = db.get_database_url()

    assert url.startswith("sqlite:///")
    assert str(investment_env / "investment.db").replace("\\", "/") in url.replace("\\", "/")


def test_investment_database_url_prefers_env(investment_env, monkeypatch):
    from business.investment import db

    monkeypatch.setenv("COWAGENT_INVESTMENT_DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/cowagent")

    assert db.get_database_url() == "postgresql+psycopg://u:p@localhost:5432/cowagent"
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "database_url"
```

Expected: tests fail because `business.investment.db` does not exist.

- [ ] **Step 3: Add dependencies**

Update `pyproject.toml` dependencies:

```toml
dependencies = [
    "click>=8.0",
    "requests>=2.28.2",
    "SQLAlchemy>=2.0",
    "alembic>=1.13",
    "psycopg[binary]>=3.2",
]
```

- [ ] **Step 4: Implement `business/investment/db.py`**

Implement:

```python
# encoding:utf-8
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine

from . import storage

_ENGINE: Engine | None = None
_ENGINE_URL: str | None = None


def _sqlite_url_for_path(path: Path) -> str:
    return "sqlite:///" + path.resolve().as_posix()


def get_database_url() -> str:
    env_url = os.environ.get("COWAGENT_INVESTMENT_DATABASE_URL", "").strip()
    if env_url:
        return env_url
    try:
        from config import conf

        config_url = str(conf().get("investment_database_url", "") or "").strip()
    except Exception:
        config_url = ""
    if config_url:
        return config_url
    return _sqlite_url_for_path(storage.get_db_path())


def is_postgresql_url(url: str | None = None) -> bool:
    value = (url or get_database_url()).lower()
    return value.startswith("postgresql://") or value.startswith("postgresql+")


def get_engine() -> Engine:
    global _ENGINE, _ENGINE_URL
    url = get_database_url()
    if _ENGINE is None or _ENGINE_URL != url:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _ENGINE = create_engine(url, future=True, connect_args=connect_args)
        _ENGINE_URL = url
    return _ENGINE


@contextmanager
def connect() -> Iterator[Connection]:
    engine = get_engine()
    with engine.begin() as conn:
        yield conn


def reset_engine_for_tests() -> None:
    global _ENGINE, _ENGINE_URL
    if _ENGINE is not None:
        _ENGINE.dispose()
    _ENGINE = None
    _ENGINE_URL = None
```

- [ ] **Step 5: Verify tests pass**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "database_url"
```

Expected: pass.

## Task 2: Define Portable SQLAlchemy Schema

**Subagent assignment:** Dispatch one fresh subagent for this task only. Scope is `business/investment/schema.py` and schema declaration tests. Main session must review before Task 3.

**Files:**

- Create: `business/investment/schema.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write schema table tests**

Add a test that imports metadata and verifies all table names exist:

```python
def test_investment_schema_declares_all_tables():
    from business.investment.schema import metadata

    assert {
        "investment_users",
        "investment_request_records",
        "investment_daily_contents",
        "investment_output_files",
        "investment_configs",
        "investment_stock_symbols",
    }.issubset(metadata.tables)
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "schema_declares"
```

Expected: fail because schema module does not exist.

- [ ] **Step 3: Implement `schema.py`**

Define `metadata = MetaData()` and one `Table` per current table. Include equivalent indexes:

```python
# encoding:utf-8
from sqlalchemy import Column, Index, Integer, MetaData, Table, Text

metadata = MetaData()

investment_users = Table(
    "investment_users",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("openid", Text, nullable=False),
    Column("name", Text),
    Column("institution", Text),
    Column("mobile", Text),
    Column("enabled", Integer, nullable=False, default=1),
    Column("allowed_services", Text, nullable=False),
    Column("auth_start_at", Text),
    Column("auth_end_at", Text),
    Column("remark", Text),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Index("idx_investment_users_openid", "openid", unique=True),
)
```

Repeat for all current tables in `business/investment/storage.py`. Preserve index names.

- [ ] **Step 4: Verify schema test passes**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "schema_declares"
```

Expected: pass.

## Task 3: Replace SQLite Schema Initialization With Metadata Creation

**Subagent assignment:** Dispatch one fresh subagent for this task only. Scope is `business/investment/storage.py` and storage initialization tests. Main session must review before Task 4.

**Files:**

- Modify: `business/investment/storage.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write compatibility test**

Keep the existing storage initialization test and add an assertion that `initialize_storage()` still creates all directories and tables using the default SQLite URL.

- [ ] **Step 2: Refactor `initialize_storage()`**

Keep:

- `_storage_root()`
- `get_storage_dirs()`
- `get_db_path()`

Change `initialize_storage()`:

```python
def initialize_storage() -> None:
    dirs = get_storage_dirs()
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    if not os.environ.get("COWAGENT_INVESTMENT_DATABASE_URL", "").strip():
        db_path = get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
    from .db import get_engine
    from .schema import metadata

    metadata.create_all(get_engine())
```

Temporarily keep `get_connection()` as a SQLite compatibility wrapper only if needed by unchanged services. It will be removed or redirected in later tasks.

- [ ] **Step 3: Verify existing storage test passes**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "storage_initializes"
```

Expected: pass.

## Task 4: Add Row Helpers and Port Config Service

**Subagent assignment:** Dispatch one fresh subagent for this task only. Scope is `business/investment/db.py`, `business/investment/config_service.py`, and config tests. Main session must review before Task 5.

**Files:**

- Modify: `business/investment/db.py`
- Modify: `business/investment/config_service.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Add row helper tests through existing config tests**

Run existing config tests first:

```powershell
py -m pytest tests/test_investment_business.py -q -k "config"
```

Expected before implementation may fail once `get_connection()` is removed or adapter changes.

- [ ] **Step 2: Add helper functions**

In `db.py`, add:

```python
from collections.abc import Mapping

def row_to_dict(row) -> dict:
    if row is None:
        return {}
    if isinstance(row, Mapping):
        return dict(row)
    return dict(row._mapping)
```

- [ ] **Step 3: Port `config_service.py` to SQLAlchemy Core**

Replace raw `sqlite3` operations with:

```python
from sqlalchemy import delete, insert, select
from .db import connect, row_to_dict
from .schema import investment_configs
```

Use `select(investment_configs.c.config_value).where(...)`.

For upsert:

- For SQLite use `sqlite_insert` from `sqlalchemy.dialects.sqlite`.
- For PostgreSQL use `postgresql_insert` from `sqlalchemy.dialects.postgresql`.
- Hide this behind a helper in `db.py`:

```python
def upsert_config(conn, key: str, value: str, updated_at: str, updated_by: str) -> None:
    table = investment_configs
    if conn.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    stmt = insert(table).values(
        config_key=key,
        config_value=value,
        updated_at=updated_at,
        updated_by=updated_by,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.config_key],
        set_={
            "config_value": stmt.excluded.config_value,
            "updated_at": stmt.excluded.updated_at,
            "updated_by": stmt.excluded.updated_by,
        },
    )
    conn.execute(stmt)
```

- [ ] **Step 4: Verify config tests pass**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "config"
```

Expected: pass.

## Task 5: Port User Service

**Subagent assignment:** Dispatch one fresh subagent for this task only. Scope is `business/investment/user_service.py`, shared DB helpers only if necessary, and user service tests. Main session must review before Task 6.

**Files:**

- Modify: `business/investment/user_service.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Run existing user service tests**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "user_service"
```

- [ ] **Step 2: Replace SQL with SQLAlchemy**

Use:

```python
from sqlalchemy import select, update
from .db import connect, row_to_dict
from .schema import investment_users
```

Upsert user records with dialect-aware `insert(...).on_conflict_do_update(...)` helper in `db.py`, similar to config.

- [ ] **Step 3: Verify user tests**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "user_service"
```

Expected: pass.

## Task 6: Port Records and Daily Content

**Subagent assignment:** Dispatch one fresh subagent for this task only. Scope is `business/investment/records.py`, `business/investment/daily_content.py`, shared DB helpers only if necessary, and record/content tests. Main session must review before Task 7.

**Files:**

- Modify: `business/investment/records.py`
- Modify: `business/investment/daily_content.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Run current content/record tests**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "records or daily_content"
```

- [ ] **Step 2: Port records queries**

Replace direct SQL calls with SQLAlchemy Core:

- `create_request_record`
- `succeed_request_record`
- `fail_request_record`
- `record_success_request`
- `record_failed_request`
- `set_output_files`
- `get_request_record`
- `list_request_records`
- `record_output_file`
- `list_content_records`
- `get_content_record`

Preserve dataclass return shapes exactly.

- [ ] **Step 3: Port daily content queries**

Replace raw SQL in:

- `save_source_file` remains filesystem only.
- `create_content_draft`
- `update_content_source`
- `_mark_generation_started`
- `update_generation_success`
- `update_generation_failure`
- `set_content_effective`
- `get_latest_effective_content`

Use SQLAlchemy `select`, `insert`, `update`.

- [ ] **Step 4: Verify**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "records or daily_content"
```

Expected: pass.

## Task 7: Port Stock Resolver and Health

**Subagent assignment:** Dispatch one fresh subagent for this task only. Scope is `business/investment/stock_resolver.py`, `business/investment/health.py`, the small investment stock stats helper in `channel/web/web_channel.py`, and resolver/health/API tests. Main session must review before Task 8.

**Files:**

- Modify: `business/investment/stock_resolver.py`
- Modify: `business/investment/health.py`
- Modify: `channel/web/web_channel.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Run resolver and health tests**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "stock_resolver or health or stocks"
```

- [ ] **Step 2: Port stock resolver**

Replace:

- `select code from investment_stock_symbols where name = ?`
- `executemany insert ... on conflict(code)`
- stats queries
- list query

Implement a dialect-aware bulk upsert helper:

```python
def upsert_stock_symbols(conn, rows: list[dict]) -> None:
    table = investment_stock_symbols
    if conn.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    stmt = insert(table).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.code],
        set_={
            "name": stmt.excluded.name,
            "market": stmt.excluded.market,
            "ts_code": stmt.excluded.ts_code,
            "source": stmt.excluded.source,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    conn.execute(stmt)
```

- [ ] **Step 3: Port health checks**

Replace SQLite `sqlite_master` table check with SQLAlchemy inspector:

```python
from sqlalchemy import inspect

def table_exists(table_name: str) -> bool:
    return inspect(get_engine()).has_table(table_name)
```

Also update `_investment_stock_stats()` in `web_channel.py` if it still uses direct `get_connection()`.

- [ ] **Step 4: Verify**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "stock_resolver or health or stocks"
```

Expected: pass.

## Task 8: Add Alembic Migration Files

**Subagent assignment:** Dispatch one fresh subagent for this task only. Scope is `migrations/investment/*`, `business/investment/migrations.py`, storage migration hook only if necessary, and migration smoke tests. Main session must review before Task 9.

**Files:**

- Create: `migrations/investment/alembic.ini`
- Create: `migrations/investment/env.py`
- Create: `migrations/investment/versions/20260525_0001_initial_investment_schema.py`
- Modify: `business/investment/migrations.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write migration smoke test**

Add test:

```python
def test_investment_migration_smoke_creates_schema(investment_env):
    from business.investment import storage
    from business.investment.db import get_engine
    from sqlalchemy import inspect

    storage.initialize_storage()
    inspector = inspect(get_engine())

    assert inspector.has_table("investment_users")
    assert inspector.has_table("investment_stock_symbols")
```

- [ ] **Step 2: Add Alembic files**

`env.py` imports:

```python
from business.investment.db import get_database_url
from business.investment.schema import metadata
```

Initial migration uses `op.create_table` and `op.create_index` matching `schema.py`.

- [ ] **Step 3: Decide migration runner behavior**

For this phase:

- `initialize_storage()` may continue using `metadata.create_all()` for SQLite local convenience.
- Alembic files must exist for production PG deployments.
- Document command:

```powershell
alembic -c migrations/investment/alembic.ini upgrade head
```

- [ ] **Step 4: Verify**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "migration_smoke or storage_initializes"
```

Expected: pass.

## Task 9: Add SQLite to PostgreSQL Migration Script

**Subagent assignment:** Dispatch one fresh subagent for this task only. Scope is `scripts/migrate_investment_sqlite_to_pg.py`, reusable upsert helpers only if necessary, and migration script tests. Main session must review before Task 10.

**Files:**

- Create: `scripts/migrate_investment_sqlite_to_pg.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write script unit tests with temp SQLite and mocked PG engine**

Minimum behavior:

- Fails clearly if source SQLite file does not exist.
- Fails clearly if target URL is not PostgreSQL.
- Reads all six tables from SQLite.
- Uses destination upsert helpers so script is repeatable.

- [ ] **Step 2: Implement script CLI**

CLI:

```powershell
py scripts/migrate_investment_sqlite_to_pg.py --sqlite investment/investment.db --pg postgresql+psycopg://user:pass@host:5432/cowagent
```

Output JSON:

```json
{
  "status": "success",
  "tables": {
    "investment_users": 10,
    "investment_configs": 8,
    "investment_stock_symbols": 5522
  }
}
```

- [ ] **Step 3: Verify script tests**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "sqlite_to_pg_migration"
```

Expected: pass.

## Task 10: Optional PostgreSQL Integration Tests

**Subagent assignment:** Dispatch one fresh subagent for this task only. Scope is PG integration tests and optional test docs. Main session must review before Task 11.

**Files:**

- Modify: `tests/test_investment_business.py`
- Optional create: `tests/integration/test_investment_postgres.py`

- [ ] **Step 1: Add opt-in marker**

Tests should run only when `COWAGENT_TEST_POSTGRES_URL` is set:

```python
pytestmark = pytest.mark.skipif(
    not os.environ.get("COWAGENT_TEST_POSTGRES_URL"),
    reason="COWAGENT_TEST_POSTGRES_URL not configured",
)
```

- [ ] **Step 2: Run same critical flows against PG**

Cover:

- storage init
- config save/get masked
- user create/verify
- rate content create/effective/get
- stock upsert/resolve
- request records

- [ ] **Step 3: Document local Docker command**

Add to docs:

```powershell
docker run --name cowagent-pg -e POSTGRES_PASSWORD=cowagent -e POSTGRES_USER=cowagent -e POSTGRES_DB=cowagent -p 5432:5432 -d postgres:16
$env:COWAGENT_TEST_POSTGRES_URL="postgresql+psycopg://cowagent:cowagent@127.0.0.1:5432/cowagent"
py -m pytest tests/integration/test_investment_postgres.py -q
```

## Task 11: Documentation and Deployment Runbook

**Subagent assignment:** Dispatch one fresh subagent for this task only. Scope is deployment documentation and any plan corrections caused by implementation discoveries. Main session must review before Task 12.

**Files:**

- Create: `docs/deployment/investment-postgresql.md`
- Modify: `docs/superpowers/plans/2026-05-25-investment-postgresql-migration-plan.md` only if implementation discoveries require updating this plan.

- [ ] **Step 1: Write deployment doc**

Include:

- SQLite default deployment.
- PostgreSQL env var.
- Alembic upgrade command.
- SQLite to PG migration command.
- Navicat PG connection example.
- Rollback plan: unset PG URL to return to SQLite.
- Warning: local image paths are not shared storage.

- [ ] **Step 2: Verify docs mention all operational commands**

Search:

```powershell
rg -n "COWAGENT_INVESTMENT_DATABASE_URL|alembic|migrate_investment_sqlite_to_pg|Navicat|rollback" docs/deployment/investment-postgresql.md
```

Expected: all terms found.

## Task 12: Final Quality Gates

**Subagent assignment:** Dispatch one fresh subagent for independent final verification only. The subagent should avoid broad code edits; any found issue must be reported or fixed narrowly, then main session reruns the full gates.

**Files:** All modified files.

- [ ] **Step 1: Run SQLite full test suite**

```powershell
py -m pytest
```

Expected: all tests pass.

- [ ] **Step 2: Run type check**

```powershell
py -m mypy business tests
```

Expected: success.

- [ ] **Step 3: Run lint**

```powershell
py -m ruff check .
```

Expected: all checks pass. If `pyproject.toml` ruff include still scopes to `business/**/*.py` and investment tests, update it only if new scripts need lint coverage.

- [ ] **Step 4: Run frontend syntax check**

```powershell
node --check channel/web/static/js/console.js
```

Expected: no output and exit code 0.

- [ ] **Step 5: Run investment script smoke test**

```powershell
py scripts/refresh_investment_stocks.py --source akshare --json
```

Expected: success or a clear external provider error. Database code must not fail due to SQLAlchemy migration.

## Acceptance Criteria

- Without PostgreSQL config, app uses the existing SQLite database path and current behavior remains unchanged.
- With `COWAGENT_INVESTMENT_DATABASE_URL=postgresql+psycopg://...`, investment storage initializes and all investment business flows use PG.
- All investment tables have equivalent schema and indexes in PG.
- SQLite to PG migration script copies existing business data and can be rerun.
- Web后台 `/api/investment/*` APIs work on both backends.
- `利率` and `转债` still read latest `effective` records.
- `新易盛 技术分析` still resolves through stock dictionary.
- Health check reports database backend and table readiness.
- No token/API key is leaked in logs, API responses, or migration output.

## Known Risks

- SQLite and PostgreSQL concurrency semantics differ. Do not assume SQLite locking behavior in PG tests.
- PostgreSQL reserved words and text comparison collation may differ from SQLite.
- Existing timestamp strings are not normalized. Keep them as text in phase 1.
- File paths in `investment_output_files` remain local paths. PG does not make generated images available across machines.
- Alembic migrations need careful review because current schema was previously created imperatively.

## Suggested New-Conversation Agent Prompt

Paste this into the new conversation:

```text
请读取并严格执行：
docs/superpowers/plans/2026-05-25-investment-postgresql-migration-plan.md

目标是让 business/investment 投资业务模块支持 PostgreSQL，同时保持 SQLite 默认兼容。请按计划使用 TDD 分任务执行，不要改 agent/memory 等非投资业务 SQLite 存储。每个任务完成后运行对应测试和质量门禁，发现问题先定位根因再修复。
```

