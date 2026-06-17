import hashlib
import xml.etree.ElementTree as ET

import pytest
import web
from wechatpy.crypto import WeChatCrypto

from channel.wechatmp import common


TOKEN = "test-token"
AES_KEY = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
APP_ID = "wx1234567890abcdef"


def _signature(*parts):
    return hashlib.sha1("".join(sorted(parts)).encode("utf-8")).hexdigest()


def _xml_text(xml, tag):
    return ET.fromstring(xml).find(tag).text


@pytest.fixture()
def wechatmp_conf(monkeypatch):
    monkeypatch.setattr(
        common,
        "conf",
        lambda: {
            "wechatmp_token": TOKEN,
            "wechatmp_aes_key": AES_KEY,
            "wechatmp_app_id": APP_ID,
        },
    )


def test_verify_server_returns_plain_echostr(wechatmp_conf):
    timestamp = "1714037059"
    nonce = "486452656"
    echostr = "plain-echo"
    data = web.storage(
        signature=_signature(TOKEN, timestamp, nonce),
        timestamp=timestamp,
        nonce=nonce,
        echostr=echostr,
    )

    assert common.verify_server(data) == echostr


def test_verify_server_accepts_encrypted_echostr(wechatmp_conf):
    crypto = WeChatCrypto(TOKEN, AES_KEY, APP_ID)
    timestamp = "1714112445"
    nonce = "415670741"
    echostr = "encrypted-echo"
    encrypted_echo_xml = crypto.encrypt_message(echostr, nonce, timestamp)
    encrypted_echo = _xml_text(encrypted_echo_xml, "Encrypt")
    data = web.storage(
        msg_signature=_xml_text(encrypted_echo_xml, "MsgSignature"),
        timestamp=timestamp,
        nonce=nonce,
        echostr=encrypted_echo,
    )

    assert common.verify_server(data) == echostr


def test_decrypt_message_if_needed_uses_msg_signature_for_encrypted_post(wechatmp_conf):
    crypto = WeChatCrypto(TOKEN, AES_KEY, APP_ID)
    timestamp = "1714112445"
    nonce = "415670741"
    plain_xml = (
        "<xml>"
        "<ToUserName><![CDATA[gh_test]]></ToUserName>"
        "<FromUserName><![CDATA[openid]]></FromUserName>"
        "<CreateTime>1714112445</CreateTime>"
        "<MsgType><![CDATA[text]]></MsgType>"
        "<Content><![CDATA[hello]]></Content>"
        "<MsgId>123</MsgId>"
        "</xml>"
    )
    encrypted_xml = crypto.encrypt_message(plain_xml, nonce, timestamp)
    args = web.storage(
        encrypt_type="aes",
        msg_signature=_xml_text(encrypted_xml, "MsgSignature"),
        timestamp=timestamp,
        nonce=nonce,
    )

    assert common.decrypt_message_if_needed(args, encrypted_xml.encode("utf-8"), crypto) == plain_xml
