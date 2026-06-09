import asyncio
import threading
import time

import web
from wechatpy import parse_message
from wechatpy.replies import ImageReply, VideoReply, VoiceReply, create_reply
from bridge.context import *
from bridge.reply import *
from channel.wechatmp.common import *
from channel.wechatmp.wechatmp_channel import WechatMPChannel
from channel.wechatmp.wechatmp_message import WeChatMPMessage
from common.log import logger
from common.utils import split_string_by_utf8_length
from config import conf, subscribe_msg


CANCEL_PENDING_RESULT_KEY = "reply.wechatmp.cancel_pending_result"
RUNNING_TECHNICAL_ANALYSIS_KEY = "reply.wechatmp.running_technical_analysis"
PENDING_TECHNICAL_ANALYSIS_KEY = "reply.wechatmp.pending_technical_analysis"
THINKING_TIMEOUT_KEY = "reply.wechatmp.thinking_timeout"
CHAT_PREFIX_HINT_KEY = "reply.wechatmp.chat_prefix_hint"
DEFAULT_CHAT_HINT_KEY = "reply.wechatmp.default_chat_hint"
UNKNOWN_ERROR_KEY = "reply.wechatmp.unknown_error"
RUNNING_STALE_SECONDS = 15 * 60


def _reply_text(key: str, default: str = "") -> str:
    try:
        from business.reply_config import get_reply_text

        return get_reply_text(key, default)
    except Exception:
        return default


def _reply_format(key: str, *args, default: str = "") -> str:
    try:
        from business.reply_config import format_reply_text

        return format_reply_text(key, *args, default=default)
    except Exception:
        return default.format(*args) if args else default


def _running_technical_analysis_text(title: str) -> str:
    return _reply_format(
        RUNNING_TECHNICAL_ANALYSIS_KEY,
        title,
        default="「{}」技术分析仍在运行中，请稍后再回复 1 尝试获取。",
    )


def _cleanup_expired(cache):
    cleanup = getattr(cache, "cleanup_expired", None)
    if cleanup:
        cleanup()


def _peek_cached_result(cache, receiver):
    peek = getattr(cache, "peek_result", None)
    if peek:
        return peek(receiver)
    replies = cache.get(receiver) if hasattr(cache, "get") else None
    if replies:
        return type("CachedResult", (), {"title": "", "replies": replies, "service_type": "", "request_id": "", "source_type": "", "source_id": ""})()
    return None


def _pop_cached_reply(cache, receiver):
    pop_result = getattr(cache, "pop_result", None)
    if pop_result:
        return pop_result(receiver)
    if receiver not in cache:
        return None
    try:
        item = cache[receiver].pop(0)
        if not cache[receiver]:
            del cache[receiver]
        return item
    except IndexError:
        return None


def _discard_cached_result(cache, receiver):
    discard = getattr(cache, "discard_result", None)
    if discard:
        discard(receiver)
        return
    if receiver in cache:
        del cache[receiver]


def _set_pending_command(cache, receiver, content):
    setter = getattr(cache, "set_pending_command", None)
    if setter:
        setter(receiver, content)


def _pop_pending_command(cache, receiver):
    popper = getattr(cache, "pop_pending_command", None)
    if popper:
        return popper(receiver)
    return None


def _pending_result_prompt(title):
    if _is_technical_analysis_service_title(title):
        return _reply_format(
            PENDING_TECHNICAL_ANALYSIS_KEY,
            _technical_analysis_title(title or ""),
            default="「{}」技术分析已生成完成，回复 1 获取技术分析主图、技术指标表；回复 0 放弃并继续处理新指令。",
        )
    prefix = title or ""
    return "{}结果已生成完成，是否需要返回？无需则回复 0，需要则回复 1。".format(prefix)


def _is_technical_analysis_service_type(service_type) -> bool:
    try:
        from business.constants import ServiceType, normalize_service

        return normalize_service(service_type) == ServiceType.TECHNICAL_ANALYSIS
    except Exception:
        return str(service_type or "") == "technical_analysis"


def _is_technical_analysis_service_title(title) -> bool:
    return str(title or "").strip().endswith("技术分析")


def _technical_analysis_title(title: str) -> str:
    text = (title or "").strip()
    trigger = "技术分析"
    if text.endswith(trigger):
        text = text[: -len(trigger)].strip()
    return text or "本次"


def _technical_titles(channel):
    titles = getattr(channel, "technical_analysis_titles", None)
    if titles is None:
        titles = {}
        try:
            setattr(channel, "technical_analysis_titles", titles)
        except Exception:
            return {}
    return titles


def _running_started_at(channel):
    started_at = getattr(channel, "running_started_at", None)
    if started_at is None:
        started_at = {}
        try:
            setattr(channel, "running_started_at", started_at)
        except Exception:
            return {}
    return started_at


