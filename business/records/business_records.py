# encoding:utf-8
from business.config.constants import ActionType, ActorType, EntryType, ErrorCode, ServiceType
from business.audit.event_service import record_request_event
from business.records.records import (
    append_request_warning,
    build_artifact_package_tree,
    create_business_workflow_record,
    create_request_record,
    fail_request_record,
    finish_business_workflow_record,
    get_content_record,
    get_file_record,
    get_file_record_by_path,
    get_request_record,
    list_artifact_folder_nodes,
    list_artifact_packages_page,
    list_content_records,
    list_content_records_page,
    list_output_files,
    list_request_records,
    list_request_records_page,
    mark_request_delivered,
    record_output_file,
    succeed_request_record,
)


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

    return create_request_record(openid, raw_input, service_type, **metadata)


def mark_business_success(
    request_id: str,
    *,
    output_files: list[str],
    elapsed_ms: int,
    **metadata,
) -> dict[str, str]:
    return succeed_request_record(request_id, output_files=output_files, elapsed_ms=elapsed_ms, **metadata)


def mark_business_failed(
    request_id: str,
    error_code: ErrorCode,
    user_prompt: str | None = None,
    detail: str = "",
    elapsed_ms: int = 0,
) -> None:
    fail_request_record(request_id, error_code, user_prompt, detail, elapsed_ms)


def append_delivery_warning(request_id: str, detail: str) -> None:
    append_request_warning(request_id, detail)
