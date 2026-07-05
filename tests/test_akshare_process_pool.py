# encoding:utf-8
from types import SimpleNamespace


def test_akshare_process_pool_worker_count_is_capped(monkeypatch):
    from business.market import akshare_process_pool

    monkeypatch.setenv("AKSHARE_PROCESS_POOL_WORKERS", "99")

    assert akshare_process_pool._max_workers() == 30
    assert akshare_process_pool._global_limit() == 30


def test_akshare_process_pool_calls_inline_for_fake_akshare(monkeypatch):
    import sys

    from business.market.akshare_process_pool import call_akshare

    calls = []
    fake_akshare = SimpleNamespace(example=lambda **kwargs: calls.append(kwargs) or {"ok": True})
    monkeypatch.setitem(sys.modules, "akshare", fake_akshare)

    assert call_akshare("example", value=1) == {"ok": True}
    assert calls == [{"value": 1}]
