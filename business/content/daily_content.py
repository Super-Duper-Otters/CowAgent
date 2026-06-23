# encoding:utf-8
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import and_, insert, or_, select, update

from business.audit_service import AdminActor, actor_from_admin, record_operation_audit
from business.config_service import sanitize_sensitive_text
from business.constants import ActionType, ActorType, EntryType, ErrorCode, ServiceType, Status, user_message
from business.db import connect, row_to_dict
from business.records import create_business_workflow_record, finish_business_workflow_record, record_output_file
from business.render_service import DEFAULT_RENDERER_PATH, template_for_service
from business.schema import investment_daily_contents
from business.storage import get_storage_dirs
from business.versioning import file_fingerprint


@dataclass
class DailyContentResult:
    success: bool
    content_id: str = ""
    output_image: str = ""
    generated_text: str = ""
    input_prompt: str = ""
    error_code: ErrorCode | None = None
    user_prompt: str = ""
    detail: str = ""
    output_files: list[str] = field(default_factory=list)


CONTENT_STATUSES = (
    Status.DRAFT,
    Status.GENERATING,
    Status.GENERATED,
    Status.GENERATE_FAILED,
    Status.EFFECTIVE,
    Status.ARCHIVED,
    Status.INVALIDATED,
)

AIGenerator = Callable[..., Any]
Renderer = Callable[[ServiceType, str], Any]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _beijing_now() -> datetime:
    return datetime.now(UTC) + timedelta(hours=8)


def _actor_identity(actor: Any | None, fallback_operator: str = ""):
    audit_actor = actor_from_admin(actor)
    operator = audit_actor.username if audit_actor is not None and audit_actor.username else fallback_operator
    return operator, audit_actor


def _content_actor_values(actor: Any | None, *, prefix: str) -> dict[str, Any]:
    if actor is None:
        return {}
    return {
        f"{prefix}_by_admin_id": getattr(actor, "id", None),
        f"{prefix}_by_username": str(getattr(actor, "username", "") or ""),
        f"{prefix}_by_role": str(getattr(actor, "role", "") or ""),
    }


def _actor_from_content_item(item: dict[str, Any]) -> AdminActor | None:
    admin_id = item.get("updated_by_admin_id") or item.get("created_by_admin_id")
    username = item.get("updated_by_username") or item.get("created_by_username") or item.get("operator") or ""
    role = item.get("updated_by_role") or item.get("created_by_role") or ""
    if admin_id is None and not username and not role:
        return None
    return AdminActor(admin_id=admin_id, username=username, role=role)


def _today() -> str:
    return _beijing_now().date().isoformat()


def _normalize_effective_date(value: str | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        return _today()
    return date.fromisoformat(text).isoformat()


def _normalize_expires_at(value: str | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) == 10:
        parsed = datetime.combine(date.fromisoformat(text), time.min)
    else:
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed - timedelta(hours=8)
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    return parsed.isoformat(timespec="microseconds")


def default_expires_at_for_effective_date(effective_date: str | None = None) -> str:
    normalized_effective_date = _normalize_effective_date(effective_date)
    next_day = date.fromisoformat(normalized_effective_date) + timedelta(days=1)
    beijing_midnight = datetime.combine(next_day, time.min)
    return _normalize_expires_at(beijing_midnight.isoformat(timespec="minutes"))


def _output_image_version(service_type: ServiceType) -> str:
    from business.config_service import get_config

    renderer_path = Path(str(get_config("render.renderer_path") or DEFAULT_RENDERER_PATH))
    if not renderer_path.is_absolute():
        renderer_path = Path.cwd() / renderer_path
    renderer_version = file_fingerprint(renderer_path)
    try:
        template_version = file_fingerprint(template_for_service(service_type))
    except ValueError:
        template_version = ""
    return f"{renderer_version}|{template_version}"


def _safe_output_segment(value: str, fallback: str = "item") -> str:
    text = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(value or "").strip()).strip("._-")
    return text[:80] or fallback


