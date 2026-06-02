# Investment Reply Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move investment and WeChatMP reply text from hard-coded constants into editable investment database configuration, exposed in the existing system configuration page.

**Architecture:** Reuse `investment_configs` as the persistence layer. Add a focused reply configuration module that defines metadata, defaults, and formatting helpers; then route `business/investment/constants.py` and `channel/wechatmp/passive_reply.py` through it. Extend the existing config API and UI so admins can edit reply text with one save button per field.

**Tech Stack:** Python, SQLAlchemy-backed `investment_configs`, web.py handlers, vanilla JavaScript console UI, pytest.

---

## File Structure

- Create `business/investment/reply_config.py`: reply key constants, labels, descriptions, defaults, grouped metadata, database-backed lookup, and safe `.format()` helper.
- Modify `business/investment/constants.py`: keep enums and default error messages, but make `user_message()` read reply configuration.
- Modify `channel/wechatmp/passive_reply.py`: replace module-level reply text constants with reply config lookups at call sites.
- Modify `business/investment/config_service.py`: add reply config keys to `CONFIG_FALLBACK_KEYS`; keep existing validation and permission behavior.
- Modify `channel/web/web_channel.py`: return reply config metadata from `InvestmentConfigHandler.GET` so UI can display human-friendly names and descriptions without duplicating backend definitions.
- Modify `channel/web/static/js/console.js`: add a “公众号回复词” section on the system configuration page using textarea fields and descriptions.
- Modify `channel/web/static/css/console.css`: add compact helper text styling for reply descriptions if existing field styling is insufficient.
- Modify `tests/test_investment_business.py`: backend behavior and API tests.
- Modify `tests/test_wechatmp_investment_reply.py`: WeChatMP dynamic reply tests.
- Modify `tests/test_investment_web_ui.py`: static UI coverage for the reply section.

---

### Task 1: Reply Config Metadata And Investment Error Messages

**Files:**
- Create: `business/investment/reply_config.py`
- Modify: `business/investment/constants.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing tests for default and database-backed investment error messages**

Add these tests near existing config service tests in `tests/test_investment_business.py`:

```python
def test_investment_user_message_uses_reply_config_defaults(investment_env):
    from business.investment.constants import ErrorCode, user_message

    assert user_message(ErrorCode.UNAUTHORIZED) == "您暂未开通该服务，如需开通请联系服务人员。"
    assert user_message(ErrorCode.SYSTEM_ERROR) == "系统暂时繁忙，请稍后重试。"


def test_investment_user_message_can_be_overridden_from_database(investment_env):
    from business.investment.config_service import save_config
    from business.investment.constants import ErrorCode, user_message

    save_config("reply.investment.unauthorized", "请联系客户经理开通权限。", operator_role="admin", operator="pytest")

    assert user_message(ErrorCode.UNAUTHORIZED) == "请联系客户经理开通权限。"
    assert user_message(ErrorCode.SYSTEM_ERROR) == "系统暂时繁忙，请稍后重试。"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
py -m pytest tests\test_investment_business.py -k "reply_config or user_message_uses_reply_config or user_message_can_be_overridden" -q
```

Expected: fail because `reply_config` does not exist and `user_message()` does not read `reply.investment.*`.

- [ ] **Step 3: Implement reply config module**

Create `business/investment/reply_config.py`:

```python
# encoding:utf-8
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReplyTextDefinition:
    key: str
    label: str
    description: str
    default: str
    placeholders: tuple[str, ...] = ()


