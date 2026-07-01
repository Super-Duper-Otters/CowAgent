import hashlib
import time
from dataclasses import dataclass
from types import SimpleNamespace
from xml.etree import ElementTree as ET

from common.log import logger
from config import conf


@dataclass(frozen=True)
class WeChatMPSimulationResult:
    reply_type: str
    content: str
    raw_reply: str


class _WechatMPArgs(SimpleNamespace):
    def get(self, key, default=None):
        return getattr(self, key, default)


def _sha1_signature(token: str, timestamp: str, nonce: str) -> str:
    return hashlib.sha1("".join(sorted([token, timestamp, nonce])).encode("utf-8")).hexdigest()


def _stable_openid(session_id: str) -> str:
    digest = hashlib.sha1(str(session_id or "web").encode("utf-8")).hexdigest()[:24]
    return f"webmp_{digest}"


def _stable_msg_id(request_id: str) -> str:
    source = str(request_id or "web-request").encode("utf-8")
    digits = "".join(ch for ch in hashlib.sha1(source).hexdigest() if ch.isdigit())
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
        return "success", "公众号链路已返回 success（无即时回复），后台可能仍在处理；请稍后发送 1 验证领取。"

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
    args = _WechatMPArgs(
        signature=_sha1_signature(token, timestamp, nonce),
        timestamp=timestamp,
        nonce=nonce,
    )
    body = _text_xml(_stable_openid(session_id), content, _stable_msg_id(request_id))
    raw_reply = handle_wechatmp_post(
        args,
        body,
        env={"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "web"},
        skip_permission=True,
        business_only=True,
    )
    raw_reply = raw_reply.decode("utf-8") if isinstance(raw_reply, bytes) else str(raw_reply)
    try:
        reply_type, parsed_content = _parse_reply(raw_reply)
    except Exception as exc:
        logger.warning("[wechatmp-web-sim] failed to parse reply: {}".format(exc))
        reply_type, parsed_content = "text", raw_reply
    return WeChatMPSimulationResult(reply_type=reply_type, content=parsed_content, raw_reply=raw_reply)
