#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]

STATUS_CODE = r"""
import json
from app.db.session import SessionLocal, get_redis_client
from app.services.app_settings import get_autoscaler_settings

STATUS_KEY = "nextboo:autoscaler:status"
WORKER_KEY_PATTERN = "nextboo:workers:active:*"

redis = get_redis_client()
with SessionLocal() as db:
    settings = get_autoscaler_settings(db)

status = redis.hgetall(STATUS_KEY)
active_workers = sorted(key.removeprefix("nextboo:workers:active:") for key in redis.keys(WORKER_KEY_PATTERN))

print("Autoscaler settings")
print(json.dumps(settings, indent=2, sort_keys=True))
print()
print("Runtime status")
print(json.dumps({
    "queue_depth": int(status.get("queue_depth") or 0),
    "current_worker_count": int(status.get("current_worker_count") or len(active_workers)),
    "recommended_worker_count": int(status.get("recommended_worker_count") or settings["autoscaler_min_workers"]),
    "last_scale_action": status.get("last_scale_action") or "",
    "last_scale_at": status.get("last_scale_at") or "",
    "last_error": status.get("last_error") or "",
    "active_workers": json.loads(status["active_workers"]) if status.get("active_workers") else active_workers,
}, indent=2, sort_keys=True))
"""

UPDATE_CODE = r"""
import json
from app.db.session import SessionLocal
from app.services.app_settings import update_autoscaler_settings

updates = json.loads({updates_json!r})

with SessionLocal() as db:
    settings = update_autoscaler_settings(db, updates)

print("Autoscaler settings updated.")
print(json.dumps(settings, indent=2, sort_keys=True))
"""


def run_backend_python(code: str) -> None:
    subprocess.run(
        ["docker", "compose", "exec", "-T", "backend", "python", "-c", code],
        cwd=ROOT_DIR,
        check=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage NextBoo autoscaler settings.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show autoscaler settings and runtime status.")

    enable_parser = subparsers.add_parser("enable", help="Enable autoscaling.")
    enable_parser.set_defaults(enable=True)

    disable_parser = subparsers.add_parser("disable", help="Disable autoscaling.")
    disable_parser.set_defaults(enable=False)

    set_parser = subparsers.add_parser("set", help="Update autoscaler tuning values.")
    set_parser.add_argument("--jobs-per-worker", type=int)
    set_parser.add_argument("--min-workers", type=int)
    set_parser.add_argument("--max-workers", type=int)
    set_parser.add_argument("--poll-seconds", type=int)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "status":
        run_backend_python(STATUS_CODE)
        return

    updates: dict[str, int | bool] = {}
    if args.command == "enable":
        updates["autoscaler_enabled"] = True
    elif args.command == "disable":
        updates["autoscaler_enabled"] = False
    elif args.command == "set":
        if args.jobs_per_worker is not None:
            updates["autoscaler_jobs_per_worker"] = max(args.jobs_per_worker, 1)
        if args.min_workers is not None:
            updates["autoscaler_min_workers"] = max(args.min_workers, 1)
        if args.max_workers is not None:
            updates["autoscaler_max_workers"] = max(args.max_workers, 1)
        if args.poll_seconds is not None:
            updates["autoscaler_poll_seconds"] = max(args.poll_seconds, 5)

    if not updates:
        print("No changes requested.")
        return

    run_backend_python(UPDATE_CODE.format(updates_json=__import__("json").dumps(updates)))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
