# encoding:utf-8
"""Structured technical-analysis card payload helpers."""

import json
import re
from dataclasses import dataclass
from typing import Any


DEFAULT_TEXT = "——"


@dataclass
class StructuredCardResult:
    success: bool
    standard_text: str = ""
    error: str = ""
    payload: dict[str, Any] | None = None


def _as_text(value: Any, default: str = DEFAULT_TEXT) -> str:
    text = str(value or "").strip()
    return text or default


def _as_evidence(value: Any) -> list[str]:
    if isinstance(value, str):
        items = re.split(r"[；;\n]", value)
    elif isinstance(value, list):
        items = value
    else:
        items = []
    evidence = [_as_text(item, "") for item in items]
    return [item for item in evidence if item] or ["报告未给出明确依据"]


def _extract_json_text(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("empty model output")
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, flags=re.I)
    if fenced:
        raw = fenced.group(1).strip()
    if raw.startswith("{") and raw.endswith("}"):
        return raw
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return raw[start : end + 1]
    raise ValueError("model output does not contain a JSON object")


def parse_technical_analysis_card_payload(text: str) -> dict[str, Any]:
    payload = json.loads(_extract_json_text(text))
    if not isinstance(payload, dict):
        raise ValueError("technical analysis JSON payload must be an object")
    return payload