INVESTMENT_REPLY_DEFINITIONS = [
    ReplyTextDefinition("reply.investment.unauthorized", "未开通服务提示", "客户没有开通当前服务时返回。", "您暂未开通该服务，如需开通请联系服务人员。"),
    ReplyTextDefinition("reply.investment.user_disabled", "服务停用提示", "客户账号被停用时返回。", "您的服务已停用，如需恢复请联系服务人员。"),
    ReplyTextDefinition("reply.investment.auth_expired", "授权过期提示", "客户授权时间过期时返回。", "您的授权已过期，如需续期请联系服务人员。"),
    ReplyTextDefinition("reply.investment.input_error", "输入格式错误提示", "客户输入无法匹配服务格式时返回。", "请输入：股票代码/股票名称 + 技术分析，或输入“利率”“转债”。"),
    ReplyTextDefinition("reply.investment.stock_not_found", "未找到股票提示", "股票代码或名称没有匹配结果时返回。", "未找到对应标的，请检查股票代码或改用标准股票代码。"),
    ReplyTextDefinition("reply.investment.stock_ambiguous", "股票名称重复提示", "股票名称匹配多个标的时返回。", "股票名称匹配到多个标的，请改用股票代码。"),
    ReplyTextDefinition("reply.investment.technical_analysis_failed", "技术分析失败提示", "技术分析生成失败时返回。", "分析生成失败，请稍后重试或联系服务人员。"),
    ReplyTextDefinition("reply.investment.image_generation_failed", "图片生成失败提示", "图片生成或上传失败时返回。", "图片生成失败，请稍后重试或联系服务人员。"),
    ReplyTextDefinition("reply.investment.no_content", "当日内容未更新提示", "利率、转债等当日内容未准备好时返回。", "今日内容尚未更新，请稍后再试。"),
    ReplyTextDefinition("reply.investment.system_error", "系统繁忙提示", "系统异常兜底提示。", "系统暂时繁忙，请稍后重试。"),
]

WECHATMP_REPLY_DEFINITIONS = [
    ReplyTextDefinition("reply.wechatmp.immediate_ack", "收到请求提示", "非技术分析投资指令开始处理时返回。", "收到，正在运行，请稍候。"),
    ReplyTextDefinition("reply.wechatmp.technical_ack", "技术分析开始生成提示", "技术分析未命中缓存、开始后台生成时返回。保留 `{}`，系统会替换为股票或标题。", "已收到，正在运行「{}」技术分析，生成过程大概30s。\n生成完成后回复 1 获取技术分析主图、技术指标表。", ("target",)),
    ReplyTextDefinition("reply.wechatmp.technical_cache_hit", "技术分析缓存命中提示", "技术分析命中缓存时返回。保留 `{}`，系统会替换为股票或标题。", "已命中「{}」技术分析缓存，正在直接交付。\n回复 1 获取技术分析主图、技术指标表。", ("target",)),
    ReplyTextDefinition("reply.wechatmp.cancel_pending_result", "放弃待领取结果提示", "客户回复 0 放弃待领取结果时返回。", "已放弃本次技术分析结果。"),
    ReplyTextDefinition("reply.wechatmp.running_technical_analysis", "技术分析仍在运行提示", "客户在技术分析仍运行时回复 1。保留 `{}`，系统会替换为股票或标题。", "「{}」技术分析仍在运行中，请稍后再回复 1 尝试获取。", ("target",)),
    ReplyTextDefinition("reply.wechatmp.pending_technical_analysis", "技术分析待领取提示", "客户有技术分析结果待领取又输入新内容时返回。保留 `{}`，系统会替换为股票或标题。", "「{}」技术分析已生成完成，回复 1 获取技术分析主图、技术指标表；回复 0 放弃并继续处理新指令。", ("target",)),
    ReplyTextDefinition("reply.wechatmp.thinking_timeout", "微信重试超时提示", "微信第三次请求时后台仍未完成时返回。", "【正在思考中，回复任意文字尝试获取回复】"),
    ReplyTextDefinition("reply.wechatmp.unmatched", "投资指令无法识别提示", "投资路由无法识别输入时返回。", "请输入以下格式之一："),
    ReplyTextDefinition("reply.wechatmp.chat_prefix_hint", "聊天前缀提示", "系统设置聊天前缀时，引导客户按前缀输入。保留 `{}`，系统会替换为前缀。", "请输入'{}'接你想说的话跟我说话。\n例如:\n{}你好，很高兴见到你。", ("prefix", "prefix")),
    ReplyTextDefinition("reply.wechatmp.default_chat_hint", "普通聊天引导提示", "没有聊天前缀时的默认聊天引导。", "你好，很高兴见到你。\n请跟我说话吧。"),
    ReplyTextDefinition("reply.wechatmp.unknown_error", "公众号未知错误提示", "公众号链路兜底错误提示。", "未知错误，请稍后再试"),
]

