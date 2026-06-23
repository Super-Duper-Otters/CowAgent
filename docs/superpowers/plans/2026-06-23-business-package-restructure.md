# Business Package Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize `business/` into focused subpackages, keep compatibility wrappers during migration, then remove wrappers after all imports and tests pass.

**Architecture:** The first commit moves implementation files into `business/*/` subpackages and leaves old top-level modules as re-export compatibility wrappers. The second commit updates all project imports to the new package paths. The final commit deletes compatibility wrappers after the full test suite passes, leaving a clean package structure.

**Tech Stack:** Python 3, SQLAlchemy, web.py, pytest, PowerShell, git.

---

## Target Structure

```text
business/
  schema/
    __init__.py
    tables.py
    db.py
    storage.py
    migrations.py
    file_migration.py
  routing/
    __init__.py
    router.py
    business_router.py
    module_dispatcher.py
  components/
    __init__.py
    registry.py
    service.py
    import_service.py
    paths.py
    skill_versions.py
    skill_registry.py
    skill_runner.py
  execution/
    __init__.py
    command_script_executor.py
    prompt_component_executor.py
    daily_content_executor.py
    technical_analysis_executor.py
  records/
    __init__.py
    records.py
    business_records.py
    cleanup.py
    export_service.py
  artifacts/
    __init__.py
    artifact_service.py
    artifacts.py
  content/
    __init__.py
    daily_content.py
    daily_content_handler.py
    render_service.py
    prompt_to_image_handler.py
    technical_analysis.py
    technical_analysis_handler.py
    stock_resolver.py
    market_date_resolver.py
  accounts/
    __init__.py
    auth_service.py
    user_service.py
    permission_service.py
  audit/
    __init__.py
    audit_service.py
    event_service.py
    ai_generation.py
    ai_generation_audit.py
  config/
    __init__.py
    config_service.py
    reply_config.py
    constants.py
  cache/
    __init__.py
    cache_service.py
    business_cache.py
    cache_policy.py
  health/
    __init__.py
    health.py
    job_service.py

  # temporary compatibility wrappers, deleted in final phase
  router.py
  schema.py
  db.py
  storage.py
  ...
```

## Move Map

```text
business/schema.py -> business/schema/tables.py
business/db.py -> business/schema/db.py
business/storage.py -> business/schema/storage.py
business/migrations.py -> business/schema/migrations.py
business/file_migration.py -> business/schema/file_migration.py

business/router.py -> business/routing/router.py
business/business_router.py -> business/routing/business_router.py
business/module_dispatcher.py -> business/routing/module_dispatcher.py

business/business_registry.py -> business/components/registry.py
business/component_service.py -> business/components/service.py
business/component_import_service.py -> business/components/import_service.py
business/component_paths.py -> business/components/paths.py
business/skill_versions.py -> business/components/skill_versions.py
business/skill_registry.py -> business/components/skill_registry.py
business/skill_runner.py -> business/components/skill_runner.py

business/executors/command_script_executor.py -> business/execution/command_script_executor.py
business/executors/prompt_component_executor.py -> business/execution/prompt_component_executor.py
business/executors/daily_content_executor.py -> business/execution/daily_content_executor.py
business/executors/technical_analysis_executor.py -> business/execution/technical_analysis_executor.py

business/records.py -> business/records/records.py
business/business_records.py -> business/records/business_records.py
business/record_cleanup.py -> business/records/cleanup.py
business/export_service.py -> business/records/export_service.py

business/artifact_service.py -> business/artifacts/artifact_service.py
business/artifacts.py -> business/artifacts/artifacts.py

business/daily_content.py -> business/content/daily_content.py
business/daily_content_handler.py -> business/content/daily_content_handler.py
business/render_service.py -> business/content/render_service.py
business/prompt_to_image_handler.py -> business/content/prompt_to_image_handler.py
business/technical_analysis.py -> business/content/technical_analysis.py
business/technical_analysis_handler.py -> business/content/technical_analysis_handler.py
business/stock_resolver.py -> business/content/stock_resolver.py
business/market_date_resolver.py -> business/content/market_date_resolver.py

business/auth_service.py -> business/accounts/auth_service.py
business/user_service.py -> business/accounts/user_service.py
business/permission_service.py -> business/accounts/permission_service.py

business/audit_service.py -> business/audit/audit_service.py
business/event_service.py -> business/audit/event_service.py
business/ai_generation.py -> business/audit/ai_generation.py
business/ai_generation_audit.py -> business/audit/ai_generation_audit.py

business/config_service.py -> business/config/config_service.py
business/reply_config.py -> business/config/reply_config.py
business/constants.py -> business/config/constants.py

business/cache_service.py -> business/cache/cache_service.py
business/business_cache.py -> business/cache/business_cache.py
business/cache_policy.py -> business/cache/cache_policy.py

business/health.py -> business/health/health.py
business/job_service.py -> business/health/job_service.py
```

