# Investment Components Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize investment skill/config management into a clear component model where active components own triggers and prompts, passive components own support scripts/templates, and system config only contains platform-level settings.

**Architecture:** Keep the existing runtime flows stable in the first phase. Add a component abstraction over the current registry/config/version services, then move UI editing from "System Config" into "Investment Components" without changing how messages are routed or how content is generated. Existing config keys remain the storage contract for compatibility.

**Tech Stack:** Python, web.py handlers, SQLAlchemy-backed config storage, vanilla JS/Tailwind console UI, pytest.

**Execution Status (2026-06-12):**

- Tasks 1-6 implemented: component metadata, component service, component settings API, prompt ownership migration, wide component page, and script version compatibility.
- Task 7 partially verified with lightweight route/config smoke checks; full backend pytest is blocked in this local environment by the investment database fixture timing out before assertions run.
- Task 8 partially verified: frontend investment UI tests, JS syntax check, Python compile check, diff whitespace check, component list smoke, and component settings save smoke passed.

---

## Current State

The current system exposes four investment entries as "skills", but they are not the same kind of capability:

- `technical-analysis`: active, script-backed, user-triggered by suffix matching such as `300502.SZ 技术分析`.
- `rate`: active, prompt-backed daily content entry, user-triggered by exact matching such as `利率`.
- `convertible-bond`: active, prompt-backed daily content entry, user-triggered by exact matching such as `转债`.
- `signal-card-renderer`: passive, script-backed rendering component used by other components, not user-triggered.

The existing backend already stores:

- triggers in `skill.<component>.triggers`
- enabled status in `skill.<component>.enabled`
- prompts in `prompt.technical_analysis`, `prompt.rate`, `prompt.convertible_bond`
- script active paths in `technical_analysis.skill_path` and `render.renderer_path`

The problem is presentation and ownership: prompts live under system config, script versions and prompt-only entries are displayed in one version table, and passive rendering looks like an active skill.

## Target Component Model

Use `component_type` as the canonical classification:

- `active_script`: user-triggered component with script versions and prompt configuration.
  - Built-in example: `technical-analysis`
- `active_prompt`: user-triggered component with prompt configuration but no script version.
  - Built-in examples: `rate`, `convertible-bond`
- `passive_script`: non-user-triggered support component with script/template versions.
  - Built-in example: `signal-card-renderer`

Rules:

- Active components must have editable triggers.
- Passive components must not expose triggers.
- Active prompt components must expose prompt editing.
- Active script components may expose prompt editing and script version management.
- Passive script components expose script/template version management and dependency information.
- System config must retain platform-level settings only.

## Files

- Modify: `business/business_registry.py`
  - Add component type metadata and helpers for prompt/render associations.
- Modify: `business/investment/skill_registry.py`
  - Keep compatibility wrapper aligned with the canonical business registry.
- Create: `business/investment/component_service.py`
  - Build component view models and save component settings.
- Modify: `business/investment/skill_versions.py`
  - Continue handling versioned script components; expose version data through component service.
- Modify: `channel/web/web_channel.py`
  - Add component endpoints and keep old skill endpoints as compatibility shims.
- Modify: `channel/web/investment_handlers.py`
  - Register new component routes.
- Modify: `channel/web/static/js/console.js`
  - Replace investment skill table with component cards/editors.
  - Move component prompts/triggers out of system config UI.
- Modify: `channel/web/chat.html`
  - Widen investment components view container.
- Modify: `channel/web/static/css/console.css`
  - Add component page styles and remove reliance on narrow table layout.
- Modify: `tests/test_investment_business.py`
  - Add backend component model and settings tests.
- Modify: `tests/test_investment_web_ui.py`
  - Add UI structure tests for component types and config ownership.

---

## Task 1: Add Component Type Metadata

**Files:**
- Modify: `business/business_registry.py`
- Modify: `business/investment/skill_registry.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing registry tests**

Add tests that assert the built-in components expose stable component types:

```python
def test_investment_builtin_components_have_explicit_types(investment_env):
    from business.business_registry import get_business_definition

    assert get_business_definition("technical-analysis").component_type == "active_script"
    assert get_business_definition("rate").component_type == "active_prompt"
    assert get_business_definition("convertible-bond").component_type == "active_prompt"
    assert get_business_definition("signal-card-renderer").component_type == "passive_script"
