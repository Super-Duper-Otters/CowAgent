# encoding:utf-8
import base64
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import requests

from common import const
from bridge.bridge import Bridge
from models.openai.openai_http_client import OpenAIHTTPError

from business.config import config_service as config_service
from business.config.config_service import get_config, safe_log_value, sanitize_sensitive_text
from business.config.constants import ErrorCode, ServiceType, Status, user_message

IMAGE_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

TRANSIENT_MODEL_STATUS_CODES = {0, 408, 409, 425, 429, 500, 502, 503, 504}
MODEL_RETRY_DELAYS_SECONDS = (0.0, 1.0)

RATE_LABELS = (
    "标的",
    "最新收盘",
    "行情日期",
    "分析模型",
    "当日核心信号",
    "复合策略信号",
    "多头",
    "空头",
    "日度主线",
    "周度全景复盘",
    "近一周整体信号",
    "周度主线",
    "授权剩余时间",
    "数据来源",
    "业务对接",
)

TECHNICAL_ANALYSIS_PROMPT_BLOCKS = {
    "role": {
        "label": "角色与 JSON 输出边界",
        "text": (
            "你是技术分析报告结构化抽取助手。请把用户提供的技术分析 Markdown 报告整理成严格 JSON，"
            "供业务代码生成 signal-card-renderer 技术分析卡片文本。\n"
            "必须只输出一个 JSON object，禁止输出解释、Markdown 代码块、表格、模板说明或补充问题。\n"
            "字段缺失时填“——”；不要编造报告中没有的数据；数值、日期、支撑阻力优先使用报告原文。\n\n"
        ),
    },
    "target_constraints": {
        "label": "标的名称约束",
        "text": (
        "如果用户内容开头包含“【系统约束：标的名称】”，这些约束优先级高于报告正文：\n"
        "1. “标的字段必须输出”后面的值必须原样用于“📈 标的：”字段；不得改写、翻译、缩写或只保留代码。\n"
        "2. 图片主标题由“📈 标的：”字段渲染而来，因此该字段必须优先使用股票字典中文名，例如“新易盛（300502.SZ）”。\n"
        "3. 若报告正文、图表标题或文件名中的标的名称与系统约束冲突，必须以系统约束为准。\n\n"
        ),
    },
    "header_fields": {
        "label": "JSON 顶层字段",
        "text": (
            "业务代码会把 JSON 渲染为下面的卡片头部结构，字段含义必须按此模板抽取：\n"
            "【固收 | 智能投研辅助系统】\n\n"
            "——————————————\n"
            "📈 标的：<target>\n"
            "[庆祝] 信号方向：<signal_direction>\n"
            "💰 最新收盘：<latest_close> 元\n"
            "📅 行情日期：<market_date>  日内涨幅：<daily_change> 或 日内跌幅：<daily_change>\n"
            "🔧 分析模型：技术分析体系\n\n"
            "JSON 顶层字段必须包含：\n"
            "{\n"
            '  "target": "<优先使用系统约束中的标的字段必须输出；否则使用股票中文名（标准代码）>",\n'
            '  "signal_direction": "<看涨观察/区间观望/看跌防守/买入/卖出等，按报告多空倾向归纳>",\n'
            '  "latest_close": "<价格，不带“元”；无法识别填“——”>",\n'
            '  "market_date": "<YYYY-MM-DD；无法识别填“——”>",\n'
            '  "daily_change": "<+x.xx% 或 -x.xx%；无法识别填空字符串>",\n'
            '  "analysis_model": "技术分析体系"\n'
            "}\n\n"
        ),
    },
    "trend_section": {
        "label": "趋势研判 JSON",
        "text": (
            '必须输出 "trend" 对象：\n'
            '"trend": {\n'
            '  "summary": "<使用“指标变化=结论”的链式表达，1 到 2 句完成趋势、动量、风险和形态归纳；必须至少引用报告原文中的一个具体指标、数值、分位、形态名称或关键位>",\n'
            '  "direction_confirm": {"conclusion": "<说明趋势与动量是否同向>", "evidence": ["<均线结构、MACD DIF/DEA、MACD柱体、RSI、KDJ等具体依据>"]},\n'
            '  "quality_confirm": {"conclusion": "<说明成交量/量价是否配合>", "evidence": ["<成交量、量比、OBV、AD、ADOSC或量价描述>"]},\n'
            '  "risk_confirm": {"conclusion": "<说明超买、波动或回撤风险>", "evidence": ["<RSI/KDJ超买超卖、ATR分位、BOLL位置/宽度、历史分位或位置风险描述>"]},\n'
            '  "pattern_verify": {"conclusion": "<最新K线形态及方向含义>", "evidence": ["<最新K线形态名称、看涨/看跌方向和验证含义>"]}\n'
            "}\n"
            "不得改变 signal_direction 给出的多空方向，不得把看涨改成看跌或把看跌改成看涨。\n"
            "示例 summary：RSI(6)从92%大幅回落至55%，超买风险化解=健康的回调整理。"
            "均线多头维持+MACD金叉不破=中期趋势未改。\n\n"
        ),
    },
    "key_levels_section": {
        "label": "核心关键位 JSON",
        "text": (
            '必须输出 "key_levels" 对象：\n'
            '"key_levels": {\n'
            '  "strong_resistance": {"value": "<上方最重要阻力位>", "source": "<来源，如 BOLL上轨/前高/均线>"},\n'
            '  "strong_support": {"value": "<下方最重要支撑位>", "source": "<来源，如 MA5/MA10/MA20/BOLL中轨>"}\n'
            "}\n\n"
        ),
    },
    "ops_guide_section": {
        "label": "实操指引 JSON",
        "text": (
            '必须输出 "operation_guide" 对象：\n'
            '"operation_guide": {\n'
            '  "summary": "<一句总评，不带冒号>",\n'
            '  "breakout": "<突破/反弹收复关键位后的走势判断>",\n'
            '  "range": "<区间震荡时的量能与等待方向>",\n'
            '  "breakdown": "<跌破关键均线/支撑后的风险提示>"\n'
            "}\n"
            "示例：summary=超买化解，均线多头维持，健康的回调整理；"
            "breakout=反弹收复109.335（前收盘）：震荡偏强延续；"
            "range=109.06~109.40区间震荡：缩量整固，等待方向；"
            "breakdown=跌破MA20（109.064）：短线走弱，关注108.80（MA60）。\n\n"
        ),
    },
    "footer_injection_rule": {
        "label": "页脚注入规则",
        "text": (
        "页脚固定字段由业务代码在渲染前注入，模型不要生成风险声明、授权剩余时间、数据来源或业务对接的固定值；"
        "数据来源和业务对接强制使用技术分析组件的 card_footer 配置。\n\n"
        ),
    },
    "conversion_rules": {
        "label": "转换规则",
        "text": (
        "转换规则：\n"
        "1. 输出必须是合法 JSON object，不能包含 Markdown 代码块。\n"
        "2. 必须包含 target、signal_direction、latest_close、market_date、trend、key_levels、operation_guide。\n"
        "3. target 必须是整张图片的主标题标的，不能输出英文名、拼音、仅代码或报告原始别名来替代系统约束名称。\n"
        "4. direction_confirm / quality_confirm / risk_confirm / pattern_verify 四项必须同时包含 conclusion 和 evidence 数组。\n"
        "5. evidence 不得只写结论，必须包含报告原文中的至少一个具体依据，如指标名、数值、分位、形态名称、关键位或量价信号；报告未提供时填“报告未给出明确依据”。\n"
        "6. trend.summary 必须优先使用“指标变化=结论”“指标A+指标B=结论”的短句组合。\n"
        "7. operation_guide 必须保持 breakout、range、breakdown 三个方向，不得因为措辞优化改变原始多空判断。\n"
        "8. 不要输出原报告的大段表格、附录、形态胜率明细或情景推演表，只保留可渲染卡片需要的信息。"
        ),
    },
}

