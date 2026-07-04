# encoding:utf-8
import csv
import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from business.content.stock_resolver import get_tushare_token
from business.market.trading_calendar import trading_calendar_from_config
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
DEFAULT_TIMEOUT_SECONDS = 180


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
    rng = random.Random(f"ta-batch-{asset_type}-20260703")
    rng.shuffle(rows)
    return rows[:limit]


def _parse_report(report_path: Path) -> dict:
    try:
        text = report_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    analysis_date = ""
    data_start = ""
    data_end = ""
    for line in text.splitlines():
        if "分析日期" in line:
            match = re.search(r"分析日期:\*\*\s*(\d{4}-\d{2}-\d{2})", line)
            if not match:
                match = re.search(r"分析日期[:：]\s*(\d{4}-\d{2}-\d{2})", line)
            if match:
                analysis_date = match.group(1)
        if "数据范围" in line:
            match = re.search(r"(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})", line)
            if match:
                data_start, data_end = match.group(1), match.group(2)
    return {
        "analysis_date": analysis_date,
        "data_start": data_start,
        "data_end": data_end,
    }


def _latest_output(output_dir: Path, pattern: str) -> Path | None:
    files = sorted(output_dir.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _calendar_env() -> dict[str, str]:
    env = {}
    try:
        calendar = trading_calendar_from_config()
        accepted_dates = calendar.accepted_market_dates()
        if calendar.enabled and accepted_dates:
            env["TECHNICAL_ANALYSIS_TRADING_CALENDAR_ENABLED"] = "1"
            env["TECHNICAL_ANALYSIS_ACCEPTED_MARKET_DATES"] = ",".join(accepted_dates)
            env["TECHNICAL_ANALYSIS_EXPECTED_MARKET_DATE"] = accepted_dates[-1]
        else:
            env["TECHNICAL_ANALYSIS_TRADING_CALENDAR_ENABLED"] = "0"
    except Exception:
        env["TECHNICAL_ANALYSIS_TRADING_CALENDAR_ENABLED"] = "0"
    return env


def _run_one(repo: Path, base_output: Path, target: dict, timeout_seconds: int) -> dict:
    symbol = str(target.get("code") or "").strip()
    name = str(target.get("name") or "").strip()
    asset_type = str(target.get("asset_type") or "").strip()
    market = str(target.get("market") or "").strip()
    ts_code = str(target.get("ts_code") or "").strip()
    safe_symbol = re.sub(r"[^A-Za-z0-9_.-]+", "_", symbol) or "target"
    output_dir = base_output / asset_type / safe_symbol
    output_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(repo)
    token = str(get_tushare_token() or "").strip()
    if token:
        env["TUSHARE_TOKEN"] = token
    env.update(_calendar_env())

    command = [
        sys.executable,
        str(repo / "builtin" / "components" / "technical-analysis" / "scripts" / "analyze_universal.py"),
        "--symbol",
        symbol,
        "--output",
        str(output_dir),
    ]
    if name:
        command.extend(["--name", name])
    if asset_type:
        command.extend(["--asset-type", asset_type])
    if market:
        command.extend(["--market", market])
    if ts_code:
        command.extend(["--ts-code", ts_code])

    started = time.time()
    result = {
        "asset_type": asset_type,
        "symbol": symbol,
        "name": name,
        "market": market,
        "ts_code": ts_code,
        "status": "error",
        "elapsed_seconds": 0,
        "analysis_date": "",
        "data_start": "",
        "data_end": "",
        "report_path": "",
        "chart_path": "",
        "error": "",
        "stdout_tail": "",
    }
    try:
        completed = subprocess.run(
            command,
            cwd=str(repo),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
        result["elapsed_seconds"] = round(time.time() - started, 2)
        report = _latest_output(output_dir, "*技术分析报告*.md")
        chart = _latest_output(output_dir, "*_TA_*.png")
        if completed.returncode == 0 and report and chart:
            result["status"] = "ok"
            result["report_path"] = str(report)
            result["chart_path"] = str(chart)
            result.update(_parse_report(report))
        else:
            result["error"] = (completed.stderr or completed.stdout or f"exit={completed.returncode}")[-3000:]
        result["stdout_tail"] = (completed.stdout or "")[-2000:]
    except subprocess.TimeoutExpired as exc:
        result["elapsed_seconds"] = round(time.time() - started, 2)
        result["status"] = "timeout"
        result["error"] = f"timeout after {timeout_seconds}s"
        result["stdout_tail"] = str(exc.stdout or "")[-2000:]
    except Exception as exc:
        result["elapsed_seconds"] = round(time.time() - started, 2)
        result["error"] = str(exc)
    return result


def _write_csv(csv_path: Path, rows: list[dict]) -> None:
    fields = [
        "asset_type",
        "symbol",
        "name",
        "market",
        "ts_code",
        "status",
        "elapsed_seconds",
        "analysis_date",
        "data_start",
        "data_end",
        "report_path",
        "chart_path",
        "error",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})


def main() -> int:
    repo = _repo_root()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    limit = int(os.environ.get("TA_BATCH_LIMIT_PER_TYPE", DEFAULT_LIMIT_PER_TYPE))
    timeout_seconds = int(os.environ.get("TA_BATCH_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    base_output = repo / "business_storage" / "tmp" / "ta_type_batch" / run_id
    base_output.mkdir(parents=True, exist_ok=True)
    results_path = base_output / "results.jsonl"
    summary_path = base_output / "summary.json"
    csv_path = base_output / "results.csv"
    log_path = base_output / "run.log"
    pointer_path = repo / "business_storage" / "tmp" / "ta_type_batch" / "latest_run.txt"
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_path.write_text(str(base_output), encoding="utf-8")

    all_results = []
    with log_path.open("a", encoding="utf-8") as log, results_path.open("a", encoding="utf-8") as results_file:
        log.write(f"run_id={run_id}\nbase_output={base_output}\nlimit_per_type={limit}\ntimeout_seconds={timeout_seconds}\n")
        log.flush()
        for asset_type, label in TYPE_ORDER:
            targets = _sample_targets(asset_type, limit)
            log.write(f"\n[{datetime.now().isoformat(timespec='seconds')}] START {asset_type} {label} count={len(targets)}\n")
            log.flush()
            for index, target in enumerate(targets, 1):
                log.write(f"[{asset_type} {index}/{len(targets)}] {target.get('code')} {target.get('name')}\n")
                log.flush()
                result = _run_one(repo, base_output, target, timeout_seconds)
                all_results.append(result)
                results_file.write(json.dumps(result, ensure_ascii=False) + "\n")
                results_file.flush()
                log.write(
                    f"  -> {result['status']} elapsed={result['elapsed_seconds']} "
                    f"date={result.get('analysis_date') or '-'} range={result.get('data_start') or '-'}~{result.get('data_end') or '-'}\n"
                )
                if result["status"] != "ok":
                    log.write(f"     error={result.get('error', '')[:500]}\n")
                log.flush()
            type_rows = [row for row in all_results if row["asset_type"] == asset_type]
            ok = sum(1 for row in type_rows if row["status"] == "ok")
            log.write(f"[{datetime.now().isoformat(timespec='seconds')}] END {asset_type} ok={ok}/{len(type_rows)}\n")
            log.flush()

    summary = {
        "run_id": run_id,
        "base_output": str(base_output),
        "limit_per_type": limit,
        "total": len(all_results),
        "ok": sum(1 for row in all_results if row["status"] == "ok"),
        "failed": sum(1 for row in all_results if row["status"] != "ok"),
        "by_type": {},
    }
    for asset_type, _label in TYPE_ORDER:
        rows = [row for row in all_results if row["asset_type"] == asset_type]
        summary["by_type"][asset_type] = {
            "total": len(rows),
            "ok": sum(1 for row in rows if row["status"] == "ok"),
            "failed": sum(1 for row in rows if row["status"] != "ok"),
        }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(csv_path, all_results)
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
