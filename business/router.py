# encoding:utf-8
"""CowAgent built-in business routing entrypoint."""

import time
from dataclasses import dataclass

from business.business_records import (
    create_business_record as create_request_record,
    mark_business_failed as fail_request_record,
)
from business.config_service import get_config, sanitize_sensitive_text
from business.constants import ErrorCode, ServiceType
from business.permission_service import (
    verify_customer_access as verify_user_access,
    verify_customer_business_access as verify_permission,
)


DEFAULT_UNMATCHED_PROMPT = """请输入以下格式之一：
1. 股票代码/股票名称 + 技术分析，例如：300502.SZ 技术分析
2. 利率
3. 转债"""
RUNNING_JOB_PROMPT = "正在运行，请稍候。"


@dataclass
class RouteResult:
    matched: bool
    service_type: ServiceType
    raw_input: str
    target_text: str = ""
    skill_key: str = ""
    error_code: ErrorCode | None = None
    module_key: str = ""


@dataclass
class BusinessReply:
    handled: bool
    success: bool
    reply_text: str
    output_files: list[str]
    service_type: ServiceType
    error_code: ErrorCode | None = None
    user_prompt: str = ""
    detail: str = ""
    request_id: str = ""
    source_type: str = ""
    source_id: str = ""
    module_key: str = ""


def parse_route(raw_input: str) -> RouteResult:
    from business.business_registry import match_business

    matched = match_business(raw_input)
    if matched is not None:
        return RouteResult(
            True,
            matched.service_type,
            raw_input,
            matched.target_text,
            matched.skill_key,
            module_key=matched.business_key,
        )
    return RouteResult(False, ServiceType.UNMATCHED, raw_input, error_code=ErrorCode.INPUT_ERROR)


def _agent_fallback_enabled() -> bool:
    value = get_config("router.enable_agent_fallback", False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "启用", "是"}
    return bool(value)


def _customer_metadata(openid: str) -> dict[str, str]:
    try:
        from business.user_service import get_user_by_openid

        user = get_user_by_openid(openid)
    except Exception:
        user = None
    if user is None:
        return {}
    return {"customer_name": user.name, "institution": user.institution}


def _create_request_record_with_customer(
    openid: str,
    raw_input: str,
    service_type: ServiceType | None,
    customer_metadata: dict[str, str],
) -> str:
    return create_request_record(
        openid,
        raw_input,
        service_type,
        customer_name=customer_metadata.get("customer_name", ""),
        institution=customer_metadata.get("institution", ""),
    )


def handle_text_message(
    openid: str,
    raw_input: str,
    *,
    technical_analysis_handler=None,
    skip_permission: bool = False,
) -> BusinessReply:
    start = time.time()

    def elapsed() -> int:
        return int((time.time() - start) * 1000)

    customer_metadata = _customer_metadata(openid)
    if not skip_permission:
        permission = verify_user_access(openid)
        if not permission.allowed:
            request_id = _create_request_record_with_customer(
                openid,
                raw_input,
                ServiceType.UNAUTHORIZED_REQUEST,
                customer_metadata,
            )
            fail_request_record(
                request_id,
                permission.error_code or ErrorCode.UNAUTHORIZED,
                permission.user_prompt,
                permission.detail,
                elapsed(),
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

    route = parse_route(raw_input)
    if not route.matched:
        request_id = _create_request_record_with_customer(openid, raw_input, ServiceType.UNMATCHED, customer_metadata)
        fail_request_record(
            request_id,
            route.error_code or ErrorCode.INPUT_ERROR,
            DEFAULT_UNMATCHED_PROMPT,
            "unmatched business route",
            elapsed(),
        )
        return BusinessReply(
            not _agent_fallback_enabled(),
            False,
            DEFAULT_UNMATCHED_PROMPT,
            [],
            ServiceType.UNMATCHED,
            route.error_code,
            request_id=request_id,
        )

    if not skip_permission:
        permission = verify_permission(openid, route.service_type)
        if not permission.allowed:
            request_id = _create_request_record_with_customer(
                openid,
                raw_input,
                ServiceType.UNAUTHORIZED_REQUEST,
                customer_metadata,
            )
            fail_request_record(
                request_id,
                permission.error_code or ErrorCode.UNAUTHORIZED,
                permission.user_prompt,
                permission.detail,
                elapsed(),
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

    from business.business_registry import get_business_definition
    from business.module_dispatcher import dispatch_module

    definition = get_business_definition(route.module_key or route.skill_key)
    return dispatch_module(
        definition,
        openid,
        raw_input,
        route,
        customer_metadata=customer_metadata,
        elapsed=elapsed,
        technical_analysis_handler=technical_analysis_handler,
    )
