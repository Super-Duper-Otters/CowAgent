# encoding:utf-8
from __future__ import annotations

import importlib
import os
import sys
import threading
from contextlib import contextmanager
from concurrent.futures import ProcessPoolExecutor, TimeoutError
from concurrent.futures.process import BrokenProcessPool
from typing import Any


MAX_AKSHARE_WORKERS = 30
_DEFAULT_TIMEOUT_SECONDS = 60.0
_WAIT_OBJECT_0 = 0x00000000
_WAIT_TIMEOUT = 0x00000102
_INFINITE = 0xFFFFFFFF
_SEMAPHORE_NAME = "Global\\CowAgentAkShareConcurrencyV1"
_executor: ProcessPoolExecutor | None = None
_executor_lock = threading.Lock()
_thread_semaphore = threading.BoundedSemaphore(MAX_AKSHARE_WORKERS)


def call_akshare(function_name: str, *args: Any, timeout: float | None = None, **kwargs: Any) -> Any:
    """Run one AkShare SDK call in a worker process.

    py_mini_racer/V8 can crash the interpreter when initialized concurrently in
    threads. Keeping AkShare calls behind a process boundary isolates that
    native failure from the web process and caps system-wide AkShare concurrency.
    """
    if _should_call_inline():
        return _call_akshare_inline(function_name, args, kwargs)
    timeout_seconds = _timeout_seconds(timeout)
    with _global_akshare_slot(timeout_seconds):
        future = _get_executor().submit(_call_akshare_inline, function_name, args, kwargs)
        try:
            return future.result(timeout=timeout_seconds)
        except TimeoutError:
            future.cancel()
            _reset_executor()
            raise TimeoutError(f"AkShare call timed out: {function_name}")
        except BrokenProcessPool:
            _reset_executor()
            raise


def shutdown_akshare_pool() -> None:
    _reset_executor()


def _reset_executor() -> None:
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None


def _get_executor() -> ProcessPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ProcessPoolExecutor(max_workers=_max_workers())
        return _executor


def _max_workers() -> int:
    try:
        configured = int(os.environ.get("AKSHARE_PROCESS_POOL_WORKERS", str(MAX_AKSHARE_WORKERS)) or MAX_AKSHARE_WORKERS)
    except ValueError:
        configured = MAX_AKSHARE_WORKERS
    return max(1, min(configured, MAX_AKSHARE_WORKERS))


def _global_limit() -> int:
    return MAX_AKSHARE_WORKERS


def _timeout_seconds(value: float | None) -> float:
    if value is not None:
        return max(0.1, float(value))
    try:
        return max(0.1, float(os.environ.get("AKSHARE_PROCESS_POOL_TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT_SECONDS))))
    except ValueError:
        return _DEFAULT_TIMEOUT_SECONDS


def _should_call_inline() -> bool:
    if os.environ.get("AKSHARE_PROCESS_POOL_DISABLED", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    module = sys.modules.get("akshare")
    return module is not None and not hasattr(module, "__file__")


def _call_akshare_inline(function_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    akshare = importlib.import_module("akshare")
    function = getattr(akshare, function_name)
    return function(*args, **kwargs)


@contextmanager
def _global_akshare_slot(timeout_seconds: float):
    if os.name == "nt":
        handle = _win32_create_semaphore(_global_limit(), _SEMAPHORE_NAME)
        acquired = False
        try:
            acquired = _win32_wait_semaphore(handle, timeout_seconds)
            if not acquired:
                raise TimeoutError("AkShare global concurrency queue timed out")
            yield
        finally:
            if acquired:
                _win32_release_semaphore(handle)
            _win32_close_handle(handle)
        return

    acquired = _thread_semaphore.acquire(timeout=timeout_seconds)
    if not acquired:
        raise TimeoutError("AkShare global concurrency queue timed out")
    try:
        yield
    finally:
        _thread_semaphore.release()


def _win32_create_semaphore(max_count: int, name: str):
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateSemaphoreW.argtypes = [wintypes.LPVOID, wintypes.LONG, wintypes.LONG, wintypes.LPCWSTR]
    kernel32.CreateSemaphoreW.restype = wintypes.HANDLE
    handle = kernel32.CreateSemaphoreW(None, max_count, max_count, name)
    if not handle:
        raise OSError(ctypes.get_last_error(), "CreateSemaphoreW failed")
    return handle


def _win32_wait_semaphore(handle, timeout_seconds: float) -> bool:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    timeout_ms = _INFINITE if timeout_seconds <= 0 else int(timeout_seconds * 1000)
    result = kernel32.WaitForSingleObject(handle, timeout_ms)
    if result == _WAIT_OBJECT_0:
        return True
    if result == _WAIT_TIMEOUT:
        return False
    raise OSError(ctypes.get_last_error(), f"WaitForSingleObject failed: {result}")


def _win32_release_semaphore(handle) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.ReleaseSemaphore.argtypes = [wintypes.HANDLE, wintypes.LONG, wintypes.LPVOID]
    kernel32.ReleaseSemaphore.restype = wintypes.BOOL
    if not kernel32.ReleaseSemaphore(handle, 1, None):
        raise OSError(ctypes.get_last_error(), "ReleaseSemaphore failed")


def _win32_close_handle(handle) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(handle)
