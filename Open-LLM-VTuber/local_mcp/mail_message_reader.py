from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import mail_tools_server


def _print_json(payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(data + b"\n")
    sys.stdout.buffer.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read one Gmail message detail for Kuro Briefing.")
    parser.add_argument("--message-id", required=True, help="Gmail message id to read.")
    parser.add_argument(
        "--max-body-chars",
        type=int,
        default=20000,
        help="Maximum plain-text body characters returned to the dashboard.",
    )
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        payload = json.loads(
            mail_tools_server.mail_get_message_detail(
                message_id=args.message_id,
                max_body_chars=args.max_body_chars,
            )
        )
        _print_json(payload)
        return 0 if payload.get("ok") else 1
    except Exception as exc:
        _print_json(
            {
                "ok": False,
                "error_type": "mail_message_reader_failed",
                "error": str(exc),
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