REPLY_TEXT_GROUPS = [
    {"title": "投资业务错误提示", "keys": [item.key for item in INVESTMENT_REPLY_DEFINITIONS]},
    {"title": "公众号处理状态", "keys": [item.key for item in WECHATMP_REPLY_DEFINITIONS]},
]

REPLY_TEXT_DEFINITIONS = {
    item.key: item
    for item in [*INVESTMENT_REPLY_DEFINITIONS, *WECHATMP_REPLY_DEFINITIONS]
}


def reply_config_fallback_keys() -> dict[str, str]:
    return {key: key for key in REPLY_TEXT_DEFINITIONS}


def default_reply_text(key: str, default: str = "") -> str:
    definition = REPLY_TEXT_DEFINITIONS.get(key)
    return definition.default if definition else default


def get_reply_text(key: str, default: str = "") -> str:
    from .config_service import get_config

    configured = get_config(key, None)
    if configured is None or str(configured) == "":
        return default_reply_text(key, default)
    return str(configured)


def format_reply_text(key: str, *args: Any, default: str = "") -> str:
    text = get_reply_text(key, default)
    if not args:
        return text
    try:
        return text.format(*args)
    except Exception:
        return default_reply_text(key, default).format(*args)


def reply_text_config_metadata() -> dict[str, Any]:
    return {
        "groups": REPLY_TEXT_GROUPS,
        "definitions": {
            key: {
                "label": definition.label,
                "description": definition.description,
                "default": definition.default,
                "placeholders": list(definition.placeholders),
            }
            for key, definition in REPLY_TEXT_DEFINITIONS.items()
        },
    }
```

- [ ] **Step 4: Wire `constants.user_message()` to reply config**

Modify `business/investment/constants.py`:

```python
USER_MESSAGE_CONFIG_KEYS = {
    ErrorCode.UNAUTHORIZED: "reply.investment.unauthorized",
    ErrorCode.USER_DISABLED: "reply.investment.user_disabled",
    ErrorCode.AUTH_EXPIRED: "reply.investment.auth_expired",
    ErrorCode.INPUT_ERROR: "reply.investment.input_error",
    ErrorCode.STOCK_NOT_FOUND: "reply.investment.stock_not_found",
    ErrorCode.STOCK_AMBIGUOUS: "reply.investment.stock_ambiguous",
    ErrorCode.TECHNICAL_ANALYSIS_FAILED: "reply.investment.technical_analysis_failed",
    ErrorCode.IMAGE_GENERATION_FAILED: "reply.investment.image_generation_failed",
    ErrorCode.NO_CONTENT: "reply.investment.no_content",
    ErrorCode.SYSTEM_ERROR: "reply.investment.system_error",
}


def user_message(error_code: ErrorCode) -> str:
    default = USER_MESSAGES.get(error_code, USER_MESSAGES[ErrorCode.SYSTEM_ERROR])
    key = USER_MESSAGE_CONFIG_KEYS.get(error_code, USER_MESSAGE_CONFIG_KEYS[ErrorCode.SYSTEM_ERROR])
    try:
        from .reply_config import get_reply_text

        return get_reply_text(key, default)
    except Exception:
        return default
