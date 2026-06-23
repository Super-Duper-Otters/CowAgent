# encoding:utf-8
"""CowAgent built-in content business handler for rate and convertible bond."""

from business.records.business_records import (
    create_business_record as create_request_record,
    mark_business_failed as fail_request_record,
    mark_business_success as succeed_request_record,
)
from business.config.config_service import sanitize_sensitive_text
from business.config.constants import ErrorCode, ServiceType
from business.execution.daily_content_executor import get_daily_content_business


def _image_reply(paths: list[str]) -> str:
    return "\n".join(f"[图片: {path}]" for path in paths)


def _create_request_record_with_customer(
    openid: str,
    raw_input: str,
    service_type: ServiceType | None,
    customer_metadata: dict[str, str],
    record_context: dict | None = None,
) -> str:
    return create_request_record(
        openid,
        raw_input,
        service_type,
        record_context=record_context,
        customer_name=customer_metadata.get("customer_name", ""),
        institution=customer_metadata.get("institution", ""),
    )


def handle_daily_content(
    openid: str,
    raw_input: str,
    route,
    *,
    definition=None,
    customer_metadata: dict[str, str] | None = None,
    record_context: dict | None = None,
    elapsed=lambda: 0,
):
    from business.routing.router import BusinessReply

    customer_metadata = customer_metadata or {}
    module_key = getattr(definition, "business_key", "") or getattr(route, "module_key", "")
    service_type = getattr(definition, "service_type", None) or route.service_type
    request_id = _create_request_record_with_customer(openid, raw_input, service_type, customer_metadata, record_context)
    content = get_daily_content_business(service_type, module_key=module_key)
    if not content.success:
        code = content.error_code or ErrorCode.NO_CONTENT
        fail_request_record(request_id, code, content.user_prompt, content.detail, elapsed())
        return BusinessReply(
            True,
            False,
            content.user_prompt,
            [],
            service_type,
            code,
            content.user_prompt,
            sanitize_sensitive_text(content.detail),
            request_id,
            module_key=module_key,
        )

    output_files = [content.output_image]
    succeed_request_record(
        request_id,
        output_files=output_files,
        elapsed_ms=elapsed(),
        artifact_roles={content.output_image: "output_image"},
    )
    return BusinessReply(
        True,
        True,
        _image_reply(output_files),
        output_files,
        service_type,
        request_id=request_id,
        source_type="content",
        source_id=content.content_id,
        module_key=module_key,
    )
