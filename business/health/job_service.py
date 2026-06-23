# encoding:utf-8
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import bindparam, insert, select, text, update

from business.config.constants import ActionType, ActorType, EntryType, ErrorCode, ServiceType, Status, user_message
from business.schema.db import connect
from business.records.records import (
    GENERATING_TIMEOUT_MINUTES,
    RequestRecord,
    _audit_values,
    _json_list,
    _now,
    _row_to_request,
    business_record_identity_values,
    external_request_identity_values,
)
from business.schema.tables import investment_request_records


@dataclass
class JobStartResult:
    created: bool
    record: RequestRecord


def _stale_cutoff() -> str:
    return (datetime.now(UTC) - timedelta(minutes=GENERATING_TIMEOUT_MINUTES)).isoformat(timespec="microseconds")


def _advisory_lock_key(openid: str, raw_input: str, service_type: ServiceType | None) -> str:
    return f"investment-job:{openid}:{raw_input}:{str(service_type) if service_type else ''}"


def _cache_advisory_lock_key(cache_key: str) -> str:
    return f"investment-cache-job:{cache_key}"


def _default_action_type(service_type: ServiceType | None) -> ActionType:
    if service_type in (ServiceType.RATE, ServiceType.CONVERTIBLE_BOND):
        return ActionType.DELIVER_EFFECTIVE_CONTENT
    return ActionType.GENERATE


def _identity_values(openid: str, service_type: ServiceType | None, record_context: dict | None = None) -> dict[str, str]:
    record_context = record_context or {}
    if not record_context:
        return external_request_identity_values(openid, service_type)
    return business_record_identity_values(
        entry_type=EntryType(str(record_context.get("entry_type") or EntryType.EXTERNAL_REQUEST)),
        action_type=ActionType(str(record_context.get("action_type") or _default_action_type(service_type))),
        actor_type=ActorType(str(record_context.get("actor_type") or ActorType.CUSTOMER)),
        actor_id=str(record_context.get("actor_id", "") or openid or ""),
        actor_name=str(record_context.get("actor_name", "") or ""),
        actor_role=str(record_context.get("actor_role", "") or ""),
    )


def _cleanup_stale_jobs(conn, openid: str, raw_input: str, service_type: ServiceType | None = None) -> None:
    conditions = [
        investment_request_records.c.openid == openid,
        investment_request_records.c.raw_input == raw_input,
        investment_request_records.c.status == str(Status.GENERATING),
        investment_request_records.c.created_at <= _stale_cutoff(),
    ]
    if service_type is not None:
        conditions.append(investment_request_records.c.service_type == str(service_type))
    conn.execute(
        update(investment_request_records)
        .where(*conditions)
        .values(
            status=str(Status.FAILED),
            error_code=str(ErrorCode.SYSTEM_ERROR),
            user_prompt=user_message(ErrorCode.SYSTEM_ERROR),
            error_message="未完成/可能超时",
            updated_at=_now(),
        )
    )


def _cleanup_stale_cache_jobs(conn, cache_key: str, service_type: ServiceType | None = None) -> None:
    conditions = [
        investment_request_records.c.cache_key == cache_key,
        investment_request_records.c.status == str(Status.GENERATING),
        investment_request_records.c.created_at <= _stale_cutoff(),
    ]
    if service_type is not None:
        conditions.append(investment_request_records.c.service_type == str(service_type))
    conn.execute(
        update(investment_request_records)
        .where(*conditions)
        .values(
            status=str(Status.FAILED),
            error_code=str(ErrorCode.SYSTEM_ERROR),
            user_prompt=user_message(ErrorCode.SYSTEM_ERROR),
            error_message="未完成/可能超时",
            updated_at=_now(),
        )
    )


def _running_select(service_type: ServiceType | None = None):
    conditions = [
        investment_request_records.c.openid == bindparam("openid"),
        investment_request_records.c.raw_input == bindparam("raw_input"),
        investment_request_records.c.status == str(Status.GENERATING),
    ]
    if service_type is not None:
        conditions.append(investment_request_records.c.service_type == str(service_type))
    return (
        select(investment_request_records)
        .where(*conditions)
        .order_by(investment_request_records.c.created_at.desc())
        .limit(1)
    )


