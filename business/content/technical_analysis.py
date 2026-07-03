# encoding:utf-8
import subprocess
import sys
import uuid
import inspect
from dataclasses import dataclass, field
from pathlib import Path
import re
import os

from sqlalchemy import and_, desc, select

from business.cache import cache_service as cache_service
from business.audit.ai_generation import generate_technical_analysis_text
from business.cache.cache_policy import technical_analysis_cache_expired_after_close, technical_analysis_cache_update_config
from business.cache.cache_service import (
    build_cache_key,
    find_cache_entry,
    find_cache_entry_by_key,
    find_latest_cache_entry,
    increment_cache_hit,
    version_fingerprint,
)
from business.config.config_service import get_config, sanitize_sensitive_text
from business.config.constants import ErrorCode, ServiceType, user_message
from business.config.reply_config import format_reply_text
from business.config.wechat_rich_text import component_link
from business.products.product_service import find_active_product, increment_product_hit, invalidate_product_if_unchanged
from business.schema.db import connect
from business.content.technical_analysis_card_config import (
    apply_technical_analysis_card_footer,
)
from business.content.market_date_resolver import MarketDateResolution, MarketDateResolver, normalize_market_date
from business.content.render_service import DEFAULT_RENDERER_PATH, render_technical_analysis_card, template_for_service
from business.schema.tables import investment_products, investment_request_records
from business.schema.storage import get_storage_dirs
from business.content.stock_resolver import (
    get_stock_symbol_by_code,
    get_tushare_token,
    list_bare_code_symbol_matches,
    list_exact_stock_name_matches,
    list_index_symbol_matches_for_bare_code,
    resolve_stock,
)
from business.versioning import file_fingerprint


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
    source_type: str = ""
    source_id: str = ""


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
    asset_type: str = ""
    market: str = ""
    ts_code: str = ""


_A_SHARE_SUFFIX_RE = re.compile(r"^(\d{6})\.(SH|SZ)$", re.IGNORECASE)
_A_SHARE_BARE_RE = re.compile(r"^\d{6}$")
_US_SUFFIX_RE = re.compile(r"^([A-Z0-9_.-]+)\.US$", re.IGNORECASE)
_US_PREFIX_RE = re.compile(r"^US:([A-Z0-9_.-]+)$", re.IGNORECASE)
_HK_SUFFIX_RE = re.compile(r"^(\d{5})\.HK$", re.IGNORECASE)
_HK_PREFIX_RE = re.compile(r"^HK(\d{5})$", re.IGNORECASE)
_GOLD_ALIASES = {"GC", "COMEX_GOLD", "GOLD_COMEX"}
_INDEX_PREFIX_RE = re.compile(r"^(sh|sz|bj)(\d{6})$", re.IGNORECASE)
_MALFORMED_INDEX_PREFIX_RE = re.compile(r"^(sh|sz|bj)\d+$", re.IGNORECASE)
_CSI_SUFFIX_RE = re.compile(r"^([A-Z]?\d{5,6})\.CSI$", re.IGNORECASE)
_ASCII_SYMBOL_RE = re.compile(r"^[A-Za-z0-9:._-]+$")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def parse_target(raw_input: str) -> str:
    text = (raw_input or "").strip()
    if text.startswith("#"):
        return text[1:].strip()
    if not text.endswith("技术分析"):
        return ""
    return text[: -len("技术分析")].strip()


def _standard_a_share_symbol(bare_symbol: str) -> str:
    return f"{bare_symbol}.SH" if bare_symbol.startswith("6") else f"{bare_symbol}.SZ"


def _normalize_csi_symbol(value: str) -> str:
    match = _CSI_SUFFIX_RE.fullmatch(str(value or "").strip())
    if not match:
        return ""
    bare = match.group(1).upper()
    if re.fullmatch(r"\d{5}", bare):
        bare = f"H{bare}"
    return f"{bare}.CSI"


def _csi_symbol_suggestion(value: str) -> str:
    match = _CSI_SUFFIX_RE.fullmatch(str(value or "").strip())
    if not match:
        return ""
    bare = match.group(1).upper()
    if re.fullmatch(r"\d{5}", bare):
        return f"H{bare}.CSI"
    return ""


