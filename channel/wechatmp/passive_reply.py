import asyncio
import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import web
from wechatpy import parse_message
from wechatpy.replies import ImageReply, VideoReply, VoiceReply, create_reply
from bridge.context import *
from bridge.reply import *
from channel.wechatmp.common import *
from channel.wechatmp.media_cache import image_media_cache, local_image_media_key
from channel.wechatmp.wechatmp_channel import WechatMPChannel
from channel.wechatmp.wechatmp_message import WeChatMPMessage
from common.log import logger
from common.utils import split_string_by_utf8_length
from config import conf, subscribe_msg


IMMEDIATE_ACK_KEY = "reply.wechatmp.immediate_ack"
INPUT_ERROR_KEY = "reply.investment.input_error"
PENDING_SUMMARY_KEY = "reply.wechatmp.pending_summary"
RUNNING_TECHNICAL_ANALYSIS_KEY = "reply.wechatmp.running_technical_analysis"
TECHNICAL_RUNNING_NEW_REQUEST_KEY = "reply.wechatmp.technical_running_new_request"
TECHNICAL_READY_KEY = "reply.wechatmp.technical_ready"
PENDING_TECHNICAL_ANALYSIS_KEY = "reply.wechatmp.pending_technical_analysis"
THINKING_TIMEOUT_KEY = "reply.wechatmp.thinking_timeout"
CHAT_PREFIX_HINT_KEY = "reply.wechatmp.chat_prefix_hint"
DEFAULT_CHAT_HINT_KEY = "reply.wechatmp.default_chat_hint"
UNKNOWN_ERROR_KEY = "reply.wechatmp.unknown_error"
RUNNING_STALE_SECONDS = 15 * 60
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def _reply_text(key: str, default: str = "") -> str:
    try:
        from business.config.reply_config import get_reply_text

        return get_reply_text(key, default)
    except Exception:
        return default


def _reply_format(key: str, *args, default: str = "") -> str:
    try:
        from business.config.reply_config import format_reply_text

        return format_reply_text(key, *args, default=default)
    except Exception:
        return default.format(*args) if args else default


def _running_technical_analysis_text(title: str) -> str:
    return _reply_format(
        RUNNING_TECHNICAL_ANALYSIS_KEY,
        title,
        default="「{}」技术分析仍在运行中，请稍后再回复 1 尝试获取。",
    )


def _technical_running_new_request_text(title: str) -> str:
    default = "「{running_title}」技术分析仍在运行中，请稍后回复1获取结果。\n当前暂不接受新的技术分析请求，请在结果领取后再发起新的技术分析。"
    text = _reply_text(TECHNICAL_RUNNING_NEW_REQUEST_KEY, default)
    try:
        return text.format(running_title=title)
    except Exception:
        try:
            return text.format(title)
        except Exception:
            return default.format(running_title=title)


def _technical_ready_text(title: str) -> str:
    default = "「{target}」技术分析结果已准备好，回复1获取。"
    text = _reply_text(TECHNICAL_READY_KEY, default)
    try:
        return text.format(target=title)
    except Exception:
        try:
            return text.format(title)
        except Exception:
            return default.format(target=title)


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


def _discard_cached_result_source(cache, cached_result):
    source_type = str(getattr(cached_result, "source_type", "") or "")
    source_id = str(getattr(cached_result, "source_id", "") or "")
    if not source_type or not source_id:
        return
    discard = getattr(cache, "discard_by_source", None)
    if discard:
        discard(source_type, source_id)


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
            default="「{}」技术分析已生成完成，回复 1 获取技术分析主图、技术指标表。",
        )
    prefix = title or ""
    return "{}结果已生成完成，回复 1 获取。".format(prefix)


def _pending_technical_summary(cache, receiver) -> str:
    summary_func = getattr(cache, "pending_technical_summary", None)
    if not summary_func:
        return ""
    summary = summary_func(receiver)
    if not summary:
        return ""
    items = "\n".join(_pending_summary_item_text(index, item) for index, item in enumerate(summary, start=1))
    template = _reply_text(
        PENDING_SUMMARY_KEY,
        "您当前还有技术分析结果待领取：\n{items}\n回复1获取或回复股票名称获取对应报告",
    )
    try:
        return template.format(items=items)
    except Exception:
        return "您当前还有技术分析结果待领取：\n{}\n回复1获取或回复股票名称获取对应报告".format(items)


