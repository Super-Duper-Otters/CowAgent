# encoding:utf-8
import threading
import time
from dataclasses import dataclass, field


@dataclass
class PassiveReplyResult:
    title: str
    replies: list[tuple[str, str]] = field(default_factory=list)
    created_at: float = 0.0
    service_type: object = ""


class PassiveReplyCache:
    def __init__(self, ttl_seconds=12 * 60 * 60, now_func=None):
        self.ttl_seconds = ttl_seconds
        self._now = now_func or time.time
        self._results = {}
        self._pending_commands = {}
        self._lock = threading.RLock()

    def append_result(self, receiver, title, replies, service_type=""):
        with self._lock:
            self._results[receiver] = PassiveReplyResult(
                title=title or "",
                replies=list(replies or []),
                created_at=self._now(),
                service_type=service_type or "",
            )

    def append_reply(self, receiver, reply_type, reply_content, title="", service_type=""):
        with self._lock:
            result = self._get_live_result_locked(receiver)
            if result is None:
                self._results[receiver] = PassiveReplyResult(
                    title=title or "",
                    replies=[(reply_type, reply_content)],
                    created_at=self._now(),
                    service_type=service_type or "",
                )
                return
            if title and not result.title:
                result.title = title
            if service_type and not result.service_type:
                result.service_type = service_type
            result.replies.append((reply_type, reply_content))

    def peek_result(self, receiver):
        with self._lock:
            result = self._get_live_result_locked(receiver)
            if result is None:
                return None
            return PassiveReplyResult(
                title=result.title,
                replies=list(result.replies),
                created_at=result.created_at,
                service_type=result.service_type,
            )

    def _get_live_result_locked(self, receiver):
        result = self._results.get(receiver)
        if result is None:
            return None
        if self._is_expired(result):
            self._results.pop(receiver, None)
            self._pending_commands.pop(receiver, None)
            return None
        return result

    def pop_result(self, receiver):
        with self._lock:
            result = self._get_live_result_locked(receiver)
            if result is None or not result.replies:
                self._results.pop(receiver, None)
                return None
            item = result.replies.pop(0)
            if not result.replies:
                self._results.pop(receiver, None)
            return item

    def discard_result(self, receiver):
        with self._lock:
            self._results.pop(receiver, None)

    def set_pending_command(self, receiver, content):
        with self._lock:
            self._pending_commands[receiver] = content

    def pop_pending_command(self, receiver):
        with self._lock:
            return self._pending_commands.pop(receiver, None)

    def cleanup_expired(self):
        with self._lock:
            expired = [receiver for receiver, result in self._results.items() if self._is_expired(result)]
            for receiver in expired:
                self._results.pop(receiver, None)
                self._pending_commands.pop(receiver, None)

    def clear(self):
        with self._lock:
            self._results.clear()
            self._pending_commands.clear()

    def get(self, receiver, default=None):
        result = self.peek_result(receiver)
        if result is None:
            return default
        return list(result.replies)

    def __contains__(self, receiver):
        return self.peek_result(receiver) is not None

    def __getitem__(self, receiver):
        result = self.peek_result(receiver)
        if result is None:
            raise KeyError(receiver)
        return list(result.replies)

    def __delitem__(self, receiver):
        with self._lock:
            self._results.pop(receiver, None)
            self._pending_commands.pop(receiver, None)

    def _is_expired(self, result):
        return self._now() - result.created_at > self.ttl_seconds