```

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```powershell
py -m pytest tests\test_investment_business.py -k "user_message_uses_reply_config or user_message_can_be_overridden" -q
```

Expected: both tests pass.

- [ ] **Step 6: Commit**

```powershell
git add business\investment\reply_config.py business\investment\constants.py tests\test_investment_business.py
git commit -m "feat(investment): configure user-facing reply messages"
```

---

### Task 2: WeChatMP Passive Reply Text Lookup

**Files:**
- Modify: `channel/wechatmp/passive_reply.py`
- Test: `tests/test_wechatmp_investment_reply.py`

- [ ] **Step 1: Write failing tests for configurable WeChatMP replies**

Add tests near existing passive technical analysis ack tests in `tests/test_wechatmp_investment_reply.py`:

```python
def test_wechatmp_passive_technical_ack_uses_configured_reply_text(investment_env, monkeypatch):
    from business.investment.config_service import save_config
    from channel.wechatmp import passive_reply

    save_config("reply.wechatmp.technical_ack", "配置提示：{} 生成中，回复1。", operator_role="admin")
    monkeypatch.setattr(passive_reply, "_technical_analysis_cache_hit", lambda _content: False, raising=False)

    assert passive_reply._investment_ack_text("天娱数科 技术分析") == "配置提示：天娱数科 生成中，回复1。"


def test_wechatmp_passive_cache_hit_uses_configured_reply_text(investment_env, monkeypatch):
    from business.investment.config_service import save_config
    from channel.wechatmp import passive_reply

    save_config("reply.wechatmp.technical_cache_hit", "缓存好了：{}，回复1取图。", operator_role="admin")
    monkeypatch.setattr(passive_reply, "_technical_analysis_cache_hit", lambda _content: True, raising=False)

    assert passive_reply._investment_ack_text("天娱数科 技术分析") == "缓存好了：天娱数科，回复1取图。"


def test_wechatmp_passive_pending_and_running_prompts_use_configured_reply_text(investment_env):
    from business.investment.config_service import save_config
    from channel.wechatmp import passive_reply

    save_config("reply.wechatmp.running_technical_analysis", "{} 还在跑。", operator_role="admin")
    save_config("reply.wechatmp.pending_technical_analysis", "{} 已完成，回1取，回0弃。", operator_role="admin")

    assert passive_reply._running_technical_analysis_text("农业银行") == "农业银行 还在跑。"
    assert passive_reply._pending_result_prompt("农业银行 技术分析") == "农业银行 已完成，回1取，回0弃。"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
py -m pytest tests\test_wechatmp_investment_reply.py -k "configured_reply_text or pending_and_running_prompts" -q
```

Expected: fail because `passive_reply.py` still uses hard-coded constants and `_running_technical_analysis_text()` does not exist.

- [ ] **Step 3: Add small helper functions in `passive_reply.py`**

Replace top-level reply text constants with key constants and helper functions:

```python
IMMEDIATE_ACK_KEY = "reply.wechatmp.immediate_ack"
PASSIVE_TECHNICAL_ACK_KEY = "reply.wechatmp.technical_ack"
PASSIVE_TECHNICAL_CACHE_HIT_KEY = "reply.wechatmp.technical_cache_hit"
CANCEL_PENDING_RESULT_KEY = "reply.wechatmp.cancel_pending_result"
RUNNING_TECHNICAL_ANALYSIS_KEY = "reply.wechatmp.running_technical_analysis"
PENDING_TECHNICAL_ANALYSIS_KEY = "reply.wechatmp.pending_technical_analysis"
THINKING_TIMEOUT_KEY = "reply.wechatmp.thinking_timeout"
UNMATCHED_KEY = "reply.wechatmp.unmatched"
CHAT_PREFIX_HINT_KEY = "reply.wechatmp.chat_prefix_hint"
DEFAULT_CHAT_HINT_KEY = "reply.wechatmp.default_chat_hint"
UNKNOWN_ERROR_KEY = "reply.wechatmp.unknown_error"
```

Add below `_technical_analysis_cache_hit()`:

```python
def _reply_text(key: str, default: str = "") -> str:
    try:
        from business.investment.reply_config import get_reply_text

        return get_reply_text(key, default)
    except Exception:
        return default


