import asyncio
import threading
import time

import web
from wechatpy import parse_message
from wechatpy.replies import ImageReply, VideoReply, VoiceReply, create_reply
import textwrap
from bridge.context import *
from bridge.reply import *
from channel.wechatmp.common import *
from channel.wechatmp.wechatmp_channel import WechatMPChannel
from channel.wechatmp.wechatmp_message import WeChatMPMessage
from common.log import logger
from common.utils import split_string_by_utf8_length
from config import conf, subscribe_msg


IMMEDIATE_ACK_TEXT = "收到，正在运行，请稍候。"
PASSIVE_TECHNICAL_ACK_TEXT = "已收到，正在运行「{}」技术分析，生成过程大概30s。\n生成完成后回复 1 获取技术分析主图、技术指标表。"
PASSIVE_TECHNICAL_CACHE_HIT_TEXT = "已命中「{}」技术分析缓存，正在直接交付。\n回复 1 获取技术分析主图、技术指标表。"
CANCEL_PENDING_RESULT_TEXT = "已放弃本次技术分析结果。"
RUNNING_TECHNICAL_ANALYSIS_TEXT = "「{}」技术分析仍在运行中，请稍后再回复 1 尝试获取。"
PENDING_TECHNICAL_ANALYSIS_TEXT = "「{}」技术分析已生成完成，回复 1 获取技术分析主图、技术指标表；回复 0 放弃并继续处理新指令。"
RUNNING_STALE_SECONDS = 15 * 60
PERMISSION_DENIED_RECORD_TTL_SECONDS = 15 * 60
_permission_denied_record_keys = {}
_permission_denied_record_lock = threading.RLock()


def _investment_route(content: str):
    try:
        from business.investment.router import parse_route

        route = parse_route(content)
        return route if route.matched else None
    except Exception as exc:
        logger.debug("[wechatmp] investment route check failed: {}".format(exc))
        return None


def _is_investment_command(content: str) -> bool:
    return _investment_route(content) is not None


def _is_technical_analysis_route(route) -> bool:
    try:
        from business.investment.constants import ServiceType

        return route is not None and route.service_type == ServiceType.TECHNICAL_ANALYSIS
    except Exception as exc:
        logger.debug("[wechatmp] technical analysis route check failed: {}".format(exc))
        return False


def _technical_analysis_target(content: str) -> str:
    route = _investment_route(content)
    if _is_technical_analysis_route(route):
        target = (route.target_text or "").strip()
        if target:
            return target
    text = (content or "").strip()
    trigger = "技术分析"
    if text.endswith(trigger):
        text = text[: -len(trigger)].strip()
    return text or "本次"


def _technical_analysis_cache_hit(content: str) -> bool:
    route = _investment_route(content)
    if not _is_technical_analysis_route(route):
        return False
    try:
        from business.investment.technical_analysis import prepare_technical_analysis_cache_context
        from business.investment.cache_service import find_cache_entry_by_key

        context = prepare_technical_analysis_cache_context(content, route.target_text)
        return bool(context.cache_key and find_cache_entry_by_key(context.cache_key) is not None)
    except Exception as exc:
        logger.debug("[wechatmp] technical analysis cache check failed: {}".format(exc))
        return False


def _investment_ack_text(content: str) -> str:
    route = _investment_route(content)
    if _is_technical_analysis_route(route):
        if _technical_analysis_cache_hit(content):
            return PASSIVE_TECHNICAL_CACHE_HIT_TEXT.format(_technical_analysis_target(content))
        return PASSIVE_TECHNICAL_ACK_TEXT.format(_technical_analysis_target(content))
    return IMMEDIATE_ACK_TEXT


def _investment_permission_prompt(openid: str, content: str, dedupe_key: str = "") -> str:
    try:
        from business.investment.router import parse_route
        from business.investment.user_service import verify_permission

        route = parse_route(content)
        if not route.matched:
            return ""
        permission = verify_permission(openid, route.service_type)
        if permission.allowed:
            return ""
        _record_permission_denied_request(openid, content, permission, dedupe_key=dedupe_key)
        return permission.user_prompt
    except Exception as exc:
        logger.debug("[wechatmp] investment permission check failed: {}".format(exc))
        from business.investment.constants import ErrorCode, user_message

        return user_message(ErrorCode.SYSTEM_ERROR)


