# encoding:utf-8
from dataclasses import dataclass, field
from typing import Any, Protocol

from .config_service import get_config, safe_log_value, sanitize_sensitive_text
from .constants import ErrorCode, ServiceType, Status, user_message


@dataclass
class AIGenerationRequest:
    service_type: ServiceType
    source_text: str
    prompt: str
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


class ExistingModelAdapter:
    def __init__(self, client: Any | None = None):
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        from models.openai.openai_http_client import get_default_client

        return get_default_client()

    def generate(self, request: AIGenerationRequest) -> str:
        response = self._get_client().chat_completions(
            api_key=request.api_key,
            api_base=request.api_base,
            model=request.model_name,
            messages=[
                {"role": "system", "content": request.prompt},
                {"role": "user", "content": request.source_text},
            ],
            temperature=request.temperature,
            stream=False,
        )
        if isinstance(response, dict) and response.get("error"):
            raise RuntimeError(response.get("message") or response["error"])
        choices = response.get("choices", []) if isinstance(response, dict) else []
        if not choices:
            raise RuntimeError("model returned empty choices")
        content = choices[0].get("message", {}).get("content", "")
        if not isinstance(content, str) or not content:
            raise RuntimeError("model returned empty text")
        return content


class BridgeModelAdapter(ExistingModelAdapter):
    """Backward-compatible name for the investment model adapter."""


def _prompt_for_service(service_type: ServiceType) -> str:
    key = {
        ServiceType.TECHNICAL_ANALYSIS: "prompt.technical_analysis",
        ServiceType.RATE: "prompt.rate",
        ServiceType.CONVERTIBLE_BOND: "prompt.convertible_bond",
    }.get(service_type)
    defaults = {
        ServiceType.TECHNICAL_ANALYSIS: "请将技术分析报告整理为信号卡片标准文本。",
        ServiceType.RATE: "请将利率资料整理为利率择时卡片标准文本。",
        ServiceType.CONVERTIBLE_BOND: "请将可转债资料整理为可转债多因子卡片标准文本。",
    }
    return str(get_config(key, defaults[service_type]) if key else defaults[service_type])


def build_generation_request(service_type: ServiceType, source_text: str) -> AIGenerationRequest:
    return AIGenerationRequest(
        service_type=service_type,
        source_text=source_text,
        prompt=_prompt_for_service(service_type),
        model_provider=str(get_config("model.provider", "")),
        model_name=str(get_config("model.name", "")),
        api_base=str(get_config("model.api_base", "")),
        api_key=str(get_config("model.api_key", "")),
        temperature=float(get_config("model.temperature", 0.7) or 0.7),
    )


def generate_standard_text(service_type: ServiceType, source_text: str, *, adapter: ModelAdapter | None = None) -> AIGenerationResult:
    request = build_generation_request(service_type, source_text)
    try:
        text = (adapter or ExistingModelAdapter()).generate(request)
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


def generate_rate_text(source_text: str, *, adapter: ModelAdapter | None = None) -> AIGenerationResult:
    return generate_standard_text(ServiceType.RATE, source_text, adapter=adapter)


def generate_convertible_bond_text(source_text: str, *, adapter: ModelAdapter | None = None) -> AIGenerationResult:
    return generate_standard_text(ServiceType.CONVERTIBLE_BOND, source_text, adapter=adapter)
