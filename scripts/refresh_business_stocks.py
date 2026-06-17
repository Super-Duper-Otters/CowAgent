# encoding:utf-8
import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from business import stock_resolver
from business import storage  # noqa: E402


def _count_successes(result: dict[str, Any]) -> tuple[int, list[str]]:
    total = 0
    errors = []
    for source, item in result.items():
        if not isinstance(item, dict):
            continue
        count = int(item.get("count") or 0)
        if count > 0:
            total += count
        error = str(item.get("error") or "").strip()
        if error:
            errors.append(f"{source}: {error}")
    return total, errors


def _build_auto_payload() -> dict[str, Any]:
    result = stock_resolver.refresh_all_symbols_from_tushare()
    count, errors = _count_successes(result)
    has_success = any(isinstance(item, dict) and "count" in item for item in result.values())
    return {
        "source": "all",
        "success": has_success,
        "count": count,
        "error": "; ".join(errors),
        "result": result,
        "db_path": str(storage.get_db_path()),
    }


def _build_single_source_payload(source: str) -> dict[str, Any]:
    refreshers = {
        "a_share": stock_resolver.refresh_a_share_symbols_from_tushare,
        "hk": stock_resolver.refresh_hk_symbols_from_tushare,
        "us": stock_resolver.refresh_us_symbols_from_tushare,
    }
    refresher = refreshers[source]
    try:
        count = refresher()
    except Exception as exc:  # noqa: BLE001 - CLI must log provider errors and return a scheduler-friendly exit code.
        return {
            "source": source,
            "success": False,
            "count": 0,
            "error": str(exc),
            "result": None,
            "db_path": str(storage.get_db_path()),
        }
    return {
        "source": source,
        "success": True,
        "count": count,
        "error": "",
        "result": {"count": count},
        "db_path": str(storage.get_db_path()),
    }


def _print_payload(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
        return
    print(f"source={payload['source']}")
    print(f"success={payload['success']}")
    print(f"count={payload['count']}")
    print(f"error={payload['error']}")
    print(f"db_path={payload['db_path']}")
    print(f"result={json.dumps(payload['result'], ensure_ascii=False)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh the investment stock dictionary.")
    parser.add_argument("--source", choices=("all", "a_share", "hk", "us"), default="all")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    storage.initialize_storage()
    payload = _build_auto_payload() if args.source == "all" else _build_single_source_payload(args.source)
    _print_payload(payload, args.json)
    return 0 if payload["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
