# encoding:utf-8
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import insert, select, update

from .audit_service import record_operation_audit
from .config_service import sanitize_sensitive_text
from .constants import ErrorCode, ServiceType, Status, user_message
from .db import connect, row_to_dict
from .records import record_output_file
from .render_service import DEFAULT_RENDERER_PATH, template_for_service
from .schema import investment_daily_contents
from .storage import get_storage_dirs
from .versioning import file_fingerprint


@dataclass
class DailyContentResult:
    success: bool
    content_id: str = ""
    output_image: str = ""
    generated_text: str = ""
    error_code: ErrorCode | None = None
    user_prompt: str = ""
    detail: str = ""
    output_files: list[str] = field(default_factory=list)


CONTENT_SERVICE_TYPES = (ServiceType.RATE, ServiceType.CONVERTIBLE_BOND)
CONTENT_STATUSES = (
    Status.DRAFT,
    Status.GENERATING,
    Status.GENERATED,
    Status.GENERATE_FAILED,
    Status.EFFECTIVE,
    Status.ARCHIVED,
)

AIGenerator = Callable[..., Any]
Renderer = Callable[[ServiceType, str], Any]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _today() -> str:
    return date.today().isoformat()


def _normalize_effective_date(value: str | None = None) -> str:
    text = str(value or "").strip()
    if not text:
        return _today()
    return date.fromisoformat(text).isoformat()


def _output_image_version(service_type: ServiceType) -> str:
    from .config_service import get_config

    renderer_path = Path(str(get_config("render.renderer_path") or DEFAULT_RENDERER_PATH))
    if not renderer_path.is_absolute():
        renderer_path = Path.cwd() / renderer_path
    renderer_version = file_fingerprint(renderer_path)
    template_version = file_fingerprint(template_for_service(service_type))
    return f"{renderer_version}|{template_version}"


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
    if service_type not in CONTENT_SERVICE_TYPES:
        raise ValueError(f"unsupported daily content service type: {service_type}")
    return service_type


def save_source_file(service_type: ServiceType, filename: str, content: bytes) -> str:
    service_type = _ensure_content_service_type(service_type)
    safe_name = (filename or "").strip()
    if not safe_name or safe_name != Path(safe_name).name or "/" in safe_name or "\\" in safe_name:
        raise ValueError("invalid source filename")
    target_dir = get_storage_dirs()["uploads"] / str(service_type)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid.uuid4().hex}_{safe_name}"
    target.write_bytes(content)
    return str(target)


def create_content_draft(
    service_type: ServiceType,
    *,
    source_files: list[str] | None = None,
    source_text: str = "",
    operator: str = "",
    effective_date: str | None = None,
    direct_output_mode: bool = False,
) -> str:
    service_type = _ensure_content_service_type(service_type)
    normalized_effective_date = _normalize_effective_date(effective_date)
    direct_output_mode = bool(direct_output_mode and service_type == ServiceType.RATE)
    content_id = str(uuid.uuid4())
    now = _now()
    with connect() as conn:
        version_row = conn.execute(
            select(investment_daily_contents.c.content_version)
            .where(
                investment_daily_contents.c.service_type == str(service_type),
                investment_daily_contents.c.effective_date == normalized_effective_date,
            )
            .order_by(investment_daily_contents.c.content_version.desc())
            .limit(1)
        ).fetchone()
        content_version = int(row_to_dict(version_row).get("content_version") or 0) + 1
        conn.execute(
            insert(investment_daily_contents).values(
                content_id=content_id,
                service_type=str(service_type),
                source_files=json.dumps(source_files or [], ensure_ascii=False),
                source_text=source_text,
                status=str(Status.DRAFT),
                operator=operator,
                effective_date=normalized_effective_date,
                content_version=content_version,
                direct_output_mode=1 if direct_output_mode else 0,
                created_at=now,
                updated_at=now,
            )
        )
    record_operation_audit(
        "create",
        "daily_content",
        content_id,
        operator=operator,
        detail={
            "service_type": str(service_type),
            "effective_date": normalized_effective_date,
            "content_version": content_version,
            "direct_output_mode": bool(direct_output_mode),
        },
    )
    return content_id


def create_rate_content_draft(
    *,
    source_files: list[str] | None = None,
    source_text: str = "",
    operator: str = "",
    effective_date: str | None = None,
    direct_output_mode: bool = False,
) -> str:
    return create_content_draft(
        ServiceType.RATE,
        source_files=source_files,
        source_text=source_text,
        operator=operator,
        effective_date=effective_date,
        direct_output_mode=direct_output_mode,
    )


