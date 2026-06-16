# Strategy Module Generalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make investment strategy modules generic for both backend pre-produced content and customer-triggered prompt-to-image generation, while preserving existing rate, convertible-bond, and technical-analysis behavior.

**Architecture:** Keep the existing investment business stack and add only a thin generic module layer. Module registration stays simple through `component.json`; routing dispatches by `handler_type`; pre-produced modules reuse `content_records`; on-demand prompt-to-image modules reuse existing prompt, AI generation, renderer, request record, artifact, and WeChat passive delivery infrastructure. Caching is explicitly out of scope for this implementation.

**Tech Stack:** Python, web.py handlers, SQLAlchemy table helpers, existing investment DB tables, existing WeChat passive reply cache, existing JavaScript console UI, pytest.

---

## Scope

Implement:

- Backend pre-produced modules like rate and convertible-bond as generic `daily_content` modules.
- Customer-triggered modules as generic `prompt_to_image` modules.
- Simple module registration metadata.
- Generic business dispatch by `handler_type`.
- Web console dynamic listing for pre-produced content modules.
- WeChat direct delivery for pre-produced modules and deferred "reply 1" delivery for on-demand modules.
- Tests for registry, routing, web API/UI expectations, and WeChat reply flow.

Do not implement:

- Generic caching for prompt-to-image modules.
- A visual module creation wizard.
- Custom database tables per module.
- A new permission model.
- A new plugin package format beyond current `component.json` plus optional scripts/assets.
- Replacement of the technical-analysis implementation.

## File Structure

### New Files

- `builtin/components/rate/component.json`
  - Built-in registration for the rate pre-produced content module.

- `builtin/components/convertible-bond/component.json`
  - Built-in registration for the convertible-bond pre-produced content module.

- `business/module_dispatcher.py`
  - Single entry point for executing matched modules by `handler_type`.

- `business/prompt_to_image_handler.py`
  - Generic on-demand customer request handler: prompt resolution, AI standard text generation, renderer invocation, artifact recording, and `BusinessReply` generation.

### Modified Files

- `business/business_registry.py`
  - Keep registration simple.
  - Read `component.json` for rate and convertible-bond.
  - Preserve current built-in fallback definitions during migration.
  - Add simple module metadata fields: `generation_mode`, `delivery_mode`, and optional `content_enabled`.

- `business/router.py`
  - Replace service-type-specific execution branches with `module_dispatcher.dispatch_module()`.
  - Keep permission checks by `service_type`.
  - Add `module_key` to `RouteResult` and `BusinessReply`.

- `business/business_router.py`
  - Copy `module_key` to outgoing `Reply` metadata.

- `business/daily_content_handler.py`
  - Accept a full module definition, not only `route.service_type`.
  - Return direct output for pre-produced content.

- `business/investment/daily_content.py`
  - Remove the hard dependency on `CONTENT_SERVICE_TYPES` for execution.
  - Keep validation simple: allow any module definition with `handler_type == "daily_content"` and a valid legacy `service_type`.
  - Preserve existing rate/convertible-bond behavior.

- `business/investment/skill_runner.py`
  - Stop being the primary route dispatcher.
  - Keep script execution helper reusable by `module_dispatcher`.

- `business/investment/render_service.py`
  - Resolve templates by `template_key` when provided.
  - Preserve current `template_for_service()` fallback.

- `business/investment/component_service.py`
  - Expose whether a component is a pre-produced content module or an on-demand prompt-to-image module.

- `channel/web/web_channel.py`
  - Support `module_key` in daily-content API.
  - Keep `service_type` compatibility.

- `channel/web/static/js/console.js`
  - Build investment content tabs from components instead of hard-coded rate/convertible-bond tabs.
  - Keep labels and upload flow simple.

- `channel/wechatmp/passive_reply_cache.py`
  - Carry `module_key` in cached passive results.

- `channel/wechatmp/wechatmp_channel.py`
  - Store `module_key` when queueing passive replies.

- `channel/wechatmp/passive_reply.py`
  - Keep technical-analysis special behavior.
  - Use module delivery metadata to allow direct/deferred behavior without hard-coding rate or convertible-bond.

