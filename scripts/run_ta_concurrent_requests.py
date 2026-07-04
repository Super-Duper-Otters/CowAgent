# encoding:utf-8
import argparse
import csv
import json
import os
import queue
import random
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import or_, select

from business.schema.db import connect, row_to_dict
from business.schema.tables import investment_stock_symbols


DEFAULT_CONCURRENCY = 5
DEFAULT_TIMEOUT_SECONDS = 900

FOCUS_CODES = [
    "000171.CSI",
    "931555CNY01.CSI",
    "932275CNY210.CSI",
    "931751HKD01.CSI",
    "000501CNY01.CSI",
    "L01224.CSI",
    "T0",
    "TF0",
    "TL0",
    "TS0",
    "TL1",
    "510910.SH",
    "560470.SH",
    "588510.SH",
    "159056.SZ",
    "123269.SZ",
    "118501.SH",
    "128100.SZ",
]


def _repo_root() -> Path:
    return REPO_ROOT


def _truncate(value: str, limit: int = 3000) -> str:
    text = str(value or "")
    return text[-limit:] if len(text) > limit else text


def _db_targets_by_codes(codes: list[str]) -> dict[str, dict]:
    if not codes:
        return {}
    table = investment_stock_symbols
    lower_codes = [code.lower() for code in codes]
    stmt = (
        select(table.c.code, table.c.name, table.c.market, table.c.ts_code, table.c.asset_type)
        .where(or_(table.c.code.in_(codes), table.c.ts_code.in_(codes)))
        .order_by(table.c.asset_type, table.c.code)
    )
    with connect() as conn:
        rows = [row_to_dict(row) for row in conn.execute(stmt).fetchall()]
    result = {}
    for row in rows:
        code = str(row.get("code") or "")
        ts_code = str(row.get("ts_code") or "")
        if code.lower() in lower_codes:
            result[code.lower()] = row
        if ts_code.lower() in lower_codes:
            result[ts_code.lower()] = row
    return result


def _sample_asset_targets(asset_type: str, limit: int, seed: str) -> list[dict]:
    table = investment_stock_symbols
    stmt = (
        select(table.c.code, table.c.name, table.c.market, table.c.ts_code, table.c.asset_type)
        .where(table.c.asset_type == asset_type)
        .order_by(table.c.code)
    )
    with connect() as conn:
        rows = [row_to_dict(row) for row in conn.execute(stmt).fetchall()]
    rng = random.Random(seed)
    rng.shuffle(rows)
    return rows[:limit]


def _sample_csi_index_targets(limit: int, seed: str) -> list[dict]:
    table = investment_stock_symbols
    stmt = (
        select(table.c.code, table.c.name, table.c.market, table.c.ts_code, table.c.asset_type)
        .where(table.c.asset_type == "index", or_(table.c.market == "CSI", table.c.code.ilike("%.CSI"), table.c.ts_code.ilike("%.CSI")))
        .order_by(table.c.code)
    )
    with connect() as conn:
        rows = [row_to_dict(row) for row in conn.execute(stmt).fetchall()]
    rng = random.Random(seed)
    rng.shuffle(rows)
    return rows[:limit]


def _target(symbol: str, *, name: str = "", asset_type: str = "manual", market: str = "", ts_code: str = "", source: str = "manual") -> dict:
    return {
        "symbol": symbol,
        "code": symbol,
        "name": name,
        "asset_type": asset_type,
        "market": market,
        "ts_code": ts_code,
        "source": source,
    }