def _reply_format(key: str, *args, default: str = "") -> str:
    try:
        from business.investment.reply_config import format_reply_text

        return format_reply_text(key, *args, default=default)
    except Exception:
        return default.format(*args) if args else default


def _running_technical_analysis_text(title: str) -> str:
    return _reply_format(RUNNING_TECHNICAL_ANALYSIS_KEY, title, default="「{}」技术分析仍在运行中，请稍后再回复 1 尝试获取。")
```

- [ ] **Step 4: Replace call sites with helpers**

Use these exact replacements:

```python
return _reply_format(PASSIVE_TECHNICAL_CACHE_HIT_KEY, _technical_analysis_target(content), default="已命中「{}」技术分析缓存，正在直接交付。\n回复 1 获取技术分析主图、技术指标表。")
return _reply_format(PASSIVE_TECHNICAL_ACK_KEY, _technical_analysis_target(content), default="已收到，正在运行「{}」技术分析，生成过程大概30s。\n生成完成后回复 1 获取技术分析主图、技术指标表。")
return _reply_text(IMMEDIATE_ACK_KEY, "收到，正在运行，请稍候。")
return _reply_format(PENDING_TECHNICAL_ANALYSIS_KEY, _technical_analysis_target(title or ""), default="「{}」技术分析已生成完成，回复 1 获取技术分析主图、技术指标表；回复 0 放弃并继续处理新指令。")
replyPost = create_reply(_running_technical_analysis_text(technical_title), msg)
replyPost = create_reply(_reply_text(CANCEL_PENDING_RESULT_KEY, "已放弃本次技术分析结果。"), msg)
reply_text = _reply_text(THINKING_TIMEOUT_KEY, "【正在思考中，回复任意文字尝试获取回复】")
return _reply_text(UNMATCHED_KEY, "请输入以下格式之一：")
reply_text = _reply_format(CHAT_PREFIX_HINT_KEY, trigger_prefix, trigger_prefix, default="请输入'{}'接你想说的话跟我说话。\n例如:\n{}你好，很高兴见到你。")
reply_text = _reply_text(DEFAULT_CHAT_HINT_KEY, "你好，很高兴见到你。\n请跟我说话吧。")
reply_text = _reply_text(UNKNOWN_ERROR_KEY, "未知错误，请稍后再试")
```

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```powershell
py -m pytest tests\test_wechatmp_investment_reply.py -k "configured_reply_text or pending_and_running_prompts or cached_technical_analysis_hit or technical_analysis_ack_uses_route_target or cache_miss_returns_running_ack" -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```powershell
git add channel\wechatmp\passive_reply.py tests\test_wechatmp_investment_reply.py
git commit -m "feat(wechatmp): load passive reply text from config"
```

---

### Task 3: Config API Exposes Reply Text Metadata

**Files:**
- Modify: `business/investment/config_service.py`
- Modify: `channel/web/web_channel.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing API tests**

Add near existing `InvestmentConfigHandler` tests:

```python
def test_web_investment_config_returns_reply_text_metadata(investment_env, monkeypatch):
    from channel.web.web_channel import InvestmentConfigHandler

    payload = _call_investment_json_handler(monkeypatch, InvestmentConfigHandler().GET)

    assert payload["status"] == "success"
    assert "reply_texts" in payload
    assert any(group["title"] == "公众号处理状态" for group in payload["reply_texts"]["groups"])
    assert payload["reply_texts"]["definitions"]["reply.wechatmp.technical_ack"]["label"] == "技术分析开始生成提示"
    assert "reply.wechatmp.technical_ack" in payload["configs"]
    assert payload["configs"]["reply.wechatmp.technical_ack"].startswith("已收到，正在运行")


