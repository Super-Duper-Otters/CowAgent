import web
from wechatpy.crypto import PrpCrypto, WeChatCrypto
from wechatpy.exceptions import InvalidAppIdException, InvalidSignatureException
from wechatpy.utils import check_signature

from config import conf

MAX_UTF8_LEN = 2048


class WeChatAPIException(Exception):
    pass


def is_encrypted_message(data):
    return data.get("encrypt_type") == "aes" or bool(data.get("msg_signature"))


def _create_crypto():
    config = conf()
    token = config.get("wechatmp_token")
    aes_key = config.get("wechatmp_aes_key")
    appid = config.get("wechatmp_app_id")
    if not token or not aes_key or not appid:
        raise Exception("Crypto not initialized, Please set wechatmp_token, wechatmp_aes_key and wechatmp_app_id in config.json")
    return WeChatCrypto(token, aes_key, appid)


def _verify_encrypted_server(data, crypto=None):
    signature = data.msg_signature
    timestamp = data.timestamp
    nonce = data.nonce
    echostr = data.echostr
    crypto = crypto or _create_crypto()
    return crypto._check_signature(signature, timestamp, nonce, echostr, PrpCrypto)


def verify_server(data, crypto=None):
    try:
        if is_encrypted_message(data) and data.get("echostr"):
            return _verify_encrypted_server(data, crypto)

        signature = data.signature
        timestamp = data.timestamp
        nonce = data.nonce
        echostr = data.get("echostr", None)
        token = conf().get("wechatmp_token")  # 请按照公众平台官网\基本配置中信息填写
        check_signature(token, signature, timestamp, nonce)
        return echostr
    except (InvalidSignatureException, InvalidAppIdException):
        raise web.Forbidden("Invalid signature")
    except Exception as e:
        raise web.Forbidden(str(e))


def decrypt_message_if_needed(args, message, crypto):
    if not is_encrypted_message(args):
        verify_server(args)
        return message

    if not crypto:
        raise Exception("Crypto not initialized, Please set wechatmp_aes_key in config.json")
    return crypto.decrypt_message(message, args.msg_signature, args.timestamp, args.nonce)
