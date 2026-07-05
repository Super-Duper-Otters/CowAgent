# encoding:utf-8
import argparse
import json
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import and_, select

from business.config.constants import ServiceType
from business.schema.db import connect, row_to_dict
from business.schema.tables import investment_products, investment_stock_symbols


DEFAULT_SYMBOLS = ["600519.SH", "000333.SZ", "510300.SH", "sh000300", "111009.SH"]


def _now_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _xml_escape(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _text_xml(openid: str, content: str, msg_id: str) -> bytes:
    created = int(time.time())
    return f"""<xml>
<ToUserName><![CDATA[gh_test]]></ToUserName>
<FromUserName><![CDATA[{openid}]]></FromUserName>
<CreateTime>{created}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[{_xml_escape(content)}]]></Content>
<MsgId>{re.sub(r"\\D", "", str(msg_id or "")) or int(time.time() * 1000)}</MsgId>
</xml>""".encode("utf-8")


def _strip_xml_text(value: str) -> str:
    text = str(value or "")
    if not text.startswith("<"):
        return text
    try:
        root = ET.fromstring(text)
    except Exception:
        return text
    content = root.findtext("Content")
    if content:
        return content
    image = root.find("Image")
    if image is not None:
        media_id = image.findtext("MediaId") or ""
        return f"[image:{media_id}]"
    msg_type = root.findtext("MsgType") or ""
    return f"[{msg_type or 'xml'}]"


def _event(run_dir: Path, payload: dict) -> None:
    payload = {"ts": datetime.now().isoformat(timespec="seconds"), **payload}
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


class _FakeMedia:
    def __init__(self):
        self.uploads = []

    def upload(self, media_type, media):
        filename = media[0] if isinstance(media, tuple) and media else "media"
        media_id = f"fake-{media_type}-{len(self.uploads) + 1:04d}"
        self.uploads.append({"media_type": media_type, "filename": filename, "media_id": media_id})
        return {"media_id": media_id}


def _patch_wechat_uploads():
    from channel.wechatmp.wechatmp_channel import WechatMPChannel

    channel = WechatMPChannel()
    fake_media = _FakeMedia()
    channel.client.media = fake_media
    if not hasattr(channel.client, "material"):
        channel.client.material = SimpleNamespace()
    channel.client.material.add = lambda media_type, media: fake_media.upload(media_type, media)
    return channel, fake_media


def _patch_authorized_customer():
    allowed = SimpleNamespace(allowed=True, user_prompt="")
    try:
        import business.routing.router as router

        router.verify_user_access = lambda _openid: allowed
        router.verify_permission = lambda _openid, _service_type: allowed
    except Exception:
        pass
    try:
        import business.accounts.permission_service as permission_service

        permission_service.verify_customer_access = lambda _openid: allowed
        permission_service.verify_customer_business_access = lambda _openid, _service_type: allowed
    except Exception:
        pass


def _post_text(openid: str, content: str, msg_id: str) -> str:
    import channel.wechatmp.passive_reply as passive_reply

    passive_reply.is_encrypted_message = lambda _args: False
    passive_reply.decrypt_message_if_needed = lambda _args, message, _crypto: message
    return passive_reply.handle_wechatmp_post(
        {},
        _text_xml(openid, content, msg_id),
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "0"},
        skip_permission=True,
        business_only=True,
    )


def _cached_targets() -> set[str]:
    stmt = select(investment_products.c.target_key).where(
        and_(
            investment_products.c.business_type == str(ServiceType.TECHNICAL_ANALYSIS),
            investment_products.c.status == "active",
        )
    )
    with connect() as conn:
        return {str(row_to_dict(row).get("target_key") or "").upper() for row in conn.execute(stmt).fetchall()}


def _sample_targets(count: int, seed: str) -> list[dict]:
    cached = _cached_targets()
    table = investment_stock_symbols
    stmt = (
        select(table.c.code, table.c.name, table.c.asset_type)
        .where(table.c.asset_type.in_(("a_share", "etf", "convertible_bond", "index")))
        .order_by(table.c.code)
    )
    with connect() as conn:
        rows = [row_to_dict(row) for row in conn.execute(stmt).fetchall()]
    candidates = [
        row
        for row in rows
        if str(row.get("code") or "").upper() not in cached
        and not re.search(r"(退市|全收益|净收益)", str(row.get("name") or ""))
        and not re.search(r"(CNY|HKD|USD|EUR|GBP|CAD)", str(row.get("code") or ""), re.I)
    ]
    rng = random.Random(seed)
    rng.shuffle(candidates)
    return candidates[:count]


