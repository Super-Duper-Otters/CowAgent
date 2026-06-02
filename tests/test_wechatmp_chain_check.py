# encoding:utf-8
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "wechatmp_chain_check.py"
    spec = importlib.util.spec_from_file_location("wechatmp_chain_check", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_normalize_wx_url_accepts_base_or_full_wx_url():
    mod = _load_script_module()

    assert mod.normalize_wx_url("https://example.trycloudflare.com") == "https://example.trycloudflare.com/wx"
    assert mod.normalize_wx_url("https://example.trycloudflare.com/") == "https://example.trycloudflare.com/wx"
    assert mod.normalize_wx_url("https://example.trycloudflare.com/wx") == "https://example.trycloudflare.com/wx"


def test_build_signed_url_uses_wechat_token_timestamp_nonce_signature():
    mod = _load_script_module()
    expected = hashlib.sha1("".join(sorted(["token", "12345", "nonce"])).encode("utf-8")).hexdigest()

    url = mod.build_signed_url(
        "https://example.trycloudflare.com/wx",
        "token",
        timestamp="12345",
        nonce="nonce",
        extra={"echostr": "ok"},
    )

    assert f"signature={expected}" in url
    assert "timestamp=12345" in url
    assert "nonce=nonce" in url
    assert "echostr=ok" in url


def test_parse_reply_xml_extracts_image_media_id():
    mod = _load_script_module()
    xml = """<xml>
<ToUserName><![CDATA[user-openid]]></ToUserName>
<FromUserName><![CDATA[gh_dev]]></FromUserName>
<CreateTime>123456</CreateTime>
<MsgType><![CDATA[image]]></MsgType>
<Image><MediaId><![CDATA[media-123]]></MediaId></Image>
</xml>"""

    parsed = mod.parse_reply_xml(xml)

    assert parsed.is_xml is True
    assert parsed.msg_type == "image"
    assert parsed.media_id == "media-123"
    assert parsed.to_user == "user-openid"
    assert parsed.from_user == "gh_dev"


def test_normalize_psycopg_url_accepts_sqlalchemy_postgresql_driver_url():
    mod = _load_script_module()

    assert (
        mod.normalize_psycopg_url("postgresql+psycopg://cowagent:cowagent@127.0.0.1:55432/cowagent")
        == "postgresql://cowagent:cowagent@127.0.0.1:55432/cowagent"
    )


def test_extract_tunnel_url_returns_last_quick_tunnel_url():
    mod = _load_script_module()
    text = """
    2026 INF |  https://old-name.trycloudflare.com  |
    2026 INF |  https://new-name.trycloudflare.com  |
    """

    assert mod.extract_latest_tunnel_url(text) == "https://new-name.trycloudflare.com"


def test_extract_cpolar_url_prefers_latest_https_public_url():
    mod = _load_script_module()
    text = """
    time="2026-06-01T16:41:52+08:00" msg="NewTunnel" Url":"http://756611d.r17.cpolar.top"
    time="2026-06-01T16:41:53+08:00" msg="NewTunnel" Url":"https://756611d.r17.cpolar.top"
    time="2026-06-01T16:43:04+08:00" msg="RespStartTunnel" PublicUrl":"https://4c883b4d.r9.cpolar.cn"
    """

    assert mod.extract_latest_cpolar_url(text) == "https://4c883b4d.r9.cpolar.cn"


def test_default_target_prefers_latest_cpolar_tunnel(monkeypatch, tmp_path):
    mod = _load_script_module()
    args = mod.build_arg_parser().parse_args([])
    monkeypatch.setattr(mod, "discover_cpolar_base_url", lambda _root: "https://cpolar.example.cn")
    monkeypatch.setattr(mod, "discover_tunnel_base_url", lambda _root: "https://default.trycloudflare.com")

    target = mod.resolve_wx_target(args, {"wechatmp_port": 8080}, tmp_path)

    assert target.source == "cpolar"
    assert target.wx_url == "https://cpolar.example.cn/wx"


def test_discover_cpolar_base_url_prefers_https_over_later_http(monkeypatch, tmp_path):
    mod = _load_script_module()
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "cpolar.log").write_text(
        """
        time="2026-06-01T16:41:53+08:00" msg="NewTunnel" Url":"https://secure.r9.cpolar.cn"
        time="2026-06-01T16:43:04+08:00" msg="RespStartTunnel" PublicUrl":"http://plain.r9.cpolar.cn"
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(mod.Path, "home", lambda: tmp_path / "home")

    assert mod.discover_cpolar_base_url(tmp_path) == "https://secure.r9.cpolar.cn"


def test_default_target_resolves_to_latest_cloudflare_tunnel(monkeypatch, tmp_path):
    mod = _load_script_module()
    args = mod.build_arg_parser().parse_args([])
    monkeypatch.setattr(mod, "discover_cpolar_base_url", lambda _root: None)
    monkeypatch.setattr(mod, "discover_tunnel_base_url", lambda _root: "https://default.trycloudflare.com")

    target = mod.resolve_wx_target(args, {"wechatmp_port": 8080}, tmp_path)

    assert target.source == "cloudflare"
    assert target.wx_url == "https://default.trycloudflare.com/wx"


def test_local_target_requires_explicit_local_flag(tmp_path):
    mod = _load_script_module()
    args = mod.build_arg_parser().parse_args(["--local"])

    target = mod.resolve_wx_target(args, {"wechatmp_port": 8080}, tmp_path)

    assert target.source == "local"
    assert target.wx_url == "http://127.0.0.1:8080/wx"


def test_cloudflared_registered_detects_edge_registration_log():
    mod = _load_script_module()

    assert mod.cloudflared_registered("INF Registered tunnel connection connIndex=0") is True
    assert mod.cloudflared_registered("INF +--------------------------------------------------------------------------------------------+") is False


def test_build_cloudflared_args_targets_wechatmp_port():
    mod = _load_script_module()

    assert mod.build_cloudflared_args(8080, "http2") == [
        "tunnel",
        "--url",
        "http://127.0.0.1:8080",
        "--protocol",
        "http2",
        "--no-autoupdate",
    ]


def test_default_cli_does_not_send_customer_service_image():
    mod = _load_script_module()

    args = mod.build_arg_parser().parse_args([])

    assert args.send_kf_image is False
    assert args.post_webhook is False
    assert args.full is False
    assert args.no_auto_repair is False


def test_default_content_queries_cover_three_investment_routes():
    mod = _load_script_module()

    queries = mod.default_content_queries("利率", "天娱数科 技术分析", "转债")

    assert queries == ["利率", "转债", "天娱数科 技术分析"]


def test_business_content_check_accepts_expected_no_content_reply(monkeypatch, tmp_path):
    mod = _load_script_module()
    from business.investment.constants import ErrorCode, ServiceType, user_message
    from business.investment.router import BusinessReply
    import business.investment.router as investment_router

    monkeypatch.setattr(
        investment_router,
        "handle_text_message",
        lambda _openid, _query: BusinessReply(
            handled=True,
            success=False,
            reply_text=user_message(ErrorCode.NO_CONTENT),
            output_files=[],
            service_type=ServiceType.CONVERTIBLE_BOND,
            error_code=ErrorCode.NO_CONTENT,
            user_prompt=user_message(ErrorCode.NO_CONTENT),
        ),
    )

    result = mod.check_business_content(tmp_path, "openid", "转债")

    assert result.ok is True
    assert "no content" in result.detail


def test_wait_for_get_verify_retries_until_tunnel_responds(monkeypatch):
    mod = _load_script_module()
    attempts = []
    results = [
        mod.CheckResult("tunnel GET /wx signature verification", False, "connection reset"),
        mod.CheckResult("tunnel GET /wx signature verification", True, "status=200"),
    ]

    def fake_check_get_verify(session, wx_url, token, timeout_sec):
        attempts.append(timeout_sec)
        return results.pop(0)

    monkeypatch.setattr(mod, "check_get_verify", fake_check_get_verify)
    monkeypatch.setattr(mod.time, "sleep", lambda _seconds: None)

    result = mod.wait_for_get_verify(object(), "https://example.trycloudflare.com/wx", "token", 10)

    assert result.ok is True
    assert len(attempts) == 2


def test_smoke_unmatched_post_accepts_passive_format_prompt(monkeypatch):
    mod = _load_script_module()

    class FakeResponse:
        status_code = 200
        text = "<xml/>"

    monkeypatch.setattr(
        mod,
        "post_wechat_text",
        lambda *_args, **_kwargs: (
            FakeResponse(),
            mod.ParsedReply(is_xml=True, msg_type="text", content="请输入以下格式之一：\n1. 示例"),
        ),
    )

    result = mod.check_smoke_unmatched_post(
        object(),
        wx_url="https://example.trycloudflare.com/wx",
        token="token",
        to_user="gh_test",
        timeout_sec=10,
    )

    assert result.ok is True
    assert "passive_text_prompt" in result.detail


def test_smoke_unmatched_post_accepts_active_authorization_prompt(monkeypatch):
    mod = _load_script_module()

    class FakeResponse:
        status_code = 200
        text = "<xml/>"

    monkeypatch.setattr(
        mod,
        "post_wechat_text",
        lambda *_args, **_kwargs: (
            FakeResponse(),
            mod.ParsedReply(is_xml=True, msg_type="text", content="您暂未开通该服务，请联系管理员开通。"),
        ),
    )

    result = mod.check_smoke_unmatched_post(
        object(),
        wx_url="https://example.cpolar.cn/wx",
        token="token",
        to_user="gh_test",
        timeout_sec=10,
    )

    assert result.ok is True
    assert "active_authorization_prompt" in result.detail


def test_smoke_repairs_cloudflare_tunnel_after_failed_check(monkeypatch, tmp_path):
    mod = _load_script_module()
    args = mod.build_arg_parser().parse_args([])
    target = mod.WxTarget("https://broken.trycloudflare.com/wx", "cloudflare")
    calls = {"verify": 0, "repair": 0}

    def fake_check_get_verify(_session, wx_url, _token, _timeout_sec):
        calls["verify"] += 1
        if wx_url.startswith("https://broken"):
            return mod.CheckResult("tunnel GET /wx signature verification", False, "connection reset")
        return mod.CheckResult("tunnel GET /wx signature verification", True, "status=200")

    def fake_repair_tunnel(*_args, **_kwargs):
        calls["repair"] += 1
        return (
            "https://fixed.trycloudflare.com",
            1234,
            tmp_path / "out.log",
            tmp_path / "err.log",
        )

    monkeypatch.setattr(mod, "check_get_verify", fake_check_get_verify)
    monkeypatch.setattr(
        mod,
        "check_smoke_unmatched_post",
        lambda *_args, **_kwargs: mod.CheckResult("POST smoke unmatched prompt", True, "passive_text_prompt"),
    )
    monkeypatch.setattr(mod, "repair_tunnel", fake_repair_tunnel)

    repaired_target, checks = mod.run_smoke_checks(
        args,
        root=tmp_path,
        config={"wechatmp_port": 8080},
        target=target,
        token="token",
        session=object(),
    )

    assert repaired_target.wx_url == "https://fixed.trycloudflare.com/wx"
    assert calls["repair"] == 1
    assert calls["verify"] == 2
    assert any(check.name == "Cloudflare tunnel auto-repair" and check.ok for check in checks)


def test_smoke_repairs_cloudflare_tunnel_after_failed_post(monkeypatch, tmp_path):
    mod = _load_script_module()
    args = mod.build_arg_parser().parse_args([])
    target = mod.WxTarget("https://broken.trycloudflare.com/wx", "cloudflare")
    calls = {"post": 0, "repair": 0}

    monkeypatch.setattr(
        mod,
        "check_get_verify",
        lambda *_args, **_kwargs: mod.CheckResult("tunnel GET /wx signature verification", True, "status=200"),
    )

    def fake_check_smoke_unmatched_post(_session, *, wx_url, **_kwargs):
        calls["post"] += 1
        if wx_url.startswith("https://broken"):
            return mod.CheckResult("POST smoke unmatched prompt", False, "ConnectionResetError")
        return mod.CheckResult("POST smoke unmatched prompt", True, "passive_text_prompt")

    def fake_repair_tunnel(*_args, **_kwargs):
        calls["repair"] += 1
        return (
            "https://fixed.trycloudflare.com",
            1234,
            tmp_path / "out.log",
            tmp_path / "err.log",
        )

    monkeypatch.setattr(mod, "check_smoke_unmatched_post", fake_check_smoke_unmatched_post)
    monkeypatch.setattr(mod, "repair_tunnel", fake_repair_tunnel)

    repaired_target, checks = mod.run_smoke_checks(
        args,
        root=tmp_path,
        config={"wechatmp_port": 8080},
        target=target,
        token="token",
        session=object(),
    )

    assert repaired_target.wx_url == "https://fixed.trycloudflare.com/wx"
    assert calls == {"post": 2, "repair": 1}
    assert checks[-1].ok is True


def test_wait_for_request_record_waits_until_requested_status(monkeypatch):
    mod = _load_script_module()
    rows = [
        ("req-1", "利率", "rate", "generating", "[]", "created", "updated", None, None, ""),
        ("req-1", "利率", "rate", "success", "[]", "created", "updated", 123, None, ""),
    ]
    executions = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args):
            executions.append(args)

        def fetchone(self):
            return rows.pop(0)

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(mod.psycopg, "connect", lambda _db_url: FakeConn())
    monkeypatch.setattr(mod.time, "sleep", lambda _seconds: None)

    record = mod.wait_for_request_record(
        "postgresql://example",
        openid="openid",
        raw_input="利率",
        since=datetime.now(timezone.utc),
        timeout_sec=5,
        statuses={"success", "failed"},
    )

    assert record["status"] == "success"
    assert len(executions) == 2


def test_active_webhook_result_accepts_success_response_and_generated_files(tmp_path):
    mod = _load_script_module()
    image = tmp_path / "card.png"
    image.write_bytes(b"png")
    record = {"status": "success", "output_files": json.dumps([str(image)]), "elapsed_ms": 10}
    reply = mod.ParsedReply(is_xml=False, raw_text="success")

    result = mod.evaluate_webhook_result(
        query="利率",
        mode="active",
        status_code=200,
        response_text="success",
        reply=reply,
        record=record,
    )

    assert result.ok is True
    assert "returned='success'" in result.detail


def test_active_webhook_result_rejects_missing_output_file():
    mod = _load_script_module()
    record = {"status": "success", "output_files": '["C:/missing/card.png"]', "elapsed_ms": 10}
    reply = mod.ParsedReply(is_xml=False, raw_text="success")

    result = mod.evaluate_webhook_result(
        query="利率",
        mode="active",
        status_code=200,
        response_text="success",
        reply=reply,
        record=record,
    )

    assert result.ok is False
    assert "existing=0" in result.detail