def _build_default_plan() -> list[dict]:
    targets: list[dict] = []
    existing = _db_targets_by_codes(FOCUS_CODES)
    for code in FOCUS_CODES:
        row = existing.get(code.lower())
        if row:
            targets.append(
                _target(
                    str(row.get("code") or code),
                    name=str(row.get("name") or ""),
                    asset_type=str(row.get("asset_type") or ""),
                    market=str(row.get("market") or ""),
                    ts_code=str(row.get("ts_code") or ""),
                    source="focus",
                )
            )
        else:
            targets.append(_target(code, source="focus_missing"))

    samples = []
    samples.extend(_sample_asset_targets("etf", 12, "ta-concurrent-etf-20260704"))
    samples.extend(_sample_asset_targets("convertible_bond", 12, "ta-concurrent-cb-20260704"))
    samples.extend(_sample_asset_targets("index", 12, "ta-concurrent-index-20260704"))
    for row in samples:
        targets.append(
            _target(
                str(row.get("code") or ""),
                name=str(row.get("name") or ""),
                asset_type=str(row.get("asset_type") or ""),
                market=str(row.get("market") or ""),
                ts_code=str(row.get("ts_code") or ""),
                source="sample",
            )
        )

    deduped = []
    seen = set()
    for item in targets:
        key = str(item.get("symbol") or "").upper()
        if not key or key in seen:
            continue
        seen.add(key)
        item["request_id"] = f"req-{len(deduped) + 1:04d}"
        item["openid"] = f"ta_concurrent_user_{(len(deduped) % 8) + 1:02d}"
        deduped.append(item)
    return deduped


def _build_category_plan(plan_mode: str, sample_limit: int) -> list[dict]:
    targets: list[dict] = []
    if plan_mode == "csi_futures":
        for row in _sample_csi_index_targets(sample_limit, f"ta-concurrent-csi-{sample_limit}-20260704"):
            targets.append(
                _target(
                    str(row.get("code") or ""),
                    name=str(row.get("name") or ""),
                    asset_type=str(row.get("asset_type") or ""),
                    market=str(row.get("market") or ""),
                    ts_code=str(row.get("ts_code") or ""),
                    source="sample_csi_index",
                )
            )
        for row in _sample_asset_targets("futures", sample_limit, f"ta-concurrent-futures-{sample_limit}-20260704"):
            targets.append(
                _target(
                    str(row.get("code") or ""),
                    name=str(row.get("name") or ""),
                    asset_type=str(row.get("asset_type") or ""),
                    market=str(row.get("market") or ""),
                    ts_code=str(row.get("ts_code") or ""),
                    source="sample_futures",
                )
            )
    elif plan_mode == "all_asset_types":
        for asset_type in ("a_share", "hk_stock", "us_stock", "index", "etf", "convertible_bond", "futures"):
            for row in _sample_asset_targets(asset_type, sample_limit, f"ta-concurrent-{asset_type}-{sample_limit}-20260704"):
                targets.append(
                    _target(
                        str(row.get("code") or ""),
                        name=str(row.get("name") or ""),
                        asset_type=str(row.get("asset_type") or ""),
                        market=str(row.get("market") or ""),
                        ts_code=str(row.get("ts_code") or ""),
                        source=f"sample_{asset_type}",
                    )
                )
    else:
        return _build_default_plan()

    deduped = []
    seen = set()
    for item in targets:
        key = str(item.get("symbol") or "").upper()
        if not key or key in seen:
            continue
        seen.add(key)
        item["request_id"] = f"req-{len(deduped) + 1:04d}"
        item["openid"] = f"ta_concurrent_user_{(len(deduped) % 8) + 1:02d}"
        deduped.append(item)
    return deduped


def _build_plan() -> list[dict]:
    plan_mode = str(os.environ.get("TA_CONCURRENT_PLAN_MODE", "") or "").strip().lower()
    sample_limit = max(1, int(os.environ.get("TA_CONCURRENT_SAMPLE_LIMIT", "100")))
    if plan_mode:
        return _build_category_plan(plan_mode, sample_limit)
    return _build_default_plan()


def _worker_result(symbol: str, openid: str, raw_input: str) -> dict:
    from config import load_config
    from business.content.technical_analysis import run_technical_analysis

    load_config()
    started = time.time()
    result = run_technical_analysis(openid, raw_input)
    payload = asdict(result)
    payload["status"] = "ok" if result.success else "error"
    payload["elapsed_seconds"] = round(time.time() - started, 2)
    payload["error_code"] = result.error_code.value if result.error_code else ""
    payload["detail"] = _truncate(result.detail)
    payload["user_prompt"] = _truncate(result.user_prompt, 1000)
    payload["requested_symbol"] = symbol
    payload["openid"] = openid
    payload["raw_input"] = raw_input
    return payload


