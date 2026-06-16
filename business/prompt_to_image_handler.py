# encoding:utf-8
"""Generic on-demand prompt-to-image module handler."""

from typing import Any

from business.business_records import create_business_record, mark_business_failed, mark_business_success
from business.config_service import get_config, sanitize_sensitive_text
from business.constants import ErrorCode, ServiceType, user_message
from business.investment.render_service import RenderRequest, render_card


DEFAULT_PROMPT_TO_IMAGE_PROMPT = (
    "请将用户提供的投研需求或资料整理为可直接渲染为图片卡片的标准中文文本。"
    "只输出卡片正文，不要输出解释、模板说明、补充问题或 Markdown 代码块。"
)

DEFAULT_PROMPT_TO_IMAGE_TEMPLATE_PROMPTS = {
    "rate": (
        "请将用户提供的投研需求或资料整理为利率择时图片卡片标准文本。"
        "必须只输出卡片正文，不要输出解释、模板说明、补充问题或 Markdown 代码块。"
        "输出必须包含并使用以下栏目和字段："
        "【浙商固收 | 智能投研辅助系统】、标的、最新收盘、行情日期、分析模型、"
        "当日核心信号、复合策略信号、多头：...；空头：...、日度主线、"
        "周度全景复盘、近一周整体信号、周度主线、授权剩余时间、业务对接。"
        "无法从资料识别的字段填“——”。"
    ),
    "convertible_bond": (
        "请将用户提供的投研需求或资料整理为可转债多因子图片卡片标准文本。"
        "必须只输出卡片正文，不要输出解释、模板说明、补充问题或 Markdown 代码块。"
        "输出必须包含：跟踪日期、分析模型、跟踪维度、市场与风格表现、行业结构、"
        "错定价跟踪、实操指引、授权剩余时间、数据来源、业务对接。"
        "无法从资料识别的字段填“——”。"
    ),
    "technical_analysis": (
        "请将用户提供的投研需求或资料整理为技术分析图片卡片标准文本。"
        "必须只输出卡片正文，不要输出解释、模板说明、补充问题或 Markdown 代码块。"
        "输出必须包含：标的、最新收盘、行情日期、分析模型、信号方向、趋势研判、"
        "核心关键位、实操指引、授权剩余时间、业务对接。"
        "无法从资料识别的字段填“——”。"
    ),
}


def _image_reply(paths: list[str]) -> str:
    return "\n".join(f"[图片: {path}]" for path in paths)


def _normalize_template_key(template_key: str) -> str:
    return str(template_key or "").strip().lower().replace("-", "_")


def _configured_prompt(prompt_key: str, *, template_key: str = "") -> str:
    configured = get_config(prompt_key, None) if prompt_key else None
    if isinstance(configured, str) and configured.strip():
        return configured
    if configured is not None and not isinstance(configured, str):
        return str(configured)
    template_prompt = DEFAULT_PROMPT_TO_IMAGE_TEMPLATE_PROMPTS.get(_normalize_template_key(template_key))
    if template_prompt:
        return template_prompt
    return DEFAULT_PROMPT_TO_IMAGE_PROMPT


def _module_generation_result(service_type: ServiceType, source_text: str, source_files: list[str], prompt_key: str, template_key: str = ""):
    from business.investment.ai_generation import AIGenerationRequest, ExistingModelAdapter, AIGenerationResult
    from business.investment.ai_generation import _global_model_config, normalize_generated_text
    from business.investment.constants import Status

    model_config = _global_model_config()
    request = AIGenerationRequest(
        service_type=service_type,
        source_text=source_text,
        prompt=_configured_prompt(prompt_key, template_key=template_key),
        source_files=list(source_files or []),
        model_provider=str(model_config["provider"]),
        model_name=str(model_config["model"]),
        api_base=str(model_config["api_base"]),
        api_key=str(model_config["api_key"]),
        temperature=float(model_config["temperature"]),
    )
    try:
        text = normalize_generated_text(request.service_type, ExistingModelAdapter().generate(request))
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
        detail = sanitize_sensitive_text(str(exc))
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


