# encoding:utf-8
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
import re
import os

from sqlalchemy import and_, desc, select

from . import cache_service
from .ai_generation import generate_technical_analysis_text
from .cache_policy import technical_analysis_cache_expired_after_close
from .cache_service import (
    build_cache_key,
    find_cache_entry,
    find_cache_entry_by_key,
    find_latest_cache_entry,
    increment_cache_hit,
    version_fingerprint,
)
from .config_service import get_config, sanitize_sensitive_text
from .constants import ErrorCode, ServiceType, user_message
from .db import connect
from .market_date_resolver import MarketDateResolution, MarketDateResolver, normalize_market_date
from .render_service import DEFAULT_RENDERER_PATH, render_technical_analysis_card, template_for_service
from .schema import investment_cache_entries, investment_request_records
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


@dataclass
class TechnicalAnalysisCacheContext:
    normalized_target: str = ""
    market_date: str = ""
    program_version: str = ""
    ta_version: str = ""
    renderer_version: str = ""
    template_version: str = ""
    version_fingerprint: str = ""
    cache_lookup_version_fingerprint: str = ""
    cache_key: str = ""
    resolved_market_date: MarketDateResolution | None = None


@dataclass(frozen=True)
class TechnicalAnalysisTarget:
    normalized_target: str = ""
    skill_symbol: str = ""
    is_a_share: bool = False
    stock_name: str = ""


_A_SHARE_SUFFIX_RE = re.compile(r"^(\d{6})\.(SH|SZ)$", re.IGNORECASE)
_A_SHARE_BARE_RE = re.compile(r"^\d{6}$")
_US_SUFFIX_RE = re.compile(r"^([A-Z0-9_.-]+)\.US$", re.IGNORECASE)
_US_PREFIX_RE = re.compile(r"^US:([A-Z0-9_.-]+)$", re.IGNORECASE)
_HK_SUFFIX_RE = re.compile(r"^(\d{5})\.HK$", re.IGNORECASE)
_HK_PREFIX_RE = re.compile(r"^HK(\d{5})$", re.IGNORECASE)
_GOLD_ALIASES = {"GC", "COMEX_GOLD", "GOLD_COMEX"}
_ASCII_SYMBOL_RE = re.compile(r"^[A-Za-z0-9:._-]+$")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def parse_target(raw_input: str) -> str:
    text = (raw_input or "").strip()
    if not text.endswith("技术分析"):
        return ""
    return text[: -len("技术分析")].strip()


def _standard_a_share_symbol(bare_symbol: str) -> str:
    return f"{bare_symbol}.SH" if bare_symbol.startswith("6") else f"{bare_symbol}.SZ"


def _technical_analysis_target(target: str) -> TechnicalAnalysisTarget:
    value = str(target or "").strip()
    if not value:
        return TechnicalAnalysisTarget()

    suffix_match = _A_SHARE_SUFFIX_RE.fullmatch(value)
    if suffix_match:
        bare_symbol = suffix_match.group(1)
        normalized = f"{bare_symbol}.{suffix_match.group(2).upper()}"
        return TechnicalAnalysisTarget(normalized_target=normalized, skill_symbol=bare_symbol, is_a_share=True)

    if _A_SHARE_BARE_RE.fullmatch(value):
        return TechnicalAnalysisTarget(
            normalized_target=_standard_a_share_symbol(value),
            skill_symbol=value,
            is_a_share=True,
        )

    us_prefix_match = _US_PREFIX_RE.fullmatch(value)
    if us_prefix_match:
        normalized = f"{us_prefix_match.group(1).upper()}.US"
        return TechnicalAnalysisTarget(normalized_target=normalized, skill_symbol=normalized)

    us_suffix_match = _US_SUFFIX_RE.fullmatch(value)
    if us_suffix_match:
        normalized = f"{us_suffix_match.group(1).upper()}.US"
        return TechnicalAnalysisTarget(normalized_target=normalized, skill_symbol=normalized)

    hk_prefix_match = _HK_PREFIX_RE.fullmatch(value)
    if hk_prefix_match:
        normalized = f"{hk_prefix_match.group(1)}.HK"
        return TechnicalAnalysisTarget(normalized_target=normalized, skill_symbol=f"HK{hk_prefix_match.group(1)}")

    hk_suffix_match = _HK_SUFFIX_RE.fullmatch(value)
    if hk_suffix_match:
        normalized = f"{hk_suffix_match.group(1)}.HK"
        return TechnicalAnalysisTarget(normalized_target=normalized, skill_symbol=f"HK{hk_suffix_match.group(1)}")

    upper_value = value.upper()
    if upper_value in _GOLD_ALIASES:
        return TechnicalAnalysisTarget(normalized_target="GC", skill_symbol="GC")

    normalized = upper_value if _ASCII_SYMBOL_RE.fullmatch(value) else value
    return TechnicalAnalysisTarget(normalized_target=normalized, skill_symbol=normalized)


