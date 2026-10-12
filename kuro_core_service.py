"""Launcher-owned Core entrypoint; no credentials in command-line arguments."""
import argparse
import logging
import os
from pathlib import Path

from kuro_core.core_app import CoreApplication


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument("--study-enabled", action="store_true")
    parser.add_argument("--study-snapshot", type=Path)
    parser.add_argument("--study-ttl-seconds", type=int, default=3600)
    parser.add_argument("--study-max-bytes", type=int, default=2097152)
    parser.add_argument("--mail-enabled", action="store_true")
    parser.add_argument("--mail-status", type=Path)
    parser.add_argument("--mail-work", type=Path)
    parser.add_argument("--mail-work-max-bytes", type=int, default=2097152)
    parser.add_argument("--mail-ttl-seconds", type=int, default=1800)
    parser.add_argument("--mail-max-bytes", type=int, default=65536)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    server = CoreApplication(
        args.db, port=args.port, token=os.environ.get("KURO_CORE_TOKEN", ""),
        instance_id=args.instance, default_timezone=args.timezone,
        study_enabled=args.study_enabled, study_snapshot_path=args.study_snapshot,
        study_ttl_seconds=args.study_ttl_seconds, study_max_bytes=args.study_max_bytes,
        mail_enabled=args.mail_enabled, mail_status_path=args.mail_status,
        mail_work_path=args.mail_work, mail_work_max_bytes=args.mail_work_max_bytes,
        mail_ttl_seconds=args.mail_ttl_seconds, mail_max_bytes=args.mail_max_bytes)
    try:
        server.start()
        server.stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