def _technical_analysis_target(target: str) -> TechnicalAnalysisTarget:
    value = str(target or "").strip()
    if not value:
        return TechnicalAnalysisTarget()

    index_match = _INDEX_PREFIX_RE.fullmatch(value)
    if index_match:
        normalized = f"{index_match.group(1).lower()}{index_match.group(2)}"
        return TechnicalAnalysisTarget(
            normalized_target=normalized,
            skill_symbol=normalized,
            asset_type="index",
            market=index_match.group(1).upper(),
        )

    csi_symbol = _normalize_csi_symbol(value)
    if csi_symbol:
        return TechnicalAnalysisTarget(
            normalized_target=csi_symbol,
            skill_symbol=csi_symbol,
            asset_type="index",
            market="CSI",
            ts_code=csi_symbol,
        )

    suffix_match = _A_SHARE_SUFFIX_RE.fullmatch(value)
    if suffix_match:
        bare_symbol = suffix_match.group(1)
        normalized = f"{bare_symbol}.{suffix_match.group(2).upper()}"
        return TechnicalAnalysisTarget(
            normalized_target=normalized,
            skill_symbol=bare_symbol,
            is_a_share=True,
            asset_type="a_share",
            market=suffix_match.group(2).upper(),
            ts_code=normalized,
        )

    if _A_SHARE_BARE_RE.fullmatch(value):
        return TechnicalAnalysisTarget(
            normalized_target=_standard_a_share_symbol(value),
            skill_symbol=value,
            is_a_share=True,
            asset_type="a_share",
            market=_standard_a_share_symbol(value).rsplit(".", 1)[1],
            ts_code=_standard_a_share_symbol(value),
        )

    us_prefix_match = _US_PREFIX_RE.fullmatch(value)
    if us_prefix_match:
        normalized = f"{us_prefix_match.group(1).upper()}.US"
        return TechnicalAnalysisTarget(normalized_target=normalized, skill_symbol=normalized, asset_type="us_stock", market="US")

    us_suffix_match = _US_SUFFIX_RE.fullmatch(value)
    if us_suffix_match:
        normalized = f"{us_suffix_match.group(1).upper()}.US"
        return TechnicalAnalysisTarget(normalized_target=normalized, skill_symbol=normalized, asset_type="us_stock", market="US")

    hk_prefix_match = _HK_PREFIX_RE.fullmatch(value)
    if hk_prefix_match:
        normalized = f"{hk_prefix_match.group(1)}.HK"
        return TechnicalAnalysisTarget(normalized_target=normalized, skill_symbol=f"HK{hk_prefix_match.group(1)}", asset_type="hk_stock", market="HK")

    hk_suffix_match = _HK_SUFFIX_RE.fullmatch(value)
    if hk_suffix_match:
        normalized = f"{hk_suffix_match.group(1)}.HK"
        return TechnicalAnalysisTarget(normalized_target=normalized, skill_symbol=f"HK{hk_suffix_match.group(1)}", asset_type="hk_stock", market="HK")

    upper_value = value.upper()
    if upper_value in _GOLD_ALIASES:
        return TechnicalAnalysisTarget(normalized_target="GC", skill_symbol="GC", asset_type="gold")

    normalized = upper_value if _ASCII_SYMBOL_RE.fullmatch(value) else value
    return TechnicalAnalysisTarget(normalized_target=normalized, skill_symbol=normalized)