def _running_lock(channel):
    lock = getattr(channel, "running_lock", None)
    if lock is None:
        lock = threading.RLock()
        try:
            setattr(channel, "running_lock", lock)
        except Exception:
            return threading.RLock()
    return lock


def _set_running_technical_title(channel, receiver, content):
    _technical_titles(channel)[receiver] = _technical_analysis_title(content)


def _get_running_technical_title(channel, receiver):
    return _technical_titles(channel).get(receiver, "")


def _mark_running(channel, receiver, is_technical_analysis=False, content=""):
    with _running_lock(channel):
        channel.running.add(receiver)
        _running_started_at(channel)[receiver] = time.time()
        if is_technical_analysis:
            _set_running_technical_title(channel, receiver, content)


def _clear_running(channel, receiver):
    with _running_lock(channel):
        channel.running.discard(receiver)
        _running_started_at(channel).pop(receiver, None)
        _technical_titles(channel).pop(receiver, None)


def _cleanup_stale_running(channel, receiver=None):
    now = time.time()
    started_at = _running_started_at(channel)
    receivers = [receiver] if receiver else list(started_at)
    with _running_lock(channel):
        for item in receivers:
            started = started_at.get(item)
            if started is not None and now - started > RUNNING_STALE_SECONDS:
                channel.running.discard(item)
                started_at.pop(item, None)
                _technical_titles(channel).pop(item, None)


def _append_cached_reply(cache, receiver, reply_type, reply_content, title="", service_type="", request_id="", source_type="", source_id=""):
    append_reply = getattr(cache, "append_reply", None)
    if append_reply:
        append_reply(
            receiver,
            reply_type,
            reply_content,
            title,
            service_type=service_type,
            request_id=request_id,
            source_type=source_type,
            source_id=source_id,
        )
        return
    cache.setdefault(receiver, []).append((reply_type, reply_content))


def _pending_result_invalidated_prompt():
    return _reply_text("reply.wechatmp.pending_result_invalidated", "内容已失效，请重新发起请求。")


def _cleanup_invalid_cached_sources(cache, exclude_receiver=None):
    cleanup = getattr(cache, "discard_invalid_sources", None)
    if not cleanup:
        return 0
    try:
        excluded = [exclude_receiver] if exclude_receiver else None
        return cleanup(_cached_result_source_is_valid, exclude_receivers=excluded)
    except Exception as exc:
        logger.debug("[wechatmp] cleanup invalid cached investment source failed: {}".format(exc))
        return 0


def _cached_result_source_is_valid(cached_result):
    source_type = str(getattr(cached_result, "source_type", "") or "")
    source_id = str(getattr(cached_result, "source_id", "") or "")
    if not source_type or not source_id:
        return True
    if source_type == "cache":
        from business.cache_service import find_cache_entry_by_key

        return find_cache_entry_by_key(source_id, require_files=False) is not None
    if source_type == "content":
        from business.constants import Status
        from business.daily_content import mark_expired_daily_contents_invalidated
        from business.business_records import get_content_record

        mark_expired_daily_contents_invalidated()
        try:
            record = get_content_record(source_id)
        except KeyError:
            return False
        return str(getattr(record, "status", "") or "") == str(Status.EFFECTIVE)
    return True


def _mark_cached_result_delivered(cached_result, rendered_reply):
    if rendered_reply == "success":
        return
    request_id = getattr(cached_result, "request_id", "")
    if not request_id:
        return
    try:
        from business import business_records

        mark_request_delivered = getattr(business_records, "mark_request_delivered", None)
        if mark_request_delivered:
            mark_request_delivered(request_id)
    except Exception as exc:
        logger.debug("[wechatmp] mark investment request delivered failed: {}".format(exc))


def _record_request_event_safe(
    request_id="",
    openid="",
    event_type="",
    message_type="",
    content="",
    media_id="",
    file_path="",
    result="",
    error="",
):
    if not request_id or not event_type:
        return
    try:
        from business import business_records

        business_records.record_request_event(
            request_id=request_id,
            openid=openid,
            channel="wechatmp",
            event_type=event_type,
            message_type=message_type,
            content=content,
            media_id=media_id,
            file_path=file_path,
            source_type="request",
            source_id=request_id,
            result=result,
            error=error,
        )
    except Exception as exc:
        logger.debug("[wechatmp] record request event failed: {}".format(exc))