```

Add a second test for trigger ownership:

```python
def test_investment_component_trigger_ownership(investment_env):
    from business.business_registry import get_business_definition

    assert get_business_definition("technical-analysis").uses_triggers is True
    assert get_business_definition("rate").uses_triggers is True
    assert get_business_definition("convertible-bond").uses_triggers is True
    assert get_business_definition("signal-card-renderer").uses_triggers is False
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
py -m pytest tests/test_investment_business.py -k "component_type or trigger_ownership" -q
```

Expected: tests fail because `component_type` and `uses_triggers` do not exist.

- [ ] **Step 3: Add fields to `BusinessDefinition`**

Add fields:

```python
component_type: str = ""
prompt_key: str = ""
renderer_component_key: str = ""
template_key: str = ""
```

Add properties:

```python
@property
def uses_triggers(self) -> bool:
    return self.component_type in {"active_script", "active_prompt"}

@property
def versioned(self) -> bool:
    return bool(self.script_name and self.config_key)
```

Include these fields in `as_dict()`.

- [ ] **Step 4: Populate built-in component metadata**

Set:

```python
technical-analysis:
  component_type="active_script"
  prompt_key="prompt.technical_analysis"
  renderer_component_key="signal-card-renderer"
  template_key="technical_analysis"

rate:
  component_type="active_prompt"
  prompt_key="prompt.rate"
  renderer_component_key="signal-card-renderer"
  template_key="rate"

convertible-bond:
  component_type="active_prompt"
  prompt_key="prompt.convertible_bond"
  renderer_component_key="signal-card-renderer"
  template_key="convertible_bond"

signal-card-renderer:
  component_type="passive_script"
```

- [ ] **Step 5: Keep uploaded component compatibility**

In `read_uploaded_business_definition()`, read optional `investment.component_type`; default legacy `handler_type=script` uploads to `active_script` when `routable=True`, otherwise `passive_script`.

- [ ] **Step 6: Run registry tests**

Run:

```powershell
py -m pytest tests/test_investment_business.py -k "component_type or trigger_ownership" -q
```

Expected: PASS.

---

## Task 2: Create Component Service

**Files:**
- Create: `business/investment/component_service.py`
- Modify: `business/investment/skill_versions.py` only if needed for reusable helpers
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing service tests**

Add tests:

```python
def test_component_service_lists_components_by_type(investment_env):
    from business.investment.component_service import list_components

    items = {item["component_key"]: item for item in list_components()}

    assert items["technical-analysis"]["component_type"] == "active_script"
    assert items["technical-analysis"]["uses_triggers"] is True
    assert items["technical-analysis"]["versioned"] is True
    assert items["rate"]["component_type"] == "active_prompt"
    assert items["rate"]["versioned"] is False
    assert items["signal-card-renderer"]["component_type"] == "passive_script"
    assert items["signal-card-renderer"]["uses_triggers"] is False
```

```python
def test_component_service_includes_prompt_and_version_data(investment_env):
    from business.investment.component_service import list_components
    from business.investment.config_service import save_config

    save_config("prompt.rate", "rate prompt v1", operator_role="admin")
    items = {item["component_key"]: item for item in list_components()}

    assert items["rate"]["settings"]["prompt"] == "rate prompt v1"
    assert "versions" not in items["rate"] or items["rate"]["versions"] == []
    assert items["technical-analysis"]["versions"]
    assert items["signal-card-renderer"]["versions"]
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
py -m pytest tests/test_investment_business.py -k "component_service" -q
```

Expected: import failure for `component_service`.

- [ ] **Step 3: Implement `list_components()`**

Create `business/investment/component_service.py` with:

```python
from business.business_registry import list_business_definitions, resolve_triggers, is_business_enabled
from .config_service import get_config
from .skill_versions import list_versions


