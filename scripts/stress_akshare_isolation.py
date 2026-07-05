# encoding:utf-8
import argparse
import concurrent.futures
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = REPO_ROOT / "business_storage" / "tmp" / "akshare_isolation_stress"

SYMBOLS = [
    "600519",
    "000001",
    "300750",
    "601318",
    "000333",
    "002594",
    "300760",
    "600036",
    "601888",
    "000858",
]


JS_SNIPPET = """
var out = 0;
for (var i = 0; i < 20000; i++) {
  out += Math.sqrt(i % 997);
}
out;
"""


def _now_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_once(index: int) -> dict:
    import akshare as ak

    symbol = SYMBOLS[index % len(SYMBOLS)]
    started = time.time()
    frame = ak.stock_zh_a_hist(symbol=symbol, period="daily", adjust="")
    elapsed = time.time() - started
    rows = 0 if frame is None else len(frame)
    latest = ""
    if rows:
        latest = str(frame.iloc[-1].get("日期", "") or frame.iloc[-1].get("date", ""))
    return {
        "index": index,
        "symbol": symbol,
        "rows": rows,
        "latest": latest,
        "elapsed": round(elapsed, 3),
    }


def _mini_racer_once(index: int) -> dict:
    from py_mini_racer import MiniRacer

    started = time.time()
    ctx = MiniRacer()
    value = ctx.eval(JS_SNIPPET)
    return {
        "index": index,
        "value": round(float(value), 3),
        "elapsed": round(time.time() - started, 3),
    }


def _task_func(kind: str):
    if kind == "mini_racer":
        return _mini_racer_once
    return _fetch_once


def _run_threaded(tasks: int, concurrency: int, kind: str) -> dict:
    started = time.time()
    results = []
    errors = []
    task_func = _task_func(kind)
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(task_func, idx) for idx in range(tasks)]
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                errors.append(repr(exc))
    return {
        "mode": "threaded",
        "kind": kind,
        "tasks": tasks,
        "concurrency": concurrency,
        "ok": len(results),
        "errors": errors[:20],
        "elapsed": round(time.time() - started, 3),
        "sample": results[:5],
    }


def _run_process_pool(tasks: int, concurrency: int, kind: str) -> dict:
    started = time.time()
    results = []
    errors = []
    task_func = _task_func(kind)
    with concurrent.futures.ProcessPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(task_func, idx) for idx in range(tasks)]
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                errors.append(repr(exc))
    return {
        "mode": "process_pool",
        "kind": kind,
        "tasks": tasks,
        "concurrency": concurrency,
        "ok": len(results),
        "errors": errors[:20],
        "elapsed": round(time.time() - started, 3),
        "sample": results[:5],
    }


def _child_main(args) -> int:
    if args.mode == "threaded":
        payload = _run_threaded(args.tasks, args.concurrency, args.kind)
    else:
        payload = _run_process_pool(args.tasks, args.concurrency, args.kind)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not payload["errors"] and payload["ok"] == args.tasks else 2


def _run_child(mode: str, tasks: int, concurrency: int, kind: str, run_dir: Path, timeout: int) -> dict:
    stem = f"{kind}_{mode}_c{concurrency}_t{tasks}"
    stdout_path = run_dir / f"{stem}.stdout.log"
    stderr_path = run_dir / f"{stem}.stderr.log"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--child",
        "--mode",
        mode,
        "--kind",
        kind,
        "--tasks",
        str(tasks),
        "--concurrency",
        str(concurrency),
    ]
    started = time.time()
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        try:
            completed = subprocess.run(
                command,
                cwd=str(REPO_ROOT),
                stdout=stdout,
                stderr=stderr,
                timeout=timeout,
                check=False,
            )
            exit_code = completed.returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            exit_code = -1
            timed_out = True
    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
    parsed = None
    if stdout_text.strip().startswith("{"):
        try:
            parsed = json.loads(stdout_text)
        except json.JSONDecodeError:
            parsed = None
    return {
        "mode": mode,
        "kind": kind,
        "tasks": tasks,
        "concurrency": concurrency,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "elapsed": round(time.time() - started, 3),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "parsed": parsed,
        "stderr_tail": stderr_text[-1200:],
    }


def _parent_main(args) -> int:
    run_dir = RUN_ROOT / _now_id()
    run_dir.mkdir(parents=True, exist_ok=True)
    (RUN_ROOT / "latest_run.txt").write_text(str(run_dir), encoding="utf-8")

    plan = []
    if args.direct_10:
        plan.append(("threaded", args.tasks, 10, args.kind))
    for concurrency in args.threaded_concurrency:
        plan.append(("threaded", args.tasks, concurrency, args.kind))
    for concurrency in args.process_concurrency:
        plan.append(("process_pool", args.tasks, concurrency, args.kind))

    results = []
    for mode, tasks, concurrency, kind in plan:
        item = _run_child(mode, tasks, concurrency, kind, run_dir, args.timeout_seconds)
        results.append(item)
        _write_json(run_dir / "summary.live.json", {"run_dir": str(run_dir), "results": results})

    summary = {"run_dir": str(run_dir), "results": results}
    _write_json(run_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--mode", choices=["threaded", "process_pool"], default="threaded")
    parser.add_argument("--kind", choices=["akshare_hist", "mini_racer"], default="akshare_hist")
    parser.add_argument("--tasks", type=int, default=30)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--direct-10", action="store_true")
    parser.add_argument("--threaded-concurrency", type=int, nargs="*", default=[])
    parser.add_argument("--process-concurrency", type=int, nargs="*", default=[5, 10, 20])
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()
    if args.child:
        return _child_main(args)
    return _parent_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