DEFAULT_TECHNICAL_ANALYSIS_PROMPT = "".join(block["text"] for block in TECHNICAL_ANALYSIS_PROMPT_BLOCKS.values())

DEFAULT_RATE_PROMPT = (
    "你是利率择时图片卡片整理助手。请把用户提供的文字、图片识别结果或投研资料整理成 "
    "signal-card-renderer 可直接渲染的利率择时卡片标准文本。\n\n"
    "必须只输出卡片正文，禁止输出解释、模板说明、补充问题、Markdown 表格、Markdown 代码块或额外标题。\n"
    "字段缺失时填“——”；不要编造资料中没有的数据。\n"
    "所有章节标题、字段名必须严格保留。每条 bullet 控制在 35 字以内，每个章节最多 3 条 bullet，避免图片过长。\n\n"
    "输出必须严格使用下面结构：\n\n"
    "【浙商固收 | 智能投研辅助系统】\n"
    "——————————————\n"
    "📉 标的：<如十债主连；无法识别填——>\n"
    "💰 最新收盘：<价格> 元\n"
    "📅 行情日期：<YYYY-MM-DD>\n"
    "🔧 分析模型：利率交易性择时体系\n\n"
    "📊 当日核心信号\n"
    "复合策略信号：<入场/持续入场/观望/出场/规避等，括号内可保留信号数量，如 入场（4/7）>\n"
    "多头：<多头信号名称，用顿号分隔；没有填——>；空头：<空头信号名称，用顿号分隔；没有填——>\n\n"
    "▪️ <当日核心判断 1，35 字以内>\n"
    "▪️ <当日核心判断 2，35 字以内>\n"
    "▪️ <当日风险或边际变化，35 字以内>\n\n"
    "💡日度主线：<一句话概括，不超过 25 字>\n\n"
    "📊 周度全景复盘\n"
    "近一周整体信号：<持续入场/震荡偏多/转弱/观望等>\n\n"
    "▪️ <周度判断 1，35 字以内>\n"
    "▪️ <周度判断 2，35 字以内>\n"
    "▪️ <周度风险或变化，35 字以内>\n\n"
    "💡周度主线：<一句话概括，不超过 25 字>\n\n"
    "——————————————\n"
    "⚠️ 本内容仅供研究参考，不构成任何投资建议\n"
    "⏱️ 授权剩余时间：——\n"
    "📚 数据来源：<资料来源；无法识别填——>\n"
    "🤝 业务对接：<联系人；无法识别填——>\n\n"
    "转换规则：\n"
    "1. 必须包含“当日核心信号”“周度全景复盘”“复合策略信号”。\n"
    "2. “多头”和“空头”必须写在同一行，格式必须是“多头：...；空头：...”。\n"
    "3. 当日和周度 bullet 必须以“▪️”开头。\n"
    "4. 不要输出长篇分析、表格、编号列表或原始材料摘录。\n"
    "5. 如果资料只有日度内容，周度部分仍保留，缺失字段填“——”。"
)