- `tests/test_investment_business.py`
  - Registry, dispatcher, daily-content, prompt-to-image tests.

- `tests/test_investment_web_ui.py`
  - Dynamic content module tabs and API compatibility tests.

- `tests/test_wechatmp_investment_reply.py`
  - WeChat direct/deferred delivery tests.

---

## Task 1: Simple Module Metadata and Built-In Manifests

**Files:**

- Create: `builtin/components/rate/component.json`
- Create: `builtin/components/convertible-bond/component.json`
- Modify: `business/business_registry.py`
- Modify: `business/investment/component_service.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing registry tests**

Add tests proving rate and convertible-bond are loaded as regular component definitions and expose simple metadata:

```python
def test_content_strategy_components_are_manifest_backed():
    from business.business_registry import get_business_definition

    rate = get_business_definition("rate")
    bond = get_business_definition("convertible-bond")

    assert rate.handler_type == "daily_content"
    assert rate.generation_mode == "pre_generated"
    assert rate.delivery_mode == "direct"
    assert rate.content_enabled is True
    assert rate.routable is True
    assert rate.default_triggers == ("利率",)

    assert bond.handler_type == "daily_content"
    assert bond.generation_mode == "pre_generated"
    assert bond.delivery_mode == "direct"
    assert bond.content_enabled is True
    assert bond.routable is True
    assert bond.default_triggers == ("转债",)
```

Add a component-service test:

```python
def test_component_service_marks_content_modules():
    from business.investment.component_service import list_components

    by_key = {item["component_key"]: item for item in list_components()}

    assert by_key["rate"]["content_enabled"] is True
    assert by_key["rate"]["generation_mode"] == "pre_generated"
    assert by_key["convertible-bond"]["content_enabled"] is True
    assert by_key["signal-card-renderer"]["content_enabled"] is False
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
pytest tests/test_investment_business.py -k "content_strategy_components_are_manifest_backed or component_service_marks_content_modules" -q
```

Expected: tests fail because `generation_mode`, `delivery_mode`, or `content_enabled` are not yet present.

- [ ] **Step 3: Add simple component manifests**

Create `builtin/components/rate/component.json`:

```json
{
  "component_key": "rate",
  "label": "利率组件",
  "description": "返回当前生效的利率投研内容图片。",
  "service_type": "rate",
  "match_type": "exact",
  "default_triggers": ["利率"],
  "handler_type": "daily_content",
  "generation_mode": "pre_generated",
  "delivery_mode": "direct",
  "content_enabled": true,
  "output_mode": "image",
  "routable": true,
  "storage_name": "rate",
  "component_type": "active_prompt",
  "prompt_key": "prompt.rate",
  "renderer_component_key": "signal-card-renderer",
  "template_key": "rate"
}
```

Create `builtin/components/convertible-bond/component.json`:

```json
{
  "component_key": "convertible-bond",
  "label": "转债组件",
  "description": "返回当前生效的可转债投研内容图片。",
  "service_type": "convertible_bond",
  "match_type": "exact",
  "default_triggers": ["转债"],
  "handler_type": "daily_content",
  "generation_mode": "pre_generated",
  "delivery_mode": "direct",
  "content_enabled": true,
  "output_mode": "image",
  "routable": true,
  "storage_name": "convertible-bond",
  "component_type": "active_prompt",
  "prompt_key": "prompt.convertible_bond",
  "renderer_component_key": "signal-card-renderer",
  "template_key": "convertible_bond"
}
```

- [ ] **Step 4: Extend `BusinessDefinition` minimally**

Add fields to `business/business_registry.py`:

```python
generation_mode: str = ""
delivery_mode: str = "direct"
content_enabled: bool = False
```

Include them in `_definition()`, `read_component_definition()`, and `as_dict()`.

Rules:

- If manifest omits `generation_mode`, default to `"pre_generated"` for `daily_content`, `"on_demand"` for `technical_analysis` and `prompt_to_image`, else `""`.
- If manifest omits `delivery_mode`, default to `"direct"` for `daily_content`, `"deferred"` for `technical_analysis` and `prompt_to_image`.
- If manifest omits `content_enabled`, default to `handler_type == "daily_content"`.

- [ ] **Step 5: Expose metadata in component service**

Ensure `list_components()` returns:

```python
item["generation_mode"] = definition.generation_mode
item["delivery_mode"] = definition.delivery_mode
item["content_enabled"] = definition.content_enabled
```

- [ ] **Step 6: Run tests**

Run:

```powershell
pytest tests/test_investment_business.py -k "content_strategy_components_are_manifest_backed or component_service_marks_content_modules" -q
```

Expected: PASS.

---

## Task 2: Generic Module Dispatcher

**Files:**

- Create: `business/module_dispatcher.py`
- Modify: `business/router.py`
- Modify: `business/business_router.py`
- Modify: `business/daily_content_handler.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing dispatcher tests**