def _wait_for_state(channel, openid: str, *, timeout_seconds: int) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        pending = channel.cache_dict.peek_result(openid)
        running = openid in channel.running
        if pending is not None:
            return {
                "state": "pending",
                "title": getattr(pending, "title", ""),
                "service_type": str(getattr(pending, "service_type", "")),
                "reply_count": len(getattr(pending, "replies", []) or []),
            }
        if not running:
            return {"state": "not_running_no_pending"}
        time.sleep(2)
    return {"state": "timeout_waiting", "running": openid in channel.running}


def _run_case(run_dir: Path, channel, case: dict, index: int, timeout_seconds: int) -> dict:
    openid = case["openid"]
    symbol = case["symbol"]
    initial = f"#{symbol}"
    prefix = f"case-{index:03d}"
    result = {
        "case_id": prefix,
        "openid": openid,
        "symbol": symbol,
        "name": case.get("name", ""),
        "events": [],
        "ok_checks": {},
    }

    def send(step: str, content: str) -> str:
        msg_id = f"{index}{len(result['events']) + 1:02d}{int(time.time() * 1000)}"
        response = _post_text(openid, content, msg_id)
        text = _strip_xml_text(response)
        item = {"case_id": prefix, "openid": openid, "symbol": symbol, "step": step, "content": content, "response": text}
        result["events"].append(item)
        _event(run_dir, item)
        return text

    ack = send("start", initial)
    ready_hit = "结果已准备好" in ack
    result["ok_checks"]["immediate_ack_or_ready"] = ack.startswith("收到，正在处理") or ready_hit
    if ready_hit:
        result["ready_hit"] = True
        return result

    time.sleep(1)
    running_one = send("running_confirm_1", "1")
    result["ok_checks"]["running_confirm_1"] = "仍在运行" in running_one or "正在运行" in running_one

    running_plain = send("running_plain", "你好")
    result["ok_checks"]["running_plain"] = "仍在运行" in running_plain or "正在运行" in running_plain

    running_new = send("running_new_hash", "#600519.SH" if symbol != "600519.SH" else "#000333.SZ")
    result["ok_checks"]["running_new_hash"] = "暂不接受新的技术分析请求" in running_new or "仍在运行" in running_new

    wait_state = _wait_for_state(channel, openid, timeout_seconds=timeout_seconds)
    result["wait_state"] = wait_state
    result["ok_checks"]["eventually_pending"] = wait_state.get("state") == "pending"
    if wait_state.get("state") == "pending":
        claim = send("claim_1", "1")
        result["ok_checks"]["claim_returns_image_or_text"] = claim.startswith("[image:") or "无法生成技术分析" in claim or "暂时不可用" in claim
        if claim.startswith("[image:"):
            second = send("claim_1_second", "1")
            result["ok_checks"]["second_claim_or_no_pending"] = second.startswith("[image:") or "当前没有待领取结果" in second or "请输入" in second
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--symbols", default="")
    args = parser.parse_args()

    from config import load_config

    load_config()
    run_id = _now_id()
    run_dir = REPO_ROOT / "business_storage" / "tmp" / "wechatmp_mixed_real_flow" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir.parent / "latest_run.txt").write_text(str(run_dir), encoding="utf-8")

    channel, fake_media = _patch_wechat_uploads()
    _patch_authorized_customer()

    requested_symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    if requested_symbols:
        targets = [{"code": symbol, "name": ""} for symbol in requested_symbols]
    else:
        sampled = _sample_targets(args.cases, f"wechatmp-mixed-real-{run_id}")
        if len(sampled) < args.cases:
            sampled.extend({"code": symbol, "name": ""} for symbol in DEFAULT_SYMBOLS)
        targets = sampled[: args.cases]

    plan = [
        {
            "openid": f"wechatmp_real_user_{idx + 1:02d}",
            "symbol": str(row.get("code") or ""),
            "name": str(row.get("name") or ""),
        }
        for idx, row in enumerate(targets)
    ]
    (run_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    results = []
    for idx, case in enumerate(plan, 1):
        results.append(_run_case(run_dir, channel, case, idx, args.timeout_seconds))
        (run_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "run_dir": str(run_dir),
        "total": len(results),
        "passed": sum(1 for item in results if all(item.get("ok_checks", {}).values())),
        "failed": sum(1 for item in results if not all(item.get("ok_checks", {}).values())),
        "media_uploads": fake_media.uploads,
        "results": [
            {
                "case_id": item["case_id"],
                "symbol": item["symbol"],
                "name": item.get("name", ""),
                "ready_hit": bool(item.get("ready_hit")),
                "wait_state": item.get("wait_state", {}),
                "ok_checks": item.get("ok_checks", {}),
            }
            for item in results
        ],
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
