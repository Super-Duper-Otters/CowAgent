# encoding:utf-8
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config_service import get_config, sanitize_sensitive_text
from .constants import ErrorCode, ServiceType, Status, user_message
from .storage import get_storage_dirs


DEFAULT_RENDERER_PATH = "skills/signal-card-renderer/scripts/render_card.py"
DEFAULT_TEMPLATE_TA_PATH = "skills/signal-card-renderer/assets/template_ta.html"
DEFAULT_TEMPLATE_BOND_PATH = "skills/signal-card-renderer/assets/template_bond.html"
DEFAULT_TEMPLATE_CB_PATH = "skills/signal-card-renderer/assets/template_cb.html"


@dataclass
class RenderRequest:
    service_type: ServiceType
    standard_text: str
    output_path: str | None = None
    output_dir: str = ""
    template_path: str = ""


@dataclass
class RenderResult:
    success: bool
    service_type: ServiceType | None = None
    standard_text: str = ""
    output_dir: str = ""
    output_path: str = ""
    image_path: str = ""
    status: Status = Status.FAILED
    error_code: ErrorCode | None = None
    user_prompt: str = ""
    detail: str = ""
    failure_reason: str = ""
    output_files: list[str] = field(default_factory=list)


Renderer = Callable[[RenderRequest, str], None]


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else Path.cwd() / path


def _configured_output_dir() -> Path:
    return Path(str(get_config("render.output_dir") or get_config("storage.tmp_dir") or (get_storage_dirs()["tmp"] / "render")))


def _default_output_path(service_type: ServiceType, output_dir: Path) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    return str(output_dir / f"{service_type}_card.png")


def _default_renderer(request: RenderRequest, target: str) -> None:
    script = _resolve_path(str(get_config("render.renderer_path") or DEFAULT_RENDERER_PATH))
    if not script.exists():
        raise FileNotFoundError(f"renderer script does not exist: {script}")
    subprocess.run(
        [sys.executable, str(script), "--text", request.standard_text, "--output", target],
        check=True,
        capture_output=True,
        text=True,
    )


def template_for_service(service_type: ServiceType) -> str:
    if service_type == ServiceType.TECHNICAL_ANALYSIS:
        return str(get_config("render.template_ta_path") or DEFAULT_TEMPLATE_TA_PATH)
    if service_type == ServiceType.RATE:
        return str(get_config("render.template_rate_path") or DEFAULT_TEMPLATE_BOND_PATH)
    if service_type == ServiceType.CONVERTIBLE_BOND:
        return str(get_config("render.template_cb_path") or DEFAULT_TEMPLATE_CB_PATH)
    raise ValueError(f"unsupported service type: {service_type}")


def _failure_result(request: RenderRequest, target: str, detail: str) -> RenderResult:
    safe_detail = sanitize_sensitive_text(detail)
    return RenderResult(
        False,
        service_type=request.service_type,
        standard_text=request.standard_text,
        output_dir=request.output_dir,
        output_path=target,
        error_code=ErrorCode.IMAGE_GENERATION_FAILED,
        user_prompt=user_message(ErrorCode.IMAGE_GENERATION_FAILED),
        detail=safe_detail,
        failure_reason=safe_detail,
    )


def render_card(request: RenderRequest, *, renderer: Renderer | None = None) -> RenderResult:
    output_dir = Path(request.output_dir) if request.output_dir else _configured_output_dir()
    target_path = Path(request.output_path) if request.output_path else Path(_default_output_path(request.service_type, output_dir))
    if not target_path.is_absolute() and request.output_dir:
        target_path = output_dir / target_path
    request.output_dir = str(output_dir)
    request.output_path = str(target_path)
    request.template_path = template_for_service(request.service_type)
    target = request.output_path
    try:
        template_path = _resolve_path(request.template_path)
        if not template_path.exists():
            return _failure_result(request, target, f"render template does not exist: {template_path}")
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        (renderer or _default_renderer)(request, target)
        path = Path(target)
        if not path.exists():
            return _failure_result(request, target, f"render output missing: {target}")
        if path.stat().st_size <= 0:
            return _failure_result(request, target, f"render output empty: {target}")
        image_path = str(path)
        return RenderResult(
            True,
            service_type=request.service_type,
            standard_text=request.standard_text,
            output_dir=request.output_dir,
            output_path=image_path,
            image_path=image_path,
            status=Status.SUCCESS,
            output_files=[image_path],
        )
    except Exception as exc:
        return _failure_result(request, target, str(exc))


def render_rate_card(text: str, output_path: str | None = None) -> RenderResult:
    return render_card(RenderRequest(ServiceType.RATE, text, output_path))


def render_convertible_bond_card(text: str, output_path: str | None = None) -> RenderResult:
    return render_card(RenderRequest(ServiceType.CONVERTIBLE_BOND, text, output_path))


def render_technical_analysis_card(text: str, output_path: str | None = None) -> RenderResult:
    return render_card(RenderRequest(ServiceType.TECHNICAL_ANALYSIS, text, output_path))