## Compatibility Wrapper Pattern

Each old module path must temporarily re-export the moved module.

Example for `business/router.py`:

```python
# encoding:utf-8
from business.routing.router import *  # noqa: F401,F403
```

Example for `business/schema.py`:

```python
# encoding:utf-8
from business.schema.tables import *  # noqa: F401,F403
```

Example for executor compatibility:

```python
# encoding:utf-8
from business.execution.command_script_executor import *  # noqa: F401,F403
```

## Task 1: Create Subpackages and Move Files with Compatibility Wrappers

**Files:**
- Create: `business/schema/__init__.py`
- Create: `business/routing/__init__.py`
- Create: `business/components/__init__.py`
- Create: `business/execution/__init__.py`
- Create: `business/records/__init__.py`
- Create: `business/artifacts/__init__.py`
- Create: `business/content/__init__.py`
- Create: `business/accounts/__init__.py`
- Create: `business/audit/__init__.py`
- Create: `business/config/__init__.py`
- Create: `business/cache/__init__.py`
- Create: `business/health/__init__.py`
- Move: files listed in Move Map
- Modify: old moved file paths into compatibility wrappers

- [ ] **Step 1: Create package directories**

Run:

```powershell
New-Item -ItemType Directory -Force `
  business\schema,business\routing,business\components,business\execution,business\records,business\artifacts,`
  business\content,business\accounts,business\audit,business\config,business\cache,business\health
```

Expected: directories exist.

- [ ] **Step 2: Add `__init__.py` files**

Create each `__init__.py` with exactly:

```python
# encoding:utf-8
```

- [ ] **Step 3: Move files using `git mv`**

Run the move map as `git mv` commands, for example:

```powershell
git mv business\router.py business\routing\router.py
git mv business\business_router.py business\routing\business_router.py
git mv business\module_dispatcher.py business\routing\module_dispatcher.py
git mv business\business_registry.py business\components\registry.py
git mv business\component_service.py business\components\service.py
git mv business\component_import_service.py business\components\import_service.py
git mv business\component_paths.py business\components\paths.py
git mv business\schema.py business\schema\tables.py
git mv business\db.py business\schema\db.py
git mv business\storage.py business\schema\storage.py
```

Continue until every item in the Move Map is moved. If a file is missing, record it in the commit message and do not create a fake replacement.

- [ ] **Step 4: Restore compatibility wrappers at old paths**

Create wrappers for every moved top-level file. Examples:

```python
# business/router.py
# encoding:utf-8
from business.routing.router import *  # noqa: F401,F403
```

```python
# business/business_registry.py
# encoding:utf-8
from business.components.registry import *  # noqa: F401,F403
```

```python
# business/config_service.py
# encoding:utf-8
from business.config.config_service import *  # noqa: F401,F403
```

For old executor paths:

```python
# business/executors/command_script_executor.py
# encoding:utf-8
from business.execution.command_script_executor import *  # noqa: F401,F403
```

- [ ] **Step 5: Run syntax check**

Run:

```powershell
python -m compileall business
```

Expected: command exits 0.

- [ ] **Step 6: Run focused routing/component tests**

Run:

