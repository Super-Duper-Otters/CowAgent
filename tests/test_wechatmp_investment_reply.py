# encoding:utf-8
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from business.investment.constants import ServiceType
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED = pytest.mark.skip(
    reason="stage 8 removes investment route and permission prechecks from wechatmp channel modules"
)


@pytest.fixture(autouse=True)
def _default_investment_user_access(monkeypatch):
    monkeypatch.setattr(
        "business.investment.user_service.verify_user_access",
        lambda _openid: SimpleNamespace(allowed=True, user_prompt=""),
    )


@pytest.fixture(autouse=True)
def _isolate_investment_record_writes(monkeypatch):
    monkeypatch.setattr("business.investment.records.create_request_record", lambda *args, **_kwargs: "test-request-id")
    monkeypatch.setattr("business.investment.records.fail_request_record", lambda *args, **_kwargs: None)
    monkeypatch.setattr("business.business_records.create_request_record", lambda *args, **_kwargs: "test-request-id")
    monkeypatch.setattr("business.business_records.fail_request_record", lambda *args, **_kwargs: None)


@pytest.fixture()
def investment_env(tmp_path, monkeypatch):
    from business.investment import db, storage

    base_url = os.environ.get("COWAGENT_TEST_POSTGRES_URL") or db.DEFAULT_DATABASE_URL
    schema_name = f"cowagent_test_{uuid4().hex}"
    url = make_url(base_url)
    schema_url = url.set(
        query={
            **dict(url.query),
            "options": f"-csearch_path={schema_name}",
        },
    ).render_as_string(hide_password=False)

    admin_engine = create_engine(base_url, future=True)
    with admin_engine.begin() as conn:
        conn.execute(text(f'create schema "{schema_name}"'))

    monkeypatch.setenv("COWAGENT_INVESTMENT_DATABASE_URL", schema_url)
    monkeypatch.setenv("COWAGENT_INVESTMENT_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.delenv("COWAGENT_INVESTMENT_DB_PATH", raising=False)

    db.reset_engine_for_tests()
    storage._MIGRATED_DATABASE_URL = None
    storage.initialize_storage()
    try:
        yield tmp_path
    finally:
        db.reset_engine_for_tests()
        storage._MIGRATED_DATABASE_URL = None
        with admin_engine.begin() as conn:
            conn.execute(text(f'drop schema if exists "{schema_name}" cascade'))
        admin_engine.dispose()


def _reset_wechatmp_singleton(wechatmp_channel):
    instances = wechatmp_channel.WechatMPChannel.__closure__[1].cell_contents
    instances.clear()


def _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts):
    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.cache_dict = channel.cache_dict
            self.running = channel.running
            self.request_cnt = channel.request_cnt
            self.technical_analysis_titles = getattr(channel, "technical_analysis_titles", {})
            self.running_started_at = getattr(channel, "running_started_at", {})
            self.running_lock = getattr(channel, "running_lock", None)

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)

        def produce(self, context):
            produced_contexts.append(context)
            self.running.discard("openid")

    fake_msg = SimpleNamespace(type="text")
    monkeypatch.setattr(passive_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(passive_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(passive_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(passive_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        passive_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="openid",
            content=current_message["content"],
            msg_id=current_message["msg_id"],
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(passive_reply, "create_reply", FakeReply)
    monkeypatch.setattr(passive_reply, "_technical_analysis_cache_hit", lambda _content: False, raising=False)
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: SimpleNamespace(allowed=True, user_prompt=""),
    )
    monkeypatch.setattr(passive_reply.web, "input", lambda: {})
    monkeypatch.setattr(passive_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        passive_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )


def test_wechatmp_stage8_channel_modules_do_not_import_investment_runtime():
    for path in (
        "channel/wechatmp/passive_reply.py",
        "channel/wechatmp/active_reply.py",
    ):
        source = open(path, encoding="utf-8").read()
        assert "business.investment" not in source


def test_passive_reply_cache_confirms_discards_expires_and_tracks_pending_command():
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache
    from business.investment.constants import ServiceType

    now = [1000.0]
    cache = PassiveReplyCache(now_func=lambda: now[0])
    cache.append_result("openid", "300502.SZ 技术分析", [("image", "media-1")], service_type=ServiceType.TECHNICAL_ANALYSIS)

    assert "openid" in cache
    assert cache.peek_result("openid").title == "300502.SZ 技术分析"
    assert cache.peek_result("openid").service_type == ServiceType.TECHNICAL_ANALYSIS
    assert cache.pop_result("openid") == ("image", "media-1")
    assert "openid" not in cache

    cache.append_result("openid", "300502.SZ 技术分析", [("image", "media-2")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    cache.discard_result("openid")
    assert cache.peek_result("openid") is None

    cache.set_pending_command("openid", "利率")
    cache.set_pending_command("openid", "转债")
    assert cache.pop_pending_command("openid") == "转债"
    assert cache.pop_pending_command("openid") is None

    cache.append_result("openid", "300502.SZ 技术分析", [("image", "media-3")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    now[0] += 12 * 60 * 60 + 1
    cache.cleanup_expired()

    assert cache.peek_result("openid") is None


def test_passive_reply_cache_default_ttl_is_six_hours():
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    assert PassiveReplyCache().ttl_seconds == 6 * 60 * 60


def test_passive_reply_cache_discards_entries_by_source_without_touching_other_sources():
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache
    from business.investment.constants import ServiceType

    cache = PassiveReplyCache()
    cache.append_result(
        "openid-a",
        "300502.SZ 技术分析",
        [("image", "media-a")],
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        source_type="cache",
        source_id="cache-a",
    )
    cache.append_result(
        "openid-b",
        "300503.SZ 技术分析",
        [("image", "media-b")],
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        source_type="cache",
        source_id="cache-b",
    )
    cache.append_result(
        "openid-c",
        "利率",
        [("image", "media-c")],
        service_type=ServiceType.RATE,
        source_type="content",
        source_id="content-c",
    )

    assert cache.discard_by_source("cache", "cache-a") == 1

    assert cache.peek_result("openid-a") is None
    assert cache.peek_result("openid-b").replies == [("image", "media-b")]
    assert cache.peek_result("openid-c").replies == [("image", "media-c")]


def test_passive_reply_cache_discards_invalid_sources_without_touching_current_receiver():
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache
    from business.investment.constants import ServiceType

    cache = PassiveReplyCache()
    cache.append_result(
        "openid-current",
        "300502.SZ 技术分析",
        [("image", "media-current")],
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        source_type="cache",
        source_id="cache-current",
    )
    cache.append_result(
        "openid-stale",
        "300503.SZ 技术分析",
        [("image", "media-stale")],
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        source_type="cache",
        source_id="cache-stale",
    )
    cache.append_result(
        "openid-live",
        "利率",
        [("image", "media-live")],
        service_type=ServiceType.RATE,
        source_type="content",
        source_id="content-live",
    )

    cleared = cache.discard_invalid_sources(
        lambda result: result.source_id != "cache-stale",
        exclude_receivers=["openid-current"],
    )

    assert cleared == 1
    assert cache.peek_result("openid-current").replies == [("image", "media-current")]
    assert cache.peek_result("openid-stale") is None
    assert cache.peek_result("openid-live").replies == [("image", "media-live")]


def test_passive_reply_cache_returns_list_copies_for_legacy_access():
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    cache = PassiveReplyCache()
    cache.append_result("openid", "利率", [("image", "media-1")], service_type=ServiceType.RATE)

    cache.get("openid").append(("image", "external-get"))
    cache["openid"].append(("image", "external-getitem"))

    assert cache.pop_result("openid") == ("image", "media-1")
    assert cache.pop_result("openid") is None


def test_passive_reply_cache_preserves_request_id_without_breaking_legacy_access():
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    cache = PassiveReplyCache()
    cache.append_result(
        "openid",
        "利率",
        [("image", "media-1")],
        service_type=ServiceType.RATE,
        request_id="request-1",
    )

    cached_result = cache.peek_result("openid")

    assert cached_result.request_id == "request-1"
    assert cache.get("openid") == [("image", "media-1")]
    assert cache["openid"] == [("image", "media-1")]
    assert cache.pop_result("openid") == ("image", "media-1")

    cache.append_reply(
        "openid",
        "text",
        "ready",
        "转债",
        service_type=ServiceType.CONVERTIBLE_BOND,
        request_id="request-2",
    )

    assert cache.peek_result("openid").request_id == "request-2"
    assert cache.pop_result("openid") == ("text", "ready")


def test_passive_reply_cache_summarizes_and_pops_technical_results_by_target_name():
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    now = [1718445600.0]
    cache = PassiveReplyCache(now_func=lambda: now[0])
    cache.append_result("openid", "天娱数科 技术分析", [("image", "media-ty-1")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    now[0] += 60
    cache.append_result("openid", "农业银行 技术分析", [("image", "media-ny-1")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    now[0] += 60
    cache.append_result("openid", "天娱数科 技术分析", [("image", "media-ty-2")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    cache.append_result("openid", "利率", [("image", "media-rate")], service_type=ServiceType.RATE)

    assert cache.pending_technical_summary("openid") == [
        ("天娱数科", 2, 1718445720.0),
        ("农业银行", 1, 1718445660.0),
    ]
    assert cache.pop_result_by_title("openid", "农业银行") == ("image", "media-ny-1")
    assert cache.pending_technical_summary("openid") == [("天娱数科", 2, 1718445720.0)]
    assert cache.pop_result("openid") == ("image", "media-ty-2")
    assert cache.pop_result("openid") == ("image", "media-ty-1")
    assert cache.pop_result("openid") == ("image", "media-rate")


def test_passive_reply_cache_keeps_new_business_result_out_of_existing_technical_package():
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    cache = PassiveReplyCache()
    cache.append_result(
        "openid",
        "天娱数科 技术分析",
        [("image", "media-ty")],
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        request_id="request-ty",
    )

    cache.append_reply(
        "openid",
        "image",
        "media-rate",
        "利率",
        service_type=ServiceType.RATE,
        request_id="request-rate",
    )

    assert cache.pop_result_by_title("openid", "利率") == ("image", "media-rate")
    assert cache.pending_technical_summary("openid") == [("天娱数科", 1, pytest.approx(cache.peek_result("openid").created_at))]


def test_passive_reply_cache_pops_latest_technical_result_for_confirm_and_title():
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    cache = PassiveReplyCache()
    cache.append_result("openid", "天娱数科 技术分析", [("image", "old-main")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    cache.append_result(
        "openid",
        "天娱数科 技术分析",
        [("image", "new-main"), ("image", "new-detail")],
        service_type=ServiceType.TECHNICAL_ANALYSIS,
    )
    cache.append_result("openid", "农业银行 技术分析", [("image", "ny-main")], service_type=ServiceType.TECHNICAL_ANALYSIS)

    assert cache.pop_result_by_title("openid", "天娱数科") == ("image", "new-main")
    assert cache.pop_result_by_title("openid", "天娱数科") == ("image", "new-detail")
    assert cache.pop_result("openid") == ("image", "ny-main")
    assert cache.pop_result("openid") == ("image", "old-main")


def test_passive_reply_cache_append_cleanup_and_pop_are_thread_safe():
    import threading
    import time

    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    cache = PassiveReplyCache(ttl_seconds=-1)
    for index in range(200):
        cache.append_result(f"old-{index}", "expired", [("text", str(index))])

    entered_cleanup = threading.Event()
    original_is_expired = cache._is_expired

    def slow_is_expired(result):
        entered_cleanup.set()
        time.sleep(0.001)
        return original_is_expired(result)

    cache._is_expired = slow_is_expired
    errors = []

    def cleanup():
        try:
            cache.cleanup_expired()
        except Exception as exc:  # pragma: no cover - assertion below reports details
            errors.append(exc)

    def append_and_pop():
        entered_cleanup.wait(timeout=1)
        for index in range(50):
            receiver = f"new-{index}"
            cache.append_result(receiver, "fresh", [("text", str(index))])
            cache.pop_result(receiver)

    cleanup_thread = threading.Thread(target=cleanup)
    worker_thread = threading.Thread(target=append_and_pop)
    cleanup_thread.start()
    worker_thread.start()
    cleanup_thread.join()
    worker_thread.join()

    assert errors == []


def _wechatmp_channel(monkeypatch):
    import channel.wechatmp.wechatmp_channel as wechatmp_channel

    wechatmp_channel.image_media_cache.clear()
    monkeypatch.setattr(
        wechatmp_channel,
        "conf",
        lambda: {
            "wechatmp_app_id": "wx-test",
            "wechatmp_app_secret": "secret",
            "wechatmp_token": "token",
            "wechatmp_aes_key": "",
            "single_chat_prefix": [""],
            "concurrency_in_session": 1,
        },
    )
    channel = wechatmp_channel.WechatMPChannel()
    channel.cache_dict.clear()
    channel.running.clear()
    channel.request_cnt.clear()
    return channel


def _context(openid="openid", msg_id="msg-1", content="利率"):
    from bridge.context import Context, ContextType

    msg = SimpleNamespace(from_user_id=openid, other_user_id=openid, msg_id=msg_id)
    return Context(
        ContextType.TEXT,
        content,
        {
            "msg": msg,
            "session_id": openid,
            "receiver": openid,
            "channel_type": "wechatmp",
            "isgroup": False,
        },
    )


def test_wechatmp_investment_success_returns_image_reply(monkeypatch, tmp_path):
    from bridge.reply import ReplyType
    from business.investment.constants import ServiceType
    from business.investment.router import BusinessReply
    import business.business_router as business_router
    import business.daily_content_handler as cowagent_content_handler

    image_path = str(tmp_path / "rate_card.png")
    monkeypatch.setattr(business_router, "verify_user_access", lambda _openid: SimpleNamespace(allowed=True, user_prompt=""))
    monkeypatch.setattr(business_router, "verify_permission", lambda _openid, _service_type: SimpleNamespace(allowed=True, user_prompt=""))
    monkeypatch.setattr(
        cowagent_content_handler,
        "handle_daily_content",
        lambda _openid, _content, _route, **_kwargs: BusinessReply(
            handled=True,
            success=True,
            reply_text=f"[图片: {image_path}]",
            output_files=[image_path],
            service_type=ServiceType.RATE,
        ),
    )
    monkeypatch.setattr(
        "business.investment.message_handler.handle_inbound_message",
        lambda *_args, **_kwargs: pytest.fail("wechatmp must route business through ChatChannel main chain"),
    )

    reply = _wechatmp_channel(monkeypatch)._generate_reply(_context())

    assert reply.type == ReplyType.IMAGE_URL
    assert reply.content == [image_path]
    assert reply.business_service_type == ServiceType.RATE
    assert reply.investment_service_type == ServiceType.RATE


def test_wechatmp_technical_analysis_router_returns_only_user_images_not_markdown(monkeypatch, tmp_path):
    from business.investment.constants import ServiceType
    from business.investment.technical_analysis import TechnicalAnalysisCacheContext, TechnicalAnalysisResult
    import business.router as business_route
    import business.technical_analysis_handler as cowagent_ta_handler

    signal_card_path = str(tmp_path / "signal-card.png")
    main_chart_path = str(tmp_path / "main-chart.png")
    markdown_report_path = str(tmp_path / "report.md")
    recorded_output_files = []

    monkeypatch.setattr(
        business_route,
        "verify_user_access",
        lambda _openid: SimpleNamespace(allowed=True, user_prompt=""),
    )
    monkeypatch.setattr(
        business_route,
        "verify_permission",
        lambda _openid, _service_type: SimpleNamespace(allowed=True, user_prompt=""),
    )
    monkeypatch.setattr(
        "business.investment.technical_analysis.prepare_technical_analysis_cache_context",
        lambda _raw_input, _target_text: TechnicalAnalysisCacheContext(),
    )
    monkeypatch.setattr(
        cowagent_ta_handler,
        "prepare_technical_analysis_business_context",
        lambda _raw_input, _target_text: TechnicalAnalysisCacheContext(),
    )
    monkeypatch.setattr(
        "business.investment.job_service.start_job_if_absent_with_metadata",
        lambda *_args, **_kwargs: SimpleNamespace(
            created=True,
            record=SimpleNamespace(request_id="request-tech"),
        ),
    )
    monkeypatch.setattr(
        cowagent_ta_handler,
        "start_job_if_absent_with_metadata",
        lambda *_args, **_kwargs: SimpleNamespace(
            created=True,
            record=SimpleNamespace(request_id="request-tech"),
        ),
    )
    monkeypatch.setattr(
        cowagent_ta_handler,
        "succeed_request_record",
        lambda _request_id, output_files, **_kwargs: recorded_output_files.extend(output_files),
    )

    reply = business_route.handle_text_message(
        "openid",
        "天娱数科 技术分析",
        technical_analysis_handler=lambda *_args: TechnicalAnalysisResult(
            success=True,
            signal_card_path=signal_card_path,
            main_chart_path=main_chart_path,
            report_path=markdown_report_path,
            output_files=[signal_card_path, main_chart_path, markdown_report_path],
        ),
    )

    assert reply.success is True
    assert reply.service_type == ServiceType.TECHNICAL_ANALYSIS
    assert reply.output_files == [signal_card_path, main_chart_path]
    assert markdown_report_path not in reply.reply_text
    assert recorded_output_files == [signal_card_path, main_chart_path, markdown_report_path]


def test_wechatmp_technical_analysis_generate_reply_uses_router_user_images(monkeypatch, tmp_path):
    from bridge.reply import ReplyType
    from business.investment.constants import ServiceType
    from business.investment.router import BusinessReply
    import business.business_router as business_router
    import business.technical_analysis_handler as cowagent_ta_handler

    signal_card_path = str(tmp_path / "signal-card.png")
    main_chart_path = str(tmp_path / "main-chart.png")
    markdown_report_path = str(tmp_path / "report.md")

    monkeypatch.setattr(business_router, "verify_user_access", lambda _openid: SimpleNamespace(allowed=True, user_prompt=""))
    monkeypatch.setattr(business_router, "verify_permission", lambda _openid, _service_type: SimpleNamespace(allowed=True, user_prompt=""))
    monkeypatch.setattr(
        cowagent_ta_handler,
        "handle_technical_analysis",
        lambda _openid, _content, _route, **_kwargs: BusinessReply(
            handled=True,
            success=True,
            reply_text=f"[图片: {signal_card_path}]\n[图片: {main_chart_path}]",
            output_files=[signal_card_path, main_chart_path],
            service_type=ServiceType.TECHNICAL_ANALYSIS,
        ),
    )

    reply = _wechatmp_channel(monkeypatch)._generate_reply(_context(content="天娱数科 技术分析"))

    assert reply.type == ReplyType.IMAGE_URL
    assert reply.content == [signal_card_path, main_chart_path]
    assert markdown_report_path not in reply.content
    assert reply.business_service_type == ServiceType.TECHNICAL_ANALYSIS
    assert reply.investment_service_type == ServiceType.TECHNICAL_ANALYSIS


def test_wechatmp_passive_send_uploads_image_list_without_text_marker(monkeypatch, tmp_path):
    from bridge.reply import Reply, ReplyType
    import pytest

    channel = _wechatmp_channel(monkeypatch)
    images = []
    for name in ("signal.png", "chart.png"):
        path = tmp_path / name
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        images.append(str(path))

    class FakeMedia:
        def __init__(self):
            self.calls = []

        def upload(self, media_type, media):
            self.calls.append((media_type, media[0]))
            return {"media_id": f"media-{len(self.calls)}"}

    channel.client.media = FakeMedia()
    channel.client.material = SimpleNamespace(
        add=lambda *_args, **_kwargs: pytest.fail("passive image replies must use temporary media upload")
    )

    channel.send(Reply(ReplyType.IMAGE_URL, images), _context())

    assert channel.client.media.calls == [
        ("image", "openid-msg-1.png"),
        ("image", "openid-msg-1.png"),
    ]
    assert channel.cache_dict["openid"] == [("image", "media-1"), ("image", "media-2")]


def test_wechatmp_passive_send_preserves_business_request_id_in_cache(monkeypatch, tmp_path):
    from bridge.reply import Reply, ReplyType

    channel = _wechatmp_channel(monkeypatch)
    text_reply = Reply(ReplyType.TEXT, "ready")
    text_reply.business_request_id = "request-text"
    text_reply.business_service_type = ServiceType.RATE

    channel.send(text_reply, _context(openid="openid-text", msg_id="msg-text"))

    assert channel.cache_dict.peek_result("openid-text").request_id == "request-text"

    image_path = tmp_path / "main.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    class FakeMedia:
        def upload(self, media_type, media):
            return {"media_id": "media-image"}

    channel.client.media = FakeMedia()
    image_reply = Reply(ReplyType.IMAGE_URL, [str(image_path)])
    image_reply.business_request_id = "request-image"
    image_reply.business_service_type = ServiceType.TECHNICAL_ANALYSIS
    image_reply.business_source_type = "cache"
    image_reply.business_source_id = "cache-image"

    channel.send(image_reply, _context(openid="openid-image", msg_id="msg-image"))

    cached_image = channel.cache_dict.peek_result("openid-image")
    assert cached_image.request_id == "request-image"
    assert cached_image.source_type == "cache"
    assert cached_image.source_id == "cache-image"


def test_wechatmp_passive_send_preserves_legacy_investment_metadata_in_cache(monkeypatch):
    from bridge.reply import Reply, ReplyType

    channel = _wechatmp_channel(monkeypatch)
    text_reply = Reply(ReplyType.TEXT, "ready")
    text_reply.investment_request_id = "legacy-request"
    text_reply.investment_service_type = ServiceType.RATE

    channel.send(text_reply, _context(openid="openid-legacy", msg_id="msg-legacy"))

    cached = channel.cache_dict.peek_result("openid-legacy")
    assert cached.request_id == "legacy-request"
    assert cached.service_type == ServiceType.RATE


def test_wechatmp_passive_send_closes_local_image_file_after_upload_success(monkeypatch, tmp_path):
    from bridge.reply import Reply, ReplyType

    channel = _wechatmp_channel(monkeypatch)
    image_path = tmp_path / "closed-success.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    class FakeMedia:
        def __init__(self):
            self.uploaded_file = None

        def upload(self, media_type, media):
            self.uploaded_file = media[1]
            assert not self.uploaded_file.closed
            return {"media_id": "media-success"}

    channel.client.media = FakeMedia()

    channel.send(Reply(ReplyType.IMAGE_URL, [str(image_path)]), _context())

    assert channel.client.media.uploaded_file.closed
    assert channel.cache_dict["openid"] == [("image", "media-success")]


def test_wechatmp_passive_send_closes_local_image_file_after_upload_failure(monkeypatch, tmp_path):
    from bridge.reply import Reply, ReplyType
    from wechatpy.exceptions import WeChatClientException

    channel = _wechatmp_channel(monkeypatch)
    image_path = tmp_path / "closed-failure.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    class FakeMedia:
        def __init__(self):
            self.uploaded_file = None

        def upload(self, media_type, media):
            self.uploaded_file = media[1]
            assert not self.uploaded_file.closed
            raise WeChatClientException(40001, "upload failed")

    channel.client.media = FakeMedia()

    channel.send(Reply(ReplyType.IMAGE_URL, [str(image_path)]), _context())

    assert channel.client.media.uploaded_file.closed
    assert channel.cache_dict.peek_result("openid") is None


def test_wechatmp_passive_send_reuses_uploaded_local_image_media_across_users(monkeypatch, tmp_path):
    from bridge.reply import Reply, ReplyType

    channel = _wechatmp_channel(monkeypatch)
    image_path = tmp_path / "shared.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    class FakeMedia:
        def __init__(self):
            self.calls = []

        def upload(self, media_type, media):
            self.calls.append((media_type, media[0]))
            return {"media_id": "media-shared"}

    channel.client.media = FakeMedia()

    channel.send(Reply(ReplyType.IMAGE_URL, [str(image_path)]), _context(openid="openid-1", msg_id="msg-1"))
    channel.send(Reply(ReplyType.IMAGE_URL, [str(image_path)]), _context(openid="openid-2", msg_id="msg-2"))

    assert channel.client.media.calls == [("image", "openid-1-msg-1.png")]
    assert channel.cache_dict["openid-1"] == [("image", "media-shared")]
    assert channel.cache_dict["openid-2"] == [("image", "media-shared")]


def test_wechatmp_passive_send_reuploads_local_image_when_file_changes(monkeypatch, tmp_path):
    from bridge.reply import Reply, ReplyType

    channel = _wechatmp_channel(monkeypatch)
    image_path = tmp_path / "shared.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")

    class FakeMedia:
        def __init__(self):
            self.calls = []

        def upload(self, media_type, media):
            self.calls.append((media_type, media[0]))
            return {"media_id": f"media-{len(self.calls)}"}

    channel.client.media = FakeMedia()

    channel.send(Reply(ReplyType.IMAGE_URL, [str(image_path)]), _context(openid="openid-1", msg_id="msg-1"))
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nchanged")
    channel.send(Reply(ReplyType.IMAGE_URL, [str(image_path)]), _context(openid="openid-2", msg_id="msg-2"))

    assert channel.client.media.calls == [
        ("image", "openid-1-msg-1.png"),
        ("image", "openid-2-msg-2.png"),
    ]
    assert channel.cache_dict["openid-1"] == [("image", "media-1")]
    assert channel.cache_dict["openid-2"] == [("image", "media-2")]


def test_wechatmp_passive_send_reuploads_local_image_when_content_changes_with_same_stat(monkeypatch, tmp_path):
    from bridge.reply import Reply, ReplyType
    import os

    channel = _wechatmp_channel(monkeypatch)
    image_path = tmp_path / "same-stat.png"
    image_path.write_bytes(b"image-v1")
    original_stat = image_path.stat()

    class FakeMedia:
        def __init__(self):
            self.calls = []

        def upload(self, media_type, media):
            self.calls.append((media_type, media[0]))
            return {"media_id": f"media-{len(self.calls)}"}

    channel.client.media = FakeMedia()

    channel.send(Reply(ReplyType.IMAGE_URL, [str(image_path)]), _context(openid="openid-1", msg_id="msg-1"))
    image_path.write_bytes(b"image-v2")
    os.utime(image_path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    channel.send(Reply(ReplyType.IMAGE_URL, [str(image_path)]), _context(openid="openid-2", msg_id="msg-2"))

    assert image_path.stat().st_size == original_stat.st_size
    assert getattr(image_path.stat(), "st_mtime_ns", int(image_path.stat().st_mtime * 1000000000)) == getattr(
        original_stat, "st_mtime_ns", int(original_stat.st_mtime * 1000000000)
    )
    assert channel.client.media.calls == [
        ("image", "openid-1-msg-1.png"),
        ("image", "openid-2-msg-2.png"),
    ]
    assert channel.cache_dict["openid-1"] == [("image", "media-1")]
    assert channel.cache_dict["openid-2"] == [("image", "media-2")]


def test_wechatmp_passive_send_discards_partial_images_when_later_upload_fails(monkeypatch, tmp_path):
    from bridge.reply import Reply, ReplyType
    from wechatpy.exceptions import WeChatClientException

    channel = _wechatmp_channel(monkeypatch)
    channel.running.add("openid")
    channel.technical_analysis_titles["openid"] = "天娱数科"
    images = []
    for name in ("main.png", "indicators.png"):
        path = tmp_path / name
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        images.append(str(path))

    class FakeMedia:
        def __init__(self):
            self.calls = 0

        def upload(self, media_type, media):
            self.calls += 1
            if self.calls == 2:
                raise WeChatClientException(40001, "upload failed")
            return {"media_id": "media-main"}

    channel.client.media = FakeMedia()
    channel.send(Reply(ReplyType.IMAGE_URL, images), _context())
    channel._success_callback("openid", _context())

    assert channel.cache_dict.peek_result("openid") is None
    assert "openid" not in channel.running
    assert "openid" not in channel.technical_analysis_titles


def test_wechatmp_passive_send_records_image_upload_failure(monkeypatch, tmp_path):
    from bridge.reply import Reply, ReplyType
    from wechatpy.exceptions import WeChatClientException

    channel = _wechatmp_channel(monkeypatch)
    image_path = tmp_path / "main.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    warnings = []

    class FakeMedia:
        def upload(self, media_type, media):
            raise WeChatClientException(40164, "invalid ip 14.153.6.203 ipv6 ::ffff:14.153.6.203, not in whitelist")

    channel.client.media = FakeMedia()
    monkeypatch.setattr("business.business_records.append_delivery_warning", lambda request_id, detail: warnings.append((request_id, detail)))
    reply = Reply(ReplyType.IMAGE_URL, [str(image_path)])
    reply.business_request_id = "request-1"

    channel.send(reply, _context())

    assert warnings == [
        (
            "request-1",
            "图片上传失败：Error code: 40164, message: invalid ip 14.153.6.203 ipv6 ::ffff:14.153.6.203, not in whitelist",
        )
    ]
    assert channel.cache_dict.peek_result("openid") is None


def test_wechatmp_passive_image_reply_does_not_delete_temporary_media(monkeypatch):
    import pytest
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.cache_dict = PassiveReplyCache()
            self.cache_dict.append_result("openid", "利率", [("image", "media-1")], service_type=ServiceType.RATE)
            self.running = set()
            self.request_cnt = {}

        def delete_media(self, _media_id):
            pytest.fail("temporary image media must not be deleted as permanent material")

    class FakeImageReply:
        def __init__(self, message):
            self.message = message
            self.media_id = ""

        def render(self):
            return f"<image>{self.media_id}</image>"

    now = [1000.0]

    def fake_time():
        now[0] += 1.0
        return now[0]

    fake_msg = SimpleNamespace(type="text")
    fake_wechatmp_msg = SimpleNamespace(from_user_id="openid", content="1", msg_id="msg-1")

    monkeypatch.setattr(passive_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(passive_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(passive_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(passive_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(passive_reply, "WeChatMPMessage", lambda _msg, client=None: fake_wechatmp_msg)
    monkeypatch.setattr(passive_reply, "ImageReply", FakeImageReply)
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: SimpleNamespace(allowed=True, user_prompt=""),
    )
    monkeypatch.setattr(passive_reply.web, "input", lambda: {})
    monkeypatch.setattr(passive_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        passive_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    assert passive_reply.Query().POST() == "<image>media-1</image>"


def test_wechatmp_passive_pending_image_returns_only_after_user_confirms(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    channel.cache_dict.append_result("openid", "300502.SZ 技术分析", [("image", "media-1")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    current_message = {"content": "1", "msg_id": "msg-confirm-1"}

    class FakeImageReply:
        def __init__(self, message):
            self.message = message
            self.media_id = ""

        def render(self):
            return f"<image>{self.media_id}</image>"

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(passive_reply, "ImageReply", FakeImageReply)

    assert passive_reply.Query().POST() == "<image>media-1</image>"
    assert produced_contexts == []


def test_wechatmp_passive_pending_summary_lists_targets_for_invalid_input(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(now_func=lambda: 1718445600.0), running=set(), request_cnt={})
    channel.cache_dict.append_result("openid", "天娱数科 技术分析", [("image", "media-ty-1")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    channel.cache_dict.append_result("openid", "农业银行 技术分析", [("image", "media-ny-1")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    channel.cache_dict.append_result("openid", "天娱数科 技术分析", [("image", "media-ty-2")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    current_message = {"content": "乱输", "msg_id": "msg-invalid-with-pending"}

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(passive_reply, "_reply_text", lambda _key, default="": default)

    assert passive_reply.Query().POST() == (
        "请输入：股票代码/股票名称 + 技术分析，或输入“利率”“转债”。\n\n"
        "您当前还有技术分析结果待领取：\n"
        "1.天娱数科 2条（生成时间：2024-06-15 18:00）\n"
        "2.农业银行 1条（生成时间：2024-06-15 18:00）\n"
        "回复1获取或回复股票名称获取对应报告"
    )
    assert produced_contexts == []


def test_wechatmp_passive_pending_result_can_be_selected_by_target_name(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    channel.cache_dict.append_result("openid", "天娱数科 技术分析", [("image", "media-ty")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    channel.cache_dict.append_result("openid", "农业银行 技术分析", [("image", "media-ny")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    current_message = {"content": "农业银行", "msg_id": "msg-select-target"}

    class FakeImageReply:
        def __init__(self, message):
            self.message = message
            self.media_id = ""

        def render(self):
            return f"<image>{self.media_id}</image>"

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(passive_reply, "ImageReply", FakeImageReply)

    assert passive_reply.Query().POST() == "<image>media-ny</image>"
    summary = channel.cache_dict.pending_technical_summary("openid")
    assert len(summary) == 1
    assert summary[0][:2] == ("天娱数科", 1)
    assert produced_contexts == []


def test_wechatmp_passive_pending_summary_is_appended_to_new_technical_ack(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    channel.cache_dict.append_result("openid", "农业银行 技术分析", [("image", "media-ny")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    current_message = {"content": "天娱数科 技术分析", "msg_id": "msg-new-tech-with-pending"}

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(passive_reply, "_reply_text", lambda _key, default="": default)

    response = passive_reply.Query().POST()
    assert response.startswith(
        "收到，正在处理，请稍候。请等待30-40s后回复1获取\n\n"
        "您当前还有技术分析结果待领取：\n"
        "1.农业银行 1条（生成时间："
    )
    assert response.endswith("）\n回复1获取或回复股票名称获取对应报告")
    assert [context.content for context in produced_contexts] == ["天娱数科 技术分析"]


def test_wechatmp_passive_invalidated_technical_cache_is_not_returned_by_confirm(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    channel.cache_dict.append_result(
        "openid",
        "300502.SZ 技术分析",
        [("image", "media-old")],
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        request_id="request-old",
        source_type="cache",
        source_id="cache-old",
    )
    current_message = {"content": "1", "msg_id": "msg-invalid-cache"}

    class FakeImageReply:
        def __init__(self, message):
            self.message = message
            self.media_id = ""

        def render(self):
            return f"<image>{self.media_id}</image>"

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(passive_reply, "ImageReply", FakeImageReply)
    monkeypatch.setattr(
        "business.cache_service.find_cache_entry_by_key",
        lambda _cache_key, require_files=False: None,
    )

    assert passive_reply.Query().POST() == "内容已失效，请重新发起请求。"
    assert channel.cache_dict.peek_result("openid") is None
    assert produced_contexts == []


def test_wechatmp_passive_invalidated_technical_cache_is_not_returned_by_target_name(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    channel.cache_dict.append_result(
        "openid",
        "贵州茅台 技术分析",
        [("image", "media-old")],
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        request_id="request-old",
        source_type="cache",
        source_id="cache-old",
    )
    current_message = {"content": "贵州茅台", "msg_id": "msg-invalid-cache-by-title"}

    class FakeImageReply:
        def __init__(self, message):
            self.message = message
            self.media_id = ""

        def render(self):
            return f"<image>{self.media_id}</image>"

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(passive_reply, "ImageReply", FakeImageReply)
    monkeypatch.setattr(
        "business.cache_service.find_cache_entry_by_key",
        lambda _cache_key, require_files=False: None,
    )

    assert passive_reply.Query().POST() == "内容已失效，请重新发起请求。"
    assert channel.cache_dict.peek_result("openid") is None
    assert produced_contexts == []


def test_wechatmp_passive_market_expired_technical_cache_is_not_returned_by_confirm(monkeypatch):
    import business.cache_service as cache_service
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    invalidated = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    channel.cache_dict.append_result(
        "openid",
        "贵州茅台 技术分析",
        [("image", "media-old")],
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        request_id="request-old",
        source_type="cache",
        source_id="technical_analysis:600519.SH:2026-06-14:v1",
    )
    current_message = {"content": "1", "msg_id": "msg-market-expired-cache"}

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(
        cache_service,
        "find_cache_entry_by_key",
        lambda _cache_key, require_files=True: SimpleNamespace(
            service_type=ServiceType.TECHNICAL_ANALYSIS,
            market_date="2026-06-14",
            updated_at="2026-06-14T18:00:00+08:00",
            normalized_target="600519.SH",
        ),
    )
    monkeypatch.setattr(cache_service, "technical_analysis_cache_expired_after_close", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(cache_service, "invalidate_cache_entry", lambda cache_key: invalidated.append(cache_key) or True)

    assert passive_reply.Query().POST() == "内容已失效，请重新发起请求。"
    assert channel.cache_dict.peek_result("openid") is None
    assert invalidated == ["technical_analysis:600519.SH:2026-06-14:v1"]
    assert produced_contexts == []


def test_wechatmp_passive_invalidated_daily_content_is_not_returned_by_confirm(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    channel.cache_dict.append_result(
        "openid",
        "利率",
        [("image", "media-old")],
        service_type=ServiceType.RATE,
        request_id="request-rate",
        source_type="content",
        source_id="content-old",
    )
    current_message = {"content": "1", "msg_id": "msg-invalid-content"}

    class FakeImageReply:
        def __init__(self, message):
            self.message = message
            self.media_id = ""

        def render(self):
            return f"<image>{self.media_id}</image>"

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(passive_reply, "ImageReply", FakeImageReply)
    monkeypatch.setattr(
        "business.investment.daily_content.mark_expired_daily_contents_invalidated",
        lambda: 0,
        raising=False,
    )
    monkeypatch.setattr(
        "business.business_records.get_content_record",
        lambda _content_id: SimpleNamespace(status="invalidated"),
    )

    assert passive_reply.Query().POST() == "内容已失效，请重新发起请求。"
    assert channel.cache_dict.peek_result("openid") is None
    assert produced_contexts == []


def test_wechatmp_passive_cached_result_marks_request_delivered_when_returned(monkeypatch):
    import business.business_records as business_records
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    delivered = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    channel.cache_dict.append_result(
        "openid",
        "利率",
        [("image", "media-1")],
        service_type=ServiceType.RATE,
        request_id="request-1",
    )
    current_message = {"content": "1", "msg_id": "msg-delivered-1"}

    class FakeImageReply:
        def __init__(self, message):
            self.message = message
            self.media_id = ""

        def render(self):
            return f"<image>{self.media_id}</image>"

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(passive_reply, "ImageReply", FakeImageReply)
    monkeypatch.setattr(business_records, "mark_request_delivered", lambda request_id: delivered.append(request_id), raising=False)

    assert passive_reply.Query().POST() == "<image>media-1</image>"
    assert delivered == ["request-1"]
    assert produced_contexts == []


def test_wechatmp_passive_technical_analysis_events_share_original_request_id(monkeypatch):
    import business.business_records as business_records
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache
    from business.investment.constants import ServiceType

    produced_contexts = []
    events = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    channel.cache_dict.append_result(
        "openid",
        "300502.SZ 技术分析",
        [("image", "media-1")],
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        request_id="request-ta-1",
    )
    current_message = {"content": "新请求", "msg_id": "msg-ta-prompt"}

    class FakeImageReply:
        def __init__(self, message):
            self.message = message
            self.media_id = ""

        def render(self):
            return f"<image>{self.media_id}</image>"

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(passive_reply, "ImageReply", FakeImageReply)
    monkeypatch.setattr(business_records, "mark_request_delivered", lambda _request_id: None, raising=False)
    monkeypatch.setattr(business_records, "record_request_event", lambda **kwargs: events.append(kwargs), raising=False)

    assert "回复1获取或回复股票名称获取对应报告" in passive_reply.Query().POST()
    current_message.update({"content": "1", "msg_id": "msg-ta-confirm"})
    assert passive_reply.Query().POST() == "<image>media-1</image>"

    assert [event["request_id"] for event in events] == ["request-ta-1", "request-ta-1", "request-ta-1"]
    assert [event["event_type"] for event in events] == ["pending_prompt_sent", "customer_confirm", "reply_image_sent"]


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_unauthorized_user_confirm_keeps_pending_result(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    channel.cache_dict.append_result("openid", "300502.SZ 技术分析", [("image", "media-1")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    current_message = {"content": "1", "msg_id": "msg-unauthorized-pending"}

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(
        "business.investment.user_service.verify_user_access",
        lambda _openid: SimpleNamespace(
            allowed=False,
            user_prompt="您暂未开通该服务，如需开通请联系服务人员。",
        ),
    )

    assert passive_reply.Query().POST() == "您暂未开通该服务，如需开通请联系服务人员。"
    assert channel.cache_dict.peek_result("openid").replies == [("image", "media-1")]
    assert produced_contexts == []


def test_wechatmp_passive_pending_video_returns_only_after_user_confirms(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    channel.cache_dict.append_result("openid", "300502.SZ 技术分析", [("video", "media-video")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    current_message = {"content": "1", "msg_id": "msg-confirm-video"}

    class FakeVideoReply:
        def __init__(self, message):
            self.message = message
            self.media_id = ""

        def render(self):
            return f"<video>{self.media_id}</video>"

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(passive_reply, "VideoReply", FakeVideoReply)

    assert passive_reply.Query().POST() == "<video>media-video</video>"
    assert produced_contexts == []


def test_wechatmp_passive_zero_no_longer_discards_pending_result(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    channel.cache_dict.append_result("openid", "300502.SZ 技术分析", [("image", "media-1")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    current_message = {"content": "0", "msg_id": "msg-cancel-1"}

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)

    response = passive_reply.Query().POST()
    assert response.startswith("请输入：股票代码/股票名称 + 技术分析，或输入“利率”“转债”。")
    assert channel.cache_dict.peek_result("openid") is not None
    assert produced_contexts == []


def test_wechatmp_passive_pending_result_returns_rate_without_discarding_technical_results(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel_state = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    channel_state.cache_dict.append_result("openid", "300502.SZ 技术分析", [("image", "media-1")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    current_message = {"content": "利率", "msg_id": "msg-rate-1"}

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.cache_dict = channel_state.cache_dict
            self.running = channel_state.running
            self.request_cnt = channel_state.request_cnt
            self.technical_analysis_titles = {}
            self.running_started_at = {}
            self.running_lock = passive_reply.threading.RLock()

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)

        def produce(self, context):
            produced_contexts.append(context)
            self.cache_dict.append_result("openid", context.content, [("image", "media-rate")], service_type=ServiceType.RATE)
            self.running.discard("openid")

    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    class FakeImageReply:
        def __init__(self, message):
            self.message = message
            self.media_id = ""

        def render(self):
            return f"<image>{self.media_id}</image>"

    fake_msg = SimpleNamespace(type="text")
    monkeypatch.setattr(passive_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(passive_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(passive_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(passive_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        passive_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="openid",
            content=current_message["content"],
            msg_id=current_message["msg_id"],
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(passive_reply, "create_reply", FakeReply)
    monkeypatch.setattr(passive_reply, "ImageReply", FakeImageReply)
    monkeypatch.setattr(passive_reply.web, "input", lambda: {})
    monkeypatch.setattr(passive_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        passive_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    assert passive_reply.Query().POST() == "<image>media-rate</image>"
    assert [context.content for context in produced_contexts] == ["利率"]
    summary = channel_state.cache_dict.pending_technical_summary("openid")
    assert len(summary) == 1
    assert summary[0][:2] == ("300502.SZ", 1)


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_pending_result_defers_new_technical_analysis_until_discard(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    channel.cache_dict.append_result("openid", "300502.SZ 技术分析", [("image", "media-1")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    current_message = {"content": "aa 技术分析", "msg_id": "msg-tech-1"}

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)

    assert passive_reply.Query().POST() == "「300502.SZ」技术分析已生成完成，回复 1 获取技术分析主图、技术指标表。"
    assert produced_contexts == []

    current_message["content"] = "0"
    current_message["msg_id"] = "msg-tech-2"

    assert passive_reply.Query().POST() == "已收到，正在运行「aa」技术分析，生成过程大概30s。\n生成完成后回复 1 获取技术分析主图、技术指标表。"
    assert [context.content for context in produced_contexts] == ["aa 技术分析"]


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_technical_analysis_ack_uses_route_target(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    current_message = {"content": "天娱数科 技术分析", "msg_id": "msg-tech-ack"}

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(passive_reply, "_technical_analysis_cache_hit", lambda _content: False, raising=False)

    response = passive_reply.Query().POST()

    assert response == "已收到，正在运行「天娱数科」技术分析，生成过程大概30s。\n生成完成后回复 1 获取技术分析主图、技术指标表。"
    assert "日期" not in response
    assert [context.content for context in produced_contexts] == ["天娱数科 技术分析"]


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_technical_ack_uses_configured_reply_text(investment_env, monkeypatch):
    from business.investment.config_service import save_config
    from channel.wechatmp import passive_reply

    save_config("reply.wechatmp.technical_ack", "配置提示：{} 生成中，回复1。", operator_role="admin")
    monkeypatch.setattr(passive_reply, "_technical_analysis_cache_hit", lambda _content: False, raising=False)

    assert passive_reply._investment_ack_text("天娱数科 技术分析") == "配置提示：天娱数科 生成中，回复1。"


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_cache_hit_uses_configured_reply_text(investment_env, monkeypatch):
    from business.investment.config_service import save_config
    from channel.wechatmp import passive_reply

    save_config("reply.wechatmp.technical_cache_hit", "缓存好了：{}，回复1取图。", operator_role="admin")
    monkeypatch.setattr(passive_reply, "_technical_analysis_cache_hit", lambda _content: True, raising=False)

    assert passive_reply._investment_ack_text("天娱数科 技术分析") == "缓存好了：天娱数科，回复1取图。"


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_unmatched_prompt_preserves_router_default_without_config(investment_env):
    from business.investment.router import DEFAULT_UNMATCHED_PROMPT
    from channel.wechatmp import passive_reply

    assert passive_reply._unmatched_prompt() == DEFAULT_UNMATCHED_PROMPT


def test_wechatmp_passive_pending_and_running_prompts_use_configured_reply_text(investment_env):
    from business.investment.config_service import save_config
    from channel.wechatmp import passive_reply

    save_config("reply.wechatmp.running_technical_analysis", "{} 还在跑。", operator_role="admin")
    save_config("reply.wechatmp.pending_technical_analysis", "{} 已完成，回1取，回0弃。", operator_role="admin")

    assert passive_reply._running_technical_analysis_text("农业银行") == "农业银行 还在跑。"
    assert passive_reply._pending_result_prompt("农业银行 技术分析") == "农业银行 已完成，回1取，回0弃。"


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_cached_technical_analysis_hit_can_be_pulled_with_one(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel_state = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    current_message = {"content": "天娱数科 技术分析", "msg_id": "msg-tech-cache-hit"}

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.cache_dict = channel_state.cache_dict
            self.running = channel_state.running
            self.request_cnt = channel_state.request_cnt
            self.technical_analysis_titles = {}
            self.running_started_at = {}
            self.running_lock = passive_reply.threading.RLock()

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)

        def produce(self, context):
            produced_contexts.append(context)
            self.cache_dict.append_result(
                "openid",
                context.content,
                [("image", "media-signal-card"), ("image", "media-main-chart")],
                service_type=ServiceType.TECHNICAL_ANALYSIS,
                request_id="request-cache-hit",
            )
            self.running.discard("openid")

    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    class FakeImageReply:
        def __init__(self, message):
            self.message = message
            self.media_id = ""

        def render(self):
            return f"<image>{self.media_id}</image>"

    fake_msg = SimpleNamespace(type="text")
    monkeypatch.setattr(passive_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(passive_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(passive_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(passive_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        passive_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="openid",
            content=current_message["content"],
            msg_id=current_message["msg_id"],
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(passive_reply, "create_reply", FakeReply)
    monkeypatch.setattr(passive_reply, "ImageReply", FakeImageReply)
    monkeypatch.setattr(passive_reply, "_technical_analysis_cache_hit", lambda _content: True, raising=False)
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: SimpleNamespace(allowed=True, user_prompt=""),
    )
    monkeypatch.setattr(passive_reply.web, "input", lambda: {})
    monkeypatch.setattr(passive_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        passive_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    assert passive_reply.Query().POST() == "已命中「天娱数科」技术分析缓存，正在直接交付。\n回复 1 获取技术分析主图、技术指标表。"

    current_message["content"] = "1"
    current_message["msg_id"] = "msg-tech-cache-hit-confirm"

    assert passive_reply.Query().POST() == "<image>media-signal-card</image>"
    assert channel_state.cache_dict.peek_result("openid").replies == [("image", "media-main-chart")]
    assert [context.content for context in produced_contexts] == ["天娱数科 技术分析"]


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_cache_miss_returns_running_ack(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel_state = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    current_message = {"content": "天娱数科 技术分析", "msg_id": "msg-tech-cache-miss"}

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.cache_dict = channel_state.cache_dict
            self.running = channel_state.running
            self.request_cnt = channel_state.request_cnt
            self.technical_analysis_titles = {}
            self.running_started_at = {}
            self.running_lock = passive_reply.threading.RLock()

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)

        def produce(self, context):
            produced_contexts.append(context)

    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    fake_msg = SimpleNamespace(type="text")
    monkeypatch.setattr(passive_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(passive_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(passive_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(passive_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        passive_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="openid",
            content=current_message["content"],
            msg_id=current_message["msg_id"],
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(passive_reply, "create_reply", FakeReply)
    monkeypatch.setattr(passive_reply, "_technical_analysis_cache_hit", lambda _content: False, raising=False)
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: SimpleNamespace(allowed=True, user_prompt=""),
    )
    monkeypatch.setattr(passive_reply.web, "input", lambda: {})
    monkeypatch.setattr(passive_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        passive_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    response = passive_reply.Query().POST()

    assert response == "已收到，正在运行「天娱数科」技术分析，生成过程大概30s。\n生成完成后回复 1 获取技术分析主图、技术指标表。"
    assert [context.content for context in produced_contexts] == ["天娱数科 技术分析"]
    assert "openid" in channel_state.running


def test_wechatmp_passive_running_technical_analysis_confirm_prompts_retry(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running={"openid"}, request_cnt={})
    current_message = {"content": "1", "msg_id": "msg-tech-running-confirm"}

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    channel.technical_analysis_titles = {"openid": "天娱数科"}

    assert passive_reply.Query().POST() == "「天娱数科」技术分析仍在运行中，请稍后再回复 1 尝试获取。"
    assert produced_contexts == []


def test_wechatmp_passive_running_technical_analysis_rejects_new_technical_request(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(
        cache_dict=PassiveReplyCache(),
        running={"openid"},
        request_cnt={},
        technical_analysis_titles={"openid": "天娱数科"},
    )
    current_message = {"content": "农业银行 技术分析", "msg_id": "msg-tech-running-new-request"}

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(passive_reply, "_reply_text", lambda _key, default="": default)

    assert passive_reply.Query().POST() == (
        "「天娱数科」技术分析仍在运行中，请稍后回复1获取结果。\n"
        "当前暂不接受新的技术分析请求，请在结果领取后再发起新的技术分析。"
    )
    assert produced_contexts == []


def test_wechatmp_passive_pending_technical_analysis_images_are_returned_one_per_confirm(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    channel.cache_dict.append_result(
        "openid",
        "天娱数科 技术分析",
        [("image", "media-main"), ("image", "media-indicators")],
        service_type=ServiceType.TECHNICAL_ANALYSIS,
    )
    current_message = {"content": "1", "msg_id": "msg-confirm-image-1"}

    class FakeImageReply:
        def __init__(self, message):
            self.message = message
            self.media_id = ""

        def render(self):
            return f"<image>{self.media_id}</image>"

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(passive_reply, "ImageReply", FakeImageReply)

    assert passive_reply.Query().POST() == "<image>media-main</image>"
    assert channel.cache_dict.peek_result("openid").replies == [("image", "media-indicators")]

    current_message["msg_id"] = "msg-confirm-image-2"

    assert passive_reply.Query().POST() == "<image>media-indicators</image>"
    assert channel.cache_dict.peek_result("openid") is None
    assert produced_contexts == []


def test_wechatmp_passive_expired_result_is_not_returned_by_confirm(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    now = [1000.0]
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(now_func=lambda: now[0]), running=set(), request_cnt={})
    channel.cache_dict.append_result("openid", "300502.SZ 技术分析", [("image", "media-1")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    now[0] += 12 * 60 * 60 + 1
    current_message = {"content": "1", "msg_id": "msg-expired-1"}

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)

    response = passive_reply.Query().POST()

    assert response == "success"
    assert channel.cache_dict.peek_result("openid") is None
    assert [context.content for context in produced_contexts] == ["1"]


def test_wechatmp_passive_one_without_pending_result_uses_normal_request_path(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    composed_contexts = []
    channel_state = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.cache_dict = channel_state.cache_dict
            self.running = channel_state.running
            self.request_cnt = channel_state.request_cnt

        def _compose_context(self, ctype, content, **kwargs):
            context = SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)
            composed_contexts.append(context)
            return context

        def produce(self, context):
            produced_contexts.append(context)
            self.running.discard("openid")

    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    fake_msg = SimpleNamespace(type="text")
    monkeypatch.setattr(passive_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(passive_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(passive_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(passive_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        passive_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="openid",
            content="1",
            msg_id="msg-no-pending-one",
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(passive_reply, "create_reply", FakeReply)
    monkeypatch.setattr(passive_reply, "_technical_analysis_cache_hit", lambda _content: False, raising=False)
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: SimpleNamespace(allowed=True, user_prompt=""),
    )
    monkeypatch.setattr(passive_reply.web, "input", lambda: {})
    monkeypatch.setattr(passive_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        passive_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    response = passive_reply.Query().POST()

    assert response == "success"
    assert [context.content for context in composed_contexts] == ["1"]
    assert [context.content for context in produced_contexts] == ["1"]


def test_wechatmp_passive_new_technical_analysis_returns_immediate_ack(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel_state = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    current_message = {"content": "天娱数科 技术分析", "msg_id": "msg-new-tech-immediate-ack"}

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.cache_dict = channel_state.cache_dict
            self.running = channel_state.running
            self.request_cnt = channel_state.request_cnt
            self.technical_analysis_titles = {}
            self.running_started_at = {}
            self.running_lock = passive_reply.threading.RLock()

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)

        def produce(self, context):
            produced_contexts.append(context)

    _fake_passive_post(monkeypatch, passive_reply, channel_state, current_message, produced_contexts)
    monkeypatch.setattr(passive_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(passive_reply, "_reply_text", lambda _key, default="": default)

    assert passive_reply.Query().POST() == "收到，正在处理，请稍候。请等待30-40s后回复1获取"
    assert [context.content for context in produced_contexts] == ["天娱数科 技术分析"]
    assert "openid" in channel_state.running


def test_wechatmp_passive_ready_technical_result_returns_claim_prompt_without_starting_generation(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel_state = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    current_message = {"content": "天娱数科 技术分析", "msg_id": "msg-tech-ready"}

    _fake_passive_post(monkeypatch, passive_reply, channel_state, current_message, produced_contexts)
    monkeypatch.setattr(passive_reply, "_reply_text", lambda _key, default="": default)
    monkeypatch.setattr(passive_reply, "_queue_ready_technical_result", lambda *_args, **_kwargs: True)

    assert passive_reply.Query().POST() == "「天娱数科」技术分析结果已准备好，回复1获取。"
    assert produced_contexts == []
    assert "openid" not in channel_state.running


def test_wechatmp_passive_ready_technical_result_queues_files_without_uploading(monkeypatch, tmp_path):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache
    from business.router import BusinessReply

    image_path = tmp_path / "ready.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), sent=[])
    msg = SimpleNamespace(from_user_id="openid", content="601398.SH 技术分析", ctype=SimpleNamespace())
    route = SimpleNamespace(raw_input="601398.SH 技术分析", service_type=ServiceType.TECHNICAL_ANALYSIS)

    def fail_send(*_args, **_kwargs):
        raise AssertionError("ready prompt must not upload images before replying")

    channel.send = fail_send
    monkeypatch.setattr(
        "business.technical_analysis_handler.get_ready_technical_analysis_reply",
        lambda *_args, **_kwargs: BusinessReply(
            handled=True,
            success=True,
            reply_text="ready",
            output_files=[str(image_path)],
            service_type=ServiceType.TECHNICAL_ANALYSIS,
            request_id="ready-request",
            source_type="cache",
            source_id="ready-cache",
        ),
    )
    monkeypatch.setattr("business.router._customer_metadata", lambda _openid: {})

    assert passive_reply._queue_ready_technical_result(channel, msg, route) is True
    cached = channel.cache_dict.peek_result("openid")
    assert cached.request_id == "ready-request"
    assert cached.source_type == "cache"
    assert cached.source_id == "ready-cache"
    assert cached.replies == [("image_file", str(image_path))]


def test_wechatmp_passive_render_image_file_uploads_on_claim(monkeypatch, tmp_path):
    import channel.wechatmp.passive_reply as passive_reply
    import channel.wechatmp.wechatmp_channel as wechatmp_channel

    image_path = tmp_path / "claim.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    channel = _wechatmp_channel(monkeypatch)

    class FakeMedia:
        def __init__(self):
            self.uploaded_file = None

        def upload(self, media_type, media):
            assert media_type == "image"
            self.uploaded_file = media[1]
            assert not self.uploaded_file.closed
            return {"media_id": "media-claim"}

    class FakeImageReply:
        def __init__(self, message):
            self.message = message
            self.media_id = ""

        def render(self):
            return f"<image>{self.media_id}</image>"

    channel.client.media = FakeMedia()
    monkeypatch.setattr(passive_reply, "ImageReply", FakeImageReply)

    rendered = passive_reply._render_cached_reply(
        channel,
        SimpleNamespace(),
        lambda value: value,
        "openid",
        "msg-claim",
        "1",
        1,
        ("image_file", str(image_path)),
        cache_title="601398.SH 技术分析",
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        request_id="request-claim",
    )

    assert rendered == "<image>media-claim</image>"
    assert channel.client.media.uploaded_file.closed
    assert wechatmp_channel.image_media_cache.get(wechatmp_channel.local_image_media_key(str(image_path))) == "media-claim"


def test_wechatmp_passive_technical_analysis_precheck_error_returns_failure_without_ack(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    import business.investment.technical_analysis as technical_analysis
    from business.investment.constants import ErrorCode
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel_state = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    current_message = {"content": "农业银行 技术分析", "msg_id": "msg-tech-ambiguous"}

    _fake_passive_post(monkeypatch, passive_reply, channel_state, current_message, produced_contexts)
    monkeypatch.setattr(passive_reply, "_reply_text", lambda _key, default="": default)
    monkeypatch.setattr(
        technical_analysis,
        "resolve_stock",
        lambda _target, auto_refresh_on_miss=True: (None, ErrorCode.STOCK_AMBIGUOUS),
    )
    monkeypatch.setattr(
        technical_analysis,
        "list_exact_stock_name_matches",
        lambda _target: [
            {"code": "01288.HK", "name": "农业银行", "market": "HK"},
            {"code": "601288.SH", "name": "农业银行", "market": "SH"},
        ],
    )

    response = passive_reply.Query().POST()

    assert response == (
        "股票名称匹配到多个标的，请改用股票代码。\n"
        "原因：股票名称“农业银行”匹配到多个标的，请改用股票代码重新发送：\n"
        "1. 01288.HK 农业银行（HK）\n"
        "2. 601288.SH 农业银行（SH）\n"
        "例如：601288.SH 技术分析"
    )
    assert produced_contexts == []
    assert "openid" not in channel_state.running


def test_wechatmp_immediate_ack_replaces_empty_pending_summary_placeholder(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    monkeypatch.setattr(
        passive_reply,
        "_reply_text",
        lambda _key, default="": "收到，正在处理，请稍候。请等待30-40s后回复1获取\n{pending_summary}",
    )

    assert passive_reply._immediate_ack_text(PassiveReplyCache(), "openid") == "收到，正在处理，请稍候。请等待30-40s后回复1获取"


def test_wechatmp_passive_rate_and_bond_return_ready_image_without_running_ack(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel_state = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.cache_dict = channel_state.cache_dict
            self.running = channel_state.running
            self.request_cnt = channel_state.request_cnt

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)

        def produce(self, context):
            produced_contexts.append(context)
            service_type = ServiceType.RATE if context.content == "利率" else ServiceType.CONVERTIBLE_BOND
            self.cache_dict.append_result("openid", context.content, [("image", f"media-{context.content}")], service_type=service_type)
            self.running.discard("openid")

    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    class FakeImageReply:
        def __init__(self, message):
            self.message = message
            self.media_id = ""

        def render(self):
            return f"<image>{self.media_id}</image>"

    now = [1000.0]

    def fake_time():
        now[0] += 1.0
        return now[0]

    fake_msg = SimpleNamespace(type="text")
    current_message = {"content": "利率", "msg_id": "msg-ack-1"}

    monkeypatch.setattr(passive_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(passive_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(passive_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(passive_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        passive_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="openid",
            content=current_message["content"],
            msg_id=current_message["msg_id"],
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(passive_reply, "create_reply", FakeReply)
    monkeypatch.setattr(passive_reply, "ImageReply", FakeImageReply)
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: SimpleNamespace(allowed=True, user_prompt=""),
    )
    monkeypatch.setattr(passive_reply.web, "input", lambda: {})
    monkeypatch.setattr(passive_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        passive_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    cases = (
        ("利率", "<image>media-利率</image>"),
        ("转债", "<image>media-转债</image>"),
    )
    for index, (content, expected) in enumerate(cases, start=1):
        current_message["content"] = content
        current_message["msg_id"] = f"msg-ack-{index}"
        response = passive_reply.Query().POST()

        assert response == expected

    assert [context.content for context in produced_contexts] == ["利率", "转债"]


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_rate_ready_between_retries_returns_image_without_confirm(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel_state = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    current_message = {"content": "利率", "msg_id": "msg-rate-ready-between"}

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.cache_dict = channel_state.cache_dict
            self.running = channel_state.running
            self.request_cnt = channel_state.request_cnt

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)

        def produce(self, context):
            produced_contexts.append(context)

    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    class FakeImageReply:
        def __init__(self, message):
            self.message = message
            self.media_id = ""

        def render(self):
            return f"<image>{self.media_id}</image>"

    now = [1000.0]

    def fake_time():
        now[0] += 1.0
        return now[0]

    fake_msg = SimpleNamespace(type="text")
    monkeypatch.setattr(passive_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(passive_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(passive_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(passive_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        passive_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="openid",
            content=current_message["content"],
            msg_id=current_message["msg_id"],
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(passive_reply, "create_reply", FakeReply)
    monkeypatch.setattr(passive_reply, "ImageReply", FakeImageReply)
    monkeypatch.setattr(passive_reply.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(passive_reply.time, "time", fake_time)
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: SimpleNamespace(allowed=True, user_prompt=""),
    )
    monkeypatch.setattr(passive_reply.web, "input", lambda: {})
    monkeypatch.setattr(passive_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        passive_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    assert passive_reply.Query().POST() == "success"

    channel_state.cache_dict.append_result("openid", "利率", [("image", "media-rate")], service_type=ServiceType.RATE)
    channel_state.running.discard("openid")

    assert passive_reply.Query().POST() == "<image>media-rate</image>"
    assert [context.content for context in produced_contexts] == ["利率"]
    assert channel_state.cache_dict.peek_result("openid") is None


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_rate_ready_between_retries_rechecks_permission_before_pop(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel_state = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    current_message = {"content": "利率", "msg_id": "msg-rate-ready-denied"}
    permission_calls = []

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.cache_dict = channel_state.cache_dict
            self.running = channel_state.running
            self.request_cnt = channel_state.request_cnt

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)

        def produce(self, context):
            produced_contexts.append(context)

    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    def fake_verify(_openid, service_type):
        permission_calls.append(service_type)
        if len(permission_calls) == 1:
            return SimpleNamespace(allowed=True, user_prompt="")
        return SimpleNamespace(allowed=False, user_prompt="您的服务已停用，如需恢复请联系服务人员。")

    now = [1000.0]

    def fake_time():
        now[0] += 1.0
        return now[0]

    fake_msg = SimpleNamespace(type="text")
    monkeypatch.setattr(passive_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(passive_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(passive_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(passive_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        passive_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="openid",
            content=current_message["content"],
            msg_id=current_message["msg_id"],
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(passive_reply, "create_reply", FakeReply)
    monkeypatch.setattr(passive_reply.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(passive_reply.time, "time", fake_time)
    monkeypatch.setattr("business.investment.user_service.verify_permission", fake_verify)
    monkeypatch.setattr(passive_reply.web, "input", lambda: {})
    monkeypatch.setattr(passive_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        passive_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    assert passive_reply.Query().POST() == "success"

    channel_state.cache_dict.append_result("openid", "利率", [("image", "media-rate")], service_type=ServiceType.RATE)
    channel_state.running.discard("openid")

    assert passive_reply.Query().POST() == "您的服务已停用，如需恢复请联系服务人员。"
    assert channel_state.cache_dict.peek_result("openid").replies == [("image", "media-rate")]
    assert len(permission_calls) == 2


def test_wechatmp_passive_rate_retry_returns_image_when_cache_ready_on_second_request(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel_state = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    current_message = {"content": "利率", "msg_id": "msg-rate-retry-2"}
    sleep_calls = []

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.cache_dict = channel_state.cache_dict
            self.running = channel_state.running
            self.request_cnt = channel_state.request_cnt

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)

        def produce(self, context):
            produced_contexts.append(context)

    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    class FakeImageReply:
        def __init__(self, message):
            self.message = message
            self.media_id = ""

        def render(self):
            return f"<image>{self.media_id}</image>"

    def fake_sleep(seconds):
        sleep_calls.append(seconds)
        if channel_state.request_cnt.get("msg-rate-retry-2") == 2 and "openid" in channel_state.running:
            channel_state.cache_dict.append_result("openid", "利率", [("image", "media-rate")], service_type=ServiceType.RATE)
            channel_state.running.discard("openid")

    fake_msg = SimpleNamespace(type="text")
    monkeypatch.setattr(passive_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(passive_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(passive_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(passive_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        passive_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="openid",
            content=current_message["content"],
            msg_id=current_message["msg_id"],
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(passive_reply, "create_reply", FakeReply)
    monkeypatch.setattr(passive_reply, "ImageReply", FakeImageReply)
    now = [1000.0]

    def fake_time():
        now[0] += 1.0
        return now[0]

    monkeypatch.setattr(passive_reply.time, "sleep", fake_sleep)
    monkeypatch.setattr(passive_reply.time, "time", fake_time)
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: SimpleNamespace(allowed=True, user_prompt=""),
    )
    monkeypatch.setattr(passive_reply.web, "input", lambda: {})
    monkeypatch.setattr(passive_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        passive_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    assert passive_reply.Query().POST() == "success"
    assert passive_reply.Query().POST() == "<image>media-rate</image>"
    assert [context.content for context in produced_contexts] == ["利率"]
    assert channel_state.request_cnt == {}
    assert sleep_calls


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_auto_wait_rechecks_permission_before_pop(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel_state = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    current_message = {"content": "利率", "msg_id": "msg-rate-wait-denied"}
    permission_calls = []

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.cache_dict = channel_state.cache_dict
            self.running = channel_state.running
            self.request_cnt = channel_state.request_cnt

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)

        def produce(self, context):
            produced_contexts.append(context)

    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    def fake_sleep(_seconds):
        if "openid" in channel_state.running:
            channel_state.cache_dict.append_result("openid", "利率", [("image", "media-rate")], service_type=ServiceType.RATE)
            channel_state.running.discard("openid")

    def fake_verify(_openid, service_type):
        permission_calls.append(service_type)
        if len(permission_calls) == 1:
            return SimpleNamespace(allowed=True, user_prompt="")
        return SimpleNamespace(allowed=False, user_prompt="您的服务已停用，如需恢复请联系服务人员。")

    now = [1000.0]

    def fake_time():
        now[0] += 1.0
        return now[0]

    fake_msg = SimpleNamespace(type="text")
    monkeypatch.setattr(passive_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(passive_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(passive_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(passive_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        passive_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="openid",
            content=current_message["content"],
            msg_id=current_message["msg_id"],
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(passive_reply, "create_reply", FakeReply)
    monkeypatch.setattr(passive_reply.time, "sleep", fake_sleep)
    monkeypatch.setattr(passive_reply.time, "time", lambda: 1000.0)
    monkeypatch.setattr("business.investment.user_service.verify_permission", fake_verify)
    monkeypatch.setattr(passive_reply.web, "input", lambda: {})
    monkeypatch.setattr(passive_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        passive_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    assert passive_reply.Query().POST() == "您的服务已停用，如需恢复请联系服务人员。"
    assert channel_state.cache_dict.peek_result("openid").replies == [("image", "media-rate")]
    assert [context.content for context in produced_contexts] == ["利率"]
    assert len(permission_calls) == 2


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_auto_wait_permission_error_does_not_pop(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel_state = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    current_message = {"content": "利率", "msg_id": "msg-rate-wait-permission-error"}
    permission_calls = []

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.cache_dict = channel_state.cache_dict
            self.running = channel_state.running
            self.request_cnt = channel_state.request_cnt

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)

        def produce(self, context):
            produced_contexts.append(context)

    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    def fake_sleep(_seconds):
        if "openid" in channel_state.running:
            channel_state.cache_dict.append_result("openid", "利率", [("image", "media-rate")], service_type=ServiceType.RATE)
            channel_state.running.discard("openid")

    def fake_verify(_openid, _service_type):
        permission_calls.append(_service_type)
        if len(permission_calls) == 1:
            return SimpleNamespace(allowed=True, user_prompt="")
        raise RuntimeError("permission db unavailable")

    fake_msg = SimpleNamespace(type="text")
    monkeypatch.setattr(passive_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(passive_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(passive_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(passive_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        passive_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="openid",
            content=current_message["content"],
            msg_id=current_message["msg_id"],
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(passive_reply, "create_reply", FakeReply)
    monkeypatch.setattr(passive_reply.time, "sleep", fake_sleep)
    monkeypatch.setattr(passive_reply.time, "time", lambda: 1000.0)
    monkeypatch.setattr("business.investment.user_service.verify_permission", fake_verify)
    monkeypatch.setattr(passive_reply.web, "input", lambda: {})
    monkeypatch.setattr(passive_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        passive_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    assert passive_reply.Query().POST() == "系统暂时繁忙，请稍后重试。"
    assert channel_state.cache_dict.peek_result("openid").replies == [("image", "media-rate")]
    assert len(permission_calls) == 2


def test_wechatmp_passive_bond_retry_returns_image_when_cache_ready_on_third_request(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel_state = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    current_message = {"content": "转债", "msg_id": "msg-bond-retry-3"}

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.cache_dict = channel_state.cache_dict
            self.running = channel_state.running
            self.request_cnt = channel_state.request_cnt

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)

        def produce(self, context):
            produced_contexts.append(context)

    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    class FakeImageReply:
        def __init__(self, message):
            self.message = message
            self.media_id = ""

        def render(self):
            return f"<image>{self.media_id}</image>"

    def fake_sleep(_seconds):
        if channel_state.request_cnt.get("msg-bond-retry-3") == 3 and "openid" in channel_state.running:
            channel_state.cache_dict.append_result("openid", "转债", [("image", "media-bond")], service_type=ServiceType.CONVERTIBLE_BOND)
            channel_state.running.discard("openid")

    fake_msg = SimpleNamespace(type="text")
    monkeypatch.setattr(passive_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(passive_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(passive_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(passive_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        passive_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="openid",
            content=current_message["content"],
            msg_id=current_message["msg_id"],
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(passive_reply, "create_reply", FakeReply)
    monkeypatch.setattr(passive_reply, "ImageReply", FakeImageReply)
    now = [1000.0]

    def fake_time():
        now[0] += 1.0
        return now[0]

    monkeypatch.setattr(passive_reply.time, "sleep", fake_sleep)
    monkeypatch.setattr(passive_reply.time, "time", fake_time)
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: SimpleNamespace(allowed=True, user_prompt=""),
    )
    monkeypatch.setattr(passive_reply.web, "input", lambda: {})
    monkeypatch.setattr(passive_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        passive_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    assert passive_reply.Query().POST() == "success"
    assert passive_reply.Query().POST() == "success"
    assert passive_reply.Query().POST() == "<image>media-bond</image>"
    assert [context.content for context in produced_contexts] == ["转债"]
    assert channel_state.request_cnt == {}


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_technical_analysis_does_not_wait_for_ready_image(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel_state = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    current_message = {"content": "天娱数科 技术分析", "msg_id": "msg-tech-no-wait"}

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.cache_dict = channel_state.cache_dict
            self.running = channel_state.running
            self.request_cnt = channel_state.request_cnt
            self.technical_analysis_titles = {}

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)

        def produce(self, context):
            produced_contexts.append(context)
            self.cache_dict.append_result("openid", context.content, [("image", "media-tech")], service_type=ServiceType.TECHNICAL_ANALYSIS)
            self.running.discard("openid")

    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    fake_msg = SimpleNamespace(type="text")
    monkeypatch.setattr(passive_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(passive_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(passive_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(passive_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        passive_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="openid",
            content=current_message["content"],
            msg_id=current_message["msg_id"],
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(passive_reply, "create_reply", FakeReply)
    monkeypatch.setattr(passive_reply, "_technical_analysis_cache_hit", lambda _content: False, raising=False)
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: SimpleNamespace(allowed=True, user_prompt=""),
    )
    monkeypatch.setattr(passive_reply.web, "input", lambda: {})
    monkeypatch.setattr(passive_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        passive_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    assert passive_reply.Query().POST() == "已收到，正在运行「天娱数科」技术分析，生成过程大概30s。\n生成完成后回复 1 获取技术分析主图、技术指标表。"
    assert channel_state.cache_dict.peek_result("openid").replies == [("image", "media-tech")]
    assert [context.content for context in produced_contexts] == ["天娱数科 技术分析"]


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_permission_error_does_not_start_investment_generation(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    current_message = {"content": "利率", "msg_id": "msg-permission-error"}

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )

    assert passive_reply.Query().POST() == "系统暂时繁忙，请稍后重试。"
    assert produced_contexts == []
    assert "openid" not in channel.running


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_permission_prompt_records_failed_precheck(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from business.investment.constants import ErrorCode

    calls = []
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: SimpleNamespace(
            allowed=False,
            error_code=ErrorCode.UNAUTHORIZED,
            user_prompt="您暂未开通该服务，如需开通请联系服务人员。",
            detail="permission denied",
        ),
    )
    monkeypatch.setattr(
        "business.business_records.create_request_record",
        lambda *args, **_kwargs: calls.append(("create", args)) or "request-id",
    )
    monkeypatch.setattr(
        "business.business_records.fail_request_record",
        lambda *args, **_kwargs: calls.append(("fail", args)),
    )

    prompt = passive_reply._investment_permission_prompt("openid", "利率")

    assert prompt == "您暂未开通该服务，如需开通请联系服务人员。"
    assert calls[0] == ("create", ("openid", "利率", ServiceType.UNAUTHORIZED_REQUEST))
    assert calls[1][0] == "fail"
    assert calls[1][1][0] == "request-id"
    assert calls[1][1][1] == ErrorCode.UNAUTHORIZED


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_permission_denied_records_are_deduped_by_message_key(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from business.investment.constants import ErrorCode

    calls = []
    passive_reply._permission_denied_record_keys.clear()
    permission = SimpleNamespace(
        allowed=False,
        error_code=ErrorCode.UNAUTHORIZED,
        user_prompt="无权限",
        detail="permission denied",
    )
    monkeypatch.setattr(
        "business.business_records.create_request_record",
        lambda *args, **_kwargs: calls.append(("create", args)) or "request-id",
    )
    monkeypatch.setattr(
        "business.business_records.fail_request_record",
        lambda *args, **_kwargs: calls.append(("fail", args)),
    )

    passive_reply._record_permission_denied_request("openid", "利率", permission, dedupe_key="msg-1")
    passive_reply._record_permission_denied_request("openid", "利率", permission, dedupe_key="msg-1")

    assert [call[0] for call in calls] == ["create", "fail"]


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_cached_result_permission_prompt_records_failed_precheck(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from business.investment.constants import ErrorCode
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    calls = []
    cache = PassiveReplyCache()
    cache.append_result(
        "openid",
        "利率",
        [("image", "media-rate")],
        service_type=ServiceType.RATE,
        request_id="request-rate",
    )
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: SimpleNamespace(
            allowed=False,
            error_code=ErrorCode.UNAUTHORIZED,
            user_prompt="您暂未开通该服务，如需开通请联系服务人员。",
            detail="permission denied",
        ),
    )
    monkeypatch.setattr(
        "business.business_records.create_request_record",
        lambda *args, **_kwargs: calls.append(("create", args)) or "request-id",
    )
    monkeypatch.setattr(
        "business.business_records.fail_request_record",
        lambda *args, **_kwargs: calls.append(("fail", args)),
    )

    prompt = passive_reply._permission_prompt_for_cached_result(
        "openid",
        cache.peek_result("openid"),
        "1",
        dedupe_key="cached-msg-1",
    )

    assert prompt == "您暂未开通该服务，如需开通请联系服务人员。"
    assert calls[0] == ("create", ("openid", "利率", ServiceType.UNAUTHORIZED_REQUEST))
    assert calls[1][0] == "fail"
    assert calls[1][1][1] == ErrorCode.UNAUTHORIZED


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_user_access_permission_prompt_records_failed_precheck_with_empty_input(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from business.investment.constants import ErrorCode

    calls = []
    monkeypatch.setattr(
        "business.investment.user_service.verify_user_access",
        lambda _openid: SimpleNamespace(
            allowed=False,
            error_code=ErrorCode.USER_DISABLED,
            user_prompt="您的服务已停用，如需恢复请联系服务人员。",
            detail="user disabled",
        ),
    )
    monkeypatch.setattr(
        "business.business_records.create_request_record",
        lambda *args, **_kwargs: calls.append(("create", args)) or "request-id",
    )
    monkeypatch.setattr(
        "business.business_records.fail_request_record",
        lambda *args, **_kwargs: calls.append(("fail", args)),
    )

    prompt = passive_reply._investment_user_access_prompt("openid")

    assert prompt == "您的服务已停用，如需恢复请联系服务人员。"
    assert calls[0] == ("create", ("openid", "", ServiceType.UNAUTHORIZED_REQUEST))
    assert calls[1][0] == "fail"
    assert calls[1][1][0] == "request-id"
    assert calls[1][1][1] == ErrorCode.USER_DISABLED


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_active_permission_prompt_records_failed_precheck(monkeypatch):
    import channel.wechatmp.active_reply as active_reply
    from business.investment.constants import ErrorCode

    calls = []
    route = SimpleNamespace(matched=True, service_type=ServiceType.RATE, raw_input="利率")
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: SimpleNamespace(
            allowed=False,
            error_code=ErrorCode.UNAUTHORIZED,
            user_prompt="您暂未开通该服务，如需开通请联系服务人员。",
            detail="permission denied",
        ),
    )
    monkeypatch.setattr(
        "business.business_records.create_request_record",
        lambda *args, **_kwargs: calls.append(("create", args)) or "request-id",
    )
    monkeypatch.setattr(
        "business.business_records.fail_request_record",
        lambda *args, **_kwargs: calls.append(("fail", args)),
    )

    prompt = active_reply._investment_permission_prompt("openid", route)

    assert prompt == "您暂未开通该服务，如需开通请联系服务人员。"
    assert calls[0] == ("create", ("openid", "利率", ServiceType.UNAUTHORIZED_REQUEST))
    assert calls[1][0] == "fail"
    assert calls[1][1][0] == "request-id"
    assert calls[1][1][1] == ErrorCode.UNAUTHORIZED


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_active_permission_denied_records_are_deduped_by_message_key(monkeypatch):
    import channel.wechatmp.active_reply as active_reply
    from business.investment.constants import ErrorCode

    calls = []
    active_reply._permission_denied_record_keys.clear()
    permission = SimpleNamespace(
        allowed=False,
        error_code=ErrorCode.UNAUTHORIZED,
        user_prompt="无权限",
        detail="permission denied",
    )
    monkeypatch.setattr(
        "business.business_records.create_request_record",
        lambda *args, **_kwargs: calls.append(("create", args)) or "request-id",
    )
    monkeypatch.setattr(
        "business.business_records.fail_request_record",
        lambda *args, **_kwargs: calls.append(("fail", args)),
    )

    active_reply._record_permission_denied_request("openid", "利率", permission, dedupe_key="msg-1")
    active_reply._record_permission_denied_request("openid", "利率", permission, dedupe_key="msg-1")

    assert [call[0] for call in calls] == ["create", "fail"]


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_permission_denied_record_retries_after_write_failure(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from business.investment.constants import ErrorCode

    calls = []
    passive_reply._permission_denied_record_keys.clear()
    permission = SimpleNamespace(
        allowed=False,
        error_code=ErrorCode.UNAUTHORIZED,
        user_prompt="无权限",
        detail="permission denied",
    )

    def fake_create(*args, **_kwargs):
        calls.append(("create", args))
        if len(calls) == 1:
            raise RuntimeError("database unavailable")
        return "request-id"

    monkeypatch.setattr("business.business_records.create_request_record", fake_create)
    monkeypatch.setattr(
        "business.business_records.fail_request_record",
        lambda *args, **_kwargs: calls.append(("fail", args)),
    )

    passive_reply._record_permission_denied_request("openid", "利率", permission, dedupe_key="msg-1")
    passive_reply._record_permission_denied_request("openid", "利率", permission, dedupe_key="msg-1")

    assert [call[0] for call in calls] == ["create", "create", "fail"]


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_active_permission_denied_record_retries_after_write_failure(monkeypatch):
    import channel.wechatmp.active_reply as active_reply
    from business.investment.constants import ErrorCode

    calls = []
    active_reply._permission_denied_record_keys.clear()
    permission = SimpleNamespace(
        allowed=False,
        error_code=ErrorCode.UNAUTHORIZED,
        user_prompt="无权限",
        detail="permission denied",
    )

    def fake_create(*args, **_kwargs):
        calls.append(("create", args))
        if len(calls) == 1:
            raise RuntimeError("database unavailable")
        return "request-id"

    monkeypatch.setattr("business.business_records.create_request_record", fake_create)
    monkeypatch.setattr(
        "business.business_records.fail_request_record",
        lambda *args, **_kwargs: calls.append(("fail", args)),
    )

    active_reply._record_permission_denied_request("openid", "利率", permission, dedupe_key="msg-1")
    active_reply._record_permission_denied_request("openid", "利率", permission, dedupe_key="msg-1")

    assert [call[0] for call in calls] == ["create", "create", "fail"]


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_pending_result_confirm_rechecks_permission_before_pop(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    channel.cache_dict.append_result("openid", "天娱数科 技术分析", [("image", "media-tech")], service_type=ServiceType.TECHNICAL_ANALYSIS)
    current_message = {"content": "1", "msg_id": "msg-disabled-confirm"}

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: SimpleNamespace(
            allowed=False,
            user_prompt="您的服务已停用，如需恢复请联系服务人员。",
        ),
    )

    assert passive_reply.Query().POST() == "您的服务已停用，如需恢复请联系服务人员。"
    assert channel.cache_dict.peek_result("openid").replies == [("image", "media-tech")]
    assert produced_contexts == []


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_pending_result_permission_uses_cached_service_type_not_title(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from business.investment.constants import ServiceType
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    channel.cache_dict.append_result(
        "openid",
        "已生成",
        [("image", "media-rate")],
        service_type=ServiceType.RATE,
    )
    current_message = {"content": "1", "msg_id": "msg-cached-service-type-confirm"}
    permission_calls = []

    def fake_verify(_openid, service_type):
        permission_calls.append(service_type)
        return SimpleNamespace(
            allowed=False,
            user_prompt="您暂未开通该服务，如需开通请联系服务人员。",
        )

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr("business.investment.user_service.verify_permission", fake_verify)

    assert passive_reply.Query().POST() == "您暂未开通该服务，如需开通请联系服务人员。"
    assert permission_calls == [ServiceType.RATE]
    assert channel.cache_dict.peek_result("openid").replies == [("image", "media-rate")]
    assert produced_contexts == []


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_pending_result_discard_permission_uses_cached_service_type(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    channel.cache_dict.append_result(
        "openid",
        "已生成",
        [("image", "media-bond")],
        service_type=ServiceType.CONVERTIBLE_BOND,
    )
    current_message = {"content": "0", "msg_id": "msg-cached-service-type-discard"}
    permission_calls = []

    def fake_verify(_openid, service_type):
        permission_calls.append(service_type)
        return SimpleNamespace(
            allowed=False,
            user_prompt="您的服务已停用，如需恢复请联系服务人员。",
        )

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr("business.investment.user_service.verify_permission", fake_verify)

    assert passive_reply.Query().POST() == "您的服务已停用，如需恢复请联系服务人员。"
    assert permission_calls == [ServiceType.CONVERTIBLE_BOND]
    assert channel.cache_dict.peek_result("openid").replies == [("image", "media-bond")]
    assert produced_contexts == []


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_split_text_keeps_original_investment_title_for_permission_recheck(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    long_text = "技术分析结论：" + ("趋势向上。" * 5000)
    channel.cache_dict.append_result("openid", "天娱数科 技术分析", [("text", long_text)], service_type=ServiceType.TECHNICAL_ANALYSIS)
    current_message = {"content": "1", "msg_id": "msg-long-text-1"}
    permission_calls = []

    def fake_verify(_openid, service_type):
        permission_calls.append(service_type)
        if len(permission_calls) == 1:
            return SimpleNamespace(allowed=True, user_prompt="")
        return SimpleNamespace(allowed=False, user_prompt="您的服务已停用，如需恢复请联系服务人员。")

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr("business.investment.user_service.verify_permission", fake_verify)

    first_response = passive_reply.Query().POST()

    assert "【未完待续，回复任意文字以继续】" in first_response
    assert channel.cache_dict.peek_result("openid").title == "天娱数科 技术分析"

    current_message["msg_id"] = "msg-long-text-2"

    assert passive_reply.Query().POST() == "您的服务已停用，如需恢复请联系服务人员。"
    assert channel.cache_dict.peek_result("openid").title == "天娱数科 技术分析"
    assert len(permission_calls) == 2


def test_wechatmp_passive_stale_running_technical_analysis_confirm_clears_state(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(
        cache_dict=PassiveReplyCache(),
        running={"openid"},
        running_started_at={"openid": 1000.0},
        request_cnt={},
        technical_analysis_titles={"openid": "天娱数科"},
    )
    current_message = {"content": "1", "msg_id": "msg-stale-running"}

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(passive_reply.time, "time", lambda: 1000.0 + 16 * 60)

    assert passive_reply.Query().POST() == "success"
    assert "openid" not in channel.running
    assert "openid" not in channel.technical_analysis_titles
    assert [context.content for context in produced_contexts] == ["1"]


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_disabled_investment_user_gets_service_stopped_prompt(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply

    produced_contexts = []
    channel_holder = {}

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.cache_dict = {}
            self.running = set()
            self.request_cnt = {}
            channel_holder["channel"] = self

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)

        def produce(self, context):
            produced_contexts.append(context)

    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    fake_msg = SimpleNamespace(type="text")

    monkeypatch.setattr(passive_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(passive_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(passive_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(passive_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        passive_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="disabled-openid",
            content="300502.SZ 技术分析",
            msg_id="msg-disabled-passive",
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(passive_reply, "create_reply", FakeReply)
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: SimpleNamespace(
            allowed=False,
            user_prompt="您的服务已停用，如需恢复请联系服务人员。",
        ),
    )
    monkeypatch.setattr(passive_reply.web, "input", lambda: {})
    monkeypatch.setattr(passive_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        passive_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    response = passive_reply.Query().POST()

    assert response == "您的服务已停用，如需恢复请联系服务人员。"
    assert produced_contexts == []
    assert channel_holder["channel"].running == set()


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_disabled_user_invalid_text_stops_before_produce(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    current_message = {"content": "hello", "msg_id": "msg-disabled-invalid"}

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(
        "business.investment.user_service.verify_user_access",
        lambda _openid: SimpleNamespace(
            allowed=False,
            user_prompt="您的服务已停用，如需恢复请联系服务人员。",
        ),
    )

    assert passive_reply.Query().POST() == "您的服务已停用，如需恢复请联系服务人员。"
    assert produced_contexts == []
    assert channel.running == set()


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_passive_user_access_error_stops_before_produce(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply
    from channel.wechatmp.passive_reply_cache import PassiveReplyCache

    produced_contexts = []
    channel = SimpleNamespace(cache_dict=PassiveReplyCache(), running=set(), request_cnt={})
    current_message = {"content": "hello", "msg_id": "msg-access-error"}

    _fake_passive_post(monkeypatch, passive_reply, channel, current_message, produced_contexts)
    monkeypatch.setattr(
        "business.investment.user_service.verify_user_access",
        lambda _openid: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )

    assert passive_reply.Query().POST() == "系统暂时繁忙，请稍后重试。"
    assert produced_contexts == []
    assert channel.running == set()


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_active_unmatched_investment_message_returns_passive_prompt(monkeypatch):
    import channel.wechatmp.active_reply as active_reply

    produced_contexts = []

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.active_fallback_cache = {}
            self.active_running = set()

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)

        def produce(self, context):
            produced_contexts.append(context)

    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    fake_msg = SimpleNamespace(type="text")

    monkeypatch.setattr(active_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(active_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(active_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(active_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        active_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="openid",
            content="随便问一句",
            msg_id="msg-active-unmatched",
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(active_reply, "create_reply", FakeReply)
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: SimpleNamespace(allowed=True, user_prompt=""),
    )
    monkeypatch.setattr(active_reply.web, "input", lambda: {})
    monkeypatch.setattr(active_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        active_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    response = active_reply.Query().POST()

    assert response.startswith("请输入以下格式之一")
    assert produced_contexts == []


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_active_valid_investment_message_returns_polling_ack(monkeypatch):
    import channel.wechatmp.active_reply as active_reply

    produced_contexts = []
    channel_holder = {}

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.active_fallback_cache = {}
            self.active_running = set()
            channel_holder["channel"] = self

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(
                ctype=ctype,
                content=content,
                kwargs=kwargs,
            )

        def produce(self, context):
            produced_contexts.append(context)

    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    fake_msg = SimpleNamespace(type="text")

    monkeypatch.setattr(active_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(active_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(active_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(active_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        active_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="openid",
            content="300502.SZ 技术分析",
            msg_id="msg-active-tech",
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(active_reply, "create_reply", FakeReply)
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: SimpleNamespace(allowed=True, user_prompt=""),
    )
    monkeypatch.setattr(active_reply.web, "input", lambda: {})
    monkeypatch.setattr(active_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        active_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    monkeypatch.setattr(active_reply, "_running_investment_job", lambda _openid, _content: None)

    response = active_reply.Query().POST()

    assert response == "收到，正在运行，请稍候。"
    assert len(produced_contexts) == 1
    assert "openid" in channel_holder["channel"].active_running


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_active_disabled_investment_user_gets_service_stopped_prompt(monkeypatch):
    import channel.wechatmp.active_reply as active_reply

    produced_contexts = []
    channel_holder = {}

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.active_fallback_cache = {}
            self.active_running = set()
            channel_holder["channel"] = self

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)

        def produce(self, context):
            produced_contexts.append(context)

    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    fake_msg = SimpleNamespace(type="text")

    monkeypatch.setattr(active_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(active_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(active_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(active_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        active_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="disabled-openid",
            content="300502.SZ 技术分析",
            msg_id="msg-disabled-active",
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(active_reply, "create_reply", FakeReply)
    monkeypatch.setattr(active_reply, "_running_investment_job", lambda _openid, _content: None)
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: SimpleNamespace(
            allowed=False,
            user_prompt="您的服务已停用，如需恢复请联系服务人员。",
        ),
    )
    monkeypatch.setattr(active_reply.web, "input", lambda: {})
    monkeypatch.setattr(active_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        active_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    response = active_reply.Query().POST()

    assert response == "您的服务已停用，如需恢复请联系服务人员。"
    assert produced_contexts == []
    assert channel_holder["channel"].active_running == set()


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_active_permission_check_error_does_not_start_generation(monkeypatch):
    import channel.wechatmp.active_reply as active_reply

    produced_contexts = []
    channel_holder = {}

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.active_fallback_cache = {}
            self.active_running = set()
            channel_holder["channel"] = self

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)

        def produce(self, context):
            produced_contexts.append(context)

    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    fake_msg = SimpleNamespace(type="text")

    monkeypatch.setattr(active_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(active_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(active_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(active_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        active_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="openid",
            content="300502.SZ 技术分析",
            msg_id="msg-active-permission-error",
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(active_reply, "create_reply", FakeReply)
    monkeypatch.setattr(active_reply, "_running_investment_job", lambda _openid, _content: None)
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    monkeypatch.setattr(active_reply.web, "input", lambda: {})
    monkeypatch.setattr(active_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        active_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    response = active_reply.Query().POST()

    assert response == "系统暂时繁忙，请稍后重试。"
    assert produced_contexts == []
    assert channel_holder["channel"].active_running == set()


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_active_parse_route_error_does_not_start_generation(monkeypatch):
    import channel.wechatmp.active_reply as active_reply

    produced_contexts = []
    channel_holder = {}

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.active_fallback_cache = {}
            self.active_running = set()
            channel_holder["channel"] = self

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)

        def produce(self, context):
            produced_contexts.append(context)

    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    fake_msg = SimpleNamespace(type="text")

    monkeypatch.setattr(active_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(active_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(active_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(active_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        active_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="openid",
            content="300502.SZ 技术分析",
            msg_id="msg-active-parse-error",
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(active_reply, "create_reply", FakeReply)
    monkeypatch.setattr(
        "business.router.parse_route",
        lambda _content: (_ for _ in ()).throw(RuntimeError("router unavailable")),
    )
    monkeypatch.setattr(active_reply.web, "input", lambda: {})
    monkeypatch.setattr(active_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        active_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    response = active_reply.Query().POST()

    assert response == "系统暂时繁忙，请稍后重试。"
    assert produced_contexts == []
    assert channel_holder["channel"].active_running == set()


@STAGE8_WECHATMP_BUSINESS_PRECHECK_REMOVED
def test_wechatmp_active_running_investment_job_does_not_start_duplicate(monkeypatch):
    import channel.wechatmp.active_reply as active_reply

    produced_contexts = []

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.active_fallback_cache = {}
            self.active_running = set()

        def _compose_context(self, ctype, content, **kwargs):
            return SimpleNamespace(ctype=ctype, content=content, kwargs=kwargs)

        def produce(self, context):
            produced_contexts.append(context)

    class FakeReply:
        def __init__(self, text, _msg):
            self.text = text

        def render(self):
            return self.text

    fake_msg = SimpleNamespace(type="text")

    monkeypatch.setattr(active_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(active_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(active_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(active_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(
        active_reply,
        "WeChatMPMessage",
        lambda _msg, client=None: SimpleNamespace(
            from_user_id="openid",
            content="300502.SZ 技术分析",
            msg_id="msg-active-duplicate",
            ctype=SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(active_reply, "create_reply", FakeReply)
    monkeypatch.setattr(active_reply, "_running_investment_job", lambda _openid, _content: SimpleNamespace(request_id="req-1"))
    monkeypatch.setattr(
        "business.investment.user_service.verify_permission",
        lambda _openid, _service_type: SimpleNamespace(allowed=True, user_prompt=""),
    )
    monkeypatch.setattr(active_reply.web, "input", lambda: {})
    monkeypatch.setattr(active_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        active_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    response = active_reply.Query().POST()

    assert response == "正在运行，请稍候。"
    assert produced_contexts == []


def test_wechatmp_active_try_mark_running_is_atomic(monkeypatch):
    import channel.wechatmp.wechatmp_channel as wechatmp_channel

    _reset_wechatmp_singleton(wechatmp_channel)
    monkeypatch.setattr(
        wechatmp_channel,
        "conf",
        lambda: {
            "wechatmp_app_id": "wx-test",
            "wechatmp_app_secret": "secret",
            "wechatmp_token": "token",
            "wechatmp_aes_key": "",
            "single_chat_prefix": [""],
            "concurrency_in_session": 1,
        },
    )
    channel = wechatmp_channel.WechatMPChannel(passive_reply=False)

    assert channel.passive_reply is True
    assert not hasattr(channel, "active_fallback_cache")
    assert not hasattr(channel, "active_running")


def test_wechatmp_active_mode_config_falls_back_to_passive_startup_with_warning(monkeypatch):
    import channel.wechatmp.wechatmp_channel as wechatmp_channel

    _reset_wechatmp_singleton(wechatmp_channel)
    monkeypatch.setattr(
        wechatmp_channel,
        "conf",
        lambda: {
            "wechatmp_app_id": "wx-test",
            "wechatmp_app_secret": "secret",
            "wechatmp_token": "token",
            "wechatmp_aes_key": "",
            "wechatmp_port": 8080,
            "single_chat_prefix": [""],
            "concurrency_in_session": 1,
        },
    )
    warnings = []
    captured_urls = []
    monkeypatch.setattr(wechatmp_channel.logger, "warning", lambda message: warnings.append(message))

    class FakeApp:
        def __init__(self, urls, _globals, autoreload=False):
            captured_urls.append(urls)

        def wsgifunc(self):
            return lambda *_args, **_kwargs: None

    class FakeServer:
        def __init__(self, *_args, **_kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr(wechatmp_channel.web, "application", FakeApp)
    monkeypatch.setattr(wechatmp_channel.web.httpserver, "StaticMiddleware", lambda app: app)
    monkeypatch.setattr(wechatmp_channel.web.httpserver, "LogMiddleware", lambda app: app)
    monkeypatch.setattr(wechatmp_channel.web.httpserver, "WSGIServer", FakeServer)

    channel = wechatmp_channel.WechatMPChannel(passive_reply=False)
    channel.startup()

    assert channel.passive_reply is True
    assert captured_urls == [("/wx", "channel.wechatmp.passive_reply.Query")]
    assert warnings == ["[wechatmp] active reply mode is disabled; falling back to passive reply"]


def test_wechatmp_active_mode_send_text_uses_passive_cache_without_active_message(monkeypatch):
    from bridge.reply import Reply, ReplyType
    import channel.wechatmp.wechatmp_channel as wechatmp_channel

    _reset_wechatmp_singleton(wechatmp_channel)
    monkeypatch.setattr(
        wechatmp_channel,
        "conf",
        lambda: {
            "wechatmp_app_id": "wx-test",
            "wechatmp_app_secret": "secret",
            "wechatmp_token": "token",
            "wechatmp_aes_key": "",
            "single_chat_prefix": [""],
            "concurrency_in_session": 1,
        },
    )
    channel = wechatmp_channel.WechatMPChannel(passive_reply=False)

    class FakeMessage:
        def send_text(self, *_args, **_kwargs):
            raise AssertionError("active customer-service text must not be sent")

    channel.client.message = FakeMessage()

    channel.send(Reply(ReplyType.TEXT, "今日内容尚未更新，请稍后再试。"), _context())

    assert not hasattr(channel, "active_fallback_cache")
    assert channel.cache_dict["openid"] == [("text", "今日内容尚未更新，请稍后再试。")]


def test_wechatmp_active_mode_send_image_uses_passive_cache_without_active_message(monkeypatch, tmp_path):
    from bridge.reply import Reply, ReplyType
    import channel.wechatmp.wechatmp_channel as wechatmp_channel

    _reset_wechatmp_singleton(wechatmp_channel)
    monkeypatch.setattr(
        wechatmp_channel,
        "conf",
        lambda: {
            "wechatmp_app_id": "wx-test",
            "wechatmp_app_secret": "secret",
            "wechatmp_token": "token",
            "wechatmp_aes_key": "",
            "single_chat_prefix": [""],
            "concurrency_in_session": 1,
        },
    )
    channel = wechatmp_channel.WechatMPChannel(passive_reply=False)

    image_paths = []
    for name in ("signal.png", "chart.png"):
        path = tmp_path / name
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        image_paths.append(str(path))

    class FakeMedia:
        def __init__(self):
            self.calls = 0

        def upload(self, *_args, **_kwargs):
            self.calls += 1
            return {"media_id": f"media-{self.calls}"}

    class FakeMessage:
        def send_image(self, *_args, **_kwargs):
            raise AssertionError("active customer-service image must not be sent")

    channel.client.media = FakeMedia()
    channel.client.message = FakeMessage()

    channel.send(Reply(ReplyType.IMAGE_URL, image_paths), _context())

    assert not hasattr(channel, "active_fallback_cache")
    assert channel.cache_dict["openid"] == [("image", "media-1"), ("image", "media-2")]
