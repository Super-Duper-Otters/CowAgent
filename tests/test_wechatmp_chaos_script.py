# encoding:utf-8
import threading
from types import SimpleNamespace

from scripts import run_wechatmp_chaos_real_flow as chaos


class _FakeCache:
    def __init__(self, results):
        self._results = {"user_1": results}
        self._lock = threading.RLock()

    def _live_results_locked(self, receiver):
        return self._results.get(receiver)


def test_ack_with_pending_summary_is_classified_as_accepted():
    response = (
        "收到，您当前还有技术分析结果待领取：\n"
        '1.<a href="weixin://bizmsgmenu?msgmenucontent=600519.SH&msgmenuid=pending_1">600519.SH</a> 2条\n'
        "正在处理，请稍候。请等待30-40s后回复1获取"
    )

    assert chaos._classify_response(response) == "accepted_ack"


def test_pending_count_counts_result_records_not_reply_items():
    channel = SimpleNamespace(
        cache_dict=_FakeCache([
            SimpleNamespace(replies=[("image", "a"), ("image", "b")]),
            SimpleNamespace(replies=[("image", "c")]),
            SimpleNamespace(replies=[]),
        ])
    )

    assert chaos._pending_count(channel, "user_1") == 2


def test_pending_claim_targets_parse_codes_from_wechat_rich_text():
    response = (
        "您当前还有技术分析结果待领取：\n"
        '1.<a href="weixin://bizmsgmenu?msgmenucontent=L11231.CSI&msgmenuid=pending_1">L11231.CSI</a> 1条\n'
        '2.<a href="weixin://bizmsgmenu?msgmenucontent=301112.SZ&msgmenuid=pending_2">301112.SZ</a> 2条\n'
        '3.<a href="weixin://bizmsgmenu?msgmenucontent=%23600519&msgmenuid=pending_3">#600519</a> 1条\n'
    )

    assert chaos._pending_claim_targets(response) == ["L11231.CSI", "301112.SZ", "#600519"]


def test_active_user_bounds_default_to_all_users():
    assert chaos._active_user_bounds(total_users=30, min_active_users=0, max_active_users=0) == (30, 30)


def test_active_user_bounds_are_clamped_to_total_users():
    assert chaos._active_user_bounds(total_users=200, min_active_users=100, max_active_users=250) == (100, 200)