DEFAULT_CONVERTIBLE_BOND_PROMPT = (
    "你是可转债多因子图片卡片整理助手。请把用户提供的文字、图片识别结果或投研资料整理成 "
    "signal-card-renderer 可直接渲染的可转债多因子卡片标准文本。\n\n"
    "必须只输出卡片正文，禁止输出解释、模板说明、补充问题、Markdown 表格、Markdown 代码块或额外标题。\n"
    "字段缺失时填“——”；不要编造资料中没有的数据。\n"
    "所有章节标题、字段名必须严格保留。每条 bullet 控制在 40 字以内，每个章节最多 3 条 bullet，避免图片过长。\n\n"
    "输出必须严格使用下面结构：\n\n"
    "【浙商固收 | 智能投研辅助系统】\n\n"
    "——————————————\n"
    "📅 跟踪日期：<YYYY-MM-DD>\n"
    "🔧 分析模型：可转债多因子择券体系\n"
    "📊 跟踪维度：流动性 / 波动率 / 动量 / 量价相关性 / 估值\n\n"
    "📊 市场与风格表现\n\n"
    "<一句市场总览，不超过 45 字>\n"
    "▪️ 最新截面：<当前市场/风格表现，40 字以内>\n"
    "▪️ 近一周变化：<近一周边际变化，40 字以内>\n"
    "▪️ 整体判断：<总体判断，40 字以内>\n\n"
    "🧭 行业结构\n\n"
    "<一句行业结构总览，不超过 45 字>\n"
    "▪️ 最新截面：<行业分布或强弱，40 字以内>\n"
    "▪️ 近一周变化：<行业边际变化，40 字以内>\n"
    "▪️ 结构判断：<行业层面判断，40 字以内>\n\n"
    "🎯 错定价跟踪\n\n"
    "<一句错定价结构总览，不超过 45 字>\n"
    "▪️ 最新截面：<必须包含“xxx、xxx、xxx等处于相对高偏离区间”；以及“xxx、xxx、xxx等处于显著负偏离区间”>\n"
    "▪️ 近一周变化：<高低偏离品种变化，40 字以内>\n"
    "▪️ 跟踪重点：<高偏离/负偏离操作关注点，40 字以内>\n\n"
    "💡 实操指引\n"
    "<一句到两句话，合计不超过 45 字>\n\n"
    "——————————————\n"
    "⚠️ 本内容仅供研究参考，不构成任何投资建议\n"
    "⏱️ 授权剩余时间：——\n"
    "📚 数据来源：<资料来源；无法识别填——>\n"
    "🤝 业务对接：<联系人；无法识别填——>\n\n"
    "转换规则：\n"
    "1. 必须包含“市场与风格表现”“行业结构”“错定价跟踪”“实操指引”四个章节。\n"
    "2. 三个主体章节内，第一段为摘要，后面 bullet 必须以“▪️”开头。\n"
    "3. “整体判断”“结构判断”“跟踪重点”必须作为 bullet 标签出现。\n"
    "4. 错定价跟踪的“最新截面”必须尽量使用句式："
    "“A、B、C等处于相对高偏离区间，需关注估值溢价风险；D、E、F等处于显著负偏离区间，具备低估修复线索。”\n"
    "5. 不要输出长篇分析、表格、编号列表或原始材料摘录。"
)


