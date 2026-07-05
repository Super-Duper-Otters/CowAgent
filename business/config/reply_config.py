# encoding:utf-8
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from business.config.wechat_rich_text import (
    CUSTOM_RICH_ACTIONS_CONFIG_KEY,
    normalize_rich_text_template,
    render_rich_text_template,
    reply_rich_action_metadata,
    rich_text_template_action_ids,
)


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
    ReplyTextDefinition("reply.investment.activation_success", "激活成功提示", "客户使用 ANAL 激活码成功后返回。保留 `{auth_end_at}`，系统会替换为授权结束日期。", "激活成功，服务有效期至 {auth_end_at}。", ("auth_end_at",)),
    ReplyTextDefinition("reply.investment.activation_invalid", "激活码无效提示", "客户输入 ANAL 开头但不存在或格式不正确时返回。", "激活失败：激活码不存在或格式不正确。"),
    ReplyTextDefinition("reply.investment.activation_used", "激活码已使用提示", "客户输入已被兑换的激活码时返回。", "激活失败：该激活码已被使用。"),
    ReplyTextDefinition("reply.investment.activation_expired", "激活码过期提示", "客户输入已超过激活码有效期的激活码时返回。", "激活失败：该激活码已过期。"),
    ReplyTextDefinition("reply.investment.activation_disabled", "激活码停用提示", "客户输入后台已停用的激活码时返回。", "激活失败：该激活码已停用。"),
    ReplyTextDefinition("reply.investment.activation_already_bound", "激活码已绑定提示", "预登记客户已绑定其他微信时返回。", "激活失败：该客户已绑定其他微信，请联系管理员处理。"),
    ReplyTextDefinition(
        "reply.investment.input_error",
        "输入格式错误提示",
        "客户输入无法匹配服务格式时返回。",
        "请输入以下格式之一：\n"
        "1. 技术分析：输入 #股票代码/名称，例如 #000300.SH\n"
        "2. 利率\n"
        "3. 转债",
    ),
    ReplyTextDefinition("reply.investment.running", "业务运行中提示", "业务请求已在运行中时返回。", "正在运行，请稍候。"),
    ReplyTextDefinition("reply.investment.stock_not_found", "未找到标的兜底提示", "股票代码或名称没有命中任何动态提示时返回；技术分析候选提示优先使用“技术分析动态提示”分组。", "未匹配到该标的，请使用完整代码重试，例如 #300502.SZ。"),
    ReplyTextDefinition("reply.investment.stock_ambiguous", "标的重复兜底提示", "名称或代码匹配多个标的但没有候选列表可展示时返回；有候选结果时优先使用动态富文本列表。", "匹配到多个标的，请点击候选项或改用完整代码。"),
    ReplyTextDefinition("reply.investment.market_data_unavailable", "行情数据异常提示", "标的已进入分析流程但行情数据源接口异常、网络异常或暂时不可用时返回。", "行情数据暂时不可用，请稍后重试。"),
    ReplyTextDefinition("reply.investment.market_history_insufficient", "行情历史不足提示", "标的行情存在但历史K线不足，暂不满足技术分析生成条件时返回。", "该标的近期行情数据暂不完整，暂无法生成技术分析，请更换标的或稍后重试。"),
    ReplyTextDefinition("reply.investment.market_data_stale", "行情数据过旧提示", "标的行情最新日期超过交易日历允许滞后范围，暂不满足技术分析生成条件时返回。", "该标的行情数据近期未更新，暂无法生成技术分析，请更换标的或稍后重试。"),
    ReplyTextDefinition("reply.investment.technical_analysis_failed", "技术分析失败提示", "技术分析生成失败时返回。", "分析生成失败，请稍后重试或联系服务人员。"),
    ReplyTextDefinition("reply.investment.image_generation_failed", "图片生成失败提示", "图片生成或上传失败时返回。", "图片生成失败，请稍后重试或联系服务人员。"),
    ReplyTextDefinition("reply.investment.no_content", "当日内容未更新提示", "利率、转债等当日内容未准备好时返回。", "今日内容尚未更新，请稍后再试。"),
    ReplyTextDefinition("reply.investment.system_error", "系统繁忙提示", "系统异常兜底提示。", "系统暂时繁忙，请稍后重试。"),
]

