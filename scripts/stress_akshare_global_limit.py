# encoding:utf-8
import argparse
import multiprocessing as mp
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from business.market.akshare_process_pool import _global_akshare_slot


def _worker(index: int, hold_seconds: float, queue) -> None:
    with _global_akshare_slot(30):
        queue.put(("enter", index, time.perf_counter()))
        time.sleep(hold_seconds)
        queue.put(("exit", index, time.perf_counter()))


def _max_active(events: list[tuple[str, int, float]]) -> int:
    active = 0
    max_seen = 0
    for event, _index, _timestamp in sorted(events, key=lambda item: (item[2], 0 if item[0] == "exit" else 1)):
        if event == "enter":
            active += 1
            max_seen = max(max_seen, active)
        elif event == "exit":
            active -= 1
    return max_seen


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=int, default=80)
    parser.add_argument("--hold-seconds", type=float, default=0.2)
    args = parser.parse_args()

    ctx = mp.get_context("spawn")
    queue = ctx.Queue()
    processes = [ctx.Process(target=_worker, args=(index, args.hold_seconds, queue)) for index in range(args.tasks)]
    started = time.perf_counter()
    for process in processes:
        process.start()
    events = []
    for _ in range(args.tasks * 2):
        events.append(queue.get(timeout=30))
    for process in processes:
        process.join(timeout=30)
    exit_codes = [process.exitcode for process in processes]
    payload = {
        "tasks": args.tasks,
        "hold_seconds": args.hold_seconds,
        "max_active": _max_active(events),
        "elapsed": round(time.perf_counter() - started, 3),
        "exit_codes": sorted(set(exit_codes)),
    }
    print(payload)
    return 0 if payload["max_active"] <= 30 and payload["exit_codes"] == [0] else 2


if __name__ == "__main__":
    raise SystemExit(main())