def _daily_content_render_output_path(item: dict[str, Any], service_type: ServiceType) -> str:
    from business.config_service import get_config

    output_dir = Path(str(get_config("render.output_dir") or get_config("storage.tmp_dir") or (get_storage_dirs()["tmp"] / "render")))
    if not output_dir.is_absolute():
        output_dir = Path.cwd() / output_dir
    effective_date = _safe_output_segment(item.get("effective_date") or _today(), "unknown-date")
    version = int(item.get("content_version") or 1)
    content_id = _safe_output_segment(str(item.get("content_id") or "")[:8], "content")
    service = _safe_output_segment(str(service_type), "service")
    target_dir = output_dir / "daily-content" / service / effective_date
    target_dir.mkdir(parents=True, exist_ok=True)
    return str(target_dir / f"{service}_{effective_date}_v{version}_{content_id}.png")


def _load_source_files(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if not value:
        return []
    try:
        data = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if str(item).strip()]


def _ensure_content_service_type(service_type: ServiceType) -> ServiceType:
    return ServiceType(service_type)


def _normalize_module_key(value: str | None = "") -> str:
    return str(value or "").strip()


def _allows_legacy_content_fallback(service_type: ServiceType, module_key: str) -> bool:
    return bool(module_key) and module_key in {str(service_type), str(service_type).replace("_", "-")}


