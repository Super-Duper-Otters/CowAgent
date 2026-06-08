# encoding:utf-8
"""CowAgent built-in technical analysis business handler."""

from business.investment.artifacts import archive_business_output_files
from business.cache_service import write_business_cache
from business.business_records import (
    mark_business_failed as fail_request_record,
    mark_business_success as succeed_request_record,
)
from business.config_service import sanitize_sensitive_text
from business.constants import ErrorCode, ServiceType, user_message
from business.investment.executors.technical_analysis_executor import (
    prepare_technical_analysis_business_context,
    run_technical_analysis_business,
)
from business.job_service import start_cache_job_if_absent, start_job_if_absent_with_metadata


RUNNING_JOB_PROMPT = "正在运行，请稍候。"


def _image_reply(paths: list[str]) -> str:
    return "\n".join(f"[图片: {path}]" for path in paths)


def _failure_reply_with_detail(prompt: str, detail: str) -> str:
    safe_detail = sanitize_sensitive_text(detail or "").strip()
    if not safe_detail:
        return prompt
    return f"{prompt}\n原因：{safe_detail}"


def handle_technical_analysis(
    openid: str,
    raw_input: str,
    route,
    *,
    customer_metadata: dict[str, str] | None = None,
    elapsed=lambda: 0,
    technical_analysis_handler=None,
):
    from business.router import BusinessReply

    customer_metadata = customer_metadata or {}
    cache_context = prepare_technical_analysis_business_context(raw_input, route.target_text)
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
            result = run_technical_analysis_business(openid, raw_input, route.target_text, cache_context=cache_context)
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
        record_output_files, artifact_roles, artifact_versions, archived_path_map = archive_business_output_files(
            request_id,
            record_output_files,
            route.service_type,
            artifact_roles=artifact_roles,
            artifact_versions=artifact_versions,
            owner_type="request",
            storage_date=result.market_date,
        )
        user_output_files = [
            archived_path_map.get(result.signal_card_path, result.signal_card_path),
            archived_path_map.get(result.main_chart_path, result.main_chart_path),
        ]
        if result.cache_key and not result.cache_hit:
            write_business_cache(
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
        return BusinessReply(
            True,
            True,
            _image_reply(user_output_files),
            user_output_files,
            route.service_type,
            request_id=request_id,
            source_type="cache" if result.cache_key else "",
            source_id=result.cache_key or "",
        )
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
