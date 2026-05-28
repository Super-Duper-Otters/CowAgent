# encoding:utf-8
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import psycopg
import requests


DEFAULT_DATABASE_URL = "postgresql://cowagent:cowagent@127.0.0.1:55432/cowagent_investment"
DEFAULT_TECHNICAL_ANALYSIS_QUERY = "天娱数科 技术分析"
DEFAULT_CONVERTIBLE_BOND_QUERY = "转债"
SMOKE_UNMATCHED_QUERY = "技术分析"
TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
TUNNEL_REGISTERED_MARKERS = (
    "Registered tunnel connection",
    "Connection registered",
)


@dataclass
class ParsedReply:
    is_xml: bool
    msg_type: str = ""
    content: str = ""
    media_id: str = ""
    to_user: str = ""
    from_user: str = ""
    raw_text: str = ""


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    skipped: bool = False
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class WxTarget:
    wx_url: str
    source: str


def mask_id(value: str | None, keep: int = 12) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= keep:
        return text
    return text[:keep] + "..."


def normalize_wx_url(value: str) -> str:
    url = (value or "").strip()
    if not url:
        raise ValueError("empty URL")
    url = url.rstrip("/")
    if url.endswith("/wx"):
        return url
    return url + "/wx"


def resolve_wx_target(args: argparse.Namespace, config: dict[str, Any], root: Path) -> WxTarget:
    if args.local:
        wx_url = normalize_wx_url(f"http://127.0.0.1:{int(config.get('wechatmp_port', 8080))}")
        return WxTarget(wx_url=wx_url, source="local")
    if args.base_url:
        return WxTarget(wx_url=normalize_wx_url(args.base_url), source="base-url")

    tunnel = discover_tunnel_base_url(root)
    if not tunnel:
        raise RuntimeError("no trycloudflare URL found in logs; pass --base-url or --local")
    return WxTarget(wx_url=normalize_wx_url(tunnel), source="cloudflare")


def build_signed_url(
    wx_url: str,
    token: str,
    *,
    timestamp: str | None = None,
    nonce: str | None = None,
    extra: dict[str, str] | None = None,
) -> str:
    timestamp = timestamp or str(int(time.time()))
    nonce = nonce or uuid.uuid4().hex[:10]
    signature = hashlib.sha1("".join(sorted([token, timestamp, nonce])).encode("utf-8")).hexdigest()
    params = {
        "signature": signature,
        "timestamp": timestamp,
        "nonce": nonce,
    }
    if extra:
        params.update(extra)
    return wx_url + "?" + urllib.parse.urlencode(params)


def parse_reply_xml(body: str) -> ParsedReply:
    text = body or ""
    if not text.strip().startswith("<xml"):
        return ParsedReply(is_xml=False, raw_text=text)
    root = ElementTree.fromstring(text)

    def node_text(path: str) -> str:
        node = root.find(path)
        if node is None:
            return ""
        return "".join(node.itertext())

    return ParsedReply(
        is_xml=True,
        msg_type=node_text("MsgType"),
        content=node_text("Content"),
        media_id=node_text("Image/MediaId"),
        to_user=node_text("ToUserName"),
        from_user=node_text("FromUserName"),
        raw_text=text,
    )


def load_config(root: Path) -> dict[str, Any]:
    config_path = root / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"config.json not found: {config_path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


def load_project_runtime_config(root: Path) -> None:
    cwd = Path.cwd()
    try:
        os.chdir(root)
        import config as project_config

        project_config.load_config()
    finally:
        os.chdir(cwd)


def parse_channel_types(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def channel_mode(config: dict[str, Any]) -> str:
    channels = parse_channel_types(config.get("channel_type"))
    if "wechatmp_service" in channels:
        return "active"
    if "wechatmp" in channels:
        return "passive"
    return "unknown"


def discover_tunnel_base_url(root: Path) -> str | None:
    candidates: list[tuple[float, int, str]] = []
    log_files = list((root / "logs").glob("cloudflared*.log"))
    log_files += [root / "run.log", root / "nohup.out"]
    for file_path in log_files:
        if not file_path.exists() or not file_path.is_file():
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        mtime = file_path.stat().st_mtime
        for index, match in enumerate(TUNNEL_URL_RE.findall(content)):
            candidates.append((mtime, index, match.rstrip("/")))
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1][2]


