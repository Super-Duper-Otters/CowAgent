# WeChat Reply Rich Text Tags Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hard-coded WeChat rich-text links in reply-word editing with readable action tags that render to `weixin://bizmsgmenu` links at runtime and stay synchronized with active component triggers.

**Architecture:** Store reply words as editable templates containing short tokens such as `{{action:technical_analysis_example}}` and `{{action:get_result}}`. Runtime reply APIs render those tokens into WeChat rich links; the config API exposes template defaults, rendered previews, and action metadata so the web editor can show display text plus trigger text instead of raw anchor HTML.

**Tech Stack:** Python reply config/rendering modules, existing investment config API, vanilla JS admin console, pytest.

---

## File Structure

- `business/config/wechat_rich_text.py`: owns WeChat rich link creation and new action-tag definitions/rendering.
- `business/config/reply_config.py`: owns reply text defaults, template defaults, runtime rendering, format safety, and metadata.
- `business/config/config_service.py`: keep existing fallback behavior compatible; no schema change.
- `channel/web/web_channel.py`: return reply template values and rich-action metadata to the config page.
- `channel/web/static/js/console.js`: render reply action chips, edit templates without exposing raw anchors, and provide refresh/reset controls.
- `tests/test_business.py`: backend behavior tests for template values, runtime rendering, and trigger synchronization.
- `tests/test_wechatmp_business_reply.py`: regression tests for actual公众号 passive replies still containing clickable rich links.

---

### Task 1: Backend Template Tags

**Files:**
- Modify: `business/config/wechat_rich_text.py`
- Modify: `business/config/reply_config.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Write failing tests**

Add tests asserting:

```python
def test_reply_text_metadata_exposes_templates_and_rich_actions():
    from business.config.reply_config import reply_text_config_metadata

    metadata = reply_text_config_metadata()
    definition = metadata["definitions"]["reply.investment.input_error"]

    assert "{{action:technical_analysis_example}}" in definition["default_template"]
    assert "weixin://bizmsgmenu" not in definition["default_template"]
    assert metadata["rich_actions"]["technical_analysis_example"]["display_text"]
    assert metadata["rich_actions"]["technical_analysis_example"]["trigger_text"].startswith("#")


def test_reply_text_runtime_renders_rich_action_tags():
    from business.config.reply_config import render_reply_template

    rendered = render_reply_template("例如 {{action:technical_analysis_example}}")

    assert '<a href="weixin://bizmsgmenu?' in rendered
    assert "msgmenucontent=%23" in rendered
    assert "#000300.SH" in rendered
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
py -m pytest tests/test_business.py::test_reply_text_metadata_exposes_templates_and_rich_actions tests/test_business.py::test_reply_text_runtime_renders_rich_action_tags -q
```

Expected: FAIL because `default_template`, `rich_actions`, and `render_reply_template` do not exist yet.

- [ ] **Step 3: Implement action definitions and renderer**

Add a dataclass-like action registry in `business/config/wechat_rich_text.py` with actions:

```python
get_result -> content "1", display "回复1获取"
get_result_short -> content "1", display "回复1"
technical_analysis_example -> component "technical-analysis", target "000300.SH"
stock_not_found_example -> component "technical-analysis", target "300502.SZ"
rate_tracking -> component "rate", display "利率择时跟踪"
convertible_bond_tracking -> component "convertible-bond", display "转债量化日度跟踪"
```

Expose:

```python
reply_rich_action_metadata() -> dict[str, dict[str, Any]]
render_rich_text_template(template: str) -> str
```

- [ ] **Step 4: Split template and runtime defaults**

In `business/config/reply_config.py`, add:

```python
default_reply_template(key, default="")
get_reply_template(key, default="")
render_reply_template(template)
```

Make `get_reply_text()` call `render_reply_template(get_reply_template(...))`. Keep existing saved raw HTML valid by only expanding `{{action:...}}` tokens.

- [ ] **Step 5: Run backend tests**

Run:

```bash
py -m pytest tests/test_business.py::test_reply_text_metadata_exposes_templates_and_rich_actions tests/test_business.py::test_reply_text_runtime_renders_rich_action_tags -q
```

Expected: PASS.

---

### Task 2: Config API Editing State

**Files:**
- Modify: `business/config/reply_config.py`
- Modify: `channel/web/web_channel.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Write failing test**

