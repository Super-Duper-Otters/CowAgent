# encoding:utf-8
from enum import StrEnum


class ServiceType(StrEnum):
    TECHNICAL_ANALYSIS = "technical_analysis"
    RATE = "rate"
    CONVERTIBLE_BOND = "convertible_bond"
    UNAUTHORIZED_REQUEST = "unauthorized_request"
    UNMATCHED = "unmatched"
    ALL = "all"


CUSTOMER_SERVICE_TYPES = (
    ServiceType.TECHNICAL_ANALYSIS,
    ServiceType.RATE,
    ServiceType.CONVERTIBLE_BOND,
)


SERVICE_LABELS = {
    ServiceType.TECHNICAL_ANALYSIS: "技术分析",
    ServiceType.RATE: "利率",
    ServiceType.CONVERTIBLE_BOND: "转债",
    ServiceType.UNAUTHORIZED_REQUEST: "无权限请求",
    ServiceType.ALL: "全部",
}

SERVICE_ALIASES = {
    "technical_analysis": ServiceType.TECHNICAL_ANALYSIS,
    "技术分析": ServiceType.TECHNICAL_ANALYSIS,
    "rate": ServiceType.RATE,
    "利率": ServiceType.RATE,
    "convertible_bond": ServiceType.CONVERTIBLE_BOND,
    "转债": ServiceType.CONVERTIBLE_BOND,
    "cb": ServiceType.CONVERTIBLE_BOND,
    "unauthorized_request": ServiceType.UNAUTHORIZED_REQUEST,
    "无权限请求": ServiceType.UNAUTHORIZED_REQUEST,
    "all": ServiceType.ALL,
    "全部": ServiceType.ALL,
}


class Status(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    DRAFT = "draft"
    GENERATING = "generating"
    GENERATED = "generated"
    GENERATE_FAILED = "generate_failed"
    EFFECTIVE = "effective"
    ARCHIVED = "archived"


class ErrorCode(StrEnum):
    UNAUTHORIZED = "unauthorized"
    USER_DISABLED = "user_disabled"
    AUTH_EXPIRED = "auth_expired"
    INPUT_ERROR = "input_error"
    STOCK_NOT_FOUND = "stock_not_found"
    STOCK_AMBIGUOUS = "stock_ambiguous"
    TECHNICAL_ANALYSIS_FAILED = "technical_analysis_failed"
    IMAGE_GENERATION_FAILED = "image_generation_failed"
    NO_CONTENT = "no_content"
    SYSTEM_ERROR = "system_error"


USER_MESSAGES = {
    ErrorCode.UNAUTHORIZED: "您暂未开通该服务，如需开通请联系服务人员。",
    ErrorCode.USER_DISABLED: "您的服务已停用，如需恢复请联系服务人员。",
    ErrorCode.AUTH_EXPIRED: "您的授权已过期，如需续期请联系服务人员。",
    ErrorCode.INPUT_ERROR: "请输入：股票代码/股票名称 + 技术分析，或输入“利率”“转债”。",
    ErrorCode.STOCK_NOT_FOUND: "未找到对应标的，请检查股票代码或改用标准股票代码。",
    ErrorCode.STOCK_AMBIGUOUS: "股票名称匹配到多个标的，请改用股票代码。",
    ErrorCode.TECHNICAL_ANALYSIS_FAILED: "分析生成失败，请稍后重试或联系服务人员。",
    ErrorCode.IMAGE_GENERATION_FAILED: "图片生成失败，请稍后重试或联系服务人员。",
    ErrorCode.NO_CONTENT: "今日内容尚未更新，请稍后再试。",
    ErrorCode.SYSTEM_ERROR: "系统暂时繁忙，请稍后重试。",
}

USER_MESSAGE_CONFIG_KEYS = {
    ErrorCode.UNAUTHORIZED: "reply.investment.unauthorized",
    ErrorCode.USER_DISABLED: "reply.investment.user_disabled",
    ErrorCode.AUTH_EXPIRED: "reply.investment.auth_expired",
    ErrorCode.INPUT_ERROR: "reply.investment.input_error",
    ErrorCode.STOCK_NOT_FOUND: "reply.investment.stock_not_found",
    ErrorCode.STOCK_AMBIGUOUS: "reply.investment.stock_ambiguous",
    ErrorCode.TECHNICAL_ANALYSIS_FAILED: "reply.investment.technical_analysis_failed",
    ErrorCode.IMAGE_GENERATION_FAILED: "reply.investment.image_generation_failed",
    ErrorCode.NO_CONTENT: "reply.investment.no_content",
    ErrorCode.SYSTEM_ERROR: "reply.investment.system_error",
}


def normalize_service(value: str | ServiceType) -> ServiceType:
    if isinstance(value, ServiceType):
        return value
    normalized = str(value or "").strip()
    return SERVICE_ALIASES.get(normalized, SERVICE_ALIASES.get(normalized.lower(), ServiceType.UNMATCHED))


def user_message(error_code: ErrorCode) -> str:
    default = USER_MESSAGES.get(error_code, USER_MESSAGES[ErrorCode.SYSTEM_ERROR])
    key = USER_MESSAGE_CONFIG_KEYS.get(error_code, USER_MESSAGE_CONFIG_KEYS[ErrorCode.SYSTEM_ERROR])
    try:
        from .reply_config import get_reply_text

        return get_reply_text(key, default)
    except Exception:
        return default