def extract_latest_tunnel_url(text: str) -> str | None:
    matches = TUNNEL_URL_RE.findall(text or "")
    return matches[-1].rstrip("/") if matches else None


def cloudflared_registered(text: str) -> bool:
    return any(marker in (text or "") for marker in TUNNEL_REGISTERED_MARKERS)


def build_cloudflared_args(port: int, protocol: str) -> list[str]:
    return [
        "tunnel",
        "--url",
        f"http://127.0.0.1:{int(port)}",
        "--protocol",
        protocol,
        "--no-autoupdate",
    ]


def find_cloudflared_exe(explicit: str | None = None) -> str:
    candidates = [
        explicit,
        os.environ.get("CLOUDFLARED_EXE"),
        shutil.which("cloudflared"),
        r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
        r"C:\Program Files\cloudflared\cloudflared.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise FileNotFoundError("cloudflared executable not found; pass --cloudflared-exe or set CLOUDFLARED_EXE")


def stop_cloudflared() -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/IM", "cloudflared.exe", "/F"], capture_output=True, text=True, check=False)
        return
    subprocess.run(["pkill", "-f", "cloudflared"], capture_output=True, text=True, check=False)


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def repair_tunnel(
    root: Path,
    *,
    port: int,
    protocol: str,
    timeout_sec: int,
    cloudflared_exe: str | None = None,
) -> tuple[str, int, Path, Path]:
    exe = find_cloudflared_exe(cloudflared_exe)
    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_log = logs_dir / "cloudflared.repair.out.log"
    err_log = logs_dir / "cloudflared.repair.err.log"
    out_log.write_text("", encoding="utf-8")
    err_log.write_text("", encoding="utf-8")

    stop_cloudflared()
    time.sleep(2)

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with out_log.open("wb") as out_handle, err_log.open("wb") as err_handle:
        process = subprocess.Popen(
            [exe, *build_cloudflared_args(port, protocol)],
            cwd=str(root),
            stdout=out_handle,
            stderr=err_handle,
            creationflags=creationflags,
        )

    deadline = time.time() + timeout_sec
    latest_url = ""
    while time.time() < deadline:
        combined_log = read_text_if_exists(err_log) + "\n" + read_text_if_exists(out_log)
        latest_url = extract_latest_tunnel_url(combined_log) or ""
        if latest_url and cloudflared_registered(combined_log):
            return latest_url, process.pid, out_log, err_log
        if process.poll() is not None:
            break
        time.sleep(1)

    combined_log = (read_text_if_exists(err_log) + "\n" + read_text_if_exists(out_log))[-1000:]
    raise RuntimeError(f"cloudflared did not produce a trycloudflare URL within {timeout_sec}s. Recent log:\n{combined_log}")


def database_url(config: dict[str, Any]) -> str:
    return normalize_psycopg_url(
        os.environ.get("COWAGENT_INVESTMENT_DATABASE_URL")
        or str(config.get("investment_database_url") or "").strip()
        or DEFAULT_DATABASE_URL
    )


def normalize_psycopg_url(url: str) -> str:
    value = str(url or "").strip()
    if value.startswith("postgresql+psycopg://"):
        return "postgresql://" + value[len("postgresql+psycopg://") :]
    if value.startswith("postgresql+psycopg2://"):
        return "postgresql://" + value[len("postgresql+psycopg2://") :]
    return value


def latest_enabled_openid(db_url: str) -> str:
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("select openid from investment_users where enabled=1 order by id desc limit 1")
            row = cur.fetchone()
    if not row:
        raise RuntimeError("no enabled user found in investment_users")
    return str(row[0])


def latest_rate_image(db_url: str, root: Path) -> Path | None:
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select output_image
                from investment_daily_contents
                where service_type='rate' and status='effective'
                order by effective_at desc, created_at desc
                limit 1
                """
            )
            row = cur.fetchone()
    if not row or not row[0]:
        fallback = root / "investment" / "generated" / "rate_card.png"
        return fallback if fallback.exists() else None
    path = Path(str(row[0]))
    return path if path.is_absolute() else root / path


def wait_for_request_record(
    db_url: str,
    *,
    openid: str,
    raw_input: str,
    since: datetime,
    timeout_sec: int,
    statuses: set[str] | None = None,
) -> dict[str, Any] | None:
    deadline = time.time() + timeout_sec
    since_text = since.isoformat(timespec="microseconds")
    last_record: dict[str, Any] | None = None
    while time.time() < deadline:
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select request_id, raw_input, service_type, status, output_files,
                           created_at, updated_at, elapsed_ms, error_code, error_message
                    from investment_request_records
                    where openid=%s and raw_input=%s and created_at >= %s
                    order by created_at desc
                    limit 1
                    """,
                    (openid, raw_input, since_text),
                )
                row = cur.fetchone()
        if row:
            keys = [
                "request_id",
                "raw_input",
                "service_type",
                "status",
                "output_files",
                "created_at",
                "updated_at",
                "elapsed_ms",
                "error_code",
                "error_message",
            ]
            last_record = dict(zip(keys, row, strict=False))
            if statuses is None or str(last_record.get("status") or "") in statuses:
                return last_record
        time.sleep(1)
    return last_record


