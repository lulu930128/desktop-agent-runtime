from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import isoformat_utc, utc_now
from .study_adapter import DEFAULT_MAX_SNAPSHOT_BYTES, build_study_status


STUDY_SHADOW_REPORT_CONTRACT = "kuro.core.shadow.study.v1"









def build_study_shadow_report(
    file_path: str | Path,
    *,
    as_of: datetime,
    ttl_seconds: int = 3600,
    max_bytes: int = DEFAULT_MAX_SNAPSHOT_BYTES,
) -> dict[str, Any]:
    status = build_study_status(
        file_path,
        as_of=as_of,
        ttl_seconds=ttl_seconds,
        max_bytes=max_bytes,
    )
    return {
        "contract": STUDY_SHADOW_REPORT_CONTRACT,
        "generatedAt": status["generatedAt"],
        "sourceCount": 1,
        "items": [status["item"]],
    }




def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect one explicitly supplied Study snapshot with bounded metadata only.")
    parser.add_argument("--study-snapshot", required=True)
    parser.add_argument("--study-max-bytes", type=int, default=DEFAULT_MAX_SNAPSHOT_BYTES)
    parser.add_argument("--default-ttl-seconds", type=int, default=3600)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = build_study_shadow_report(args.study_snapshot, as_of=utc_now(),
            ttl_seconds=args.default_ttl_seconds, max_bytes=args.study_max_bytes)
    except Exception as exc:
        parser.exit(2, f"Kuro Core shadow probe failed: {type(exc).__name__}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