def generate_standard_text_for_module(
    service_type: ServiceType,
    source_text: str,
    source_files: list[str] | None = None,
    prompt_key: str = "",
    module_key: str = "",
    template_key: str = "",
):
    from business.investment.ai_generation import generate_standard_text

    try:
        return generate_standard_text(
            service_type,
            source_text,
            source_files=source_files,
            prompt_key=prompt_key,
            module_key=module_key,
        )
    except TypeError as exc:
        if "prompt_key" not in str(exc) and "module_key" not in str(exc):
            raise
        return _module_generation_result(service_type, source_text, list(source_files or []), prompt_key, template_key)
    except KeyError:
        return _module_generation_result(service_type, source_text, list(source_files or []), prompt_key, template_key)


def _result_success(result: Any) -> bool:
    return bool(getattr(result, "success", False))


def _output_files(render_result: Any) -> list[str]:
    paths = list(getattr(render_result, "output_files", []) or [])
    if not paths and getattr(render_result, "image_path", ""):
        paths = [getattr(render_result, "image_path")]
    return [str(path) for path in paths if str(path)]


def handle_prompt_to_image(
    openid: str,
    raw_input: str,
    route,
    *,
    definition,
    customer_metadata: dict[str, str] | None = None,
    elapsed=lambda: 0,
):
    from business.router import BusinessReply

    customer_metadata = customer_metadata or {}
    module_key = str(getattr(definition, "business_key", "") or getattr(route, "module_key", "") or "")
    service_type = getattr(definition, "service_type", None) or route.service_type
    request_id = create_business_record(
        openid,
        raw_input,
        service_type,
        customer_name=customer_metadata.get("customer_name", ""),
        institution=customer_metadata.get("institution", ""),
    )
    source_text = str(getattr(route, "target_text", "") or raw_input)

    try:
        ai_result = generate_standard_text_for_module(
            service_type,
            source_text,
            source_files=[],
            prompt_key=getattr(definition, "prompt_key", ""),
            module_key=module_key,
            template_key=getattr(definition, "template_key", ""),
        )
        if not _result_success(ai_result):
            code = getattr(ai_result, "error_code", None) or ErrorCode.SYSTEM_ERROR
            prompt = getattr(ai_result, "user_prompt", "") or user_message(code)
            detail = sanitize_sensitive_text(getattr(ai_result, "detail", ""))
            mark_business_failed(request_id, code, prompt, detail, elapsed())
            return BusinessReply(True, False, prompt, [], service_type, code, prompt, detail, request_id, module_key=module_key)

        render_result = render_card(
            RenderRequest(
                service_type=service_type,
                standard_text=str(getattr(ai_result, "text", "")),
                template_key=getattr(definition, "template_key", ""),
            )
        )
        if not _result_success(render_result):
            code = getattr(render_result, "error_code", None) or ErrorCode.IMAGE_GENERATION_FAILED
            prompt = getattr(render_result, "user_prompt", "") or user_message(code)
            detail = sanitize_sensitive_text(getattr(render_result, "detail", ""))
            mark_business_failed(request_id, code, prompt, detail, elapsed())
            return BusinessReply(True, False, prompt, [], service_type, code, prompt, detail, request_id, module_key=module_key)

        output_files = _output_files(render_result)
        mark_business_success(
            request_id,
            output_files=output_files,
            elapsed_ms=elapsed(),
            artifact_roles={path: "output_image" for path in output_files},
        )
        return BusinessReply(
            True,
            True,
            _image_reply(output_files),
            output_files,
            service_type,
            request_id=request_id,
            source_type="request",
            source_id=request_id,
            module_key=module_key,
        )
    except Exception as exc:
        detail = sanitize_sensitive_text(str(exc))
        prompt = user_message(ErrorCode.SYSTEM_ERROR)
        mark_business_failed(request_id, ErrorCode.SYSTEM_ERROR, prompt, detail, elapsed())
        return BusinessReply(
            True,
            False,
            prompt,
            [],
            service_type,
            ErrorCode.SYSTEM_ERROR,
            prompt,
            detail,
            request_id,
            module_key=module_key,
        )
