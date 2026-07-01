# encoding:utf-8
"""Generic investment module dispatch."""

from business.config.config_service import sanitize_sensitive_text
from business.config.constants import ErrorCode, ServiceType, user_message


def _with_module_key(reply, module_key: str):
    if reply is not None and module_key and not getattr(reply, "module_key", ""):
        reply.module_key = module_key
    return reply


def _failure_reply_with_detail(prompt: str, detail: str) -> str:
    # Component details are backend diagnostics such as stderr, tracebacks, or file paths.
    return prompt


def dispatch_module(
    definition,
    openid,
    raw_input,
    route,
    *,
    customer_metadata=None,
    record_context=None,
    elapsed=lambda: 0,
    technical_analysis_handler=None,
):
    handler_type = str(getattr(definition, "handler_type", "") or "")
    module_key = str(getattr(definition, "business_key", "") or getattr(route, "module_key", "") or "")

    if handler_type == "daily_content":
        from business.content.daily_content_handler import handle_daily_content

        return _with_module_key(
            handle_daily_content(
                openid,
                raw_input,
                route,
                definition=definition,
                customer_metadata=customer_metadata,
                record_context=record_context,
                elapsed=elapsed,
            ),
            module_key,
        )

    if handler_type in {"technical_analysis", "builtin_technical_analysis"}:
        from business.content.technical_analysis_handler import handle_technical_analysis

        return _with_module_key(
            handle_technical_analysis(
                openid,
                raw_input,
                route,
                customer_metadata=customer_metadata,
                record_context=record_context,
                elapsed=elapsed,
                technical_analysis_handler=technical_analysis_handler,
            ),
            module_key,
        )

    if handler_type == "prompt_to_image":
        from business.content.prompt_to_image_handler import handle_prompt_to_image

        return handle_prompt_to_image(
            openid,
            raw_input,
            route,
            definition=definition,
            customer_metadata=customer_metadata,
            record_context=record_context,
            elapsed=elapsed,
        )

    if handler_type == "prompt_component":
        from business.records.business_records import create_business_record, mark_business_failed, mark_business_success
        from business.execution.prompt_component_executor import run_prompt_component
        from business.routing.router import BusinessReply

        customer_metadata = customer_metadata or {}
        request_id = create_business_record(
            openid,
            raw_input,
            route.service_type,
            record_context=record_context,
            module_key=module_key,
            customer_name=customer_metadata.get("customer_name", ""),
            institution=customer_metadata.get("institution", ""),
        )
        try:
            result = run_prompt_component(definition, openid, raw_input, getattr(route, "target_text", ""))
            if not result.success:
                code = result.error_code or ErrorCode.SYSTEM_ERROR
                prompt = result.user_prompt or user_message(code)
                detail = sanitize_sensitive_text(result.detail)
                mark_business_failed(request_id, code, prompt, detail, elapsed())
                return BusinessReply(
                    True,
                    False,
                    _failure_reply_with_detail(prompt, detail),
                    [],
                    route.service_type,
                    code,
                    prompt,
                    detail,
                    request_id,
                    module_key=module_key,
                )
            mark_business_success(request_id, output_files=[], artifact_roles={}, elapsed_ms=elapsed())
            return BusinessReply(
                True,
                True,
                result.reply_text,
                [],
                route.service_type,
                request_id=request_id,
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
                route.service_type,
                ErrorCode.SYSTEM_ERROR,
                prompt,
                detail,
                request_id,
                module_key=module_key,
            )

    if handler_type == "command_script" or getattr(definition, "execution", {}):
        from business.records.business_records import create_business_record, mark_business_failed, mark_business_success
        from business.config.constants import ErrorCode, user_message
        from business.execution.command_script_executor import run_command_script_component
        from business.routing.router import BusinessReply

        customer_metadata = customer_metadata or {}
        request_id = create_business_record(
            openid,
            raw_input,
            route.service_type,
            record_context=record_context,
            module_key=module_key,
            customer_name=customer_metadata.get("customer_name", ""),
            institution=customer_metadata.get("institution", ""),
        )
        try:
            result = run_command_script_component(definition, openid, raw_input, getattr(route, "target_text", ""))
            if not result.success:
                code = result.error_code or ErrorCode.SYSTEM_ERROR
                prompt = result.user_prompt or user_message(code)
                detail = sanitize_sensitive_text(result.detail)
                mark_business_failed(request_id, code, prompt, detail, elapsed())
                return BusinessReply(
                    True,
                    False,
                    _failure_reply_with_detail(prompt, detail),
                    [],
                    route.service_type,
                    code,
                    prompt,
                    detail,
                    request_id,
                    module_key=module_key,
                )
            storage_namespace = f"components/{module_key}" if route.service_type == ServiceType.UNMATCHED and module_key else ""
            archived_path_map = mark_business_success(
                request_id,
                output_files=result.archive_files,
                artifact_roles=result.artifact_roles,
                elapsed_ms=elapsed(),
                storage_namespace=storage_namespace,
            )
            if result.archive_files:
                from business.products.product_service import create_product_from_success_request

                create_product_from_success_request(
                    request_id,
                    target_key=getattr(route, "target_text", "") or raw_input,
                    target_label=raw_input,
                )
            reply_files = [archived_path_map.get(path, path) for path in result.reply_files]
            return BusinessReply(
                True,
                True,
                result.reply_text,
                reply_files,
                route.service_type,
                request_id=request_id,
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
                route.service_type,
                ErrorCode.SYSTEM_ERROR,
                prompt,
                detail,
                request_id,
                module_key=module_key,
            )

    if handler_type == "script":
        from business.records.business_records import create_business_record, mark_business_failed, mark_business_success
        from business.routing.router import BusinessReply
        from business.components.skill_runner import run_investment_skill

        customer_metadata = customer_metadata or {}
        request_id = create_business_record(
            openid,
            raw_input,
            route.service_type,
            record_context=record_context,
            module_key=module_key,
            customer_name=customer_metadata.get("customer_name", ""),
            institution=customer_metadata.get("institution", ""),
        )
        try:
            result = run_investment_skill(definition, openid, raw_input, getattr(route, "target_text", ""))
            if not result.success:
                code = result.error_code or ErrorCode.SYSTEM_ERROR
                prompt = result.user_prompt or user_message(code)
                detail = sanitize_sensitive_text(result.detail)
                mark_business_failed(request_id, code, prompt, detail, elapsed())
                return BusinessReply(
                    True,
                    False,
                    _failure_reply_with_detail(prompt, detail),
                    [],
                    route.service_type,
                    code,
                    prompt,
                    detail,
                    request_id,
                    module_key=module_key,
                )
            storage_namespace = f"components/{module_key}" if route.service_type == ServiceType.UNMATCHED and module_key else ""
            archived_path_map = mark_business_success(
                request_id,
                output_files=result.output_files,
                elapsed_ms=elapsed(),
                storage_namespace=storage_namespace,
            )
            if result.output_files:
                from business.products.product_service import create_product_from_success_request

                create_product_from_success_request(
                    request_id,
                    target_key=getattr(route, "target_text", "") or raw_input,
                    target_label=raw_input,
                )
            reply_files = [archived_path_map.get(path, path) for path in result.output_files]
            return BusinessReply(
                True,
                True,
                result.reply_text,
                reply_files,
                route.service_type,
                request_id=request_id,
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
                route.service_type,
                ErrorCode.SYSTEM_ERROR,
                prompt,
                detail,
                request_id,
                module_key=module_key,
            )

    from business.routing.router import BusinessReply

    return BusinessReply(
        True,
        False,
        user_message(ErrorCode.INPUT_ERROR),
        [],
        route.service_type,
        ErrorCode.INPUT_ERROR,
        request_id="",
        detail=f"unsupported handler_type: {handler_type}",
        module_key=module_key,
    )