class ModelResponseError(RuntimeError):
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class AIGenerationRequest:
    service_type: ServiceType
    source_text: str
    prompt: str
    source_files: list[str] = field(default_factory=list)
    model_provider: str = ""
    model_name: str = ""
    api_base: str = ""
    api_key: str = ""
    temperature: float = 0.7

    @property
    def safe_model_params(self) -> dict[str, str | float]:
        return {
            "provider": self.model_provider,
            "model": self.model_name,
            "api_base": self.api_base,
            "api_key": safe_log_value("model.api_key", self.api_key),
            "temperature": self.temperature,
        }


@dataclass
class AIGenerationResult:
    success: bool
    text: str = ""
    error_code: ErrorCode | None = None
    user_prompt: str = ""
    detail: str = ""
    output_files: list[str] = field(default_factory=list)
    prompt: str = ""
    service_type: ServiceType | None = None
    source_text: str = ""
    model_params: dict[str, str | float] = field(default_factory=dict)
    generated_text: str = ""
    status: Status = Status.FAILED
    failure_reason: str = ""


class ModelAdapter(Protocol):
    def generate(self, request: AIGenerationRequest) -> str:
        ...


def _line_value_from_labels(text: str, label: str, labels: tuple[str, ...]) -> str:
    others = [item for item in labels if item != label]
    stop = "|".join(re.escape(item) for item in others)
    pattern = re.compile(
        rf"(?:^|[；;\n]\s*){re.escape(label)}\s*[:：]\s*(.*?)(?=(?:[；;\n]\s*(?:{stop})\s*[:：])|$)",
        re.S,
    )
    match = pattern.search(text)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip(" ；;")


def _normalize_rate_text(text: str) -> str:
    def has_standalone_heading(heading: str) -> bool:
        for line in text.splitlines():
            cleaned = re.sub(r"^[#\s📊🧭🎯]+", "", line).strip()
            if cleaned == heading:
                return True
        return False

    if all(has_standalone_heading(heading) for heading in ("当日核心信号", "周度全景复盘")):
        return text
    values = {label: _line_value_from_labels(text, label, RATE_LABELS) for label in RATE_LABELS}
    if not all(values.get(label) for label in ("标的", "行情日期", "复合策略信号")):
        return text
    daily_summary = values.get("当日核心信号") or "——"
    weekly_summary = values.get("周度全景复盘") or "——"
    data_source = values.get("数据来源") or "——"
    return "\n".join(
        [
            "【浙商固收 | 智能投研辅助系统】",
            "——————————————",
            f"📉 标的：{values.get('标的') or '——'}",
            f"💰 最新收盘：{values.get('最新收盘') or '——'}",
            f"📅 行情日期：{values.get('行情日期') or '——'}",
            f"🔧 分析模型：{values.get('分析模型') or '利率交易性择时体系'}",
            "",
            "📊 当日核心信号",
            f"复合策略信号：{values.get('复合策略信号') or '——'}",
            f"多头：{values.get('多头') or '——'}；空头：{values.get('空头') or '——'}",
            "",
            f"▪️{daily_summary}",
            f"💡日度主线：{values.get('日度主线') or daily_summary}",
            "",
            "📊 周度全景复盘",
            f"近一周整体信号：{values.get('近一周整体信号') or values.get('复合策略信号') or '——'}",
            "",
            f"▪️{weekly_summary}",
            f"💡周度主线：{values.get('周度主线') or weekly_summary}",
            "",
            "——————————————",
            "⚠️ 本内容仅供研究参考，不构成任何投资建议",
            f"⏱️ 授权剩余时间：{values.get('授权剩余时间') or '——'}",
            f"📚 数据来源：{data_source}",
            f"🤝 业务对接：{values.get('业务对接') or '——'}",
        ]
    )


