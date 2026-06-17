# encoding:utf-8
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from business.constants import ErrorCode, user_message
from .daily_content import get_latest_effective_content
from .technical_analysis import run_technical_analysis


@dataclass
class InvestmentSkillRunResult:
    success: bool
    reply_text: str = ""
    output_files: list[str] = field(default_factory=list)
    error_code: ErrorCode | None = None
    user_prompt: str = ""
    detail: str = ""


def _image_reply(paths: list[str]) -> str:
    return "\n".join(f"[图片: {path}]" for path in paths)


def _run_daily_content(definition: Any) -> InvestmentSkillRunResult:
    content = get_latest_effective_content(definition.service_type)
    if not content.success:
        code = content.error_code or ErrorCode.NO_CONTENT
        return InvestmentSkillRunResult(
            False,
            error_code=code,
            user_prompt=content.user_prompt,
            detail=content.detail,
        )
    return InvestmentSkillRunResult(True, _image_reply([content.output_image]), [content.output_image])


def _run_script(
    definition: Any,
    openid: str,
    raw_input: str,
    target_text: str,
) -> InvestmentSkillRunResult:
    script_path = ""
    config_key = str(getattr(definition, "config_key", "") or "")
    if config_key:
        from business.config_service import get_config

        script_path = str(get_config(config_key, "") or "")
    script = Path(script_path or definition.default_script_path or definition.entry)
    if not script.is_absolute():
        script = Path.cwd() / script
    payload = {
        "openid": openid,
        "raw_input": raw_input,
        "target_text": target_text,
        "skill_key": getattr(definition, "skill_key", "") or getattr(definition, "business_key", ""),
    }
    completed = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(completed.stdout or "{}")
    output_files = [str(item) for item in data.get("output_files", [])]
    return InvestmentSkillRunResult(
        bool(data.get("success")),
        str(data.get("reply_text") or _image_reply(output_files)),
        output_files,
        detail=str(data.get("detail") or ""),
    )


def run_investment_skill(
    definition: Any,
    openid: str,
    raw_input: str,
    target_text: str = "",
) -> InvestmentSkillRunResult:
    if definition.handler_type == "daily_content":
        return _run_daily_content(definition)
    if definition.handler_type == "builtin_technical_analysis":
        result = run_technical_analysis(openid, raw_input, target_text)
        if not result.success:
            code = result.error_code or ErrorCode.TECHNICAL_ANALYSIS_FAILED
            return InvestmentSkillRunResult(False, error_code=code, user_prompt=user_message(code), detail=result.detail)
        output_files = [result.signal_card_path, result.main_chart_path]
        return InvestmentSkillRunResult(True, _image_reply(output_files), output_files)
    if definition.handler_type == "script":
        return _run_script(definition, openid, raw_input, target_text)
    return InvestmentSkillRunResult(
        False,
        error_code=ErrorCode.INPUT_ERROR,
        user_prompt=user_message(ErrorCode.INPUT_ERROR),
        detail=f"unsupported handler_type: {definition.handler_type}",
    )