def _pending_summary_item_text(index: int, item) -> str:
    target, count, created_at = _unpack_pending_summary_item(item)
    created_text = _format_pending_created_at(created_at)
    if created_text:
        return f"{index}.{target} {count}条（生成时间：{created_text}）"
    return f"{index}.{target} {count}条"


def _unpack_pending_summary_item(item):
    if len(item) >= 3:
        return item[0], item[1], item[2]
    return item[0], item[1], None


def _format_pending_created_at(created_at) -> str:
    if created_at in (None, ""):
        return ""
    try:
        return datetime.fromtimestamp(float(created_at), BEIJING_TZ).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def _append_pending_technical_summary(text: str, cache, receiver) -> str:
    summary = _pending_technical_summary(cache, receiver)
    if not summary:
        if "{pending_summary}" in text:
            return text.replace("{pending_summary}", "").strip()
        return text
    if "{pending_summary}" in text:
        return text.replace("{pending_summary}", summary)
    if not text:
        return summary
    return "{}\n\n{}".format(text.rstrip(), summary)


def _input_error_text(cache, receiver) -> str:
    return _append_pending_technical_summary(
        _reply_text(INPUT_ERROR_KEY, "请输入：股票代码/股票名称 + 技术分析，或输入“利率”“转债”。"),
        cache,
        receiver,
    )


def _immediate_ack_text(cache, receiver) -> str:
    return _append_pending_technical_summary(
        _reply_text(IMMEDIATE_ACK_KEY, "收到，正在处理，请稍候。请等待30-40s后回复1获取"),
        cache,
        receiver,
    )


def _parse_business_route(content):
    try:
        from business.routing.router import parse_route

        return parse_route(content)
    except Exception as exc:
        logger.debug("[wechatmp] parse business route failed: {}".format(exc))
        return None


def _route_is_matched(route) -> bool:
    return bool(getattr(route, "matched", False))


def _route_is_technical_analysis(route) -> bool:
    return _is_technical_analysis_service_type(getattr(route, "service_type", ""))


def _technical_analysis_precheck_error(route) -> str:
    if not _route_is_technical_analysis(route):
        return ""
    try:
        from business.content.technical_analysis_handler import validate_technical_analysis_request

        return validate_technical_analysis_request(getattr(route, "raw_input", ""), route)
    except Exception as exc:
        logger.warning("[wechatmp] technical analysis precheck failed: {}".format(exc))
        return ""


def _queue_ready_technical_result(channel, wechatmp_msg, route) -> bool:
    if not _route_is_technical_analysis(route):
        return False
    try:
        from business.routing import router as business_route
        from business.content.technical_analysis_handler import get_ready_technical_analysis_reply

        openid = str(getattr(wechatmp_msg, "from_user_id", "") or "")
        business_reply = get_ready_technical_analysis_reply(
            openid,
            getattr(route, "raw_input", "") or str(getattr(wechatmp_msg, "content", "") or ""),
            route,
            customer_metadata=business_route._customer_metadata(openid),
        )
        if business_reply is None or not getattr(business_reply, "success", False) or not getattr(business_reply, "output_files", None):
            return False

        title = getattr(route, "raw_input", "") or str(getattr(wechatmp_msg, "content", "") or "")
        for path in business_reply.output_files:
            if not path:
                continue
            _append_cached_reply(
                channel.cache_dict,
                openid,
                "image_file",
                path,
                title,
                service_type=business_reply.service_type,
                request_id=getattr(business_reply, "request_id", ""),
                source_type=getattr(business_reply, "source_type", ""),
                source_id=getattr(business_reply, "source_id", ""),
            )
        return _peek_cached_result(channel.cache_dict, openid) is not None
    except Exception as exc:
        logger.warning("[wechatmp] queue ready technical result failed: {}".format(exc))
        return False


def _pop_cached_reply_by_title(cache, receiver, title):
    pop_for_title = getattr(cache, "pop_result_for_title", None)
    if pop_for_title:
        selected = pop_for_title(receiver, title)
        if selected is None:
            return None, None
        return selected
    pop_by_title = getattr(cache, "pop_result_by_title", None)
    if pop_by_title:
        return pop_by_title(receiver, title), None
    return None, None