def build_text_message_xml(*, to_user: str, from_user: str, content: str, msg_id: str, create_time: int) -> bytes:
    return f"""<xml>
<ToUserName><![CDATA[{to_user}]]></ToUserName>
<FromUserName><![CDATA[{from_user}]]></FromUserName>
<CreateTime>{create_time}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[{content}]]></Content>
<MsgId>{msg_id}</MsgId>
</xml>""".encode("utf-8")


def post_wechat_text(
    session: requests.Session,
    *,
    wx_url: str,
    token: str,
    to_user: str,
    openid: str,
    content: str,
    msg_id: str | None = None,
    timeout_sec: int = 20,
) -> tuple[requests.Response, ParsedReply]:
    msg_id = msg_id or str(int(time.time() * 1000))
    create_time = int(time.time())
    signed = build_signed_url(wx_url, token, timestamp=str(create_time))
    xml = build_text_message_xml(
        to_user=to_user,
        from_user=openid,
        content=content,
        msg_id=msg_id,
        create_time=create_time,
    )
    response = session.post(signed, data=xml, headers={"Content-Type": "application/xml"}, timeout=timeout_sec)
    return response, parse_reply_xml(response.text)


def log_offset(root: Path) -> int:
    log_path = root / "run.log"
    if not log_path.exists():
        return 0
    return log_path.stat().st_size


def count_log_pattern_since(root: Path, start_offset: int, pattern: str) -> int:
    log_path = root / "run.log"
    if not log_path.exists():
        return 0
    with log_path.open("rb") as handle:
        handle.seek(start_offset)
        data = handle.read().decode("utf-8", errors="replace")
    return data.count(pattern)


def wait_for_log_count(root: Path, *, start_offset: int, pattern: str, expected_count: int, timeout_sec: int) -> int:
    deadline = time.time() + timeout_sec
    last_count = 0
    while time.time() < deadline:
        last_count = count_log_pattern_since(root, start_offset, pattern)
        if last_count >= expected_count:
            return last_count
        time.sleep(1)
    return last_count


def result_line(result: CheckResult) -> str:
    if result.skipped:
        status = "SKIP"
    elif result.ok:
        status = "PASS"
    else:
        status = "FAIL"
    detail = f" - {result.detail}" if result.detail else ""
    return f"[{status}] {result.name}{detail}"


def default_content_queries(rate_query: str, ta_query: str, cb_query: str) -> list[str]:
    queries = [rate_query, cb_query, ta_query]
    return [query for query in queries if str(query or "").strip()]


def check_get_verify(session: requests.Session, wx_url: str, token: str, timeout_sec: int) -> CheckResult:
    echostr = "wechatmp_chain_ok"
    url = build_signed_url(wx_url, token, extra={"echostr": echostr})
    try:
        response = session.get(url, timeout=timeout_sec)
    except Exception as exc:
        return CheckResult("tunnel GET /wx signature verification", False, f"{type(exc).__name__}: {exc}")
    ok = response.status_code == 200 and response.text == echostr
    return CheckResult(
        "tunnel GET /wx signature verification",
        ok,
        f"status={response.status_code}, body={response.text[:80]!r}",
    )


