# encoding:utf-8
import argparse
import csv
import json
import os
import random
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from business.schema.db import connect, row_to_dict
from business.schema.tables import investment_stock_symbols


TYPE_ORDER = [
    ("a_share", "A股"),
    ("hk_stock", "港股"),
    ("us_stock", "美股"),
    ("index", "指数"),
    ("etf", "ETF"),
    ("convertible_bond", "可转债"),
    ("futures", "期货"),
]
DEFAULT_LIMIT_PER_TYPE = 50
DEFAULT_TIMEOUT_SECONDS = 600


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _sample_targets(asset_type: str, limit: int) -> list[dict]:
    table = investment_stock_symbols
    stmt = (
        select(table.c.code, table.c.name, table.c.market, table.c.ts_code, table.c.asset_type)
        .where(table.c.asset_type == asset_type)
        .order_by(table.c.code)
    )
    with connect() as conn:
        rows = [row_to_dict(row) for row in conn.execute(stmt).fetchall()]
    rng = random.Random(f"ta-full-chain-{asset_type}-20260703")
    rng.shuffle(rows)
    return rows[:limit]


def _truncate(value: str, limit: int = 3000) -> str:
    text = str(value or "")
    return text[-limit:] if len(text) > limit else text


def _worker_result(target: str) -> dict:
    from config import load_config
    from business.content.technical_analysis import run_technical_analysis

    load_config()
    started = time.time()
    result = run_technical_analysis("ta_full_chain_batch", f"{target} 技术分析")
    payload = asdict(result)
    payload["status"] = "ok" if result.success else "error"
    payload["elapsed_seconds"] = round(time.time() - started, 2)
    payload["error_code"] = result.error_code.value if result.error_code else ""
    payload["detail"] = _truncate(result.detail)
    payload["user_prompt"] = _truncate(result.user_prompt, 1000)
    return payload


def _run_worker(symbol: str, output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = _worker_result(symbol)
    except Exception as exc:
        payload = {
            "success": False,
            "status": "error",
            "elapsed_seconds": 0,
            "error_code": "",
            "detail": _truncate(str(exc)),
            "user_prompt": "",
        }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def _run_one(repo: Path, run_dir: Path, target: dict, timeout_seconds: int) -> dict:
    symbol = str(target.get("code") or "").strip()
    started = time.time()
    safe_symbol = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in symbol) or "target"
    worker_dir = run_dir / "workers" / str(target.get("asset_type") or "unknown")
    worker_output = worker_dir / f"{safe_symbol}.json"
    stdout_path = worker_dir / f"{safe_symbol}.stdout.log"
    stderr_path = worker_dir / f"{safe_symbol}.stderr.log"
    worker_dir.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--symbol",
        symbol,
        "--worker-output",
        str(worker_output),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo)
    env["PYTHONIOENCODING"] = "utf-8"
    base = {
        "asset_type": str(target.get("asset_type") or ""),
        "symbol": symbol,
        "name": str(target.get("name") or ""),
        "market": str(target.get("market") or ""),
        "ts_code": str(target.get("ts_code") or ""),
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
        if worker_output.exists():
            payload = json.loads(worker_output.read_text(encoding="utf-8"))
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


def _summary(rows: list[dict], run_dir: Path, limit: int, timeout_seconds: int, current: dict | None = None) -> dict:
    summary = {
        "run_dir": str(run_dir),
        "limit_per_type": limit,
        "timeout_seconds": timeout_seconds,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "total_done": len(rows),
        "total_planned_max": limit * len(TYPE_ORDER),
        "ok": sum(1 for row in rows if row.get("status") == "ok"),
        "failed": sum(1 for row in rows if row.get("status") != "ok"),
        "current": current or {},
        "by_type": {},
    }
    for asset_type, label in TYPE_ORDER:
        type_rows = [row for row in rows if row.get("asset_type") == asset_type]
        summary["by_type"][asset_type] = {
            "label": label,
            "done": len(type_rows),
            "ok": sum(1 for row in type_rows if row.get("status") == "ok"),
            "failed": sum(1 for row in type_rows if row.get("status") != "ok"),
        }
    return summary


def _write_csv(csv_path: Path, rows: list[dict]) -> None:
    fields = [
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
        "detail",
        "user_prompt",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})