def _is_technical_analysis_service_type(service_type) -> bool:
    try:
        from business.config.constants import ServiceType, normalize_service

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
        from business.cache.cache_service import find_cache_entry_by_key, invalidate_cache_entry, technical_analysis_cache_expired_after_close

        entry = find_cache_entry_by_key(source_id, require_files=True)
        if entry is None:
            return False
        if _is_technical_analysis_service_type(getattr(entry, "service_type", "")) and technical_analysis_cache_expired_after_close(
            entry.market_date,
            entry.updated_at,
            normalized_target=entry.normalized_target,
        ):
            invalidate_cache_entry(source_id)
            return False
        return True
    if source_type == "content":
        from business.config.constants import Status
        from business.content.daily_content import mark_expired_daily_contents_invalidated
        from business.records.business_records import get_content_record

        mark_expired_daily_contents_invalidated()
        try:
            record = get_content_record(source_id)
        except KeyError:
            return False
        return str(getattr(record, "status", "") or "") == str(Status.EFFECTIVE)
    if source_type == "product":
        from business.products.product_service import find_active_product_by_id

        return find_active_product_by_id(source_id) is not None
    return True


def _mark_cached_result_delivered(cached_result, rendered_reply):
    if rendered_reply == "success":
        return
    request_id = getattr(cached_result, "request_id", "")
    if not request_id:
        return
    try:
        from business.records import business_records as business_records
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
        from business.records import business_records as business_records
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