def check_smoke_unmatched_post(
    session: requests.Session,
    *,
    wx_url: str,
    token: str,
    to_user: str,
    timeout_sec: int,
) -> CheckResult:
    try:
        response, reply = post_wechat_text(
            session,
            wx_url=wx_url,
            token=token,
            to_user=to_user,
            openid="openid_codex_smoke_probe",
            content=SMOKE_UNMATCHED_QUERY,
            timeout_sec=timeout_sec,
        )
    except Exception as exc:
        return CheckResult("POST smoke unmatched prompt", False, f"{type(exc).__name__}: {exc}")

    ok = response.status_code == 200 and reply.msg_type == "text" and reply.content.startswith("请输入以下格式之一")
    detail = f"status={response.status_code}, msg_type={reply.msg_type}, content={reply.content[:80]!r}"
    if ok:
        detail += ", passive_text_prompt"
    return CheckResult("POST smoke unmatched prompt", ok, detail)


def run_smoke_checks(
    args: argparse.Namespace,
    *,
    root: Path,
    config: dict[str, Any],
    target: WxTarget,
    token: str,
    session: requests.Session,
) -> tuple[WxTarget, list[CheckResult]]:
    def repair_cloudflare_tunnel() -> bool:
        nonlocal target
        try:
            tunnel_url, pid, out_log, err_log = repair_tunnel(
                root,
                port=int(config.get("wechatmp_port", 8080)),
                protocol=args.tunnel_protocol,
                timeout_sec=args.timeout,
                cloudflared_exe=args.cloudflared_exe,
            )
            target = WxTarget(wx_url=normalize_wx_url(tunnel_url), source="cloudflare-repaired")
            checks.append(
                CheckResult(
                    "Cloudflare tunnel auto-repair",
                    True,
                    f"new_url={tunnel_url}, wx_url={target.wx_url}, pid={pid}, logs={err_log}",
                    data={"tunnel_url": tunnel_url, "wx_url": target.wx_url, "pid": pid, "out_log": str(out_log), "err_log": str(err_log)},
                )
            )
        except Exception as exc:
            checks.append(CheckResult("Cloudflare tunnel auto-repair", False, f"{type(exc).__name__}: {exc}"))
            return False
        return True

    repaired = False
    checks = [check_get_verify(session, target.wx_url, token, args.timeout)]
    if target.source == "cloudflare" and not checks[-1].ok and not args.no_auto_repair:
        repaired = repair_cloudflare_tunnel()
        if repaired:
            checks.append(check_get_verify(session, target.wx_url, token, args.timeout))

    if checks[-1].ok:
        smoke_post = check_smoke_unmatched_post(
            session,
            wx_url=target.wx_url,
            token=token,
            to_user=args.to_user,
            timeout_sec=args.timeout,
        )
        checks.append(smoke_post)
        if target.source.startswith("cloudflare") and not smoke_post.ok and not repaired and not args.no_auto_repair:
            repaired = repair_cloudflare_tunnel()
            if repaired:
                checks.append(check_get_verify(session, target.wx_url, token, args.timeout))
                if checks[-1].ok:
                    checks.append(
                        check_smoke_unmatched_post(
                            session,
                            wx_url=target.wx_url,
                            token=token,
                            to_user=args.to_user,
                            timeout_sec=args.timeout,
                        )
                    )
    return target, checks


def wait_for_get_verify(session: requests.Session, wx_url: str, token: str, timeout_sec: int) -> CheckResult:
    deadline = time.time() + timeout_sec
    last_result = CheckResult("tunnel GET /wx signature verification", False, "not attempted")
    while time.time() < deadline:
        per_attempt_timeout = max(1, min(5, int(deadline - time.time())))
        last_result = check_get_verify(session, wx_url, token, per_attempt_timeout)
        if last_result.ok:
            return last_result
        time.sleep(2)
    return last_result


def check_direct_media_upload(config: dict[str, Any], image_path: Path | None, root: Path) -> CheckResult:
    if not image_path:
        return CheckResult("WeChat temporary media upload", False, "no rate image found")
    if not image_path.exists():
        return CheckResult("WeChat temporary media upload", False, f"image does not exist: {image_path}")
    appid = str(config.get("wechatmp_app_id") or "")
    secret = str(config.get("wechatmp_app_secret") or "")
    if not appid or not secret:
        return CheckResult("WeChat temporary media upload", False, "wechatmp_app_id/app_secret missing")
    try:
        sys.path.insert(0, str(root))
        from channel.wechatmp.wechatmp_client import WechatMPClient

        wechat_session = requests.Session()
        wechat_session.trust_env = False
        client = WechatMPClient(appid, secret, session=wechat_session)
        client.fetch_access_token()
        content_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
        with image_path.open("rb") as handle:
            response = client.media.upload("image", (image_path.name, handle, content_type))
    except Exception as exc:
        return CheckResult("WeChat temporary media upload", False, f"{type(exc).__name__}: {exc}")
    media_id = response.get("media_id", "")
    return CheckResult(
        "WeChat temporary media upload",
        bool(media_id),
        f"image={image_path.name}, size={image_path.stat().st_size}, media_id={mask_id(media_id)}",
        data={"media_id": media_id, "image_path": str(image_path)},
    )