WECHATMP_REPLY_DEFINITIONS = [
    ReplyTextDefinition("reply.wechatmp.immediate_ack", "收到请求提示", "客户触发需要等待的业务后立即返回。保留 `{pending_summary}`，系统会替换为待领取摘要。", "收到，正在处理，请稍候。请等待30-40s后{{action:get_result}}\n{pending_summary}", ("pending_summary",)),
    ReplyTextDefinition("reply.wechatmp.pending_summary", "待领取内容摘要", "客户有技术分析结果待领取时追加返回。保留 `{items}`，系统会替换为可直接点击的富文本股票列表。", "您当前还有技术分析结果待领取：\n{items}", ("items",)),
    ReplyTextDefinition("reply.wechatmp.pending_result_invalidated", "待领取内容失效提示", "客户领取结果时，原内容或缓存已失效时返回。", "内容已失效，请重新发起请求。"),
    ReplyTextDefinition("reply.wechatmp.running_technical_analysis", "技术分析仍在运行提示", "客户在技术分析仍运行时回复 1。保留 `{target}`，系统会替换为股票或标题。", "「{target}」技术分析仍在运行中，请稍后再{{action:get_result_short}}尝试获取。", ("target",)),
    ReplyTextDefinition("reply.wechatmp.technical_running_new_request", "运行中重复技术分析提示", "客户已有技术分析运行中又发起新的技术分析时返回。保留 `{running_title}`，系统会替换为正在运行的股票或标题。", "「{running_title}」技术分析仍在运行中，请稍后{{action:get_result}}。\n当前暂不接受新的技术分析请求，请在结果领取后再发起新的技术分析。", ("running_title",)),
    ReplyTextDefinition("reply.wechatmp.technical_ready", "技术分析可领取提示", "客户发起技术分析时，结果已准备好可直接领取时返回。保留 `{target}`，系统会替换为股票或标题。", "「{target}」技术分析结果已准备好，{{action:get_result}}。", ("target",)),
    ReplyTextDefinition("reply.wechatmp.pending_technical_analysis", "技术分析待领取提示", "客户有技术分析结果待领取又输入新内容时返回。保留 `{target}`，系统会替换为股票或标题。", "「{target}」技术分析已生成完成，{{action:get_result_short}}获取技术分析主图、技术指标表。", ("target",)),
    ReplyTextDefinition("reply.wechatmp.thinking_timeout", "微信重试超时提示", "微信第三次请求时后台仍未完成时返回。", "【正在思考中，回复任意文字尝试获取回复】"),
    ReplyTextDefinition("reply.wechatmp.chat_prefix_hint", "聊天前缀提示", "系统设置聊天前缀时，引导客户按前缀输入。保留 `{prefix}`，系统会替换为前缀。", "请输入'{}'接你想说的话跟我说话。\n例如:\n{}你好，很高兴见到你。", ("prefix",)),
    ReplyTextDefinition("reply.wechatmp.default_chat_hint", "普通聊天引导提示", "没有聊天前缀时的默认聊天引导。", "你好，很高兴见到你。\n请跟我说话吧。"),
    ReplyTextDefinition("reply.wechatmp.unknown_error", "公众号未知错误提示", "公众号链路兜底错误提示。", "未知错误，请稍后再试"),
    ReplyTextDefinition("reply.wechatmp.system_error", "公众号系统异常提示", "公众号入口发生异常时返回。", "系统暂时繁忙，请稍后重试。"),
    ReplyTextDefinition("reply.wechatmp.unsupported_message", "不支持消息类型提示", "客户发送公众号暂不处理的消息类型时返回。", "暂不支持该消息类型，请发送文字、语音或图片。"),
    ReplyTextDefinition("reply.wechatmp.continue_prompt", "长文本续取提示", "公众号回复超过单条长度限制时追加在本条末尾。", "\n【未完待续，回复任意文字以继续】"),
    ReplyTextDefinition("reply.wechatmp.media_read_failed", "媒体读取失败提示", "公众号读取本地或远程媒体失败时返回。", "媒体读取失败，请稍后重试或联系服务人员。"),
    ReplyTextDefinition("reply.wechatmp.media_upload_failed", "媒体上传失败提示", "公众号上传图片、语音或视频到微信失败时返回。", "媒体上传失败，请稍后重试或联系服务人员。"),
    ReplyTextDefinition("reply.wechatmp.active_immediate_ack", "主动模式收到请求提示", "公众号主动客服模式收到请求后立即返回。", "收到，正在运行，请稍候。"),
    ReplyTextDefinition("reply.wechatmp.active_waiting", "主动模式运行中提示", "公众号主动客服模式已有任务运行中时返回。", "正在运行，请稍候。"),
]

