# encoding:utf-8
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import insert, select, update

from .config_service import sanitize_sensitive_text
from .constants import ErrorCode, ServiceType, Status, user_message
from .db import connect, row_to_dict
from .records import record_output_file
from .schema import investment_daily_contents
from .storage import get_storage_dirs


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

AIGenerator = Callable[[ServiceType, str], Any]
Renderer = Callable[[ServiceType, str], Any]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


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
) -> str:
    service_type = _ensure_content_service_type(service_type)
    content_id = str(uuid.uuid4())
    now = _now()
    with connect() as conn:
        conn.execute(
            insert(investment_daily_contents).values(
                content_id=content_id,
                service_type=str(service_type),
                source_files=json.dumps(source_files or [], ensure_ascii=False),
                source_text=source_text,
                status=str(Status.DRAFT),
                operator=operator,
                created_at=now,
                updated_at=now,
            )
        )
    return content_id


def create_rate_content_draft(
    *,
    source_files: list[str] | None = None,
    source_text: str = "",
    operator: str = "",
) -> str:
    return create_content_draft(ServiceType.RATE, source_files=source_files, source_text=source_text, operator=operator)


def create_convertible_bond_content_draft(
    *,
    source_files: list[str] | None = None,
    source_text: str = "",
    operator: str = "",
) -> str:
    return create_content_draft(ServiceType.CONVERTIBLE_BOND, source_files=source_files, source_text=source_text, operator=operator)


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


def update_generation_success(content_id: str, generated_text: str, output_image: str) -> None:
    service_type: ServiceType | None = None
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
        if output_image:
            row = conn.execute(
                select(investment_daily_contents.c.service_type).where(investment_daily_contents.c.content_id == content_id)
            ).fetchone()
            item = row_to_dict(row)
            if item.get("service_type"):
                service_type = ServiceType(item["service_type"])
    if output_image and service_type is not None:
        record_output_file(content_id, output_image, "image", service_type)


def update_generation_failure(content_id: str, detail: str) -> None:
    safe_detail = sanitize_sensitive_text(detail)
    with connect() as conn:
        conn.execute(
            update(investment_daily_contents)
            .where(investment_daily_contents.c.content_id == content_id)
            .values(status=str(Status.GENERATE_FAILED), error_message=safe_detail, updated_at=_now())
        )


def _default_ai_generator(service_type: ServiceType, source_text: str):
    from .ai_generation import generate_standard_text

    return generate_standard_text(service_type, source_text)


def _default_renderer(service_type: ServiceType, generated_text: str):
    from .render_service import RenderRequest, render_card

    return render_card(RenderRequest(service_type=service_type, standard_text=generated_text))


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
    ai_result = (ai_generator or _default_ai_generator)(service_type, item["source_text"] or "")
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


def set_content_effective(content_id: str, output_image: str | None = None, *, operator: str = "") -> None:
    with connect() as conn:
        row = conn.execute(
            select(investment_daily_contents.c.service_type, investment_daily_contents.c.output_image).where(
                investment_daily_contents.c.content_id == content_id
            )
        ).fetchone()
        if row is None:
            raise KeyError(content_id)
        item = row_to_dict(row)
        service_type = item["service_type"]
        final_image = output_image or item["output_image"]
        now = _now()
        conn.execute(
            update(investment_daily_contents)
            .where(
                investment_daily_contents.c.service_type == service_type,
                investment_daily_contents.c.status == str(Status.EFFECTIVE),
            )
            .values(status=str(Status.ARCHIVED), effective_at=None, updated_at=now)
        )
        conn.execute(
            update(investment_daily_contents)
            .where(investment_daily_contents.c.content_id == content_id)
            .values(status=str(Status.EFFECTIVE), output_image=final_image, effective_at=now, updated_at=now, operator=operator)
        )
    record_output_file(content_id, final_image, "image", ServiceType(service_type))


def get_latest_effective_content(service_type: ServiceType) -> DailyContentResult:
    with connect() as conn:
        row = conn.execute(
            select(investment_daily_contents)
            .where(
                investment_daily_contents.c.service_type == str(service_type),
                investment_daily_contents.c.status == str(Status.EFFECTIVE),
            )
            .order_by(investment_daily_contents.c.effective_at.desc(), investment_daily_contents.c.created_at.desc())
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
    return DailyContentResult(
        True,
        content_id=item["content_id"],
        output_image=item["output_image"],
        generated_text=item["generated_text"] or "",
        output_files=[item["output_image"]],
    )