def check_direct_customer_service_image_send(
    config: dict[str, Any],
    image_path: Path | None,
    openid: str,
    root: Path,
) -> CheckResult:
    if not image_path:
        return CheckResult("WeChat customer-service image send", False, "no rate image found")
    if not image_path.exists():
        return CheckResult("WeChat customer-service image send", False, f"image does not exist: {image_path}")
    appid = str(config.get("wechatmp_app_id") or "")
    secret = str(config.get("wechatmp_app_secret") or "")
    if not appid or not secret:
        return CheckResult("WeChat customer-service image send", False, "wechatmp_app_id/app_secret missing")
    try:
        sys.path.insert(0, str(root))
        from channel.wechatmp.wechatmp_client import WechatMPClient

        wechat_session = requests.Session()
        wechat_session.trust_env = False
        client = WechatMPClient(appid, secret, session=wechat_session)
        client.fetch_access_token()
        content_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
        with image_path.open("rb") as handle:
            upload_response = client.media.upload("image", (image_path.name, handle, content_type))
        media_id = upload_response.get("media_id", "")
        if not media_id:
            return CheckResult("WeChat customer-service image send", False, f"upload response missing media_id: {upload_response}")
        send_response = client.message.send_image(openid, media_id)
    except Exception as exc:
        return CheckResult("WeChat customer-service image send", False, f"{type(exc).__name__}: {exc}")
    return CheckResult(
        "WeChat customer-service image send",
        True,
        f"openid={mask_id(openid)}, media_id={mask_id(media_id)}, response={send_response}",
        data={"media_id": media_id, "response": send_response},
    )


def check_business_content(root: Path, openid: str, query: str) -> CheckResult:
    try:
        sys.path.insert(0, str(root))
        from business.investment.constants import ErrorCode, user_message
        from business.investment.router import handle_text_message

        reply = handle_text_message(openid, query)
    except Exception as exc:
        return CheckResult(f"local content route: {query}", False, f"{type(exc).__name__}: {exc}")

    output_files = [Path(str(path)) for path in reply.output_files if str(path or "").strip()]
    existing_files = [path for path in output_files if path.exists()]
    ok = reply.handled and reply.success and bool(output_files) and len(existing_files) == len(output_files)
    expected_no_content = (
        reply.handled
        and not reply.success
        and reply.error_code == ErrorCode.NO_CONTENT
        and (reply.user_prompt or reply.reply_text) == user_message(ErrorCode.NO_CONTENT)
    )
    if expected_no_content:
        ok = True
    detail = (
        f"service_type={reply.service_type}, success={reply.success}, "
        f"files={len(output_files)}, existing={len(existing_files)}"
    )
    if expected_no_content:
        detail += ", no content prompt returned"
    if not ok and reply.user_prompt:
        detail += f", prompt={reply.user_prompt[:80]!r}"
    return CheckResult(
        f"local content route: {query}",
        ok,
        detail,
        data={"output_files": [str(path) for path in output_files]},
    )