TECHNICAL_ANALYSIS_REPLY_DEFINITIONS = [
    ReplyTextDefinition(
        "reply.technical_analysis.stock_name_ambiguous",
        "股票名称重复候选提示",
        "股票名称匹配多个标的时返回。保留 `{target}`、`{candidate_list}`。",
        "股票名称“{target}”匹配到多个标的，请点击候选项：\n{candidate_list}",
        ("target", "candidate_list"),
    ),
    ReplyTextDefinition(
        "reply.technical_analysis.bare_code_index_suggestion",
        "裸代码指数建议提示",
        "裸数字代码没有匹配个股但匹配指数时返回。保留 `{target}`、`{name}`、`{candidate}`、`{candidate_list}`。",
        "未找到 {target} 对应的个股。若您要分析指数“{name}”，请点击：{candidate}",
        ("target", "name", "candidate", "candidate_list"),
    ),
    ReplyTextDefinition(
        "reply.technical_analysis.bare_code_index_candidates",
        "裸代码指数多候选提示",
        "裸数字代码没有匹配个股但匹配多个指数时返回。保留 `{target}`、`{candidate_list}`。",
        "未找到 {target} 对应的个股。若您要分析指数，请点击候选项：\n{candidate_list}",
        ("target", "candidate_list"),
    ),
    ReplyTextDefinition(
        "reply.technical_analysis.bare_code_ambiguous",
        "裸代码多标的提示",
        "同一裸代码匹配多个标的时返回。保留 `{target}`、`{candidate_list}`。",
        "代码 {target} 匹配到多个标的，请点击候选项：\n{candidate_list}",
        ("target", "candidate_list"),
    ),
    ReplyTextDefinition(
        "reply.technical_analysis.bare_code_candidates",
        "裸代码非A股候选提示",
        "裸数字代码没有匹配 A 股但匹配其他类型标的时返回。保留 `{target}`、`{candidate_list}`。",
        "代码 {target} 未匹配到 A 股。若您要分析以下标的，请点击候选项：\n{candidate_list}",
        ("target", "candidate_list"),
    ),
    ReplyTextDefinition(
        "reply.technical_analysis.unknown_bare_code",
        "未知裸代码提示",
        "裸数字代码没有匹配个股或指数时返回。保留 `{target}`、`{example}`。",
        "未找到 {target} 对应的个股或指数，请检查代码，或点击示例 {example}。",
        ("target", "example"),
    ),
    ReplyTextDefinition(
        "reply.technical_analysis.csi_symbol_suggestion",
        "CSI 指数代码建议提示",
        "CSI 指数缺少前缀时返回。保留 `{target}`、`{suggestion}`。",
        "未找到 {target} 对应标的。若您要分析 CSI 指数，请点击：{suggestion}",
        ("target", "suggestion"),
    ),
]

REPLY_TEXT_GROUPS = [
    {"title": "投资业务错误提示", "keys": [item.key for item in INVESTMENT_REPLY_DEFINITIONS]},
    {"title": "技术分析动态提示", "keys": [item.key for item in TECHNICAL_ANALYSIS_REPLY_DEFINITIONS]},
    {"title": "公众号处理状态", "keys": [item.key for item in WECHATMP_REPLY_DEFINITIONS]},
]

REPLY_TEXT_DEFINITIONS = {
    item.key: item
    for item in [*INVESTMENT_REPLY_DEFINITIONS, *TECHNICAL_ANALYSIS_REPLY_DEFINITIONS, *WECHATMP_REPLY_DEFINITIONS]
}


def reply_config_fallback_keys() -> dict[str, str]:
    return {**{key: key for key in REPLY_TEXT_DEFINITIONS}, CUSTOM_RICH_ACTIONS_CONFIG_KEY: CUSTOM_RICH_ACTIONS_CONFIG_KEY}


def default_reply_template(key: str, default: str = "") -> str:
    dynamic = _dynamic_default_reply_template(key)
    if dynamic:
        return dynamic
    definition = REPLY_TEXT_DEFINITIONS.get(key)
    return definition.default if definition else default