def _technical_analysis_target_from_input(target: str) -> tuple[TechnicalAnalysisTarget, ErrorCode | None, str]:
    value = str(target or "").strip()
    if _MALFORMED_INDEX_PREFIX_RE.fullmatch(value) and not _INDEX_PREFIX_RE.fullmatch(value):
        return TechnicalAnalysisTarget(), ErrorCode.STOCK_NOT_FOUND, f"cannot resolve symbol: {value}"
    csi_suggestion = _csi_symbol_suggestion(value)
    if csi_suggestion:
        return (
            TechnicalAnalysisTarget(),
            ErrorCode.STOCK_NOT_FOUND,
            _csi_symbol_suggestion_detail(value, csi_suggestion),
        )
    target_info = _technical_analysis_target(value)
    if not value or not _CJK_RE.search(value):
        if _A_SHARE_BARE_RE.fullmatch(value):
            symbol_matches = list_bare_code_symbol_matches(value)
            if len(symbol_matches) > 1:
                return (
                    TechnicalAnalysisTarget(),
                    ErrorCode.STOCK_AMBIGUOUS,
                    _bare_code_ambiguous_detail(value, symbol_matches),
                )
        if target_info.normalized_target:
            stock = get_stock_symbol_by_code(target_info.normalized_target)
            stock_name = str(stock.get("name") or "").strip()
            if stock_name:
                resolved_ts_code = str(stock.get("ts_code") or target_info.ts_code)
                if target_info.asset_type == "index" and target_info.market == "CSI":
                    resolved_ts_code = _normalize_csi_symbol(resolved_ts_code) or resolved_ts_code
                target_info = TechnicalAnalysisTarget(
                    normalized_target=target_info.normalized_target,
                    skill_symbol=target_info.skill_symbol,
                    is_a_share=target_info.is_a_share,
                    stock_name=stock_name,
                    asset_type=str(stock.get("asset_type") or target_info.asset_type),
                    market=str(stock.get("market") or target_info.market),
                    ts_code=resolved_ts_code,
                )
            elif _A_SHARE_BARE_RE.fullmatch(value):
                index_matches = list_index_symbol_matches_for_bare_code(value)
                if index_matches:
                    return (
                        TechnicalAnalysisTarget(),
                        ErrorCode.STOCK_NOT_FOUND,
                        _bare_code_index_suggestion_detail(value, index_matches),
                    )
                if not allow_unresolved_bare_code_analysis():
                    return (
                        TechnicalAnalysisTarget(),
                        ErrorCode.STOCK_NOT_FOUND,
                        _unknown_bare_code_detail(value),
                    )
        return target_info, None, ""

    symbol, error = resolve_stock(value, auto_refresh_on_miss=False)
    if error == ErrorCode.STOCK_AMBIGUOUS:
        return TechnicalAnalysisTarget(), error, _ambiguous_stock_detail(value)
    if error or not symbol:
        return TechnicalAnalysisTarget(), ErrorCode.STOCK_NOT_FOUND, f"cannot resolve stock name: {value}"

    resolved = _technical_analysis_target(symbol)
    stock = get_stock_symbol_by_code(symbol)
    return (
        TechnicalAnalysisTarget(
            normalized_target=resolved.normalized_target,
            skill_symbol=resolved.skill_symbol,
            is_a_share=resolved.is_a_share,
            stock_name=str(stock.get("name") or value),
            asset_type=str(stock.get("asset_type") or resolved.asset_type),
            market=str(stock.get("market") or resolved.market),
            ts_code=str(stock.get("ts_code") or resolved.ts_code),
        ),
        None,
        "",
    )


def _ambiguous_stock_detail(value: str) -> str:
    matches = list_exact_stock_name_matches(value)
    if not matches:
        candidate_list = ""
    else:
        candidate_list = _candidate_list(matches, lambda row: _stock_candidate_label(row, value))
    return format_reply_text(
        "reply.technical_analysis.stock_name_ambiguous",
        target=value,
        candidate_list=candidate_list,
    )


def _candidate_list(rows: list[dict[str, str]], label_func) -> str:
    lines: list[str] = []
    for index, row in enumerate(rows, start=1):
        code = str(row.get("code") or "").strip()
        lines.append(f"{index}. {component_link('technical-analysis', code, label_func(row))}")
    return "\n".join(lines)


def _stock_candidate_label(row: dict[str, str], fallback_name: str = "") -> str:
    code = str(row.get("code") or "").strip()
    name = str(row.get("name") or fallback_name).strip()
    market = str(row.get("market") or "").strip().upper()
    suffix = f"（{market}）" if market else ""
    return f"{code} {name}{suffix}".strip()


