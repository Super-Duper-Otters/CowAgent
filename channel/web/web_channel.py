import hashlib
import hmac
import time
import json
import logging
import mimetypes
import os
import threading
import uuid
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from queue import Queue, Empty
from typing import Tuple
from urllib.parse import quote

import web

from bridge.context import Context, ContextType
from bridge.reply import Reply, ReplyType
from channel.chat_channel import ChatChannel, check_prefix
from channel.chat_message import ChatMessage
from collections import OrderedDict
from common import const
from common.log import logger
from common.singleton import singleton
from config import conf

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".avi", ".mov", ".mkv"}

def _is_password_enabled():
    return bool(conf().get("web_password", ""))


def _session_expire_seconds():
    return int(conf().get("web_session_expire_days", 30)) * 86400


def _create_auth_token():
    """Create a stateless signed token: ``<timestamp_hex>.<hmac_hex>``."""
    ts = format(int(time.time()), "x")
    sig = hmac.new(
        conf().get("web_password", "").encode(),
        ts.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{ts}.{sig}"


def _verify_auth_token(token):
    """Verify a signed token is valid and not expired.

    The token is derived from the password, so it survives server restarts
    and automatically invalidates when the password changes.
    """
    if not token or "." not in token:
        return False
    ts_hex, sig = token.split(".", 1)
    try:
        ts = int(ts_hex, 16)
    except ValueError:
        return False
    if time.time() - ts > _session_expire_seconds():
        return False
    expected = hmac.new(
        conf().get("web_password", "").encode(),
        ts_hex.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(sig, expected)


def _check_auth():
    """Return True if request is authenticated or password not enabled."""
    if not _is_password_enabled():
        return True
    return _verify_auth_token(web.cookies().get("cow_auth_token", ""))


def _investment_admin_login_enabled():
    try:
        from business.investment.auth_service import count_admin_users

        return count_admin_users() > 0
    except Exception:
        return False


def _is_console_login_required():
    return _is_password_enabled() or _investment_admin_login_enabled()


def _check_console_auth():
    if _investment_admin_login_enabled():
        return _current_investment_admin() is not None
    return _check_auth()


def _safe_next_path(value: str | None, default: str = "/chat") -> str:
    if not value:
        return default
    value = str(value)
    if not value.startswith("/") or value.startswith("//") or "\r" in value or "\n" in value:
        return default
    if value.startswith("/login"):
        return default
    return value


def _login_redirect_url(next_path: str | None = "/chat") -> str:
    return f"/login?next={quote(_safe_next_path(next_path), safe='')}"


def _current_request_path(default: str = "/chat") -> str:
    return _safe_next_path(getattr(web.ctx, "fullpath", "") or getattr(web.ctx, "path", "") or default)


def _require_auth():
    """Raise 401 if not authenticated. Call at the top of protected handlers."""
    if not _check_auth():
        raise web.HTTPError("401 Unauthorized",
                            {"Content-Type": "application/json; charset=utf-8"},
                            json.dumps({"status": "error", "message": "Unauthorized"}))


def _require_console_auth():
    if not _check_console_auth():
        raise web.HTTPError(
            "401 Unauthorized",
            {"Content-Type": "application/json; charset=utf-8"},
            json.dumps({"status": "error", "message": "Unauthorized"}, ensure_ascii=False),
        )


def _investment_session_token():
    return web.cookies().get("cow_investment_session", "")


def _current_investment_admin():
    from business.investment.auth_service import AdminUser, count_admin_users, get_admin_session

    if count_admin_users() == 0:
        _require_auth()
        return AdminUser(id=0, username="bootstrap", role="admin", enabled=True, bootstrap=True)
    return get_admin_session(_investment_session_token())


def _investment_permission_error(permission: str):
    from business.investment.auth_service import require_permission

    result = require_permission(_current_investment_admin(), permission)
    if result.allowed:
        return {}
    return {"status": "error", "code": result.code, "message": result.message, "permission": permission}


def _require_investment_permission(permission: str):
    from business.investment.auth_service import require_permission

    admin = _current_investment_admin()
    result = require_permission(admin, permission)
    if not result.allowed:
        error = {"status": "error", "code": result.code, "message": result.message, "permission": permission}
        raise web.HTTPError(
            "401 Unauthorized" if error.get("code") == "unauthorized" else "403 Forbidden",
            {"Content-Type": "application/json; charset=utf-8"},
            json.dumps(error, ensure_ascii=False),
        )
    return admin


def _investment_admin_payload(admin):
    if admin is None:
        return None
    from business.investment.auth_service import permissions_for_role

    permissions = sorted(permissions_for_role(admin.role))
    return {
        "username": admin.username,
        "role": admin.role,
        "permissions": permissions,
        "bootstrap": bool(getattr(admin, "bootstrap", False)),
    }


def _record_investment_operation(action: str, target_type: str, target_id: str = "", *, admin=None, detail=None):
    try:
        from business.investment.audit_service import record_operation_audit

        operator = getattr(admin, "username", "") if admin is not None else ""
        record_operation_audit(action, target_type, target_id, operator=operator, detail=detail or {})
    except Exception as audit_error:
        logger.warning(f"[Investment] operation audit failed: {audit_error}")


def _get_upload_dir() -> str:
    from common.utils import expand_path
    ws_root = expand_path(conf().get("agent_workspace", "~/cow"))
    tmp_dir = os.path.join(ws_root, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    return tmp_dir


def _sanitize_upload_relative_path(relative_path: str) -> str:
    """Normalize relative upload path and reject escapes / absolute paths."""
    relative_path = (relative_path or "").replace("\\", "/").strip("/")
    if not relative_path:
        raise ValueError("Empty relative path")
    parts = []
    for part in relative_path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError("Invalid relative path")
        parts.append(part)
    if not parts:
        raise ValueError("Invalid relative path")
    norm_path = "/".join(parts)
    if os.path.isabs(norm_path):
        raise ValueError("Invalid relative path")
    return norm_path


def _sanitize_upload_id(upload_id: str) -> str:
    """Allow only simple batch ids for directory uploads."""
    sanitized = "".join(ch for ch in (upload_id or "") if ch.isalnum() or ch in ("-", "_"))
    if not sanitized:
        raise ValueError("Invalid upload id")
    return sanitized[:80]


def _is_within_directory(root_path: str, target_path: str) -> bool:
    try:
        return os.path.commonpath([root_path, target_path]) == root_path
    except ValueError:
        return False


def _resolve_upload_path(upload_root: str, relative_path: str) -> Tuple[str, str]:
    """Resolve a relative upload path under upload_root and reject escapes."""
    safe_rel_path = _sanitize_upload_relative_path(relative_path)
    upload_root_real = os.path.realpath(upload_root)
    save_path = os.path.realpath(os.path.join(upload_root_real, *safe_rel_path.split("/")))
    if not _is_within_directory(upload_root_real, save_path):
        raise ValueError("Invalid directory upload path")
    return safe_rel_path, save_path


def _read_uploaded_file_bytes(file_obj) -> bytes:
    """Return uploaded content as bytes across web.py upload object variants."""
    if isinstance(file_obj, bytes):
        return file_obj
    if isinstance(file_obj, str):
        return file_obj.encode("utf-8")

    content = None

    if hasattr(file_obj, "file") and hasattr(file_obj.file, "read"):
        content = file_obj.file.read()
    elif hasattr(file_obj, "read"):
        content = file_obj.read()
    elif hasattr(file_obj, "value"):
        content = file_obj.value

    if content is None:
        raise ValueError("Unable to read uploaded file content")
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8")
    raise TypeError(f"Unsupported uploaded content type: {type(content).__name__}")


def _raw_web_input():
    """Return unprocessed multipart form data when web.py exposes rawinput."""
    rawinput = getattr(getattr(web, "webapi", None), "rawinput", None)
    if not callable(rawinput):
        raise RuntimeError("web.py rawinput is not available")
    try:
        return rawinput(method="post")
    except TypeError:
        return rawinput()


def _ensure_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _generate_session_title(user_message: str, assistant_reply: str = "") -> str:
    """Delegate to the shared SessionService implementation."""
    from agent.chat.session_service import generate_session_title
    return generate_session_title(user_message, assistant_reply)


class WebMessage(ChatMessage):
    def __init__(
            self,
            msg_id,
            content,
            ctype=ContextType.TEXT,
            from_user_id="User",
            to_user_id="Chatgpt",
            other_user_id="Chatgpt",
    ):
        self.msg_id = msg_id
        self.ctype = ctype
        self.content = content
        self.from_user_id = from_user_id
        self.to_user_id = to_user_id
        self.other_user_id = other_user_id


def _is_investment_web_command(prompt: str) -> bool:
    from business.investment.skill_registry import match_investment_skill

    return match_investment_skill(prompt) is not None


def _format_investment_web_reply(business_reply) -> str:
    if not business_reply.success or not business_reply.output_files:
        return business_reply.reply_text
    links = []
    for path in business_reply.output_files:
        file_name = os.path.basename(path) or "investment-output.png"
        links.append(f"![{file_name}](/api/file?path={quote(path)})")
    return "已生成投资业务图片：\n\n" + "\n\n".join(links)


def _build_investment_web_reply(session_id: str, prompt: str):
    if _is_investment_web_command(prompt):
        from business.investment.router import handle_text_message

        business_reply = handle_text_message(session_id, prompt, skip_permission=True)
        if not business_reply.handled:
            return None
        return Reply(ReplyType.TEXT, _format_investment_web_reply(business_reply))

    from business.investment.config_service import get_config
    from business.investment.router import DEFAULT_UNMATCHED_PROMPT

    if get_config("router.enable_web_open_chat", False):
        return None
    return Reply(ReplyType.TEXT, DEFAULT_UNMATCHED_PROMPT)


@singleton
class WebChannel(ChatChannel):
    channel_type = "web"
    NOT_SUPPORT_REPLYTYPE = [ReplyType.VOICE]
    _instance = None

    # def __new__(cls):
    #     if cls._instance is None:
    #         cls._instance = super(WebChannel, cls).__new__(cls)
    #     return cls._instance

    def __init__(self):
        super().__init__()
        self.msg_id_counter = 0
        self.session_queues = {}  # session_id -> Queue (fallback polling)
        self.request_to_session = {}  # request_id -> session_id
        self.sse_queues = {}  # request_id -> Queue (SSE streaming)
        self._http_server = None

    def _generate_msg_id(self):
        """生成唯一的消息ID"""
        self.msg_id_counter += 1
        return str(int(time.time())) + str(self.msg_id_counter)

    def _generate_request_id(self):
        """生成唯一的请求ID"""
        return str(uuid.uuid4())

    def _generate_reply(self, context: Context, reply: Reply = Reply()) -> Reply:
        if context.type == ContextType.TEXT:
            try:
                session_id = context.get("session_id") or getattr(context.get("msg"), "from_user_id", "") or "web"
                investment_reply = _build_investment_web_reply(session_id, context.content)
                if investment_reply is not None:
                    return investment_reply
            except Exception as exc:
                logger.exception(f"[WebChannel] investment router failed: {exc}")
                from business.investment.constants import ErrorCode, user_message

                return Reply(ReplyType.TEXT, user_message(ErrorCode.SYSTEM_ERROR))
        from bridge.bridge import Bridge

        return Bridge().fetch_reply_content(context.content, context)

    def send(self, reply: Reply, context: Context):
        try:
            if reply.type in self.NOT_SUPPORT_REPLYTYPE:
                logger.warning(f"Web channel doesn't support {reply.type} yet")
                return

            if reply.type == ReplyType.IMAGE_URL:
                time.sleep(0.5)

            request_id = context.get("request_id", None)
            if not request_id:
                logger.error("No request_id found in context, cannot send message")
                return

            session_id = self.request_to_session.get(request_id)
            if not session_id:
                logger.error(f"No session_id found for request {request_id}")
                return

            # SSE mode: push events to SSE queue
            if request_id in self.sse_queues:
                content = reply.content if reply.content is not None else ""

                # Intermediate status lines (e.g. /install-browser phases) must NOT use "done",
                # or the frontend closes EventSource and drops subsequent events.
                if getattr(reply, "sse_phase", False):
                    self.sse_queues[request_id].put({
                        "type": "phase",
                        "content": content,
                        "request_id": request_id,
                        "timestamp": time.time(),
                    })
                    logger.debug(f"SSE phase for request {request_id}")
                    return

                # Files are already pushed via on_event (file_to_send) during agent execution.
                # Skip duplicate file pushes here; just let the done event through.
                if reply.type in (ReplyType.IMAGE_URL, ReplyType.FILE) and content.startswith("file://"):
                    text_content = getattr(reply, 'text_content', '')
                    if text_content:
                        self.sse_queues[request_id].put({
                            "type": "done",
                            "content": text_content,
                            "request_id": request_id,
                            "timestamp": time.time()
                        })
                    logger.debug(f"SSE skipped duplicate file for request {request_id}")
                    return

                # Skip http-URL FILE/IMAGE_URL replies produced by chat_channel's media extraction:
                # the text reply (already sent as "done") contains the URL and the frontend will
                # render it via renderMarkdown/injectVideoPlayers, so no separate SSE event needed.
                if reply.type in (ReplyType.FILE, ReplyType.IMAGE_URL) and content.startswith(("http://", "https://")):
                    logger.debug(f"SSE skipped http media reply for request {request_id}")
                    return

                self.sse_queues[request_id].put({
                    "type": "done",
                    "content": content,
                    "request_id": request_id,
                    "timestamp": time.time()
                })
                logger.debug(f"SSE done sent for request {request_id}")
                return

            # Fallback: polling mode
            if session_id in self.session_queues:
                content = reply.content if reply.content is not None else ""
                # Skip file:// IMAGE_URL/FILE replies originating from an SSE-enabled
                # request: they were already pushed via the `file_to_send` event during
                # agent execution. By the time the chat_channel sends the IMAGE_URL reply,
                # the SSE stream has typically closed (after the text "done") and the
                # request_id is gone from sse_queues, so we'd otherwise duplicate the file
                # as a polling bubble. Scheduler/push tasks have no on_event and must
                # still go through polling normally.
                if (
                    reply.type in (ReplyType.IMAGE_URL, ReplyType.FILE)
                    and content.startswith("file://")
                    and context.get("on_event") is not None
                ):
                    logger.debug(f"Polling skipped duplicate file reply for session {session_id}")
                    return
                response_data = {
                    "type": str(reply.type),
                    "content": content,
                    "timestamp": time.time(),
                    "request_id": request_id
                }
                self.session_queues[session_id].put(response_data)
                logger.debug(f"Response sent to poll queue for session {session_id}, request {request_id}")
            else:
                logger.warning(f"No response queue found for session {session_id}, response dropped")

        except Exception as e:
            logger.error(f"Error in send method: {e}")

    def _make_sse_callback(self, request_id: str):
        """Build an on_event callback that pushes agent stream events into the SSE queue."""

        # Cap reasoning bytes pushed to the frontend per request to avoid
        # browser stalls / crashes on very long chains-of-thought. Anything
        # beyond the cap is dropped from the stream (DB still persists a
        # truncated copy via _truncate_reasoning_for_storage).
        # Keep aligned with frontend REASONING_RENDER_CAP and backend
        # MAX_STORED_REASONING_CHARS.
        MAX_REASONING_STREAM_CHARS = 4 * 1024  # 4 KB
        # Use a single-element list as a mutable counter accessible from closure.
        reasoning_chars_sent = [0]
        reasoning_capped_notified = [False]

        def on_event(event: dict):
            if request_id not in self.sse_queues:
                return
            q = self.sse_queues[request_id]
            event_type = event.get("type")
            data = event.get("data", {})

            if event_type == "reasoning_update":
                delta = data.get("delta", "")
                if not delta:
                    return
                remaining = MAX_REASONING_STREAM_CHARS - reasoning_chars_sent[0]
                if remaining <= 0:
                    if not reasoning_capped_notified[0]:
                        reasoning_capped_notified[0] = True
                        q.put({
                            "type": "reasoning",
                            "content": "\n\n... [reasoning truncated for display] ...",
                        })
                    return
                if len(delta) > remaining:
                    delta = delta[:remaining]
                reasoning_chars_sent[0] += len(delta)
                q.put({"type": "reasoning", "content": delta})

            elif event_type == "message_update":
                delta = data.get("delta", "")
                if delta:
                    q.put({"type": "delta", "content": delta})

            elif event_type == "tool_execution_start":
                tool_name = data.get("tool_name", "tool")
                arguments = data.get("arguments", {})
                q.put({"type": "tool_start", "tool": tool_name, "arguments": arguments})

            elif event_type == "tool_execution_end":
                tool_name = data.get("tool_name", "tool")
                status = data.get("status", "success")
                result = data.get("result", "")
                exec_time = data.get("execution_time", 0)
                # Truncate long results to avoid huge SSE payloads
                result_str = str(result)
                if len(result_str) > 2000:
                    result_str = result_str[:2000] + "…"
                q.put({
                    "type": "tool_end",
                    "tool": tool_name,
                    "status": status,
                    "result": result_str,
                    "execution_time": round(exec_time, 2)
                })

            elif event_type == "message_end":
                tool_calls = data.get("tool_calls", [])
                if tool_calls:
                    q.put({"type": "message_end", "has_tool_calls": True})

            elif event_type == "agent_end":
                # Safety net: if the agent finishes with an empty final_response,
                # chat_channel skips _send_reply (because reply.content is empty),
                # which means no "done" event is ever emitted and the SSE stream
                # would hang until the 10-min idle timeout. Push a fallback "done"
                # here so the frontend always gets closure.
                final_response = data.get("final_response", "")
                if not final_response or not str(final_response).strip():
                    logger.warning(
                        f"[WebChannel] agent_end with empty final_response for "
                        f"request {request_id}, sending fallback done"
                    )
                    q.put({
                        "type": "done",
                        "content": "(模型未返回任何内容，请重试或换一种方式描述你的需求)",
                        "request_id": request_id,
                        "timestamp": time.time(),
                    })

            elif event_type == "file_to_send":
                file_path = data.get("path", "")
                file_name = data.get("file_name", os.path.basename(file_path))
                file_type = data.get("file_type", "file")
                from urllib.parse import quote
                web_url = f"/api/file?path={quote(file_path)}"
                is_image = file_type == "image"
                q.put({
                    "type": "image" if is_image else "file",
                    "content": web_url,
                    "file_name": file_name,
                })

        return on_event

    def upload_file(self):
        """Handle file or directory upload via multipart/form-data."""
        try:
            params = _raw_web_input()
            file_obj = params.get("file")
            file_objs = params.get("files")
            relative_path = params.get("relative_path", "")
            relative_paths = params.get("relative_paths")
            upload_id = params.get("upload_id", "")

            directory_files = _ensure_list(file_objs)

            # NOTE: cgi.FieldStorage raises TypeError on truthy checks for single-file
            # uploads (Python 3.9+). Always use `is not None` instead of `if file_obj`.
            if not directory_files and file_obj is not None and relative_path:
                directory_files = [file_obj]

            directory_rel_paths = _ensure_list(relative_paths)

            if not directory_rel_paths and relative_path:
                directory_rel_paths = [relative_path]

            is_directory_upload = bool(directory_files) or bool(directory_rel_paths) or bool(relative_path) or bool(upload_id)

            upload_dir = _get_upload_dir()
            if is_directory_upload:
                if not upload_id:
                    return json.dumps({"status": "error", "message": "Missing upload_id for directory upload"})
                if not directory_files:
                    return json.dumps({"status": "error", "message": "No files uploaded"})
                if len(directory_files) != len(directory_rel_paths):
                    return json.dumps({"status": "error", "message": "Directory upload payload mismatch"})

                safe_upload_id = _sanitize_upload_id(upload_id)
                upload_root = os.path.join(upload_dir, f"webdir_{safe_upload_id}")
                upload_root_real = os.path.realpath(upload_root)

                root_name = None
                saved_files = 0
                for file_obj, rel_path in zip(directory_files, directory_rel_paths):
                    if file_obj is None:
                        raise ValueError("Invalid uploaded file")
                    safe_rel_path, save_path = _resolve_upload_path(upload_root_real, rel_path)
                    current_root_name = safe_rel_path.split("/", 1)[0]
                    if root_name is None:
                        root_name = current_root_name
                    elif root_name != current_root_name:
                        raise ValueError("Directory upload must use a single root folder")
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    content_bytes = _read_uploaded_file_bytes(file_obj)
                    with open(save_path, "wb") as f:
                        f.write(content_bytes)
                    saved_files += 1

                if not root_name:
                    raise ValueError("Directory root path missing")

                root_path = os.path.realpath(os.path.join(upload_root_real, root_name))
                if not _is_within_directory(upload_root_real, root_path):
                    raise ValueError("Invalid directory upload path")

                logger.info(f"[WebChannel] Directory uploaded: {root_name} -> {root_path} ({saved_files} files)")
                return json.dumps({
                    "status": "success",
                    "file_path": root_path,
                    "file_name": root_name,
                    "file_type": "directory",
                    "file_count": saved_files,
                    "root_path": root_path,
                    "root_name": root_name,
                    "upload_type": "directory",
                }, ensure_ascii=False)

            if file_obj is None or not hasattr(file_obj, "filename") or not file_obj.filename:
                return json.dumps({"status": "error", "message": "No file uploaded"})

            original_name = file_obj.filename
            ext = os.path.splitext(original_name)[1].lower()
            safe_name = f"web_{uuid.uuid4().hex[:8]}{ext}"
            save_path = os.path.join(upload_dir, safe_name)
            public_path = safe_name
            display_name = original_name

            content_bytes = _read_uploaded_file_bytes(file_obj)
            with open(save_path, "wb") as f:
                f.write(content_bytes)

            if ext in IMAGE_EXTENSIONS:
                file_type = "image"
            elif ext in VIDEO_EXTENSIONS:
                file_type = "video"
            else:
                file_type = "file"

            from urllib.parse import quote
            preview_url = f"/uploads/{quote(public_path, safe='/')}"

            logger.info(f"[WebChannel] File uploaded: {original_name} -> {save_path} ({file_type})")

            return json.dumps({
                "status": "success",
                "file_path": save_path,
                "file_name": display_name,
                "file_type": file_type,
                "preview_url": preview_url,
            }, ensure_ascii=False)

        except Exception as e:
            logger.error(f"[WebChannel] File upload error: {e}", exc_info=True)
            return json.dumps({"status": "error", "message": str(e)})

    def post_message(self):
        """
        Handle incoming messages from users via POST request.
        Returns a request_id for tracking this specific request.
        Supports optional attachments (file paths from /upload).
        """
        try:
            data = web.data()
            json_data = json.loads(data)
            session_id = json_data.get('session_id', f'session_{int(time.time())}')
            prompt = json_data.get('message', '')
            use_sse = json_data.get('stream', True)
            attachments = json_data.get('attachments', [])

            # Append file references to the prompt (same format as QQ channel)
            if attachments:
                file_refs = []
                for att in attachments:
                    ftype = att.get("file_type", "file")
                    fpath = att.get("file_path", "")
                    if not fpath:
                        continue
                    if ftype == "image":
                        file_refs.append(f"[图片: {fpath}]")
                    elif ftype == "video":
                        file_refs.append(f"[视频: {fpath}]")
                    elif ftype == "directory":
                        file_refs.append(f"[目录: {fpath}]")
                    else:
                        file_refs.append(f"[文件: {fpath}]")
                if file_refs:
                    prompt = prompt + "\n" + "\n".join(file_refs)
                    logger.info(f"[WebChannel] Attached {len(file_refs)} file(s) to message")

            request_id = self._generate_request_id()
            self.request_to_session[request_id] = session_id

            if session_id not in self.session_queues:
                self.session_queues[session_id] = Queue()

            if use_sse:
                self.sse_queues[request_id] = Queue()

            trigger_prefixs = conf().get("single_chat_prefix", [""])
            if check_prefix(prompt, trigger_prefixs) is None:
                if trigger_prefixs:
                    prompt = trigger_prefixs[0] + prompt
                    logger.debug(f"[WebChannel] Added prefix to message: {prompt}")

            msg = WebMessage(self._generate_msg_id(), prompt)
            msg.from_user_id = session_id

            context = self._compose_context(ContextType.TEXT, prompt, msg=msg, isgroup=False)

            if context is None:
                logger.warning(f"[WebChannel] Context is None for session {session_id}, message may be filtered")
                if request_id in self.sse_queues:
                    del self.sse_queues[request_id]
                return json.dumps({"status": "error", "message": "Message was filtered"})

            context["session_id"] = session_id
            context["receiver"] = session_id
            context["request_id"] = request_id

            if use_sse:
                context["on_event"] = self._make_sse_callback(request_id)

            threading.Thread(target=self.produce, args=(context,)).start()

            return json.dumps({"status": "success", "request_id": request_id, "stream": use_sse})

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    def stream_response(self, request_id: str):
        """
        SSE generator for a given request_id.
        Yields UTF-8 encoded bytes to avoid WSGI Latin-1 mangling.
        Supports client reconnection: the queue is only removed after a
        "done" event is consumed, so a new GET /stream with the same
        request_id can resume reading remaining events.
        """
        if request_id not in self.sse_queues:
            yield b"data: {\"type\": \"error\", \"message\": \"invalid request_id\"}\n\n"
            return

        q = self.sse_queues[request_id]
        idle_timeout = 600  # 10 minutes without any real event
        deadline = time.time() + idle_timeout
        done = False

        try:
            while time.time() < deadline:
                try:
                    item = q.get(timeout=1)
                except Empty:
                    yield b": keepalive\n\n"
                    continue

                # Real event received, reset idle deadline
                deadline = time.time() + idle_timeout

                payload = json.dumps(item, ensure_ascii=False)
                yield f"data: {payload}\n\n".encode("utf-8")

                if item.get("type") == "done":
                    done = True
                    break
        finally:
            if done:
                self.sse_queues.pop(request_id, None)

    def poll_response(self):
        """
        Poll for responses using the session_id.
        """
        try:
            data = web.data()
            json_data = json.loads(data)
            session_id = json_data.get('session_id')

            if not session_id or session_id not in self.session_queues:
                return json.dumps({"status": "error", "message": "Invalid session ID"})

            # 尝试从队列获取响应，不等待
            try:
                # 使用peek而不是get，这样如果前端没有成功处理，下次还能获取到
                response = self.session_queues[session_id].get(block=False)

                # 返回响应，包含请求ID以区分不同请求
                return json.dumps({
                    "status": "success",
                    "has_content": True,
                    "content": response["content"],
                    "request_id": response["request_id"],
                    "timestamp": response["timestamp"]
                })

            except Empty:
                # 没有新响应
                return json.dumps({"status": "success", "has_content": False})

        except Exception as e:
            logger.error(f"Error polling response: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    def chat_page(self):
        """Serve the chat HTML page."""
        file_path = os.path.join(os.path.dirname(__file__), 'chat.html')  # 使用绝对路径
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def startup(self):
        configured_host = conf().get("web_host", "")
        host = configured_host or ("0.0.0.0" if _is_password_enabled() else "127.0.0.1")
        port = conf().get("web_port", 9899)
        is_public_bind = host in ("0.0.0.0", "::")

        # 打印可用渠道类型提示
        logger.info(
            "[WebChannel] 全部可用通道如下，可修改 config.json 配置文件中的 channel_type 字段进行切换，多个通道用逗号分隔：")
        logger.info("[WebChannel]   1. weixin           - 微信")
        logger.info("[WebChannel]   2. web              - 网页")
        logger.info("[WebChannel]   3. terminal         - 终端")
        logger.info("[WebChannel]   4. feishu           - 飞书")
        logger.info("[WebChannel]   5. dingtalk         - 钉钉")
        logger.info("[WebChannel]   6. wecom_bot        - 企微智能机器人")
        logger.info("[WebChannel]   7. wechatcom_app    - 企微自建应用")
        logger.info("[WebChannel]   8. wechatmp         - 个人公众号")
        logger.info("[WebChannel]   9. wechatmp_service - 企业公众号")
        logger.info("[WebChannel] ✅ Web控制台已运行")
        logger.info(f"[WebChannel] 🌐 本地访问: http://localhost:{port}")
        if is_public_bind:
            logger.info(f"[WebChannel] 🌍 服务器访问: http://YOUR_IP:{port} (将YOUR_IP替换为服务器IP)")
            if not _is_password_enabled():
                logger.info("[WebChannel] ⚠️  当前监听 0.0.0.0 且未设置 web_password，公网部署建议在 config.json 中配置访问密码")
        else:
            logger.info(f"[WebChannel] 🔒 当前仅监听 {host}，仅本机可访问。如需公网访问，请将 web_host 改为 0.0.0.0 并配置 web_password 密码")

        try:
            import webbrowser
            webbrowser.open(f"http://localhost:{port}")
            logger.debug(f"[WebChannel] Opened browser at http://localhost:{port}")
        except Exception as e:
            logger.debug(f"[WebChannel] Could not open browser: {e}")

        # 确保静态文件目录存在
        static_dir = os.path.join(os.path.dirname(__file__), 'static')
        if not os.path.exists(static_dir):
            os.makedirs(static_dir)
            logger.debug(f"[WebChannel] Created static directory: {static_dir}")

        urls = (
            '/', 'RootHandler',
            '/login', 'LoginPageHandler',
            '/auth/login', 'AuthLoginHandler',
            '/auth/check', 'AuthCheckHandler',
            '/auth/logout', 'AuthLogoutHandler',
            '/message', 'MessageHandler',
            '/upload', 'UploadHandler',
            '/uploads/(.*)', 'UploadsHandler',
            '/api/file', 'FileServeHandler',
            '/poll', 'PollHandler',
            '/stream', 'StreamHandler',
            '/chat', 'ChatHandler',
            '/config', 'ConfigHandler',
            '/api/channels', 'ChannelsHandler',
            '/api/weixin/qrlogin', 'WeixinQrHandler',
            '/api/feishu/register', 'FeishuRegisterHandler',
            '/api/tools', 'ToolsHandler',
            '/api/skills', 'SkillsHandler',
            '/api/memory', 'MemoryHandler',
            '/api/memory/content', 'MemoryContentHandler',
            '/api/knowledge/list', 'KnowledgeListHandler',
            '/api/knowledge/read', 'KnowledgeReadHandler',
            '/api/knowledge/graph', 'KnowledgeGraphHandler',
            '/api/scheduler', 'SchedulerHandler',
            '/api/sessions', 'SessionsHandler',
            '/api/sessions/(.*)/generate_title', 'SessionTitleHandler',
            '/api/sessions/(.*)/clear_context', 'SessionClearContextHandler',
            '/api/sessions/(.*)', 'SessionDetailHandler',
            '/api/history', 'HistoryHandler',
            '/api/logs', 'LogsHandler',
            '/api/version', 'VersionHandler',
            '/api/investment/export/requests.xlsx', 'InvestmentRequestRecordsExportHandler',
            '/api/investment/export/users.xlsx', 'InvestmentUsersExportHandler',
            '/api/investment/auth/me', 'InvestmentAuthMeHandler',
            '/api/investment/admin-users/(.*)/status/(enable|disable)', 'InvestmentAdminUserStatusHandler',
            '/api/investment/admin-users/(.*)/password', 'InvestmentAdminUserPasswordHandler',
            '/api/investment/admin-users', 'InvestmentAdminUsersHandler',
            '/api/investment/users/import-template.xlsx', 'InvestmentUsersImportTemplateHandler',
            '/api/investment/users/import', 'InvestmentUsersImportHandler',
            '/api/investment/users', 'InvestmentUsersHandler',
            '/api/investment/users/(.*)/status/(enable|disable)', 'InvestmentUserStatusHandler',
            '/api/investment/users/(.*)/disable', 'InvestmentUserDisableHandler',
            '/api/investment/daily-content', 'InvestmentDailyContentHandler',
            '/api/investment/daily-content/(.*)/generate', 'InvestmentDailyContentGenerateHandler',
            '/api/investment/daily-content/(.*)/effective', 'InvestmentDailyContentEffectiveHandler',
            '/api/investment/audits', 'InvestmentOperationAuditsHandler',
            '/api/investment/records/requests', 'InvestmentRequestRecordsHandler',
            '/api/investment/records/contents', 'InvestmentContentRecordsHandler',
            '/api/investment/cache', 'InvestmentCacheHandler',
            '/api/investment/cache/clear', 'InvestmentCacheClearHandler',
            '/api/investment/cache/(.*)/invalidate', 'InvestmentCacheEntryInvalidateHandler',
            '/api/investment/skills/versions', 'InvestmentSkillVersionsHandler',
            '/api/investment/skills/packages/upload', 'InvestmentSkillPackageUploadHandler',
            '/api/investment/skills/(.*)/settings', 'InvestmentSkillSettingsHandler',
            '/api/investment/skills/(.*)/upload', 'InvestmentSkillUploadHandler',
            '/api/investment/skills/(.*)/versions/(.*)/activate', 'InvestmentSkillActivateHandler',
            '/api/investment/skills/(.*)/versions/(.*)/delete', 'InvestmentSkillDeleteHandler',
            '/api/investment/config', 'InvestmentConfigHandler',
            '/api/investment/stocks/refresh', 'InvestmentStocksRefreshHandler',
            '/api/investment/stocks', 'InvestmentStocksHandler',
            '/api/investment/health', 'InvestmentHealthHandler',
            '/assets/(.*)', 'AssetsHandler',
        )
        app = web.application(urls, globals(), autoreload=False)

        # 完全禁用web.py的HTTP日志输出
        web.httpserver.LogMiddleware.log = lambda self, status, environ: None

        # 配置web.py的日志级别为ERROR
        logging.getLogger("web").setLevel(logging.ERROR)
        logging.getLogger("web.httpserver").setLevel(logging.ERROR)

        # Build WSGI app with middleware (same as runsimple but without print)
        func = web.httpserver.StaticMiddleware(app.wsgifunc())
        func = web.httpserver.LogMiddleware(func)
        server = web.httpserver.WSGIServer((host, port), func)
        server.daemon_threads = True
        # Default request_queue_size(5) / timeout(10s) / numthreads(10) are
        # too small: when SSE streams occupy many threads, the backlog fills
        # and new connections get refused (ERR_CONNECTION_ABORTED).
        server.request_queue_size = 128
        server.timeout = 300
        server.requests.min = 20
        server.requests.max = 80
        self._http_server = server
        try:
            server.start()
        except (KeyboardInterrupt, SystemExit):
            server.stop()
        except OSError as e:
            if e.errno in (48, 98):  # macOS/Linux EADDRINUSE
                logger.error(
                    f"[WebChannel] 端口 {port} 已被占用，可执行 `cow restart` 清理残留进程，"
                    f"或在 config.json 中修改 web_port"
                )
            raise

    def stop(self):
        if self._http_server:
            try:
                self._http_server.stop()
                logger.info("[WebChannel] HTTP server stopped")
            except Exception as e:
                logger.warning(f"[WebChannel] Error stopping HTTP server: {e}")
            self._http_server = None


class RootHandler:
    def GET(self):
        if not _check_console_auth():
            raise web.seeother(_login_redirect_url("/chat"))
        raise web.seeother('/chat')


class LoginPageHandler:
    def GET(self):
        web.header('Cache-Control', 'no-cache, no-store, must-revalidate')
        web.header('Pragma', 'no-cache')
        params = web.input(next="/chat")
        next_path = _safe_next_path(getattr(params, "next", "/chat"))
        if _check_console_auth():
            raise web.seeother(next_path)
        file_path = os.path.join(os.path.dirname(__file__), 'login.html')
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()


class AuthCheckHandler:
    def GET(self):
        web.header('Content-Type', 'application/json; charset=utf-8')
        investment_admin = None
        try:
            investment_admin = _current_investment_admin()
        except Exception:
            investment_admin = None
        auth_required = _is_console_login_required()
        authenticated = _check_console_auth() if auth_required else True
        if not auth_required:
            return json.dumps({"status": "success", "auth_required": False, "authenticated": True, "investment_admin": _investment_admin_payload(investment_admin)}, ensure_ascii=False)
        if authenticated:
            return json.dumps({"status": "success", "auth_required": True, "authenticated": True, "investment_admin": _investment_admin_payload(investment_admin)}, ensure_ascii=False)
        return json.dumps({"status": "success", "auth_required": True, "authenticated": False, "investment_admin": None}, ensure_ascii=False)


class AuthLoginHandler:
    def POST(self):
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            data = json.loads(web.data())
        except Exception:
            return json.dumps({"status": "error", "message": "Invalid request"})
        username = str(data.get("username", "") or "").strip()
        password = data.get("password", "")
        try:
            from business.investment.auth_service import authenticate_admin, count_admin_users, create_admin_session

            if count_admin_users() > 0:
                admin = authenticate_admin(username, password)
                if admin is None:
                    logger.warning("[WebChannel] Invalid investment admin login attempt")
                    return json.dumps({"status": "error", "message": "Wrong username or password"})
                token = create_admin_session(admin)
                web.setcookie("cow_investment_session", token, expires=_session_expire_seconds(),
                              path="/", httponly=True, samesite="Lax")
                web.setcookie("cow_auth_token", _create_auth_token(), expires=_session_expire_seconds(),
                              path="/", httponly=True, samesite="Lax")
                return json.dumps({"status": "success", "investment_admin": _investment_admin_payload(admin)}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[WebChannel] investment admin login error: {e}", exc_info=True)
            return json.dumps({"status": "error", "message": "Investment admin login failed"})
        if not _is_password_enabled():
            return json.dumps({"status": "success"})
        expected = conf().get("web_password", "")
        if not hmac.compare_digest(password, expected):
            logger.warning("[WebChannel] Invalid login attempt")
            return json.dumps({"status": "error", "message": "Wrong password"})
        token = _create_auth_token()
        web.setcookie("cow_auth_token", token, expires=_session_expire_seconds(),
                       path="/", httponly=True, samesite="Lax")
        return json.dumps({"status": "success"})


class AuthLogoutHandler:
    def POST(self):
        web.header('Content-Type', 'application/json; charset=utf-8')
        web.setcookie("cow_auth_token", "", expires=-1, path="/")
        web.setcookie("cow_investment_session", "", expires=-1, path="/")
        return json.dumps({"status": "success"})


class MessageHandler:
    def POST(self):
        _require_console_auth()
        return WebChannel().post_message()


class UploadHandler:
    def POST(self):
        _require_console_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        return WebChannel().upload_file()


class UploadsHandler:
    def GET(self, file_name):
        _require_console_auth()
        try:
            upload_dir = _get_upload_dir()
            full_path = os.path.normpath(os.path.join(upload_dir, file_name))
            if not os.path.abspath(full_path).startswith(os.path.abspath(upload_dir)):
                raise web.notfound()
            if not os.path.isfile(full_path):
                raise web.notfound()
            content_type = mimetypes.guess_type(full_path)[0] or "application/octet-stream"
            web.header('Content-Type', content_type)
            web.header('Cache-Control', 'public, max-age=86400')
            with open(full_path, 'rb') as f:
                return f.read()
        except web.HTTPError:
            raise
        except Exception as e:
            logger.error(f"[WebChannel] Error serving upload: {e}")
            raise web.notfound()


def _is_path_under(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(root)]) == os.path.abspath(root)
    except ValueError:
        return False


def _allowed_file_roots():
    roots = [_get_upload_dir()]
    try:
        from business.investment.storage import get_storage_dirs

        roots.append(str(get_storage_dirs()["root"]))
    except Exception as exc:
        logger.debug("[WebChannel] investment storage root unavailable: {}".format(exc))
    return roots


def _is_allowed_file_path(file_path: str) -> bool:
    return any(_is_path_under(file_path, root) for root in _allowed_file_roots())


class FileServeHandler:
    def GET(self):
        _require_console_auth()
        try:
            params = web.input(path="")
            file_path = params.path
            if not file_path or not os.path.isabs(file_path):
                raise web.notfound()
            file_path = os.path.normpath(file_path)
            if not os.path.isfile(file_path):
                raise web.notfound()
            if not _is_allowed_file_path(file_path):
                raise web.notfound()
            content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
            file_name = os.path.basename(file_path)
            from urllib.parse import quote
            web.header('Content-Type', content_type)
            web.header('Content-Disposition', f"inline; filename*=UTF-8''{quote(file_name)}")
            web.header('Cache-Control', 'public, max-age=3600')
            with open(file_path, 'rb') as f:
                return f.read()
        except web.HTTPError:
            raise
        except Exception as e:
            logger.error(f"[WebChannel] Error serving file: {e}")
            raise web.notfound()


class PollHandler:
    def POST(self):
        _require_console_auth()
        return WebChannel().poll_response()


class StreamHandler:
    def GET(self):
        _require_console_auth()
        params = web.input(request_id='')
        request_id = params.request_id
        if not request_id:
            raise web.badrequest()

        web.header('Content-Type', 'text/event-stream; charset=utf-8')
        web.header('Cache-Control', 'no-cache')
        web.header('X-Accel-Buffering', 'no')
        web.header('Access-Control-Allow-Origin', '*')

        return WebChannel().stream_response(request_id)


class ChatHandler:
    def GET(self):
        if not _check_console_auth():
            raise web.seeother(_login_redirect_url(_current_request_path("/chat")))
        web.header('Cache-Control', 'no-cache, no-store, must-revalidate')
        web.header('Pragma', 'no-cache')
        file_path = os.path.join(os.path.dirname(__file__), 'chat.html')
        with open(file_path, 'r', encoding='utf-8') as f:
            html = f.read()
        cache_bust = str(int(time.time()))
        html = html.replace('assets/js/console.js', f'assets/js/console.js?v={cache_bust}')
        html = html.replace('assets/css/console.css', f'assets/css/console.css?v={cache_bust}')
        return html


class ConfigHandler:

    _RECOMMENDED_MODELS = [
        const.DEEPSEEK_V4_FLASH, const.DEEPSEEK_V4_PRO, const.DEEPSEEK_CHAT, const.DEEPSEEK_REASONER,
        const.MINIMAX_M2_7_HIGHSPEED, const.MINIMAX_M2_7, const.MINIMAX_M2_5, const.MINIMAX_M2_1, const.MINIMAX_M2_1_LIGHTNING,
        const.CLAUDE_4_6_SONNET, const.CLAUDE_4_7_OPUS, const.CLAUDE_4_6_OPUS, const.CLAUDE_4_5_SONNET,
        const.GEMINI_31_FLASH_LITE_PRE, const.GEMINI_31_PRO_PRE, const.GEMINI_3_FLASH_PRE,
        const.GPT_54, const.GPT_54_MINI, const.GPT_54_NANO, const.GPT_5, const.GPT_41, const.GPT_4o,
        const.GLM_5_1, const.GLM_5_TURBO, const.GLM_5, const.GLM_4_7,
        const.QWEN36_PLUS, const.QWEN35_PLUS, const.QWEN3_MAX,
        const.DOUBAO_SEED_2_PRO, const.DOUBAO_SEED_2_CODE,
        const.KIMI_K2_6, const.KIMI_K2_5, const.KIMI_K2,
        const.ERNIE_5_1, const.ERNIE_5, const.ERNIE_X1_1, const.ERNIE_45_TURBO_128K, const.ERNIE_45_TURBO_32K,
    ]

    # Generic placeholder hints surfaced in the web console. We deliberately
    # show the version-path tail (e.g. "/v1") so users are reminded to type
    # the full base URL. The form is intentionally vague (`...../v1`) so it
    # never looks like a real default a user might paste verbatim — and we
    # never auto-rewrite anything on the server side.
    _PLACEHOLDER_V1 = "https://...../v1"
    _PLACEHOLDER_QIANFAN = "https://...../v2"
    _PLACEHOLDER_ZHIPU = "https://...../api/paas/v4"
    _PLACEHOLDER_DOUBAO = "https://...../api/v3"
    _PLACEHOLDER_GEMINI = "https://....."

    PROVIDER_MODELS = OrderedDict([
        ("deepseek", {
            "label": "DeepSeek",
            "api_key_field": "deepseek_api_key",
            "api_base_key": "deepseek_api_base",
            "api_base_default": "https://api.deepseek.com/v1",
            "api_base_placeholder": _PLACEHOLDER_V1,
            "models": [const.DEEPSEEK_V4_FLASH, const.DEEPSEEK_V4_PRO, const.DEEPSEEK_CHAT, const.DEEPSEEK_REASONER],
        }),
        ("minimax", {
            "label": "MiniMax",
            "api_key_field": "minimax_api_key",
            "api_base_key": None,
            "api_base_default": None,
            "api_base_placeholder": "",
            "models": [const.MINIMAX_M2_7, const.MINIMAX_M2_7_HIGHSPEED, const.MINIMAX_M2_5, const.MINIMAX_M2_1, const.MINIMAX_M2_1_LIGHTNING],
        }),
        ("claudeAPI", {
            "label": "Claude",
            "api_key_field": "claude_api_key",
            "api_base_key": "claude_api_base",
            "api_base_default": "https://api.anthropic.com/v1",
            "api_base_placeholder": _PLACEHOLDER_V1,
            "models": [const.CLAUDE_4_6_SONNET, const.CLAUDE_4_7_OPUS, const.CLAUDE_4_6_OPUS, const.CLAUDE_4_5_SONNET],
        }),
        ("gemini", {
            "label": "Gemini",
            "api_key_field": "gemini_api_key",
            "api_base_key": "gemini_api_base",
            "api_base_default": "https://generativelanguage.googleapis.com",
            "api_base_placeholder": _PLACEHOLDER_GEMINI,
            "models": [const.GEMINI_31_FLASH_LITE_PRE, const.GEMINI_31_PRO_PRE, const.GEMINI_3_FLASH_PRE],
        }),
        ("openai", {
            "label": "OpenAI",
            "api_key_field": "open_ai_api_key",
            "api_base_key": "open_ai_api_base",
            "api_base_default": "https://api.openai.com/v1",
            "api_base_placeholder": _PLACEHOLDER_V1,
            "models": [const.GPT_54, const.GPT_54_MINI, const.GPT_54_NANO, const.GPT_5, const.GPT_41, const.GPT_4o],
        }),
        ("zhipu", {
            "label": "智谱AI",
            "api_key_field": "zhipu_ai_api_key",
            "api_base_key": "zhipu_ai_api_base",
            "api_base_default": "https://open.bigmodel.cn/api/paas/v4",
            "api_base_placeholder": _PLACEHOLDER_ZHIPU,
            "models": [const.GLM_5_1, const.GLM_5_TURBO, const.GLM_5, const.GLM_4_7],
        }),
        ("dashscope", {
            "label": "通义千问",
            "api_key_field": "dashscope_api_key",
            "api_base_key": None,
            "api_base_default": None,
            "api_base_placeholder": "",
            "models": [const.QWEN36_PLUS, const.QWEN35_PLUS, const.QWEN3_MAX],
        }),
        ("doubao", {
            "label": "豆包",
            "api_key_field": "ark_api_key",
            "api_base_key": "ark_base_url",
            "api_base_default": "https://ark.cn-beijing.volces.com/api/v3",
            "api_base_placeholder": _PLACEHOLDER_DOUBAO,
            "models": [const.DOUBAO_SEED_2_PRO, const.DOUBAO_SEED_2_CODE],
        }),
        ("moonshot", {
            "label": "Kimi",
            "api_key_field": "moonshot_api_key",
            "api_base_key": "moonshot_base_url",
            "api_base_default": "https://api.moonshot.cn/v1",
            "api_base_placeholder": _PLACEHOLDER_V1,
            "models": [const.KIMI_K2_6, const.KIMI_K2_5, const.KIMI_K2],
        }),
        ("qianfan", {
            "label": "百度千帆",
            "api_key_field": "qianfan_api_key",
            "api_base_key": "qianfan_api_base",
            "api_base_default": "https://qianfan.baidubce.com/v2",
            "api_base_placeholder": _PLACEHOLDER_QIANFAN,
            "models": [const.ERNIE_5_1, const.ERNIE_5, const.ERNIE_X1_1, const.ERNIE_45_TURBO_128K, const.ERNIE_45_TURBO_32K],
        }),
        ("modelscope", {
            "label": "ModelScope",
            "api_key_field": "modelscope_api_key",
            "api_base_key": None,
            "api_base_default": None,
            "api_base_placeholder": "",
            "models": [const.QWEN3_5_27B, const.QWEN3_235B_A22B_INSTRUCT_2507],
        }),
        ("linkai", {
            "label": "LinkAI",
            "api_key_field": "linkai_api_key",
            "api_base_key": None,
            "api_base_default": None,
            "api_base_placeholder": "",
            "models": _RECOMMENDED_MODELS,
        }),
        ("custom", {
            "label": "自定义",
            "api_key_field": "custom_api_key",
            "api_base_key": "custom_api_base",
            "api_base_default": "",
            "api_base_placeholder": _PLACEHOLDER_V1,
            "models": [],
        }),
    ])

    EDITABLE_KEYS = {
        "model", "bot_type", "use_linkai",
        "open_ai_api_base", "deepseek_api_base", "qianfan_api_base", "claude_api_base", "gemini_api_base",
        "zhipu_ai_api_base", "moonshot_base_url", "ark_base_url", "custom_api_base",
        "open_ai_api_key", "deepseek_api_key", "qianfan_api_key", "claude_api_key", "gemini_api_key",
        "zhipu_ai_api_key", "dashscope_api_key", "moonshot_api_key",
        "ark_api_key", "minimax_api_key", "linkai_api_key", "custom_api_key",
        "agent_max_context_tokens", "agent_max_context_turns", "agent_max_steps",
        "enable_thinking", "web_password",
    }

    @staticmethod
    def _mask_key(value: str) -> str:
        """Mask the middle part of an API key for display."""
        if not value or len(value) <= 8:
            return value
        return value[:4] + "*" * (len(value) - 8) + value[-4:]

    def GET(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            local_config = conf()
            use_agent = local_config.get("agent", True)
            title = "CowAgent" if use_agent else "AI Assistant"

            api_bases = {}
            api_keys_masked = {}
            for pid, pinfo in self.PROVIDER_MODELS.items():
                base_key = pinfo.get("api_base_key")
                if base_key:
                    api_bases[base_key] = local_config.get(base_key, pinfo["api_base_default"])
                key_field = pinfo.get("api_key_field")
                if key_field and key_field not in api_keys_masked:
                    raw = local_config.get(key_field, "")
                    api_keys_masked[key_field] = self._mask_key(raw) if raw else ""

            providers = {}
            for pid, p in self.PROVIDER_MODELS.items():
                providers[pid] = {
                    "label": p["label"],
                    "models": p["models"],
                    "api_base_key": p["api_base_key"],
                    "api_base_default": p["api_base_default"],
                    "api_base_placeholder": p.get("api_base_placeholder", ""),
                    "api_key_field": p.get("api_key_field"),
                }

            raw_pwd = local_config.get("web_password", "")
            masked_pwd = ("*" * len(raw_pwd)) if raw_pwd else ""

            return json.dumps({
                "status": "success",
                "use_agent": use_agent,
                "title": title,
                "model": local_config.get("model", ""),
                "bot_type": "openai" if local_config.get("bot_type") == "chatGPT" else local_config.get("bot_type", ""),
                "use_linkai": bool(local_config.get("use_linkai", False)),
                "channel_type": local_config.get("channel_type", ""),
                "agent_max_context_tokens": local_config.get("agent_max_context_tokens", 50000),
                "agent_max_context_turns": local_config.get("agent_max_context_turns", 20),
                "agent_max_steps": local_config.get("agent_max_steps", 20),
                "enable_thinking": bool(local_config.get("enable_thinking", False)),
                "api_bases": api_bases,
                "api_keys": api_keys_masked,
                "providers": providers,
                "web_password_masked": masked_pwd,
            }, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error getting config: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    def POST(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            data = json.loads(web.data())
            updates = data.get("updates", {})
            if not updates:
                return json.dumps({"status": "error", "message": "no updates provided"})

            local_config = conf()
            applied = {}
            for key, value in updates.items():
                if key not in self.EDITABLE_KEYS:
                    continue
                if key in ("agent_max_context_tokens", "agent_max_context_turns", "agent_max_steps"):
                    value = int(value)
                if key in ("use_linkai", "enable_thinking"):
                    value = bool(value)
                local_config[key] = value
                applied[key] = value

            if not applied:
                return json.dumps({"status": "error", "message": "no valid keys to update"})

            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    file_cfg = json.load(f)
            else:
                file_cfg = {}
            file_cfg.update(applied)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(file_cfg, f, indent=4, ensure_ascii=False)

            logger.info(f"[WebChannel] Config updated: {list(applied.keys())}")

            # Reset Bridge so that bot routing reflects the new config.
            # Without this, Bridge keeps its cached bot instance (e.g. LinkAIBot)
            # even after the user switches bot_type / use_linkai / model in UI.
            bridge_routing_keys = {"bot_type", "use_linkai", "model"}
            if any(k in applied for k in bridge_routing_keys):
                try:
                    from bridge.bridge import Bridge
                    Bridge().reset_bot()
                    logger.info("[WebChannel] Bridge bot routing reset due to config change")
                except Exception as reset_err:
                    logger.warning(f"[WebChannel] Failed to reset bridge: {reset_err}")

            return json.dumps({"status": "success", "applied": applied}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error updating config: {e}")
            return json.dumps({"status": "error", "message": str(e)})


class ChannelsHandler:
    """API for managing external channel configurations (feishu, dingtalk, etc)."""

    CHANNEL_DEFS = OrderedDict([
        ("weixin", {
            "label": {"zh": "微信", "en": "WeChat"},
            "icon": "fa-comment",
            "color": "emerald",
            "fields": [],
        }),
        ("feishu", {
            "label": {"zh": "飞书", "en": "Feishu"},
            "icon": "fa-paper-plane",
            "color": "blue",
            "fields": [
                {"key": "feishu_app_id", "label": "App ID", "type": "text"},
                {"key": "feishu_app_secret", "label": "App Secret", "type": "secret"},
            ],
        }),
        ("dingtalk", {
            "label": {"zh": "钉钉", "en": "DingTalk"},
            "icon": "fa-comments",
            "color": "blue",
            "fields": [
                {"key": "dingtalk_client_id", "label": "Client ID", "type": "text"},
                {"key": "dingtalk_client_secret", "label": "Client Secret", "type": "secret"},
            ],
        }),
        ("wecom_bot", {
            "label": {"zh": "企微智能机器人", "en": "WeCom Bot"},
            "icon": "fa-robot",
            "color": "emerald",
            "fields": [
                {"key": "wecom_bot_id", "label": "Bot ID", "type": "text"},
                {"key": "wecom_bot_secret", "label": "Secret", "type": "secret"},
            ],
        }),
        ("qq", {
            "label": {"zh": "QQ 机器人", "en": "QQ Bot"},
            "icon": "fa-comment",
            "color": "blue",
            "fields": [
                {"key": "qq_app_id", "label": "App ID", "type": "text"},
                {"key": "qq_app_secret", "label": "App Secret", "type": "secret"},
            ],
        }),
        ("wechatcom_app", {
            "label": {"zh": "企微自建应用", "en": "WeCom App"},
            "icon": "fa-building",
            "color": "emerald",
            "fields": [
                {"key": "wechatcom_corp_id", "label": "Corp ID", "type": "text"},
                {"key": "wechatcomapp_agent_id", "label": "Agent ID", "type": "text"},
                {"key": "wechatcomapp_secret", "label": "Secret", "type": "secret"},
                {"key": "wechatcomapp_token", "label": "Token", "type": "secret"},
                {"key": "wechatcomapp_aes_key", "label": "AES Key", "type": "secret"},
                {"key": "wechatcomapp_port", "label": "Port", "type": "number", "default": 9898},
            ],
        }),
        ("wechatmp", {
            "label": {"zh": "公众号", "en": "WeChat MP"},
            "icon": "fa-comment-dots",
            "color": "emerald",
            "fields": [
                {"key": "wechatmp_app_id", "label": "App ID", "type": "text"},
                {"key": "wechatmp_app_secret", "label": "App Secret", "type": "secret"},
                {"key": "wechatmp_token", "label": "Token", "type": "secret"},
                {"key": "wechatmp_aes_key", "label": "AES Key", "type": "secret"},
                {"key": "wechatmp_port", "label": "Port", "type": "number", "default": 8080},
            ],
        }),
    ])

    @staticmethod
    def _get_weixin_login_status() -> str:
        try:
            import sys
            app_module = sys.modules.get('__main__') or sys.modules.get('app')
            mgr = getattr(app_module, '_channel_mgr', None) if app_module else None
            if mgr:
                ch = mgr.get_channel("weixin")
                if ch and hasattr(ch, 'login_status'):
                    return ch.login_status
        except Exception:
            pass
        return "unknown"

    @staticmethod
    def _mask_secret(value: str) -> str:
        if not value or len(value) <= 8:
            return value
        return value[:4] + "*" * (len(value) - 8) + value[-4:]

    @staticmethod
    def _parse_channel_list(raw) -> list:
        if isinstance(raw, list):
            return [ch.strip() for ch in raw if ch.strip()]
        if isinstance(raw, str):
            return [ch.strip() for ch in raw.split(",") if ch.strip()]
        return []

    @classmethod
    def _active_channel_set(cls) -> set:
        return set(cls._parse_channel_list(conf().get("channel_type", "")))

    def GET(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            local_config = conf()
            active_channels = self._active_channel_set()
            channels = []
            for ch_name, ch_def in self.CHANNEL_DEFS.items():
                fields_out = []
                for f in ch_def["fields"]:
                    raw_val = local_config.get(f["key"], f.get("default", ""))
                    if f["type"] == "secret" and raw_val:
                        display_val = self._mask_secret(str(raw_val))
                    else:
                        display_val = raw_val
                    fields_out.append({
                        "key": f["key"],
                        "label": f["label"],
                        "type": f["type"],
                        "value": display_val,
                        "default": f.get("default", ""),
                    })
                ch_info = {
                    "name": ch_name,
                    "label": ch_def["label"],
                    "icon": ch_def["icon"],
                    "color": ch_def["color"],
                    "active": ch_name in active_channels,
                    "fields": fields_out,
                }
                if ch_name == "weixin" and ch_name in active_channels:
                    ch_info["login_status"] = self._get_weixin_login_status()
                channels.append(ch_info)
            return json.dumps({"status": "success", "channels": channels}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[WebChannel] Channels API error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    def POST(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            body = json.loads(web.data())
            action = body.get("action")
            channel_name = body.get("channel")

            if not action or not channel_name:
                return json.dumps({"status": "error", "message": "action and channel required"})

            if channel_name not in self.CHANNEL_DEFS:
                return json.dumps({"status": "error", "message": f"unknown channel: {channel_name}"})

            if action == "save":
                return self._handle_save(channel_name, body.get("config", {}))
            elif action == "connect":
                return self._handle_connect(channel_name, body.get("config", {}))
            elif action == "disconnect":
                return self._handle_disconnect(channel_name)
            else:
                return json.dumps({"status": "error", "message": f"unknown action: {action}"})
        except Exception as e:
            logger.error(f"[WebChannel] Channels POST error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    def _handle_save(self, channel_name: str, updates: dict):
        ch_def = self.CHANNEL_DEFS[channel_name]
        valid_keys = {f["key"] for f in ch_def["fields"]}
        secret_keys = {f["key"] for f in ch_def["fields"] if f["type"] == "secret"}

        local_config = conf()
        applied = {}
        for key, value in updates.items():
            if key not in valid_keys:
                continue
            if key in secret_keys:
                if not value or (len(value) > 8 and "*" * 4 in value):
                    continue
            field_def = next((f for f in ch_def["fields"] if f["key"] == key), None)
            if field_def:
                if field_def["type"] == "number":
                    value = int(value)
                elif field_def["type"] == "bool":
                    value = bool(value)
            local_config[key] = value
            applied[key] = value

        if not applied:
            return json.dumps({"status": "error", "message": "no valid fields to update"})

        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "config.json")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                file_cfg = json.load(f)
        else:
            file_cfg = {}
        file_cfg.update(applied)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(file_cfg, f, indent=4, ensure_ascii=False)

        logger.info(f"[WebChannel] Channel '{channel_name}' config updated: {list(applied.keys())}")

        should_restart = False
        active_channels = self._active_channel_set()
        if channel_name in active_channels:
            should_restart = True
            try:
                import sys
                app_module = sys.modules.get('__main__') or sys.modules.get('app')
                mgr = getattr(app_module, '_channel_mgr', None) if app_module else None
                if mgr:
                    threading.Thread(
                        target=mgr.restart,
                        args=(channel_name,),
                        daemon=True,
                    ).start()
                    logger.info(f"[WebChannel] Channel '{channel_name}' restart triggered")
            except Exception as e:
                logger.warning(f"[WebChannel] Failed to restart channel '{channel_name}': {e}")

        return json.dumps({
            "status": "success",
            "applied": list(applied.keys()),
            "restarted": should_restart,
        }, ensure_ascii=False)

    def _handle_connect(self, channel_name: str, updates: dict):
        """Save config fields, add channel to channel_type, and start it."""
        ch_def = self.CHANNEL_DEFS[channel_name]
        valid_keys = {f["key"] for f in ch_def["fields"]}
        secret_keys = {f["key"] for f in ch_def["fields"] if f["type"] == "secret"}

        # Feishu connected via web console must use websocket (long connection) mode
        if channel_name == "feishu":
            updates.setdefault("feishu_event_mode", "websocket")
            valid_keys.add("feishu_event_mode")

        local_config = conf()
        applied = {}
        for key, value in updates.items():
            if key not in valid_keys:
                continue
            if key in secret_keys:
                if not value or (len(value) > 8 and "*" * 4 in value):
                    continue
            field_def = next((f for f in ch_def["fields"] if f["key"] == key), None)
            if field_def:
                if field_def["type"] == "number":
                    value = int(value)
                elif field_def["type"] == "bool":
                    value = bool(value)
            local_config[key] = value
            applied[key] = value

        existing = self._parse_channel_list(conf().get("channel_type", ""))
        if channel_name not in existing:
            existing.append(channel_name)
        new_channel_type = ",".join(existing)
        local_config["channel_type"] = new_channel_type

        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "config.json")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                file_cfg = json.load(f)
        else:
            file_cfg = {}
        file_cfg.update(applied)
        file_cfg["channel_type"] = new_channel_type
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(file_cfg, f, indent=4, ensure_ascii=False)

        logger.info(f"[WebChannel] Channel '{channel_name}' connecting, channel_type={new_channel_type}")

        def _do_start():
            try:
                import sys
                app_module = sys.modules.get('__main__') or sys.modules.get('app')
                clear_fn = getattr(app_module, '_clear_singleton_cache', None) if app_module else None
                mgr = getattr(app_module, '_channel_mgr', None) if app_module else None
                if mgr is None:
                    logger.warning(f"[WebChannel] ChannelManager not available, cannot start '{channel_name}'")
                    return
                # Stop existing instance first if still running (e.g. re-connect without disconnect)
                existing_ch = mgr.get_channel(channel_name)
                if existing_ch is not None:
                    logger.info(f"[WebChannel] Stopping existing '{channel_name}' before reconnect...")
                    mgr.stop(channel_name)
                # Always wait for the remote service to release the old connection before
                # establishing a new one (DingTalk drops callbacks on duplicate connections)
                logger.info(f"[WebChannel] Waiting for '{channel_name}' old connection to close...")
                time.sleep(5)
                if clear_fn:
                    clear_fn(channel_name)
                logger.info(f"[WebChannel] Starting channel '{channel_name}'...")
                mgr.start([channel_name], first_start=False)
                logger.info(f"[WebChannel] Channel '{channel_name}' start completed")
            except Exception as e:
                logger.error(f"[WebChannel] Failed to start channel '{channel_name}': {e}",
                             exc_info=True)

        threading.Thread(target=_do_start, daemon=True).start()

        return json.dumps({
            "status": "success",
            "channel_type": new_channel_type,
        }, ensure_ascii=False)

    def _handle_disconnect(self, channel_name: str):
        existing = self._parse_channel_list(conf().get("channel_type", ""))
        existing = [ch for ch in existing if ch != channel_name]
        new_channel_type = ",".join(existing)

        local_config = conf()
        local_config["channel_type"] = new_channel_type

        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "config.json")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                file_cfg = json.load(f)
        else:
            file_cfg = {}
        file_cfg["channel_type"] = new_channel_type
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(file_cfg, f, indent=4, ensure_ascii=False)

        def _do_stop():
            try:
                import sys
                app_module = sys.modules.get('__main__') or sys.modules.get('app')
                mgr = getattr(app_module, '_channel_mgr', None) if app_module else None
                clear_fn = getattr(app_module, '_clear_singleton_cache', None) if app_module else None
                if mgr:
                    mgr.stop(channel_name)
                else:
                    logger.warning(f"[WebChannel] ChannelManager not found, cannot stop '{channel_name}'")
                if clear_fn:
                    clear_fn(channel_name)
                logger.info(f"[WebChannel] Channel '{channel_name}' disconnected, "
                            f"channel_type={new_channel_type}")
            except Exception as e:
                logger.warning(f"[WebChannel] Failed to stop channel '{channel_name}': {e}",
                               exc_info=True)

        threading.Thread(target=_do_stop, daemon=True).start()

        return json.dumps({
            "status": "success",
            "channel_type": new_channel_type,
        }, ensure_ascii=False)


class WeixinQrHandler:
    """Handle WeChat QR code login from the web console.

    GET  /api/weixin/qrlogin          → fetch a new QR code
    POST /api/weixin/qrlogin          → poll QR status or start channel after login
    """

    _qr_state = {}

    @staticmethod
    def _qr_to_data_uri(data: str) -> str:
        """Generate a QR code as a PNG data URI."""
        try:
            import qrcode as qr_lib
            import io
            import base64
            qr = qr_lib.QRCode(error_correction=qr_lib.constants.ERROR_CORRECT_L, box_size=6, border=2)
            qr.add_data(data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/png;base64,{b64}"
        except ImportError:
            return ""

    @staticmethod
    def _get_running_channel():
        try:
            import sys
            app_module = sys.modules.get('__main__') or sys.modules.get('app')
            mgr = getattr(app_module, '_channel_mgr', None) if app_module else None
            if mgr:
                return mgr.get_channel("weixin")
        except Exception:
            pass
        return None

    def GET(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            running_ch = self._get_running_channel()
            if running_ch and hasattr(running_ch, '_current_qr_url') and running_ch._current_qr_url:
                qr_image = self._qr_to_data_uri(running_ch._current_qr_url)
                return json.dumps({
                    "status": "success",
                    "qrcode_url": running_ch._current_qr_url,
                    "qr_image": qr_image,
                    "source": "channel",
                })

            from channel.weixin.weixin_api import WeixinApi, DEFAULT_BASE_URL
            base_url = conf().get("weixin_base_url", DEFAULT_BASE_URL)
            api = WeixinApi(base_url=base_url)
            qr_resp = api.fetch_qr_code()
            qrcode = qr_resp.get("qrcode", "")
            qrcode_url = qr_resp.get("qrcode_img_content", "")
            if not qrcode:
                return json.dumps({"status": "error", "message": "No QR code returned"})
            qr_image = self._qr_to_data_uri(qrcode_url)
            WeixinQrHandler._qr_state = {
                "qrcode": qrcode,
                "qrcode_url": qrcode_url,
                "base_url": base_url,
            }
            return json.dumps({"status": "success", "qrcode_url": qrcode_url, "qr_image": qr_image})
        except Exception as e:
            logger.error(f"[WebChannel] WeixinQr GET error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    def POST(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            body = json.loads(web.data())
            action = body.get("action", "poll")

            if action == "poll":
                return self._poll_status()
            elif action == "refresh":
                return self.GET()
            else:
                return json.dumps({"status": "error", "message": f"unknown action: {action}"})
        except Exception as e:
            logger.error(f"[WebChannel] WeixinQr POST error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    def _poll_status(self):
        state = WeixinQrHandler._qr_state
        qrcode = state.get("qrcode", "")
        base_url = state.get("base_url", "")
        if not qrcode:
            return json.dumps({"status": "error", "message": "No active QR session"})

        from channel.weixin.weixin_api import WeixinApi, DEFAULT_BASE_URL
        api = WeixinApi(base_url=base_url or DEFAULT_BASE_URL)
        try:
            status_resp = api.poll_qr_status(qrcode, timeout=10)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

        qr_status = status_resp.get("status", "wait")

        if qr_status == "confirmed":
            bot_token = status_resp.get("bot_token", "")
            bot_id = status_resp.get("ilink_bot_id", "")
            result_base_url = status_resp.get("baseurl", base_url)
            user_id = status_resp.get("ilink_user_id", "")

            if not bot_token or not bot_id:
                return json.dumps({"status": "error", "message": "Login confirmed but missing token"})

            cred_path = os.path.expanduser(
                conf().get("weixin_credentials_path", "~/.weixin_cow_credentials.json")
            )
            from channel.weixin.weixin_channel import _save_credentials
            _save_credentials(cred_path, {
                "token": bot_token,
                "base_url": result_base_url,
                "bot_id": bot_id,
                "user_id": user_id,
            })
            conf()["weixin_token"] = bot_token
            conf()["weixin_base_url"] = result_base_url

            WeixinQrHandler._qr_state = {}
            logger.info(f"[WebChannel] WeChat QR login confirmed: bot_id={bot_id}")

            return json.dumps({
                "status": "success",
                "qr_status": "confirmed",
                "bot_id": bot_id,
            })

        if qr_status == "expired":
            new_resp = api.fetch_qr_code()
            new_qrcode = new_resp.get("qrcode", "")
            new_qrcode_url = new_resp.get("qrcode_img_content", "")
            new_qr_image = self._qr_to_data_uri(new_qrcode_url)
            WeixinQrHandler._qr_state["qrcode"] = new_qrcode
            WeixinQrHandler._qr_state["qrcode_url"] = new_qrcode_url
            return json.dumps({
                "status": "success",
                "qr_status": "expired",
                "qrcode_url": new_qrcode_url,
                "qr_image": new_qr_image,
            })

        return json.dumps({"status": "success", "qr_status": qr_status})


class FeishuRegisterHandler:
    """飞书智能体应用一键创建（OAuth 设备授权流，基于 lark.register_app SDK）。

    GET  /api/feishu/register   → 启动注册：调用 SDK 生成二维码 URL，立即返回；
                                   后台线程继续轮询飞书侧直到用户扫码授权。
    POST /api/feishu/register   → 轮询当前会话状态（pending / done / error / expired）。
                                   注册成功后不直接写 config，由前端再调
                                   /api/channels {action:'connect'} 走标准启用流程。
    """

    # 进程内单例状态（{url, expire_in, status, app_id, app_secret, error, thread}）。
    # 简单的本地自部署场景下不需要 session 隔离。
    _state = {}
    _lock = threading.Lock()

    @staticmethod
    def _qr_to_data_uri(data: str) -> str:
        """复用 WeixinQrHandler 的二维码渲染。"""
        return WeixinQrHandler._qr_to_data_uri(data)

    @classmethod
    def _reset_state(cls):
        with cls._lock:
            cls._state = {}

    @classmethod
    def _start_register_thread(cls):
        """启动一次新的注册会话。如已有进行中的会话，先取消（通过 cancel_event）。"""
        # 先取消可能存在的上一次会话，避免两个 SDK 线程并发 poll 同一个端点
        with cls._lock:
            old_cancel = cls._state.get("cancel_event") if cls._state else None
            if old_cancel is not None:
                old_cancel.set()
            cancel_event = threading.Event()
            cls._state = {"status": "starting", "cancel_event": cancel_event}

        def _worker():
            try:
                import lark_oapi as lark
            except ImportError:
                with cls._lock:
                    cls._state["status"] = "error"
                    cls._state["error"] = "lark-oapi SDK 未安装，请执行 pip install -U lark-oapi"
                return

            def _on_qr(info):
                # SDK 拿到二维码 URL 后立即回调；写入 state 让前端 GET 立刻能拿到
                with cls._lock:
                    cls._state["url"] = info.get("url", "")
                    cls._state["expire_in"] = info.get("expire_in", 600)
                    cls._state["qr_image"] = cls._qr_to_data_uri(info.get("url", ""))
                    cls._state["status"] = "pending"
                logger.info(f"[FeishuRegister] QR ready, expire_in={info.get('expire_in')}s")

            def _on_status(info):
                # 过滤掉 polling 心跳（每 5 秒一次，纯噪音）；
                # 保留 slow_down / domain_switched 等真正的状态切换事件
                status = info.get("status")
                if status == "polling":
                    return
                logger.info(f"[FeishuRegister] SDK status: {info}")

            try:
                result = lark.register_app(
                    on_qr_code=_on_qr,
                    on_status_change=_on_status,
                    source="cowagent",
                    cancel_event=cancel_event,
                )
                with cls._lock:
                    cls._state["status"] = "done"
                    cls._state["app_id"] = result.get("client_id", "")
                    cls._state["app_secret"] = result.get("client_secret", "")
                logger.info(f"[FeishuRegister] App created: app_id={result.get('client_id')}")
            except Exception as e:
                err_msg = str(e)
                err_cls = e.__class__.__name__
                # 飞书 SDK 抛出的 AppExpiredError / AppAccessDeniedError / RegisterAppError
                if "Expired" in err_cls:
                    status = "expired"
                elif "Denied" in err_cls:
                    status = "denied"
                elif "abort" in err_msg.lower() or "cancel" in err_msg.lower():
                    # 被新一轮注册抢占，保持安静
                    return
                else:
                    status = "error"
                with cls._lock:
                    # 仅当当前 state 仍属于本次 worker 时才写入，避免覆盖更新的会话
                    if cls._state.get("cancel_event") is cancel_event:
                        cls._state["status"] = status
                        cls._state["error"] = err_msg
                logger.warning(f"[FeishuRegister] Register failed ({err_cls}): {err_msg}")

        threading.Thread(target=_worker, daemon=True, name="feishu-register").start()

    def GET(self):
        """启动一次新的注册会话。如果已有 pending/done 会话则覆盖。"""
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            self._start_register_thread()
            # 等待 SDK 拿到二维码 URL（最多 10s）。SDK 内部会马上回调 _on_qr。
            import time as _t
            for _ in range(100):
                with self._lock:
                    if self._state.get("url") or self._state.get("status") in ("error", "expired", "denied"):
                        break
                _t.sleep(0.1)
            with self._lock:
                if self._state.get("status") in ("error", "expired", "denied"):
                    return json.dumps({
                        "status": "error",
                        "message": self._state.get("error", "register failed"),
                    })
                if not self._state.get("url"):
                    return json.dumps({
                        "status": "error",
                        "message": "等待飞书二维码超时，请重试",
                    })
                return json.dumps({
                    "status": "success",
                    "qrcode_url": self._state["url"],
                    "qr_image": self._state.get("qr_image", ""),
                    "expire_in": self._state.get("expire_in", 600),
                })
        except Exception as e:
            logger.error(f"[WebChannel] FeishuRegister GET error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    def POST(self):
        """轮询注册结果。"""
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            body = json.loads(web.data() or b"{}")
            action = body.get("action", "poll")
            if action != "poll":
                return json.dumps({"status": "error", "message": f"unknown action: {action}"})

            with self._lock:
                status = self._state.get("status", "idle")
                if status == "done":
                    payload = {
                        "status": "success",
                        "register_status": "done",
                        "app_id": self._state.get("app_id", ""),
                        "app_secret": self._state.get("app_secret", ""),
                    }
                    # 一次性返回凭据后清掉，避免敏感信息长期驻留内存
                    self._state = {}
                    return json.dumps(payload)
                if status in ("error", "expired", "denied"):
                    return json.dumps({
                        "status": "success",
                        "register_status": status,
                        "message": self._state.get("error", ""),
                    })
                # pending / starting：还在等用户扫码
                return json.dumps({
                    "status": "success",
                    "register_status": "pending",
                })
        except Exception as e:
            logger.error(f"[WebChannel] FeishuRegister POST error: {e}")
            return json.dumps({"status": "error", "message": str(e)})


def _get_workspace_root():
    """Resolve the agent workspace directory."""
    from common.utils import expand_path
    return expand_path(conf().get("agent_workspace", "~/cow"))


class ToolsHandler:
    def GET(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            from agent.tools.tool_manager import ToolManager
            tm = ToolManager()
            if not tm.tool_classes:
                tm.load_tools()
            tools = []
            for name, cls in tm.tool_classes.items():
                try:
                    instance = cls()
                    tools.append({
                        "name": name,
                        "description": instance.description,
                    })
                except Exception:
                    tools.append({"name": name, "description": ""})
            return json.dumps({"status": "success", "tools": tools}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[WebChannel] Tools API error: {e}")
            return json.dumps({"status": "error", "message": str(e)})


class SkillsHandler:
    def GET(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            from agent.skills.service import SkillService
            from agent.skills.manager import SkillManager
            workspace_root = _get_workspace_root()
            manager = SkillManager(custom_dir=os.path.join(workspace_root, "skills"))
            service = SkillService(manager)
            skills = service.query()
            return json.dumps({"status": "success", "skills": skills}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[WebChannel] Skills API error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    def POST(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            from agent.skills.service import SkillService
            from agent.skills.manager import SkillManager
            body = json.loads(web.data())
            action = body.get("action")
            name = body.get("name")
            if not action or not name:
                return json.dumps({"status": "error", "message": "action and name are required"})
            workspace_root = _get_workspace_root()
            manager = SkillManager(custom_dir=os.path.join(workspace_root, "skills"))
            service = SkillService(manager)
            if action == "open":
                service.open({"name": name})
            elif action == "close":
                service.close({"name": name})
            else:
                return json.dumps({"status": "error", "message": f"unknown action: {action}"})
            return json.dumps({"status": "success"}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[WebChannel] Skills POST error: {e}")
            return json.dumps({"status": "error", "message": str(e)})


class MemoryHandler:
    def GET(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            from agent.memory.service import MemoryService
            params = web.input(page='1', page_size='20', category='memory')
            workspace_root = _get_workspace_root()
            service = MemoryService(workspace_root)
            result = service.list_files(
                page=int(params.page), page_size=int(params.page_size),
                category=params.category,
            )
            return json.dumps({"status": "success", **result}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[WebChannel] Memory API error: {e}")
            return json.dumps({"status": "error", "message": str(e)})


class MemoryContentHandler:
    def GET(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            from agent.memory.service import MemoryService
            params = web.input(filename='', category='memory')
            if not params.filename:
                return json.dumps({"status": "error", "message": "filename required"})
            workspace_root = _get_workspace_root()
            service = MemoryService(workspace_root)
            result = service.get_content(params.filename, category=params.category)
            return json.dumps({"status": "success", **result}, ensure_ascii=False)
        except ValueError:
            return json.dumps({"status": "error", "message": "invalid filename"})
        except FileNotFoundError:
            return json.dumps({"status": "error", "message": "file not found"})
        except Exception as e:
            logger.error(f"[WebChannel] Memory content API error: {e}")
            return json.dumps({"status": "error", "message": str(e)})


class SchedulerHandler:
    def GET(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            from agent.tools.scheduler.task_store import TaskStore
            workspace_root = _get_workspace_root()
            store_path = os.path.join(workspace_root, "scheduler", "tasks.json")
            store = TaskStore(store_path)
            tasks = store.list_tasks()
            return json.dumps({"status": "success", "tasks": tasks}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[WebChannel] Scheduler API error: {e}")
            return json.dumps({"status": "error", "message": str(e)})


class SessionsHandler:
    def GET(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            params = web.input(page='1', page_size='50')
            from agent.memory import get_conversation_store
            store = get_conversation_store()
            result = store.list_sessions(
                channel_type="web",
                page=int(params.page),
                page_size=int(params.page_size),
            )
            return json.dumps({"status": "success", **result}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[WebChannel] Sessions API error: {e}")
            return json.dumps({"status": "error", "message": str(e)})


class SessionDetailHandler:
    def DELETE(self, session_id: str):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        logger.info(f"[WebChannel] DELETE session request: {session_id}")
        try:
            if not session_id:
                return json.dumps({"status": "error", "message": "session_id required"})

            from agent.memory import get_conversation_store
            store = get_conversation_store()
            store.clear_session(session_id)

            # Also remove the Agent instance from AgentBridge if exists
            try:
                from bridge.bridge import Bridge
                ab = Bridge().get_agent_bridge()
                if session_id in ab.agents:
                    del ab.agents[session_id]
                    logger.info(f"[WebChannel] Removed agent instance for session {session_id}")
            except Exception:
                pass

            channel = WebChannel()
            channel.session_queues.pop(session_id, None)

            logger.info(f"[WebChannel] Session deleted: {session_id}")
            return json.dumps({"status": "success"})
        except Exception as e:
            logger.error(f"[WebChannel] Session delete error: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    def PUT(self, session_id: str):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            if not session_id:
                return json.dumps({"status": "error", "message": "session_id required"})
            body = json.loads(web.data())
            title = body.get("title", "").strip()
            if not title:
                return json.dumps({"status": "error", "message": "title required"})

            from agent.memory import get_conversation_store
            store = get_conversation_store()
            found = store.rename_session(session_id, title)
            if not found:
                return json.dumps({"status": "error", "message": "session not found"})
            return json.dumps({"status": "success"})
        except Exception as e:
            logger.error(f"[WebChannel] Session rename error: {e}")
            return json.dumps({"status": "error", "message": str(e)})


class SessionTitleHandler:
    def POST(self, session_id: str):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            if not session_id:
                return json.dumps({"status": "error", "message": "session_id required"})

            body = json.loads(web.data())
            user_message = body.get("user_message", "")
            assistant_reply = body.get("assistant_reply", "")
            if not user_message:
                return json.dumps({"status": "error", "message": "user_message required"})

            title = _generate_session_title(user_message, assistant_reply)

            from agent.memory import get_conversation_store
            store = get_conversation_store()
            updated = store.rename_session(session_id, title)
            logger.info(f"[WebChannel] Session title set: sid={session_id}, title='{title}', db_updated={updated}")

            return json.dumps({"status": "success", "title": title}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[WebChannel] Title generation error: {e}")
            return json.dumps({"status": "error", "message": str(e)})


class SessionClearContextHandler:
    def POST(self, session_id: str):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            if not session_id:
                return json.dumps({"status": "error", "message": "session_id required"})

            from agent.memory import get_conversation_store
            store = get_conversation_store()
            new_seq = store.clear_context(session_id)

            # Delete the agent instance so a fresh one is created on the next message
            try:
                from bridge.bridge import Bridge
                bridge = Bridge()
                ab = bridge.get_agent_bridge()
                if session_id in ab.agents:
                    del ab.agents[session_id]
                    logger.info(f"[WebChannel] Cleared agent instance for session {session_id}")
            except Exception:
                pass

            return json.dumps({"status": "success", "context_start_seq": new_seq})
        except Exception as e:
            logger.error(f"[WebChannel] Clear context error: {e}")
            return json.dumps({"status": "error", "message": str(e)})


class HistoryHandler:
    def GET(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        web.header('Access-Control-Allow-Origin', '*')
        try:
            params = web.input(session_id='', page='1', page_size='20')
            session_id = params.session_id.strip()
            if not session_id:
                return json.dumps({"status": "error", "message": "session_id required"})

            from agent.memory import get_conversation_store
            store = get_conversation_store()
            result = store.load_history_page(
                session_id=session_id,
                page=int(params.page),
                page_size=int(params.page_size),
            )
            return json.dumps({"status": "success", **result}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[WebChannel] History API error: {e}")
            return json.dumps({"status": "error", "message": str(e)})


class LogsHandler:
    def GET(self):
        _require_auth()
        web.header('Content-Type', 'text/event-stream; charset=utf-8')
        web.header('Cache-Control', 'no-cache')
        web.header('X-Accel-Buffering', 'no')

        from config import get_root
        log_path = os.path.join(get_root(), "run.log")

        def generate():
            if not os.path.isfile(log_path):
                yield b"data: {\"type\": \"error\", \"message\": \"run.log not found\"}\n\n"
                return

            # Read last 200 lines for initial display
            try:
                with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                    lines = f.readlines()
                tail_lines = lines[-200:]
                chunk = ''.join(tail_lines)
                payload = json.dumps({"type": "init", "content": chunk}, ensure_ascii=False)
                yield f"data: {payload}\n\n".encode('utf-8')
            except Exception as e:
                yield f"data: {{\"type\": \"error\", \"message\": \"{e}\"}}\n\n".encode('utf-8')
                return

            # Tail new lines
            try:
                with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                    f.seek(0, 2)  # seek to end
                    deadline = time.time() + 600  # 10 min max
                    while time.time() < deadline:
                        line = f.readline()
                        if line:
                            payload = json.dumps({"type": "line", "content": line}, ensure_ascii=False)
                            yield f"data: {payload}\n\n".encode('utf-8')
                        else:
                            yield b": keepalive\n\n"
                            time.sleep(1)
            except GeneratorExit:
                return
            except Exception:
                return

        return generate()


class AssetsHandler:
    def GET(self, file_path):  # 修改默认参数
        try:
            # 如果请求是/static/，需要处理
            if file_path == '':
                # 返回目录列表...
                pass

            # 获取当前文件的绝对路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            static_dir = os.path.join(current_dir, 'static')

            full_path = os.path.normpath(os.path.join(static_dir, file_path))

            # 安全检查：确保请求的文件在static目录内
            if not os.path.abspath(full_path).startswith(os.path.abspath(static_dir)):
                logger.error(f"Security check failed for path: {full_path}")
                raise web.notfound()

            if not os.path.exists(full_path) or not os.path.isfile(full_path):
                logger.error(f"File not found: {full_path}")
                raise web.notfound()

            # 设置正确的Content-Type
            content_type = mimetypes.guess_type(full_path)[0]
            if content_type:
                web.header('Content-Type', content_type)
            else:
                # 默认为二进制流
                web.header('Content-Type', 'application/octet-stream')

            # 读取并返回文件内容
            with open(full_path, 'rb') as f:
                return f.read()

        except Exception as e:
            logger.error(f"Error serving static file: {e}", exc_info=True)  # 添加更详细的错误信息
            raise web.notfound()


class KnowledgeListHandler:
    def GET(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            from agent.knowledge.service import KnowledgeService
            svc = KnowledgeService(_get_workspace_root())
            result = svc.list_tree()
            return json.dumps({"status": "success", **result}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[WebChannel] Knowledge list error: {e}")
            return json.dumps({"status": "error", "message": str(e)})


class KnowledgeReadHandler:
    def GET(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            from agent.knowledge.service import KnowledgeService
            params = web.input(path='')
            svc = KnowledgeService(_get_workspace_root())
            result = svc.read_file(params.path)
            return json.dumps({"status": "success", **result}, ensure_ascii=False)
        except (ValueError, FileNotFoundError) as e:
            return json.dumps({"status": "error", "message": str(e)})
        except Exception as e:
            logger.error(f"[WebChannel] Knowledge read error: {e}")
            return json.dumps({"status": "error", "message": str(e)})


class KnowledgeGraphHandler:
    def GET(self):
        _require_auth()
        web.header('Content-Type', 'application/json; charset=utf-8')
        try:
            from agent.knowledge.service import KnowledgeService
            svc = KnowledgeService(_get_workspace_root())
            return json.dumps(svc.build_graph(), ensure_ascii=False)
        except Exception as e:
            logger.error(f"[WebChannel] Knowledge graph error: {e}")
            return json.dumps({"nodes": [], "links": []})


class VersionHandler:
    def GET(self):
        web.header('Content-Type', 'application/json; charset=utf-8')
        from cli import __version__
        return json.dumps({"version": __version__})


def _investment_json_body():
    raw = web.data() or b"{}"
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _investment_is_multipart_request():
    content_type = getattr(web.ctx, "env", {}).get("CONTENT_TYPE", "")
    return str(content_type).lower().startswith("multipart/form-data")


def _investment_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _investment_safe_limit(value, default: int = 50, minimum: int = 1, maximum: int = 200) -> int:
    try:
        limit = int(str(value or "").strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, min(limit, maximum))


def _investment_safe_page(value, default: int = 1) -> int:
    try:
        page = int(str(value or "").strip())
    except (TypeError, ValueError):
        return default
    return max(1, page)


def _investment_safe_pagination(params, default_page_size: int) -> tuple[int, int]:
    page = _investment_safe_page(getattr(params, "page", "1"))
    page_size_value = getattr(params, "page_size", "")
    if page_size_value in (None, ""):
        page_size_value = getattr(params, "limit", "")
    page_size = _investment_safe_limit(page_size_value, default=default_page_size, minimum=1, maximum=200)
    return page, page_size


def _investment_pagination_payload(page: int, page_size: int, total: int) -> dict:
    total = max(0, int(total or 0))
    page_size = max(1, int(page_size or 1))
    return {
        "page": max(1, int(page or 1)),
        "page_size": page_size,
        "total": total,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


def _investment_json_response(payload):
    web.header('Content-Type', 'application/json; charset=utf-8')
    return json.dumps(payload, ensure_ascii=False)


def _investment_xlsx_response(data: bytes, filename: str):
    web.header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    web.header('Content-Disposition', f'attachment; filename="{filename}"')
    return data


def _investment_date_bound(value: str, end: bool = False) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "T" in text or " " in text:
        return text
    beijing_zone = timezone(timedelta(hours=8))
    parsed_date = datetime.strptime(text, "%Y-%m-%d").date()
    if end:
        beijing_bound = datetime.combine(parsed_date, datetime.max.time(), tzinfo=beijing_zone)
        return beijing_bound.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="microseconds")
    beijing_bound = datetime.combine(parsed_date, datetime.min.time(), tzinfo=beijing_zone)
    return beijing_bound.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def _investment_month_bounds(year: int, month: int) -> tuple[str, str]:
    last_day = monthrange(int(year), int(month))[1]
    return (
        _investment_date_bound(f"{int(year):04d}-{int(month):02d}-01"),
        _investment_date_bound(f"{int(year):04d}-{int(month):02d}-{last_day:02d}", end=True),
    )


def _investment_quarter_bounds(year: int, quarter: int) -> tuple[str, str]:
    quarter_value = int(quarter)
    if quarter_value < 1 or quarter_value > 4:
        raise ValueError("quarter must be between 1 and 4")
    start_month = (quarter_value - 1) * 3 + 1
    end_month = start_month + 2
    start_date, _ = _investment_month_bounds(int(year), start_month)
    _, end_date = _investment_month_bounds(int(year), end_month)
    return start_date, end_date


def _investment_stock_stats():
    from sqlalchemy import select
    from business.investment.db import connect, row_to_dict
    from business.investment.schema import investment_stock_symbols
    from business.investment.stock_resolver import stock_dictionary_stats

    stats = stock_dictionary_stats()
    table = investment_stock_symbols
    latest_updated_at = select(table.c.updated_at).order_by(table.c.updated_at.desc()).limit(1).scalar_subquery()
    stmt = select(table.c.source).where(table.c.updated_at == latest_updated_at).order_by(table.c.source).limit(1)
    with connect() as conn:
        row = conn.execute(stmt).fetchone()
    stats["latest_source"] = row_to_dict(row).get("source", "") if row else ""
    return stats


class InvestmentAuthMeHandler:
    def GET(self):
        try:
            admin = _current_investment_admin()
            if admin is None:
                return _investment_json_response({"status": "error", "code": "unauthorized", "message": "未登录或登录已过期"})
            return _investment_json_response({"status": "success", "admin": _investment_admin_payload(admin)})
        except web.HTTPError as error:
            return error.data


def _investment_admin_user_payload(admin):
    return {
        "id": admin.id,
        "username": admin.username,
        "role": admin.role,
        "enabled": admin.enabled,
        "last_login_at": admin.last_login_at,
    }


class InvestmentAdminUsersHandler:
    def GET(self):
        _require_investment_permission("admin_users.read")
        try:
            from business.investment.auth_service import count_admin_users, list_admin_users

            params = web.input(keyword='', page='1', page_size='20')
            page, page_size = _investment_safe_pagination(params, 20)
            keyword = getattr(params, "keyword", "") or None
            total = count_admin_users(keyword=keyword)

            return _investment_json_response({
                "status": "success",
                "users": [
                    _investment_admin_user_payload(admin)
                    for admin in list_admin_users(keyword=keyword, page=page, page_size=page_size)
                ],
                "pagination": _investment_pagination_payload(page, page_size, total),
            })
        except Exception as e:
            logger.error(f"[Investment] admin users GET error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})

    def POST(self):
        admin = _require_investment_permission("admin_users.write")
        try:
            from business.investment.auth_service import create_admin_user, get_admin_user, reset_admin_password, update_admin_user

            body = _investment_json_body()
            username = str(body.get("username", "")).strip()
            if not username:
                return _investment_json_response({"status": "error", "message": "username required"})
            role = str(body.get("role", "") or "content_operator").strip()
            password = str(body.get("password", "") or "")
            enabled = body.get("enabled")
            existing = get_admin_user(username)
            if existing:
                update_admin_user(username, role=role or existing.role, enabled=bool(enabled) if enabled is not None else None)
                if password:
                    _require_investment_permission("admin_users.reset_password")
                    reset_admin_password(username, password)
                action = "updated"
                _record_investment_operation(
                    "admin_user.update",
                    "admin_user",
                    username,
                    admin=admin,
                    detail={"role": role or existing.role, "enabled": enabled},
                )
            else:
                if not password:
                    return _investment_json_response({"status": "error", "message": "password required"})
                create_admin_user(username, password, role=role or "content_operator", enabled=bool(enabled) if enabled is not None else True)
                action = "created"
                _record_investment_operation(
                    "admin_user.create",
                    "admin_user",
                    username,
                    admin=admin,
                    detail={"role": role or "content_operator", "enabled": bool(enabled) if enabled is not None else True},
                )
            return _investment_json_response({"status": "success", "action": action})
        except Exception as e:
            logger.error(f"[Investment] admin users POST error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentAdminUserStatusHandler:
    def POST(self, username, action):
        admin = _require_investment_permission("admin_users.write")
        try:
            from business.investment.auth_service import update_admin_user

            update_admin_user(username, enabled=(action == "enable"))
            _record_investment_operation(
                f"admin_user.{action}",
                "admin_user",
                username,
                admin=admin,
                detail={"enabled": action == "enable"},
            )
            return _investment_json_response({"status": "success"})
        except Exception as e:
            logger.error(f"[Investment] admin user status error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentAdminUserPasswordHandler:
    def POST(self, username):
        admin = _require_investment_permission("admin_users.reset_password")
        try:
            from business.investment.auth_service import reset_admin_password

            body = _investment_json_body()
            password = str(body.get("password", "") or "")
            if not password:
                return _investment_json_response({"status": "error", "message": "password required"})
            reset_admin_password(username, password)
            _record_investment_operation("admin_user.reset_password", "admin_user", username, admin=admin)
            return _investment_json_response({"status": "success"})
        except Exception as e:
            logger.error(f"[Investment] admin user password reset error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentRequestRecordsExportHandler:
    def GET(self):
        _require_investment_permission("records.export")
        try:
            from business.investment.export_service import export_request_records_xlsx

            params = web.input(
                start_date='',
                end_date='',
                service_type='',
                status='',
                keyword='',
                customer='',
                year='',
                month='',
                quarter='',
            )
            start_date = _investment_date_bound(params.start_date)
            end_date = _investment_date_bound(params.end_date, end=True)
            if getattr(params, "year", "") and getattr(params, "month", ""):
                start_date, end_date = _investment_month_bounds(int(params.year), int(params.month))
            elif getattr(params, "year", "") and getattr(params, "quarter", ""):
                start_date, end_date = _investment_quarter_bounds(int(params.year), int(params.quarter))
            data = export_request_records_xlsx(
                start_date,
                end_date,
                service_type=params.service_type or None,
                status=getattr(params, "status", "") or None,
                keyword=getattr(params, "keyword", "") or "",
                customer=getattr(params, "customer", "") or "",
            )
            return _investment_xlsx_response(data, "investment-requests.xlsx")
        except Exception as e:
            logger.error(f"[Investment] request records export error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentUsersExportHandler:
    def GET(self):
        admin = _require_investment_permission("customers.export")
        try:
            from business.investment.export_service import export_users_xlsx

            params = web.input(enabled='')
            enabled = None
            if params.enabled != "":
                enabled = _investment_bool(params.enabled)
            _record_investment_operation("customer.export", "customer", admin=admin, detail={"enabled": enabled})
            return _investment_xlsx_response(export_users_xlsx(enabled=enabled), "investment-users.xlsx")
        except Exception as e:
            logger.error(f"[Investment] users export error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentUsersHandler:
    def GET(self):
        _require_investment_permission("customers.read")
        try:
            from business.investment.user_service import count_users, list_users

            params = web.input(openid='', enabled='', keyword='', page='1', page_size='20')
            page, page_size = _investment_safe_pagination(params, 20)
            enabled = None
            enabled_value = getattr(params, "enabled", "")
            if enabled_value != "":
                enabled = enabled_value in ("1", "true", "True", "yes")
            openid = getattr(params, "openid", "") or None
            keyword = getattr(params, "keyword", "") or None
            total = count_users(enabled=enabled, openid=openid, keyword=keyword)
            users = list_users(
                enabled=enabled,
                openid=openid,
                keyword=keyword,
                page=page,
                page_size=page_size,
            )
            return _investment_json_response({
                "status": "success",
                "users": [
                    {
                        "id": user.id,
                        "openid": user.openid,
                        "name": user.name,
                        "institution": user.institution,
                        "mobile": user.mobile,
                        "enabled": user.enabled,
                        "allowed_services": [str(item) for item in (user.allowed_services or [])],
                        "auth_start_at": user.auth_start_at.isoformat() if user.auth_start_at else "",
                        "auth_end_at": user.auth_end_at.isoformat() if user.auth_end_at else "",
                        "remark": user.remark,
                    }
                    for user in users
                ],
                "pagination": _investment_pagination_payload(page, page_size, total),
            })
        except Exception as e:
            logger.error(f"[Investment] users GET error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})

    def POST(self):
        admin = _require_investment_permission("customers.write")
        try:
            from business.investment.user_service import create_user, update_user, get_user_by_openid

            body = _investment_json_body()
            openid = body.get("openid", "").strip()
            if not openid:
                return _investment_json_response({"status": "error", "message": "openid required"})
            values = {
                "name": body.get("name", ""),
                "institution": body.get("institution", ""),
                "mobile": body.get("mobile", ""),
                "enabled": bool(body.get("enabled", True)),
                "allowed_services": body.get("allowed_services", ["全部"]),
                "auth_start_at": body.get("auth_start_at") or None,
                "auth_end_at": body.get("auth_end_at") or None,
                "remark": body.get("remark", ""),
            }
            if get_user_by_openid(openid):
                update_user(openid, **values)
                action = "updated"
            else:
                create_user(openid, **values)
                action = "created"
            _record_investment_operation(
                f"customer.{action[:-1] if action.endswith('d') else action}",
                "customer",
                openid,
                admin=admin,
                detail={key: value for key, value in values.items() if key != "allowed_services"} | {"allowed_services": values["allowed_services"]},
            )
            return _investment_json_response({"status": "success", "action": action})
        except Exception as e:
            logger.error(f"[Investment] users POST error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentUserStatusHandler:
    def POST(self, openid, action):
        admin = _require_investment_permission("customers.enable")
        try:
            from business.investment.user_service import disable_user, enable_user, get_user_by_openid

            if get_user_by_openid(openid) is None:
                return _investment_json_response({"status": "error", "message": "user not found"})
            if action == "enable":
                enable_user(openid)
            else:
                disable_user(openid)
            _record_investment_operation(f"customer.{action}", "customer", openid, admin=admin)
            return _investment_json_response({"status": "success"})
        except Exception as e:
            logger.error(f"[Investment] user status error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentUserDisableHandler:
    def POST(self, openid):
        return InvestmentUserStatusHandler().POST(openid, "disable")


class InvestmentUsersImportHandler:
    def POST(self):
        admin = _require_investment_permission("customers.import")
        try:
            from business.investment.user_service import get_user_by_openid, import_users, parse_users_excel

            params = _raw_web_input()
            file_obj = params.get("file")
            if file_obj is None:
                return _investment_json_response({"status": "error", "message": "file required"})
            rows = parse_users_excel(_read_uploaded_file_bytes(file_obj))
            commit = str(params.get("commit", "")).strip().lower() in {"1", "true", "yes", "commit"}
            new_users = sum(1 for row in rows if row.openid_generated or get_user_by_openid(row.openid) is None)
            result = import_users(rows) if commit else None
            created = result.created if result else 0
            updated = result.updated if result else 0
            if commit:
                _record_investment_operation(
                    "customer.import",
                    "customer",
                    admin=admin,
                    detail={"parsed": len(rows), "new_users": new_users, "created": created, "updated": updated},
                )
            return _investment_json_response({
                "status": "success",
                "committed": commit,
                "parsed": len(rows),
                "new_users": new_users,
                "created": created,
                "updated": updated,
                "preview": [_investment_import_user_preview(row) for row in rows[:10]],
            })
        except Exception as e:
            logger.error(f"[Investment] users import error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentUsersImportTemplateHandler:
    def GET(self):
        _require_investment_permission("customers.import")
        try:
            from business.investment.export_service import export_users_import_template_xlsx

            return _investment_xlsx_response(export_users_import_template_xlsx(), "investment-users-import-template.xlsx")
        except Exception as e:
            logger.error(f"[Investment] users import template error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


def _investment_import_user_preview(row):
    def _date_text(value):
        return value.isoformat(timespec="seconds") if value else ""

    return {
        "openid": row.openid,
        "name": row.name,
        "institution": row.institution,
        "mobile": row.mobile,
        "enabled": row.enabled,
        "allowed_services": row.allowed_services,
        "auth_start_at": _date_text(row.auth_start_at),
        "auth_end_at": _date_text(row.auth_end_at),
        "remark": row.remark,
        "openid_generated": row.openid_generated,
    }


class InvestmentDailyContentHandler:
    def GET(self):
        _require_investment_permission("content.read")
        try:
            from business.investment.records import list_content_records
            from business.investment.constants import normalize_service, ServiceType
            from business.investment.daily_content import get_latest_effective_content
            from business.investment.records import get_content_record

            params = web.input(limit='50', service_type='', effective_date='')
            service_value = str(getattr(params, "service_type", "") or "").strip()
            service_type = normalize_service(service_value) if service_value else None
            if service_type == ServiceType.UNMATCHED:
                return _investment_json_response({
                    "status": "success",
                    "current_effective": None,
                    "contents": [],
                })
            contents = list_content_records(
                limit=_investment_safe_limit(getattr(params, "limit", "50")),
                service_type=service_type,
                effective_date=getattr(params, "effective_date", "") or None,
            )
            current_effective = None
            if service_type in (ServiceType.RATE, ServiceType.CONVERTIBLE_BOND):
                latest = get_latest_effective_content(service_type)
                if latest.success and latest.content_id:
                    record = get_content_record(latest.content_id)
                    current_effective = record.__dict__ | {
                        "service_type": str(record.service_type),
                        "status": str(record.status),
                    }
            return _investment_json_response({
                "status": "success",
                "current_effective": current_effective,
                "contents": [content.__dict__ | {
                    "service_type": str(content.service_type),
                    "status": str(content.status),
                } for content in contents],
            })
        except Exception as e:
            logger.error(f"[Investment] content GET error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})

    def POST(self):
        _require_investment_permission("content.upload")
        try:
            from business.investment.constants import normalize_service
            from business.investment.daily_content import create_content_draft, save_source_file, update_generation_success

            source_files = []
            if _investment_is_multipart_request():
                params = _raw_web_input()
                body = {
                    "service_type": params.get("service_type", ""),
                    "source_text": params.get("source_text", ""),
                    "joke_text": params.get("joke_text", ""),
                    "operator": params.get("operator", ""),
                    "effective_date": params.get("effective_date", ""),
                    "direct_output_mode": params.get("direct_output_mode", ""),
                    "generated_text": params.get("generated_text", ""),
                    "output_image": params.get("output_image", ""),
                }
                file_items = []
                primary_file = params.get("file")
                if primary_file is not None:
                    file_items.append(primary_file)
                file_items.extend(_ensure_list(params.get("files")))
                service_type = normalize_service(body.get("service_type", ""))
                for file_obj in file_items:
                    filename = getattr(file_obj, "filename", "") or getattr(file_obj, "name", "") or "source.bin"
                    source_files.append(save_source_file(service_type, os.path.basename(filename), _read_uploaded_file_bytes(file_obj)))
            else:
                body = _investment_json_body()
                source_files = body.get("source_files", [])
            service_type = normalize_service(body.get("service_type", ""))
            source_text = body.get("source_text", "")
            joke_text = body.get("joke_text", "")
            if joke_text:
                source_text = f"{source_text}\n\n{joke_text}".strip()
            content_id = create_content_draft(
                service_type,
                source_files=source_files,
                source_text=source_text,
                operator=body.get("operator", ""),
                effective_date=body.get("effective_date") or None,
                direct_output_mode=_investment_bool(body.get("direct_output_mode")),
            )
            if body.get("generated_text") or body.get("output_image"):
                update_generation_success(content_id, body.get("generated_text", ""), body.get("output_image", ""))
            return _investment_json_response({"status": "success", "content_id": content_id})
        except Exception as e:
            logger.error(f"[Investment] content POST error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentDailyContentGenerateHandler:
    def POST(self, content_id):
        _require_investment_permission("content.generate")
        try:
            from business.investment.daily_content import generate_content, mark_generation_started, update_generation_failure

            result = mark_generation_started(content_id)
            if result.success:
                def run_generation_task():
                    try:
                        generate_content(content_id)
                    except Exception as task_error:
                        logger.error(f"[Investment] background content generate error: {task_error}", exc_info=True)
                        update_generation_failure(content_id, str(task_error))

                threading.Thread(
                    target=run_generation_task,
                    name=f"investment-generate-{content_id[:8]}",
                    daemon=True,
                ).start()
            payload = {
                "status": "success" if result.success else "error",
                "content_id": result.content_id,
                "generated_text": result.generated_text,
                "output_image": result.output_image,
                "output_files": result.output_files,
                "generation_status": "started" if result.success else "",
                "error_code": str(result.error_code) if result.error_code else "",
                "user_prompt": result.user_prompt,
                "detail": result.detail,
            }
            return _investment_json_response(payload)
        except Exception as e:
            logger.error(f"[Investment] content generate error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentDailyContentEffectiveHandler:
    def POST(self, content_id):
        _require_investment_permission("content.publish")
        try:
            from business.investment.daily_content import set_content_effective

            body = _investment_json_body()
            set_content_effective(
                content_id,
                body.get("output_image") or None,
                effective_date=body.get("effective_date") or None,
                operator=body.get("operator", ""),
            )
            return _investment_json_response({"status": "success"})
        except Exception as e:
            logger.error(f"[Investment] set effective error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentOperationAuditsHandler:
    def GET(self):
        _require_investment_permission("audits.read")
        try:
            from business.investment.audit_service import list_operation_audits_page

            params = web.input(
                limit='50',
                page='1',
                page_size='',
                action='',
                target_type='',
                target_id='',
                operator='',
                keyword='',
                start_date='',
                end_date='',
            )
            page, page_size = _investment_safe_pagination(params, 80)
            audits, total = list_operation_audits_page(
                page=page,
                page_size=page_size,
                action=getattr(params, "action", "") or None,
                target_type=getattr(params, "target_type", "") or None,
                target_id=getattr(params, "target_id", "") or None,
                operator=getattr(params, "operator", "") or None,
                keyword=getattr(params, "keyword", "") or "",
                start_date=_investment_date_bound(getattr(params, "start_date", "")),
                end_date=_investment_date_bound(getattr(params, "end_date", ""), end=True),
            )
            return _investment_json_response({
                "status": "success",
                "audits": [audit.__dict__ for audit in audits],
                "pagination": _investment_pagination_payload(page, page_size, total),
            })
        except Exception as e:
            logger.error(f"[Investment] audits GET error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentRequestRecordsHandler:
    def GET(self):
        _require_investment_permission("records.read")
        try:
            from business.investment.records import list_output_files, list_request_records_page
            from business.investment.constants import ServiceType, normalize_service

            params = web.input(
                limit='50',
                page='1',
                page_size='',
                service_type='',
                status='',
                keyword='',
                customer='',
                start_date='',
                end_date='',
            )
            service_value = str(getattr(params, "service_type", "") or "").strip()
            service_type = normalize_service(service_value) if service_value else None
            if service_type == ServiceType.UNMATCHED and service_value not in {"unmatched", str(ServiceType.UNMATCHED)}:
                page, page_size = _investment_safe_pagination(params, 80)
                return _investment_json_response({
                    "status": "success",
                    "records": [],
                    "pagination": _investment_pagination_payload(page, page_size, 0),
                })
            page, page_size = _investment_safe_pagination(params, 80)
            records, total = list_request_records_page(
                page=page,
                page_size=page_size,
                service_type=service_type,
                status=getattr(params, "status", "") or None,
                keyword=getattr(params, "keyword", "") or "",
                customer=getattr(params, "customer", "") or "",
                start_date=_investment_date_bound(getattr(params, "start_date", "")),
                end_date=_investment_date_bound(getattr(params, "end_date", ""), end=True),
            )
            return _investment_json_response({
                "status": "success",
                "records": [record.__dict__ | {
                    "service_type": str(record.service_type) if record.service_type else "",
                    "status": str(record.status),
                    "error_code": str(record.error_code) if record.error_code else "",
                    "output_artifacts": list_output_files(record.request_id),
                } for record in records],
                "pagination": _investment_pagination_payload(page, page_size, total),
            })
        except Exception as e:
            logger.error(f"[Investment] request records error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentContentRecordsHandler:
    def GET(self):
        _require_investment_permission("records.read")
        try:
            from business.investment.constants import ServiceType, normalize_service
            from business.investment.records import list_content_records_page, list_output_files

            params = web.input(limit='50', page='1', page_size='', service_type='', effective_date='', status='')
            service_value = str(getattr(params, "service_type", "") or "").strip()
            service_type = normalize_service(service_value) if service_value else None
            if service_type == ServiceType.UNMATCHED:
                page, page_size = _investment_safe_pagination(params, 80)
                return _investment_json_response({
                    "status": "success",
                    "records": [],
                    "pagination": _investment_pagination_payload(page, page_size, 0),
                })
            page, page_size = _investment_safe_pagination(params, 80)
            records, total = list_content_records_page(
                page=page,
                page_size=page_size,
                service_type=service_type,
                effective_date=getattr(params, "effective_date", "") or None,
                status=getattr(params, "status", "") or None,
            )
            return _investment_json_response({
                "status": "success",
                "records": [record.__dict__ | {
                    "service_type": str(record.service_type),
                    "status": str(record.status),
                    "output_artifacts": list_output_files(record.content_id),
                } for record in records],
                "pagination": _investment_pagination_payload(page, page_size, total),
            })
        except Exception as e:
            logger.error(f"[Investment] content records error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentCacheHandler:
    def GET(self):
        _require_investment_permission("cache.read")
        try:
            from business.investment.cache_service import list_cache_entries_page, list_cache_market_dates
            from business.investment.constants import ServiceType, normalize_service

            params = web.input(limit='50', page='1', page_size='', service_type='', market_date='', include_invalidated='')
            service_value = str(getattr(params, "service_type", "") or "").strip()
            service_type = normalize_service(service_value) if service_value else None
            if service_type == ServiceType.UNMATCHED:
                page, page_size = _investment_safe_pagination(params, 120)
                return _investment_json_response({
                    "status": "success",
                    "entries": [],
                    "market_dates": [],
                    "pagination": _investment_pagination_payload(page, page_size, 0),
                })
            include_invalidated = str(getattr(params, "include_invalidated", "")).lower() in {"1", "true", "yes"}
            page, page_size = _investment_safe_pagination(params, 120)
            entries, total = list_cache_entries_page(
                page=page,
                page_size=page_size,
                service_type=service_type,
                market_date=getattr(params, "market_date", "") or "",
                include_invalidated=include_invalidated,
            )
            return _investment_json_response({
                "status": "success",
                "entries": [entry.__dict__ | {"service_type": str(entry.service_type)} for entry in entries],
                "market_dates": list_cache_market_dates(
                    service_type=service_type,
                    include_invalidated=include_invalidated,
                ),
                "pagination": _investment_pagination_payload(page, page_size, total),
            })
        except Exception as e:
            logger.error(f"[Investment] cache entries error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentCacheEntryInvalidateHandler:
    def POST(self, cache_key):
        _require_investment_permission("cache.write")
        try:
            from business.investment.audit_service import record_operation_audit
            from business.investment.cache_service import invalidate_cache_entry

            body = _investment_json_body()
            invalidated = invalidate_cache_entry(cache_key)
            record_operation_audit(
                "cache.invalidate",
                "investment_cache_entry",
                target_id=cache_key,
                operator=body.get("operator", "web-console"),
                detail={"invalidated": invalidated},
            )
            return _investment_json_response({"status": "success", "invalidated": invalidated})
        except Exception as e:
            logger.error(f"[Investment] cache invalidate error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentCacheClearHandler:
    def POST(self):
        _require_investment_permission("cache.write")
        try:
            from business.investment.audit_service import record_operation_audit
            from business.investment.cache_service import clear_cache_entries
            from business.investment.constants import ServiceType, normalize_service

            body = _investment_json_body()
            service_type = normalize_service(body.get("service_type", "")) if body.get("service_type") else None
            if service_type == ServiceType.UNMATCHED:
                service_type = None
            market_date = str(body.get("market_date") or "").strip()
            removed = clear_cache_entries(service_type=service_type, market_date=market_date)
            record_operation_audit(
                "cache.clear",
                "investment_cache_entry",
                operator=body.get("operator", "web-console"),
                detail={"service_type": str(service_type) if service_type else "", "market_date": market_date, "removed": removed},
            )
            return _investment_json_response({"status": "success", "removed": removed})
        except Exception as e:
            logger.error(f"[Investment] cache clear error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentConfigHandler:
    def GET(self):
        _require_investment_permission("config.read")
        try:
            from business.investment.config_service import CONFIG_FALLBACK_KEYS, get_configs
            from business.investment.reply_config import reply_text_config_metadata

            return _investment_json_response({
                "status": "success",
                "configs": get_configs(list(CONFIG_FALLBACK_KEYS.keys()), masked=True),
                "reply_texts": reply_text_config_metadata(),
            })
        except Exception as e:
            logger.error(f"[Investment] config GET error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})

    def POST(self):
        admin = _require_investment_permission("config.write")
        try:
            from business.investment.config_service import save_configs
            from business.investment.audit_service import record_operation_audit

            body = _investment_json_body()
            save_configs(
                body.get("configs", {}),
                operator_role=admin.role,
                operator=body.get("operator", "") or admin.username,
            )
            record_operation_audit(
                "config.update",
                "investment_config",
                operator=body.get("operator", "") or admin.username,
                detail={"keys": sorted((body.get("configs", {}) or {}).keys())},
            )
            return _investment_json_response({"status": "success"})
        except Exception as e:
            logger.error(f"[Investment] config POST error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentSkillVersionsHandler:
    def GET(self):
        _require_investment_permission("skills.read")
        try:
            from business.investment.skill_versions import list_all_skills

            return _investment_json_response({
                "status": "success",
                "skills": list_all_skills(),
            })
        except Exception as e:
            logger.error(f"[Investment] skill versions GET error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentSkillSettingsHandler:
    def POST(self, skill_key):
        _require_investment_permission("skills.write")
        try:
            from business.investment.config_service import save_config
            from business.investment.skill_registry import get_skill_definition
            from business.investment.skill_versions import list_all_skills

            definition = get_skill_definition(skill_key)
            body = _investment_json_body()
            operator = body.get("operator", "web-console")

            if "enabled" in body:
                save_config(
                    definition.enabled_config_key,
                    bool(body.get("enabled")),
                    operator_role="admin",
                    operator=operator,
                )

            if "triggers" in body:
                triggers = body.get("triggers") or []
                if isinstance(triggers, str):
                    triggers = [item.strip() for item in triggers.replace("，", ",").split(",")]
                triggers = [str(item).strip() for item in triggers if str(item).strip()]
                if definition.routable and not triggers:
                    return _investment_json_response({"status": "error", "message": "triggers cannot be empty"})
                save_config(
                    definition.triggers_config_key,
                    triggers,
                    operator_role="admin",
                    operator=operator,
                )

            return _investment_json_response({"status": "success", "skills": list_all_skills()})
        except Exception as e:
            logger.error(f"[Investment] skill settings error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentSkillPackageUploadHandler:
    def POST(self):
        _require_investment_permission("skills.write")
        try:
            from business.investment.skill_versions import list_all_skills, save_package_upload

            params = _raw_web_input()
            file_obj = params.get("file")
            if file_obj is None:
                return _investment_json_response({"status": "error", "message": "file required"})
            filename = getattr(file_obj, "filename", "") or getattr(file_obj, "name", "") or "investment-skill.zip"
            uploaded = save_package_upload(
                os.path.basename(filename),
                _read_uploaded_file_bytes(file_obj),
                operator=params.get("operator", "web-console"),
            )
            return _investment_json_response({
                "status": "success",
                "uploaded": uploaded,
                "skills": list_all_skills(),
            })
        except Exception as e:
            logger.error(f"[Investment] skill package upload error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentSkillUploadHandler:
    def POST(self, skill_key):
        _require_investment_permission("skills.write")
        try:
            from business.investment.skill_versions import list_all_skills, save_upload

            params = _raw_web_input()
            file_obj = params.get("file")
            if file_obj is None:
                return _investment_json_response({"status": "error", "message": "file required"})
            filename = getattr(file_obj, "filename", "") or getattr(file_obj, "name", "") or "investment-skill.bin"
            version = save_upload(
                skill_key,
                os.path.basename(filename),
                _read_uploaded_file_bytes(file_obj),
                operator=params.get("operator", "web-console"),
            )
            return _investment_json_response({
                "status": "success",
                "version": version,
                "skills": list_all_skills(),
            })
        except Exception as e:
            logger.error(f"[Investment] skill upload error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentSkillActivateHandler:
    def POST(self, skill_key, version_id):
        _require_investment_permission("skills.write")
        try:
            from business.investment.skill_versions import activate_version, list_all_skills

            body = _investment_json_body()
            version = activate_version(skill_key, version_id, operator=body.get("operator", "web-console"))
            return _investment_json_response({
                "status": "success",
                "version": version,
                "skills": list_all_skills(),
            })
        except Exception as e:
            logger.error(f"[Investment] skill activate error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentSkillDeleteHandler:
    def POST(self, skill_key, version_id):
        _require_investment_permission("skills.write")
        try:
            from business.investment.skill_versions import delete_version, list_all_skills

            body = _investment_json_body()
            deleted = delete_version(skill_key, version_id, operator=body.get("operator", "web-console"))
            return _investment_json_response({
                "status": "success",
                "deleted": deleted,
                "skills": list_all_skills(),
            })
        except Exception as e:
            logger.error(f"[Investment] skill delete error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentStocksHandler:
    def GET(self):
        _require_investment_permission("stocks.read")
        try:
            from business.investment.stock_resolver import list_stock_symbols

            params = web.input(name='', limit='20')
            stocks = list_stock_symbols(params.name, limit=int(params.limit or 20))
            return _investment_json_response({
                "status": "success",
                "stocks": stocks,
                "stats": _investment_stock_stats(),
            })
        except Exception as e:
            logger.error(f"[Investment] stocks GET error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})


class InvestmentStocksRefreshHandler:
    def POST(self):
        _require_investment_permission("stocks.write")
        try:
            from business.investment import stock_resolver

            body = _investment_json_body()
            source = str(body.get("source") or "auto").strip().lower()
            if source == "auto":
                result = stock_resolver.refresh_from_auto()
            elif source == "akshare":
                result = {"akshare": {"count": stock_resolver.refresh_from_akshare()}}
            elif source == "tushare":
                result = {"tushare": {"count": stock_resolver.refresh_from_tushare()}}
            else:
                return _investment_json_response({"status": "error", "message": f"unsupported source: {source}"})
            return _investment_json_response({
                "status": "success",
                "result": result,
                "stats": _investment_stock_stats(),
            })
        except Exception as e:
            logger.error(f"[Investment] stocks refresh error: {e}")
            return _investment_json_response({
                "status": "error",
                "message": str(e),
                "stats": _investment_stock_stats(),
            })


class InvestmentHealthHandler:
    def GET(self):
        _require_investment_permission("health.read")
        params = web.input(smoke="")
        run_smoke = _investment_bool(getattr(params, "smoke", ""))
        return self._run(run_smoke)

    def POST(self):
        _require_investment_permission("health.read")
        params = web.input(smoke="")
        body = _investment_json_body()
        run_smoke = _investment_bool(getattr(params, "smoke", "")) or _investment_bool(body.get("smoke"))
        return self._run(run_smoke)

    def _run(self, run_smoke: bool):
        try:
            from business.investment.health import run_health_checks

            checks = run_health_checks(run_smoke=run_smoke)
            level = "error" if any(item.level == "error" for item in checks) else "warning" if any(item.level == "warning" for item in checks) else "ok"
            return _investment_json_response({
                "status": "success",
                "ok": level != "error",
                "level": level,
                "run_smoke": run_smoke,
                "checks": [dict(getattr(item, "__dict__", {})) for item in checks],
            })
        except Exception as e:
            logger.error(f"[Investment] health error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})
