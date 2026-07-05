# encoding:utf-8
import argparse
import json
import random
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_wechatmp_mixed_real_flow import (  # noqa: E402
    _patch_authorized_customer,
    _patch_wechat_uploads,
    _post_text,
    _sample_targets,
    _strip_xml_text,
)


MISFIRE_TEXTS = [
    "你好",
    "随便看看",
    "abc",
    "#",
    "##600519",
    "#不存在的标的XYZ",
    "000001",
    "1",
    "2",
    "0",
    "技术分析",
]


def _now_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _pending_count(channel, openid: str) -> int:
    cache = channel.cache_dict
    with cache._lock:
        results = cache._live_results_locked(openid) or []
        return len([item for item in results if item.replies])


def _running(channel, openid: str) -> bool:
    return openid in channel.running


def _numeric_msg_id(index: int) -> str:
    return f"9{index:06d}{int(time.time() * 1000)}"


def _pending_claim_targets(response_text: str) -> list[str]:
    text = str(response_text or "")
    targets = []
    seen = set()
    for match in re.finditer(r"msgmenucontent=([^&\"]+)&msgmenuid=pending_", text):
        target = unquote(match.group(1)).strip()
        if target and target not in seen:
            seen.add(target)
            targets.append(target)
    return targets


def _classify_response(response_text: str) -> str:
    text = str(response_text or "")
    if "正在处理，请稍候" in text:
        return "accepted_ack"
    if "结果已准备好" in text:
        return "ready_hit"
    if "暂不接受新的技术分析请求" in text:
        return "running_reject_new_hash"
    if "仍在运行" in text or "正在运行" in text:
        return "running_prompt"
    if text.startswith("[image:"):
        return "claim_image"
    if "当前没有待领取结果" in text:
        return "no_pending"
    if "请输入" in text:
        return "input_error"
    if "无法生成技术分析" in text:
        return "cannot_generate"
    if "暂时不可用" in text:
        return "data_or_system_unavailable"
    if text == "success":
        return "success_empty"
    return "other"


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _weighted_choice(rng: random.Random, weighted_actions: list[tuple[str, int]]) -> str:
    actions = [action for action, _weight in weighted_actions]
    weights = [weight for _action, weight in weighted_actions]
    return rng.choices(actions, weights=weights, k=1)[0]


def _active_user_bounds(total_users: int, min_active_users: int, max_active_users: int) -> tuple[int, int]:
    total = max(1, int(total_users or 1))
    if min_active_users <= 0 and max_active_users <= 0:
        return total, total
    minimum = max(1, min(total, int(min_active_users or 1)))
    maximum = max(minimum, min(total, int(max_active_users or total)))
    return minimum, maximum