def _investment_user_access_prompt(openid: str, dedupe_key: str = "") -> str:
    try:
        from business.investment.user_service import verify_user_access

        permission = verify_user_access(openid)
        if permission.allowed:
            return ""
        _record_permission_denied_request(openid, "", permission, dedupe_key=dedupe_key)
        return permission.user_prompt
    except Exception as exc:
        logger.debug("[wechatmp] investment user access check failed: {}".format(exc))
        from business.investment.constants import ErrorCode, user_message

        return user_message(ErrorCode.SYSTEM_ERROR)


def _claim_permission_denied_record_key(dedupe_key: str) -> bool:
    if not dedupe_key:
        return True
    now = time.time()
    with _permission_denied_record_lock:
        expired = [
            key
            for key, recorded_at in _permission_denied_record_keys.items()
            if now - recorded_at > PERMISSION_DENIED_RECORD_TTL_SECONDS
        ]
        for key in expired:
            _permission_denied_record_keys.pop(key, None)
        if dedupe_key in _permission_denied_record_keys:
            return False
        _permission_denied_record_keys[dedupe_key] = now
        return True


def _release_permission_denied_record_key(dedupe_key: str) -> None:
    if not dedupe_key:
        return
    with _permission_denied_record_lock:
        _permission_denied_record_keys.pop(dedupe_key, None)


def _record_permission_denied_request(openid: str, content: str, permission, dedupe_key: str = "") -> None:
    if not _claim_permission_denied_record_key(dedupe_key):
        return
    try:
        from business.investment.constants import ErrorCode, ServiceType
        from business.investment.records import create_request_record, fail_request_record

        request_id = create_request_record(openid, content or "", ServiceType.UNAUTHORIZED_REQUEST)
        fail_request_record(
            request_id,
            getattr(permission, "error_code", None) or ErrorCode.UNAUTHORIZED,
            getattr(permission, "user_prompt", "") or "",
            getattr(permission, "detail", "") or "permission denied before investment router",
            0,
        )
    except Exception as exc:
        _release_permission_denied_record_key(dedupe_key)
        logger.debug("[wechatmp] record permission denied request failed: {}".format(exc))


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
        return type("CachedResult", (), {"title": "", "replies": replies, "service_type": "", "request_id": ""})()
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
    route = _investment_route(title or "")
    if _is_technical_analysis_route(route) or str(title or "").strip().endswith("技术分析"):
        return PENDING_TECHNICAL_ANALYSIS_TEXT.format(_technical_analysis_target(title or ""))
    prefix = title or ""
    return "{}结果已生成完成，是否需要返回？无需则回复 0，需要则回复 1。".format(prefix)


def _is_direct_ready_result_request(content, cached_result):
    current_route = _investment_route(content)
    if current_route is None or _is_technical_analysis_route(current_route):
        return False
    return bool(getattr(cached_result, "service_type", "")) and cached_result.service_type == current_route.service_type


def _permission_prompt_for_cached_result(openid, cached_result, content="", dedupe_key=""):
    service_type = getattr(cached_result, "service_type", "")
    if not service_type:
        return ""
    try:
        from business.investment.constants import normalize_service
        from business.investment.user_service import verify_permission

        permission = verify_permission(openid, normalize_service(service_type))
        if permission.allowed:
            return ""
        raw_input = getattr(cached_result, "title", "") or content or ""
        _record_permission_denied_request(openid, raw_input, permission, dedupe_key=dedupe_key)
        return permission.user_prompt
    except Exception as exc:
        logger.debug("[wechatmp] cached investment permission check failed: {}".format(exc))
        from business.investment.constants import ErrorCode, user_message

        return user_message(ErrorCode.SYSTEM_ERROR)


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
    _technical_titles(channel)[receiver] = _technical_analysis_target(content)


def _get_running_technical_title(channel, receiver):
    return _technical_titles(channel).get(receiver, "")


def _mark_running(channel, receiver, is_technical_analysis, content):
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


def _unmatched_prompt():
    try:
        from business.investment.router import DEFAULT_UNMATCHED_PROMPT

        return DEFAULT_UNMATCHED_PROMPT
    except Exception:
        return "请输入以下格式之一："


def _append_cached_reply(cache, receiver, reply_type, reply_content, title="", service_type="", request_id=""):
    append_reply = getattr(cache, "append_reply", None)
    if append_reply:
        append_reply(receiver, reply_type, reply_content, title, service_type=service_type, request_id=request_id)
        return
    cache.setdefault(receiver, []).append((reply_type, reply_content))