```powershell
pytest tests\test_business.py tests\test_business_web_ui.py tests\test_technical_analysis_skill_v02.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit compatibility move**

Run:

```powershell
git status --short
git add business
git commit -m "refactor: group business modules by responsibility"
```

Expected: commit succeeds. This commit still contains compatibility wrappers.

## Task 2: Update Project Imports to New Package Paths

**Files:**
- Modify: all project files containing `from business.` or `import business.`
- Test: `tests/`

- [ ] **Step 1: Find all old imports**

Run:

```powershell
rg -n "from business\.|import business\." .
```

Expected: old import paths are listed.

- [ ] **Step 2: Replace import paths according to the import map**

Use these replacements:

```text
business.schema -> business.schema.tables
business.db -> business.schema.db
business.storage -> business.schema.storage
business.migrations -> business.schema.migrations
business.file_migration -> business.schema.file_migration

business.router -> business.routing.router
business.business_router -> business.routing.business_router
business.module_dispatcher -> business.routing.module_dispatcher

business.business_registry -> business.components.registry
business.component_service -> business.components.service
business.component_import_service -> business.components.import_service
business.component_paths -> business.components.paths
business.skill_versions -> business.components.skill_versions
business.skill_registry -> business.components.skill_registry
business.skill_runner -> business.components.skill_runner

business.executors.command_script_executor -> business.execution.command_script_executor
business.executors.prompt_component_executor -> business.execution.prompt_component_executor
business.executors.daily_content_executor -> business.execution.daily_content_executor
business.executors.technical_analysis_executor -> business.execution.technical_analysis_executor

business.records -> business.records.records
business.business_records -> business.records.business_records
business.record_cleanup -> business.records.cleanup
business.export_service -> business.records.export_service

business.artifact_service -> business.artifacts.artifact_service
business.artifacts -> business.artifacts.artifacts

business.daily_content -> business.content.daily_content
business.daily_content_handler -> business.content.daily_content_handler
business.render_service -> business.content.render_service
business.prompt_to_image_handler -> business.content.prompt_to_image_handler
business.technical_analysis -> business.content.technical_analysis
business.technical_analysis_handler -> business.content.technical_analysis_handler
business.stock_resolver -> business.content.stock_resolver
business.market_date_resolver -> business.content.market_date_resolver

business.auth_service -> business.accounts.auth_service
business.user_service -> business.accounts.user_service
business.permission_service -> business.accounts.permission_service

business.audit_service -> business.audit.audit_service
business.event_service -> business.audit.event_service
business.ai_generation -> business.audit.ai_generation
business.ai_generation_audit -> business.audit.ai_generation_audit

business.config_service -> business.config.config_service
business.reply_config -> business.config.reply_config
business.constants -> business.config.constants

business.cache_service -> business.cache.cache_service
business.business_cache -> business.cache.business_cache
business.cache_policy -> business.cache.cache_policy