def _extract_technical_analysis_intraday_change(source_text: str) -> tuple[str, str]:
    match = re.search(
        r"\|\s*日涨跌幅\s*\|\s*\*{0,2}\s*([+-]?\d+(?:\.\d+)?%)\s*\*{0,2}\s*\|",
        source_text or "",
    )
    if not match:
        match = re.search(r"日涨跌幅\s*[:：]\s*\*{0,2}\s*([+-]?\d+(?:\.\d+)?%)", source_text or "")
    if not match:
        return "", ""
    change = match.group(1).strip()
    try:
        numeric = float(change.rstrip("%"))
    except ValueError:
        return "", ""
    return ("涨幅" if numeric >= 0 else "跌幅"), change


def _normalize_technical_analysis_text(text: str, source_text: str) -> str:
    if re.search(r"日内(?:涨幅|跌幅)\s*[:：]\s*[+-]?\d+(?:\.\d+)?%", text or ""):
        return text
    direction, change = _extract_technical_analysis_intraday_change(source_text)
    if not direction:
        return text

    def replace_market_line(match: re.Match[str]) -> str:
        prefix = match.group(1).rstrip()
        normalized_prefix = re.sub(r"\s+日涨跌幅\s*[:：]\s*[+-]?\d+(?:\.\d+)?%", "", prefix)
        return f"{normalized_prefix}  日内{direction}：{change}"

    return re.sub(
        r"^([^\n]*行情日期\s*[:：]\s*\d{4}-\d{2}-\d{2}[^\n]*)$",
        replace_market_line,
        text,
        count=1,
        flags=re.M,
    )


def normalize_generated_text(service_type: ServiceType, text: str, source_text: str = "") -> str:
    if service_type == ServiceType.TECHNICAL_ANALYSIS:
        from business.content.technical_analysis_card_structured import technical_analysis_card_text_from_model_output

        structured = technical_analysis_card_text_from_model_output(text)
        if structured.success:
            return _normalize_technical_analysis_text(structured.standard_text, source_text)
        if re.match(r"^\s*(?:```json\s*)?\{", text or "", flags=re.I):
            raise ValueError(f"technical analysis JSON payload invalid: {structured.error}")
        return _normalize_technical_analysis_text(text, source_text)
    if service_type == ServiceType.RATE:
        return _normalize_rate_text(text)
    return text