def _component_settings(definition) -> dict:
    settings = {"enabled": is_business_enabled(definition)}
    if definition.uses_triggers:
        settings["triggers"] = list(resolve_triggers(definition))
    if definition.prompt_key:
        settings["prompt_key"] = definition.prompt_key
        settings["prompt"] = get_config(definition.prompt_key, "")
    return settings


def _component_versions(definition) -> list[dict]:
    if not definition.versioned:
        return []
    return list_versions(definition.business_key)


def list_components() -> list[dict]:
    items = []
    for definition in list_business_definitions():
        item = definition.as_dict()
        item["component_key"] = definition.business_key
        item["uses_triggers"] = definition.uses_triggers
        item["versioned"] = definition.versioned
        item["settings"] = _component_settings(definition)
        item["versions"] = _component_versions(definition)
        items.append(item)
    return items
```

- [ ] **Step 4: Run component service tests**

Run:

```powershell
py -m pytest tests/test_investment_business.py -k "component_service" -q
```

Expected: PASS.

---

## Task 3: Add Component Settings Save API

**Files:**
- Modify: `business/investment/component_service.py`
- Modify: `channel/web/web_channel.py`
- Modify: `channel/web/investment_handlers.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing backend API tests**

Add tests that call the web handlers directly:

```python
def test_component_settings_save_updates_active_prompt_component(investment_env, monkeypatch):
    import json
    import channel.web.web_channel as web_channel
    from business.investment.config_service import get_config
    from business.business_registry import resolve_triggers, get_business_definition

    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps({
            "enabled": False,
            "triggers": ["今日利率", "利率观察"],
            "prompt": "updated rate prompt",
        }, ensure_ascii=False).encode("utf-8"),
    )
    handler = web_channel.InvestmentComponentSettingsHandler()
    response = json.loads(handler.POST("rate"))

    assert response["status"] == "success"
    assert get_config("skill.rate.enabled") is False
    assert resolve_triggers(get_business_definition("rate")) == ("今日利率", "利率观察")
    assert get_config("prompt.rate") == "updated rate prompt"
```

```python
def test_component_settings_rejects_triggers_for_passive_component(investment_env, monkeypatch):
    import json
    import channel.web.web_channel as web_channel

    monkeypatch.setattr(
        web_channel.web,
        "data",
        lambda: json.dumps({"triggers": ["渲染"]}, ensure_ascii=False).encode("utf-8"),
    )
    response = json.loads(web_channel.InvestmentComponentSettingsHandler().POST("signal-card-renderer"))

    assert response["status"] == "error"
    assert "triggers" in response["message"]
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
py -m pytest tests/test_investment_business.py -k "component_settings" -q
```

Expected: handler does not exist.

- [ ] **Step 3: Implement `save_component_settings()`**

In `component_service.py`, add:

```python
from business.business_registry import get_business_definition
from .config_service import save_config


def save_component_settings(component_key: str, values: dict, *, operator_role: str, operator: str, actor=None) -> dict:
    definition = get_business_definition(component_key)
    if "triggers" in values:
        if not definition.uses_triggers:
            raise ValueError("passive components do not accept triggers")
        triggers = values.get("triggers") or []
        if isinstance(triggers, str):
            triggers = [item.strip() for item in triggers.replace("，", ",").split(",")]
        triggers = [str(item).strip() for item in triggers if str(item).strip()]
        if not triggers:
            raise ValueError("active component triggers cannot be empty")
        save_config(definition.triggers_config_key, triggers, operator_role=operator_role, operator=operator, actor=actor)
    if "enabled" in values:
        save_config(definition.enabled_config_key, bool(values.get("enabled")), operator_role=operator_role, operator=operator, actor=actor)
    if "prompt" in values:
        if not definition.prompt_key:
            raise ValueError("component does not accept prompt")
        save_config(definition.prompt_key, str(values.get("prompt") or ""), operator_role=operator_role, operator=operator, actor=actor)
    return next(item for item in list_components() if item["component_key"] == component_key)
```

- [ ] **Step 4: Add web handlers and routes**

