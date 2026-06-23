# encoding:utf-8
"""Executor for runtime active prompt investment components."""

from dataclasses import dataclass
from typing import Any

from business.audit.ai_generation import AIGenerationRequest, ExistingModelAdapter, ModelAdapter, _global_model_config
from business.config.config_service import sanitize_sensitive_text
from business.config.constants import ErrorCode, ServiceType, user_message


@dataclass
class PromptComponentRunResult:
    success: bool
    reply_text: str = ""
    output_type: str = "markdown"
    error_code: ErrorCode | None = None
    user_prompt: str = ""
    detail: str = ""


def _render_prompt(template: str, variables: dict[str, str]) -> str:
    rendered = str(template or "")
    for key, value in variables.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def _prompt_config(definition: Any) -> dict:
    prompt = getattr(definition, "prompt", {}) if isinstance(getattr(definition, "prompt", {}), dict) else {}
    template = str(prompt.get("template") or "").strip()
    if not template:
        raise ValueError("prompt component requires prompt.template")
    output_type = str(prompt.get("output_type") or "markdown").strip() or "markdown"
    if output_type not in {"text", "markdown"}:
        raise ValueError("prompt.output_type must be text or markdown")
    return {"template": template, "output_type": output_type}


def run_prompt_component(
    definition: Any,
    openid: str,
    raw_input: str,
    target_text: str,
    *,
    adapter: ModelAdapter | None = None,
) -> PromptComponentRunResult:
    try:
        prompt = _prompt_config(definition)
        source_text = str(target_text or raw_input or "").strip()
        rendered_prompt = _render_prompt(
            prompt["template"],
            {
                "raw_input": str(raw_input or ""),
                "target_text": str(target_text or ""),
                "openid": str(openid or ""),
            },
        )
        model_config = _global_model_config()
        request = AIGenerationRequest(
            service_type=ServiceType.UNMATCHED,
            source_text=source_text,
            prompt=rendered_prompt,
            model_provider=str(model_config["provider"]),
            model_name=str(model_config["model"]),
            api_base=str(model_config["api_base"]),
            api_key=str(model_config["api_key"]),
            temperature=float(model_config["temperature"]),
        )
        text = (adapter or ExistingModelAdapter()).generate(request).strip()
        if not text:
            raise RuntimeError("model returned empty text")
        return PromptComponentRunResult(True, reply_text=text, output_type=prompt["output_type"])
    except Exception as exc:
        detail = sanitize_sensitive_text(str(exc))
        return PromptComponentRunResult(
            False,
            error_code=ErrorCode.SYSTEM_ERROR,
            user_prompt=user_message(ErrorCode.SYSTEM_ERROR),
            detail=detail,
        )