Add a test that proves rate no longer needs a service-specific branch:

```python
def test_router_dispatches_daily_content_by_handler_type(investment_env, tmp_path, monkeypatch):
    from business.constants import ServiceType
    from business.investment.daily_content import create_content_draft, set_content_effective
    from business.router import handle_text_message

    image = tmp_path / "rate.png"
    image.write_bytes(b"png")
    content_id = create_content_draft(ServiceType.RATE, source_text="rate source", operator="pytest")
    set_content_effective(content_id, str(image), operator="pytest")

    reply = handle_text_message("openid-rate-generic", "利率", skip_permission=True)

    assert reply.handled is True
    assert reply.success is True
    assert reply.module_key == "rate"
    assert reply.service_type == ServiceType.RATE
    assert reply.output_files == [str(image)]
```

Add a metadata propagation test:

```python
def test_business_router_sets_module_key_on_reply(monkeypatch):
    from bridge.context import Context
    from business.constants import ServiceType
    from business.router import BusinessReply
    from business.business_router import _reply_from_business

    business_reply = BusinessReply(
        handled=True,
        success=True,
        reply_text="[图片: x.png]",
        output_files=["x.png"],
        service_type=ServiceType.RATE,
        module_key="rate",
        request_id="request-1",
    )

    reply = _reply_from_business(business_reply)

    assert reply.business_module_key == "rate"
    assert reply.investment_module_key == "rate"
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
pytest tests/test_investment_business.py -k "router_dispatches_daily_content_by_handler_type or business_router_sets_module_key_on_reply" -q
```

Expected: tests fail because `module_key` is not on `BusinessReply` and dispatcher does not exist.

- [ ] **Step 3: Create `business/module_dispatcher.py`**

Implement a small dispatcher:

```python
# encoding:utf-8
"""Generic investment module dispatch."""

from business.constants import ErrorCode, user_message


def dispatch_module(definition, openid, raw_input, route, *, customer_metadata=None, elapsed=lambda: 0, technical_analysis_handler=None):
    handler_type = str(getattr(definition, "handler_type", "") or "")

    if handler_type == "daily_content":
        from business.daily_content_handler import handle_daily_content

        return handle_daily_content(
            openid,
            raw_input,
            route,
            definition=definition,
            customer_metadata=customer_metadata,
            elapsed=elapsed,
        )

    if handler_type in {"technical_analysis", "builtin_technical_analysis"}:
        from business.technical_analysis_handler import handle_technical_analysis

        return handle_technical_analysis(
            openid,
            raw_input,
            route,
            customer_metadata=customer_metadata,
            elapsed=elapsed,
            technical_analysis_handler=technical_analysis_handler,
        )

    if handler_type == "script":
        from business.skill_runner import run_investment_skill
        from business.router import BusinessReply
        from business.business_records import create_business_record, mark_business_failed, mark_business_success
        from business.config_service import sanitize_sensitive_text

        request_id = create_business_record(
            openid,
            raw_input,
            route.service_type,
            customer_name=(customer_metadata or {}).get("customer_name", ""),
            institution=(customer_metadata or {}).get("institution", ""),
        )
        result = run_investment_skill(definition, openid, raw_input, getattr(route, "target_text", ""))
        if not result.success:
            code = result.error_code or ErrorCode.SYSTEM_ERROR
            prompt = result.user_prompt or user_message(code)
            detail = sanitize_sensitive_text(result.detail)
            mark_business_failed(request_id, code, prompt, detail, elapsed())
            return BusinessReply(True, False, prompt, [], route.service_type, code, prompt, detail, request_id, module_key=definition.business_key)
        mark_business_success(request_id, output_files=result.output_files, elapsed_ms=elapsed())
        return BusinessReply(True, True, result.reply_text, result.output_files, route.service_type, request_id=request_id, module_key=definition.business_key)

    from business.router import BusinessReply

    return BusinessReply(
        True,
        False,
        user_message(ErrorCode.INPUT_ERROR),
        [],
        route.service_type,
        ErrorCode.INPUT_ERROR,
        request_id="",
        module_key=getattr(definition, "business_key", ""),
        detail=f"unsupported handler_type: {handler_type}",
    )
```

