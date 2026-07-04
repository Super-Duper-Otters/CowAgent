# Web Chat WeChatMP Chain Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit Web chat switch that lets an admin send Web dialog messages through the WeChat Official Account passive-reply chain, so Web can verify both shared business routing and WeChatMP-side pending/retry/claim behavior.

**Architecture:** Keep normal Web chat unchanged by default. Add a simulator adapter that builds a signed plaintext WeChatMP XML text message, calls the same passive-reply handler used by `/wx`, normalizes the XML/text response into a Web-visible reply, and optionally stubs media upload for Web verification to avoid accidental calls to real WeChat media APIs. The Web message endpoint chooses the simulator only when the request body asks for WeChatMP chain mode and the admin config allows it.

**Tech Stack:** Python `web.py`, `wechatpy`, existing `bridge.reply`, existing `channel.web.web_channel` SSE queues, existing `channel.wechatmp.passive_reply`, vanilla JS in `channel/web/static/js/console.js`, pytest.

---

## File Structure

- Create `channel/wechatmp/simulator.py`
  - Owns Web-to-WeChatMP simulation only.
  - Builds signed WeChat XML text messages.
  - Calls the reusable passive handler.
  - Converts WeChat XML replies such as text/image/voice/video into Web-safe text.
  - Uses stable fake openid/message id values derived from the Web session.

- Modify `channel/wechatmp/passive_reply.py`
  - Extract `handle_wechatmp_post(args, body, env=None)` from `Query.POST`.
  - Keep `Query.POST` as the real HTTP wrapper.
  - Add a narrow media-upload simulation hook so Web-chain verification can avoid real WeChat media upload calls.

- Modify `channel/web/web_channel.py`
  - Add `router.enable_web_wechatmp_chain_verification` config guard.
  - Read `wechatmp_chain` from `/message` JSON.
  - If enabled and requested, synchronously call the simulator and push the normalized response into the existing SSE/poll response path.

- Modify `business/config/config_service.py`, `config.py`, `config-template.json`
  - Add default config key `router.enable_web_wechatmp_chain_verification` mapped to a JSON fallback key.

- Modify `channel/web/static/js/console.js`
  - Add a local Web chat toggle labelled `公众号链路验证`.
  - Persist the toggle in `localStorage`.
  - Send `wechatmp_chain: true` with `/message` only when enabled.

- Test in `tests/test_business.py`
  - Cover passive handler extraction.
  - Cover simulator return for `000133技术分析`.
  - Cover `/message` branch when the Web toggle body flag is on.
  - Cover config guard off.

---

### Task 1: Extract A Reusable Passive Reply Handler