def _bare_code_index_suggestion_detail(value: str, matches: list[dict[str, str]]) -> str:
    bare_code = str(value or "").strip()
    if not matches:
        return ""
    if len(matches) == 1:
        row = matches[0]
        code = str(row.get("code") or "").strip()
        name = str(row.get("name") or "该指数").strip()
        candidate = component_link("technical-analysis", code)
        return format_reply_text(
            "reply.technical_analysis.bare_code_index_suggestion",
            target=bare_code,
            name=name,
            candidate=candidate,
            candidate_list=f"1. {candidate}",
        )
    candidate_list = _candidate_list(
        matches,
        lambda row: f"{str(row.get('code') or '').strip()} {str(row.get('name') or '指数').strip()}".strip(),
    )
    return format_reply_text(
        "reply.technical_analysis.bare_code_index_candidates",
        target=bare_code,
        candidate_list=candidate_list,
    )


def _bare_code_ambiguous_detail(value: str, matches: list[dict[str, str]]) -> str:
    bare_code = str(value or "").strip()
    return format_reply_text(
        "reply.technical_analysis.bare_code_ambiguous",
        target=bare_code,
        candidate_list=_candidate_list(matches, _asset_candidate_label),
    )


def _asset_candidate_label(row: dict[str, str]) -> str:
    code = str(row.get("code") or "").strip()
    name = str(row.get("name") or "").strip()
    asset_type = str(row.get("asset_type") or "").strip().lower()
    asset_label = {
        "a_share": "A股",
        "index": "指数",
        "etf": "ETF",
        "fund": "基金",
        "convertible_bond": "可转债",
    }.get(asset_type, asset_type or "标的")
    label = f"（{asset_label}）" if asset_label else ""
    return f"{code} {name}{label}".strip()


def _unknown_bare_code_detail(value: str) -> str:
    return format_reply_text(
        "reply.technical_analysis.unknown_bare_code",
        target=str(value or "").strip(),
        example=component_link("technical-analysis", "300502.SZ"),
    )


def _csi_symbol_suggestion_detail(value: str, suggestion: str) -> str:
    raw = str(value or "").strip().upper()
    return format_reply_text(
        "reply.technical_analysis.csi_symbol_suggestion",
        target=raw,
        suggestion=component_link("technical-analysis", suggestion),
    )


def _is_user_facing_resolution_detail(detail: str) -> bool:
    text = str(detail or "")
    return (
        (text.startswith("未找到 ") and ("请发送" in text or "请点击" in text or "重新发送" in text or "请检查代码" in text))
        or (text.startswith("代码 ") and "匹配到多个标的" in text and ("重新发送" in text or "请点击" in text))
        or (text.startswith("股票名称") and "匹配到多个标的" in text and ("重新发送" in text or "请点击" in text))
    )


def _technical_analysis_error_prompt(error: ErrorCode, detail: str = "") -> str:
    if error in {ErrorCode.STOCK_NOT_FOUND, ErrorCode.STOCK_AMBIGUOUS} and _is_user_facing_resolution_detail(detail):
        return detail
    return user_message(error)


def allow_unresolved_bare_code_analysis() -> bool:
    return bool(get_config(ALLOW_UNRESOLVED_BARE_CODE_ANALYSIS_CONFIG_KEY, False))


def _skill_symbol(symbol: str) -> str:
    return _technical_analysis_target(symbol).skill_symbol or str(symbol or "").strip()


def _technical_analysis_display_target(target_info: TechnicalAnalysisTarget) -> str:
    code = str(target_info.normalized_target or "").strip()
    name = str(target_info.stock_name or "").strip()
    if name and code and name != code:
        return f"{name}（{code}）"
    return name or code


def _technical_analysis_report_with_target_context(report_text: str, target_info: TechnicalAnalysisTarget) -> str:
    display_target = _technical_analysis_display_target(target_info)
    if not display_target:
        return report_text
    lines = [
        "【系统约束：标的名称】",
        f"- 标准代码：{target_info.normalized_target or '——'}",
        f"- 中文名称：{target_info.stock_name or '——'}",
        f"- 标的字段必须输出：{display_target}",
        "- 图片主标题来自“标的”字段，必须使用上述标的字段；禁止使用英文名、拼音、仅代码或报告中的其他原始名称。",
        "",
        "【技术分析报告原文】",
        report_text,
    ]
    return "\n".join(lines)


