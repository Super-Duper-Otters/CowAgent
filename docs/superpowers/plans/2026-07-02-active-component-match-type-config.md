# Active Component Match Type Config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let every active investment component edit trigger match position from its component configuration page.

**Architecture:** Store runtime match type in `skill.<component>.match_type`, falling back to the component manifest default. Component listing exposes the effective value in `settings.match_type`, settings save/reset updates the runtime config, and routing uses the resolved match type.

**Tech Stack:** Python business services, web.py handlers, vanilla JavaScript console UI, pytest.

---

### Task 1: Backend Behavior

**Files:**
- Modify: `business/components/registry.py`
- Modify: `business/components/service.py`
- Modify: `channel/web/web_channel.py`
- Test: `tests/test_business.py`

- [x] **Step 1: Write failing tests**

Add tests covering runtime match type route parsing and component settings save.

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_business.py::test_parse_route_uses_configured_active_component_match_type tests/test_business.py::test_component_settings_save_updates_active_component_match_type -q`

- [ ] **Step 3: Implement runtime match type helpers**

Add `match_type_config_key` and `resolve_match_type()`, validate `exact|prefix|suffix`, use it in routing and component settings.

- [ ] **Step 4: Verify backend tests pass**

Run the same targeted pytest command.

### Task 2: Console UI

**Files:**
- Modify: `channel/web/static/js/console.js`

- [ ] **Step 1: Add match type control for all active components**

Render a dropdown beside trigger words for any `uses_triggers` component, prefilled from `settings.match_type`.

- [ ] **Step 2: Include match type in save payload**

Add top-level `match_type` to component settings payload when the dropdown exists.

- [ ] **Step 3: Verify existing runtime component manifest editing still uses `component_config.match_type`**

Keep existing command/prompt runtime manifest editors intact.

### Task 3: Final Verification

**Files:**
- Test: `tests/test_business.py`

- [ ] **Step 1: Run targeted regression tests**

Run component settings, route, and web UI tests touched by this behavior.