class ExistingModelAdapter:
    def __init__(self, bot: Any | None = None):
        self._bot = bot

    def _get_bot(self) -> Any:
        if self._bot is not None:
            return self._bot
        return Bridge().get_bot("chat")

    @staticmethod
    def _image_block(source_file: str) -> dict[str, Any] | None:
        path = Path(source_file)
        mime_type = IMAGE_MIME_TYPES.get(path.suffix.lower())
        if not mime_type or not path.is_file():
            return None
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
        }

    @classmethod
    def _image_blocks(cls, request: AIGenerationRequest) -> list[dict[str, Any]]:
        return [block for path in request.source_files if (block := cls._image_block(path)) is not None]

    @classmethod
    def _build_user_message(cls, request: AIGenerationRequest) -> dict[str, Any]:
        image_blocks = cls._image_blocks(request)
        if not image_blocks:
            return {"role": "user", "content": request.source_text}

        text_parts = []
        if request.source_text.strip():
            text_parts.append(request.source_text.strip())
        text_parts.append("请读取并整理以下上传图片中的利率/转债资料。")
        text_parts.append("附件文件：")
        text_parts.extend(f"- {path}" for path in request.source_files)
        return {
            "role": "user",
            "content": [
                {"type": "text", "text": "\n".join(text_parts)},
                *image_blocks,
            ],
        }

    @staticmethod
    def _is_transient_model_error(exc: Exception) -> bool:
        if isinstance(exc, OpenAIHTTPError):
            return exc.status_code in TRANSIENT_MODEL_STATUS_CODES
        if isinstance(exc, ModelResponseError):
            return exc.status_code in TRANSIENT_MODEL_STATUS_CODES
        return isinstance(
            exc,
            (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
            ),
        )

    @staticmethod
    def _content_from_response(response: Any) -> str:
        if not isinstance(response, dict) and hasattr(response, "__iter__"):
            last_chunk: Any = None
            for chunk in response:
                last_chunk = chunk
                if isinstance(chunk, dict) and chunk.get("error"):
                    raise ModelResponseError(
                        str(chunk.get("message") or chunk.get("error")),
                        int(chunk.get("status_code") or 500),
                    )
            response = last_chunk
        if isinstance(response, dict) and response.get("error"):
            raise ModelResponseError(
                str(response.get("message") or response["error"]),
                int(response.get("status_code") or 500),
            )
        choices = response.get("choices", []) if isinstance(response, dict) else []
        if not choices:
            raise RuntimeError("model returned empty choices")
        content = choices[0].get("message", {}).get("content", "")
        if not isinstance(content, str) or not content:
            raise RuntimeError("model returned empty text")
        return content

    def _chat_response(self, request: AIGenerationRequest, messages: list[dict[str, Any]]) -> Any:
        return self._get_bot().call_with_tools(
            messages=messages,
            tools=None,
            model=request.model_name,
            temperature=request.temperature,
            stream=False,
        )

    def _chat_content(self, request: AIGenerationRequest, messages: list[dict[str, Any]]) -> str:
        for attempt in range(len(MODEL_RETRY_DELAYS_SECONDS) + 1):
            try:
                response = self._chat_response(request, messages)
                return self._content_from_response(response)
            except Exception as exc:
                if attempt >= len(MODEL_RETRY_DELAYS_SECONDS) or not self._is_transient_model_error(exc):
                    raise
                delay = MODEL_RETRY_DELAYS_SECONDS[attempt]
                if delay > 0:
                    time.sleep(delay)
        raise RuntimeError("model returned empty text")

    def _extract_image_text(self, request: AIGenerationRequest) -> str:
        image_blocks = self._image_blocks(request)
        if not image_blocks:
            return request.source_text
        text_parts = [
            "请读取上传图片中的投研资料，提取为可供后续整理的结构化原文。",
            "图片已经附在本条消息中，不要要求用户重新提供资料。",
            "附件文件：",
            *(f"- {path}" for path in request.source_files),
            "如果是利率择时图，请提取：标题、标的/合约、日期、最新收盘、复合策略信号、多头信号、空头信号、日度主线、周度变化、数据来源、业务对接。",
            "如果是可转债图，请提取：跟踪日期、跟踪维度、市场与风格表现、行业结构、错定价跟踪、实操指引、数据来源、业务对接。",
        ]
        if request.source_text.strip():
            text_parts.append(f"用户补充文本：\n{request.source_text.strip()}")
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "你是投研资料图片 OCR 与信息抽取助手。必须直接读取图片内容并输出结构化中文文本；"
                    "禁止输出“请提供原文”“请上传图片”“我无法查看图片”之类的索要资料话术。"
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "\n".join(text_parts)},
                    *image_blocks,
                ],
            },
        ]
        return self._chat_content(request, messages)

    def generate(self, request: AIGenerationRequest) -> str:
        image_blocks = self._image_blocks(request)
        if image_blocks:
            extracted_text = self._extract_image_text(request)
            user_message = {
                "role": "user",
                "content": (
                    "以下是上传图片的识别结果，请据此生成标准卡片文本。禁止要求用户再提供原文；"
                    f"缺失字段按系统要求填“——”。\n\n{extracted_text}"
                ),
            }
        else:
            user_message = self._build_user_message(request)
        return self._chat_content(
            request,
            [
                {"role": "system", "content": request.prompt},
                user_message,
            ],
        )