def _running_cache_select(service_type: ServiceType | None = None):
    conditions = [
        investment_request_records.c.cache_key == bindparam("cache_key"),
        investment_request_records.c.status == str(Status.GENERATING),
    ]
    if service_type is not None:
        conditions.append(investment_request_records.c.service_type == str(service_type))
    return (
        select(investment_request_records)
        .where(*conditions)
        .order_by(investment_request_records.c.created_at.desc())
        .limit(1)
    )


def find_running_job(openid: str, raw_input: str, service_type: ServiceType | None = None) -> RequestRecord | None:
    with connect() as conn:
        _cleanup_stale_jobs(conn, openid, raw_input, service_type)
        row = conn.execute(_running_select(service_type), {"openid": openid, "raw_input": raw_input}).fetchone()
    if row is None:
        return None
    return _row_to_request(row)


def find_running_cache_job(cache_key: str, service_type: ServiceType | None = None) -> RequestRecord | None:
    if not cache_key:
        return None
    with connect() as conn:
        _cleanup_stale_cache_jobs(conn, cache_key, service_type)
        row = conn.execute(_running_cache_select(service_type), {"cache_key": cache_key}).fetchone()
    if row is None:
        return None
    return _row_to_request(row)


def start_job_if_absent(openid: str, raw_input: str, service_type: ServiceType) -> JobStartResult:
    return start_job_if_absent_with_metadata(openid, raw_input, service_type)


def start_job_if_absent_with_metadata(
    openid: str,
    raw_input: str,
    service_type: ServiceType,
    **metadata,
) -> JobStartResult:
    record_context = metadata.pop("record_context", None)
    with connect() as conn:
        conn.execute(
            text("select pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": _advisory_lock_key(openid, raw_input, service_type)},
        )
        _cleanup_stale_jobs(conn, openid, raw_input, service_type)
        running = conn.execute(_running_select(service_type), {"openid": openid, "raw_input": raw_input}).fetchone()
        if running is not None:
            return JobStartResult(False, _row_to_request(running))

        request_id = str(uuid.uuid4())
        now = _now()
        conn.execute(
            insert(investment_request_records).values(
                request_id=request_id,
                openid=openid,
                raw_input=raw_input,
                service_type=str(service_type),
                **_identity_values(openid, service_type, record_context),
                status=str(Status.GENERATING),
                output_files=_json_list([]),
                **_audit_values(**metadata),
                created_at=now,
                updated_at=now,
            )
        )
        row = conn.execute(
            select(investment_request_records).where(investment_request_records.c.request_id == request_id)
        ).fetchone()
    return JobStartResult(True, _row_to_request(row))


def start_cache_job_if_absent(
    openid: str,
    raw_input: str,
    service_type: ServiceType,
    cache_key: str,
    normalized_target: str = "",
    market_date: str = "",
    **metadata,
) -> JobStartResult:
    record_context = metadata.pop("record_context", None)
    if not cache_key:
        return start_job_if_absent_with_metadata(openid, raw_input, service_type, record_context=record_context, **metadata)

    audit_metadata = {
        **metadata,
        "cache_key": cache_key,
        "normalized_target": normalized_target,
        "market_date": market_date,
    }
    with connect() as conn:
        conn.execute(
            text("select pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": _cache_advisory_lock_key(cache_key)},
        )
        _cleanup_stale_cache_jobs(conn, cache_key, service_type)
        running = conn.execute(_running_cache_select(service_type), {"cache_key": cache_key}).fetchone()
        if running is not None:
            return JobStartResult(False, _row_to_request(running))

        request_id = str(uuid.uuid4())
        now = _now()
        conn.execute(
            insert(investment_request_records).values(
                request_id=request_id,
                openid=openid,
                raw_input=raw_input,
                service_type=str(service_type),
                **_identity_values(openid, service_type, record_context),
                status=str(Status.GENERATING),
                output_files=_json_list([]),
                **_audit_values(**audit_metadata),
                created_at=now,
                updated_at=now,
            )
        )
        row = conn.execute(
            select(investment_request_records).where(investment_request_records.c.request_id == request_id)
        ).fetchone()
    return JobStartResult(True, _row_to_request(row))