def _force_technical_analysis_display_target(standard_text: str, target_info: TechnicalAnalysisTarget) -> str:
    display_target = _technical_analysis_display_target(target_info)
    if not display_target:
        return standard_text
    replacement = f"📈 标的：{display_target}"
    pattern = re.compile(r"^.*?标的\s*[:：].*$", re.M)
    if pattern.search(standard_text):
        return pattern.sub(replacement, standard_text, count=1)
    brand_match = re.search(r"^【.+?】\s*$", standard_text, flags=re.M)
    if brand_match:
        insert_at = brand_match.end()
        return f"{standard_text[:insert_at]}\n{replacement}{standard_text[insert_at:]}"
    return f"{replacement}\n{standard_text}"


DEFAULT_TECHNICAL_ANALYSIS_PATH = "builtin/components/technical-analysis/scripts/analyze_universal.py"
ALLOW_UNRESOLVED_BARE_CODE_ANALYSIS_CONFIG_KEY = "technical_analysis.allow_unresolved_bare_code_analysis"


def _run_skill(
    symbol: str,
    output_dir: Path,
    *,
    name: str = "",
    asset_type: str = "",
    market: str = "",
    ts_code: str = "",
) -> tuple[Path, Path]:
    skill_path = Path(str(get_config("technical_analysis.skill_path") or DEFAULT_TECHNICAL_ANALYSIS_PATH))
    if not skill_path.is_absolute():
        skill_path = Path.cwd() / skill_path
    env = os.environ.copy()
    tushare_token = str(get_tushare_token() or "").strip()
    if tushare_token:
        env["TUSHARE_TOKEN"] = tushare_token
    cache_update_config = technical_analysis_cache_update_config()
    env["TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_START"] = str(cache_update_config.get("probe_start") or "15:30")
    env["TECHNICAL_ANALYSIS_CACHE_UPDATE_PROBE_END"] = str(cache_update_config.get("probe_end") or "18:00")
    command = [sys.executable, str(skill_path), "--symbol", symbol, "--output", str(output_dir)]
    if name:
        command.extend(["--name", str(name)])
    if asset_type:
        command.extend(["--asset-type", str(asset_type)])
    if market:
        command.extend(["--market", str(market)])
    if ts_code:
        command.extend(["--ts-code", str(ts_code)])
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        parts = [str(exc)]
        if exc.stdout:
            parts.append(str(exc.stdout))
        if exc.stderr:
            parts.append(str(exc.stderr))
        raise RuntimeError("\n".join(parts)) from exc
    reports = sorted(output_dir.glob("*技术分析报告*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    charts = sorted(output_dir.glob("*_TA_*.png"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not reports or not charts:
        raise RuntimeError("technical analysis skill did not produce report or main chart")
    return reports[0], charts[0]


def _run_skill_for_target(target_info: TechnicalAnalysisTarget, output_dir: Path) -> tuple[Path, Path]:
    kwargs = {
        "name": target_info.stock_name,
        "asset_type": target_info.asset_type,
        "market": target_info.market,
        "ts_code": target_info.ts_code,
    }
    try:
        signature = inspect.signature(_run_skill)
    except (TypeError, ValueError):
        signature = None
    if signature is not None and not any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        kwargs = {key: value for key, value in kwargs.items() if key in signature.parameters}
    return _run_skill(target_info.skill_symbol or _skill_symbol(target_info.normalized_target), output_dir, **kwargs)


def _classify_technical_analysis_failure(detail: str) -> ErrorCode:
    text = str(detail or "")
    data_failure_markers = (
        "所有数据源失败",
        "所有数据源均失败",
        "数据量不足",
        "无 symbol_code",
        "未配置 TUSHARE_TOKEN",
        "no data",
        "empty data",
    )
    if any(marker.lower() in text.lower() for marker in data_failure_markers):
        return ErrorCode.MARKET_DATA_UNAVAILABLE
    return ErrorCode.TECHNICAL_ANALYSIS_FAILED


def _configured_skill_path() -> Path:
    skill_path = Path(str(get_config("technical_analysis.skill_path") or DEFAULT_TECHNICAL_ANALYSIS_PATH))
    return skill_path if skill_path.is_absolute() else Path.cwd() / skill_path


def _configured_renderer_path() -> Path:
    renderer_path = Path(str(get_config("render.renderer_path") or DEFAULT_RENDERER_PATH))
    return renderer_path if renderer_path.is_absolute() else Path.cwd() / renderer_path


def _extract_market_date_from_text(text: str) -> str:
    value = text or ""
    for line in value.splitlines():
        if "数据范围" in line:
            line_dates = re.findall(r"\d{4}-\d{2}-\d{2}", line)
            if line_dates:
                return normalize_market_date(line_dates[-1])
    for pattern in (
        r"行情日期\s*[:：]\s*(\d{4}-\d{2}-\d{2})",
        r"数据日期\s*[:：]\s*(\d{4}-\d{2}-\d{2})",
        r"数据范围\s*[:：]\s*\d{4}-\d{2}-\d{2}\s*[~～至-]+\s*(\d{4}-\d{2}-\d{2})",
    ):
        match = re.search(pattern, value)
        if match:
            return normalize_market_date(match.group(1))
    match = re.search(r"\d{4}-\d{2}-\d{2}", value)
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
    if target.normalized_target and target.asset_type not in {"", "gold"}:
        return MarketDateResolver().resolve(target.normalized_target, requested_market_date)
    return MarketDateResolution()


def _force_technical_analysis_market_date(standard_text: str, market_date: str) -> str:
    normalized = normalize_market_date(market_date)
    if not normalized:
        return standard_text
    text = standard_text or ""
    replacement = f"📅 行情日期：{normalized}"
    pattern = r"(?m)^([^\n]*行情日期\s*[:：]\s*)\d{4}-\d{2}-\d{2}([^\n]*)$"
    if re.search(pattern, text):
        return re.sub(pattern, lambda match: f"{match.group(1)}{normalized}{match.group(2)}", text, count=1)
    return f"{replacement}\n{text}"


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
        investment_products.c.business_type == str(ServiceType.TECHNICAL_ANALYSIS),
        investment_products.c.target_key == symbol,
        investment_products.c.source_cache_key != "",
        investment_products.c.status == "active",
        investment_products.c.version_fingerprint != current_version_fingerprint,
        investment_request_records.c.ta_version == ta_version,
        investment_request_records.c.renderer_version == renderer_version,
        investment_request_records.c.template_version == template_version,
    ]
    if market_date:
        conditions.append(investment_products.c.business_date == market_date)
    stmt = (
        select(investment_products)
        .join(
            investment_request_records,
            investment_products.c.source_request_id == investment_request_records.c.request_id,
        )
        .where(and_(*conditions))
        .order_by(desc(investment_products.c.business_date), desc(investment_products.c.updated_at))
    )
    with connect() as conn:
        rows = conn.execute(stmt).fetchall()
    entries = []
    for row in rows:
        item = dict(row._mapping)
        entries.append(
            cache_service.CacheEntry(
                cache_key=str(item.get("source_cache_key") or ""),
                service_type=ServiceType(item.get("business_type")),
                normalized_target=str(item.get("target_key") or ""),
                market_date=str(item.get("business_date") or ""),
                version_fingerprint=str(item.get("version_fingerprint") or ""),
                output_files=cache_service._load_list(item.get("output_files")),
                artifact_owner_id=str(item.get("source_request_id") or ""),
                status=str(item.get("status") or "active"),
                hit_count=int(item.get("hit_count") or 0),
                created_at=str(item.get("created_at") or ""),
                updated_at=str(item.get("updated_at") or ""),
            )
        )
    return entries


def _compatible_cache_entry_has_files(entry: cache_service.CacheEntry) -> bool:
    if cache_service._files_available(entry.output_files):
        return True
    cache_service._invalidate_cache_entry_if_unchanged(entry)
    return False


def _technical_analysis_cache_entry_allowed(entry: cache_service.CacheEntry) -> bool:
    if technical_analysis_cache_expired_after_close(entry.market_date, entry.updated_at, normalized_target=entry.normalized_target):
        cache_service._invalidate_cache_entry_if_unchanged(entry)
        return False
    return True


def _technical_analysis_product_allowed(product: dict, *, normalized_target: str) -> bool:
    output_files = list(product.get("output_files") or [])
    if len(output_files) < 2 or not all(Path(path).is_file() for path in output_files[:2]):
        invalidate_product_if_unchanged(product)
        return False
    if technical_analysis_cache_expired_after_close(
        str(product.get("business_date") or ""),
        str(product.get("updated_at") or ""),
        normalized_target=normalized_target,
    ):
        invalidate_product_if_unchanged(product)
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


def _product_owner_matches_versions(
    product: dict,
    *,
    current_version_fingerprint: str,
    ta_version: str,
    renderer_version: str,
    template_version: str,
) -> bool:
    if str(product.get("version_fingerprint") or "") == current_version_fingerprint:
        return True
    source_request_id = str(product.get("source_request_id") or "")
    if not source_request_id:
        return False
    stmt = (
        select(investment_request_records.c.request_id)
        .where(
            investment_request_records.c.request_id == source_request_id,
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
            user_prompt=_technical_analysis_error_prompt(error, error_detail),
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
    if resolved_market_date.known and resolved_market_date.market_date:
        product = find_active_product(
            business_type=str(ServiceType.TECHNICAL_ANALYSIS),
            target_key=symbol,
            business_date=resolved_market_date.market_date,
            version_fingerprint=cache_lookup_version,
        )
        if product is not None and not _technical_analysis_product_allowed(product, normalized_target=symbol):
            product = None
        if product is not None and not _product_owner_matches_versions(
            product,
            current_version_fingerprint=combined_version,
            ta_version=ta_version,
            renderer_version=renderer_version,
            template_version=template_version,
        ):
            product = None
        if product is not None:
            increment_product_hit(product["product_id"])
            product_cache_key = str(product.get("source_cache_key") or "")
            output_files = list(product.get("output_files") or [])
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
                market_date=str(product.get("business_date") or ""),
                program_version=program_version,
                ta_version=ta_version,
                renderer_version=renderer_version,
                template_version=template_version,
                version_fingerprint=str(product.get("version_fingerprint") or cache_lookup_version),
                cache_key=product_cache_key,
                cache_hit=True,
                source_type="product",
                source_id=str(product.get("product_id") or ""),
            )
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
            source_type="cache",
            source_id=cached.cache_key,
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
        generated_report_path, generated_chart_path = _run_skill_for_target(target_info, output_dir)
        report_text = generated_report_path.read_text(encoding="utf-8")
        report_text_with_context = _technical_analysis_report_with_target_context(report_text, target_info)
        ai_result = generate_technical_analysis_text(report_text_with_context)
        if not ai_result.success:
            return TechnicalAnalysisResult(
                False,
                error_code=ErrorCode.TECHNICAL_ANALYSIS_FAILED,
                user_prompt=user_message(ErrorCode.TECHNICAL_ANALYSIS_FAILED),
                detail=sanitize_sensitive_text(ai_result.detail),
            )
        standard_text = _force_technical_analysis_display_target(ai_result.text, target_info)
        generated_market_date, market_date_warning = _market_date(standard_text, generated_report_path, generated_chart_path)
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
        standard_text = _force_technical_analysis_market_date(standard_text, market_date)
        standard_text = apply_technical_analysis_card_footer(standard_text)
        version_suffix = re.sub(r"[^A-Za-z0-9]+", "", combined_version)[-12:] or "version"
        card_market_date = market_date or "unknown"
        card_path = output_dir / f"{_target_path_part(symbol.replace('.', '_'))}_signal_card_{card_market_date}_{version_suffix}.png"
        render_result = render_technical_analysis_card(standard_text, str(card_path))
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
        detail = sanitize_sensitive_text(str(exc))
        code = _classify_technical_analysis_failure(detail)
        return TechnicalAnalysisResult(
            False,
            error_code=code,
            user_prompt=user_message(code),
            detail=detail,
        )