def _run_worker(args: argparse.Namespace) -> int:
    output_path = Path(args.worker_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = _worker_result(args.symbol, args.openid, args.raw_input or f"#{args.symbol}")
    except Exception as exc:
        payload = {
            "success": False,
            "status": "error",
            "elapsed_seconds": 0,
            "error_code": "",
            "detail": _truncate(str(exc)),
            "user_prompt": "",
            "requested_symbol": args.symbol,
            "openid": args.openid,
            "raw_input": args.raw_input or f"#{args.symbol}",
        }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def _run_one(repo: Path, run_dir: Path, target: dict, timeout_seconds: int) -> dict:
    symbol = str(target.get("symbol") or target.get("code") or "").strip()
    request_id = str(target.get("request_id") or symbol)
    openid = str(target.get("openid") or "ta_concurrent_user")
    raw_input = f"#{symbol}"
    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in request_id)
    worker_dir = run_dir / "workers"
    worker_dir.mkdir(parents=True, exist_ok=True)
    output_path = worker_dir / f"{safe_name}.json"
    stdout_path = worker_dir / f"{safe_name}.stdout.log"
    stderr_path = worker_dir / f"{safe_name}.stderr.log"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--symbol",
        symbol,
        "--openid",
        openid,
        "--raw-input",
        raw_input,
        "--worker-output",
        str(output_path),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo)
    env["PYTHONIOENCODING"] = "utf-8"
    base = {
        **target,
        "symbol": symbol,
        "openid": openid,
        "raw_input": raw_input,
        "status": "error",
        "success": False,
        "elapsed_seconds": 0,
        "market_date": "",
        "cache_hit": False,
        "source_type": "",
        "signal_card_path": "",
        "main_chart_path": "",
        "report_path": "",
        "output_files": [],
        "error_code": "",
        "detail": "",
        "user_prompt": "",
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }
    started = time.time()
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            completed = subprocess.run(
                command,
                cwd=str(repo),
                env=env,
                stdout=stdout,
                stderr=stderr,
                text=True,
                timeout=timeout_seconds,
            )
        base["elapsed_seconds"] = round(time.time() - started, 2)
        if output_path.exists():
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            base.update(payload)
            base["status"] = "ok" if payload.get("success") else str(payload.get("status") or "error")
        else:
            base["detail"] = f"worker did not write output; exit={completed.returncode}"
        if completed.returncode != 0 and base["status"] == "ok":
            base["status"] = "worker_exit_error"
            base["success"] = False
            base["detail"] = f"worker exit={completed.returncode}; previous result was ok"
    except subprocess.TimeoutExpired:
        base["elapsed_seconds"] = round(time.time() - started, 2)
        base["status"] = "timeout"
        base["detail"] = f"timeout after {timeout_seconds}s"
    except Exception as exc:
        base["elapsed_seconds"] = round(time.time() - started, 2)
        base["status"] = "error"
        base["detail"] = _truncate(str(exc))
    return base


def _summary(rows: list[dict], total: int, run_dir: Path, concurrency: int, timeout_seconds: int, running: list[dict] | None = None) -> dict:
    by_type = {}
    for row in rows:
        asset_type = str(row.get("asset_type") or "unknown")
        item = by_type.setdefault(asset_type, {"done": 0, "ok": 0, "failed": 0})
        item["done"] += 1
        if row.get("status") == "ok":
            item["ok"] += 1
        else:
            item["failed"] += 1
    return {
        "run_dir": str(run_dir),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "concurrency": concurrency,
        "timeout_seconds": timeout_seconds,
        "total_planned": total,
        "total_done": len(rows),
        "ok": sum(1 for row in rows if row.get("status") == "ok"),
        "failed": sum(1 for row in rows if row.get("status") != "ok"),
        "running": running or [],
        "by_type": by_type,
    }