def _load_existing_results(results_path: Path) -> list[dict]:
    rows = []
    if not results_path.exists():
        return rows
    for line in results_path.read_text(encoding="utf-8", errors="replace").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            item = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _result_key(row: dict) -> tuple[str, str]:
    return (str(row.get("asset_type") or ""), str(row.get("symbol") or ""))


def _main_batch() -> int:
    repo = _repo_root()
    limit = int(os.environ.get("TA_FULL_CHAIN_LIMIT_PER_TYPE", DEFAULT_LIMIT_PER_TYPE))
    timeout_seconds = int(os.environ.get("TA_FULL_CHAIN_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    resume_run_dir = str(os.environ.get("TA_FULL_CHAIN_RESUME_RUN_DIR") or "").strip()
    if resume_run_dir:
        run_dir = Path(resume_run_dir).resolve()
        run_id = run_dir.name
    else:
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = repo / "business_storage" / "tmp" / "ta_full_chain_batch" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    parent_dir = run_dir.parent
    (parent_dir / "latest_run.txt").write_text(str(run_dir), encoding="utf-8")

    log_path = run_dir / "run.log"
    results_path = run_dir / "results.jsonl"
    live_summary_path = run_dir / "summary.live.json"
    final_summary_path = run_dir / "summary.json"
    csv_path = run_dir / "results.csv"
    rows: list[dict] = _load_existing_results(results_path)
    completed = {_result_key(row) for row in rows}

    with log_path.open("a", encoding="utf-8") as log, results_path.open("a", encoding="utf-8") as results_file:
        mode = "resume" if resume_run_dir else "new"
        log.write(
            f"run_id={run_id}\nrun_dir={run_dir}\nmode={mode}\n"
            f"loaded_existing_results={len(rows)}\nlimit_per_type={limit}\ntimeout_seconds={timeout_seconds}\n"
        )
        log.flush()
        live_summary_path.write_text(
            json.dumps(_summary(rows, run_dir, limit, timeout_seconds), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for asset_type, label in TYPE_ORDER:
            targets = _sample_targets(asset_type, limit)
            log.write(f"\n[{datetime.now().isoformat(timespec='seconds')}] START {asset_type} {label} count={len(targets)}\n")
            log.flush()
            for index, target in enumerate(targets, 1):
                key = (asset_type, str(target.get("code") or ""))
                if key in completed:
                    log.write(f"[{asset_type} {index}/{len(targets)}] SKIP completed {target.get('code')} {target.get('name')}\n")
                    log.flush()
                    continue
                current = {
                    "asset_type": asset_type,
                    "index": index,
                    "count": len(targets),
                    "symbol": target.get("code"),
                    "name": target.get("name"),
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                }
                live_summary_path.write_text(
                    json.dumps(_summary(rows, run_dir, limit, timeout_seconds, current), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                log.write(f"[{asset_type} {index}/{len(targets)}] {target.get('code')} {target.get('name')}\n")
                log.flush()
                result = _run_one(repo, run_dir, target, timeout_seconds)
                rows.append(result)
                completed.add(_result_key(result))
                results_file.write(json.dumps(result, ensure_ascii=False) + "\n")
                results_file.flush()
                live_summary_path.write_text(
                    json.dumps(_summary(rows, run_dir, limit, timeout_seconds), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                log.write(
                    f"  -> {result.get('status')} elapsed={result.get('elapsed_seconds')} "
                    f"date={result.get('market_date') or '-'} card={result.get('signal_card_path') or '-'} "
                    f"cache={result.get('cache_hit')}\n"
                )
                if result.get("status") != "ok":
                    log.write(f"     error_code={result.get('error_code') or '-'} detail={str(result.get('detail') or '')[:800]}\n")
                log.flush()
            log.write(f"[{datetime.now().isoformat(timespec='seconds')}] END {asset_type}\n")
            log.flush()

    final_summary = _summary(rows, run_dir, limit, timeout_seconds)
    final_summary_path.write_text(json.dumps(final_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    live_summary_path.write_text(json.dumps(final_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(csv_path, rows)
    return 0 if final_summary["failed"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--symbol", default="")
    parser.add_argument("--worker-output", default="")
    args = parser.parse_args()
    if args.worker:
        if not args.symbol or not args.worker_output:
            return 2
        return _run_worker(args.symbol, Path(args.worker_output))
    return _main_batch()


if __name__ == "__main__":
    raise SystemExit(main())
