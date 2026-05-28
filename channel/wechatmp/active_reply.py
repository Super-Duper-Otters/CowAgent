import time

import web
from wechatpy import parse_message
from wechatpy.replies import ImageReply, create_reply

from bridge.context import *
from bridge.reply import *
from channel.wechatmp.common import *
from channel.wechatmp.wechatmp_channel import WechatMPChannel
from channel.wechatmp.wechatmp_message import WeChatMPMessage
from common.log import logger
from config import conf, subscribe_msg


ACTIVE_IMMEDIATE_ACK_TEXT = "收到，正在运行，请稍候。稍后发送任意文字可拉取结果。"
ACTIVE_WAITING_TEXT = "正在运行，请稍候。稍后发送任意文字可拉取结果。"


def _render_text_reply(text, msg, encrypt_func):
    reply_post = create_reply(text, msg)
    return encrypt_func(reply_post.render())


def _render_cached_reply(reply_type, reply_content, msg, encrypt_func):
    if reply_type == "image":
        reply_post = ImageReply(message=msg)
        reply_post.media_id = reply_content
        return encrypt_func(reply_post.render())
    return _render_text_reply(str(reply_content), msg, encrypt_func)


def _pop_active_fallback(channel, openid):
    if hasattr(channel, "pop_active_fallback"):
        return channel.pop_active_fallback(openid)
    cache = getattr(channel, "active_fallback_cache", None)
    if not cache or not cache.get(openid):
        return None
    item = cache[openid].pop(0)
    if not cache[openid]:
        del cache[openid]
    return item


def _is_active_running(channel, openid):
    if hasattr(channel, "is_active_running"):
        return channel.is_active_running(openid)
    return openid in getattr(channel, "active_running", set())


def _mark_active_running(channel, openid):
    if hasattr(channel, "mark_active_running"):
        channel.mark_active_running(openid)
    elif hasattr(channel, "active_running"):
        channel.active_running.add(openid)


# This class is instantiated once per query
class Query:
    def GET(self):
        return verify_server(web.input())

    def POST(self):
        # Make sure to return the instance that first created, @singleton will do that.
        try:
            args = web.input()
            channel = WechatMPChannel()
            message = web.data()
            encrypt_func = lambda x: x
            if is_encrypted_message(args):
                logger.debug("[wechatmp] Receive encrypted post data:\n" + message.decode("utf-8"))
                message = decrypt_message_if_needed(args, message, channel.crypto)
                encrypt_func = lambda x: channel.crypto.encrypt_message(x, args.nonce, args.timestamp)
            else:
                message = decrypt_message_if_needed(args, message, channel.crypto)
                logger.debug("[wechatmp] Receive post data:\n" + message.decode("utf-8"))
            msg = parse_message(message)
            if msg.type in ["text", "voice", "image"]:
                wechatmp_msg = WeChatMPMessage(msg, client=channel.client)
                from_user = wechatmp_msg.from_user_id
                content = wechatmp_msg.content
                message_id = wechatmp_msg.msg_id

                cached_item = _pop_active_fallback(channel, from_user)
                if cached_item:
                    logger.info("[wechatmp] active fallback passive reply to {}: {}".format(from_user, cached_item[0]))
                    return _render_cached_reply(cached_item[0], cached_item[1], msg, encrypt_func)

                if _is_active_running(channel, from_user):
                    logger.info("[wechatmp] active task still running for {}".format(from_user))
                    return _render_text_reply(ACTIVE_WAITING_TEXT, msg, encrypt_func)

                logger.info(
                    "[wechatmp] {}:{} Receive post query {} {}: {}".format(
                        web.ctx.env.get("REMOTE_ADDR"),
                        web.ctx.env.get("REMOTE_PORT"),
                        from_user,
                        message_id,
                        content,
                    )
                )
                if msg.type == "voice" and wechatmp_msg.ctype == ContextType.TEXT and conf().get("voice_reply_voice", False):
                    context = channel._compose_context(wechatmp_msg.ctype, content, isgroup=False, desire_rtype=ReplyType.VOICE, msg=wechatmp_msg)
                else:
                    context = channel._compose_context(wechatmp_msg.ctype, content, isgroup=False, msg=wechatmp_msg)
                if context:
                    try:
                        from business.investment.router import DEFAULT_UNMATCHED_PROMPT, parse_route

                        route = parse_route(content)
                        if not route.matched:
                            return _render_text_reply(DEFAULT_UNMATCHED_PROMPT, msg, encrypt_func)
                        _mark_active_running(channel, from_user)
                        channel.produce(context)
                        return _render_text_reply(ACTIVE_IMMEDIATE_ACK_TEXT, msg, encrypt_func)
                    except Exception as exc:
                        logger.exception("[wechatmp] active investment pre-reply failed: {}".format(exc))
                    channel.produce(context)
                # The reply will be sent by channel.send() in another thread
                return "success"
            elif msg.type == "event":
                logger.info("[wechatmp] Event {} from {}".format(msg.event, msg.source))
                if msg.event in ["subscribe", "subscribe_scan"]:
                    reply_text = subscribe_msg()
                    if reply_text:
                        replyPost = create_reply(reply_text, msg)
                        return encrypt_func(replyPost.render())
                else:
                    return "success"
            else:
                logger.info("暂且不处理")
            return "success"
        except Exception as exc:
            logger.exception(exc)
            return exc
