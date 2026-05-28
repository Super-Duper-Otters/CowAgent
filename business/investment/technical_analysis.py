# encoding:utf-8
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
import re

from .ai_generation import generate_technical_analysis_text
from .cache_service import build_cache_key, find_cache_entry, increment_cache_hit, version_fingerprint, write_cache_entry
from .config_service import get_config, sanitize_sensitive_text
from .constants import ErrorCode, ServiceType, user_message
from .db import connect, row_to_dict
from .render_service import DEFAULT_RENDERER_PATH, render_technical_analysis_card, template_for_service
from .schema import investment_stock_symbols
from .storage import get_storage_dirs
from .stock_resolver import resolve_stock
from .versioning import file_fingerprint


@dataclass
class TechnicalAnalysisRequest:
    openid: str
    raw_input: str
    target_text: str = ""


@dataclass
class TechnicalAnalysisResult:
    success: bool
    signal_card_path: str = ""
    main_chart_path: str = ""
    report_path: str = ""
    error_code: ErrorCode | None = None
    user_prompt: str = ""
    detail: str = ""
    output_files: list[str] = field(default_factory=list)
    normalized_target: str = ""
    stock_code: str = ""
    stock_name: str = ""
    market_date: str = ""
    program_version: str = ""
    ta_version: str = ""
    renderer_version: str = ""
    template_version: str = ""
    version_fingerprint: str = ""
    cache_key: str = ""
    cache_hit: bool = False


def parse_target(raw_input: str) -> str:
    text = (raw_input or "").strip()
    if not text.endswith("技术分析"):
        return ""
    return text[: -len("技术分析")].strip()


def _skill_symbol(symbol: str) -> str:
    return symbol.split(".", 1)[0] if "." in symbol else symbol