def _confirm(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        value = {}
    return {
        "conclusion": _as_text(value.get("conclusion")),
        "evidence": _as_evidence(value.get("evidence")),
    }


def _level(payload: dict[str, Any], key: str) -> dict[str, str]:
    value = payload.get(key)
    if not isinstance(value, dict):
        value = {}
    return {
        "value": _as_text(value.get("value")),
        "source": _as_text(value.get("source")),
    }


def normalize_technical_analysis_card_payload(payload: dict[str, Any]) -> dict[str, Any]:
    trend = payload.get("trend")
    if not isinstance(trend, dict):
        trend = {}
    key_levels = payload.get("key_levels")
    if not isinstance(key_levels, dict):
        key_levels = {}
    operation = payload.get("operation_guide")
    if not isinstance(operation, dict):
        operation = {}
    return {
        "target": _as_text(payload.get("target")),
        "signal_direction": _as_text(payload.get("signal_direction")),
        "latest_close": _as_text(payload.get("latest_close")),
        "market_date": _as_text(payload.get("market_date")),
        "daily_change": _as_text(payload.get("daily_change"), ""),
        "analysis_model": _as_text(payload.get("analysis_model"), "技术分析体系"),
        "trend": {
            "summary": _as_text(trend.get("summary")),
            "direction_confirm": _confirm(trend, "direction_confirm"),
            "quality_confirm": _confirm(trend, "quality_confirm"),
            "risk_confirm": _confirm(trend, "risk_confirm"),
            "pattern_verify": _confirm(trend, "pattern_verify"),
        },
        "key_levels": {
            "strong_resistance": _level(key_levels, "strong_resistance"),
            "strong_support": _level(key_levels, "strong_support"),
        },
        "operation_guide": {
            "summary": _as_text(operation.get("summary")),
            "breakout": _as_text(operation.get("breakout")),
            "range": _as_text(operation.get("range")),
            "breakdown": _as_text(operation.get("breakdown")),
        },
    }


def validate_technical_analysis_card_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("target", "signal_direction", "latest_close", "market_date"):
        if _as_text(payload.get(key)) == DEFAULT_TEXT:
            errors.append(f"missing {key}")
    trend = payload.get("trend") if isinstance(payload.get("trend"), dict) else {}
    if _as_text(trend.get("summary")) == DEFAULT_TEXT:
        errors.append("missing trend.summary")
    for key in ("direction_confirm", "quality_confirm", "risk_confirm", "pattern_verify"):
        item = trend.get(key) if isinstance(trend.get(key), dict) else {}
        if _as_text(item.get("conclusion")) == DEFAULT_TEXT:
            errors.append(f"missing trend.{key}.conclusion")
        if not _as_evidence(item.get("evidence")):
            errors.append(f"missing trend.{key}.evidence")
    key_levels = payload.get("key_levels") if isinstance(payload.get("key_levels"), dict) else {}
    for key in ("strong_resistance", "strong_support"):
        item = key_levels.get(key) if isinstance(key_levels.get(key), dict) else {}
        if _as_text(item.get("value")) == DEFAULT_TEXT:
            errors.append(f"missing key_levels.{key}.value")
    operation = payload.get("operation_guide") if isinstance(payload.get("operation_guide"), dict) else {}
    for key in ("summary", "breakout", "range", "breakdown"):
        if _as_text(operation.get(key)) == DEFAULT_TEXT:
            errors.append(f"missing operation_guide.{key}")
    return errors


def _format_price(value: str) -> str:
    text = _as_text(value)
    if text == DEFAULT_TEXT or text.endswith("元"):
        return text
    return f"{text} 元"


def _format_market_date(payload: dict[str, Any]) -> str:
    market_date = _as_text(payload.get("market_date"))
    daily_change = _as_text(payload.get("daily_change"), "")
    if not daily_change:
        return market_date
    label = "日内跌幅" if daily_change.startswith("-") else "日内涨幅"
    if "跌幅" in daily_change or "涨幅" in daily_change:
        return f"{market_date}  {daily_change}"
    return f"{market_date}  {label}：{daily_change}"


def _compact(text: str, max_len: int = 45) -> str:
    value = re.sub(r"\s+", "", _as_text(text))
    return value if len(value) <= max_len else f"{value[: max_len - 1]}…"


def _confirm_line(label: str, item: dict[str, Any]) -> str:
    conclusion = _as_text(item.get("conclusion"))
    evidence = "、".join(_as_evidence(item.get("evidence"))[:3])
    return f"▪️ {label}：{_compact(f'{conclusion}，依据：{evidence}', 72)}"


def render_technical_analysis_standard_text(payload: dict[str, Any]) -> str:
    data = normalize_technical_analysis_card_payload(payload)
    trend = data["trend"]
    levels = data["key_levels"]
    operation = data["operation_guide"]
    resistance = levels["strong_resistance"]
    support = levels["strong_support"]
    return "\n".join(
        [
            "【固收 | 智能投研辅助系统】",
            "",
            "——————————————",
            f"📈 标的：{data['target']}",
            f"[庆祝] 信号方向：{data['signal_direction']}",
            f"💰 最新收盘：{_format_price(data['latest_close'])}",
            f"📅 行情日期：{_format_market_date(data)}",
            f"🔧 分析模型：{data['analysis_model']}",
            "",
            "📊 趋势研判",
            _compact(trend["summary"], 120),
            _confirm_line("方向确认（趋势 x 动量）", trend["direction_confirm"]),
            _confirm_line("质量确认（趋势 x 量价）", trend["quality_confirm"]),
            _confirm_line("风险确认（动量 x 波动 x 位置风险）", trend["risk_confirm"]),
            _confirm_line("形态验证", trend["pattern_verify"]),
            "",
            "🎯 核心关键位",
            f"▪️ 强压力：{resistance['value']}（{resistance['source']}）",
            f"▪️ 强支撑：{support['value']}（{support['source']}）",
            "",
            "💡 实操指引",
            f"{operation['summary']}：",
            f"- 📈 {operation['breakout']}",
            f"- 🔄 {operation['range']}",
            f"- 📉 {operation['breakdown']}",
        ]
    )


def technical_analysis_card_text_from_model_output(text: str) -> StructuredCardResult:
    try:
        payload = parse_technical_analysis_card_payload(text)
        errors = validate_technical_analysis_card_payload(payload)
        if errors:
            return StructuredCardResult(False, error="; ".join(errors), payload=payload)
        return StructuredCardResult(True, render_technical_analysis_standard_text(payload), payload=payload)
    except Exception as exc:
        return StructuredCardResult(False, error=str(exc))
