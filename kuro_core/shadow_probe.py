from __future__ import annotations

import argparse
import ipaddress
import json
from datetime import datetime
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse
from urllib.request import urlopen

from .contracts import isoformat_utc, utc_now
from .legacy_briefing_adapter import source_status_observations


SHADOW_REPORT_CONTRACT = "kuro.core.shadow.source-status.v1"
DEFAULT_BRIEFING_URL = "http://127.0.0.1:23567/briefing"


def require_loopback_url(value: str) -> str:
    normalized = str(value or "").strip()
    parsed = urlparse(normalized)
    if parsed.scheme != "http" or not parsed.hostname:
        raise ValueError("Shadow probe URL must use http and include a host.")
    if parsed.username or parsed.password:
        raise ValueError("Shadow probe URL cannot contain credentials.")
    if parsed.path.rstrip("/") != "/briefing" or parsed.query or parsed.fragment:
        raise ValueError("Shadow probe URL must target the exact /briefing path without query or fragment.")
    if parsed.path.rstrip("/") != "/briefing" or parsed.query or parsed.fragment:
        raise ValueError("Shadow probe URL must target the exact /briefing path without query or fragment.")
    host = parsed.hostname.lower()
    if host != "localhost":
        try:
            if not ipaddress.ip_address(host).is_loopback:
                raise ValueError("Shadow probe URL must target a loopback address.")
        except ValueError as exc:
            if "loopback address" in str(exc):
                raise
            raise ValueError("Shadow probe URL must target a loopback address.") from exc
    return normalized


def fetch_briefing(url: str, *, timeout_seconds: float) -> dict[str, Any]:
    safe_url = require_loopback_url(url)
    if timeout_seconds <= 0 or timeout_seconds > 30:
        raise ValueError("timeout_seconds must be greater than 0 and at most 30.")
    with urlopen(safe_url, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Briefing endpoint must return a JSON object.")
    return payload


def build_shadow_report(
    payload: Mapping[str, Any],
    *,
    as_of: datetime,
    ttl_by_source: Mapping[str, int] | None = None,
    default_ttl_seconds: int = 3600,
) -> dict[str, Any]:
    observations = source_status_observations(
        payload,
        received_at=as_of,
        ttl_by_source=ttl_by_source,
        default_ttl_seconds=default_ttl_seconds,
    )
    items = [
        {
            "integrationId": observation.integration_id,
            "connection": observation.connection.value,
            "availability": observation.availability.value,
            "freshness": observation.effective_freshness(as_of=as_of).value,
            "status": observation.data_status(as_of=as_of).value,
            "observedAt": isoformat_utc(observation.observed_at),
            "validUntil": isoformat_utc(observation.valid_until),
            "limitationCount": len(observation.limitations),
        }
        for observation in observations
    ]
    return {
        "contract": SHADOW_REPORT_CONTRACT,
        "generatedAt": isoformat_utc(as_of),
        "sourceCount": len(items),
        "items": items,
    }


def parse_ttl_overrides(values: Sequence[str]) -> dict[str, int]:
    overrides: dict[str, int] = {}
    for value in values:
        source_id, separator, raw_seconds = str(value or "").partition("=")
        source_id = source_id.strip()
        if not separator or not source_id or not raw_seconds.strip():
            raise ValueError("Each --source-ttl value must use SOURCE=SECONDS.")
        try:
            seconds = int(raw_seconds)
        except ValueError as exc:
            raise ValueError(f"Invalid TTL seconds for source '{source_id}'.") from exc
        overrides[source_id] = seconds
    return overrides


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read Kuro's loopback Briefing source health and print a private-data-free shadow report."
    )
    parser.add_argument("--url", default=DEFAULT_BRIEFING_URL)
    parser.add_argument("--timeout-seconds", type=float, default=3.0)
    parser.add_argument("--default-ttl-seconds", type=int, default=3600)
    parser.add_argument(
        "--source-ttl",
        action="append",
        default=[],
        metavar="SOURCE=SECONDS",
        help="Override freshness TTL for one source. May be specified more than once.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = fetch_briefing(args.url, timeout_seconds=args.timeout_seconds)
        report = build_shadow_report(
            payload,
            as_of=utc_now(),
            ttl_by_source=parse_ttl_overrides(args.source_ttl),
            default_ttl_seconds=args.default_ttl_seconds,
        )
    except Exception as exc:
        parser.exit(2, f"Kuro Core shadow probe failed: {exc}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
