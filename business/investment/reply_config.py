# encoding:utf-8
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReplyTextDefinition:
    key: str
    label: str
    description: str
    default: str
    placeholders: tuple[str, ...] = ()


INVESTMENT_REPLY_DEFINITIONS = [
    ReplyTextDefinition("reply.investment.unauthorized", "未开通服务提示", "客户没有开通当前服务时返回。", "您暂未开通该服务，如需开通请联系服务人员。"),
    ReplyTextDefinition("reply.investment.user_disabled", "服务停用提示", "客户账号被停用时返回。", "您的服务已停用，如需恢复请联系服务人员。"),
    ReplyTextDefinition("reply.investment.auth_expired", "授权过期提示", "客户授权时间过期时返回。", "您的授权已过期，如需续期请联系服务人员。"),
    ReplyTextDefinition("reply.investment.input_error", "输入格式错误提示", "客户输入无法匹配服务格式时返回。", "请输入：股票代码/股票名称 + 技术分析，或输入“利率”“转债”。"),
    ReplyTextDefinition("reply.investment.stock_not_found", "未找到股票提示", "股票代码或名称没有匹配结果时返回。", "未匹配到该标的，请使用股票代码后重试，例如 300502.SZ、00700.HK、AAPL.US。"),
    ReplyTextDefinition("reply.investment.stock_ambiguous", "股票名称重复提示", "股票名称匹配多个标的时返回。", "股票名称匹配到多个标的，请改用股票代码。"),
    ReplyTextDefinition("reply.investment.technical_analysis_failed", "技术分析失败提示", "技术分析生成失败时返回。", "分析生成失败，请稍后重试或联系服务人员。"),
    ReplyTextDefinition("reply.investment.image_generation_failed", "图片生成失败提示", "图片生成或上传失败时返回。", "图片生成失败，请稍后重试或联系服务人员。"),
    ReplyTextDefinition("reply.investment.no_content", "当日内容未更新提示", "利率、转债等当日内容未准备好时返回。", "今日内容尚未更新，请稍后再试。"),
    ReplyTextDefinition("reply.investment.system_error", "系统繁忙提示", "系统异常兜底提示。", "系统暂时繁忙，请稍后重试。"),
]

WECHATMP_REPLY_DEFINITIONS = [
    ReplyTextDefinition("reply.wechatmp.immediate_ack", "收到请求提示", "客户触发需要等待的业务后立即返回。保留 `{pending_summary}`，系统会替换为待领取摘要。", "收到，正在处理，请稍候。请等待30-40s后回复1获取\n{pending_summary}", ("pending_summary",)),
    ReplyTextDefinition("reply.wechatmp.pending_summary", "待领取内容摘要", "客户有技术分析结果待领取时追加返回。保留 `{items}`，系统会替换为股票列表。", "您当前还有技术分析结果待领取：\n{items}\n回复1获取或回复股票名称获取对应报告", ("items",)),
    ReplyTextDefinition("reply.wechatmp.pending_result_invalidated", "待领取内容失效提示", "客户领取结果时，原内容或缓存已失效时返回。", "内容已失效，请重新发起请求。"),
    ReplyTextDefinition("reply.wechatmp.running_technical_analysis", "技术分析仍在运行提示", "客户在技术分析仍运行时回复 1。保留 `{}`，系统会替换为股票或标题。", "「{}」技术分析仍在运行中，请稍后再回复 1 尝试获取。", ("target",)),
    ReplyTextDefinition("reply.wechatmp.technical_running_new_request", "运行中重复技术分析提示", "客户已有技术分析运行中又发起新的技术分析时返回。保留 `{running_title}`，系统会替换为正在运行的股票或标题。", "「{running_title}」技术分析仍在运行中，请稍后回复1获取结果。\n当前暂不接受新的技术分析请求，请在结果领取后再发起新的技术分析。", ("running_title",)),
    ReplyTextDefinition("reply.wechatmp.technical_ready", "技术分析可领取提示", "客户发起技术分析时，结果已准备好可直接领取时返回。保留 `{target}`，系统会替换为股票或标题。", "「{target}」技术分析结果已准备好，回复1获取。", ("target",)),
    ReplyTextDefinition("reply.wechatmp.pending_technical_analysis", "技术分析待领取提示", "客户有技术分析结果待领取又输入新内容时返回。保留 `{}`，系统会替换为股票或标题。", "「{}」技术分析已生成完成，回复 1 获取技术分析主图、技术指标表。", ("target",)),
    ReplyTextDefinition("reply.wechatmp.thinking_timeout", "微信重试超时提示", "微信第三次请求时后台仍未完成时返回。", "【正在思考中，回复任意文字尝试获取回复】"),
    ReplyTextDefinition("reply.wechatmp.chat_prefix_hint", "聊天前缀提示", "系统设置聊天前缀时，引导客户按前缀输入。保留 `{}`，系统会替换为前缀。", "请输入'{}'接你想说的话跟我说话。\n例如:\n{}你好，很高兴见到你。", ("prefix", "prefix")),
    ReplyTextDefinition("reply.wechatmp.default_chat_hint", "普通聊天引导提示", "没有聊天前缀时的默认聊天引导。", "你好，很高兴见到你。\n请跟我说话吧。"),
    ReplyTextDefinition("reply.wechatmp.unknown_error", "公众号未知错误提示", "公众号链路兜底错误提示。", "未知错误，请稍后再试"),
]

REPLY_TEXT_GROUPS = [
    {"title": "投资业务错误提示", "keys": [item.key for item in INVESTMENT_REPLY_DEFINITIONS]},
    {"title": "公众号处理状态", "keys": [item.key for item in WECHATMP_REPLY_DEFINITIONS]},
]

REPLY_TEXT_DEFINITIONS = {
    item.key: item
    for item in [*INVESTMENT_REPLY_DEFINITIONS, *WECHATMP_REPLY_DEFINITIONS]
}


def reply_config_fallback_keys() -> dict[str, str]:
    return {key: key for key in REPLY_TEXT_DEFINITIONS}


def default_reply_text(key: str, default: str = "") -> str:
    definition = REPLY_TEXT_DEFINITIONS.get(key)
    return definition.default if definition else default


def get_reply_text(key: str, default: str = "") -> str:
    from .config_service import get_config

    configured = get_config(key, None)
    if configured is None or str(configured) == "":
        return default_reply_text(key, default)
    return str(configured)


def format_reply_text(key: str, *args: Any, default: str = "") -> str:
    text = get_reply_text(key, default)
    if not args:
        return text
    try:
        return text.format(*args)
    except Exception:
        return default_reply_text(key, default).format(*args)


def reply_text_config_metadata() -> dict[str, Any]:
    return {
        "groups": REPLY_TEXT_GROUPS,
        "definitions": {
            key: {
                "label": definition.label,
                "description": definition.description,
                "default": definition.default,
                "placeholders": list(definition.placeholders),
            }
            for key, definition in REPLY_TEXT_DEFINITIONS.items()
        },
    }
