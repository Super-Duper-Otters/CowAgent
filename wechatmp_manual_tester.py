# encoding:utf-8
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import requests

from wechatmp_chain_check import (
    ParsedReply,
    build_signed_url,
    build_text_message_xml,
    database_url,
    load_config,
    normalize_wx_url,
    parse_reply_xml,
)


DEFAULT_TO_USER = "gh_test"
DEFAULT_OPENID = "o92zVw4BYH2qaibHAA-_fuw6w32k"
BOX_WIDTH = 96


@dataclass
class ManualExchange:
    wx_url: str
    openid: str
    to_user: str
    input_text: str
    signed_url: str
    request_xml: bytes
    status_code: int
    elapsed_seconds: float
    reply: ParsedReply


@dataclass
class InteractiveState:
    openid: str
    show_xml: bool
    last_png: Path | None = None
    pending_pngs: list[Path] = field(default_factory=list)
    next_png_index: int = 0


def default_wx_url(config: dict) -> str:
    return normalize_wx_url(f"http://127.0.0.1:{int(config.get('wechatmp_port', 8080))}")


def default_token(config: dict) -> str:
    token = str(config.get("wechatmp_token") or "").strip()
    if not token:
        raise RuntimeError("wechatmp_token is empty; pass --token or configure config.json")
    return token


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manually send WeChat Official Account XML text messages to the CowAgent /wx backend.",
    )
    parser.add_argument("text", nargs="*", help="Message text to send. Omit to enter manual interactive mode.")
    parser.add_argument(
        "--openid",
        default=DEFAULT_OPENID,
        help="Initial simulated WeChat user OpenID. Change it in interactive mode with /openid <openid>.",
    )
    parser.add_argument("--url", help="Backend /wx URL or base URL. Defaults to local config port.")
    parser.add_argument("--token", help="WechatMP token. Defaults to config.json wechatmp_token.")
    parser.add_argument("--to-user", default=DEFAULT_TO_USER, help="Simulated public account id used as ToUserName.")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds.")
    parser.add_argument(
        "--inspect-db",
        dest="inspect_db",
        action="store_true",
        default=True,
        help="Print the matching investment request record and output_files. Enabled by default.",
    )
    parser.add_argument("--no-inspect-db", dest="inspect_db", action="store_false", help="Disable DB inspection output.")
    parser.add_argument("--db-timeout", type=int, default=45, help="Seconds to wait for a matching DB request record.")
    parser.add_argument(
        "--open-image",
        dest="open_image",
        action="store_true",
        default=True,
        help="Open the first existing PNG from output_files after DB inspection. Enabled by default.",
    )
    parser.add_argument("--no-open-image", dest="open_image", action="store_false", help="Disable automatic local PNG opening.")
    parser.add_argument("--show-xml", action="store_true", help="Print request and response XML.")
    parser.add_argument("--interactive", "-i", action="store_true", help="Start an interactive sender loop.")
    return parser


def should_run_interactive(args: argparse.Namespace) -> bool:
    return bool(args.interactive or not args.text)


def normalize_args(args: argparse.Namespace) -> argparse.Namespace:
    if args.open_image:
        args.inspect_db = True
    return args


def should_open_remembered_after_text(text: str, args: argparse.Namespace, state: InteractiveState) -> bool:
    return bool(
        args.open_image
        and text.strip() == "1"
        and state.pending_pngs
        and state.next_png_index < len(state.pending_pngs)
        and state.pending_pngs[state.next_png_index].exists()
    )


def should_inspect_db_after_text(text: str, args: argparse.Namespace, state: InteractiveState | None = None) -> bool:
    if not (args.inspect_db or args.open_image):
        return False
    if state is not None and should_open_remembered_after_text(text, args, state):
        return False
    return True


def _display_width(text: str) -> int:
    width = 0
    for char in str(text):
        width += 2 if ord(char) > 127 else 1
    return width