def check_rate_message(
    session: requests.Session,
    *,
    wx_url: str,
    token: str,
    to_user: str,
    openid: str,
    query: str,
    mode: str,
    root: Path,
    db_url: str,
    timeout_sec: int,
    wait_timeout_sec: int,
) -> CheckResult:
    since = datetime.now(timezone.utc) - timedelta(seconds=2)
    start_offset = log_offset(root)
    try:
        response, reply = post_wechat_text(
            session,
            wx_url=wx_url,
            token=token,
            to_user=to_user,
            openid=openid,
            content=query,
            timeout_sec=timeout_sec,
        )
    except Exception as exc:
        return CheckResult("POST rate message", False, f"{type(exc).__name__}: {exc}")

    if mode == "passive":
        ok = response.status_code == 200 and reply.msg_type == "image" and bool(reply.media_id)
        detail = f"status={response.status_code}, msg_type={reply.msg_type or reply.raw_text[:40]}, media_id={mask_id(reply.media_id)}"
        return CheckResult("POST rate message passive image reply", ok, detail)

    if mode == "active":
        record = wait_for_request_record(
            db_url,
            openid=openid,
            raw_input=query,
            since=since,
            timeout_sec=wait_timeout_sec,
            statuses={"success", "failed"},
        )
        send_count = wait_for_log_count(
            root,
            start_offset=start_offset,
            pattern=f"Do send image to {openid}",
            expected_count=1,
            timeout_sec=wait_timeout_sec,
        )
        ok = response.status_code == 200 and response.text == "success" and record is not None and record.get("status") == "success" and send_count >= 1
        detail = (
            f"response={response.text[:40]!r}, db_status={record.get('status') if record else 'missing'}, "
            f"active_image_sends={send_count}"
        )
        return CheckResult("POST rate message active customer-service reply", ok, detail)

    ok = response.status_code == 200
    return CheckResult("POST rate message", ok, f"mode={mode}, status={response.status_code}, body={response.text[:80]!r}")


def expected_image_count_from_record(record: dict[str, Any] | None) -> int:
    if not record:
        return 0
    try:
        files = json.loads(str(record.get("output_files") or "[]"))
    except json.JSONDecodeError:
        return 0
    return len([path for path in files if str(path).lower().endswith((".png", ".jpg", ".jpeg"))])


def output_paths_from_record(record: dict[str, Any] | None) -> list[Path]:
    if not record:
        return []
    try:
        files = json.loads(str(record.get("output_files") or "[]"))
    except json.JSONDecodeError:
        return []
    return [Path(str(path)) for path in files if str(path or "").strip()]


def evaluate_webhook_result(
    *,
    query: str,
    mode: str,
    status_code: int,
    response_text: str,
    reply: ParsedReply,
    record: dict[str, Any] | None,
) -> CheckResult:
    response_preview = (response_text or "")[:80]
    if mode == "active":
        output_paths = output_paths_from_record(record)
        existing_count = len([path for path in output_paths if path.exists()])
        ok = (
            status_code == 200
            and (response_text or "").strip() == "success"
            and record is not None
            and record.get("status") == "success"
            and bool(output_paths)
            and existing_count == len(output_paths)
        )
        detail = (
            f"status={status_code}, returned={response_preview!r}, "
            f"db_status={record.get('status') if record else 'missing'}, "
            f"files={len(output_paths)}, existing={existing_count}, "
            f"elapsed_ms={record.get('elapsed_ms') if record else 'n/a'}"
        )
        return CheckResult(f"POST webhook content: {query}", ok, detail, data={"output_files": [str(path) for path in output_paths]})

    if reply.is_xml:
        ok = status_code == 200 and bool(reply.msg_type)
        detail = f"status={status_code}, msg_type={reply.msg_type}, media_id={mask_id(reply.media_id)}, content={reply.content[:40]!r}"
        return CheckResult(f"POST webhook content: {query}", ok, detail)

    ok = status_code == 200 and bool((response_text or "").strip())
    return CheckResult(f"POST webhook content: {query}", ok, f"status={status_code}, returned={response_preview!r}")


def check_webhook_message(
    session: requests.Session,
    *,
    wx_url: str,
    token: str,
    to_user: str,
    openid: str,
    query: str,
    mode: str,
    db_url: str,
    timeout_sec: int,
    wait_timeout_sec: int,
) -> CheckResult:
    since = datetime.now(timezone.utc) - timedelta(seconds=2)
    try:
        response, reply = post_wechat_text(
            session,
            wx_url=wx_url,
            token=token,
            to_user=to_user,
            openid=openid,
            content=query,
            timeout_sec=timeout_sec,
        )
    except Exception as exc:
        return CheckResult(f"POST webhook content: {query}", False, f"{type(exc).__name__}: {exc}")

    record = wait_for_request_record(
        db_url,
        openid=openid,
        raw_input=query,
        since=since,
        timeout_sec=wait_timeout_sec,
        statuses={"success", "failed"},
    )
    return evaluate_webhook_result(
        query=query,
        mode=mode,
        status_code=response.status_code,
        response_text=response.text,
        reply=reply,
        record=record,
    )