def _render_cached_reply(channel, msg, encrypt_func, from_user, message_id, content, request_cnt, cached_item, cache_title="", service_type="", request_id=""):
    if cached_item is None:
        return "success"
    reply_type, reply_content = cached_item
    if reply_type == "text":
        if len(reply_content.encode("utf8")) <= MAX_UTF8_LEN:
            reply_text = reply_content
        else:
            continue_text = "\n【未完待续，回复任意文字以继续】"
            splits = split_string_by_utf8_length(
                reply_content,
                MAX_UTF8_LEN - len(continue_text.encode("utf-8")),
                max_split=1,
            )
            reply_text = splits[0] + continue_text
            _append_cached_reply(channel.cache_dict, from_user, "text", splits[1], cache_title, service_type=service_type, request_id=request_id)

        logger.info(
            "[wechatmp] Request {} do send to {} {}: {}\n{}".format(
                request_cnt,
                from_user,
                message_id,
                content,
                reply_text,
            )
        )
        replyPost = create_reply(reply_text, msg)
        _record_request_event_safe(
            request_id=request_id,
            openid=from_user,
            event_type="reply_text_sent",
            message_type="text",
            content=reply_text,
            result="success",
        )
        return encrypt_func(replyPost.render())

    if reply_type == "voice":
        media_id = reply_content
        asyncio.run_coroutine_threadsafe(channel.delete_media(media_id), channel.delete_media_loop)
        logger.info(
            "[wechatmp] Request {} do send to {} {}: {} voice media_id {}".format(
                request_cnt,
                from_user,
                message_id,
                content,
                media_id,
            )
        )
        replyPost = VoiceReply(message=msg)
        replyPost.media_id = media_id
        return encrypt_func(replyPost.render())

    if reply_type == "image":
        media_id = reply_content
        logger.info(
            "[wechatmp] Request {} do send to {} {}: {} image media_id {}".format(
                request_cnt,
                from_user,
                message_id,
                content,
                media_id,
            )
        )
        replyPost = ImageReply(message=msg)
        replyPost.media_id = media_id
        _record_request_event_safe(
            request_id=request_id,
            openid=from_user,
            event_type="reply_image_sent",
            message_type="image",
            content=cache_title,
            media_id=media_id,
            result="success",
        )
        return encrypt_func(replyPost.render())

    if reply_type == "video":
        media_id = reply_content
        logger.info(
            "[wechatmp] Request {} do send to {} {}: {} video media_id {}".format(
                request_cnt,
                from_user,
                message_id,
                content,
                media_id,
            )
        )
        replyPost = VideoReply(message=msg)
        replyPost.media_id = media_id
        return encrypt_func(replyPost.render())

    return "success"