def save_source_file(
    service_type: ServiceType,
    filename: str,
    content: bytes,
    *,
    owner_id: str = "unassigned",
    effective_date: str | None = None,
    module_key: str = "",
) -> str:
    from business.config_service import get_config

    service_type = _ensure_content_service_type(service_type)
    safe_name = (filename or "").strip()
    if not safe_name or safe_name != Path(safe_name).name or "/" in safe_name or "\\" in safe_name:
        raise ValueError("invalid source filename")
    files_root = Path(str(get_config("storage.files_dir") or get_storage_dirs()["files"]))
    if not files_root.is_absolute():
        files_root = Path.cwd() / files_root
    storage_date = _safe_output_segment(effective_date or _today(), "unknown-date")
    target_dir = (
        files_root
        / _safe_output_segment(str(service_type), "service")
        / storage_date
        / "content"
        / _safe_output_segment(owner_id, "content")
        / "source_image"
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"source_image_{uuid.uuid4().hex}_{safe_name}"
    target.write_bytes(content)
    return str(target)


def create_content_draft(
    service_type: ServiceType,
    *,
    source_files: list[str] | None = None,
    source_text: str = "",
    operator: str = "",
    effective_date: str | None = None,
    expires_at: str | None = None,
    auto_effective_after_generate: bool = False,
    actor: Any | None = None,
    module_key: str = "",
) -> str:
    service_type = _ensure_content_service_type(service_type)
    normalized_module_key = _normalize_module_key(module_key)
    normalized_effective_date = _normalize_effective_date(effective_date)
    normalized_expires_at = _normalize_expires_at(expires_at)
    content_id = str(uuid.uuid4())
    now = _now()
    operator, audit_actor = _actor_identity(actor, operator)
    actor_values = {}
    actor_values.update(_content_actor_values(actor, prefix="created"))
    actor_values.update(_content_actor_values(actor, prefix="updated"))
    with connect() as conn:
        version_conditions = [
            investment_daily_contents.c.service_type == str(service_type),
            investment_daily_contents.c.effective_date == normalized_effective_date,
        ]
        if normalized_module_key:
            version_conditions.append(investment_daily_contents.c.module_key == normalized_module_key)
        version_row = conn.execute(
            select(investment_daily_contents.c.content_version)
            .where(*version_conditions)
            .order_by(investment_daily_contents.c.content_version.desc())
            .limit(1)
        ).fetchone()
        content_version = int(row_to_dict(version_row).get("content_version") or 0) + 1
        conn.execute(
            insert(investment_daily_contents).values(
                content_id=content_id,
                service_type=str(service_type),
                module_key=normalized_module_key,
                source_files=json.dumps(source_files or [], ensure_ascii=False),
                source_text=source_text,
                status=str(Status.DRAFT),
                operator=operator,
                effective_date=normalized_effective_date,
                expires_at=normalized_expires_at,
                content_version=content_version,
                direct_output_mode=0,
                auto_effective_after_generate=1 if auto_effective_after_generate else 0,
                created_at=now,
                updated_at=now,
                **actor_values,
            )
        )
    record_operation_audit(
        "content.create",
        "daily_content",
        content_id,
        operator=operator,
        actor=audit_actor,
        detail={
            "service_type": str(service_type),
            "module_key": normalized_module_key,
            "effective_date": normalized_effective_date,
            "expires_at": normalized_expires_at,
            "content_version": content_version,
            "auto_effective_after_generate": bool(auto_effective_after_generate),
        },
    )
    return content_id


def create_rate_content_draft(
    *,
    source_files: list[str] | None = None,
    source_text: str = "",
    operator: str = "",
    effective_date: str | None = None,
    expires_at: str | None = None,
    auto_effective_after_generate: bool = False,
    actor: Any | None = None,
) -> str:
    return create_content_draft(
        ServiceType.RATE,
        source_files=source_files,
        source_text=source_text,
        operator=operator,
        effective_date=effective_date,
        expires_at=expires_at,
        auto_effective_after_generate=auto_effective_after_generate,
        actor=actor,
    )


def create_convertible_bond_content_draft(
    *,
    source_files: list[str] | None = None,
    source_text: str = "",
    operator: str = "",
    effective_date: str | None = None,
    expires_at: str | None = None,
    auto_effective_after_generate: bool = False,
    actor: Any | None = None,
) -> str:
    return create_content_draft(
        ServiceType.CONVERTIBLE_BOND,
        source_files=source_files,
        source_text=source_text,
        operator=operator,
        effective_date=effective_date,
        expires_at=expires_at,
        auto_effective_after_generate=auto_effective_after_generate,
        actor=actor,
    )


def update_content_source(content_id: str, *, source_files: list[str] | None = None, source_text: str | None = None) -> None:
    values: dict[str, Any] = {"updated_at": _now()}
    if source_files is not None:
        values["source_files"] = json.dumps(source_files, ensure_ascii=False)
    if source_text is not None:
        values["source_text"] = source_text
    with connect() as conn:
        conn.execute(
            update(investment_daily_contents)
            .where(investment_daily_contents.c.content_id == content_id)
            .values(**values)
        )


def _mark_generation_started(content_id: str, *, actor: Any | None = None) -> None:
    values = {"status": str(Status.GENERATING), "error_message": "", "updated_at": _now()}
    values.update(_content_actor_values(actor, prefix="updated"))
    with connect() as conn:
        conn.execute(
            update(investment_daily_contents)
            .where(investment_daily_contents.c.content_id == content_id)
            .values(**values)
        )


def mark_generation_started(content_id: str, *, actor: Any | None = None) -> DailyContentResult:
    with connect() as conn:
        row = conn.execute(
            select(investment_daily_contents.c.service_type).where(investment_daily_contents.c.content_id == content_id)
        ).fetchone()
    if row is None:
        return DailyContentResult(False, content_id=content_id, error_code=ErrorCode.SYSTEM_ERROR, user_prompt=user_message(ErrorCode.SYSTEM_ERROR), detail="content not found")
    service_type = ServiceType(row_to_dict(row)["service_type"])
    _ensure_content_service_type(service_type)
    _mark_generation_started(content_id, actor=actor)
    return DailyContentResult(True, content_id=content_id)


def update_generation_success(content_id: str, generated_text: str, output_image: str, input_prompt: str = "") -> str:
    service_type: ServiceType | None = None
    operator = ""
    audit_actor = None
    stored_output_image = output_image
    with connect() as conn:
        row = conn.execute(
            select(investment_daily_contents).where(investment_daily_contents.c.content_id == content_id)
        ).fetchone()
        item = row_to_dict(row)
        if item.get("service_type"):
            service_type = ServiceType(item["service_type"])
        operator = item.get("operator") or ""
        audit_actor = _actor_from_content_item(item)
    if output_image and service_type is not None:
        from business.artifact_service import archive_artifact_file

        stored_output_image = archive_artifact_file(
            content_id,
            output_image,
            "output_image",
            service_type,
            owner_type="content",
        )
    with connect() as conn:
        conn.execute(
            update(investment_daily_contents)
            .where(investment_daily_contents.c.content_id == content_id)
            .values(
                input_prompt=str(input_prompt or ""),
                generated_text=generated_text,
                output_image=stored_output_image,
                status=str(Status.GENERATED),
                error_message="",
                updated_at=_now(),
            )
        )
    if stored_output_image and service_type is not None:
        record_output_file(
            content_id,
            stored_output_image,
            None,
            service_type,
            artifact_role="output_image",
            version_tag=_output_image_version(service_type),
            owner_type="content",
        )
    if item.get("auto_effective_after_generate"):
        set_content_effective(
            content_id,
            stored_output_image,
            effective_date=item.get("effective_date") or None,
            expires_at=item.get("expires_at") if "expires_at" in item else None,
            operator=operator,
            actor=audit_actor,
        )
    record_operation_audit(
        "content.generate",
        "daily_content",
        content_id,
        operator=operator,
        actor=audit_actor,
        detail={"service_type": str(service_type) if service_type else "", "output_image": stored_output_image},
    )
    return stored_output_image


def update_generation_failure(content_id: str, detail: str, input_prompt: str = "") -> None:
    safe_detail = sanitize_sensitive_text(detail)
    operator = ""
    audit_actor = None
    with connect() as conn:
        row = conn.execute(
            select(investment_daily_contents).where(investment_daily_contents.c.content_id == content_id)
        ).fetchone()
        item = row_to_dict(row)
        operator = item.get("operator") or ""
        audit_actor = _actor_from_content_item(item)
        conn.execute(
            update(investment_daily_contents)
            .where(investment_daily_contents.c.content_id == content_id)
            .values(
                status=str(Status.GENERATE_FAILED),
                error_message=safe_detail,
                input_prompt=str(input_prompt or ""),
                updated_at=_now(),
            )
        )
    record_operation_audit(
        "content.generate",
        "daily_content",
        content_id,
        operator=operator,
        actor=audit_actor,
        detail={"success": False, "detail": safe_detail},
    )


def _module_definition(module_key: str):
    if not module_key:
        return None
    try:
        from business.business_registry import get_business_definition

        return get_business_definition(module_key)
    except Exception:
        return None


def _default_ai_generator(
    service_type: ServiceType,
    source_text: str,
    source_files: list[str] | None = None,
    *,
    module_key: str = "",
    prompt_key: str = "",
):
    if module_key or prompt_key:
        from business.prompt_to_image_handler import generate_standard_text_for_module

        return generate_standard_text_for_module(
            service_type,
            source_text,
            source_files=source_files,
            prompt_key=prompt_key,
            module_key=module_key,
        )
    from business.ai_generation import generate_standard_text

    return generate_standard_text(service_type, source_text, source_files=source_files)


def _default_renderer(
    service_type: ServiceType,
    generated_text: str,
    output_path: str | None = None,
    *,
    template_key: str = "",
):
    from business.render_service import RenderRequest, render_card

    return render_card(
        RenderRequest(
            service_type=service_type,
            standard_text=generated_text,
            output_path=output_path,
            template_key=template_key,
        )
    )


def generate_content(
    content_id: str,
    ai_generator: AIGenerator | None = None,
    renderer: Renderer | None = None,
    actor: Any | None = None,
) -> DailyContentResult:
    started_at = datetime.now(UTC)
    business_request_id = ""
    ai_audit_id = ""
    with connect() as conn:
        row = conn.execute(
            select(investment_daily_contents).where(investment_daily_contents.c.content_id == content_id)
        ).fetchone()
    if row is None:
        return DailyContentResult(False, content_id=content_id, error_code=ErrorCode.SYSTEM_ERROR, user_prompt=user_message(ErrorCode.SYSTEM_ERROR), detail="content not found")
    item = row_to_dict(row)
    service_type = ServiceType(item["service_type"])
    _ensure_content_service_type(service_type)
    module_key = _normalize_module_key(item.get("module_key"))
    definition = _module_definition(module_key)
    prompt_key = str(getattr(definition, "prompt_key", "") or "")
    template_key = str(getattr(definition, "template_key", "") or "")
    source_files = _load_source_files(item.get("source_files"))
    operator, audit_actor = _actor_identity(actor, item.get("operator") or "")
    actor_id = str(getattr(audit_actor, "admin_id", "") or "")
    actor_role = str(getattr(audit_actor, "role", "") or "")
    actor_type = ActorType.ADMIN if audit_actor is not None else ActorType.SYSTEM
    try:
        business_request_id = create_business_workflow_record(
            entry_type=EntryType.INTERNAL_CALL,
            service_type=service_type,
            action_type=ActionType.GENERATE,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_name=operator,
            actor_role=actor_role,
            raw_input=item["source_text"] or "",
        )
    except Exception:
        business_request_id = ""
    _mark_generation_started(content_id, actor=actor)
    try:
        from business.ai_generation_audit import start_ai_generation_audit

        ai_audit_id = start_ai_generation_audit(
            entry_type=EntryType.INTERNAL_CALL,
            service_type=service_type,
            action_type=ActionType.GENERATE,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_name=operator,
            actor_role=actor_role,
            business_record_type="request",
            business_record_id=business_request_id,
            input_text=item["source_text"] or "",
            sources=source_files,
        )
    except Exception:
        ai_audit_id = ""
    if ai_generator is None:
        ai_result = _default_ai_generator(
            service_type,
            item["source_text"] or "",
            source_files,
            module_key=module_key,
            prompt_key=prompt_key,
        )
    else:
        try:
            ai_result = ai_generator(service_type, item["source_text"] or "", source_files)
        except TypeError:
            ai_result = ai_generator(service_type, item["source_text"] or "")
    if not ai_result.success:
        detail = sanitize_sensitive_text(getattr(ai_result, "detail", "AI generation failed"))
        input_prompt = str(getattr(ai_result, "prompt", "") or "")
        code = getattr(ai_result, "error_code", None) or ErrorCode.SYSTEM_ERROR
        update_generation_failure(content_id, detail, input_prompt=input_prompt)
        if business_request_id:
            finish_business_workflow_record(
                business_request_id,
                status=Status.FAILED,
                error_code=str(code),
                user_prompt=user_message(code),
                error_message=detail,
                elapsed_ms=int((datetime.now(UTC) - started_at).total_seconds() * 1000),
            )
        if ai_audit_id:
            from business.ai_generation_audit import finish_ai_generation_audit

            finish_ai_generation_audit(
                ai_audit_id,
                result="failed",
                error_code=str(code),
                error=detail,
                input_prompt=input_prompt,
                elapsed_ms=int((datetime.now(UTC) - started_at).total_seconds() * 1000),
            )
        return DailyContentResult(False, content_id=content_id, error_code=code, user_prompt=user_message(code), detail=detail)
    generated_text = str(getattr(ai_result, "text", ""))
    input_prompt = str(getattr(ai_result, "prompt", "") or "")
    if ai_audit_id:
        from business.ai_generation_audit import finish_ai_generation_audit

        finish_ai_generation_audit(
            ai_audit_id,
            result="success",
            output_text=generated_text,
            input_prompt=input_prompt,
            elapsed_ms=int((datetime.now(UTC) - started_at).total_seconds() * 1000),
        )
    if renderer is None:
        render_result = _default_renderer(
            service_type,
            generated_text,
            output_path=_daily_content_render_output_path(item, service_type),
            template_key=template_key,
        )
    else:
        render_result = renderer(service_type, generated_text)
    if not render_result.success:
        detail = sanitize_sensitive_text(getattr(render_result, "detail", "render failed"))
        code = getattr(render_result, "error_code", None) or ErrorCode.IMAGE_GENERATION_FAILED
        update_generation_failure(content_id, detail)
        if business_request_id:
            finish_business_workflow_record(
                business_request_id,
                status=Status.FAILED,
                error_code=str(code),
                user_prompt=user_message(code),
                error_message=detail or generated_text,
                elapsed_ms=int((datetime.now(UTC) - started_at).total_seconds() * 1000),
            )
        return DailyContentResult(False, content_id=content_id, error_code=code, user_prompt=user_message(code), detail=detail)
    output_image = str(getattr(render_result, "image_path", ""))
    output_image = update_generation_success(content_id, generated_text, output_image, input_prompt=input_prompt)
    if business_request_id:
        finish_business_workflow_record(
            business_request_id,
            status=Status.SUCCESS,
            error_message=generated_text,
            output_files=[output_image],
            elapsed_ms=int((datetime.now(UTC) - started_at).total_seconds() * 1000),
        )
    return DailyContentResult(
        True,
        content_id=content_id,
        output_image=output_image,
        generated_text=generated_text,
        input_prompt=input_prompt,
        output_files=[output_image],
    )


def regenerate_content(content_id: str, ai_generator: AIGenerator | None = None, renderer: Renderer | None = None) -> DailyContentResult:
    return generate_content(content_id, ai_generator=ai_generator, renderer=renderer)


def set_content_effective(
    content_id: str,
    output_image: str | None = None,
    *,
    effective_date: str | None = None,
    expires_at: str | None = None,
    operator: str = "",
    actor: Any | None = None,
) -> None:
    archived_ids: list[str] = []
    operator, audit_actor = _actor_identity(actor, operator)
    publish_values = {}
    publish_values.update(_content_actor_values(actor, prefix="updated"))
    publish_values.update(_content_actor_values(actor, prefix="published"))
    with connect() as conn:
        row = conn.execute(
            select(
                investment_daily_contents.c.service_type,
                investment_daily_contents.c.module_key,
                investment_daily_contents.c.output_image,
                investment_daily_contents.c.effective_date,
                investment_daily_contents.c.expires_at,
            ).where(
                investment_daily_contents.c.content_id == content_id
            )
        ).fetchone()
        if row is None:
            raise KeyError(content_id)
        item = row_to_dict(row)
        service_type = item["service_type"]
        module_key = _normalize_module_key(item.get("module_key"))
        final_image = output_image or item["output_image"]
        normalized_effective_date = _normalize_effective_date(effective_date or item.get("effective_date"))
        original_effective_date = item.get("effective_date") or ""
        if expires_at is not None:
            normalized_expires_at = _normalize_expires_at(expires_at)
        elif effective_date is not None and normalized_effective_date != original_effective_date:
            normalized_expires_at = ""
        else:
            normalized_expires_at = item.get("expires_at") or ""
        final_service_type = ServiceType(service_type)
        if final_image:
            from business.artifact_service import archive_artifact_file

            final_image = archive_artifact_file(
                content_id,
                final_image,
                "output_image",
                final_service_type,
                owner_type="content",
            )
        now = _now()
        archive_conditions = [
            investment_daily_contents.c.effective_date == normalized_effective_date,
            investment_daily_contents.c.status == str(Status.EFFECTIVE),
            investment_daily_contents.c.content_id != content_id,
        ]
        if module_key:
            archive_conditions.append(investment_daily_contents.c.module_key == module_key)
        else:
            archive_conditions.append(investment_daily_contents.c.service_type == service_type)
        archive_rows = conn.execute(
            select(investment_daily_contents.c.content_id).where(*archive_conditions)
        ).fetchall()
        archived_ids = [row_to_dict(archive_row)["content_id"] for archive_row in archive_rows]
        conn.execute(
            update(investment_daily_contents)
            .where(*archive_conditions)
            .values(status=str(Status.ARCHIVED), archived_at=now, updated_at=now)
        )
        conn.execute(
            update(investment_daily_contents)
            .where(investment_daily_contents.c.content_id == content_id)
            .values(
                status=str(Status.EFFECTIVE),
                output_image=final_image,
                effective_date=normalized_effective_date,
                expires_at=normalized_expires_at,
                effective_at=now,
                archived_at=None,
                updated_at=now,
                operator=operator,
                **publish_values,
            )
        )
    if final_image:
        record_output_file(
            content_id,
            final_image,
            "image",
            final_service_type,
            artifact_role="output_image",
            version_tag=_output_image_version(final_service_type),
            owner_type="content",
        )
    for archived_id in archived_ids:
        record_operation_audit(
            "content.archive",
            "daily_content",
            archived_id,
            operator=operator,
            actor=audit_actor,
            detail={
                "service_type": service_type,
                "module_key": module_key,
                "effective_date": normalized_effective_date,
                "replaced_by": content_id,
            },
        )
    record_operation_audit(
        "content.publish",
        "daily_content",
        content_id,
        operator=operator,
        actor=audit_actor,
        detail={
            "service_type": service_type,
            "module_key": module_key,
            "effective_date": normalized_effective_date,
            "expires_at": normalized_expires_at,
            "output_image": final_image,
        },
    )


def update_content_expires_at(
    content_id: str,
    expires_at: str | None,
    *,
    operator: str = "",
    actor: Any | None = None,
) -> str:
    normalized_expires_at = _normalize_expires_at(expires_at)
    now = _now()
    operator, audit_actor = _actor_identity(actor, operator)
    actor_values = _content_actor_values(actor, prefix="updated")
    with connect() as conn:
        row = conn.execute(
            select(
                investment_daily_contents.c.service_type,
                investment_daily_contents.c.expires_at,
            ).where(investment_daily_contents.c.content_id == content_id)
        ).fetchone()
        if row is None:
            raise KeyError(content_id)
        item = row_to_dict(row)
        conn.execute(
            update(investment_daily_contents)
            .where(investment_daily_contents.c.content_id == content_id)
            .values(
                expires_at=normalized_expires_at,
                updated_at=now,
                operator=operator,
                **actor_values,
            )
        )
    record_operation_audit(
        "content.update_expiry",
        "daily_content",
        content_id,
        operator=operator,
        actor=audit_actor,
        detail={
            "service_type": item.get("service_type", ""),
            "previous_expires_at": item.get("expires_at", ""),
            "expires_at": normalized_expires_at,
        },
    )
    return normalized_expires_at


def invalidate_content(
    content_id: str,
    *,
    operator: str = "",
    actor: Any | None = None,
) -> bool:
    now = _now()
    operator, audit_actor = _actor_identity(actor, operator)
    actor_values = _content_actor_values(actor, prefix="updated")
    with connect() as conn:
        row = conn.execute(
            select(
                investment_daily_contents.c.service_type,
                investment_daily_contents.c.status,
            ).where(investment_daily_contents.c.content_id == content_id)
        ).fetchone()
        if row is None:
            raise KeyError(content_id)
        item = row_to_dict(row)
        if item.get("status") == str(Status.INVALIDATED):
            invalidated = False
        else:
            result = conn.execute(
                update(investment_daily_contents)
                .where(investment_daily_contents.c.content_id == content_id)
                .values(
                    status=str(Status.INVALIDATED),
                    archived_at=now,
                    updated_at=now,
                    operator=operator,
                    **actor_values,
                )
            )
            invalidated = bool(result.rowcount)
    record_operation_audit(
        "content.invalidate",
        "daily_content",
        content_id,
        operator=operator,
        actor=audit_actor,
        detail={
            "service_type": item.get("service_type", ""),
            "previous_status": item.get("status", ""),
            "invalidated": invalidated,
        },
    )
    return invalidated


def get_latest_effective_content(service_type: ServiceType, module_key: str = "") -> DailyContentResult:
    mark_expired_daily_contents_invalidated()
    today = _today()
    now = _now()
    service_type = _ensure_content_service_type(service_type)
    normalized_module_key = _normalize_module_key(module_key)
    conditions = [
        investment_daily_contents.c.service_type == str(service_type),
        investment_daily_contents.c.status == str(Status.EFFECTIVE),
        investment_daily_contents.c.effective_date <= today,
        or_(
            investment_daily_contents.c.expires_at.is_(None),
            investment_daily_contents.c.expires_at == "",
            investment_daily_contents.c.expires_at > now,
        ),
    ]
    if normalized_module_key:
        if _allows_legacy_content_fallback(service_type, normalized_module_key):
            conditions.append(
                or_(
                    investment_daily_contents.c.module_key == normalized_module_key,
                    investment_daily_contents.c.module_key.is_(None),
                    investment_daily_contents.c.module_key == "",
                )
            )
        else:
            conditions.append(investment_daily_contents.c.module_key == normalized_module_key)
    with connect() as conn:
        row = conn.execute(
            select(investment_daily_contents)
            .where(*conditions)
            .order_by(
                investment_daily_contents.c.effective_date.desc(),
                investment_daily_contents.c.effective_at.desc(),
                investment_daily_contents.c.created_at.desc(),
            )
            .limit(1)
        ).fetchone()
    item = row_to_dict(row)
    if row is None or not item["output_image"]:
        return DailyContentResult(
            False,
            error_code=ErrorCode.NO_CONTENT,
            user_prompt=user_message(ErrorCode.NO_CONTENT),
            detail=f"no effective content for {normalized_module_key or service_type}",
        )
    if not Path(item["output_image"]).is_file():
        return DailyContentResult(
            False,
            error_code=ErrorCode.NO_CONTENT,
            user_prompt=user_message(ErrorCode.NO_CONTENT),
            detail=f"effective content image missing: {item['output_image']}",
        )
    return DailyContentResult(
        True,
        content_id=item["content_id"],
        output_image=item["output_image"],
        generated_text=item["generated_text"] or "",
        output_files=[item["output_image"]],
    )


def mark_expired_daily_contents_invalidated(now: str | None = None) -> int:
    current = now or _now()
    with connect() as conn:
        return int(
            conn.execute(
                update(investment_daily_contents)
                .where(
                    and_(
                        investment_daily_contents.c.status.in_(
                            [str(Status.GENERATED), str(Status.EFFECTIVE)]
                        ),
                        investment_daily_contents.c.expires_at.is_not(None),
                        investment_daily_contents.c.expires_at != "",
                        investment_daily_contents.c.expires_at <= current,
                    )
                )
                .values(status=str(Status.INVALIDATED), updated_at=current)
            ).rowcount
            or 0
        )
