# encoding:utf-8
import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from business.content import stock_resolver as stock_resolver  # noqa: E402
from business.schema import storage as storage  # noqa: E402


def _database_payload() -> dict[str, str]:
    return {"database": "postgresql"}


def _count_successes(result: dict[str, Any]) -> tuple[int, list[str]]:
    total = 0
    errors = []
    for source, item in result.items():
        if not isinstance(item, dict):
            continue
        if "count" in item:
            item_count = int(item.get("count") or 0)
            if item_count > 0:
                total += item_count
            error = str(item.get("error") or "").strip()
            if error:
                errors.append(f"{source}: {error}")
            continue
        count, nested_errors = _count_successes(item)
        total += count
        errors.extend(f"{source}.{error}" for error in nested_errors)
        if "error" in item:
            error = str(item.get("error") or "").strip()
            if error:
                errors.append(f"{source}: {error}")
    return total, errors


def _has_success_count(result: dict[str, Any]) -> bool:
    for item in result.values():
        if not isinstance(item, dict):
            continue
        if "count" in item:
            return True
        if _has_success_count(item):
            return True
    return False


def _build_auto_payload() -> dict[str, Any]:
    result = stock_resolver.refresh_all_symbol_sources()
    count, errors = _count_successes(result)
    has_success = _has_success_count(result)
    return {
        "source": "all",
        "success": has_success,
        "count": count,
        "error": "; ".join(errors),
        "result": result,
        **_database_payload(),
    }


def _build_single_source_payload(source: str) -> dict[str, Any]:
    refreshers = {
        "tushare": stock_resolver.refresh_all_symbols_from_tushare,
        "akshare": stock_resolver.refresh_all_symbols_from_akshare,
        "baostock": stock_resolver.refresh_all_symbols_from_baostock,
        "a_share": stock_resolver.refresh_a_share_symbols_from_tushare,
        "hk": stock_resolver.refresh_hk_symbols_from_tushare,
        "us": stock_resolver.refresh_us_symbols_from_tushare,
        "akshare_a_share": stock_resolver.refresh_a_share_symbols_from_akshare,
        "akshare_hk": stock_resolver.refresh_hk_symbols_from_akshare,
        "akshare_us": stock_resolver.refresh_us_symbols_from_akshare,
        "etf": stock_resolver.refresh_etf_symbols_from_akshare,
        "convertible_bond": stock_resolver.refresh_convertible_bond_symbols_from_akshare,
        "gold": stock_resolver.refresh_gold_symbols_from_akshare,
        "futures": stock_resolver.refresh_bond_futures_symbols_from_akshare,
    }
    refresher = refreshers[source]
    try:
        result = refresher()
    except Exception as exc:  # noqa: BLE001 - CLI must log provider errors and return a scheduler-friendly exit code.
        return {
            "source": source,
            "success": False,
            "count": 0,
            "error": str(exc),
            "result": None,
            **_database_payload(),
        }
    if isinstance(result, dict):
        count, errors = _count_successes(result)
        return {
            "source": source,
            "success": _has_success_count(result),
            "count": count,
            "error": "; ".join(errors),
            "result": result,
            **_database_payload(),
        }
    count = int(result)
    return {
        "source": source,
        "success": True,
        "count": count,
        "error": "",
        "result": {"count": count},
        **_database_payload(),
    }


def _print_payload(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
        return
    print(f"source={payload['source']}")
    print(f"success={payload['success']}")
    print(f"count={payload['count']}")
    print(f"error={payload['error']}")
    print(f"database={payload['database']}")
    print(f"result={json.dumps(payload['result'], ensure_ascii=False)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh the business stock dictionary.")
    parser.add_argument(
        "--source",
        choices=(
            "all",
            "tushare",
            "akshare",
            "baostock",
            "a_share",
            "hk",
            "us",
            "akshare_a_share",
            "akshare_hk",
            "akshare_us",
            "etf",
            "convertible_bond",
            "gold",
            "futures",
        ),
        default="all",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    storage.initialize_storage()
    payload = _build_auto_payload() if args.source == "all" else _build_single_source_payload(args.source)
    _print_payload(payload, args.json)
    return 0 if payload["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
