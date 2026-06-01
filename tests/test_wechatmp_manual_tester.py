# encoding:utf-8
import importlib.util
import sys
from pathlib import Path


def _load_script_module():
    script_path = Path(__file__).resolve().parents[1] / "wechatmp_manual_tester.py"
    spec = importlib.util.spec_from_file_location("wechatmp_manual_tester", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_format_exchange_shows_manual_input_openid_and_text_reply():
    mod = _load_script_module()
    result = mod.ManualExchange(
        wx_url="http://127.0.0.1:8080/wx",
        openid="openid-user-a",
        to_user="gh_test",
        input_text="农业银行技术分析",
        signed_url="http://127.0.0.1:8080/wx?signature=sig&timestamp=1&nonce=n",
        request_xml=b"<xml><Content><![CDATA[test]]></Content></xml>",
        status_code=200,
        elapsed_seconds=0.1234,
        reply=mod.ParsedReply(
            is_xml=True,
            msg_type="text",
            content="已生成「农业银行」技术分析。\n回复 1 获取技术分析主图、技术指标表。",
            to_user="openid-user-a",
            from_user="gh_test",
            raw_text="<xml/>",
        ),
    )

    output = mod.format_exchange(result, show_xml=False)

    assert "OpenID: openid-user-a" in output
    assert "输入: 农业银行技术分析" in output
    assert "HTTP: 200" in output
    assert "回复类型: text" in output
    assert "已生成「农业银行」技术分析" in output
    assert "+-- 后台回复 · text · 0.123s " in output
    assert "| 输入     农业银行技术分析" in output


def test_format_exchange_can_show_wechat_xml_and_image_media_id():
    mod = _load_script_module()
    result = mod.ManualExchange(
        wx_url="http://127.0.0.1:8080/wx",
        openid="openid-user-a",
        to_user="gh_test",
        input_text="1",
        signed_url="http://127.0.0.1:8080/wx?signature=sig&timestamp=1&nonce=n",
        request_xml=b"<xml><Content><![CDATA[1]]></Content></xml>",
        status_code=200,
        elapsed_seconds=0.05,
        reply=mod.ParsedReply(
            is_xml=True,
            msg_type="image",
            media_id="mock-media-id",
            to_user="openid-user-a",
            from_user="gh_test",
            raw_text="<xml><MsgType><![CDATA[image]]></MsgType></xml>",
        ),
    )

    output = mod.format_exchange(result, show_xml=True)

    assert "请求XML:" in output
    assert "<Content><![CDATA[1]]></Content>" in output
    assert "回复类型: image" in output
    assert "MediaId: mock-media-id" in output
    assert "响应XML:" in output
    assert "+-- 请求 XML " in output
    assert "+-- 响应 XML " in output


def test_interactive_openid_command_switches_current_openid():
    mod = _load_script_module()
    state = mod.InteractiveState(openid="old-openid", show_xml=False)

    handled = mod.handle_interactive_command("/openid new-openid", state)

    assert handled is True
    assert state.openid == "new-openid"


def test_parser_accepts_positional_text_and_openid():
    mod = _load_script_module()

    args = mod.build_arg_parser().parse_args(["--openid", "openid-user-a", "农业银行技术分析"])

    assert args.openid == "openid-user-a"
    assert args.text == ["农业银行技术分析"]


def test_parser_defaults_to_manual_mode_with_default_openid():
    mod = _load_script_module()

    args = mod.build_arg_parser().parse_args([])

    assert args.openid == mod.DEFAULT_OPENID
    assert args.text == []
    assert args.inspect_db is True
    assert args.open_image is True
    assert mod.should_run_interactive(args) is True


def test_parser_keeps_one_shot_mode_when_text_is_passed_without_openid():
    mod = _load_script_module()

    args = mod.build_arg_parser().parse_args(["农业银行技术分析"])

    assert args.openid == mod.DEFAULT_OPENID
    assert mod.should_run_interactive(args) is False


def test_format_header_renders_manual_tui_context():
    mod = _load_script_module()

    output = mod.format_header(
        wx_url="http://127.0.0.1:8080/wx",
        openid="openid-user-a",
        to_user="gh_test",
        inspect_db=True,
        open_image=True,
    )

    assert "+-- CowAgent WeChatMP Manual Tester " in output
    assert "| URL        http://127.0.0.1:8080/wx" in output
    assert "| OpenID     openid-user-a" in output
    assert "| InspectDB  on" in output
    assert "| OpenImage  on" in output


def test_format_user_input_renders_chat_prompt():
    mod = _load_script_module()

    output = mod.format_user_input("农业银行技术分析")

    assert output == "> 农业银行技术分析"


def test_format_request_record_shows_output_files_and_first_png(tmp_path):
    mod = _load_script_module()
    png = tmp_path / "card.png"
    md = tmp_path / "report.md"
    png.write_bytes(b"png")
    md.write_text("report", encoding="utf-8")
    record = {
        "request_id": "req-1",
        "service_type": "technical_analysis",
        "status": "success",
        "cache_hit": 1,
        "elapsed_ms": 648,
        "error_message": "",
        "output_files": f'["{str(png).replace("\\", "\\\\")}", "{str(md).replace("\\", "\\\\")}"]',
    }

    output = mod.format_request_record(record)

    assert "请求记录: req-1" in output
    assert "service_type: technical_analysis" in output
    assert "cache_hit: 1" in output
    assert str(png) in output
    assert str(md) in output
    assert f"首张PNG: {png}" in output
    assert "+-- 请求记录 " in output
    assert "| status       success" in output


def test_output_files_accepts_json_or_list(tmp_path):
    mod = _load_script_module()
    png = tmp_path / "a.png"
    txt = tmp_path / "a.txt"

    assert mod.parse_output_files([str(png), str(txt)]) == [str(png), str(txt)]
    assert mod.parse_output_files(f'["{str(png).replace("\\", "\\\\")}"]') == [str(png)]
    assert mod.parse_output_files("") == []


def test_open_first_png_invokes_platform_opener(monkeypatch, tmp_path):
    mod = _load_script_module()
    png = tmp_path / "card.png"
    txt = tmp_path / "report.txt"
    png.write_bytes(b"png")
    txt.write_text("report", encoding="utf-8")
    opened = []

    monkeypatch.setattr(mod.os, "startfile", lambda path: opened.append(path), raising=False)

    opened_path = mod.open_first_png([str(txt), str(png)])

    assert opened_path == png
    assert opened == [str(png)]


def test_open_image_implies_db_inspection():
    mod = _load_script_module()

    args = mod.build_arg_parser().parse_args(["--open-image"])
    mod.normalize_args(args)

    assert args.inspect_db is True


def test_parser_can_disable_default_image_opening():
    mod = _load_script_module()

    args = mod.build_arg_parser().parse_args(["--no-open-image", "--no-inspect-db"])
    mod.normalize_args(args)

    assert args.open_image is False
    assert args.inspect_db is False


def test_reply_one_prefers_remembered_png_without_db_inspection(tmp_path):
    mod = _load_script_module()
    png = tmp_path / "card.png"
    png.write_bytes(b"png")
    state = mod.InteractiveState(openid="openid-user-a", show_xml=False, last_png=png, pending_pngs=[png])
    args = mod.build_arg_parser().parse_args([])
    mod.normalize_args(args)

    assert mod.should_inspect_db_after_text("1", args, state) is False
    assert mod.should_open_remembered_after_text("1", args, state) is True


def test_reply_one_uses_backend_after_remembered_pngs_are_consumed(tmp_path):
    mod = _load_script_module()
    png = tmp_path / "card.png"
    png.write_bytes(b"png")
    state = mod.InteractiveState(
        openid="openid-user-a",
        show_xml=False,
        last_png=png,
        pending_pngs=[png],
        next_png_index=1,
    )
    args = mod.build_arg_parser().parse_args([])
    mod.normalize_args(args)

    assert mod.should_open_remembered_after_text("1", args, state) is False
    assert mod.should_inspect_db_after_text("1", args, state) is True


def test_interactive_state_remembers_latest_png_from_record(tmp_path):
    mod = _load_script_module()
    png = tmp_path / "card.png"
    second_png = tmp_path / "chart.png"
    png.write_bytes(b"png")
    second_png.write_bytes(b"png")
    state = mod.InteractiveState(openid="openid-user-a", show_xml=False)

    mod.remember_record_png(state, {"output_files": [str(png), str(second_png)]})

    assert state.last_png == png
    assert state.pending_pngs == [png, second_png]
    assert state.next_png_index == 0


def test_open_remembered_png_advances_through_pending_pngs(monkeypatch, tmp_path):
    mod = _load_script_module()
    first_png = tmp_path / "card.png"
    second_png = tmp_path / "chart.png"
    first_png.write_bytes(b"png")
    second_png.write_bytes(b"png")
    state = mod.InteractiveState(
        openid="openid-user-a",
        show_xml=False,
        last_png=first_png,
        pending_pngs=[first_png, second_png],
    )
    opened = []
    monkeypatch.setattr(mod.os, "startfile", lambda path: opened.append(path), raising=False)

    first_opened = mod.open_remembered_png(state)
    second_opened = mod.open_remembered_png(state)
    third_opened = mod.open_remembered_png(state)

    assert first_opened == first_png
    assert second_opened == second_png
    assert third_opened is None
    assert opened == [str(first_png), str(second_png)]
    assert state.next_png_index == 2


def test_inspect_db_does_not_warn_about_missing_png_when_record_has_no_outputs(monkeypatch, capsys):
    mod = _load_script_module()
    args = mod.build_arg_parser().parse_args([])
    mod.normalize_args(args)
    exchange = mod.ManualExchange(
        wx_url="http://127.0.0.1:8080/wx",
        openid="openid-user-a",
        to_user="gh_test",
        input_text="你好",
        signed_url="http://127.0.0.1:8080/wx?signature=sig&timestamp=1&nonce=n",
        request_xml=b"<xml/>",
        status_code=200,
        elapsed_seconds=0.1,
        reply=mod.ParsedReply(is_xml=True, msg_type="text", content="请输入以下格式之一："),
    )
    monkeypatch.setattr(
        mod,
        "fetch_request_record",
        lambda *_args, **_kwargs: {
            "request_id": "req-unmatched",
            "service_type": "unmatched",
            "status": "failed",
            "cache_hit": 0,
            "elapsed_ms": 40,
            "error_code": "input_error",
            "error_message": "unmatched investment route",
            "output_files": [],
        },
    )

    mod.inspect_db_after_send(args, {}, exchange, since=mod.datetime.now(mod.timezone.utc))

    captured = capsys.readouterr()
    assert "未找到可打开的 PNG" not in captured.out
    assert "output_files:" in captured.out