- [ ] **Step 4: Add `module_key` to route and reply models**

In `business/router.py`:

- Add `module_key: str = ""` to `RouteResult`.
- Add `module_key: str = ""` to `BusinessReply`.
- In `parse_route()`, set `module_key=matched.business_key`.

- [ ] **Step 5: Replace service-specific execution branches**

In `handle_text_message()`:

- After permission succeeds and definition is loaded, call:

```python
from business.module_dispatcher import dispatch_module

return dispatch_module(
    definition,
    openid,
    raw_input,
    route,
    customer_metadata=customer_metadata,
    elapsed=elapsed,
    technical_analysis_handler=technical_analysis_handler,
)
```

Remove the direct rate/convertible-bond and technical-analysis branches from `router.py`.

- [ ] **Step 6: Update daily content handler signature**

In `business/daily_content_handler.py`, change `handle_daily_content()` to accept `definition=None`.

Use:

```python
module_key = getattr(definition, "business_key", "") or getattr(route, "module_key", "")
service_type = getattr(definition, "service_type", None) or route.service_type
```

Set returned `BusinessReply(..., module_key=module_key)`.

- [ ] **Step 7: Propagate module metadata to bridge replies**

In `business/business_router.py`, add:

```python
if getattr(business_reply, "module_key", ""):
    reply.business_module_key = business_reply.module_key
    reply.investment_module_key = business_reply.module_key
```

- [ ] **Step 8: Run dispatcher tests**

Run:

```powershell
pytest tests/test_investment_business.py -k "router_dispatches_daily_content_by_handler_type or business_router_sets_module_key_on_reply" -q
```

Expected: PASS.

---

## Task 3: Generic Prompt-To-Image On-Demand Handler

**Files:**

