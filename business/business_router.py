# encoding:utf-8
"""CowAgent built-in business routing entrypoint."""

from bridge.context import Context
from bridge.reply import Reply, ReplyType
from common.log import logger

from business import router as business_route
from business.config_service import sanitize_sensitive_text
from business.constants import ErrorCode, ServiceType, user_message
from business.permission_service import (
    verify_customer_access as verify_user_access,
    verify_customer_business_access as verify_permission,
)


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


def build_business_reply(context: Context, *, skip_permission: bool = False) -> Reply | None:
    if context is None or not isinstance(context.content, str):
        return None
    try:
        route = business_route.parse_route(context.content)
        if not route.matched:
            return None
        if route.service_type == ServiceType.TECHNICAL_ANALYSIS:
            from business.technical_analysis_handler import handle_technical_analysis

            openid = _openid_from_context(context)
            customer_metadata = business_route._customer_metadata(openid)
            if not skip_permission:
                access = verify_user_access(openid)
                if not access.allowed:
                    business_reply = _permission_failure_reply(openid, context.content, access, customer_metadata)
                    return _reply_from_business(business_reply)
                permission = verify_permission(openid, route.service_type)
                if not permission.allowed:
                    business_reply = _permission_failure_reply(openid, context.content, permission, customer_metadata)
                    return _reply_from_business(business_reply)
            return _reply_from_business(
                handle_technical_analysis(
                    openid,
                    context.content,
                    route,
                    customer_metadata=customer_metadata,
                )
            )
        if route.service_type in (ServiceType.RATE, ServiceType.CONVERTIBLE_BOND):
            from business.daily_content_handler import handle_daily_content

            openid = _openid_from_context(context)
            customer_metadata = business_route._customer_metadata(openid)
            if not skip_permission:
                access = verify_user_access(openid)
                if not access.allowed:
                    business_reply = _permission_failure_reply(openid, context.content, access, customer_metadata)
                    return _reply_from_business(business_reply)
                permission = verify_permission(openid, route.service_type)
                if not permission.allowed:
                    business_reply = _permission_failure_reply(openid, context.content, permission, customer_metadata)
                    return _reply_from_business(business_reply)
            return _reply_from_business(
                handle_daily_content(
                    openid,
                    context.content,
                    route,
                    customer_metadata=customer_metadata,
                )
            )
        business_reply = business_route.handle_text_message(
            _openid_from_context(context),
            context.content,
            skip_permission=skip_permission,
        )
    except Exception as exc:
        logger.exception("[business_router] investment business failed: {}".format(exc))
        return Reply(ReplyType.TEXT, user_message(ErrorCode.SYSTEM_ERROR))
    return _reply_from_business(business_reply)


def _permission_failure_reply(openid: str, raw_input: str, permission, customer_metadata: dict[str, str]):
    from business.router import BusinessReply
    from business.business_records import (
        create_business_record as create_request_record,
        mark_business_failed as fail_request_record,
    )

    request_id = create_request_record(
        openid,
        raw_input,
        ServiceType.UNAUTHORIZED_REQUEST,
        customer_name=customer_metadata.get("customer_name", ""),
        institution=customer_metadata.get("institution", ""),
    )
    fail_request_record(
        request_id,
        permission.error_code or ErrorCode.UNAUTHORIZED,
        permission.user_prompt,
        permission.detail,
        0,
    )
    return BusinessReply(
        True,
        False,
        permission.user_prompt,
        [],
        ServiceType.UNAUTHORIZED_REQUEST,
        permission.error_code,
        permission.user_prompt,
        sanitize_sensitive_text(permission.detail),
        request_id,
    )