**Files:**
- Modify: `channel/wechatmp/passive_reply.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Write the failing passive-handler extraction test**

Add this test near the existing routing/technical-analysis tests in `tests/test_business.py`:

```python
def test_wechatmp_passive_handler_accepts_injected_request(monkeypatch):
    import hashlib
    import time
    from types import SimpleNamespace
    from xml.etree import ElementTree as ET

    from channel.wechatmp.passive_reply import handle_wechatmp_post

    monkeypatch.setitem(conf(), "wechatmp_token", "test-token")

    timestamp = str(int(time.time()))
    nonce = "nonce-1"
    signature = hashlib.sha1("".join(sorted(["test-token", timestamp, nonce])).encode("utf-8")).hexdigest()
    args = {
        "signature": signature,
        "timestamp": timestamp,
        "nonce": nonce,
    }
    body = b"""<xml>
<ToUserName><![CDATA[gh_test]]></ToUserName>
<FromUserName><![CDATA[openid-web-test]]></FromUserName>
<CreateTime>1</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[not-a-business-command]]></Content>
<MsgId>10001</MsgId>
</xml>"""

    monkeypatch.setattr(
        "channel.wechatmp.passive_reply.WechatMPChannel",
        lambda: SimpleNamespace(
            cache_dict={},
            running=set(),
            technical_analysis_titles={},
            running_started_at={},
            request_cnt={},
            crypto=None,
            client=SimpleNamespace(),
        ),
    )

    result = handle_wechatmp_post(args, body, env={"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "1"})

    root = ET.fromstring(result)
    assert root.findtext("MsgType") == "text"
    assert root.findtext("Content")
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
py -m pytest tests/test_business.py::test_wechatmp_passive_handler_accepts_injected_request -q
```

Expected: fails with `ImportError` or `AttributeError` because `handle_wechatmp_post` does not exist.

- [ ] **Step 3: Extract the handler**

In `channel/wechatmp/passive_reply.py`, replace the body of `Query.POST` with a wrapper and move the current logic into `handle_wechatmp_post`:

```python
def handle_wechatmp_post(args, message: bytes, env=None):
    env = env or {}
    try:
        request_time = time.time()
        channel = WechatMPChannel()
        _cleanup_expired(channel.cache_dict)
        encrypt_func = lambda x: x
        if is_encrypted_message(args):
            logger.debug("[wechatmp] Receive encrypted post data:\n" + message.decode("utf-8"))
            message = decrypt_message_if_needed(args, message, channel.crypto)
            encrypt_func = lambda x: channel.crypto.encrypt_message(x, args.nonce, args.timestamp)
        else:
            message = decrypt_message_if_needed(args, message, channel.crypto)
            logger.debug("[wechatmp] Receive post data:\n" + message.decode("utf-8"))

        # Keep the existing Query.POST logic from `msg = parse_message(message)` through
        # the final `return "success"` here. Replace the log-only access to `web.ctx.env`
        # with the injected `env` mapping:
        # env.get("REMOTE_ADDR"), env.get("REMOTE_PORT")
    except Exception as exc:
        logger.exception(exc)
        return _system_error_text()


class Query:
    def GET(self):
        return verify_server(web.input())

    def POST(self):
        return handle_wechatmp_post(web.input(), web.data(), env=getattr(web.ctx, "env", {}) or {})
```

When moving the existing block, replace this expression:

```python
web.ctx.env.get("REMOTE_ADDR"), web.ctx.env.get("REMOTE_PORT")
```

with:

```python
env.get("REMOTE_ADDR"), env.get("REMOTE_PORT")
```

- [ ] **Step 4: Run the extraction test**

Run:

```powershell
py -m pytest tests/test_business.py::test_wechatmp_passive_handler_accepts_injected_request -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```powershell
git add channel/wechatmp/passive_reply.py tests/test_business.py
git commit -m "refactor: expose reusable wechatmp passive handler"
```

---

### Task 2: Add The WeChatMP Web Simulator

**Files:**
- Create: `channel/wechatmp/simulator.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Write the failing simulator test**

Add this test:

```python
def test_wechatmp_web_simulator_returns_bare_code_index_suggestion(monkeypatch):
    from channel.wechatmp.simulator import simulate_wechatmp_text_message

    monkeypatch.setitem(conf(), "wechatmp_token", "test-token")

    from business.content.stock_resolver import StockSymbolMatch

    monkeypatch.setattr(
        "business.content.technical_analysis.list_stock_symbol_matches",
        lambda value, limit=5: [],
    )
    monkeypatch.setattr(
        "business.content.technical_analysis.list_index_symbol_matches_for_bare_code",
        lambda value, limit=3: [
            StockSymbolMatch(
                query="000133",
                code="sh000133",
                ts_code="000133.SH",
                name="上证指数样例",
                exchange="SH",
                asset_type="index",
                source="test",
                confidence=100,
            )
        ],
    )

    result = simulate_wechatmp_text_message(
        session_id="web-session-1",
        content="000133技术分析",
        request_id="request-1",
    )

    assert result.reply_type == "text"
    assert "请发送：sh000133 技术分析" in result.content
    assert result.raw_reply
```

- [ ] **Step 2: Run the simulator test to verify it fails**

Run:

```powershell
py -m pytest tests/test_business.py::test_wechatmp_web_simulator_returns_bare_code_index_suggestion -q
```

Expected: fails because `channel.wechatmp.simulator` does not exist.

- [ ] **Step 3: Create `channel/wechatmp/simulator.py`**

Create the file with this implementation:

```python
import hashlib
import time
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from common.log import logger
from config import conf


@dataclass(frozen=True)
class WeChatMPSimulationResult:
    reply_type: str
    content: str
    raw_reply: str


def _sha1_signature(token: str, timestamp: str, nonce: str) -> str:
    return hashlib.sha1("".join(sorted([token, timestamp, nonce])).encode("utf-8")).hexdigest()


def _stable_openid(session_id: str) -> str:
    digest = hashlib.sha1(str(session_id or "web").encode("utf-8")).hexdigest()[:24]
    return f"webmp_{digest}"


def _stable_msg_id(request_id: str) -> str:
    digits = "".join(ch for ch in hashlib.sha1(str(request_id or time.time()).encode("utf-8")).hexdigest() if ch.isdigit())
    return (digits + "0" * 16)[:16]


def _text_xml(openid: str, content: str, msg_id: str) -> bytes:
    escaped_content = content.replace("]]>", "]]]]><![CDATA[>")
    return f"""<xml>
<ToUserName><![CDATA[gh_web_verify]]></ToUserName>
<FromUserName><![CDATA[{openid}]]></FromUserName>
<CreateTime>{int(time.time())}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[{escaped_content}]]></Content>
<MsgId>{msg_id}</MsgId>
</xml>""".encode("utf-8")


def _parse_reply(raw_reply: str) -> tuple[str, str]:
    if raw_reply == "success":
        return "success", "success"
    root = ET.fromstring(raw_reply)
    reply_type = root.findtext("MsgType") or "text"
    if reply_type == "text":
        return reply_type, root.findtext("Content") or ""
    if reply_type in {"image", "voice", "video"}:
        media_id = root.findtext(".//MediaId") or ""
        return reply_type, f"[公众号{reply_type}回复] media_id={media_id}"
    return reply_type, raw_reply


def simulate_wechatmp_text_message(session_id: str, content: str, request_id: str = "") -> WeChatMPSimulationResult:
    from channel.wechatmp.passive_reply import handle_wechatmp_post

    token = str(conf().get("wechatmp_token") or "")
    if not token:
        raise RuntimeError("wechatmp_token is required for WeChatMP chain verification")

    timestamp = str(int(time.time()))
    nonce = "web-verify"
    args = {
        "signature": _sha1_signature(token, timestamp, nonce),
        "timestamp": timestamp,
        "nonce": nonce,
    }
    body = _text_xml(_stable_openid(session_id), content, _stable_msg_id(request_id))
    raw_reply = handle_wechatmp_post(args, body, env={"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "web"})
    raw_reply = raw_reply.decode("utf-8") if isinstance(raw_reply, bytes) else str(raw_reply)
    try:
        reply_type, parsed_content = _parse_reply(raw_reply)
    except Exception as exc:
        logger.warning("[wechatmp-web-sim] failed to parse reply: {}".format(exc))
        reply_type, parsed_content = "text", raw_reply
    return WeChatMPSimulationResult(reply_type=reply_type, content=parsed_content, raw_reply=raw_reply)
```

- [ ] **Step 4: Run the simulator test**

Run:

```powershell
py -m pytest tests/test_business.py::test_wechatmp_web_simulator_returns_bare_code_index_suggestion -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```powershell
git add channel/wechatmp/simulator.py tests/test_business.py
git commit -m "feat: add wechatmp web simulator"
```

---

### Task 3: Wire The Web Message Endpoint To The Simulator

**Files:**
- Modify: `config.py`
- Modify: `config-template.json`
- Modify: `business/config/config_service.py`
- Modify: `channel/web/web_channel.py`
- Test: `tests/test_business.py`

- [ ] **Step 1: Write failing Web endpoint tests**

Add these tests:

```python
def test_web_message_uses_wechatmp_chain_when_enabled(monkeypatch):
    import json
    import web
    from channel.web.web_channel import WebChannel

    monkeypatch.setitem(conf(), "investment_web_wechatmp_chain_verification", True)
    monkeypatch.setattr("channel.web.web_channel._require_console_auth", lambda: None)
    monkeypatch.setattr(
        "channel.web.web_channel.web.data",
        lambda: json.dumps({
            "session_id": "web-session-1",
            "message": "000133技术分析",
            "stream": True,
            "wechatmp_chain": True,
        }).encode("utf-8"),
    )

    calls = []
    monkeypatch.setattr(
        "channel.wechatmp.simulator.simulate_wechatmp_text_message",
        lambda session_id, content, request_id="": calls.append((session_id, content, request_id)) or type(
            "R",
            (),
            {"reply_type": "text", "content": "请发送：sh000133 技术分析", "raw_reply": "<xml/>"},
        )(),
    )

    channel = WebChannel()
    response = json.loads(channel.post_message())

    assert response["status"] == "success"
    assert response["stream"] is True
    assert calls and calls[0][0] == "web-session-1"
    queued = channel.sse_queues[response["request_id"]].get_nowait()
    assert queued["type"] == "done"
    assert "sh000133" in queued["content"]


def test_web_message_rejects_wechatmp_chain_when_disabled(monkeypatch):
    import json
    from channel.web.web_channel import WebChannel

    monkeypatch.setitem(conf(), "investment_web_wechatmp_chain_verification", False)
    monkeypatch.setattr("channel.web.web_channel._require_console_auth", lambda: None)
    monkeypatch.setattr(
        "channel.web.web_channel.web.data",
        lambda: json.dumps({
            "session_id": "web-session-1",
            "message": "000133技术分析",
            "stream": True,
            "wechatmp_chain": True,
        }).encode("utf-8"),
    )

    channel = WebChannel()
    response = json.loads(channel.post_message())

    assert response["status"] == "error"
    assert "公众号链路验证未开启" in response["message"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
py -m pytest tests/test_business.py::test_web_message_uses_wechatmp_chain_when_enabled tests/test_business.py::test_web_message_rejects_wechatmp_chain_when_disabled -q
```

Expected: first test fails because `wechatmp_chain` is ignored; second fails because no guard exists.

- [ ] **Step 3: Add config defaults**

In `config.py`, add:

```python
"investment_web_wechatmp_chain_verification": False,
```

In `config-template.json`, add:

```json
"investment_web_wechatmp_chain_verification": false,
```

In `business/config/config_service.py`, add this fallback mapping:

```python
"router.enable_web_wechatmp_chain_verification": "investment_web_wechatmp_chain_verification",
```

- [ ] **Step 4: Add the Web branch**

In `channel/web/web_channel.py`, inside `WebChannel.post_message()` after `request_id`, queue creation, and before prefix/context composition, add:

```python
            wechatmp_chain = bool(json_data.get("wechatmp_chain", False))
            if wechatmp_chain:
                from business.config.config_service import get_config

                if not get_config("router.enable_web_wechatmp_chain_verification", False):
                    if request_id in self.sse_queues:
                        del self.sse_queues[request_id]
                    return json.dumps({"status": "error", "message": "公众号链路验证未开启"}, ensure_ascii=False)

                from channel.wechatmp.simulator import simulate_wechatmp_text_message

                simulated = simulate_wechatmp_text_message(session_id, prompt, request_id=request_id)
                reply = Reply(ReplyType.TEXT, simulated.content)
                _persist_web_visible_turn(session_id, prompt, reply)
                if use_sse:
                    self.sse_queues[request_id].put({
                        "type": "done",
                        "content": simulated.content,
                        "request_id": request_id,
                        "timestamp": time.time(),
                    })
                else:
                    self.session_queues[session_id].put({
                        "request_id": request_id,
                        "response": simulated.content,
                        "timestamp": time.time(),
                    })
                return json.dumps({"status": "success", "request_id": request_id, "stream": use_sse}, ensure_ascii=False)
```

- [ ] **Step 5: Run the Web endpoint tests**

Run:

```powershell
py -m pytest tests/test_business.py::test_web_message_uses_wechatmp_chain_when_enabled tests/test_business.py::test_web_message_rejects_wechatmp_chain_when_disabled -q
```

Expected: `2 passed`.

- [ ] **Step 6: Commit**

```powershell
git add config.py config-template.json business/config/config_service.py channel/web/web_channel.py tests/test_business.py
git commit -m "feat: route web chat through wechatmp verification chain"
```

---

### Task 4: Add The Web Chat Toggle

**Files:**
- Modify: `channel/web/static/js/console.js`
- Test: `channel/web/static/js/console.js` syntax check

- [ ] **Step 1: Add frontend state**

Near the other chat/session constants in `channel/web/static/js/console.js`, add:

```javascript
const WECHATMP_CHAIN_KEY = 'cow_web_chat_wechatmp_chain';
let webChatWechatmpChain = localStorage.getItem(WECHATMP_CHAIN_KEY) === '1';
```

- [ ] **Step 2: Render the toggle**

Add a compact toggle button in the chat header toolbar creation area. If the toolbar is static HTML and only wired by JS, inject it after the chat input controls initialize:

```javascript
function renderWechatmpChainToggle() {
    const sendBtn = document.getElementById('send-btn');
    if (!sendBtn || document.getElementById('wechatmp-chain-toggle')) return;
    const wrapper = document.createElement('label');
    wrapper.className = 'investment-switch text-xs';
    wrapper.innerHTML = `
        <input id="wechatmp-chain-toggle" type="checkbox"${webChatWechatmpChain ? ' checked' : ''}>
        <span class="investment-switch-track" aria-hidden="true"><span class="investment-switch-thumb"></span></span>
        <span class="investment-switch-label">公众号链路验证</span>
    `;
    wrapper.querySelector('input').addEventListener('change', (event) => {
        webChatWechatmpChain = event.target.checked === true;
        localStorage.setItem(WECHATMP_CHAIN_KEY, webChatWechatmpChain ? '1' : '0');
    });
    sendBtn.parentElement.insertBefore(wrapper, sendBtn);
}

renderWechatmpChainToggle();
```

- [ ] **Step 3: Send the request flag**

In `sendMessage()`, after creating `body`, add:

```javascript
    if (webChatWechatmpChain) {
        body.wechatmp_chain = true;
    }
```

- [ ] **Step 4: Syntax-check frontend JavaScript**

Run:

```powershell
node --check channel\web\static\js\console.js
```

Expected: no output and exit code `0`.

- [ ] **Step 5: Commit**

```powershell
git add channel/web/static/js/console.js
git commit -m "feat: add web chat wechatmp chain toggle"
```

---

### Task 5: Regression Verification

**Files:**
- Test only

- [ ] **Step 1: Run the targeted pytest set**

Run:

```powershell
py -m pytest tests/test_business.py -k "wechatmp_passive_handler_accepts_injected_request or wechatmp_web_simulator_returns_bare_code_index_suggestion or web_message_uses_wechatmp_chain_when_enabled or web_message_rejects_wechatmp_chain_when_disabled or router_returns_bare_code_index_suggestion_to_chat or router_respects_unknown_bare_code_guard_switch" -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run frontend syntax check**

Run:

```powershell
node --check channel\web\static\js\console.js
```

Expected: no output and exit code `0`.

- [ ] **Step 3: Manual Web verification**

Start the Web server using the project’s normal command, open `/chat`, and verify these cases:

1. Toggle off, send `000133技术分析`: Web uses the normal Web business route and returns the shared business-layer prompt.
2. Toggle on while `router.enable_web_wechatmp_chain_verification=false`, send `000133技术分析`: Web returns `公众号链路验证未开启`.
3. Toggle on while `router.enable_web_wechatmp_chain_verification=true`, send `000133技术分析`: Web returns the WeChatMP passive-chain text containing `请发送：sh000133 技术分析`.
4. Toggle on, send a valid technical-analysis request, then send `1`: Web should exercise the WeChatMP pending-result claim path for the same synthetic openid.

- [ ] **Step 4: Commit verification-only fixes**

If verification exposes a small defect, fix it and commit:

```powershell
git add channel/wechatmp channel/web business/config config.py config-template.json tests/test_business.py
git commit -m "fix: stabilize wechatmp web verification"
```

Do not create this commit if no fix was needed.

---

## Scope Notes

This Web switch validates the公众号 passive-reply business chain: permission precheck, activation-code handling, technical-analysis precheck, running state, pending cache, immediate ack, timeout text, and reply-1 claim behavior.

It does not prove Tencent server signature delivery, encrypted callback transport, real media upload, or real customer-service message delivery. Those still require an actual WeChat Official Account callback test or the existing公众号 health/check scripts.

## Self-Review

- Spec coverage: the plan adds a Web switch, routes selected Web messages through公众号 passive chain, keeps current Web behavior as default, and preserves a config guard.
- Placeholder scan: no task depends on unspecified behavior; each code-changing task includes concrete code snippets and exact commands.
- Type consistency: the simulator returns `WeChatMPSimulationResult(reply_type, content, raw_reply)`, and Web endpoint tests consume those same fields.