def test_web_investment_config_saves_reply_text_values(investment_env, monkeypatch):
    from business.investment.config_service import get_config
    from channel.web.web_channel import InvestmentConfigHandler

    body = {"configs": {"reply.wechatmp.immediate_ack": "已收到，请稍候。"}}
    payload = _call_investment_json_handler(monkeypatch, InvestmentConfigHandler().POST, body=body)

    assert payload["status"] == "success"
    assert get_config("reply.wechatmp.immediate_ack") == "已收到，请稍候。"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
py -m pytest tests\test_investment_business.py -k "reply_text_metadata or saves_reply_text_values" -q
```

Expected: fail because `reply_texts` is not returned and reply keys are not in `CONFIG_FALLBACK_KEYS`.

- [ ] **Step 3: Add reply fallback keys**

Modify `business/investment/config_service.py` after `CONFIG_FALLBACK_KEYS` is defined:

```python
try:
    from .reply_config import reply_config_fallback_keys

    CONFIG_FALLBACK_KEYS.update(reply_config_fallback_keys())
except Exception:
    pass
```

- [ ] **Step 4: Return metadata from config handler**

Modify `InvestmentConfigHandler.GET` in `channel/web/web_channel.py`:

```python
from business.investment.config_service import CONFIG_FALLBACK_KEYS, get_configs
from business.investment.reply_config import reply_text_config_metadata

return _investment_json_response({
    "status": "success",
    "configs": get_configs(list(CONFIG_FALLBACK_KEYS.keys()), masked=True),
    "reply_texts": reply_text_config_metadata(),
})
```

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```powershell
py -m pytest tests\test_investment_business.py -k "reply_text_metadata or saves_reply_text_values or investment_config" -q
```

Expected: selected config tests pass.

- [ ] **Step 6: Commit**

```powershell
git add business\investment\config_service.py channel\web\web_channel.py tests\test_investment_business.py
git commit -m "feat(investment): expose reply text config metadata"
```

---

### Task 4: System Configuration Page UI

**Files:**
- Modify: `channel/web/static/js/console.js`
- Modify: `channel/web/static/css/console.css`
- Test: `tests/test_investment_web_ui.py`

- [ ] **Step 1: Write failing UI tests**

Add tests in `tests/test_investment_web_ui.py`:

```python
def test_investment_config_page_renders_reply_text_section():
    js = CONSOLE_JS.read_text(encoding="utf-8")

    assert "renderInvestmentReplyConfigGroups(" in js
    assert "reply_texts" in js
    assert "公众号回复词" in js
    assert "投资业务错误提示" in js
    assert "公众号处理状态" in js
    assert "reply.wechatmp.technical_ack" in js
    assert "reply.investment.unauthorized" in js


def test_investment_reply_config_fields_show_descriptions_and_use_textareas():
    js = CONSOLE_JS.read_text(encoding="utf-8")
    css = CONSOLE_CSS.read_text(encoding="utf-8")

    assert "function renderInvestmentReplyConfigField(" in js
    assert "investment-config-description" in js
    assert "renderInvestmentConfigField(key, label, 'textarea'" in js
    assert ".investment-config-description" in css
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
py -m pytest tests\test_investment_web_ui.py -k "reply_config" -q
```

Expected: fail because reply UI functions and CSS do not exist.

- [ ] **Step 3: Render reply config groups from API metadata**

Modify `renderInvestmentConfig()` in `channel/web/static/js/console.js`:

```javascript
const replyTextGroups = canReadConfig ? renderInvestmentReplyConfigGroups(data.reply_texts || {}, configs) : '';
```

Include `${replyTextGroups}` after `${groups}` in the page body.

Add functions after `renderInvestmentConfigGroup()`:

```javascript
function renderInvestmentReplyConfigGroups(replyTexts, configs) {
    const groups = replyTexts.groups || [];
    const definitions = replyTexts.definitions || {};
    if (!groups.length) return '';
    const renderedGroups = groups.map(group => `
        <section class="investment-panel investment-workbench-full">
            <div class="investment-panel-title"><i class="fas fa-message"></i><span>${escapeHtml(group.title || '公众号回复词')}</span></div>
            <div class="investment-grid cols-1">
                ${(group.keys || []).map(key => renderInvestmentReplyConfigField(key, definitions[key] || {}, configs[key])).join('')}
            </div>
        </section>`).join('');
    return `
        <section class="investment-panel investment-workbench-full">
            <div class="investment-panel-heading">
                <div>
                    <div class="investment-panel-title"><i class="fas fa-comments"></i><span>公众号回复词</span></div>
                    <div class="investment-subtitle">这些文案会直接展示给公众号客户。带 {} 的文案请保留占位符，系统会自动替换股票或状态名称。</div>
                </div>
            </div>
        </section>
        ${renderedGroups}`;
}