business.health -> business.health.health
business.job_service -> business.health.job_service
```

- [ ] **Step 3: Find dynamic references**

Run:

```powershell
rg -n '"business\.|''business\.|business\\' .
```

Expected: any string-based references are reviewed and updated only when they reference Python module paths. File paths, comments, docs, and migration history can remain unchanged unless they break tests.

- [ ] **Step 4: Run syntax check**

Run:

```powershell
python -m compileall business channel tests
```

Expected: command exits 0.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
pytest tests\test_business.py tests\test_business_web_ui.py tests\test_wechatmp_business_reply.py tests\test_technical_analysis_skill_v02.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit import migration**

Run:

```powershell
git status --short
git add .
git commit -m "refactor: update business imports to subpackages"
```

Expected: commit succeeds. Compatibility wrappers still exist but should no longer be needed by project imports.

## Task 3: Delete Compatibility Wrappers After Passing Tests

**Files:**
- Delete: old top-level wrapper files in `business/`
- Delete or keep: `business/executors/` only if no imports remain
- Test: full test suite

- [ ] **Step 1: Confirm no production or test import uses wrappers**

Run:

```powershell
rg -n "from business\.(router|business_router|module_dispatcher|business_registry|component_service|component_import_service|component_paths|schema|db|storage|records|business_records|artifact_service|daily_content|auth_service|user_service|permission_service|audit_service|config_service|reply_config|cache_service)|import business\.(router|business_router|module_dispatcher|business_registry|component_service|component_import_service|component_paths|schema|db|storage|records|business_records|artifact_service|daily_content|auth_service|user_service|permission_service|audit_service|config_service|reply_config|cache_service)" .
```

Expected: no results from source files. If results remain, update those imports before deletion.

- [ ] **Step 2: Delete wrapper files**

Delete wrappers that were created in Task 1. Use `git rm`:

```powershell
git rm business\router.py
git rm business\business_router.py
git rm business\module_dispatcher.py
git rm business\business_registry.py
git rm business\component_service.py
git rm business\component_import_service.py
git rm business\component_paths.py
git rm business\schema.py
git rm business\db.py
git rm business\storage.py
git rm business\records.py
git rm business\business_records.py
git rm business\artifact_service.py
git rm business\daily_content.py
git rm business\auth_service.py
git rm business\user_service.py
git rm business\permission_service.py
git rm business\audit_service.py
git rm business\config_service.py
git rm business\reply_config.py
git rm business\cache_service.py
```

Also delete executor wrappers if no imports remain:

```powershell
git rm business\executors\command_script_executor.py
git rm business\executors\prompt_component_executor.py
git rm business\executors\daily_content_executor.py
git rm business\executors\technical_analysis_executor.py
```

- [ ] **Step 3: Remove empty old executor package if unused**

Run:

```powershell
Get-ChildItem business\executors -Force
```

If only `__init__.py` remains and no imports reference `business.executors`, delete it:

```powershell
git rm business\executors\__init__.py
Remove-Item business\executors -Force
```

- [ ] **Step 4: Run syntax check**

Run:

```powershell
python -m compileall business channel tests
```

Expected: command exits 0.

- [ ] **Step 5: Run full test suite**

Run:

```powershell
pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit compatibility removal**

Run:

```powershell
git status --short
git add .
git commit -m "refactor: remove business compatibility wrappers"
```

Expected: commit succeeds. Final tree has no old compatibility wrappers.

## Task 4: Validate Runtime Entry Points

**Files:**
- Validate: `app.py`
- Validate: `channel/web/web_channel.py`
- Validate: `channel/wechatmp/*`
- Validate: `business_storage/` remains untouched

- [ ] **Step 1: Confirm runtime data was not moved**

Run:

```powershell
git status --short business_storage config.json
```

Expected: no staged or unstaged changes caused by restructuring.

- [ ] **Step 2: Confirm key API modules import**

Run:

```powershell
python - <<'PY'
import app
import channel.web.web_channel
import channel.wechatmp.wechatmp_channel
import business.routing.router
import business.components.registry
import business.records.records
import business.artifacts.artifact_service
print("imports ok")
PY
```

Expected: prints `imports ok`.

- [ ] **Step 3: Run Web UI test**

Run:

```powershell
pytest tests\test_business_web_ui.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit runtime validation fixes if needed**

Only if Step 2 or Step 3 required import fixes:

```powershell
git status --short
git add .
git commit -m "fix: update runtime imports after business restructure"
```

Expected: commit succeeds only when there are actual fixes.

## Do Not Move in This Plan

These are runtime, deployment, test, or local artifacts. They must not be moved during this package restructure:

```text
business_storage/
config.json
docker/
scripts/
migrations/
tests/
test_artifacts/
tmp/
nohup.out
nohup.err
.cow.pid
cowagent-local.tar
```

## Acceptance Criteria

- `business/` contains focused subpackages for routing, components, execution, records, artifacts, content, accounts, audit, config, cache, schema, and health.
- Compatibility wrappers are created only temporarily.
- All project imports use the new subpackage paths before wrappers are deleted.
- `python -m compileall business channel tests` passes.
- `pytest -q` passes.
- `business_storage/` and `config.json` are not moved or rewritten by this restructure.
- Final commit removes compatibility wrappers so the tree is clean.