def _upload_image_file_for_passive_reply(channel, from_user, message_id, image_content):
    media_cache_key = local_image_media_key(image_content)
    cached_media_id = image_media_cache.get(media_cache_key)
    if cached_media_id:
        logger.info("[wechatmp] image media cache hit, receiver {}, media_id {}".format(from_user, cached_media_id))
        return cached_media_id

    image_storage = None
    try:
        image_storage, image_type = channel._image_storage_from_path_or_url(image_content)
        filename = from_user + "-" + str(message_id) + "." + image_type
        content_type = "image/" + image_type
        response = channel.client.media.upload("image", (filename, image_storage, content_type))
    finally:
        local_image_path = image_content[7:] if isinstance(image_content, str) and image_content.startswith("file://") else image_content
        if image_storage is not None and isinstance(local_image_path, str) and os.path.exists(local_image_path):
            image_storage.close()

    media_id = response["media_id"]
    image_media_cache.set(media_cache_key, media_id)
    logger.info("[wechatmp] image uploaded on passive claim, receiver {}, media_id {}".format(from_user, media_id))
    return media_id


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

    if reply_type == "image_file":
        try:
            media_id = _upload_image_file_for_passive_reply(channel, from_user, message_id, reply_content)
        except Exception as exc:
            logger.error("[wechatmp] upload cached image file failed: {}".format(exc))
            _record_request_event_safe(
                request_id=request_id,
                openid=from_user,
                event_type="reply_image_failed",
                message_type="image",
                content=cache_title,
                file_path=reply_content,
                result="failed",
                error=str(exc),
            )
            return _pending_result_invalidated_prompt()
        logger.info(
            "[wechatmp] Request {} do send to {} {}: {} image file {}".format(
                request_cnt,
                from_user,
                message_id,
                content,
                reply_content,
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
            file_path=reply_content,
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
                parsed_route = None
                allow_new_request_with_pending_result = False
                reply_immediate_ack_after_start = False

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
                    cached_item, selected_result = _pop_cached_reply_by_title(channel.cache_dict, from_user, content)
                    if cached_item is not None:
                        selected_result = selected_result or pending_result
                        if not _cached_result_source_is_valid(selected_result):
                            _discard_cached_result_source(channel.cache_dict, selected_result)
                            replyPost = create_reply(_pending_result_invalidated_prompt(), msg)
                            return encrypt_func(replyPost.render())
                        rendered_reply = _render_cached_reply(
                            channel,
                            msg,
                            encrypt_func,
                            from_user,
                            message_id,
                            content,
                            1,
                            cached_item,
                            getattr(selected_result, "title", ""),
                            getattr(selected_result, "service_type", ""),
                            getattr(selected_result, "request_id", ""),
                        )
                        _mark_cached_result_delivered(selected_result, rendered_reply)
                        return rendered_reply

                    parsed_route = _parse_business_route(content)
                    if not _route_is_matched(parsed_route):
                        _record_request_event_safe(
                            request_id=getattr(pending_result, "request_id", ""),
                            openid=from_user,
                            event_type="pending_prompt_sent",
                            message_type="text",
                            content=content,
                            result="success",
                        )
                        replyPost = create_reply(_input_error_text(channel.cache_dict, from_user), msg)
                        return encrypt_func(replyPost.render())
                    precheck_error = _technical_analysis_precheck_error(parsed_route)
                    if precheck_error:
                        replyPost = create_reply(_append_pending_technical_summary(precheck_error, channel.cache_dict, from_user), msg)
                        return encrypt_func(replyPost.render())
                    if _queue_ready_technical_result(channel, wechatmp_msg, parsed_route):
                        replyPost = create_reply(_technical_ready_text(_technical_analysis_title(content)), msg)
                        return encrypt_func(replyPost.render())
                    allow_new_request_with_pending_result = True
                    if _route_is_technical_analysis(parsed_route):
                        _pop_pending_command(channel.cache_dict, from_user)
                        reply_immediate_ack_after_start = True
                    else:
                        _set_pending_command(channel.cache_dict, from_user, content)

                if content == "1" and from_user in channel.running:
                    technical_title = _get_running_technical_title(channel, from_user)
                    if technical_title:
                        replyPost = create_reply(_running_technical_analysis_text(technical_title), msg)
                        return encrypt_func(replyPost.render())
                if from_user in channel.running:
                    parsed_route = parsed_route or _parse_business_route(content)
                    if _route_is_technical_analysis(parsed_route):
                        technical_title = _get_running_technical_title(channel, from_user) or getattr(parsed_route, "target_text", "") or content
                        replyPost = create_reply(_technical_running_new_request_text(technical_title), msg)
                        return encrypt_func(replyPost.render())

                # New request
                if (
                    (_peek_cached_result(channel.cache_dict, from_user) is None or allow_new_request_with_pending_result)
                    and from_user not in channel.running
                    or content.startswith("#")
                    and message_id not in channel.request_cnt  # insert the godcmd
                ):
                    if parsed_route is None:
                        parsed_route = _parse_business_route(content)
                    precheck_error = _technical_analysis_precheck_error(parsed_route)
                    if precheck_error:
                        replyPost = create_reply(_append_pending_technical_summary(precheck_error, channel.cache_dict, from_user), msg)
                        return encrypt_func(replyPost.render())
                    if _queue_ready_technical_result(channel, wechatmp_msg, parsed_route):
                        replyPost = create_reply(_technical_ready_text(_technical_analysis_title(content)), msg)
                        return encrypt_func(replyPost.render())
                    if _route_is_technical_analysis(parsed_route):
                        reply_immediate_ack_after_start = True
                    # The first query begin
                    if msg.type == "voice" and wechatmp_msg.ctype == ContextType.TEXT and conf().get("voice_reply_voice", False):
                        context = channel._compose_context(wechatmp_msg.ctype, content, isgroup=False, desire_rtype=ReplyType.VOICE, msg=wechatmp_msg)
                    else:
                        context = channel._compose_context(wechatmp_msg.ctype, content, isgroup=False, msg=wechatmp_msg)
                    logger.debug("[wechatmp] context: {} {} {}".format(context, wechatmp_msg, supported))

                    if supported and context:
                        _mark_running(
                            channel,
                            from_user,
                            is_technical_analysis=_route_is_technical_analysis(parsed_route),
                            content=content,
                        )
                        channel.produce(context)
                        if reply_immediate_ack_after_start:
                            replyPost = create_reply(_immediate_ack_text(channel.cache_dict, from_user), msg)
                            return encrypt_func(replyPost.render())
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
                if allow_new_request_with_pending_result:
                    cached_item, selected_result = _pop_cached_reply_by_title(channel.cache_dict, from_user, content)
                    if cached_item is None:
                        return "success"
                    if selected_result is not None and not _cached_result_source_is_valid(selected_result):
                        _discard_cached_result_source(channel.cache_dict, selected_result)
                        replyPost = create_reply(_pending_result_invalidated_prompt(), msg)
                        return encrypt_func(replyPost.render())
                    rendered_reply = _render_cached_reply(
                        channel,
                        msg,
                        encrypt_func,
                        from_user,
                        message_id,
                        content,
                        request_cnt,
                        cached_item,
                        getattr(selected_result, "title", content),
                        getattr(selected_result, "service_type", ""),
                        getattr(selected_result, "request_id", ""),
                    )
                    if selected_result is not None:
                        _mark_cached_result_delivered(selected_result, rendered_reply)
                    return rendered_reply

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
