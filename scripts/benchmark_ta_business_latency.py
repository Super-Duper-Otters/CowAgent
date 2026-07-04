# encoding:utf-8
"""Benchmark technical-analysis business latency without WeChat HTTP I/O.

The script calls the real business layer and records wall-clock timings for
important internal functions. By default it avoids expensive generation and
focuses on routing, validation, cache lookup, running, and error replies.
Use --include-run to allow real technical-analysis generation.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from business.config.constants import ErrorCode, ServiceType
from business.content.technical_analysis import prepare_technical_analysis_cache_context, run_technical_analysis
from business.schema.db import connect, row_to_dict
from business.schema.tables import investment_stock_symbols


TYPE_ORDER = [
    "a_share",
    "hk_stock",
    "us_stock",
    "index",
    "etf",
    "convertible_bond",
    "futures",
]


@dataclass
class TimedCall:
    label: str
    elapsed_ms: float
    ok: bool = True
    error: str = ""


@dataclass
class TimingProbe:
    calls: list[TimedCall] = field(default_factory=list)

    def record(self, label: str, elapsed_ms: float, ok: bool = True, error: str = "") -> None:
        self.calls.append(TimedCall(label, elapsed_ms, ok=ok, error=error[:300]))

    def summary(self) -> dict[str, dict[str, Any]]:
        grouped: dict[str, list[TimedCall]] = defaultdict(list)
        for call in self.calls:
            grouped[call.label].append(call)
        return {
            label: {
                **_summary([call.elapsed_ms for call in calls]),
                "errors": sum(1 for call in calls if not call.ok),
            }
            for label, calls in sorted(grouped.items())
        }

    def per_case(self) -> list[dict[str, Any]]:
        return [
            {
                "label": call.label,
                "elapsed_ms": round(call.elapsed_ms, 3),
                "ok": call.ok,
                **({"error": call.error} if call.error else {}),
            }
            for call in self.calls
        ]


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile / 100
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - rank) + ordered[upper] * (rank - lower)


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "avg_ms": round(statistics.mean(values), 3),
        "p50_ms": round(_percentile(values, 50), 3),
        "p95_ms": round(_percentile(values, 95), 3),
        "p99_ms": round(_percentile(values, 99), 3),
        "max_ms": round(max(values), 3),
    }


def _sample_targets(limit_per_type: int, seed: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with connect() as conn:
        for asset_type in TYPE_ORDER:
            stmt = (
                select(
                    investment_stock_symbols.c.code,
                    investment_stock_symbols.c.name,
                    investment_stock_symbols.c.market,
                    investment_stock_symbols.c.ts_code,
                    investment_stock_symbols.c.asset_type,
                )
                .where(investment_stock_symbols.c.asset_type == asset_type)
                .order_by(investment_stock_symbols.c.code)
            )
            items = [row_to_dict(row) for row in conn.execute(stmt).fetchall()]
            rng = random.Random(f"{seed}:{asset_type}")
            rng.shuffle(items)
            rows.extend(items[:limit_per_type])
    return rows


def _target_text(row: dict[str, Any]) -> str:
    return str(row.get("code") or "").strip()


def _technical_analysis_raw_input(target: str) -> str:
    try:
        from business.components.registry import get_business_definition, resolve_match_type, resolve_triggers

        definition = get_business_definition("technical-analysis")
        triggers = sorted(resolve_triggers(definition), key=len, reverse=True)
        trigger = triggers[0] if triggers else "技术分析"
        match_type = resolve_match_type(definition)
        if match_type == "prefix":
            return f"{trigger}{target}".strip()
        if match_type == "exact":
            return trigger
        return f"{target} {trigger}".strip()
    except Exception:
        return f"{target} 技术分析".strip()


def _wrap_function(module: Any, name: str, label: str, probe: TimingProbe) -> Callable[[], None]:
    original = getattr(module, name)

    def wrapped(*args, **kwargs):
        started = time.perf_counter()
        ok = True
        error = ""
        try:
            return original(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - benchmark must report failures then preserve behavior.
            ok = False
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            probe.record(label, (time.perf_counter() - started) * 1000, ok=ok, error=error)

    setattr(module, name, wrapped)

    def restore() -> None:
        setattr(module, name, original)

    return restore


@contextmanager
def _instrumented_probe():
    import business.artifacts.artifacts as artifacts
    import business.cache.cache_service as cache_service
    import business.components.registry as registry
    import business.config.config_service as config_service
    import business.content.market_date_resolver as market_date_resolver
    import business.content.stock_resolver as stock_resolver
    import business.content.technical_analysis as technical_analysis
    import business.content.technical_analysis_handler as ta_handler
    import business.products.product_service as product_service
    import business.routing.router as router

    probe = TimingProbe()
    restores: list[Callable[[], None]] = []
    targets = (
        (config_service, "get_config", "config.get_config"),
        (registry, "match_business", "route.match_business"),
        (registry, "list_business_definitions", "route.list_business_definitions"),
        (router, "_customer_metadata", "route.customer_metadata"),
        (router, "parse_route", "route.parse_route"),
        (router, "verify_user_access", "permission.verify_user_access"),
        (router, "verify_permission", "permission.verify_business_access"),
        (ta_handler, "validate_technical_analysis_request", "ta.precheck"),
        (ta_handler, "prepare_technical_analysis_business_context", "ta.prepare_context"),
        (ta_handler, "start_cache_job_if_absent", "job.start_cache_job"),
        (ta_handler, "start_job_if_absent_with_metadata", "job.start_job"),
        (ta_handler, "run_technical_analysis_business", "ta.run_business"),
        (ta_handler, "archive_business_output_files", "artifact.archive_output_files"),
        (ta_handler, "write_business_cache", "cache.write_business_cache"),
        (ta_handler, "succeed_request_record", "record.mark_success"),
        (ta_handler, "fail_request_record", "record.mark_failed"),
        (ta_handler, "replace_active_product", "product.replace_active_product"),
        (technical_analysis, "_technical_analysis_target_from_input", "ta.resolve_target"),
        (technical_analysis, "_resolve_market_date", "ta.resolve_market_date"),
        (technical_analysis, "_versions", "ta.versions"),
        (technical_analysis, "_run_skill_for_target", "ta.skill_subprocess"),
        (technical_analysis, "generate_technical_analysis_text", "ta.ai_generate_text"),
        (technical_analysis, "render_technical_analysis_card", "ta.render_card"),
        (technical_analysis, "find_active_product", "product.find_active"),
        (technical_analysis, "find_cache_entry", "cache.find_entry"),
        (technical_analysis, "find_cache_entry_by_key", "cache.find_entry_by_key"),
        (technical_analysis, "find_latest_cache_entry", "cache.find_latest_entry"),
        (technical_analysis, "increment_cache_hit", "cache.increment_hit"),
        (technical_analysis, "increment_product_hit", "product.increment_hit"),
        (cache_service, "find_cache_entry_by_key", "cache_service.find_entry_by_key"),
        (cache_service, "find_latest_cache_entry_for_target", "cache_service.find_latest_for_target"),
        (cache_service, "technical_analysis_cache_expired_after_close", "cache_policy.expired_after_close"),
        (product_service, "invalidate_products_by_source", "product.invalidate_by_source"),
        (stock_resolver, "get_stock_symbol_by_code", "stock.get_by_code"),
        (stock_resolver, "list_exact_stock_name_matches", "stock.list_exact_name"),
        (stock_resolver, "list_bare_code_symbol_matches", "stock.list_bare_code"),
        (stock_resolver, "list_index_symbol_matches_for_bare_code", "stock.list_index_bare_code"),
        (market_date_resolver.MarketDateResolver, "_latest_market_date", "market_date.latest"),
        (artifacts, "archive_business_output_files", "artifact.archive_business_output_files"),
    )
    try:
        for module, name, label in targets:
            if hasattr(module, name):
                restores.append(_wrap_function(module, name, label, probe))
        yield probe
    finally:
        for restore in reversed(restores):
            restore()


def _reply_shape(reply) -> dict[str, Any]:
    return {
        "handled": bool(getattr(reply, "handled", False)),
        "success": bool(getattr(reply, "success", False)),
        "service_type": str(getattr(reply, "service_type", "")),
        "error_code": str(getattr(reply, "error_code", "") or ""),
        "request_id": str(getattr(reply, "request_id", "") or ""),
        "source_type": str(getattr(reply, "source_type", "") or ""),
        "source_id": str(getattr(reply, "source_id", "") or ""),
        "output_files_count": len(getattr(reply, "output_files", []) or []),
        "reply_text_preview": str(getattr(reply, "reply_text", "") or "")[:180],
    }


def _case_payload(name: str, raw_input: str, started: float, probe: TimingProbe, reply=None, error: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "raw_input": raw_input,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "reply": _reply_shape(reply) if reply is not None else {},
        "error": error,
        "segments": probe.per_case(),
        "segment_summary": probe.summary(),
    }


def _run_business_case(name: str, raw_input: str, *, openid: str, skip_permission: bool) -> dict[str, Any]:
    from business.routing.router import handle_text_message

    with _instrumented_probe() as probe:
        started = time.perf_counter()
        try:
            reply = handle_text_message(openid, raw_input, skip_permission=skip_permission)
            return _case_payload(name, raw_input, started, probe, reply=reply)
        except Exception as exc:  # noqa: BLE001 - benchmark output should capture unexpected failures.
            return _case_payload(name, raw_input, started, probe, error=f"{type(exc).__name__}: {exc}")


def _run_context_case(row: dict[str, Any]) -> dict[str, Any]:
    target = _target_text(row)
    raw_input = _technical_analysis_raw_input(target)
    with _instrumented_probe() as probe:
        started = time.perf_counter()
        try:
            context = prepare_technical_analysis_cache_context(raw_input, target)
            payload = _case_payload("prepare_context", raw_input, started, probe)
            payload["context"] = {
                "asset_type": str(row.get("asset_type") or ""),
                "normalized_target": context.normalized_target,
                "market_date": context.market_date,
                "cache_key": context.cache_key,
                "resolved_market_date": {
                    "known": bool(context.resolved_market_date.known) if context.resolved_market_date else False,
                    "market_date": context.resolved_market_date.market_date if context.resolved_market_date else "",
                    "source": context.resolved_market_date.source if context.resolved_market_date else "",
                },
            }
            return payload
        except Exception as exc:  # noqa: BLE001
            return _case_payload("prepare_context", raw_input, started, probe, error=f"{type(exc).__name__}: {exc}")


def _run_direct_run_case(row: dict[str, Any], *, openid: str) -> dict[str, Any]:
    target = _target_text(row)
    raw_input = _technical_analysis_raw_input(target)
    with _instrumented_probe() as probe:
        started = time.perf_counter()
        try:
            context = prepare_technical_analysis_cache_context(raw_input, target)
            result = run_technical_analysis(openid, raw_input, target, cache_context=context)
            payload = _case_payload("run_technical_analysis", raw_input, started, probe)
            payload["result"] = {
                "success": result.success,
                "error_code": str(result.error_code or ""),
                "cache_hit": bool(result.cache_hit),
                "cache_key": result.cache_key,
                "source_type": result.source_type,
                "source_id": result.source_id,
                "output_files_count": len(result.output_files or []),
                "detail_preview": str(result.detail or "")[:240],
            }
            return payload
        except Exception as exc:  # noqa: BLE001
            return _case_payload("run_technical_analysis", raw_input, started, probe, error=f"{type(exc).__name__}: {exc}")


def _aggregate_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    elapsed_by_name: dict[str, list[float]] = defaultdict(list)
    segment_values: dict[str, list[float]] = defaultdict(list)
    reply_counts: dict[str, int] = defaultdict(int)
    for case in cases:
        elapsed_by_name[case["name"]].append(float(case["elapsed_ms"]))
        reply = case.get("reply") or {}
        if reply:
            key = "|".join(
                [
                    str(reply.get("service_type") or ""),
                    "success" if reply.get("success") else "failed",
                    str(reply.get("error_code") or ""),
                    str(reply.get("source_type") or ""),
                ]
            )
            reply_counts[key] += 1
        for call in case.get("segments") or []:
            segment_values[str(call["label"])].append(float(call["elapsed_ms"]))
    return {
        "by_case_name": {name: _summary(values) for name, values in sorted(elapsed_by_name.items())},
        "segments": {name: _summary(values) for name, values in sorted(segment_values.items())},
        "reply_counts": dict(sorted(reply_counts.items())),
    }


def run_benchmark(
    *,
    limit_per_type: int,
    include_run: bool,
    seed: str,
    openid: str,
    skip_permission: bool,
    cases: list[str],
) -> dict[str, Any]:
    targets = _sample_targets(limit_per_type, seed)
    chosen = targets[:]
    first_target = _target_text(chosen[0]) if chosen else "300502.SZ"
    context_cases = [_run_context_case(row) for row in chosen]

    business_cases = []
    case_set = set(cases)
    if "input_error" in case_set:
        business_cases.append(_run_business_case("input_error", "不是技术分析输入", openid=openid, skip_permission=skip_permission))
    if "stock_not_found" in case_set:
        business_cases.append(
            _run_business_case("stock_not_found", _technical_analysis_raw_input("不存在股票XYZ"), openid=openid, skip_permission=skip_permission)
        )
    if "business" in case_set:
        business_cases.append(
            _run_business_case("business_technical_analysis", _technical_analysis_raw_input(first_target), openid=openid, skip_permission=skip_permission)
        )

    run_cases = []
    if include_run:
        for row in chosen:
            run_cases.append(_run_direct_run_case(row, openid=openid))

    all_cases = [*context_cases, *business_cases, *run_cases]
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "description": "Technical-analysis business benchmark excluding WeChat HTTP ingress/egress and WeChat media upload.",
        "limit_per_type": limit_per_type,
        "include_run": include_run,
        "skip_permission": skip_permission,
        "openid": openid,
        "targets": len(targets),
        "cases": all_cases,
        "summary": _aggregate_cases(all_cases),
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Benchmark technical-analysis business latency without WeChat I/O.")
    parser.add_argument("--limit-per-type", type=int, default=1, help="Sample targets per asset type for prepare/run cases.")
    parser.add_argument("--include-run", action="store_true", help="Also call run_technical_analysis; may invoke real generation.")
    parser.add_argument("--seed", default="ta-business-latency")
    parser.add_argument("--openid", default="ta_latency_benchmark")
    parser.add_argument("--skip-permission", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--cases",
        default="input_error,stock_not_found,business",
        help="Comma-separated business cases: input_error,stock_not_found,business",
    )
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    selected_cases = [item.strip() for item in str(args.cases or "").split(",") if item.strip()]
    payload = run_benchmark(
        limit_per_type=max(1, args.limit_per_type),
        include_run=bool(args.include_run),
        seed=str(args.seed or "ta-business-latency"),
        openid=str(args.openid or "ta_latency_benchmark"),
        skip_permission=bool(args.skip_permission),
        cases=selected_cases,
    )
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