- Create: `business/prompt_to_image_handler.py`
- Modify: `business/module_dispatcher.py`
- Modify: `business/investment/render_service.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing prompt-to-image tests**

Add a test with an uploaded/runtime component manifest:

```python
def test_prompt_to_image_module_generates_image_from_customer_input(investment_env, tmp_path, monkeypatch):
    import json
    from pathlib import Path

    from business.investment.component_paths import runtime_component_root
    from business.router import handle_text_message

    component_dir = runtime_component_root("macro-brief")
    component_dir.mkdir(parents=True, exist_ok=True)
    (component_dir / "component.json").write_text(json.dumps({
        "component_key": "macro-brief",
        "label": "宏观简报",
        "description": "按客户输入生成宏观简报图。",
        "service_type": "unmatched",
        "match_type": "prefix",
        "default_triggers": ["宏观简报"],
        "handler_type": "prompt_to_image",
        "generation_mode": "on_demand",
        "delivery_mode": "deferred",
        "output_mode": "image",
        "routable": True,
        "component_type": "active_prompt",
        "prompt_key": "prompt.macro_brief",
        "renderer_component_key": "signal-card-renderer",
        "template_key": "rate"
    }, ensure_ascii=False), encoding="utf-8")

    output = tmp_path / "macro.png"

    def fake_generate_standard_text(service_type, source_text, source_files=None, prompt_key="", module_key=""):
        assert "今天流动性偏宽" in source_text
        assert prompt_key == "prompt.macro_brief"
        assert module_key == "macro-brief"
        return type("AIResult", (), {
            "success": True,
            "text": "标准宏观简报",
            "prompt": "prompt used",
            "detail": "",
            "error_code": None,
        })()

    def fake_render_card(request, renderer=None):
        output.write_bytes(b"png")
        return type("RenderResult", (), {
            "success": True,
            "image_path": str(output),
            "output_files": [str(output)],
            "detail": "",
            "error_code": None,
            "user_prompt": "",
        })()

    monkeypatch.setattr("business.prompt_to_image_handler.generate_standard_text_for_module", fake_generate_standard_text)
    monkeypatch.setattr("business.prompt_to_image_handler.render_card", fake_render_card)

    reply = handle_text_message("openid-macro", "宏观简报 今天流动性偏宽", skip_permission=True)

    assert reply.success is True
    assert reply.module_key == "macro-brief"
    assert reply.output_files == [str(output)]
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
pytest tests/test_investment_business.py -k "prompt_to_image_module_generates_image_from_customer_input" -q
```

Expected: FAIL because `prompt_to_image` is unsupported.

- [ ] **Step 3: Add prefix matching support if missing**

In `business/business_registry.match_business()`, support:

```python
if definition.match_type == "prefix":
    for trigger in triggers:
        if text.startswith(trigger):
            target = text[len(trigger):].strip()
            return BusinessMatch(
                definition.business_key,
                definition.service_type,
                raw_input,
                target,
                definition.skill_key or definition.business_key,
            )
```

- [ ] **Step 4: Create prompt-to-image handler**

Create `business/prompt_to_image_handler.py`:

```python
# encoding:utf-8
"""Generic on-demand prompt-to-image module handler."""

from pathlib import Path

from business.business_records import create_business_record, mark_business_failed, mark_business_success
from business.config_service import sanitize_sensitive_text
from business.constants import ErrorCode, user_message
from business.investment.render_service import RenderRequest, render_card


def _image_reply(paths: list[str]) -> str:
    return "\n".join(f"[图片: {path}]" for path in paths)


def generate_standard_text_for_module(service_type, source_text, source_files=None, prompt_key="", module_key=""):
    from business.investment.ai_generation import generate_standard_text

    return generate_standard_text(service_type, source_text, source_files=source_files, prompt_key=prompt_key, module_key=module_key)


def handle_prompt_to_image(openid, raw_input, route, *, definition, customer_metadata=None, elapsed=lambda: 0):
    from business.router import BusinessReply

    customer_metadata = customer_metadata or {}
    module_key = getattr(definition, "business_key", "") or getattr(route, "module_key", "")
    service_type = definition.service_type
    request_id = create_business_record(
        openid,
        raw_input,
        service_type,
        customer_name=customer_metadata.get("customer_name", ""),
        institution=customer_metadata.get("institution", ""),
    )
    source_text = getattr(route, "target_text", "") or raw_input
    try:
        ai_result = generate_standard_text_for_module(
            service_type,
            source_text,
            source_files=[],
            prompt_key=getattr(definition, "prompt_key", ""),
            module_key=module_key,
        )
        if not ai_result.success:
            code = getattr(ai_result, "error_code", None) or ErrorCode.SYSTEM_ERROR
            prompt = user_message(code)
            detail = sanitize_sensitive_text(getattr(ai_result, "detail", ""))
            mark_business_failed(request_id, code, prompt, detail, elapsed())
            return BusinessReply(True, False, prompt, [], service_type, code, prompt, detail, request_id, module_key=module_key)

        render_result = render_card(RenderRequest(
            service_type=service_type,
            standard_text=str(getattr(ai_result, "text", "")),
        ))
        if not render_result.success:
            code = getattr(render_result, "error_code", None) or ErrorCode.IMAGE_GENERATION_FAILED
            prompt = getattr(render_result, "user_prompt", "") or user_message(code)
            detail = sanitize_sensitive_text(getattr(render_result, "detail", ""))
            mark_business_failed(request_id, code, prompt, detail, elapsed())
            return BusinessReply(True, False, prompt, [], service_type, code, prompt, detail, request_id, module_key=module_key)

        output_files = [str(item) for item in getattr(render_result, "output_files", []) or [getattr(render_result, "image_path", "")] if str(item)]
        mark_business_success(request_id, output_files=output_files, elapsed_ms=elapsed())
        return BusinessReply(
            True,
            True,
            _image_reply(output_files),
            output_files,
            service_type,
            request_id=request_id,
            module_key=module_key,
            source_type="request",
            source_id=request_id,
        )
    except Exception as exc:
        detail = sanitize_sensitive_text(str(exc))
        prompt = user_message(ErrorCode.SYSTEM_ERROR)
        mark_business_failed(request_id, ErrorCode.SYSTEM_ERROR, prompt, detail, elapsed())
        return BusinessReply(True, False, prompt, [], service_type, ErrorCode.SYSTEM_ERROR, prompt, detail, request_id, module_key=module_key)
