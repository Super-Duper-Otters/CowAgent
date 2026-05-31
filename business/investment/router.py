# encoding:utf-8
import time
from dataclasses import dataclass

from .config_service import get_config, sanitize_sensitive_text
from .constants import ErrorCode, ServiceType, user_message
from .daily_content import get_latest_effective_content
from .records import create_request_record, fail_request_record, succeed_request_record
from .user_service import verify_permission, verify_user_access


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


def parse_route(raw_input: str) -> RouteResult:
    from .skill_registry import match_investment_skill

    matched = match_investment_skill(raw_input)
    if matched is not None:
        return RouteResult(True, matched.service_type, raw_input, matched.target_text, matched.skill_key)
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

    customer_metadata = _customer_metadata(openid)
    if not skip_permission:
        permission = verify_user_access(openid)
        if not permission.allowed:
            request_id = _create_request_record_with_customer(openid, raw_input, ServiceType.UNAUTHORIZED_REQUEST, customer_metadata)
            fail_request_record(request_id, permission.error_code or ErrorCode.UNAUTHORIZED, permission.user_prompt, permission.detail, elapsed())
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
        fail_request_record(request_id, route.error_code or ErrorCode.INPUT_ERROR, DEFAULT_UNMATCHED_PROMPT, "unmatched investment route", elapsed())
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
            request_id = _create_request_record_with_customer(openid, raw_input, ServiceType.UNAUTHORIZED_REQUEST, customer_metadata)
            fail_request_record(request_id, permission.error_code or ErrorCode.UNAUTHORIZED, permission.user_prompt, permission.detail, elapsed())
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

    if route.skill_key:
        from .skill_registry import get_skill_definition

        definition = get_skill_definition(route.skill_key)
        if definition.handler_type == "script":
            request_id = _create_request_record_with_customer(openid, raw_input, route.service_type, customer_metadata)
            try:
                from .skill_runner import run_investment_skill

                result = run_investment_skill(definition, openid, raw_input, route.target_text)
                if not result.success:
                    code = result.error_code or ErrorCode.SYSTEM_ERROR
                    prompt = result.user_prompt or user_message(code)
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
                        request_id,
                    )
                succeed_request_record(request_id, output_files=result.output_files, elapsed_ms=elapsed())
                return BusinessReply(True, True, result.reply_text, result.output_files, route.service_type, request_id=request_id)
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
                    request_id,
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
                request_id,
            )
        output_files = [content.output_image]
        succeed_request_record(
            request_id,
            output_files=output_files,
            elapsed_ms=elapsed(),
            artifact_roles={content.output_image: "output_image"},
        )
        return BusinessReply(True, True, _image_reply(output_files), output_files, route.service_type, request_id=request_id)

    if route.service_type == ServiceType.TECHNICAL_ANALYSIS:
        from .job_service import start_cache_job_if_absent, start_job_if_absent_with_metadata
        from .technical_analysis import prepare_technical_analysis_cache_context

        cache_context = prepare_technical_analysis_cache_context(raw_input, route.target_text)
        if cache_context.cache_key:
            job = start_cache_job_if_absent(
                openid,
                raw_input,
                route.service_type,
                cache_context.cache_key,
                normalized_target=cache_context.normalized_target,
                market_date=cache_context.market_date,
                **customer_metadata,
            )
        else:
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
                request_id=job.record.request_id,
            )
        request_id = job.record.request_id
        try:
            if technical_analysis_handler is None:
                from .technical_analysis import run_technical_analysis

                result = run_technical_analysis(openid, raw_input, route.target_text, cache_context=cache_context)
            else:
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
                    request_id,
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
            return BusinessReply(True, True, _image_reply(user_output_files), user_output_files, route.service_type, request_id=request_id)
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
                request_id,
            )

    request_id = _create_request_record_with_customer(openid, raw_input, route.service_type, customer_metadata)
    fail_request_record(request_id, ErrorCode.INPUT_ERROR, user_message(ErrorCode.INPUT_ERROR), "unsupported route", elapsed())
    return BusinessReply(
        True,
        False,
        user_message(ErrorCode.INPUT_ERROR),
        [],
        route.service_type,
        ErrorCode.INPUT_ERROR,
        request_id=request_id,
    )