def _technical_analysis_target_from_input(target: str) -> tuple[TechnicalAnalysisTarget, ErrorCode | None, str]:
    value = str(target or "").strip()
    target_info = _technical_analysis_target(value)
    if not value or not _CJK_RE.search(value):
        return target_info, None, ""

    symbol, error = resolve_stock(value, auto_refresh_on_miss=False)
    if error == ErrorCode.STOCK_AMBIGUOUS:
        return TechnicalAnalysisTarget(), error, f"ambiguous stock name: {value}"
    if error or not symbol:
        return TechnicalAnalysisTarget(), ErrorCode.STOCK_NOT_FOUND, f"cannot resolve stock name: {value}"

    resolved = _technical_analysis_target(symbol)
    return (
        TechnicalAnalysisTarget(
            normalized_target=resolved.normalized_target,
            skill_symbol=resolved.skill_symbol,
            is_a_share=resolved.is_a_share,
            stock_name=value,
        ),
        None,
        "",
    )


def _skill_symbol(symbol: str) -> str:
    return _technical_analysis_target(symbol).skill_symbol or str(symbol or "").strip()


def _run_skill(symbol: str, output_dir: Path) -> tuple[Path, Path]:
    skill_path = Path(str(get_config("technical_analysis.skill_path") or "skills/技术分析/scripts/analyze_universal.py"))
    if not skill_path.is_absolute():
        skill_path = Path.cwd() / skill_path
    chart_days = str(get_config("technical_analysis.default_chart_days", 120) or 120)
    env = os.environ.copy()
    tushare_token = str(get_config("tushare.token", "") or "").strip()
    if tushare_token:
        env["TUSHARE_TOKEN"] = tushare_token
    command = [sys.executable, str(skill_path), "--symbol", symbol, "--days", chart_days, "--output", str(output_dir)]
    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
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


def _extract_market_date_from_text(text: str) -> str:
    match = re.search(r"\d{4}-\d{2}-\d{2}", text or "")
    return normalize_market_date(match.group(0)) if match else ""


def _target_and_requested_market_date(target: str) -> tuple[str, str]:
    market_date = _extract_market_date_from_text(target)
    if not market_date:
        return target, ""
    cleaned = re.sub(r"\d{4}-\d{2}-\d{2}", " ", target)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned, market_date


def _resolve_market_date(target: TechnicalAnalysisTarget, requested_market_date: str = "") -> MarketDateResolution:
    explicit_date = normalize_market_date(requested_market_date)
    if explicit_date:
        return MarketDateResolution(market_date=explicit_date, known=True, source="explicit")
    if target.is_a_share:
        return MarketDateResolver().resolve(target.normalized_target, requested_market_date)
    return MarketDateResolution()