def create_convertible_bond_content_draft(
    *,
    source_files: list[str] | None = None,
    source_text: str = "",
    operator: str = "",
    effective_date: str | None = None,
) -> str:
    return create_content_draft(
        ServiceType.CONVERTIBLE_BOND,
        source_files=source_files,
        source_text=source_text,
        operator=operator,
        effective_date=effective_date,
        direct_output_mode=False,
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


def _mark_generation_started(content_id: str) -> None:
    with connect() as conn:
        conn.execute(
            update(investment_daily_contents)
            .where(investment_daily_contents.c.content_id == content_id)
            .values(status=str(Status.GENERATING), error_message="", updated_at=_now())
        )


def mark_generation_started(content_id: str) -> DailyContentResult:
    with connect() as conn:
        row = conn.execute(
            select(investment_daily_contents.c.service_type).where(investment_daily_contents.c.content_id == content_id)
        ).fetchone()
    if row is None:
        return DailyContentResult(False, content_id=content_id, error_code=ErrorCode.SYSTEM_ERROR, user_prompt=user_message(ErrorCode.SYSTEM_ERROR), detail="content not found")
    service_type = ServiceType(row_to_dict(row)["service_type"])
    _ensure_content_service_type(service_type)
    _mark_generation_started(content_id)
    return DailyContentResult(True, content_id=content_id)


def update_generation_success(content_id: str, generated_text: str, output_image: str) -> None:
    service_type: ServiceType | None = None
    operator = ""
    with connect() as conn:
        conn.execute(
            update(investment_daily_contents)
            .where(investment_daily_contents.c.content_id == content_id)
            .values(
                generated_text=generated_text,
                output_image=output_image,
                status=str(Status.GENERATED),
                error_message="",
                updated_at=_now(),
            )
        )
        row = conn.execute(
            select(investment_daily_contents.c.service_type, investment_daily_contents.c.operator).where(
                investment_daily_contents.c.content_id == content_id
            )
        ).fetchone()
        item = row_to_dict(row)
        if item.get("service_type"):
            service_type = ServiceType(item["service_type"])
        operator = item.get("operator") or ""
    if output_image and service_type is not None:
        record_output_file(
            content_id,
            output_image,
            "image",
            service_type,
            artifact_role="output_image",
            version_tag=_output_image_version(service_type),
        )
    record_operation_audit(
        "generate",
        "daily_content",
        content_id,
        operator=operator,
        detail={"service_type": str(service_type) if service_type else "", "output_image": output_image},
    )


def update_generation_failure(content_id: str, detail: str) -> None:
    safe_detail = sanitize_sensitive_text(detail)
    operator = ""
    with connect() as conn:
        row = conn.execute(
            select(investment_daily_contents.c.operator).where(investment_daily_contents.c.content_id == content_id)
        ).fetchone()
        operator = row_to_dict(row).get("operator") or ""
        conn.execute(
            update(investment_daily_contents)
            .where(investment_daily_contents.c.content_id == content_id)
            .values(status=str(Status.GENERATE_FAILED), error_message=safe_detail, updated_at=_now())
        )
    record_operation_audit(
        "generate",
        "daily_content",
        content_id,
        operator=operator,
        detail={"success": False, "detail": safe_detail},
    )


def _default_ai_generator(service_type: ServiceType, source_text: str, source_files: list[str] | None = None):
    from .ai_generation import generate_standard_text

    return generate_standard_text(service_type, source_text, source_files=source_files)


def _default_renderer(service_type: ServiceType, generated_text: str):
    from .render_service import RenderRequest, render_card

    return render_card(RenderRequest(service_type=service_type, standard_text=generated_text))


def _validate_direct_output_png(output_image: str) -> str:
    path = Path(output_image)
    if not path.is_absolute():
        return "direct output mode requires an absolute uploaded PNG path"
    if path.suffix.lower() != ".png":
        return "direct output mode only supports PNG files"

    uploads_dir = get_storage_dirs()["uploads"].resolve()
    resolved = path.resolve(strict=False)
    if not resolved.is_relative_to(uploads_dir):
        return "direct output mode requires a PNG file from the investment uploads directory"
    if not path.is_file():
        return "direct output mode requires an existing PNG upload"
    return ""


def generate_content(
    content_id: str,
    ai_generator: AIGenerator | None = None,
    renderer: Renderer | None = None,
) -> DailyContentResult:
    with connect() as conn:
        row = conn.execute(
            select(investment_daily_contents).where(investment_daily_contents.c.content_id == content_id)
        ).fetchone()
    if row is None:
        return DailyContentResult(False, content_id=content_id, error_code=ErrorCode.SYSTEM_ERROR, user_prompt=user_message(ErrorCode.SYSTEM_ERROR), detail="content not found")
    item = row_to_dict(row)
    service_type = ServiceType(item["service_type"])
    _ensure_content_service_type(service_type)
    _mark_generation_started(content_id)
    source_files = _load_source_files(item.get("source_files"))
    if service_type == ServiceType.RATE and bool(item.get("direct_output_mode")):
        if not source_files:
            detail = "direct output mode requires an uploaded PNG"
            update_generation_failure(content_id, detail)
            return DailyContentResult(False, content_id=content_id, error_code=ErrorCode.INPUT_ERROR, user_prompt=user_message(ErrorCode.INPUT_ERROR), detail=detail)
        output_image = source_files[0]
        detail = _validate_direct_output_png(output_image)
        if detail:
            update_generation_failure(content_id, detail)
            return DailyContentResult(False, content_id=content_id, error_code=ErrorCode.INPUT_ERROR, user_prompt=user_message(ErrorCode.INPUT_ERROR), detail=detail)
        update_generation_success(content_id, "", output_image)
        return DailyContentResult(True, content_id=content_id, output_image=output_image, output_files=[output_image])
    if ai_generator is None:
        ai_result = _default_ai_generator(service_type, item["source_text"] or "", source_files)
    else:
        ai_result = ai_generator(service_type, item["source_text"] or "")
    if not ai_result.success:
        detail = sanitize_sensitive_text(getattr(ai_result, "detail", "AI generation failed"))
        code = getattr(ai_result, "error_code", None) or ErrorCode.SYSTEM_ERROR
        update_generation_failure(content_id, detail)
        return DailyContentResult(False, content_id=content_id, error_code=code, user_prompt=user_message(code), detail=detail)
    generated_text = str(getattr(ai_result, "text", ""))
    render_result = (renderer or _default_renderer)(service_type, generated_text)
    if not render_result.success:
        detail = sanitize_sensitive_text(getattr(render_result, "detail", "render failed"))
        code = getattr(render_result, "error_code", None) or ErrorCode.IMAGE_GENERATION_FAILED
        update_generation_failure(content_id, detail)
        return DailyContentResult(False, content_id=content_id, error_code=code, user_prompt=user_message(code), detail=detail)
    output_image = str(getattr(render_result, "image_path", ""))
    update_generation_success(content_id, generated_text, output_image)
    return DailyContentResult(
        True,
        content_id=content_id,
        output_image=output_image,
        generated_text=generated_text,
        output_files=[output_image],
    )


def regenerate_content(content_id: str, ai_generator: AIGenerator | None = None, renderer: Renderer | None = None) -> DailyContentResult:
    return generate_content(content_id, ai_generator=ai_generator, renderer=renderer)


def set_content_effective(
    content_id: str,
    output_image: str | None = None,
    *,
    effective_date: str | None = None,
    operator: str = "",
) -> None:
    archived_ids: list[str] = []
    with connect() as conn:
        row = conn.execute(
            select(
                investment_daily_contents.c.service_type,
                investment_daily_contents.c.output_image,
                investment_daily_contents.c.effective_date,
            ).where(
                investment_daily_contents.c.content_id == content_id
            )
        ).fetchone()
        if row is None:
            raise KeyError(content_id)
        item = row_to_dict(row)
        service_type = item["service_type"]
        final_image = output_image or item["output_image"]
        normalized_effective_date = _normalize_effective_date(effective_date or item.get("effective_date"))
        now = _now()
        archive_rows = conn.execute(
            select(investment_daily_contents.c.content_id).where(
                investment_daily_contents.c.service_type == service_type,
                investment_daily_contents.c.effective_date == normalized_effective_date,
                investment_daily_contents.c.status == str(Status.EFFECTIVE),
                investment_daily_contents.c.content_id != content_id,
            )
        ).fetchall()
        archived_ids = [row_to_dict(archive_row)["content_id"] for archive_row in archive_rows]
        conn.execute(
            update(investment_daily_contents)
            .where(
                investment_daily_contents.c.service_type == service_type,
                investment_daily_contents.c.effective_date == normalized_effective_date,
                investment_daily_contents.c.status == str(Status.EFFECTIVE),
                investment_daily_contents.c.content_id != content_id,
            )
            .values(status=str(Status.ARCHIVED), archived_at=now, updated_at=now)
        )
        conn.execute(
            update(investment_daily_contents)
            .where(investment_daily_contents.c.content_id == content_id)
            .values(
                status=str(Status.EFFECTIVE),
                output_image=final_image,
                effective_date=normalized_effective_date,
                effective_at=now,
                archived_at=None,
                updated_at=now,
                operator=operator,
            )
        )
    if final_image:
        final_service_type = ServiceType(service_type)
        record_output_file(
            content_id,
            final_image,
            "image",
            final_service_type,
            artifact_role="output_image",
            version_tag=_output_image_version(final_service_type),
        )
    for archived_id in archived_ids:
        record_operation_audit(
            "archive",
            "daily_content",
            archived_id,
            operator=operator,
            detail={"service_type": service_type, "effective_date": normalized_effective_date, "replaced_by": content_id},
        )
    record_operation_audit(
        "effective",
        "daily_content",
        content_id,
        operator=operator,
        detail={"service_type": service_type, "effective_date": normalized_effective_date, "output_image": final_image},
    )


def get_latest_effective_content(service_type: ServiceType) -> DailyContentResult:
    today = _today()
    with connect() as conn:
        row = conn.execute(
            select(investment_daily_contents)
            .where(
                investment_daily_contents.c.service_type == str(service_type),
                investment_daily_contents.c.status == str(Status.EFFECTIVE),
                investment_daily_contents.c.effective_date <= today,
            )
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
            detail=f"no effective content for {service_type}",
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
