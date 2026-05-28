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
RUNNING_JOB_PROMPT = "正在运行，请稍候。"


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


def _failure_reply_with_detail(prompt: str, detail: str) -> str:
    safe_detail = sanitize_sensitive_text(detail or "").strip()
    if not safe_detail:
        return prompt
    return f"{prompt}\n原因：{safe_detail}"


def _agent_fallback_enabled() -> bool:
    value = get_config("router.enable_agent_fallback", False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "启用", "是"}
    return bool(value)


def _customer_metadata(openid: str) -> dict[str, str]:
    try:
        from .user_service import get_user_by_openid

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

    route = parse_route(raw_input)
    if not route.matched:
        request_id = _create_request_record_with_customer(openid, raw_input, ServiceType.UNMATCHED, _customer_metadata(openid))
        fail_request_record(request_id, route.error_code or ErrorCode.INPUT_ERROR, DEFAULT_UNMATCHED_PROMPT, "unmatched investment route", elapsed())
        return BusinessReply(
            not _agent_fallback_enabled(),
            False,
            DEFAULT_UNMATCHED_PROMPT,
            [],
            ServiceType.UNMATCHED,
            route.error_code,
        )

    customer_metadata = _customer_metadata(openid)
    if not skip_permission:
        permission = verify_permission(openid, route.service_type)
        if not permission.allowed:
            request_id = _create_request_record_with_customer(openid, raw_input, route.service_type, customer_metadata)
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
        request_id = _create_request_record_with_customer(openid, raw_input, route.service_type, customer_metadata)
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
        succeed_request_record(
            request_id,
            output_files=output_files,
            elapsed_ms=elapsed(),
            artifact_roles={content.output_image: "output_image"},
        )
        return BusinessReply(True, True, _image_reply(output_files), output_files, route.service_type)

    if route.service_type == ServiceType.TECHNICAL_ANALYSIS:
        from .job_service import start_job_if_absent_with_metadata

        job = start_job_if_absent_with_metadata(openid, raw_input, route.service_type, **customer_metadata)
        if not job.created:
            return BusinessReply(
                True,
                False,
                RUNNING_JOB_PROMPT,
                [],
                route.service_type,
                user_prompt=RUNNING_JOB_PROMPT,
                detail=job.record.request_id,
            )
        request_id = job.record.request_id
        try:
            if technical_analysis_handler is None:
                from .technical_analysis import run_technical_analysis

                technical_analysis_handler = run_technical_analysis
            result = technical_analysis_handler(openid, raw_input, route.target_text)
            if not result.success:
                code = result.error_code or ErrorCode.TECHNICAL_ANALYSIS_FAILED
                prompt = user_message(code)
                fail_request_record(request_id, code, prompt, result.detail, elapsed())
                detail = sanitize_sensitive_text(result.detail)
                return BusinessReply(
                    True,
                    False,
                    _failure_reply_with_detail(prompt, detail),
                    [],
                    route.service_type,
                    code,
                    prompt,
                    detail,
                )
            user_output_files = [result.signal_card_path, result.main_chart_path]
            record_output_files = result.output_files or user_output_files
            artifact_roles = {
                result.signal_card_path: "signal_card",
                result.main_chart_path: "main_chart",
                result.report_path: "markdown_report",
            }
            artifact_versions = {
                result.signal_card_path: result.renderer_version,
                result.main_chart_path: result.ta_version,
                result.report_path: result.ta_version,
            }
            if result.cache_key and not result.cache_hit:
                from .cache_service import write_cache_entry

                write_cache_entry(
                    cache_key=result.cache_key,
                    service_type=ServiceType.TECHNICAL_ANALYSIS,
                    normalized_target=result.normalized_target,
                    market_date=result.market_date,
                    version_fingerprint=result.version_fingerprint,
                    output_files=record_output_files,
                    artifact_owner_id=request_id,
                )
            succeed_request_record(
                request_id,
                output_files=record_output_files,
                elapsed_ms=elapsed(),
                artifact_roles=artifact_roles,
                artifact_versions=artifact_versions,
                normalized_target=result.normalized_target,
                stock_code=result.stock_code,
                stock_name=result.stock_name,
                market_date=result.market_date,
                cache_key=result.cache_key,
                cache_hit=result.cache_hit,
                program_version=result.program_version,
                ta_version=result.ta_version,
                renderer_version=result.renderer_version,
                template_version=result.template_version,
                warning=result.detail,
                **customer_metadata,
            )
            return BusinessReply(True, True, _image_reply(user_output_files), user_output_files, route.service_type)
        except Exception as exc:
            detail = sanitize_sensitive_text(str(exc))
            prompt = user_message(ErrorCode.SYSTEM_ERROR)
            fail_request_record(request_id, ErrorCode.SYSTEM_ERROR, prompt, detail, elapsed())
            return BusinessReply(
                True,
                False,
                prompt,
                [],
                route.service_type,
                ErrorCode.SYSTEM_ERROR,
                prompt,
                detail,
            )

    request_id = _create_request_record_with_customer(openid, raw_input, route.service_type, customer_metadata)
    fail_request_record(request_id, ErrorCode.INPUT_ERROR, user_message(ErrorCode.INPUT_ERROR), "unsupported route", elapsed())
    return BusinessReply(True, False, user_message(ErrorCode.INPUT_ERROR), [], route.service_type, ErrorCode.INPUT_ERROR)