def _mark_cached_result_delivered(cached_result, rendered_reply):
    if rendered_reply == "success":
        return
    request_id = getattr(cached_result, "request_id", "")
    if not request_id:
        return
    try:
        from business.investment import records

        mark_request_delivered = getattr(records, "mark_request_delivered", None)
        if mark_request_delivered:
            mark_request_delivered(request_id)
    except Exception as exc:
        logger.debug("[wechatmp] mark investment request delivered failed: {}".format(exc))


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

                access_prompt = _investment_user_access_prompt(
                    from_user,
                    dedupe_key=f"user-access:{from_user}:{message_id}",
                )
                if access_prompt:
                    replyPost = create_reply(access_prompt, msg)
                    return encrypt_func(replyPost.render())

                supported = True
                if "【收到不支持的消息类型，暂无法显示】" in content:
                    supported = False  # not supported, used to refresh

                _cleanup_stale_running(channel, from_user)
                pending_result = _peek_cached_result(channel.cache_dict, from_user)
                if pending_result is not None:
                    if content == "1" or _is_direct_ready_result_request(content, pending_result):
                        permission_prompt = _permission_prompt_for_cached_result(
                            from_user,
                            pending_result,
                            content,
                            dedupe_key=f"cached:{from_user}:{message_id}:{getattr(pending_result, 'request_id', '')}",
                        )
                        if permission_prompt:
                            replyPost = create_reply(permission_prompt, msg)
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
                        permission_prompt = _permission_prompt_for_cached_result(
                            from_user,
                            pending_result,
                            content,
                            dedupe_key=f"cached:{from_user}:{message_id}:{getattr(pending_result, 'request_id', '')}",
                        )
                        if permission_prompt:
                            replyPost = create_reply(permission_prompt, msg)
                            return encrypt_func(replyPost.render())
                        _discard_cached_result(channel.cache_dict, from_user)
                        pending_command = _pop_pending_command(channel.cache_dict, from_user)
                        if pending_command:
                            content = pending_command
                        else:
                            replyPost = create_reply(CANCEL_PENDING_RESULT_TEXT, msg)
                            return encrypt_func(replyPost.render())
                    else:
                        _set_pending_command(channel.cache_dict, from_user, content)
                        replyPost = create_reply(_pending_result_prompt(pending_result.title), msg)
                        return encrypt_func(replyPost.render())

                if content == "1" and from_user in channel.running:
                    technical_title = _get_running_technical_title(channel, from_user)
                    if technical_title:
                        replyPost = create_reply(RUNNING_TECHNICAL_ANALYSIS_TEXT.format(technical_title), msg)
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
                        permission_prompt = _investment_permission_prompt(
                            from_user,
                            content,
                            dedupe_key=f"request:{from_user}:{message_id}:{content}",
                        )
                        if permission_prompt:
                            replyPost = create_reply(permission_prompt, msg)
                            return encrypt_func(replyPost.render())
                        route = _investment_route(content)
                        is_technical_analysis = _is_technical_analysis_route(route)
                        _mark_running(channel, from_user, is_technical_analysis, content)
                        channel.produce(context)
                        if is_technical_analysis:
                            replyPost = create_reply(_investment_ack_text(content), msg)
                            return encrypt_func(replyPost.render())
                    else:
                        trigger_prefix = conf().get("single_chat_prefix", [""])[0]
                        if trigger_prefix or not supported:
                            if trigger_prefix:
                                reply_text = textwrap.dedent(
                                    f"""\
                                    请输入'{trigger_prefix}'接你想说的话跟我说话。
                                    例如:
                                    {trigger_prefix}你好，很高兴见到你。"""
                                )
                            else:
                                reply_text = textwrap.dedent(
                                    """\
                                    你好，很高兴见到你。
                                    请跟我说话吧。"""
                                )
                        else:
                            logger.error(f"[wechatmp] unknown error")
                            reply_text = textwrap.dedent(
                                """\
                                未知错误，请稍后再试"""
                            )

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
                        reply_text = "【正在思考中，回复任意文字尝试获取回复】"
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
                    permission_prompt = _permission_prompt_for_cached_result(
                        from_user,
                        pending_result,
                        content,
                        dedupe_key=f"cached:{from_user}:{message_id}:{getattr(pending_result, 'request_id', '')}",
                    )
                    if permission_prompt:
                        replyPost = create_reply(permission_prompt, msg)
                        return encrypt_func(replyPost.render())
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
