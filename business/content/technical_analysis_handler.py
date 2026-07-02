# encoding:utf-8
"""CowAgent built-in technical analysis business handler."""

from business.artifacts.artifacts import archive_business_output_files
from business.cache.cache_service import write_business_cache
from business.records.business_records import (
    mark_business_failed as fail_request_record,
    mark_business_success as succeed_request_record,
)
from business.config.config_service import sanitize_sensitive_text
from business.config.constants import ErrorCode, ServiceType, user_message
from business.execution.technical_analysis_executor import (
    prepare_technical_analysis_business_context,
    run_technical_analysis_business,
)
from business.health.job_service import start_cache_job_if_absent, start_job_if_absent_with_metadata
from business.products.product_service import replace_active_product

def _image_reply(paths: list[str]) -> str:
    return "\n".join(f"[图片: {path}]" for path in paths)


def _failure_reply_with_detail(prompt: str, detail: str) -> str:
    safe_detail = sanitize_sensitive_text(detail or "").strip()
    if not safe_detail:
        return prompt
    return f"{prompt}\n原因：{safe_detail}"


def _customer_failure_reply(prompt: str, code: ErrorCode | None, detail: str) -> str:
    if code == ErrorCode.STOCK_AMBIGUOUS:
        if (prompt or "").strip() == (detail or "").strip():
            return prompt
        return _failure_reply_with_detail(prompt, detail)
    return prompt


def _target_label(stock_code: str, stock_name: str) -> str:
    code = str(stock_code or "").strip()
    name = str(stock_name or "").strip()
    if code and name and code != name:
        return f"{code} {name}"
    return code or name


def validate_technical_analysis_request(raw_input: str, route) -> str:
    """Return a user-facing error when a technical-analysis request cannot start."""
    from business.content.technical_analysis import (
        _target_and_requested_market_date,
        _technical_analysis_error_prompt,
        _technical_analysis_target_from_input,
        parse_target,
    )

    target_text = getattr(route, "target_text", "") or parse_target(raw_input)
    target, _requested_market_date = _target_and_requested_market_date(target_text)
    target_info, error, detail = _technical_analysis_target_from_input(target)
    if error:
        return _customer_failure_reply(_technical_analysis_error_prompt(error, detail), error, detail)
    if not target_info.normalized_target:
        return _customer_failure_reply(
            user_message(ErrorCode.STOCK_NOT_FOUND),
            ErrorCode.STOCK_NOT_FOUND,
            f"cannot resolve stock: {target}",
        )
    return ""


def get_ready_technical_analysis_reply(
    openid: str,
    raw_input: str,
    route,
    *,
    customer_metadata: dict[str, str] | None = None,
    record_context: dict | None = None,
    elapsed=lambda: 0,
):
    from business.cache.cache_service import find_cache_entry_by_key, technical_analysis_cache_expired_after_close
    from business.products.product_service import invalidate_products_by_source

    cache_context = prepare_technical_analysis_business_context(raw_input, route.target_text)
    if not cache_context.cache_key:
        return None
    entry = find_cache_entry_by_key(cache_context.cache_key, require_files=True)
    if entry is None:
        return None
    if technical_analysis_cache_expired_after_close(
        entry.market_date,
        entry.updated_at,
        normalized_target=entry.normalized_target,
    ):
        invalidate_products_by_source(source_cache_key=entry.cache_key)
        return None
    return handle_technical_analysis(
        openid,
        raw_input,
        route,
        customer_metadata=customer_metadata,
        record_context=record_context,
        elapsed=elapsed,
        cache_context=cache_context,
    )


def handle_technical_analysis(
    openid: str,
    raw_input: str,
    route,
    *,
    customer_metadata: dict[str, str] | None = None,
    record_context: dict | None = None,
    elapsed=lambda: 0,
    technical_analysis_handler=None,
    cache_context=None,
):
    from business.routing.router import BusinessReply

    customer_metadata = customer_metadata or {}
    cache_context = cache_context or prepare_technical_analysis_business_context(raw_input, route.target_text)
    if cache_context.cache_key:
        job = start_cache_job_if_absent(
            openid,
            raw_input,
            route.service_type,
            cache_context.cache_key,
            normalized_target=cache_context.normalized_target,
            market_date=cache_context.market_date,
            record_context=record_context,
            **customer_metadata,
        )
    else:
        job = start_job_if_absent_with_metadata(
            openid,
            raw_input,
            route.service_type,
            record_context=record_context,
            **customer_metadata,
    )
    if not job.created:
        running_prompt = user_message(ErrorCode.RUNNING)
        return BusinessReply(
            True,
            False,
            running_prompt,
            [],
            route.service_type,
            user_prompt=running_prompt,
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
            prompt = result.user_prompt or user_message(code)
            fail_request_record(request_id, code, prompt, result.detail, elapsed())
            detail = sanitize_sensitive_text(result.detail)
            return BusinessReply(
                True,
                False,
                _customer_failure_reply(prompt, code, detail),
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
        analysis_date = str(getattr(job.record, "created_at", "") or "")[:10]
        record_output_files, artifact_roles, artifact_versions, archived_path_map = archive_business_output_files(
            request_id,
            record_output_files,
            route.service_type,
            artifact_roles=artifact_roles,
            artifact_versions=artifact_versions,
            owner_type="request",
            storage_date=analysis_date,
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
        product_id = ""
        if (
            not result.cache_hit
            and not result.cache_key
            and result.normalized_target
            and result.market_date
            and result.version_fingerprint
            and record_output_files
        ):
            product = replace_active_product(
                business_type=str(ServiceType.TECHNICAL_ANALYSIS),
                target_key=result.normalized_target,
                target_label=_target_label(result.stock_code, result.stock_name),
                business_date=result.market_date,
                version_fingerprint=result.version_fingerprint,
                output_files=record_output_files,
                source_type="request",
                source_request_id=request_id,
                source_cache_key=result.cache_key,
                metadata={
                    "program_version": result.program_version,
                    "ta_version": result.ta_version,
                    "renderer_version": result.renderer_version,
                    "template_version": result.template_version,
                },
            )
            product_id = str(product.get("product_id") or "")
        return BusinessReply(
            True,
            True,
            _image_reply(user_output_files),
            user_output_files,
            route.service_type,
            request_id=request_id,
            source_type=(
                "product"
                if product_id
                else getattr(result, "source_type", "")
                or ("cache" if result.cache_key else "")
            ),
            source_id=product_id or getattr(result, "source_id", "") or result.cache_key or "",
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