def _pad_display(text: str, width: int) -> str:
    value = str(text)
    return value + " " * max(0, width - _display_width(value))


def _wrap_text(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for raw_line in str(text or "").splitlines() or [""]:
        current = ""
        current_width = 0
        for char in raw_line:
            char_width = 2 if ord(char) > 127 else 1
            if current and current_width + char_width > width:
                lines.append(current)
                current = char
                current_width = char_width
            else:
                current += char
                current_width += char_width
        lines.append(current)
    return lines


def tui_box(title: str, lines: list[str], *, width: int = BOX_WIDTH) -> str:
    inner_width = max(20, width - 4)
    title_text = f"-- {title} "
    top = "+" + title_text + "-" * max(0, width - 1 - _display_width(title_text)) + "+"
    body: list[str] = []
    for line in lines or [""]:
        for wrapped in _wrap_text(line, inner_width):
            body.append("| " + _pad_display(wrapped, inner_width) + " |")
    bottom = "+" + "-" * (width - 2) + "+"
    return "\n".join([top, *body, bottom])


def format_kv(label: str, value) -> str:
    return f"{label:<11}{value}"


def format_header(*, wx_url: str, openid: str, to_user: str, inspect_db: bool, open_image: bool) -> str:
    return tui_box(
        "CowAgent WeChatMP Manual Tester",
        [
            format_kv("URL", wx_url),
            format_kv("OpenID", openid),
            format_kv("ToUserName", to_user),
            format_kv("InspectDB", "on" if inspect_db else "off"),
            format_kv("OpenImage", "on" if open_image else "off"),
            "Commands   /openid <id>  /xml on|off  /quit",
        ],
    )


def format_user_input(text: str) -> str:
    return f"> {text}"


def send_wechat_text(
    session: requests.Session,
    *,
    wx_url: str,
    token: str,
    to_user: str,
    openid: str,
    text: str,
    timeout_sec: int,
) -> ManualExchange:
    create_time = int(time.time())
    msg_id = str(int(time.time() * 1000))
    signed_url = build_signed_url(wx_url, token, timestamp=str(create_time))
    request_xml = build_text_message_xml(
        to_user=to_user,
        from_user=openid,
        content=text,
        msg_id=msg_id,
        create_time=create_time,
    )
    started = time.perf_counter()
    response = session.post(
        signed_url,
        data=request_xml,
        headers={"Content-Type": "application/xml"},
        timeout=timeout_sec,
    )
    elapsed = time.perf_counter() - started
    return ManualExchange(
        wx_url=wx_url,
        openid=openid,
        to_user=to_user,
        input_text=text,
        signed_url=signed_url,
        request_xml=request_xml,
        status_code=response.status_code,
        elapsed_seconds=elapsed,
        reply=parse_reply_xml(response.text),
    )


def parse_output_files(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return [text]
        return parse_output_files(decoded)
    return [str(value)]


def first_existing_png(output_files: list[str]) -> Path | None:
    for item in output_files:
        path = Path(str(item))
        if path.suffix.lower() == ".png" and path.exists():
            return path
    return None


def open_first_png(output_files: list[str]) -> Path | None:
    path = first_existing_png(output_files)
    if path is None:
        return None
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
    return path


def open_path(path: Path) -> Path:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
    return path


def remember_record_png(state: InteractiveState, record: dict | None) -> Path | None:
    pngs = [
        Path(item)
        for item in parse_output_files(record.get("output_files") if record else [])
        if Path(item).suffix.lower() == ".png" and Path(item).exists()
    ]
    if not pngs:
        return None
    state.pending_pngs = pngs
    state.next_png_index = 0
    state.last_png = pngs[0]
    return pngs[0]


def open_remembered_png(state: InteractiveState) -> Path | None:
    if state.pending_pngs and state.next_png_index < len(state.pending_pngs):
        path = state.pending_pngs[state.next_png_index]
        state.next_png_index += 1
        state.last_png = path
        if path.exists():
            return open_path(path)
    return None


def fetch_request_record(
    db_url: str,
    *,
    openid: str,
    raw_input: str,
    since: datetime,
    timeout_sec: int,
) -> dict | None:
    deadline = time.time() + max(0, timeout_sec)
    since_text = since.isoformat(timespec="microseconds")
    last_record = None
    columns = [
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
        "cache_hit",
    ]
    while True:
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    select {", ".join(columns)}
                    from investment_request_records
                    where openid=%s and raw_input=%s and created_at >= %s
                    order by created_at desc
                    limit 1
                    """,
                    (openid, raw_input, since_text),
                )
                row = cur.fetchone()
        if row:
            last_record = dict(zip(columns, row, strict=False))
            if str(last_record.get("status") or "") != "generating":
                return last_record
        if time.time() >= deadline:
            return last_record
        time.sleep(1)


def format_request_record(record: dict | None) -> str:
    if not record:
        return tui_box("请求记录", ["未找到"])
    output_files = parse_output_files(record.get("output_files"))
    lines = [
        f"请求记录: {record.get('request_id') or ''}",
        f"service_type: {record.get('service_type') or ''}",
        f"cache_hit: {record.get('cache_hit')}",
        format_kv("service_type", record.get("service_type") or ""),
        f"status       {record.get('status') or ''}",
        format_kv("status", record.get("status") or ""),
        format_kv("cache_hit", record.get("cache_hit")),
        format_kv("elapsed_ms", record.get("elapsed_ms")),
    ]
    if record.get("error_code"):
        lines.append(format_kv("error_code", record.get("error_code")))
    if record.get("error_message"):
        lines.append(format_kv("error_msg", record.get("error_message")))
    lines.append("output_files:")
    if output_files:
        lines.extend(f"- {item}" for item in output_files)
    else:
        lines.append("- (empty)")
    png = first_existing_png(output_files)
    if png:
        lines.append(f"首张PNG: {png}")
    rendered = tui_box("请求记录", lines)
    if output_files:
        raw_paths = ["完整输出路径:", *output_files]
        if png:
            raw_paths.append(f"首张PNG: {png}")
        rendered += "\n" + "\n".join(raw_paths)
    return rendered


def inspect_db_after_send(
    args: argparse.Namespace,
    config: dict,
    exchange: ManualExchange,
    *,
    since: datetime,
    state: InteractiveState | None = None,
) -> dict | None:
    record = fetch_request_record(
        database_url(config),
        openid=exchange.openid,
        raw_input=exchange.input_text,
        since=since,
        timeout_sec=args.db_timeout,
    )
    print("")
    print(format_request_record(record))
    if state is not None:
        remember_record_png(state, record)
    if args.open_image:
        output_files = parse_output_files(record.get("output_files") if record else [])
        opened = open_first_png(output_files)
        if opened is None and state is not None and exchange.input_text.strip() == "1":
            opened = open_remembered_png(state)
        if opened:
            print(f"已打开图片: {opened}")
        elif output_files:
            print("未找到可打开的 PNG")
    return record


def format_exchange(exchange: ManualExchange, *, show_xml: bool) -> str:
    blocks = [
        tui_box(
            f"后台回复 · {exchange.reply.msg_type or 'raw'} · {exchange.elapsed_seconds:.3f}s",
            [
                f"URL: {exchange.wx_url}",
                f"OpenID: {exchange.openid}",
                f"ToUserName: {exchange.to_user}",
                f"输入: {exchange.input_text}",
                f"输入     {exchange.input_text}",
                f"HTTP: {exchange.status_code}",
            ],
        )
    ]
    if show_xml:
        blocks.append(
            tui_box(
                "请求 XML",
                [
                    "请求XML:",
                    exchange.request_xml.decode("utf-8", errors="replace"),
                ],
            )
        )

    reply_lines = []
    if exchange.reply.is_xml:
        reply_lines.append(f"回复类型: {exchange.reply.msg_type or '(empty)'}")
        if exchange.reply.content:
            reply_lines.append("回复文本:")
            reply_lines.append(exchange.reply.content)
        if exchange.reply.media_id:
            reply_lines.append(f"MediaId: {exchange.reply.media_id}")
        if exchange.reply.to_user or exchange.reply.from_user:
            reply_lines.append(f"Reply ToUserName: {exchange.reply.to_user}")
            reply_lines.append(f"Reply FromUserName: {exchange.reply.from_user}")
    else:
        reply_lines.append("回复类型: raw")
        reply_lines.append(exchange.reply.raw_text)
    blocks.append(tui_box("内容", reply_lines))

    if show_xml:
        blocks.append(tui_box("响应 XML", ["响应XML:", exchange.reply.raw_text]))
    return "\n\n".join(blocks)


def handle_interactive_command(raw_text: str, state: InteractiveState) -> bool:
    text = raw_text.strip()
    if text.startswith("/openid "):
        next_openid = text[len("/openid ") :].strip()
        if next_openid:
            state.openid = next_openid
            print(f"OpenID 已切换为: {state.openid}")
        else:
            print("用法: /openid <openid>")
        return True
    if text == "/xml on":
        state.show_xml = True
        print("已开启 XML 输出")
        return True
    if text == "/xml off":
        state.show_xml = False
        print("已关闭 XML 输出")
        return True
    return False


def run_interactive(args: argparse.Namespace, *, wx_url: str, token: str, config: dict) -> int:
    state = InteractiveState(openid=args.openid, show_xml=args.show_xml)
    session = requests.Session()
    print(format_header(wx_url=wx_url, openid=state.openid, to_user=args.to_user, inspect_db=args.inspect_db, open_image=args.open_image))
    while True:
        try:
            raw_text = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        text = raw_text.strip()
        if not text:
            continue
        if text in {"/quit", "/exit"}:
            return 0
        if handle_interactive_command(text, state):
            if text.startswith("/openid "):
                print(format_header(wx_url=wx_url, openid=state.openid, to_user=args.to_user, inspect_db=args.inspect_db, open_image=args.open_image))
            continue
        try:
            since = datetime.now(timezone.utc)
            exchange = send_wechat_text(
                session,
                wx_url=wx_url,
                token=token,
                to_user=args.to_user,
                openid=state.openid,
                text=text,
                timeout_sec=args.timeout,
            )
        except Exception as exc:
            print(f"发送失败: {type(exc).__name__}: {exc}")
            continue
        print(format_exchange(exchange, show_xml=state.show_xml))
        if should_open_remembered_after_text(text, args, state):
            opened = open_remembered_png(state)
            if opened:
                print(f"已打开最近图片: {opened}")
            else:
                print("未找到可打开的最近 PNG")
        elif should_inspect_db_after_text(text, args, state):
            inspect_db_after_send(args, config, exchange, since=since, state=state)


def main(argv: list[str] | None = None) -> int:
    args = normalize_args(build_arg_parser().parse_args(argv))
    root = Path(__file__).resolve().parent
    config = load_config(root)
    wx_url = normalize_wx_url(args.url) if args.url else default_wx_url(config)
    token = args.token or default_token(config)
    if should_run_interactive(args):
        return run_interactive(args, wx_url=wx_url, token=token, config=config)

    text = " ".join(args.text).strip()
    if not text:
        print("缺少消息内容。传入文本，或使用 --interactive。", file=sys.stderr)
        return 2
    since = datetime.now(timezone.utc)
    exchange = send_wechat_text(
        requests.Session(),
        wx_url=wx_url,
        token=token,
        to_user=args.to_user,
        openid=args.openid,
        text=text,
        timeout_sec=args.timeout,
    )
    print(format_exchange(exchange, show_xml=args.show_xml))
    if should_inspect_db_after_text(text, args):
        inspect_db_after_send(args, config, exchange, since=since)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