def _dynamic_default_reply_template(key: str) -> str:
    if key == "reply.investment.input_error":
        return (
            "请输入以下格式之一：\n"
            "1. 技术分析：输入当前触发词 + 股票代码/名称，例如 {{action:technical_analysis_example}}\n"
            "2. {{action:rate_tracking}}\n"
            "3. {{action:convertible_bond_tracking}}"
        )
    if key == "reply.investment.stock_not_found":
        return "未匹配到该标的，请使用完整代码重试，例如 {{action:stock_not_found_example}}。"
    if key == "reply.wechatmp.immediate_ack":
        return "收到，正在处理，请稍候。请等待30-40s后{{action:get_result}}\n{pending_summary}"
    if key == "reply.wechatmp.pending_summary":
        return "您当前还有技术分析结果待领取：\n{items}"
    if key == "reply.wechatmp.running_technical_analysis":
        return "「{target}」技术分析仍在运行中，请稍后再{{action:get_result_short}}尝试获取。"
    if key == "reply.wechatmp.technical_running_new_request":
        return "「{running_title}」技术分析仍在运行中，请稍后{{action:get_result}}。\n当前暂不接受新的技术分析请求，请在结果领取后再发起新的技术分析。"
    if key == "reply.wechatmp.technical_ready":
        return "「{target}」技术分析结果已准备好，{{action:get_result}}。"
    if key == "reply.wechatmp.pending_technical_analysis":
        return "「{target}」技术分析已生成完成，{{action:get_result_short}}获取技术分析主图、技术指标表。"
    return ""


def render_reply_template(template: str) -> str:
    return render_rich_text_template(template)


def default_reply_text(key: str, default: str = "") -> str:
    return render_reply_template(default_reply_template(key, default))


def get_reply_template(key: str, default: str = "") -> str:
    from config import conf
    from sqlalchemy import select

    from business.config.config_service import CONFIG_FALLBACK_KEYS, _deserialize
    from business.schema.db import connect, row_to_dict
    from business.schema.tables import investment_configs

    with connect() as conn:
        row = conn.execute(
            select(investment_configs.c.config_value).where(investment_configs.c.config_key == key),
        ).fetchone()
    configured = _deserialize(row_to_dict(row)["config_value"]) if row else None
    if configured is None:
        fallback_key = CONFIG_FALLBACK_KEYS.get(key, key)
        configured = conf().get(fallback_key, None)
    if configured is None or str(configured) == "":
        return default_reply_template(key, default)
    return normalize_rich_text_template(str(configured))


def get_reply_text(key: str, default: str = "") -> str:
    return render_reply_template(get_reply_template(key, default))


def format_reply_text(key: str, *args: Any, default: str = "", **kwargs: Any) -> str:
    text = get_reply_text(key, default)
    if not args and not kwargs:
        return text
    try:
        return text.format(*args, **kwargs)
    except Exception:
        return default_reply_text(key, default).format(*args, **kwargs)


def reply_text_config_metadata() -> dict[str, Any]:
    all_actions = reply_rich_action_metadata()
    return {
        "groups": REPLY_TEXT_GROUPS,
        "rich_actions": all_actions,
        "definitions": {
            key: _reply_text_definition_metadata(key, definition)
            for key, definition in REPLY_TEXT_DEFINITIONS.items()
        },
    }


def _reply_text_definition_metadata(key: str, definition: ReplyTextDefinition) -> dict[str, Any]:
    default_template = default_reply_template(key, definition.default)
    action_ids = rich_text_template_action_ids(default_template)
    return {
        "label": definition.label,
        "description": definition.description,
        "default_template": default_template,
        "default": render_reply_template(default_template),
        "rendered_preview": render_reply_template(default_template),
        "placeholders": list(definition.placeholders),
        "placeholder_details": _placeholder_details(definition.placeholders),
        "rich_actions": reply_rich_action_metadata(action_ids),
    }


def _placeholder_details(placeholders: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    return {name: _placeholder_detail(name) for name in placeholders}


def _placeholder_detail(name: str) -> dict[str, Any]:
    rich_placeholders = {
        "items": ("rich_text_list", "待领取富文本列表"),
        "candidate_list": ("rich_text_list", "候选富文本列表"),
        "candidate": ("rich_text", "候选富文本"),
        "suggestion": ("rich_text", "建议富文本"),
        "example": ("rich_text", "示例富文本"),
    }
    if name in rich_placeholders:
        kind, display_text = rich_placeholders[name]
        return {
            "name": name,
            "kind": kind,
            "display_text": display_text,
            "token": f"{{{name}}}",
            "dynamic": True,
        }
    return {
        "name": name,
        "kind": "text",
        "display_text": name,
        "token": f"{{{name}}}",
        "dynamic": True,
    }
