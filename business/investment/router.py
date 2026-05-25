# encoding:utf-8
import time
from dataclasses import dataclass

from .config_service import get_config, sanitize_sensitive_text
from .constants import ErrorCode, ServiceType, user_message
from .daily_content import get_latest_effective_content
from .records import create_request_record, fail_request_record, succeed_request_record
from .user_service import verify_permission


DEFAULT_UNMATCHED_PROMPT = """请输入以下格式之一：
1. 股票代码/股票名称 + 技术分析，例如：300502.SZ 技术分析
2. 利率
3. 转债"""


@dataclass
class RouteResult:
    matched: bool
    service_type: ServiceType
    raw_input: str
    target_text: str = ""
    error_code: ErrorCode | None = None


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


def parse_route(raw_input: str) -> RouteResult:
    text = (raw_input or "").strip()
    if text == "利率":
        return RouteResult(True, ServiceType.RATE, raw_input)
    if text == "转债":
        return RouteResult(True, ServiceType.CONVERTIBLE_BOND, raw_input)
    if text.endswith("技术分析"):
        target = text[: -len("技术分析")].strip()
        if target:
            return RouteResult(True, ServiceType.TECHNICAL_ANALYSIS, raw_input, target)
        return RouteResult(False, ServiceType.UNMATCHED, raw_input, error_code=ErrorCode.INPUT_ERROR)
    return RouteResult(False, ServiceType.UNMATCHED, raw_input, error_code=ErrorCode.INPUT_ERROR)


def _image_reply(paths: list[str]) -> str:
    return "\n".join(f"[图片: {path}]" for path in paths)


def _agent_fallback_enabled() -> bool:
    value = get_config("router.enable_agent_fallback", False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "启用", "是"}
    return bool(value)


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

    route = parse_route(raw_input)
    if not route.matched:
        request_id = create_request_record(openid, raw_input, ServiceType.UNMATCHED)
        fail_request_record(request_id, route.error_code or ErrorCode.INPUT_ERROR, DEFAULT_UNMATCHED_PROMPT, "unmatched investment route", elapsed())
        return BusinessReply(
            not _agent_fallback_enabled(),
            False,
            DEFAULT_UNMATCHED_PROMPT,
            [],
            ServiceType.UNMATCHED,
            route.error_code,
        )

    request_id = create_request_record(openid, raw_input, route.service_type)

    if not skip_permission:
        permission = verify_permission(openid, route.service_type)
        if not permission.allowed:
            fail_request_record(request_id, permission.error_code or ErrorCode.UNAUTHORIZED, permission.user_prompt, permission.detail, elapsed())
            return BusinessReply(
                True,
                False,
                permission.user_prompt,
                [],
                route.service_type,
                permission.error_code,
                permission.user_prompt,
                sanitize_sensitive_text(permission.detail),
            )

    if route.service_type in (ServiceType.RATE, ServiceType.CONVERTIBLE_BOND):
        content = get_latest_effective_content(route.service_type)
        if not content.success:
            code = content.error_code or ErrorCode.NO_CONTENT
            fail_request_record(request_id, code, content.user_prompt, content.detail, elapsed())
            return BusinessReply(
                True,
                False,
                content.user_prompt,
                [],
                route.service_type,
                code,
                content.user_prompt,
                sanitize_sensitive_text(content.detail),
            )
        output_files = [content.output_image]
        succeed_request_record(request_id, output_files=output_files, elapsed_ms=elapsed())
        return BusinessReply(True, True, _image_reply(output_files), output_files, route.service_type)

    if route.service_type == ServiceType.TECHNICAL_ANALYSIS:
        if technical_analysis_handler is None:
            from .technical_analysis import run_technical_analysis

            technical_analysis_handler = run_technical_analysis
        result = technical_analysis_handler(openid, raw_input, route.target_text)
        if not result.success:
            code = result.error_code or ErrorCode.TECHNICAL_ANALYSIS_FAILED
            prompt = user_message(code)
            fail_request_record(request_id, code, prompt, result.detail, elapsed())
            return BusinessReply(True, False, prompt, [], route.service_type, code, prompt, sanitize_sensitive_text(result.detail))
        user_output_files = [result.signal_card_path, result.main_chart_path]
        record_output_files = result.output_files or user_output_files
        succeed_request_record(request_id, output_files=record_output_files, elapsed_ms=elapsed())
        return BusinessReply(True, True, _image_reply(user_output_files), user_output_files, route.service_type)

    fail_request_record(request_id, ErrorCode.INPUT_ERROR, user_message(ErrorCode.INPUT_ERROR), "unsupported route", elapsed())
    return BusinessReply(True, False, user_message(ErrorCode.INPUT_ERROR), [], route.service_type, ErrorCode.INPUT_ERROR)
