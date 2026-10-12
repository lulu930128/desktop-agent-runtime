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
from mail_status_handoff import _commit_lock, MailStatusWriteError


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
        mail_tools_server.mail_refresh(
            max_results=args.max_results,
            newer_than_days=args.newer_than_days,
            unread_only=not args.all_recent,
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
        "handoff": result.get("handoff"),
        "workHandoff": result.get("workHandoff"),
        "error_type": result.get("error_type", ""),
        "error": result.get("error", ""),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Poll Gmail read-only summaries into bounded Core handoffs."
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
        "--once",
        action="store_true",
        help="Run one update and exit.",
    )
    return parser


def run_loop(args):
    last_run = None
    while True:
        # Reload the existing canonical preferences; no second settings truth.
        preferences = mail_tools_server._load_mail_preferences()
        enabled = os.getenv("KURO_MAIL_BRIEFING_AUTO", "1") != "0" and preferences["autoRefresh"]
        interval = max(MIN_INTERVAL_SECONDS, preferences["intervalSeconds"])
        now = time.monotonic()
        if enabled and (last_run is None or now - last_run >= interval):
            _print_json(_run_once(args))
            last_run = time.monotonic()
        if not enabled:
            last_run = None
        time.sleep(1)


def main() -> int:
    args = build_parser().parse_args()
    if args.once:
        _print_json(_run_once(args))
        return 0
    # Single Launcher-owned process; OS releases the lock even on crash.
    # Manual --once refresh is not a second long-running poller.
    root = mail_tools_server.PRIVATE_DIR
    root.mkdir(parents=True, exist_ok=True)
    try:
        with _commit_lock(root / "mail_poller.lock", timeout=0.05):
            run_loop(args)
    except MailStatusWriteError:
        _print_json({"ok": False, "error_type": "mail_poller_already_owned"})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