class BridgeModelAdapter(ExistingModelAdapter):
    """Backward-compatible name for the investment model adapter."""


MODEL_PROVIDER_CONFIG_KEYS = {
    "custom": ("custom_api_base", "custom_api_key"),
    "openai": ("open_ai_api_base", "open_ai_api_key"),
    "chatgpt": ("open_ai_api_base", "open_ai_api_key"),
    "open_ai": ("open_ai_api_base", "open_ai_api_key"),
    "deepseek": ("deepseek_api_base", "deepseek_api_key"),
    "qianfan": ("qianfan_api_base", "qianfan_api_key"),
    "claude": ("claude_api_base", "claude_api_key"),
    "claudeapi": ("claude_api_base", "claude_api_key"),
    "gemini": ("gemini_api_base", "gemini_api_key"),
    "zhipu_ai": ("zhipu_ai_api_base", "zhipu_ai_api_key"),
    "zhipu": ("zhipu_ai_api_base", "zhipu_ai_api_key"),
    "glm-4": ("zhipu_ai_api_base", "zhipu_ai_api_key"),
    "moonshot": ("moonshot_base_url", "moonshot_api_key"),
    "kimi": ("moonshot_base_url", "moonshot_api_key"),
    "qwen": ("dashscope_api_base", "dashscope_api_key"),
    "qwen_dashscope": ("dashscope_api_base", "dashscope_api_key"),
    "dashscope": ("dashscope_api_base", "dashscope_api_key"),
    "doubao": ("ark_base_url", "ark_api_key"),
    "ark": ("ark_base_url", "ark_api_key"),
    "minimax": ("minimax_api_base", "minimax_api_key"),
    "linkai": ("linkai_api_base", "linkai_api_key"),
}

MODEL_BOT_TYPE_MAP = {
    "text-davinci-003": const.OPEN_AI,
    "wenxin": const.BAIDU,
    "wenxin-4": const.BAIDU,
    "xunfei": const.XUNFEI,
    const.QWEN: const.QWEN_DASHSCOPE,
    const.QWEN_TURBO: const.QWEN_DASHSCOPE,
    const.QWEN_PLUS: const.QWEN_DASHSCOPE,
    const.QWEN_MAX: const.QWEN_DASHSCOPE,
    const.QIANFAN: const.QIANFAN,
    const.MOONSHOT: const.MOONSHOT,
    "moonshot-v1-8k": const.MOONSHOT,
    "moonshot-v1-32k": const.MOONSHOT,
    "moonshot-v1-128k": const.MOONSHOT,
    const.MODELSCOPE: const.MODELSCOPE,
}

MODEL_PREFIX_MAP = (
    ("qwen", const.QWEN_DASHSCOPE),
    ("qwq", const.QWEN_DASHSCOPE),
    ("qvq", const.QWEN_DASHSCOPE),
    ("gemini", const.GEMINI),
    ("glm", const.ZHIPU_AI),
    ("claude", const.CLAUDEAPI),
    ("moonshot", const.MOONSHOT),
    ("kimi", const.MOONSHOT),
    ("doubao", const.DOUBAO),
    ("deepseek", const.DEEPSEEK),
    ("ernie", const.QIANFAN),
)


def _resolve_global_provider(app_config: dict[str, Any]) -> str:
    if app_config.get("use_linkai") is True and app_config.get("linkai_api_key"):
        return const.LINKAI
    configured_provider = str(app_config.get("bot_type") or "")
    if configured_provider:
        return configured_provider

    model = app_config.get("model") or ""
    if not isinstance(model, str):
        model = str(model)
    if app_config.get("use_azure_chatgpt", False):
        return const.CHATGPTONAZURE
    if model in MODEL_BOT_TYPE_MAP:
        return MODEL_BOT_TYPE_MAP[model]
    lowered_model = model.lower()
    if lowered_model.startswith("minimax") or model in ("abab6.5-chat", "abab6.5"):
        return const.MiniMax
    for prefix, provider in MODEL_PREFIX_MAP:
        if lowered_model.startswith(prefix):
            return provider
    return const.OPENAI


def _normalize_api_base(provider: str, api_base: Any) -> str:
    value = str(api_base or "").rstrip("/")
    if provider.lower() == const.LINKAI and value and not value.endswith("/v1"):
        return f"{value}/v1"
    return value