def check_ta_message(
    session: requests.Session,
    *,
    wx_url: str,
    token: str,
    to_user: str,
    openid: str,
    query: str,
    mode: str,
    root: Path,
    db_url: str,
    timeout_sec: int,
    wait_timeout_sec: int,
) -> CheckResult:
    since = datetime.now(timezone.utc) - timedelta(seconds=2)
    start_offset = log_offset(root)
    try:
        response, reply = post_wechat_text(
            session,
            wx_url=wx_url,
            token=token,
            to_user=to_user,
            openid=openid,
            content=query,
            timeout_sec=timeout_sec,
        )
    except Exception as exc:
        return CheckResult("POST technical-analysis message", False, f"{type(exc).__name__}: {exc}")

    record = wait_for_request_record(
        db_url,
        openid=openid,
        raw_input=query,
        since=since,
        timeout_sec=wait_timeout_sec,
        statuses={"success", "failed"},
    )
    image_count = expected_image_count_from_record(record)

    if mode == "active":
        send_count = wait_for_log_count(
            root,
            start_offset=start_offset,
            pattern=f"Do send image to {openid}",
            expected_count=max(image_count, 1),
            timeout_sec=wait_timeout_sec,
        )
        ok = response.status_code == 200 and response.text == "success" and record is not None and record.get("status") == "success" and send_count >= max(image_count, 1)
        detail = (
            f"response={response.text[:40]!r}, db_status={record.get('status') if record else 'missing'}, "
            f"expected_images={image_count}, active_image_sends={send_count}, elapsed_ms={record.get('elapsed_ms') if record else 'n/a'}"
        )
        return CheckResult("POST technical-analysis active customer-service reply", ok, detail)

    if mode == "passive":
        if reply.msg_type == "image":
            return CheckResult("POST technical-analysis passive reply", True, f"immediate image media_id={mask_id(reply.media_id)}")
        detail = (
            f"first_response={reply.msg_type or response.text[:40]!r}, "
            f"db_status={record.get('status') if record else 'missing'}, elapsed_ms={record.get('elapsed_ms') if record else 'n/a'}"
        )
        return CheckResult("POST technical-analysis passive reply", record is not None and record.get("status") == "success", detail)

    ok = record is not None and record.get("status") == "success"
    return CheckResult("POST technical-analysis message", ok, f"mode={mode}, db_status={record.get('status') if record else 'missing'}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check WeChat MP backend, tunnel, media upload, and message reply chains.")
    parser.add_argument("--base-url", help="Tunnel base URL or full /wx URL. Defaults to latest trycloudflare URL from logs.")
    parser.add_argument("--local", action="store_true", help="Use local http://127.0.0.1:<wechatmp_port>/wx instead of tunnel discovery.")
    parser.add_argument("--openid", help="OpenID to simulate. Defaults to latest enabled investment user.")
    parser.add_argument("--to-user", default="gh_test", help="Developer account id used as ToUserName in simulated incoming XML.")
    parser.add_argument("--rate-query", default="利率", help="Rate command to test.")
    parser.add_argument("--cb-query", default=DEFAULT_CONVERTIBLE_BOND_QUERY, help="Convertible-bond command to test.")
    parser.add_argument("--ta-query", default=DEFAULT_TECHNICAL_ANALYSIS_QUERY, help="Technical-analysis command to test.")
    parser.add_argument("--timeout", type=int, default=25, help="HTTP request timeout in seconds.")
    parser.add_argument("--wait-timeout", type=int, default=120, help="Wait timeout for DB/log async checks.")
    parser.add_argument("--smoke", action="store_true", help="Run minimal Cloudflare /wx GET plus safe passive prompt POST only.")
    parser.add_argument("--full", action="store_true", help="Run full local business generation checks for rate, convertible bond, and technical analysis.")
    parser.add_argument("--no-auto-repair", action="store_true", help="Do not recreate the Cloudflare quick tunnel if smoke GET verification fails.")
    parser.add_argument("--wechat-api", action="store_true", help="Also test WeChat temporary media upload. Does not send messages.")
    parser.add_argument("--send-kf-image", action="store_true", help="Actually send one customer-service image to --openid. Off by default.")
    parser.add_argument("--post-webhook", action="store_true", help="Simulate incoming WeChat POST. In active mode this can trigger customer-service sending.")
    parser.add_argument("--skip-upload", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--repair-tunnel", action="store_true", help="Restart cloudflared quick tunnel and print the new URL.")
    parser.add_argument("--cloudflared-exe", help="Path to cloudflared.exe. Defaults to PATH or common Windows install paths.")
    parser.add_argument("--tunnel-protocol", default="http2", choices=["http2", "quic"], help="cloudflared protocol for --repair-tunnel.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parent
    config = load_config(root)
    load_project_runtime_config(root)
    token = str(config.get("wechatmp_token") or "")
    if not token:
        raise RuntimeError("wechatmp_token missing in config.json")

    if args.repair_tunnel:
        port = int(config.get("wechatmp_port", 8080))
        tunnel_url, pid, out_log, err_log = repair_tunnel(
            root,
            port=port,
            protocol=args.tunnel_protocol,
            timeout_sec=args.timeout,
            cloudflared_exe=args.cloudflared_exe,
        )
        wx_url = normalize_wx_url(tunnel_url)
        session = requests.Session()
        session.trust_env = False
        verify = wait_for_get_verify(session, wx_url, token, args.timeout)
        payload = {
            "tunnel_url": tunnel_url,
            "wx_url": wx_url,
            "pid": pid,
            "protocol": args.tunnel_protocol,
            "out_log": str(out_log),
            "err_log": str(err_log),
            "verify": verify.__dict__,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"New Cloudflare tunnel URL: {tunnel_url}")
            print(f"WeChat backend URL: {wx_url}")
            print(f"cloudflared PID: {pid}")
            print(result_line(verify))
            print(f"Logs: {err_log}")
        return 0 if verify.ok else 1

    target = resolve_wx_target(args, config, root)
    wx_url = target.wx_url

    db_url = database_url(config)
    openid = args.openid or latest_enabled_openid(db_url)
    mode = channel_mode(config)
    session = requests.Session()
    session.trust_env = False

    checks: list[CheckResult] = [
        CheckResult("configuration", mode != "unknown", f"channel_mode={mode}, target={target.source}, wx_url={wx_url}, openid={mask_id(openid)}"),
    ]

    if args.smoke:
        target, smoke_checks = run_smoke_checks(
            args,
            root=root,
            config=config,
            target=target,
            token=token,
            session=session,
        )
        wx_url = target.wx_url
        checks.extend(smoke_checks)
        if args.json:
            print(json.dumps([check.__dict__ for check in checks], ensure_ascii=False, indent=2, default=str))
        else:
            print(f"WeChat MP smoke check: {datetime.now().isoformat(timespec='seconds')}")
            for check in checks:
                print(result_line(check))
        failed = [check for check in checks if not check.skipped and not check.ok]
        return 1 if failed else 0

    checks.append(check_get_verify(session, wx_url, token, args.timeout))

    if args.post_webhook:
        for query in default_content_queries(args.rate_query, args.ta_query, args.cb_query):
            checks.append(
                check_webhook_message(
                    session,
                    wx_url=wx_url,
                    token=token,
                    to_user=args.to_user,
                    openid=openid,
                    query=query,
                    mode=mode,
                    db_url=db_url,
                    timeout_sec=args.timeout,
                    wait_timeout_sec=args.wait_timeout,
                )
            )
    else:
        for query in default_content_queries(args.rate_query, args.ta_query, args.cb_query):
            checks.append(check_business_content(root, openid, query))
        checks.append(CheckResult("POST webhook simulation", True, "skipped; pass --post-webhook to run direct /wx POST", skipped=True))

    rate_image = None
    if args.wechat_api and not args.skip_upload:
        rate_image = latest_rate_image(db_url, root)
        checks.append(check_direct_media_upload(config, rate_image, root))
    else:
        checks.append(CheckResult("WeChat temporary media upload", True, "skipped; pass --wechat-api to run", skipped=True))

    if args.send_kf_image:
        if rate_image is None:
            rate_image = latest_rate_image(db_url, root)
        checks.append(check_direct_customer_service_image_send(config, rate_image, openid, root))
    else:
        checks.append(CheckResult("WeChat customer-service image send", True, "skipped; pass --send-kf-image to actually send", skipped=True))

    if args.json:
        print(json.dumps([check.__dict__ for check in checks], ensure_ascii=False, indent=2, default=str))
    else:
        print(f"WeChat MP chain check: {datetime.now().isoformat(timespec='seconds')}")
        for check in checks:
            print(result_line(check))

    failed = [check for check in checks if not check.skipped and not check.ok]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
