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
    module_key: str = ""
    request_id: str = ""
    source_type: str = ""
    source_id: str = ""


class PassiveReplyCache:
    def __init__(self, ttl_seconds=6 * 60 * 60, now_func=None):
        self.ttl_seconds = ttl_seconds
        self._now = now_func or time.time
        self._results = {}
        self._pending_commands = {}
        self._technical_confirm_bindings = {}
        self._lock = threading.RLock()

    def append_result(self, receiver, title, replies, service_type="", request_id="", source_type="", source_id="", module_key=""):
        with self._lock:
            self._results.setdefault(receiver, []).append(PassiveReplyResult(
                title=title or "",
                replies=list(replies or []),
                created_at=self._now(),
                service_type=service_type or "",
                module_key=str(module_key or ""),
                request_id=request_id or "",
                source_type=str(source_type or ""),
                source_id=str(source_id or ""),
            ))

    def append_reply(self, receiver, reply_type, reply_content, title="", service_type="", request_id="", source_type="", source_id="", module_key=""):
        with self._lock:
            result = self._find_append_target_locked(receiver, title, service_type, module_key, request_id, source_type, source_id)
            if result is None:
                self._results.setdefault(receiver, []).append(PassiveReplyResult(
                    title=title or "",
                    replies=[(reply_type, reply_content)],
                    created_at=self._now(),
                    service_type=service_type or "",
                    module_key=str(module_key or ""),
                    request_id=request_id or "",
                    source_type=str(source_type or ""),
                    source_id=str(source_id or ""),
                ))
                return
            if title and not result.title:
                result.title = title
            if service_type and not result.service_type:
                result.service_type = service_type
            if module_key and not result.module_key:
                result.module_key = str(module_key)
            if request_id and not result.request_id:
                result.request_id = request_id
            if source_type and not result.source_type:
                result.source_type = str(source_type)
            if source_id and not result.source_id:
                result.source_id = str(source_id)
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
                module_key=result.module_key,
                request_id=result.request_id,
                source_type=result.source_type,
                source_id=result.source_id,
            )

    def _find_append_target_locked(self, receiver, title, service_type, module_key, request_id, source_type, source_id):
        results = self._live_results_locked(receiver)
        if not results:
            return None
        normalized_request_id = str(request_id or "")
        if normalized_request_id:
            for result in reversed(results):
                if str(result.request_id or "") == normalized_request_id:
                    return result
            return None
        normalized_title = str(title or "")
        normalized_service_type = str(service_type or "")
        normalized_module_key = str(module_key or "")
        normalized_source_type = str(source_type or "")
        normalized_source_id = str(source_id or "")
        latest = results[-1]
        if (
            latest.title == normalized_title
            and str(latest.service_type or "") == normalized_service_type
            and str(latest.module_key or "") == normalized_module_key
            and str(latest.source_type or "") == normalized_source_type
            and str(latest.source_id or "") == normalized_source_id
        ):
            return latest
        return None

    def _get_live_result_locked(self, receiver):
        live_results = self._live_results_locked(receiver)
        if not live_results:
            return None
        for result in reversed(live_results):
            if self._is_technical_result(result) and result.replies:
                return result
        return live_results[0]

    def _live_results_locked(self, receiver):
        results = self._results.get(receiver)
        if not results:
            return None
        live_results = [result for result in results if not self._is_expired(result)]
        if len(live_results) != len(results):
            if live_results:
                self._results[receiver] = live_results
            else:
                self._results.pop(receiver, None)
                self._pending_commands.pop(receiver, None)
                self._technical_confirm_bindings.pop(receiver, None)
                return None
        return live_results

    def pop_result(self, receiver):
        with self._lock:
            result = self._get_live_result_locked(receiver)
            if result is None or not result.replies:
                self._drop_empty_results_locked(receiver)
                return None
            item = result.replies.pop(0)
            self._drop_empty_results_locked(receiver)
            return item

    def pop_latest_technical_result(self, receiver):
        selected = self.pop_latest_technical_result_with_metadata(receiver)
        if selected is None:
            return None
        item, _result = selected
        return item

    def pop_latest_technical_result_with_metadata(self, receiver):
        with self._lock:
            results = self._results.get(receiver) or []
            for index in range(len(results) - 1, -1, -1):
                result = results[index]
                if self._is_expired(result):
                    del results[index]
                    continue
                if not self._is_technical_result(result):
                    continue
                if not result.replies:
                    del results[index]
                    continue
                item = result.replies.pop(0)
                result_copy = self._result_copy(result, [item])
                if not result.replies:
                    del results[index]
                if results:
                    self._results[receiver] = results
                else:
                    self._results.pop(receiver, None)
                    self._pending_commands.pop(receiver, None)
                return item, result_copy
            if not results:
                self._results.pop(receiver, None)
            return None

    def bind_technical_confirm(self, receiver, title, request_id="", source_type="", source_id=""):
        target = self._normalize_technical_title(title)
        if not target:
            return
        with self._lock:
            self._technical_confirm_bindings[receiver] = {
                "title": target,
                "request_id": str(request_id or ""),
                "source_type": str(source_type or ""),
                "source_id": str(source_id or ""),
                "created_at": 0.0,
            }

    def has_technical_confirm_binding(self, receiver):
        with self._lock:
            return receiver in self._technical_confirm_bindings

    def clear_technical_confirm_binding(self, receiver):
        with self._lock:
            self._technical_confirm_bindings.pop(receiver, None)

    def pop_bound_technical_result_with_metadata(self, receiver):
        with self._lock:
            binding = self._technical_confirm_bindings.get(receiver)
            if not binding:
                return None
            results = self._results.get(receiver) or []
            selected_index = self._bound_technical_result_index_locked(results, binding)
            if selected_index is None:
                self._technical_confirm_bindings.pop(receiver, None)
                self._drop_empty_results_locked(receiver)
                return None
            result = results[selected_index]
            item = result.replies.pop(0)
            result_copy = self._result_copy(result, [item])
            self._technical_confirm_bindings[receiver] = {
                "title": self._normalize_technical_title(result.title),
                "request_id": str(result.request_id or ""),
                "source_type": str(result.source_type or ""),
                "source_id": str(result.source_id or ""),
                "created_at": float(result.created_at or 0.0),
            }
            if not result.replies:
                del results[selected_index]
                if self._bound_technical_result_index_locked(results, self._technical_confirm_bindings[receiver]) is None:
                    self._technical_confirm_bindings.pop(receiver, None)
            if results:
                self._results[receiver] = results
            else:
                self._results.pop(receiver, None)
                self._pending_commands.pop(receiver, None)
            return item, result_copy

    def pop_result_for_title(self, receiver, title):
        target = self._normalize_technical_title(title)
        with self._lock:
            results = self._results.get(receiver) or []
            for index in range(len(results) - 1, -1, -1):
                result = results[index]
                if self._is_expired(result):
                    del results[index]
                    continue
                if self._normalize_technical_title(result.title) != target:
                    continue
                if not result.replies:
                    del results[index]
                    continue
                item = result.replies.pop(0)
                result_copy = self._result_copy(result, [item])
                if not result.replies:
                    del results[index]
                if results:
                    self._results[receiver] = results
                else:
                    self._results.pop(receiver, None)
                    self._pending_commands.pop(receiver, None)
                return item, result_copy
            if not results:
                self._results.pop(receiver, None)
            return None

    def pop_result_by_title(self, receiver, title):
        selected = self.pop_result_for_title(receiver, title)
        if selected is None:
            return None
        item, _result = selected
        return item

    def pending_technical_summary(self, receiver):
        try:
            from business.config.constants import ServiceType, normalize_service
        except Exception:
            ServiceType = None
            normalize_service = None
        summary = []
        counts = {}
        latest_created_at = {}
        with self._lock:
            results = self._results.get(receiver) or []
            live_results = []
            for result in results:
                if self._is_expired(result):
                    continue
                live_results.append(result)
                is_technical = str(result.service_type or "") == "technical_analysis"
                if normalize_service and ServiceType:
                    try:
                        is_technical = normalize_service(result.service_type) == ServiceType.TECHNICAL_ANALYSIS
                    except Exception:
                        pass
                if not is_technical or not result.replies:
                    continue
                target = self._normalize_technical_title(result.title)
                if not target:
                    continue
                if target not in counts:
                    summary.append(target)
                    counts[target] = 0
                counts[target] += 1
                latest_created_at[target] = max(latest_created_at.get(target, 0.0), float(result.created_at or 0.0))
            if live_results:
                self._results[receiver] = live_results
            else:
                self._results.pop(receiver, None)
                self._pending_commands.pop(receiver, None)
        return [(target, counts[target], latest_created_at.get(target, 0.0)) for target in summary]

    def pending_summary(self, receiver):
        summary = []
        counts = {}
        latest_created_at = {}
        with self._lock:
            results = self._results.get(receiver) or []
            live_results = []
            for result in results:
                if self._is_expired(result):
                    continue
                live_results.append(result)
                if not result.replies:
                    continue
                target = self._summary_title(result)
                if not target:
                    continue
                if target not in counts:
                    summary.append(target)
                    counts[target] = 0
                counts[target] += len(result.replies)
                latest_created_at[target] = max(latest_created_at.get(target, 0.0), float(result.created_at or 0.0))
            if live_results:
                self._results[receiver] = live_results
            else:
                self._results.pop(receiver, None)
                self._pending_commands.pop(receiver, None)
        return [(target, counts[target], latest_created_at.get(target, 0.0)) for target in summary]

    def _drop_empty_results_locked(self, receiver):
        results = self._results.get(receiver) or []
        results = [result for result in results if result.replies]
        if results:
            self._results[receiver] = results
        else:
            self._results.pop(receiver, None)
            self._pending_commands.pop(receiver, None)
            self._technical_confirm_bindings.pop(receiver, None)

    def discard_result(self, receiver):
        with self._lock:
            self._results.pop(receiver, None)
            self._technical_confirm_bindings.pop(receiver, None)

    def discard_by_source(self, source_type, source_id):
        normalized_type = str(source_type or "")
        normalized_id = str(source_id or "")
        if not normalized_type or not normalized_id:
            return 0
        removed = 0
        with self._lock:
            for receiver, results in list(self._results.items()):
                kept = []
                for result in results:
                    if result.source_type == normalized_type and result.source_id == normalized_id:
                        removed += 1
                    else:
                        kept.append(result)
                if kept:
                    self._results[receiver] = kept
                else:
                    self._results.pop(receiver, None)
                    self._pending_commands.pop(receiver, None)
                    self._technical_confirm_bindings.pop(receiver, None)
            return removed

    def discard_invalid_sources(self, is_source_valid, exclude_receivers=None):
        if not callable(is_source_valid):
            return 0
        excluded = set(exclude_receivers or [])
        with self._lock:
            removed = 0
            for receiver, results in list(self._results.items()):
                if receiver in excluded:
                    continue
                kept = []
                for result in results:
                    if self._is_expired(result):
                        removed += 1
                        continue
                    if result.source_type and result.source_id and not is_source_valid(result):
                        removed += 1
                        continue
                    kept.append(result)
                if kept:
                    self._results[receiver] = kept
                else:
                    self._results.pop(receiver, None)
                    self._pending_commands.pop(receiver, None)
                    self._technical_confirm_bindings.pop(receiver, None)
            return removed

    def set_pending_command(self, receiver, content):
        with self._lock:
            self._pending_commands[receiver] = content

    def pop_pending_command(self, receiver):
        with self._lock:
            return self._pending_commands.pop(receiver, None)

    def cleanup_expired(self):
        with self._lock:
            for receiver, results in list(self._results.items()):
                live_results = [result for result in results if not self._is_expired(result)]
                if live_results:
                    self._results[receiver] = live_results
                else:
                    self._results.pop(receiver, None)
                    self._pending_commands.pop(receiver, None)
                    self._technical_confirm_bindings.pop(receiver, None)

    def clear(self):
        with self._lock:
            self._results.clear()
            self._pending_commands.clear()
            self._technical_confirm_bindings.clear()

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
            self._technical_confirm_bindings.pop(receiver, None)

    def _is_expired(self, result):
        return self._now() - result.created_at > self.ttl_seconds

    def _is_technical_result(self, result):
        service_text = str(result.service_type or "")
        if service_text == "technical_analysis":
            return True
        try:
            from business.config.constants import ServiceType, normalize_service

            return normalize_service(result.service_type) == ServiceType.TECHNICAL_ANALYSIS
        except Exception:
            return False

    def _normalize_technical_title(self, title):
        text = str(title or "").strip()
        if text.startswith("#"):
            text = text[1:].strip()
        suffix = "技术分析"
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
        return text

    def _summary_title(self, result):
        if self._is_technical_result(result):
            return self._normalize_technical_title(result.title)
        return str(result.title or "").strip()

    def _bound_technical_result_index_locked(self, results, binding):
        target = str(binding.get("title") or "")
        request_id = str(binding.get("request_id") or "")
        source_type = str(binding.get("source_type") or "")
        source_id = str(binding.get("source_id") or "")
        created_at = float(binding.get("created_at") or 0.0)
        for index in range(len(results) - 1, -1, -1):
            result = results[index]
            if self._is_expired(result):
                del results[index]
                continue
            if not self._is_technical_result(result):
                continue
            if self._normalize_technical_title(result.title) != target:
                continue
            if not result.replies:
                del results[index]
                continue
            if request_id and str(result.request_id or "") != request_id:
                continue
            if source_type and str(result.source_type or "") != source_type:
                continue
            if source_id and str(result.source_id or "") != source_id:
                continue
            if created_at and float(result.created_at or 0.0) != created_at:
                continue
            return index
        return None

    def _result_copy(self, result, replies):
        return PassiveReplyResult(
            title=result.title,
            replies=list(replies or []),
            created_at=result.created_at,
            service_type=result.service_type,
            module_key=result.module_key,
            request_id=result.request_id,
            source_type=result.source_type,
            source_id=result.source_id,
        )
