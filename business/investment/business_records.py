# encoding:utf-8
from .constants import ErrorCode, ServiceType


def create_business_record(
    openid: str,
    raw_input: str,
    service_type: ServiceType | None,
    **metadata,
) -> str:
    from .records import create_request_record

    return create_request_record(openid, raw_input, service_type, **metadata)


def mark_business_success(
    request_id: str,
    *,
    output_files: list[str],
    elapsed_ms: int,
    **metadata,
) -> None:
    from .records import succeed_request_record

    succeed_request_record(request_id, output_files=output_files, elapsed_ms=elapsed_ms, **metadata)


def mark_business_failed(
    request_id: str,
    error_code: ErrorCode,
    user_prompt: str | None = None,
    detail: str = "",
    elapsed_ms: int = 0,
) -> None:
    from .records import fail_request_record

    fail_request_record(request_id, error_code, user_prompt, detail, elapsed_ms)


def append_delivery_warning(request_id: str, detail: str) -> None:
    from .records import append_request_warning

    append_request_warning(request_id, detail)