```

- [ ] **Step 5: Register handler in dispatcher**

In `business/module_dispatcher.py`:

```python
if handler_type == "prompt_to_image":
    from business.prompt_to_image_handler import handle_prompt_to_image

    return handle_prompt_to_image(
        openid,
        raw_input,
        route,
        definition=definition,
        customer_metadata=customer_metadata,
        elapsed=elapsed,
    )
```

- [ ] **Step 6: Make AI generation wrapper compatible**

If `business.investment.ai_generation.generate_standard_text()` does not accept `prompt_key` or `module_key`, update `generate_standard_text_for_module()` to read prompt text with `get_config(prompt_key, "")` and pass through existing arguments without changing the lower-level function signature.

- [ ] **Step 7: Run prompt-to-image test**

Run:

```powershell
pytest tests/test_investment_business.py -k "prompt_to_image_module_generates_image_from_customer_input" -q
```

Expected: PASS.

---

## Task 4: Web Console Dynamic Pre-Produced Content Modules

**Files:**

- Modify: `channel/web/web_channel.py`
- Modify: `channel/web/static/js/console.js`
- Test: `tests/test_investment_web_ui.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing API compatibility test**

Add:

```python
def test_daily_content_api_accepts_module_key_for_content_modules(investment_env, tmp_path):
    from business.constants import ServiceType
    from business.investment.daily_content import create_content_draft, set_content_effective
    from channel.web.web_channel import InvestmentDailyContentHandler

    image = tmp_path / "rate-current.png"
    image.write_bytes(b"png")
    content_id = create_content_draft(ServiceType.RATE, source_text="rate", operator="pytest")
    set_content_effective(content_id, str(image), operator="pytest")

    response = InvestmentDailyContentHandler().GET()

    assert response
```

Adapt the existing web test helper style in `tests/test_investment_business.py` to pass query params `module_key=rate` and assert:

```python
assert payload["current_effective"]["module_key"] == "rate"
assert payload["contents"][0]["module_key"] == "rate"
```

- [ ] **Step 2: Write failing UI test**

In `tests/test_investment_web_ui.py`, add a static JS test that asserts the content page no longer hard-codes only two tabs:

```python
def test_daily_content_tabs_are_built_from_content_components():
    js = Path("channel/web/static/js/console.js").read_text(encoding="utf-8")

    assert "content_enabled" in js
    assert "renderInvestmentContentModuleTabs" in js
    assert "currentInvestmentContentModuleKey" in js
```

- [ ] **Step 3: Run failing tests**

Run:

```powershell
pytest tests/test_investment_business.py -k "daily_content_api_accepts_module_key" -q
pytest tests/test_investment_web_ui.py -k "daily_content_tabs_are_built_from_content_components" -q
```

Expected: FAIL until API and UI are updated.

- [ ] **Step 4: Add module resolution helper in web handler**

In `InvestmentDailyContentHandler.GET/POST`, resolve:

