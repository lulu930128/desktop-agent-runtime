"""Launcher-owned Core entrypoint; no credentials in command-line arguments."""
import argparse
import logging
import os
from pathlib import Path

from kuro_core.schedule_api import ScheduleServer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--timezone", default="UTC")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    server = ScheduleServer(args.db, port=args.port, token=os.environ.get("KURO_CORE_TOKEN", ""), instance_id=args.instance, default_timezone=args.timezone)
    try:
        server.start()
        server.stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