def _global_model_config() -> dict[str, str | float]:
    app_config = config_service.conf()
    provider = _resolve_global_provider(app_config)
    base_key, api_key_key = MODEL_PROVIDER_CONFIG_KEYS.get(provider.lower(), ("custom_api_base", "custom_api_key"))
    api_base = app_config.get(base_key) if base_key else ""
    api_key = app_config.get(api_key_key) if api_key_key else ""
    return {
        "provider": provider,
        "model": str(app_config.get("model") or ""),
        "api_base": _normalize_api_base(provider, api_base),
        "api_key": str(api_key or ""),
        "temperature": float(app_config.get("temperature", 0.7) or 0.7),
    }


def default_prompt_for_service(service_type: ServiceType) -> str:
    defaults = {
        ServiceType.TECHNICAL_ANALYSIS: DEFAULT_TECHNICAL_ANALYSIS_PROMPT,
        ServiceType.RATE: DEFAULT_RATE_PROMPT,
        ServiceType.CONVERTIBLE_BOND: DEFAULT_CONVERTIBLE_BOND_PROMPT,
    }
    return defaults[service_type]


def _prompt_for_service(service_type: ServiceType) -> str:
    key = {
        ServiceType.TECHNICAL_ANALYSIS: "prompt.technical_analysis",
        ServiceType.RATE: "prompt.rate",
        ServiceType.CONVERTIBLE_BOND: "prompt.convertible_bond",
    }.get(service_type)
    configured = get_config(key, None) if key else None
    if isinstance(configured, str) and configured.strip():
        return configured
    if configured is not None and not isinstance(configured, str):
        return str(configured)
    return default_prompt_for_service(service_type)


def build_generation_request(
    service_type: ServiceType,
    source_text: str,
    *,
    source_files: list[str] | None = None,
) -> AIGenerationRequest:
    model_config = _global_model_config()
    return AIGenerationRequest(
        service_type=service_type,
        source_text=source_text,
        prompt=_prompt_for_service(service_type),
        source_files=list(source_files or []),
        model_provider=str(model_config["provider"]),
        model_name=str(model_config["model"]),
        api_base=str(model_config["api_base"]),
        api_key=str(model_config["api_key"]),
        temperature=float(model_config["temperature"]),
    )


def generate_standard_text(
    service_type: ServiceType,
    source_text: str,
    *,
    source_files: list[str] | None = None,
    adapter: ModelAdapter | None = None,
) -> AIGenerationResult:
    request = build_generation_request(service_type, source_text, source_files=source_files)
    try:
        text = normalize_generated_text(
            request.service_type,
            (adapter or ExistingModelAdapter()).generate(request),
            request.source_text,
        )
        return AIGenerationResult(
            True,
            text=text,
            prompt=request.prompt,
            service_type=request.service_type,
            source_text=request.source_text,
            model_params=request.safe_model_params,
            generated_text=text,
            status=Status.SUCCESS,
        )
    except Exception as exc:
        detail = str(exc)
        if request.api_key:
            detail = detail.replace(request.api_key, safe_log_value("model.api_key", request.api_key))
        detail = sanitize_sensitive_text(detail)
        return AIGenerationResult(
            False,
            error_code=ErrorCode.SYSTEM_ERROR,
            user_prompt=user_message(ErrorCode.SYSTEM_ERROR),
            detail=detail,
            prompt=request.prompt,
            service_type=request.service_type,
            source_text=request.source_text,
            model_params=request.safe_model_params,
            status=Status.FAILED,
            failure_reason=detail,
        )


def generate_technical_analysis_text(report_text: str, *, adapter: ModelAdapter | None = None) -> AIGenerationResult:
    return generate_standard_text(ServiceType.TECHNICAL_ANALYSIS, report_text, adapter=adapter)


def generate_rate_text(
    source_text: str,
    *,
    source_files: list[str] | None = None,
    adapter: ModelAdapter | None = None,
) -> AIGenerationResult:
    return generate_standard_text(ServiceType.RATE, source_text, source_files=source_files, adapter=adapter)


def generate_convertible_bond_text(
    source_text: str,
    *,
    source_files: list[str] | None = None,
    adapter: ModelAdapter | None = None,
) -> AIGenerationResult:
    return generate_standard_text(ServiceType.CONVERTIBLE_BOND, source_text, source_files=source_files, adapter=adapter)