```python
module_key = str(getattr(params, "module_key", "") or body.get("module_key", "") or "").strip()
if module_key:
    from business.business_registry import get_business_definition
    definition = get_business_definition(module_key)
    service_type = definition.service_type
else:
    service_type = normalize_service(service_value) if service_value else None
    definition = None
```

Response rows should include:

```python
"module_key": module_key or _module_key_for_service(record.service_type),
"module_label": definition.label if definition else investmentServiceLabel fallback,
```

Implement `_module_key_for_service()` locally or in a small helper by scanning `list_business_definitions()`.

- [ ] **Step 5: Keep POST compatible**

Allow POST body or multipart form to include `module_key`.

Use module definition to find service_type:

```python
if module_key:
    service_type = get_business_definition(module_key).service_type
else:
    service_type = normalize_service(body.get("service_type", ""))
```

Store content as before.

- [ ] **Step 6: Update console state**

In `console.js`, add:

```javascript
let currentInvestmentContentModuleKey = '';
```

Add:

```javascript
function investmentContentModules() {
    return (currentInvestmentSkills || []).filter(component => component.content_enabled || component.handler_type === 'daily_content');
}
```

Add `renderInvestmentContentModuleTabs(modules)` that renders buttons from `module_key/component_key`, label, and icon fallback.

- [ ] **Step 7: Update daily content render flow**

Change `renderInvestmentDailyContent()` to:

- Ensure components are loaded.
- Pick the first content module if `currentInvestmentContentModuleKey` is empty.
- Render tabs dynamically.
- Call `renderInvestmentContent(moduleKey)`.

Change requests to:

```javascript
const query = new URLSearchParams({module_key: moduleKey});
```

Keep service_type fallback only when old functions call with `rate` or `convertible_bond`.

- [ ] **Step 8: Run web tests**

Run:

```powershell
pytest tests/test_investment_business.py -k "daily_content_api_accepts_module_key" -q
pytest tests/test_investment_web_ui.py -k "daily_content_tabs_are_built_from_content_components" -q
```

Expected: PASS.

---

## Task 5: WeChat Direct vs Deferred Delivery

**Files:**

- Modify: `business/router.py`
- Modify: `business/business_router.py`
- Modify: `channel/wechatmp/passive_reply_cache.py`
- Modify: `channel/wechatmp/wechatmp_channel.py`
- Modify: `channel/wechatmp/passive_reply.py`
- Test: `tests/test_wechatmp_investment_reply.py`

- [ ] **Step 1: Write failing cache metadata test**

Add:

```python
def test_passive_reply_cache_keeps_module_key():
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    cache = PassiveReplyCache(now_func=lambda: 100)
    cache.append_reply("openid", "image", "media-id", "宏观简报", service_type="unmatched", module_key="macro-brief", request_id="req-1")

    result = cache.peek_result("openid")

    assert result.module_key == "macro-brief"
```

- [ ] **Step 2: Write failing direct/deferred metadata test**

Add a test around `WechatMPChannel.send()` or existing helpers proving module key is carried into passive cache when reply metadata exists:

```python
def test_wechatmp_send_caches_business_module_key(monkeypatch):
    from bridge.reply import Reply, ReplyType
    from channel.wechatmp.wechatmp_channel import WechatMPChannel

    channel = WechatMPChannel()
    reply = Reply(ReplyType.TEXT, "ready")
    reply.business_module_key = "macro-brief"
    reply.business_service_type = "unmatched"
    reply.business_request_id = "req-1"
    context = {"receiver": "openid", "msg": type("Msg", (), {"msg_id": "m1"})(), "content": "宏观简报 xxx"}

    channel.send(reply, context)

    assert channel.cache_dict.peek_result("openid").module_key == "macro-brief"
```

- [ ] **Step 3: Run failing tests**

Run:

```powershell
pytest tests/test_wechatmp_investment_reply.py -k "module_key or caches_business_module_key" -q
```

Expected: FAIL because module_key is not cached.

- [ ] **Step 4: Extend passive cache dataclass and methods**

In `PassiveReplyResult`, add:

```python
module_key: str = ""
```

