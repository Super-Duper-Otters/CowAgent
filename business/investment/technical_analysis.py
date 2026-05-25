# encoding:utf-8
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .ai_generation import generate_technical_analysis_text
from .config_service import get_config, sanitize_sensitive_text
from .constants import ErrorCode, user_message
from .render_service import render_technical_analysis_card
from .storage import get_storage_dirs
from .stock_resolver import resolve_stock


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


def run_technical_analysis(openid: str, raw_input: str, target_text: str | None = None) -> TechnicalAnalysisResult:
    request = TechnicalAnalysisRequest(openid=openid, raw_input=raw_input, target_text=target_text or parse_target(raw_input))
    target = request.target_text
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
    output_dir = Path(str(get_config("technical_analysis.output_dir") or get_storage_dirs()["technical_analysis"])) / symbol.replace(".", "_")
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        report_path, chart_path = _run_skill(_skill_symbol(symbol), output_dir)
        report_text = report_path.read_text(encoding="utf-8")
        ai_result = generate_technical_analysis_text(report_text)
        if not ai_result.success:
            return TechnicalAnalysisResult(
                False,
                error_code=ErrorCode.TECHNICAL_ANALYSIS_FAILED,
                user_prompt=user_message(ErrorCode.TECHNICAL_ANALYSIS_FAILED),
                detail=sanitize_sensitive_text(ai_result.detail),
            )
        card_path = output_dir / f"{symbol.replace('.', '_')}_signal_card.png"
        render_result = render_technical_analysis_card(ai_result.text, str(card_path))
        if not render_result.success:
            return TechnicalAnalysisResult(
                False,
                error_code=ErrorCode.IMAGE_GENERATION_FAILED,
                user_prompt=user_message(ErrorCode.IMAGE_GENERATION_FAILED),
                detail=sanitize_sensitive_text(render_result.detail),
            )
        return TechnicalAnalysisResult(
            True,
            render_result.image_path,
            str(chart_path),
            str(report_path),
            output_files=[render_result.image_path, str(chart_path), str(report_path)],
        )
    except Exception as exc:
        return TechnicalAnalysisResult(
            False,
            error_code=ErrorCode.TECHNICAL_ANALYSIS_FAILED,
            user_prompt=user_message(ErrorCode.TECHNICAL_ANALYSIS_FAILED),
            detail=sanitize_sensitive_text(str(exc)),
        )