Add routes:

```python
'/api/investment/components', 'InvestmentComponentsHandler',
'/api/investment/components/(.*)/settings', 'InvestmentComponentSettingsHandler',
```

Add handlers that require `skills.read` for GET and `skills.write` for POST.

- [ ] **Step 5: Run backend API tests**

Run:

```powershell
py -m pytest tests/test_investment_business.py -k "component_settings or component_service" -q
```

Expected: PASS.

---

## Task 4: Move Component Prompts Out of System Config UI

**Files:**
- Modify: `channel/web/static/js/console.js`
- Test: `tests/test_investment_web_ui.py`

- [ ] **Step 1: Write failing UI ownership test**

Add:

```python
def test_component_prompts_are_not_in_system_config_page():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    config_groups = js[js.index("const INVEST_CONFIG_GROUPS"):js.index("const INVEST_ADMIN_ONLY_CONFIG_KEYS")]

    assert "prompt.technical_analysis" not in config_groups
    assert "prompt.rate" not in config_groups
    assert "prompt.convertible_bond" not in config_groups
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
py -m pytest tests/test_investment_web_ui.py -k "component_prompts_are_not" -q
```

Expected: FAIL because prompts are still in `INVEST_CONFIG_GROUPS`.

- [ ] **Step 3: Remove component prompts from `INVEST_CONFIG_GROUPS`**

Remove the `存储与提示词` group from `INVEST_CONFIG_GROUPS`. Keep `后台Web对话`, `股票字典`, and `目录配置`.

- [ ] **Step 4: Run UI ownership test**

Run:

```powershell
py -m pytest tests/test_investment_web_ui.py -k "component_prompts_are_not" -q
```

Expected: PASS.

---

## Task 5: Rebuild Investment Components Page

**Files:**
- Modify: `channel/web/static/js/console.js`
- Modify: `channel/web/chat.html`
- Modify: `channel/web/static/css/console.css`
- Test: `tests/test_investment_web_ui.py`

- [ ] **Step 1: Write failing page structure tests**

Add tests:

```python
def test_investment_components_page_uses_wide_container():
    html = CHAT_HTML.read_text(encoding="utf-8")
    start = html.index('id="view-invest-skills"')
    end = html.index('id="view-invest-health"')
    body = html[start:end]

    assert "w-full max-w-[1600px] mx-auto" in body
    assert "max-w-6xl mx-auto" not in body
```

```python
def test_investment_components_page_groups_component_types():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "/api/investment/components" in js
    assert "active_script" in js
    assert "active_prompt" in js
    assert "passive_script" in js
    assert "renderInvestmentComponentCard" in js
    assert "renderInvestmentSkillConfigTable" not in js
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
py -m pytest tests/test_investment_web_ui.py -k "components_page" -q
```

Expected: FAIL because current page uses skill table and narrow container.

- [ ] **Step 3: Widen `view-invest-skills` container**

Change the inner wrapper from:

```html
<div class="max-w-6xl mx-auto">
```

to:

```html
<div class="w-full max-w-[1600px] mx-auto">
```

- [ ] **Step 4: Replace skill table loader with component loader**

Rename or replace:

- `loadInvestmentSkillVersions()` -> `loadInvestmentComponents()`
- `/api/investment/skills/versions` -> `/api/investment/components`
- `renderInvestmentSkillConfigTable()` -> component section/card renderers

Render sections:

```javascript
const groups = [
  ['active_script', '脚本型主动组件'],
  ['active_prompt', '提示词型主动组件'],
  ['passive_script', '脚本型被动组件'],
];
```

- [ ] **Step 5: Render settings based on component type**

For `active_script` cards show:

- enabled switch
- triggers editor
- prompt textarea if present
- active version and upload/edit version action

For `active_prompt` cards show:

- enabled switch
- triggers editor
- prompt textarea
- latest effective content status placeholder

For `passive_script` cards show:

- no triggers editor
- active version and upload/edit version action
- called-by text: `技术分析 / 利率 / 转债`

- [ ] **Step 6: Add component styles**

Add CSS classes for:

