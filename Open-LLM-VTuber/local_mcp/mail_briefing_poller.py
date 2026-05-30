from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import mail_tools_server


DEFAULT_INTERVAL_SECONDS = 900
MIN_INTERVAL_SECONDS = 300


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _print_json(payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(data + b"\n")
    sys.stdout.buffer.flush()


def _run_once(args: argparse.Namespace) -> dict:
    result = json.loads(
        mail_tools_server.mail_update_briefing(
            max_results=args.max_results,
            newer_than_days=args.newer_than_days,
            unread_only=not args.all_recent,
            pet_control_url=args.pet_control_url,
            include_spam_trash=False,
        )
    )
    return {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ok": bool(result.get("ok")),
        "account": result.get("account", ""),
        "query": result.get("query", ""),
        "resultSizeEstimate": result.get("resultSizeEstimate"),
        "messageCount": result.get("messageCount"),
        "briefing": result.get("briefing"),
        "error_type": result.get("error_type", ""),
        "error": result.get("error", ""),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Poll Gmail read-only summaries into the Kuro Briefing panel."
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=_env_int("KURO_MAIL_POLL_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS),
        help="Polling interval. Values below 300 are clamped unless --once is used.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=_env_int("KURO_MAIL_MAX_RESULTS", 12),
        help="Maximum Gmail messages to fetch per poll.",
    )
    parser.add_argument(
        "--newer-than-days",
        type=int,
        default=_env_int("KURO_MAIL_NEWER_THAN_DAYS", 7),
        help="Gmail newer_than window in days.",
    )
    parser.add_argument(
        "--all-recent",
        action="store_true",
        help="Fetch recent inbox mail instead of unread-only mail.",
    )
    parser.add_argument(
        "--pet-control-url",
        default=os.getenv("KURO_PET_CONTROL_URL", ""),
        help="Local Kuro pet control base URL. Defaults to http://127.0.0.1:23567.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one update and exit.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.once:
        args.interval_seconds = max(MIN_INTERVAL_SECONDS, args.interval_seconds)

    while True:
        _print_json(_run_once(args))
        if args.once:
            return 0
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