# This class is instantiated once per query
class Query:
    def GET(self):
        return verify_server(web.input())

    def POST(self):
        try:
            args = web.input()
            request_time = time.time()
            channel = WechatMPChannel()
            _cleanup_expired(channel.cache_dict)
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

                supported = True
                if "【收到不支持的消息类型，暂无法显示】" in content:
                    supported = False  # not supported, used to refresh

                _cleanup_stale_running(channel, from_user)
                _cleanup_invalid_cached_sources(channel.cache_dict, exclude_receiver=from_user)
                pending_result = _peek_cached_result(channel.cache_dict, from_user)
                if pending_result is not None:
                    if content == "1":
                        _record_request_event_safe(
                            request_id=getattr(pending_result, "request_id", ""),
                            openid=from_user,
                            event_type="customer_confirm",
                            message_type="text",
                            content=content,
                            result="accepted",
                        )
                        if not _cached_result_source_is_valid(pending_result):
                            _discard_cached_result(channel.cache_dict, from_user)
                            _pop_pending_command(channel.cache_dict, from_user)
                            replyPost = create_reply(_pending_result_invalidated_prompt(), msg)
                            return encrypt_func(replyPost.render())
                        if content == "1":
                            _pop_pending_command(channel.cache_dict, from_user)
                        cached_item = _pop_cached_reply(channel.cache_dict, from_user)
                        rendered_reply = _render_cached_reply(
                            channel,
                            msg,
                            encrypt_func,
                            from_user,
                            message_id,
                            content,
                            1,
                            cached_item,
                            pending_result.title,
                            getattr(pending_result, "service_type", ""),
                            getattr(pending_result, "request_id", ""),
                        )
                        _mark_cached_result_delivered(pending_result, rendered_reply)
                        return rendered_reply
                    if content == "0":
                        _record_request_event_safe(
                            request_id=getattr(pending_result, "request_id", ""),
                            openid=from_user,
                            event_type="customer_cancel",
                            message_type="text",
                            content=content,
                            result="accepted",
                        )
                        _discard_cached_result(channel.cache_dict, from_user)
                        pending_command = _pop_pending_command(channel.cache_dict, from_user)
                        if pending_command:
                            content = pending_command
                        else:
                            replyPost = create_reply(_reply_text(CANCEL_PENDING_RESULT_KEY, "已放弃本次技术分析结果。"), msg)
                            return encrypt_func(replyPost.render())
                    else:
                        _set_pending_command(channel.cache_dict, from_user, content)
                        replyPost = create_reply(_pending_result_prompt(pending_result.title), msg)
                        _record_request_event_safe(
                            request_id=getattr(pending_result, "request_id", ""),
                            openid=from_user,
                            event_type="pending_prompt_sent",
                            message_type="text",
                            content=content,
                            result="success",
                        )
                        return encrypt_func(replyPost.render())

                if content == "1" and from_user in channel.running:
                    technical_title = _get_running_technical_title(channel, from_user)
                    if technical_title:
                        replyPost = create_reply(_running_technical_analysis_text(technical_title), msg)
                        return encrypt_func(replyPost.render())

                # New request
                if (
                    _peek_cached_result(channel.cache_dict, from_user) is None
                    and from_user not in channel.running
                    or content.startswith("#")
                    and message_id not in channel.request_cnt  # insert the godcmd
                ):
                    # The first query begin
                    if msg.type == "voice" and wechatmp_msg.ctype == ContextType.TEXT and conf().get("voice_reply_voice", False):
                        context = channel._compose_context(wechatmp_msg.ctype, content, isgroup=False, desire_rtype=ReplyType.VOICE, msg=wechatmp_msg)
                    else:
                        context = channel._compose_context(wechatmp_msg.ctype, content, isgroup=False, msg=wechatmp_msg)
                    logger.debug("[wechatmp] context: {} {} {}".format(context, wechatmp_msg, supported))

                    if supported and context:
                        _mark_running(channel, from_user)
                        channel.produce(context)
                    else:
                        trigger_prefix = conf().get("single_chat_prefix", [""])[0]
                        if trigger_prefix or not supported:
                            if trigger_prefix:
                                reply_text = _reply_format(
                                    CHAT_PREFIX_HINT_KEY,
                                    trigger_prefix,
                                    trigger_prefix,
                                    default="请输入'{}'接你想说的话跟我说话。\n例如:\n{}你好，很高兴见到你。",
                                )
                            else:
                                reply_text = _reply_text(DEFAULT_CHAT_HINT_KEY, "你好，很高兴见到你。\n请跟我说话吧。")
                        else:
                            logger.error(f"[wechatmp] unknown error")
                            reply_text = _reply_text(UNKNOWN_ERROR_KEY, "未知错误，请稍后再试")

                        replyPost = create_reply(reply_text, msg)
                        return encrypt_func(replyPost.render())

                # Wechat official server will request 3 times (5 seconds each), with the same message_id.
                # Because the interval is 5 seconds, here assumed that do not have multithreading problems.
                request_cnt = channel.request_cnt.get(message_id, 0) + 1
                channel.request_cnt[message_id] = request_cnt
                logger.info(
                    "[wechatmp] Request {} from {} {} {}:{}\n{}".format(
                        request_cnt, from_user, message_id, web.ctx.env.get("REMOTE_ADDR"), web.ctx.env.get("REMOTE_PORT"), content
                    )
                )

                task_running = True
                waiting_until = request_time + 4
                while time.time() < waiting_until:
                    if from_user in channel.running:
                        time.sleep(0.1)
                    else:
                        task_running = False
                        break

                reply_text = ""
                if task_running:
                    if request_cnt < 3:
                        # waiting for timeout (the POST request will be closed by Wechat official server)
                        time.sleep(2)
                        # and do nothing, waiting for the next request
                        return "success"
                    else:  # request_cnt == 3:
                        # return timeout message
                        reply_text = _reply_text(THINKING_TIMEOUT_KEY, "【正在思考中，回复任意文字尝试获取回复】")
                        replyPost = create_reply(reply_text, msg)
                        return encrypt_func(replyPost.render())

                # reply is ready
                channel.request_cnt.pop(message_id)

                # no return because of bandwords or other reasons
                if _peek_cached_result(channel.cache_dict, from_user) is None and from_user not in channel.running:
                    return "success"

                # Only one request can access to the cached data
                pending_result = _peek_cached_result(channel.cache_dict, from_user)
                if pending_result is not None:
                    if _is_technical_analysis_service_type(getattr(pending_result, "service_type", "")):
                        _set_running_technical_title(channel, from_user, pending_result.title)
                cached_item = _pop_cached_reply(channel.cache_dict, from_user)
                rendered_reply = _render_cached_reply(
                    channel,
                    msg,
                    encrypt_func,
                    from_user,
                    message_id,
                    content,
                    request_cnt,
                    cached_item,
                    pending_result.title if pending_result is not None else "",
                    getattr(pending_result, "service_type", "") if pending_result is not None else "",
                    getattr(pending_result, "request_id", "") if pending_result is not None else "",
                )
                if pending_result is not None:
                    _mark_cached_result_delivered(pending_result, rendered_reply)
                return rendered_reply

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