class ChaosRunner:
    def __init__(self, args):
        self.args = args
        self.run_id = _now_id()
        self.run_dir = REPO_ROOT / "business_storage" / "tmp" / "wechatmp_chaos_real_flow" / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir.parent / "latest_run.txt").write_text(str(self.run_dir), encoding="utf-8")
        self.events_path = self.run_dir / "events.jsonl"
        self.summary_live_path = self.run_dir / "summary.live.json"
        self.summary_path = self.run_dir / "summary.json"
        self.rng = random.Random(args.seed or f"wechatmp-chaos-{self.run_id}")
        self.channel, self.fake_media = _patch_wechat_uploads()
        _patch_authorized_customer()
        self.users = [f"wechatmp_chaos_user_{idx + 1:03d}" for idx in range(args.users)]
        self.min_active_users, self.max_active_users = _active_user_bounds(
            len(self.users),
            args.min_active_users,
            args.max_active_users,
        )
        self.active_users = set(self.rng.sample(self.users, k=self.min_active_users))
        all_targets = _sample_targets(args.target_requests + args.extra_targets, f"wechatmp-chaos-targets-{self.run_id}")
        self.targets = all_targets[: args.target_requests]
        self.noise_targets = all_targets[args.target_requests :] or all_targets
        self.target_index = 0
        self.noise_target_index = 0
        self.event_index = 0
        self.stats = Counter()
        self.started_by_user = Counter()
        self.claimed_by_user = Counter()
        self.last_symbol_by_user = {}
        self.last_response_by_user = {}
        self.pending_targets_by_user = {}
        _write_json(self.run_dir / "plan.json", {
            "target_requests": args.target_requests,
            "users": self.users,
            "min_active_users": self.min_active_users,
            "max_active_users": self.max_active_users,
            "initial_active_users": sorted(self.active_users),
            "max_pending_per_user": args.max_pending_per_user,
            "targets": self.targets,
            "noise_target_count": len(self.noise_targets),
        })

    def send(self, openid: str, content: str, *, action: str, symbol: str = "") -> str:
        self.event_index += 1
        raw = _post_text(openid, content, _numeric_msg_id(self.event_index))
        response = _strip_xml_text(raw)
        category = _classify_response(response)
        pending_targets = _pending_claim_targets(response)
        if pending_targets:
            self.pending_targets_by_user[openid] = pending_targets
        self.stats[f"response.{category}"] += 1
        self.stats[f"action.{action}"] += 1
        if category == "accepted_ack":
            self.stats["technical.accepted"] += 1
            if action == "start_technical":
                self.stats["technical.target_accepted"] += 1
            elif action.startswith("new_hash"):
                self.stats["technical.noise_accepted"] += 1
            self.started_by_user[openid] += 1
            if symbol:
                self.last_symbol_by_user[openid] = symbol
        elif category == "ready_hit":
            self.stats["technical.ready_hit"] += 1
            if action == "start_technical":
                self.stats["technical.target_ready_hit"] += 1
        elif category == "claim_image":
            self.claimed_by_user[openid] += 1
        event = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "event_index": self.event_index,
            "openid": openid,
            "action": action,
            "content": content,
            "symbol": symbol,
            "response_category": category,
            "response": response[:500],
            "pending_claim_targets": pending_targets[:20],
            "running": _running(self.channel, openid),
            "pending_count": _pending_count(self.channel, openid),
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.last_response_by_user[openid] = event
        self.write_summary(live=True)
        return category

    def next_target(self) -> dict | None:
        if self.target_index >= len(self.targets):
            return None
        target = self.targets[self.target_index]
        self.target_index += 1
        return target

    def next_noise_target(self) -> dict | None:
        if not self.noise_targets:
            return None
        target = self.noise_targets[self.noise_target_index % len(self.noise_targets)]
        self.noise_target_index += 1
        return target

    def start_technical(self, openid: str) -> bool:
        target = self.next_target()
        if not target:
            return False
        symbol = str(target.get("code") or "")
        if not symbol:
            return False
        category = self.send(openid, f"#{symbol}", action="start_technical", symbol=symbol)
        self.stats["technical.target_sent"] += 1
        if category not in {"accepted_ack", "ready_hit"}:
            self.stats["technical.start_not_accepted"] += 1
        return category == "accepted_ack"

    def pending_claim_targets(self, openid: str) -> list[str]:
        targets = []
        summary = getattr(self.channel.cache_dict, "pending_summary", None)
        if callable(summary):
            try:
                targets = [str(item[0]) for item in summary(openid) if item and item[0]]
            except Exception:
                targets = []
        if targets:
            self.pending_targets_by_user[openid] = targets
            return targets
        return list(self.pending_targets_by_user.get(openid) or [])

    def claim_latest(self, openid: str, action: str) -> None:
        category = self.send(openid, "1", action=action)
        if category == "claim_image" or _pending_count(self.channel, openid) <= 0:
            return
        if self.rng.random() < self.args.code_claim_after_latest_fail_probability:
            self.claim_by_code(openid, f"{action}_then_code")

    def claim_by_code(self, openid: str, action: str) -> None:
        targets = self.pending_claim_targets(openid)
        if not targets:
            return
        target = self.rng.choice(targets)
        self.send(openid, target, action=action, symbol=target)

    def choose_user_behavior(self, openid: str) -> str:
        running = _running(self.channel, openid)
        pending = _pending_count(self.channel, openid)
        if running:
            return _weighted_choice(self.rng, [
                ("claim_latest", 3),
                ("plain", 3),
                ("new_hash", 3),
                ("misfire", 1),
            ])
        if pending:
            if pending >= self.args.max_pending_per_user:
                return _weighted_choice(self.rng, [
                    ("claim_by_code", max(self.args.claim_weight, 8)),
                    ("claim_latest", 2),
                    ("plain", 1),
                    ("misfire", 1),
                    ("skip", 1),
                ])
            return _weighted_choice(self.rng, [
                ("claim_by_code", self.args.claim_weight),
                ("claim_latest", max(1, self.args.claim_weight - 1)),
                ("new_hash", 2),
                ("plain", 2),
                ("misfire", 2),
                ("skip", self.args.skip_claim_weight),
            ])
        return self.rng.choice(["misfire", "skip"])

    def action_label(self, behavior: str, openid: str) -> str:
        if _running(self.channel, openid):
            return f"{behavior}_while_running"
        if _pending_count(self.channel, openid):
            return f"{behavior}_with_pending"
        return f"{behavior}_idle"

    def run_user_behavior(self, openid: str, behavior: str | None = None) -> None:
        choice = behavior or self.choose_user_behavior(openid)
        action = self.action_label(choice, openid)

        if choice == "skip":
            return
        if choice == "claim_latest":
            self.claim_latest(openid, action)
            return
        if choice == "claim_by_code":
            self.claim_by_code(openid, action)
            return
        if choice == "plain":
            self.send(openid, self.rng.choice(["你好", "现在怎么样", "结果呢", "再来一个"]), action=action)
            return
        if choice == "misfire":
            self.send(openid, self.rng.choice(MISFIRE_TEXTS), action=action)
            return
        if choice == "new_hash":
            target = self.next_noise_target()
            if not target:
                return
            symbol = str(target.get("code") or "")
            self.send(openid, f"#{symbol}", action=action, symbol=symbol)

    def available_start_users(self) -> list[str]:
        users = []
        for openid in self.active_user_list():
            if _running(self.channel, openid):
                continue
            if _pending_count(self.channel, openid) >= self.args.max_pending_per_user:
                continue
            users.append(openid)
        self.rng.shuffle(users)
        return users

    def active_user_list(self) -> list[str]:
        users = list(self.active_users)
        self.rng.shuffle(users)
        return users

    def rebalance_active_users(self) -> None:
        if self.min_active_users == self.max_active_users:
            return
        if self.rng.random() >= self.args.user_churn_probability:
            return
        active_count = len(self.active_users)
        can_add = active_count < self.max_active_users
        can_remove = active_count > self.min_active_users
        if can_add and (not can_remove or self.rng.random() < 0.55):
            inactive = [user for user in self.users if user not in self.active_users]
            if not inactive:
                return
            count = self.rng.randint(1, min(self.args.user_churn_burst, self.max_active_users - active_count, len(inactive)))
            self.active_users.update(self.rng.sample(inactive, k=count))
            self.stats["users.activated"] += count
            return
        if can_remove:
            removable = [user for user in self.active_users if not _running(self.channel, user)]
            if not removable:
                return
            count = self.rng.randint(1, min(self.args.user_churn_burst, active_count - self.min_active_users, len(removable)))
            for user in self.rng.sample(removable, k=count):
                self.active_users.discard(user)
            self.stats["users.deactivated"] += count

    def exercise_full_queues(self) -> None:
        full_users = [
            openid
            for openid in self.active_user_list()
            if not _running(self.channel, openid) and _pending_count(self.channel, openid) >= self.args.max_pending_per_user
        ]
        self.rng.shuffle(full_users)
        for openid in full_users[: max(1, min(self.args.chaos_burst, len(full_users)))]:
            self.run_user_behavior(openid)

    def write_summary(self, *, live: bool) -> None:
        pending_counts = {openid: _pending_count(self.channel, openid) for openid in self.users}
        running_users = [openid for openid in self.users if _running(self.channel, openid)]
        summary = {
            "run_dir": str(self.run_dir),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "target_requests": self.args.target_requests,
            "target_sent": int(self.stats["technical.target_sent"]),
            "target_accepted": int(self.stats["technical.target_accepted"]),
            "target_ready_hits": int(self.stats["technical.target_ready_hit"]),
            "target_not_accepted": int(self.stats["technical.start_not_accepted"]),
            "noise_accepted": int(self.stats["technical.noise_accepted"]),
            "accepted_technical": int(self.stats["technical.accepted"]),
            "ready_hits": int(self.stats["technical.ready_hit"]),
            "event_count": self.event_index,
            "total_user_count": len(self.users),
            "active_user_count": len(self.active_users),
            "min_active_users": self.min_active_users,
            "max_active_users": self.max_active_users,
            "running_count": len(running_users),
            "running_users": running_users[:50],
            "pending_total": sum(pending_counts.values()),
            "max_pending_per_user_observed": max(pending_counts.values() or [0]),
            "pending_counts": pending_counts,
            "stats": dict(self.stats),
            "media_upload_count": len(self.fake_media.uploads),
            "started_by_user": dict(self.started_by_user),
            "claimed_by_user": dict(self.claimed_by_user),
        }
        _write_json(self.summary_live_path if live else self.summary_path, summary)

    def run(self) -> int:
        start_time = time.time()
        while self.stats["technical.target_sent"] < self.args.target_requests:
            self.rebalance_active_users()
            elapsed = time.time() - start_time
            if elapsed > self.args.timeout_seconds:
                self.stats["runner.timeout_before_target"] += 1
                break

            available = self.available_start_users()
            if available:
                batch = available[: max(1, min(self.args.start_burst, len(available)))]
                for openid in batch:
                    if self.stats["technical.target_sent"] >= self.args.target_requests:
                        break
                    self.start_technical(openid)
                    for _ in range(self.rng.randint(0, self.args.max_immediate_chaos)):
                        self.run_user_behavior(openid)
            else:
                self.exercise_full_queues()
                active_users = self.active_user_list()
                for openid in self.rng.sample(active_users, k=min(len(active_users), self.args.chaos_burst)):
                    self.run_user_behavior(openid)
                time.sleep(self.args.sleep_seconds)

            active_users = self.active_user_list()
            for openid in self.rng.sample(active_users, k=min(len(active_users), self.args.chaos_burst)):
                if self.rng.random() < self.args.background_chaos_probability:
                    self.run_user_behavior(openid)
            time.sleep(self.args.sleep_seconds)

        drain_deadline = time.time() + self.args.drain_seconds
        while time.time() < drain_deadline:
            if not any(_running(self.channel, user) for user in self.users):
                break
            active_users = self.active_user_list()
            for openid in self.rng.sample(active_users, k=min(len(active_users), self.args.chaos_burst)):
                self.run_user_behavior(openid)
            time.sleep(max(1.0, self.args.sleep_seconds))

        for openid in self.users:
            while _pending_count(self.channel, openid) and self.rng.random() < self.args.final_claim_probability:
                self.run_user_behavior(openid, self.rng.choice(["claim_latest", "claim_by_code"]))
                time.sleep(0.1)

        self.write_summary(live=True)
        self.write_summary(live=False)
        print((self.summary_path).read_text(encoding="utf-8"))
        return 0 if self.stats["technical.target_sent"] >= self.args.target_requests else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-requests", type=int, default=1000)
    parser.add_argument("--users", type=int, default=30)
    parser.add_argument("--min-active-users", type=int, default=0)
    parser.add_argument("--max-active-users", type=int, default=0)
    parser.add_argument("--user-churn-probability", type=float, default=0.0)
    parser.add_argument("--user-churn-burst", type=int, default=5)
    parser.add_argument("--max-pending-per-user", type=int, default=15)
    parser.add_argument("--timeout-seconds", type=int, default=6 * 60 * 60)
    parser.add_argument("--drain-seconds", type=int, default=30 * 60)
    parser.add_argument("--extra-targets", type=int, default=500)
    parser.add_argument("--start-burst", type=int, default=5)
    parser.add_argument("--chaos-burst", type=int, default=8)
    parser.add_argument("--max-immediate-chaos", type=int, default=3)
    parser.add_argument("--sleep-seconds", type=float, default=0.5)
    parser.add_argument("--background-chaos-probability", type=float, default=0.45)
    parser.add_argument("--claim-weight", type=int, default=3)
    parser.add_argument("--skip-claim-weight", type=int, default=5)
    parser.add_argument("--final-claim-probability", type=float, default=0.35)
    parser.add_argument("--code-claim-after-latest-fail-probability", type=float, default=0.7)
    parser.add_argument("--seed", default="")
    args = parser.parse_args()

    from config import load_config

    load_config()
    runner = ChaosRunner(args)
    return runner.run()


if __name__ == "__main__":
    raise SystemExit(main())