def _run_skill(symbol: str, output_dir: Path) -> tuple[Path, Path]:
    skill_path = Path(str(get_config("technical_analysis.skill_path") or "skills/技术分析/scripts/analyze_universal.py"))
    if not skill_path.is_absolute():
        skill_path = Path.cwd() / skill_path
    chart_days = str(get_config("technical_analysis.default_chart_days", 120) or 120)
    subprocess.run(
        [sys.executable, str(skill_path), "--symbol", symbol, "--days", chart_days, "--output", str(output_dir)],
        check=True,
        capture_output=True,
        text=True,
    )
    reports = sorted(output_dir.glob("*技术分析报告*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    charts = sorted(output_dir.glob("*_TA_*.png"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not reports or not charts:
        raise RuntimeError("technical analysis skill did not produce report or main chart")
    return reports[0], charts[0]


def _configured_skill_path() -> Path:
    skill_path = Path(str(get_config("technical_analysis.skill_path") or "skills/技术分析/scripts/analyze_universal.py"))
    return skill_path if skill_path.is_absolute() else Path.cwd() / skill_path


def _configured_renderer_path() -> Path:
    renderer_path = Path(str(get_config("render.renderer_path") or DEFAULT_RENDERER_PATH))
    return renderer_path if renderer_path.is_absolute() else Path.cwd() / renderer_path


def _stock_name(symbol: str, target: str) -> str:
    with connect() as conn:
        row = conn.execute(
            investment_stock_symbols.select().where(investment_stock_symbols.c.code == symbol)
        ).fetchone()
    item = row_to_dict(row)
    return item.get("name") or target


def _extract_market_date_from_text(text: str) -> str:
    match = re.search(r"\d{4}-\d{2}-\d{2}", text or "")
    return match.group(0) if match else ""


def _target_and_requested_market_date(target: str) -> tuple[str, str]:
    market_date = _extract_market_date_from_text(target)
    if not market_date:
        return target, ""
    cleaned = re.sub(r"\d{4}-\d{2}-\d{2}", " ", target)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned, market_date


def _market_date(standard_text: str = "", *paths: Path) -> tuple[str, str]:
    text_date = _extract_market_date_from_text(standard_text)
    if text_date:
        return text_date, ""
    for path in paths:
        if path.suffix.lower() in {".md", ".txt"} and path.is_file():
            file_text_date = _extract_market_date_from_text(path.read_text(encoding="utf-8", errors="ignore"))
            if file_text_date:
                return file_text_date, ""
    for path in paths:
        match = re.search(r"\d{4}-\d{2}-\d{2}", path.name)
        if match:
            return match.group(0), ""
    fallback = date.today().isoformat()
    return fallback, f"market_date fallback: no date found in standard text, report, or filename; used {fallback}"


def _versions() -> tuple[str, str, str, str]:
    return (
        file_fingerprint(__file__),
        file_fingerprint(_configured_skill_path()),
        file_fingerprint(_configured_renderer_path()),
        file_fingerprint(template_for_service(ServiceType.TECHNICAL_ANALYSIS)),
    )


def run_technical_analysis(openid: str, raw_input: str, target_text: str | None = None) -> TechnicalAnalysisResult:
    request = TechnicalAnalysisRequest(openid=openid, raw_input=raw_input, target_text=target_text or parse_target(raw_input))
    target, requested_market_date = _target_and_requested_market_date(request.target_text)
    symbol, error = resolve_stock(target)
    if error:
        return TechnicalAnalysisResult(False, error_code=error, user_prompt=user_message(error), detail=f"cannot resolve stock: {target}")
    if symbol is None:
        return TechnicalAnalysisResult(
            False,
            error_code=ErrorCode.STOCK_NOT_FOUND,
            user_prompt=user_message(ErrorCode.STOCK_NOT_FOUND),
            detail=f"cannot resolve stock: {target}",
        )
    program_version, ta_version, renderer_version, template_version = _versions()
    combined_version = version_fingerprint(program_version, ta_version, renderer_version, template_version)
    cached = None
    if requested_market_date:
        cached = find_cache_entry(
            service_type=ServiceType.TECHNICAL_ANALYSIS,
            normalized_target=symbol,
            version_fingerprint=combined_version,
            market_date=requested_market_date,
        )
    if cached is not None:
        increment_cache_hit(cached.cache_key)
        output_files = cached.output_files
        signal_card_path = output_files[0] if output_files else ""
        main_chart_path = output_files[1] if len(output_files) > 1 else ""
        cached_report_path = output_files[2] if len(output_files) > 2 else ""
        return TechnicalAnalysisResult(
            True,
            signal_card_path,
            main_chart_path,
            cached_report_path,
            output_files=output_files,
            normalized_target=symbol,
            stock_code=symbol,
            stock_name=_stock_name(symbol, target),
            market_date=cached.market_date,
            program_version=program_version,
            ta_version=ta_version,
            renderer_version=renderer_version,
            template_version=template_version,
            version_fingerprint=combined_version,
            cache_key=cached.cache_key,
            cache_hit=True,
        )
    output_dir = Path(str(get_config("technical_analysis.output_dir") or get_storage_dirs()["technical_analysis"])) / symbol.replace(".", "_")
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        generated_report_path, generated_chart_path = _run_skill(_skill_symbol(symbol), output_dir)
        report_text = generated_report_path.read_text(encoding="utf-8")
        ai_result = generate_technical_analysis_text(report_text)
        if not ai_result.success:
            return TechnicalAnalysisResult(
                False,
                error_code=ErrorCode.TECHNICAL_ANALYSIS_FAILED,
                user_prompt=user_message(ErrorCode.TECHNICAL_ANALYSIS_FAILED),
                detail=sanitize_sensitive_text(ai_result.detail),
            )
        market_date, market_date_warning = _market_date(ai_result.text, generated_report_path, generated_chart_path)
        cache_key = build_cache_key(ServiceType.TECHNICAL_ANALYSIS, symbol, market_date, combined_version)
        version_suffix = re.sub(r"[^A-Za-z0-9]+", "", combined_version)[-12:] or "version"
        card_path = output_dir / f"{symbol.replace('.', '_')}_signal_card_{market_date}_{version_suffix}.png"
        render_result = render_technical_analysis_card(ai_result.text, str(card_path))
        if not render_result.success:
            return TechnicalAnalysisResult(
                False,
                error_code=ErrorCode.IMAGE_GENERATION_FAILED,
                user_prompt=user_message(ErrorCode.IMAGE_GENERATION_FAILED),
                detail=sanitize_sensitive_text(render_result.detail),
            )
        output_files = [render_result.image_path, str(generated_chart_path), str(generated_report_path)]
        write_cache_entry(
            cache_key=cache_key,
            service_type=ServiceType.TECHNICAL_ANALYSIS,
            normalized_target=symbol,
            market_date=market_date,
            version_fingerprint=combined_version,
            output_files=output_files,
        )
        return TechnicalAnalysisResult(
            True,
            render_result.image_path,
            str(generated_chart_path),
            str(generated_report_path),
            output_files=output_files,
            normalized_target=symbol,
            stock_code=symbol,
            stock_name=_stock_name(symbol, target),
            market_date=market_date,
            program_version=program_version,
            ta_version=ta_version,
            renderer_version=renderer_version,
            template_version=template_version,
            version_fingerprint=combined_version,
            cache_key=cache_key,
            cache_hit=False,
            detail=market_date_warning,
        )
    except Exception as exc:
        return TechnicalAnalysisResult(
            False,
            error_code=ErrorCode.TECHNICAL_ANALYSIS_FAILED,
            user_prompt=user_message(ErrorCode.TECHNICAL_ANALYSIS_FAILED),
            detail=sanitize_sensitive_text(str(exc)),
        )