def _target_path_part(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", symbol).strip("._") or "target"


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
        file_name_date = _extract_market_date_from_text(path.name)
        if file_name_date:
            return file_name_date, ""
    return "", "market_date unknown: no date found in standard text, report, or filename"


def _versions() -> tuple[str, str, str, str]:
    return (
        file_fingerprint(__file__),
        file_fingerprint(_configured_skill_path()),
        file_fingerprint(_configured_renderer_path()),
        file_fingerprint(template_for_service(ServiceType.TECHNICAL_ANALYSIS)),
    )


def _cache_version_fingerprint(ta_version: str, renderer_version: str, template_version: str) -> str:
    return version_fingerprint(ta_version, renderer_version, template_version)


def _compatible_cache_entries(
    *,
    symbol: str,
    current_version_fingerprint: str,
    ta_version: str,
    renderer_version: str,
    template_version: str,
    market_date: str = "",
) -> list[cache_service.CacheEntry]:
    conditions = [
        investment_cache_entries.c.service_type == str(ServiceType.TECHNICAL_ANALYSIS),
        investment_cache_entries.c.normalized_target == symbol,
        investment_cache_entries.c.status == "active",
        investment_cache_entries.c.version_fingerprint != current_version_fingerprint,
        investment_request_records.c.ta_version == ta_version,
        investment_request_records.c.renderer_version == renderer_version,
        investment_request_records.c.template_version == template_version,
    ]
    if market_date:
        conditions.append(investment_cache_entries.c.market_date == market_date)
    stmt = (
        select(investment_cache_entries)
        .join(
            investment_request_records,
            investment_cache_entries.c.artifact_owner_id == investment_request_records.c.request_id,
        )
        .where(and_(*conditions))
        .order_by(desc(investment_cache_entries.c.market_date), desc(investment_cache_entries.c.updated_at))
    )
    with connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [cache_service._row_to_entry(row) for row in rows]


def _compatible_cache_entry_has_files(entry: cache_service.CacheEntry) -> bool:
    if cache_service._files_available(entry.output_files):
        return True
    cache_service._invalidate_cache_entry_if_unchanged(entry)
    return False


def _technical_analysis_cache_entry_allowed(entry: cache_service.CacheEntry) -> bool:
    if technical_analysis_cache_expired_after_close(entry.market_date, entry.updated_at):
        cache_service._invalidate_cache_entry_if_unchanged(entry)
        return False
    return True


def _find_compatible_cache_entry_for_market_date(
    *,
    symbol: str,
    market_date: str,
    current_version_fingerprint: str,
    ta_version: str,
    renderer_version: str,
    template_version: str,
):
    for cached in _compatible_cache_entries(
        symbol=symbol,
        current_version_fingerprint=current_version_fingerprint,
        ta_version=ta_version,
        renderer_version=renderer_version,
        template_version=template_version,
        market_date=market_date,
    ):
        if not _technical_analysis_cache_entry_allowed(cached):
            continue
        if _compatible_cache_entry_has_files(cached):
            return cached
    return None


def _find_latest_current_cache_entry(
    *,
    symbol: str,
    version_fingerprint: str,
):
    for _attempt in range(5):
        cached = find_latest_cache_entry(
            service_type=ServiceType.TECHNICAL_ANALYSIS,
            normalized_target=symbol,
            version_fingerprint=version_fingerprint,
        )
        if cached is None:
            return None
        if _technical_analysis_cache_entry_allowed(cached):
            return cached
    return None


def _cache_entry_owner_matches_versions(
    entry: cache_service.CacheEntry,
    *,
    current_version_fingerprint: str,
    ta_version: str,
    renderer_version: str,
    template_version: str,
) -> bool:
    if entry.version_fingerprint == current_version_fingerprint:
        return True
    if not entry.artifact_owner_id:
        return False
    stmt = (
        select(investment_request_records.c.request_id)
        .where(
            investment_request_records.c.request_id == entry.artifact_owner_id,
            investment_request_records.c.ta_version == ta_version,
            investment_request_records.c.renderer_version == renderer_version,
            investment_request_records.c.template_version == template_version,
        )
        .limit(1)
    )
    with connect() as conn:
        return conn.execute(stmt).fetchone() is not None


def _find_cache_context_entry(
    cache_context: TechnicalAnalysisCacheContext,
    *,
    symbol: str,
    expected_market_date: str,
    expected_version_fingerprint: str,
    current_version_fingerprint: str,
    ta_version: str,
    renderer_version: str,
    template_version: str,
) -> cache_service.CacheEntry | None:
    cached = find_cache_entry_by_key(cache_context.cache_key)
    if cached is None:
        return None
    if cached.service_type != ServiceType.TECHNICAL_ANALYSIS:
        return None
    if cached.normalized_target != symbol:
        return None
    if expected_market_date and cached.market_date != expected_market_date:
        return None
    if cached.version_fingerprint != expected_version_fingerprint:
        return None
    if not _cache_entry_owner_matches_versions(
        cached,
        current_version_fingerprint=current_version_fingerprint,
        ta_version=ta_version,
        renderer_version=renderer_version,
        template_version=template_version,
    ):
        return None
    if not _technical_analysis_cache_entry_allowed(cached):
        return None
    return cached


def prepare_technical_analysis_cache_context(
    raw_input: str,
    target_text: str | None = None,
) -> TechnicalAnalysisCacheContext:
    target, requested_market_date = _target_and_requested_market_date(target_text or parse_target(raw_input))
    target_info, error, _detail = _technical_analysis_target_from_input(target)
    if error:
        return TechnicalAnalysisCacheContext()
    symbol = target_info.normalized_target
    if not symbol:
        return TechnicalAnalysisCacheContext()
    program_version, ta_version, renderer_version, template_version = _versions()
    combined_version = _cache_version_fingerprint(ta_version, renderer_version, template_version)
    resolved_market_date = _resolve_market_date(target_info, requested_market_date)
    if not resolved_market_date.known or not resolved_market_date.market_date:
        cached = _find_latest_current_cache_entry(
            symbol=symbol,
            version_fingerprint=combined_version,
        )
        return TechnicalAnalysisCacheContext(
            normalized_target=symbol,
            market_date=cached.market_date if cached is not None else "",
            program_version=program_version,
            ta_version=ta_version,
            renderer_version=renderer_version,
            template_version=template_version,
            version_fingerprint=combined_version,
            cache_lookup_version_fingerprint=cached.version_fingerprint if cached is not None else combined_version,
            cache_key=cached.cache_key if cached is not None else "",
            resolved_market_date=resolved_market_date,
        )
    cached = find_cache_entry(
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        normalized_target=symbol,
        version_fingerprint=combined_version,
        market_date=resolved_market_date.market_date,
    )
    if cached is not None and not _technical_analysis_cache_entry_allowed(cached):
        cached = None
    if cached is None:
        cached = _find_compatible_cache_entry_for_market_date(
            symbol=symbol,
            market_date=resolved_market_date.market_date,
            current_version_fingerprint=combined_version,
            ta_version=ta_version,
            renderer_version=renderer_version,
            template_version=template_version,
        )
    return TechnicalAnalysisCacheContext(
        normalized_target=symbol,
        market_date=cached.market_date if cached is not None else resolved_market_date.market_date,
        program_version=program_version,
        ta_version=ta_version,
        renderer_version=renderer_version,
        template_version=template_version,
        version_fingerprint=combined_version,
        cache_lookup_version_fingerprint=cached.version_fingerprint if cached is not None else combined_version,
        cache_key=(
            cached.cache_key
            if cached is not None
            else build_cache_key(
                ServiceType.TECHNICAL_ANALYSIS,
                symbol,
                resolved_market_date.market_date,
                combined_version,
            )
        ),
        resolved_market_date=resolved_market_date,
    )


def run_technical_analysis(
    openid: str,
    raw_input: str,
    target_text: str | None = None,
    *,
    cache_context: TechnicalAnalysisCacheContext | None = None,
) -> TechnicalAnalysisResult:
    request = TechnicalAnalysisRequest(openid=openid, raw_input=raw_input, target_text=target_text or parse_target(raw_input))
    target, requested_market_date = _target_and_requested_market_date(request.target_text)
    target_info, error, error_detail = _technical_analysis_target_from_input(target)
    if error:
        return TechnicalAnalysisResult(
            False,
            error_code=error,
            user_prompt=user_message(error),
            detail=error_detail,
        )
    symbol = target_info.normalized_target
    if not symbol:
        return TechnicalAnalysisResult(
            False,
            error_code=ErrorCode.STOCK_NOT_FOUND,
            user_prompt=user_message(ErrorCode.STOCK_NOT_FOUND),
            detail=f"cannot resolve stock: {target}",
        )
    cache_context_provided = cache_context is not None
    use_cache_context = cache_context_provided and cache_context.normalized_target == symbol
    if use_cache_context:
        program_version = cache_context.program_version
        ta_version = cache_context.ta_version
        renderer_version = cache_context.renderer_version
        template_version = cache_context.template_version
        combined_version = cache_context.version_fingerprint
        cache_lookup_version = cache_context.cache_lookup_version_fingerprint or combined_version
    else:
        program_version, ta_version, renderer_version, template_version = _versions()
        combined_version = _cache_version_fingerprint(ta_version, renderer_version, template_version)
        cache_lookup_version = combined_version
    cached = None
    if use_cache_context and cache_context.resolved_market_date is not None:
        resolved_market_date = cache_context.resolved_market_date
    else:
        resolved_market_date = _resolve_market_date(target_info, requested_market_date)
    if use_cache_context and cache_context.cache_key:
        cached = _find_cache_context_entry(
            cache_context,
            symbol=symbol,
            expected_market_date=resolved_market_date.market_date if resolved_market_date.known else cache_context.market_date,
            expected_version_fingerprint=cache_lookup_version,
            current_version_fingerprint=combined_version,
            ta_version=ta_version,
            renderer_version=renderer_version,
            template_version=template_version,
        )
    if cached is None and resolved_market_date.known and resolved_market_date.market_date:
        if use_cache_context and cache_context.cache_key:
            cached = _find_cache_context_entry(
                cache_context,
                symbol=symbol,
                expected_market_date=resolved_market_date.market_date,
                expected_version_fingerprint=cache_lookup_version,
                current_version_fingerprint=combined_version,
                ta_version=ta_version,
                renderer_version=renderer_version,
                template_version=template_version,
            )
        else:
            cached = find_cache_entry(
                service_type=ServiceType.TECHNICAL_ANALYSIS,
                normalized_target=symbol,
                version_fingerprint=cache_lookup_version,
                market_date=resolved_market_date.market_date,
            )
            if cached is not None and not _technical_analysis_cache_entry_allowed(cached):
                cached = None
        if cached is None and cache_lookup_version == combined_version and not (use_cache_context and cache_context.cache_key):
            cached = _find_compatible_cache_entry_for_market_date(
                symbol=symbol,
                market_date=resolved_market_date.market_date,
                current_version_fingerprint=combined_version,
                ta_version=ta_version,
                renderer_version=renderer_version,
                template_version=template_version,
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
            stock_name=target_info.stock_name,
            market_date=cached.market_date,
            program_version=program_version,
            ta_version=ta_version,
            renderer_version=renderer_version,
            template_version=template_version,
            version_fingerprint=combined_version,
            cache_key=cached.cache_key,
            cache_hit=True,
        )
    output_base = Path(
        str(
            get_config("technical_analysis.output_dir")
            or get_config("storage.tmp_dir")
            or (get_storage_dirs()["tmp"] / "technical-analysis")
        )
    )
    output_dir = output_base / _target_path_part(symbol.replace(".", "_")) / uuid.uuid4().hex
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        generated_report_path, generated_chart_path = _run_skill(target_info.skill_symbol or _skill_symbol(symbol), output_dir)
        report_text = generated_report_path.read_text(encoding="utf-8")
        ai_result = generate_technical_analysis_text(report_text)
        if not ai_result.success:
            return TechnicalAnalysisResult(
                False,
                error_code=ErrorCode.TECHNICAL_ANALYSIS_FAILED,
                user_prompt=user_message(ErrorCode.TECHNICAL_ANALYSIS_FAILED),
                detail=sanitize_sensitive_text(ai_result.detail),
            )
        generated_market_date, market_date_warning = _market_date(ai_result.text, generated_report_path, generated_chart_path)
        if resolved_market_date.source == "explicit" and resolved_market_date.market_date:
            market_date = resolved_market_date.market_date
            market_date_warning = ""
        elif not requested_market_date and resolved_market_date.known and resolved_market_date.market_date:
            market_date = resolved_market_date.market_date
            if generated_market_date and generated_market_date != market_date:
                market_date_warning = f"market_date resolved from market data source: {resolved_market_date.source}"
        elif generated_market_date:
            market_date = generated_market_date
        elif resolved_market_date.known and resolved_market_date.market_date:
            market_date = resolved_market_date.market_date
            market_date_warning = f"market_date resolved from market data source: {resolved_market_date.source}"
        else:
            market_date = ""
        if use_cache_context and cache_context.cache_key and market_date == cache_context.market_date:
            cache_key = cache_context.cache_key
        else:
            cache_key = (
                build_cache_key(ServiceType.TECHNICAL_ANALYSIS, symbol, market_date, combined_version)
                if market_date
                else ""
            )
        version_suffix = re.sub(r"[^A-Za-z0-9]+", "", combined_version)[-12:] or "version"
        card_market_date = market_date or "unknown"
        card_path = output_dir / f"{_target_path_part(symbol.replace('.', '_'))}_signal_card_{card_market_date}_{version_suffix}.png"
        render_result = render_technical_analysis_card(ai_result.text, str(card_path))
        if not render_result.success:
            return TechnicalAnalysisResult(
                False,
                error_code=ErrorCode.IMAGE_GENERATION_FAILED,
                user_prompt=user_message(ErrorCode.IMAGE_GENERATION_FAILED),
                detail=sanitize_sensitive_text(render_result.detail),
            )
        output_files = [render_result.image_path, str(generated_chart_path), str(generated_report_path)]
        return TechnicalAnalysisResult(
            True,
            render_result.image_path,
            str(generated_chart_path),
            str(generated_report_path),
            output_files=output_files,
            normalized_target=symbol,
            stock_code=symbol,
            stock_name=target_info.stock_name,
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