def _write_csv(csv_path: Path, rows: list[dict]) -> None:
    fields = [
        "request_id",
        "openid",
        "source",
        "asset_type",
        "symbol",
        "name",
        "market",
        "ts_code",
        "status",
        "elapsed_seconds",
        "market_date",
        "cache_hit",
        "source_type",
        "signal_card_path",
        "main_chart_path",
        "report_path",
        "error_code",
        "user_prompt",
        "detail",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _main_batch() -> int:
    repo = _repo_root()
    concurrency = max(1, int(os.environ.get("TA_CONCURRENT_CONCURRENCY", DEFAULT_CONCURRENCY)))
    timeout_seconds = int(os.environ.get("TA_CONCURRENT_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = repo / "business_storage" / "tmp" / "ta_concurrent_requests" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    parent_dir = run_dir.parent
    parent_dir.mkdir(parents=True, exist_ok=True)
    (parent_dir / "latest_run.txt").write_text(str(run_dir), encoding="utf-8")

    plan = _build_plan()
    plan_path = run_dir / "plan.json"
    results_path = run_dir / "results.jsonl"
    summary_live_path = run_dir / "summary.live.json"
    summary_path = run_dir / "summary.json"
    csv_path = run_dir / "results.csv"
    log_path = run_dir / "run.log"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    work_queue: queue.Queue[dict | None] = queue.Queue()
    for item in plan:
        work_queue.put(item)
    for _ in range(concurrency):
        work_queue.put(None)

    results: list[dict] = []
    running: dict[str, dict] = {}
    lock = threading.Lock()

    def write_live_summary() -> None:
        summary_live_path.write_text(
            json.dumps(_summary(results, len(plan), run_dir, concurrency, timeout_seconds, list(running.values())), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def worker(worker_id: int) -> None:
        while True:
            item = work_queue.get()
            if item is None:
                return
            request_id = str(item.get("request_id") or "")
            with lock:
                running[request_id] = {
                    "worker_id": worker_id,
                    "request_id": request_id,
                    "symbol": item.get("symbol"),
                    "openid": item.get("openid"),
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                }
                write_live_summary()
            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"[worker {worker_id}] START {request_id} {item.get('symbol')} {item.get('name')} {item.get('openid')}\n")
            result = _run_one(repo, run_dir, item, timeout_seconds)
            with lock:
                running.pop(request_id, None)
                results.append(result)
                with results_path.open("a", encoding="utf-8") as results_file:
                    results_file.write(json.dumps(result, ensure_ascii=False) + "\n")
                with log_path.open("a", encoding="utf-8") as log:
                    log.write(
                        f"[worker {worker_id}] END {request_id} {result.get('symbol')} "
                        f"{result.get('status')} elapsed={result.get('elapsed_seconds')} "
                        f"date={result.get('market_date') or '-'} error={result.get('error_code') or '-'}\n"
                    )
                    if result.get("status") != "ok":
                        log.write(f"  detail={str(result.get('detail') or '')[:800]}\n")
                write_live_summary()

    log_path.write_text(
        f"run_id={run_id}\nrun_dir={run_dir}\nconcurrency={concurrency}\ntimeout_seconds={timeout_seconds}\ntotal={len(plan)}\n",
        encoding="utf-8",
    )
    write_live_summary()
    threads = [threading.Thread(target=worker, args=(idx + 1,), daemon=False) for idx in range(concurrency)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    final_summary = _summary(results, len(plan), run_dir, concurrency, timeout_seconds)
    summary_path.write_text(json.dumps(final_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_live_path.write_text(json.dumps(final_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(csv_path, results)
    return 0 if final_summary["failed"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--symbol", default="")
    parser.add_argument("--openid", default="")
    parser.add_argument("--raw-input", default="")
    parser.add_argument("--worker-output", default="")
    args = parser.parse_args()
    if args.worker:
        if not args.symbol or not args.openid or not args.worker_output:
            return 2
        return _run_worker(args)
    return _main_batch()


if __name__ == "__main__":
    raise SystemExit(main())