Add a test that config metadata contains both editable templates and rendered preview:

```python
def test_reply_text_metadata_separates_template_from_rendered_default():
    from business.config.reply_config import reply_text_config_metadata

    definition = reply_text_config_metadata()["definitions"]["reply.wechatmp.immediate_ack"]

    assert "{{action:get_result}}" in definition["default_template"]
    assert "weixin://bizmsgmenu" in definition["default"]
    assert "get_result" in definition["rich_actions"]
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
py -m pytest tests/test_business.py::test_reply_text_metadata_separates_template_from_rendered_default -q
```

Expected: FAIL until metadata includes the new fields.

- [ ] **Step 3: Expose metadata fields**

Update `reply_text_config_metadata()` so every definition includes:

```python
default_template
default
rendered_preview
rich_actions
```

The top-level payload includes:

```python
rich_actions
```

- [ ] **Step 4: Keep `/api/investment/config` compatible**

Keep `configs` unchanged for non-reply keys. For reply keys, frontend can use `definition.default_template` when config is empty and can render chips from metadata.

- [ ] **Step 5: Run test**

Run:

```bash
py -m pytest tests/test_business.py::test_reply_text_metadata_separates_template_from_rendered_default -q
```

Expected: PASS.

---

### Task 3: Frontend Action-Tag Editor

**Files:**
- Modify: `channel/web/static/js/console.js`

- [ ] **Step 1: Render readable preview**

Update `renderInvestmentReplyConfigField()` to compute preview through a helper:

```javascript
investmentRenderReplyTemplatePreview(template, replyTexts)
```

The helper replaces `{{action:id}}` with compact chips showing `display_text` and `trigger_text`.

- [ ] **Step 2: Replace raw textarea-only editor**

Update `openInvestmentReplyConfigDialog()` to show:

```html
<textarea ... hidden raw template storage ...>
<div class="investment-reply-template-preview">chips + text</div>
<aside class="investment-reply-action-panel">selected action details</aside>
```

Keep the textarea available as the saved value so `saveInvestmentConfigKey(key, 'textarea')` remains compatible.

- [ ] **Step 3: Add insert/refresh/reset controls**

Add functions:

```javascript
insertInvestmentReplyAction(key, actionId)
refreshInvestmentReplyAction(key, actionId)
resetInvestmentReplyTemplate(key)
openInvestmentReplyActionPanel(key, actionId)
```

Refresh rewrites the action chip view from current backend metadata. Reset restores `default_template`.

- [ ] **Step 4: Keep placeholders working**

Keep `insertInvestmentReplyPlaceholder()` unchanged for `{pending_summary}`, `{items}`, `{target}`, and `{running_title}`.

- [ ] **Step 5: Manual UI smoke test**

Open the config page and verify:

- Rows show compact rich-action labels rather than raw `<a href=...>`.
- Edit dialog shows action list/chips.
- Refresh updates chip trigger display from metadata.
- Reset restores template tokens.
- Save persists the template string.

---

### Task 4: Regression Verification

**Files:**
- Modify only if tests reveal a gap: `channel/wechatmp/passive_reply.py`, `channel/wechatmp/passive_reply_cache.py`, `business/content/technical_analysis.py`
- Test: `tests/test_business.py`, `tests/test_wechatmp_business_reply.py`

- [ ] **Step 1: Run rich reply regression tests**

Run:

```bash
py -m pytest tests/test_business.py tests/test_wechatmp_business_reply.py -q
```

Expected: PASS.

- [ ] **Step 2: Compile touched Python files**

Run:

```bash
py -m compileall business\config\wechat_rich_text.py business\config\reply_config.py business\content\technical_analysis.py channel\wechatmp\passive_reply.py channel\wechatmp\passive_reply_cache.py channel\web\web_channel.py
```

Expected: no compile errors.

- [ ] **Step 3: Review dirty tree**

Run:

```bash
git status --short
git diff -- business/config/wechat_rich_text.py business/config/reply_config.py channel/web/static/js/console.js tests/test_business.py tests/test_wechatmp_business_reply.py
```

Expected: only scoped rich-text/reply-word changes from this task are in the diff.