- `.investment-component-page`
- `.investment-component-section`
- `.investment-component-grid`
- `.investment-component-card`
- `.investment-component-meta`
- `.investment-component-editor`

Use full-width sections and compact cards. Do not place cards inside cards.

- [ ] **Step 7: Run page structure tests**

Run:

```powershell
py -m pytest tests/test_investment_web_ui.py -k "components_page or component_prompts_are_not" -q
```

Expected: PASS.

---

## Task 6: Preserve Script Version Upload Behavior

**Files:**
- Modify: `channel/web/static/js/console.js`
- Modify: `channel/web/web_channel.py` only if route compatibility requires it
- Test: `tests/test_investment_web_ui.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write UI tests for script-only version controls**

Add:

```python
def test_only_versioned_components_show_upload_controls():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    card_body = _js_function_body(js, "renderInvestmentComponentCard")

    assert "component.versioned" in card_body
    assert "uploadInvestmentSkill" in card_body
    assert "component.uses_triggers" in card_body
```

- [ ] **Step 2: Write backend compatibility test**

Keep existing tests that assert:

```python
assert get_config("technical_analysis.skill_path") == uploaded["script_path"]
assert get_config("render.renderer_path") == uploaded["script_path"]
```

Do not change these storage keys in this refactor.

- [ ] **Step 3: Run targeted tests**

Run:

```powershell
py -m pytest tests/test_investment_web_ui.py -k "versioned_components" -q
py -m pytest tests/test_investment_business.py -k "skill_path or renderer_path or package_upload" -q
```

Expected: PASS.

---

## Task 7: Verify Runtime Behavior Is Unchanged

**Files:**
- Test only unless failures reveal integration gaps
- Test: `tests/test_investment_business.py`
- Test: `tests/test_wechatmp_investment_reply.py`

- [ ] **Step 1: Run route trigger tests**

Run:

```powershell
py -m pytest tests/test_investment_business.py -k "triggers or parse_route or handle_text_message" -q
```

Expected: PASS. Custom triggers still affect routing.

- [ ] **Step 2: Run daily content delivery tests**

Run:

```powershell
py -m pytest tests/test_investment_business.py -k "daily_content or latest_effective or no_content" -q
```

Expected: PASS. `利率` and `转债` still return current effective images.

- [ ] **Step 3: Run technical analysis and renderer tests**

Run:

```powershell
py -m pytest tests/test_investment_business.py -k "technical_analysis or render_card or renderer" -q
```

Expected: PASS. Technical analysis and card rendering still use the active script paths.

- [ ] **Step 4: Run WeChat investment reply tests**

Run:

```powershell
py -m pytest tests/test_wechatmp_investment_reply.py -q
```

Expected: PASS.

---

## Task 8: Final Verification

**Files:**
- No source changes unless verification catches issues

- [ ] **Step 1: Run focused frontend/backend tests**

Run:

```powershell
py -m pytest tests/test_investment_web_ui.py tests/test_investment_business.py -q
```

Expected: PASS.

- [ ] **Step 2: Run relevant integration tests if local services are configured**

Run only if the local investment database/test services are available:

```powershell
py -m pytest tests/integration/test_investment_postgres.py -q
```

Expected: PASS or skipped due to missing integration environment.

- [ ] **Step 3: Manual UI smoke check**

Start the app as the project normally does in this environment, open the web console, and verify:

- System Config no longer shows component prompts.
- Investment Components page is wide.
- Technical analysis card shows trigger, prompt, and script version.
- Rate card shows trigger and prompt, no script version table.
- Convertible bond card shows trigger and prompt, no script version table.
- Signal card renderer card shows script/template version info and no trigger editor.

---

## Rollout Notes

- Keep existing config keys in place for compatibility.
- Do not change message routing in the first refactor.
- Do not rename database columns or migrate stored config keys in this phase.
- Keep old `/api/investment/skills/*` endpoints until the UI and tests fully move to `/api/investment/components/*`.
- Treat "Skill" as legacy wording in code paths where renaming would create unnecessary churn; use "Component" in new APIs and UI.