function renderInvestmentReplyConfigField(key, definition, value = '') {
    const label = definition.label || key;
    const description = definition.description || '';
    return `
        <div>
            ${renderInvestmentConfigField(key, label, 'textarea', value)}
            ${description ? `<div class="investment-config-description">${escapeHtml(description)}</div>` : ''}
        </div>`;
}
```

- [ ] **Step 4: Add description CSS**

Add to `channel/web/static/css/console.css` near config field styles:

```css
.investment-config-description {
    margin: -6px 0 10px;
    color: #64748b;
    font-size: 12px;
    line-height: 1.5;
}
.dark .investment-config-description {
    color: #94a3b8;
}
```

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```powershell
py -m pytest tests\test_investment_web_ui.py -k "reply_config or config_page" -q
```

Expected: selected UI tests pass.

- [ ] **Step 6: Commit**

```powershell
git add channel\web\static\js\console.js channel\web\static\css\console.css tests\test_investment_web_ui.py
git commit -m "feat(investment): add reply text editor to config page"
```

---

### Task 5: Final Regression And Integration

**Files:**
- Verify only; no expected production file edits.

- [ ] **Step 1: Run backend reply/config tests**

Run:

```powershell
py -m pytest tests\test_investment_business.py -k "reply_text or user_message or investment_config" -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run WeChatMP passive reply tests**

Run:

```powershell
py -m pytest tests\test_wechatmp_investment_reply.py -k "configured_reply_text or pending_and_running_prompts or technical_analysis or cached_technical_analysis_hit or permission" -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run UI tests**

Run:

```powershell
py -m pytest tests\test_investment_web_ui.py -q
```

Expected: full UI static test file passes.

- [ ] **Step 4: Inspect git diff**

Run:

```powershell
git status --short
git diff --stat
git diff -- business/investment/constants.py channel/wechatmp/passive_reply.py business/investment/reply_config.py channel/web/static/js/console.js channel/web/web_channel.py
```

Expected: only reply config, config API/UI, and tests are changed; existing unrelated dirty files remain untouched unless they were already modified before this plan.

- [ ] **Step 5: Commit any final fixes**

If final regression required small fixes, commit them:

```powershell
git add business\investment\reply_config.py business\investment\constants.py business\investment\config_service.py channel\wechatmp\passive_reply.py channel\web\web_channel.py channel\web\static\js\console.js channel\web\static\css\console.css tests\test_investment_business.py tests\test_wechatmp_investment_reply.py tests\test_investment_web_ui.py
git commit -m "fix(investment): finalize reply text configuration"
```

If no final fixes were needed, do not create an empty commit.

---

## Self-Review

- Spec coverage: The plan covers database-backed reply text defaults, `constants.py`, `passive_reply.py`, config API metadata, system configuration page UI, and targeted regressions.
- Placeholder scan: The plan contains concrete keys, function names, commands, and expected outcomes. It intentionally does not include open-ended implementation placeholders.
- Type consistency: Reply keys use `reply.investment.*` and `reply.wechatmp.*` consistently across backend, API, UI, and tests. The UI receives `reply_texts.groups` and `reply_texts.definitions` from the backend.
