# encoding:utf-8
"""CowAgent built-in business routing entrypoint."""

from bridge.context import Context
from bridge.reply import Reply, ReplyType
from common.log import logger

from business import router as business_route
from business.constants import ErrorCode, user_message
from business.investment.constants import ActorType, EntryType


def _openid_from_context(context: Context) -> str:
    msg = context.get("msg") if context else None
    return str(getattr(msg, "from_user_id", "") or context.get("session_id", "") or "")


def _reply_from_business(business_reply) -> Reply | None:
    if not business_reply.handled:
        return None
    output_files = [path for path in business_reply.output_files if path]
    if business_reply.success and output_files:
        reply = Reply(ReplyType.IMAGE_URL, output_files)
    else:
        reply = Reply(ReplyType.TEXT, business_reply.reply_text)

    reply.business_service_type = business_reply.service_type
    reply.investment_service_type = business_reply.service_type
    if getattr(business_reply, "module_key", ""):
        reply.business_module_key = business_reply.module_key
        reply.investment_module_key = business_reply.module_key
    if getattr(business_reply, "request_id", ""):
        reply.business_request_id = business_reply.request_id
        reply.investment_request_id = business_reply.request_id
    if getattr(business_reply, "source_type", ""):
        reply.business_source_type = business_reply.source_type
        reply.investment_source_type = business_reply.source_type
    if getattr(business_reply, "source_id", ""):
        reply.business_source_id = business_reply.source_id
        reply.investment_source_id = business_reply.source_id
    return reply


def _is_wechatmp_context(context: Context) -> bool:
    channel_type = str(context.get("channel_type", "") if context else "")
    return channel_type in {"wechatmp", "wechatmp_service"}


def _business_record_context(context: Context) -> dict:
    if context is None:
        return {}
    channel_type = str(context.get("channel_type", "") or "")
    entry_type = context.get("business_entry_type") or context.get("investment_entry_type")
    if not entry_type and channel_type == "web":
        entry_type = EntryType.INTERNAL_CALL
    if not entry_type:
        return {}
    actor_type = context.get("business_actor_type") or context.get("investment_actor_type")
    actor_id = str(context.get("business_actor_id") or context.get("investment_actor_id") or "")
    actor_name = str(context.get("business_actor_name") or context.get("investment_actor_name") or "")
    actor_role = str(context.get("business_actor_role") or context.get("investment_actor_role") or "")
    if not actor_type:
        actor_type = ActorType.ADMIN if str(entry_type) == str(EntryType.INTERNAL_CALL) else ActorType.CUSTOMER
    return {
        "entry_type": entry_type,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "actor_name": actor_name,
        "actor_role": actor_role,
    }


def build_business_reply(context: Context, *, skip_permission: bool = False) -> Reply | None:
    if context is None or not isinstance(context.content, str):
        return None
    try:
        route = business_route.parse_route(context.content)
        if not route.matched:
            if _is_wechatmp_context(context):
                business_reply = business_route.handle_text_message(
                    _openid_from_context(context),
                    context.content,
                    skip_permission=skip_permission,
                    record_context=_business_record_context(context),
                )
                return _reply_from_business(business_reply)
            return None
        business_reply = business_route.handle_text_message(
            _openid_from_context(context),
            context.content,
            skip_permission=skip_permission,
            record_context=_business_record_context(context),
        )
    except Exception as exc:
        logger.exception("[business_router] investment business failed: {}".format(exc))
        return Reply(ReplyType.TEXT, user_message(ErrorCode.SYSTEM_ERROR))
    return _reply_from_business(business_reply)