Update:

- `append_result()`
- `append_reply()`
- `peek_result()`
- `_find_append_target_locked()`
- `pop_result_for_title()`

to preserve `module_key`.

- [ ] **Step 5: Propagate module_key from channel send**

In `WechatMPChannel.send()`:

```python
business_module_key = getattr(reply, "business_module_key", "") or getattr(reply, "investment_module_key", "")
```

Pass `module_key=business_module_key` to every `append_reply()` call.

- [ ] **Step 6: Keep direct/deferred behavior simple**

Do not change direct sending logic for Web.

For WeChat:

- Pre-produced `daily_content` modules can still be cached and returned immediately if generated within the passive window.
- On-demand `prompt_to_image` modules use the existing pending cache path and `reply 1` behavior when generation takes longer than the passive wait.
- Technical-analysis special prompts remain unchanged.

No custom module queue logic is required in this task.

- [ ] **Step 7: Run WeChat tests**

Run:

```powershell
pytest tests/test_wechatmp_investment_reply.py -k "module_key or caches_business_module_key" -q
```

Expected: PASS.

---

## Task 6: Integration Cleanup and Full Verification

**Files:**

- Modify only files touched by prior tasks if integration issues appear.
- Test: `tests/test_investment_business.py`
- Test: `tests/test_investment_web_ui.py`
- Test: `tests/test_wechatmp_investment_reply.py`

- [ ] **Step 1: Run targeted investment suite**

Run:

```powershell
pytest tests/test_investment_business.py tests/test_investment_web_ui.py tests/test_wechatmp_investment_reply.py -q
```

Expected: PASS or only unrelated pre-existing failures.

- [ ] **Step 2: Fix compatibility failures**

If existing tests fail because they expect old hard-coded values:

- Keep old API fields.
- Add new fields instead of replacing old fields.
- Keep `service_type` in all responses.
- Keep rate and convertible-bond labels unchanged.
- Keep `ServiceType` enum unchanged.

- [ ] **Step 3: Check static references for hard-coded content tabs**

Run:

```powershell
rg -n "利率内容|转债内容|convertible_bond|CONTENT_SERVICE_TYPES|ServiceType.RATE, ServiceType.CONVERTIBLE_BOND" business channel/web/static/js tests
```

Expected:

- Hard-coded labels may remain in fallback tests or legacy label maps.
- No business router dispatch should depend on `ServiceType.RATE, ServiceType.CONVERTIBLE_BOND`.
- No content page tab rendering should be limited to only rate and convertible-bond.

- [ ] **Step 4: Run registry smoke commands**

Run:

```powershell
@'
from business.business_registry import list_business_definitions
for item in list_business_definitions():
    print(item.business_key, item.handler_type, item.generation_mode, item.delivery_mode, item.content_enabled)
'@ | python -
```

Expected output includes:

```text
technical-analysis builtin_technical_analysis on_demand deferred False
rate daily_content pre_generated direct True
convertible-bond daily_content pre_generated direct True
signal-card-renderer renderer  direct False
```

- [ ] **Step 5: Final test run**

Run:

```powershell
pytest tests/test_investment_business.py tests/test_investment_web_ui.py tests/test_wechatmp_investment_reply.py -q
```

Expected: PASS.

---

## Implementation Notes

- Keep `ServiceType` intact.
- Keep old `service_type` API parameters intact.
- Add `module_key` without forcing a database migration unless a task explicitly needs it.
- Avoid new folders beyond `builtin/components/rate` and `builtin/components/convertible-bond`.
- Do not introduce a generic plugin framework.
- Do not implement cache for `prompt_to_image`.
- Keep handler code small and explicit.
- If a generic helper becomes complex, prefer a local helper in the file that needs it.

## Self-Review Checklist

- Every requirement is mapped to a task.
- No cache implementation is included.
- rate and convertible-bond remain backend pre-produced modules.
- prompt-to-image covers customer-triggered generation.
- technical-analysis upgrade flow is preserved.
- Web and WeChat remain compatible with existing behavior.
- Module registration remains simple `component.json`.
