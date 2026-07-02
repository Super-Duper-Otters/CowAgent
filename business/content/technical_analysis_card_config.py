# encoding:utf-8
import re

from business.config.config_service import get_config


TECHNICAL_ANALYSIS_CARD_FOOTER_DEFAULTS = {
    "risk_disclaimer": "本内容仅供研究参考，不构成任何投资建议",
    "auth_remaining": "——",
    "data_source": "AKShare / Tushare / BaoStock",
    "contact": "刘静怡13681991121",
}

TECHNICAL_ANALYSIS_CARD_FOOTER_CONFIG_KEYS = {
    "risk_disclaimer": "technical_analysis.card.risk_disclaimer",
    "auth_remaining": "technical_analysis.card.auth_remaining",
    "data_source": "technical_analysis.card.data_source",
    "contact": "technical_analysis.card.contact",
}


def technical_analysis_card_footer_config() -> dict[str, str]:
    return {
        field: str(get_config(config_key, TECHNICAL_ANALYSIS_CARD_FOOTER_DEFAULTS[field]) or "").strip()
        or TECHNICAL_ANALYSIS_CARD_FOOTER_DEFAULTS[field]
        for field, config_key in TECHNICAL_ANALYSIS_CARD_FOOTER_CONFIG_KEYS.items()
    }


def _strip_prefixed_value(value: str, pattern: str) -> str:
    return re.sub(pattern, "", str(value or "").strip(), count=1).strip() or "——"


def technical_analysis_card_footer_lines(config: dict[str, str] | None = None) -> list[str]:
    values = config or technical_analysis_card_footer_config()
    risk = str(values.get("risk_disclaimer") or "").strip() or TECHNICAL_ANALYSIS_CARD_FOOTER_DEFAULTS["risk_disclaimer"]
    auth = _strip_prefixed_value(values.get("auth_remaining", ""), r"^⏱️?\s*授权剩余时间\s*[:：]\s*")
    data_source = _strip_prefixed_value(values.get("data_source", ""), r"^📚?\s*数据来源\s*[:：]\s*")
    contact = _strip_prefixed_value(values.get("contact", ""), r"^🤝?\s*业务对接\s*[:：]\s*")
    risk_line = risk if risk.startswith("⚠️") else f"⚠️ {risk}"
    return [
        risk_line,
        f"⏱️ 授权剩余时间：{auth}",
        f"📚 数据来源：{data_source}",
        f"🤝 业务对接：{contact}",
    ]


def apply_technical_analysis_card_footer(text: str, config: dict[str, str] | None = None) -> str:
    cleaned_lines = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append(line)
            continue
        if stripped.startswith("⚠️"):
            continue
        if re.search(r"授权剩余时间\s*[:：]", stripped):
            continue
        if re.search(r"数据来源\s*[:：]", stripped):
            continue
        if re.search(r"业务对接\s*[:：]", stripped):
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines).rstrip()
    footer = "\n".join(["——————————————", *technical_analysis_card_footer_lines(config)])
    return f"{cleaned}\n{footer}" if cleaned else footer
