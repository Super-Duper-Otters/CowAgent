# encoding:utf-8
from .constants import ActionType, ActorType, EntryType, ErrorCode, ServiceType


def _coerce_entry_type(value) -> EntryType:
    if isinstance(value, EntryType):
        return value
    return EntryType(str(value or EntryType.EXTERNAL_REQUEST))


def _coerce_actor_type(value) -> ActorType:
    if isinstance(value, ActorType):
        return value
    return ActorType(str(value or ActorType.CUSTOMER))


def _default_action_type(service_type: ServiceType | None) -> ActionType:
    if service_type in (ServiceType.RATE, ServiceType.CONVERTIBLE_BOND):
        return ActionType.DELIVER_EFFECTIVE_CONTENT
    return ActionType.GENERATE


def _coerce_action_type(value, service_type: ServiceType | None) -> ActionType:
    if isinstance(value, ActionType):
        return value
    if value:
        return ActionType(str(value))
    return _default_action_type(service_type)


def create_business_record(
    openid: str,
    raw_input: str,
    service_type: ServiceType | None,
    **metadata,
) -> str:
    record_context = metadata.pop("record_context", None) or {}
    if record_context:
        from .records import create_business_workflow_record

        return create_business_workflow_record(
            entry_type=_coerce_entry_type(record_context.get("entry_type")),
            service_type=service_type,
            action_type=_coerce_action_type(record_context.get("action_type"), service_type),
            actor_type=_coerce_actor_type(record_context.get("actor_type")),
            actor_id=str(record_context.get("actor_id", "") or openid or ""),
            actor_name=str(record_context.get("actor_name", "") or ""),
            actor_role=str(record_context.get("actor_role", "") or ""),
            openid=openid,
            raw_input=raw_input,
            **metadata,
        )

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
