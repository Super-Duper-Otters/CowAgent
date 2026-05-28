# encoding:utf-8
from types import SimpleNamespace


def _wechatmp_channel(monkeypatch):
    import channel.wechatmp.wechatmp_channel as wechatmp_channel

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


def _context(openid="openid", msg_id="msg-1"):
    from bridge.context import Context, ContextType

    msg = SimpleNamespace(from_user_id=openid, other_user_id=openid, msg_id=msg_id)
    return Context(
        ContextType.TEXT,
        "利率",
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
    import business.investment.router as investment_router

    image_path = str(tmp_path / "rate_card.png")
    monkeypatch.setattr(
        investment_router,
        "handle_text_message",
        lambda _openid, _content: BusinessReply(
            handled=True,
            success=True,
            reply_text=f"[图片: {image_path}]",
            output_files=[image_path],
            service_type=ServiceType.RATE,
        ),
    )

    reply = _wechatmp_channel(monkeypatch)._generate_reply(_context())

    assert reply.type == ReplyType.IMAGE_URL
    assert reply.content == [image_path]


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


def test_wechatmp_passive_image_reply_does_not_delete_temporary_media(monkeypatch):
    import pytest
    import channel.wechatmp.passive_reply as passive_reply

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.cache_dict = {"openid": [("image", "media-1")]}
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

    fake_msg = SimpleNamespace(type="text")
    fake_wechatmp_msg = SimpleNamespace(from_user_id="openid", content="利率", msg_id="msg-1")

    monkeypatch.setattr(passive_reply, "WechatMPChannel", FakeChannel)
    monkeypatch.setattr(passive_reply, "is_encrypted_message", lambda _args: False)
    monkeypatch.setattr(passive_reply, "decrypt_message_if_needed", lambda _args, message, _crypto: message)
    monkeypatch.setattr(passive_reply, "parse_message", lambda _message: fake_msg)
    monkeypatch.setattr(passive_reply, "WeChatMPMessage", lambda _msg, client=None: fake_wechatmp_msg)
    monkeypatch.setattr(passive_reply, "ImageReply", FakeImageReply)
    monkeypatch.setattr(passive_reply.web, "input", lambda: {})
    monkeypatch.setattr(passive_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        passive_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    assert passive_reply.Query().POST() == "<image>media-1</image>"


def test_wechatmp_passive_valid_investment_command_immediately_acknowledges(monkeypatch):
    import channel.wechatmp.passive_reply as passive_reply

    produced_contexts = []

    class FakeChannel:
        def __init__(self):
            self.client = SimpleNamespace()
            self.crypto = None
            self.cache_dict = {}
            self.running = set()
            self.request_cnt = {}

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
    monkeypatch.setattr(passive_reply.web, "input", lambda: {})
    monkeypatch.setattr(passive_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        passive_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    for index, content in enumerate(("利率", "转债", "300502.SZ 技术分析"), start=1):
        current_message["content"] = content
        current_message["msg_id"] = f"msg-ack-{index}"
        response = passive_reply.Query().POST()

        assert response == "收到，正在运行，请稍候。"

    assert len(produced_contexts) == 3


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
    monkeypatch.setattr(active_reply.web, "input", lambda: {})
    monkeypatch.setattr(active_reply.web, "data", lambda: b"<xml/>")
    monkeypatch.setattr(
        active_reply.web.ctx,
        "env",
        {"REMOTE_ADDR": "127.0.0.1", "REMOTE_PORT": "12345"},
        raising=False,
    )

    response = active_reply.Query().POST()

    assert response == "收到，正在运行，请稍候。稍后发送任意文字可拉取结果。"
    assert len(produced_contexts) == 1
    assert "openid" in channel_holder["channel"].active_running


def test_wechatmp_active_send_text_failure_queues_passive_fallback(monkeypatch):
    from bridge.reply import Reply, ReplyType
    import channel.wechatmp.wechatmp_channel as wechatmp_channel

    instances = wechatmp_channel.WechatMPChannel.__closure__[1].cell_contents
    instances.clear()
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
            raise RuntimeError("48001 api unauthorized")

    channel.client.message = FakeMessage()

    channel.send(Reply(ReplyType.TEXT, "今日内容尚未更新，请稍后再试。"), _context())

    assert channel.active_fallback_cache["openid"] == [("text", "今日内容尚未更新，请稍后再试。")]


def test_wechatmp_active_send_image_failure_queues_all_uploaded_images(monkeypatch, tmp_path):
    from bridge.reply import Reply, ReplyType
    import channel.wechatmp.wechatmp_channel as wechatmp_channel

    instances = wechatmp_channel.WechatMPChannel.__closure__[1].cell_contents
    instances.clear()
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
            raise RuntimeError("48001 api unauthorized")

    channel.client.media = FakeMedia()
    channel.client.message = FakeMessage()

    channel.send(Reply(ReplyType.IMAGE_URL, image_paths), _context())

    assert channel.active_fallback_cache["openid"] == [("image", "media-1"), ("image", "media-2")]
