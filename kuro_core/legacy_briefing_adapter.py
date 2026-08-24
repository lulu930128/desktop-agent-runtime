from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Mapping

from .contracts import (
    AvailabilityStatus,
    ConnectionStatus,
    FreshnessStatus,
    Observation,
    parse_datetime,
)


DEFAULT_TTL_SECONDS = 60 * 60
MAX_TTL_SECONDS = 30 * 24 * 60 * 60


def source_status_observations(
    payload: Mapping[str, Any],
    *,
    received_at: datetime,
    ttl_by_source: Mapping[str, int] | None = None,
    default_ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> list[Observation]:
    """Convert legacy Briefing source status into shadow Core observations.

    No message body, attachment, market payload, or study record is copied.  The
    adapter intentionally captures only source health metadata needed to compare
    legacy and Core freshness semantics.
    """

    _validate_ttl("default_ttl_seconds", default_ttl_seconds)
    source = payload.get("snapshot") if isinstance(payload.get("snapshot"), Mapping) else payload
    if not isinstance(source, Mapping):
        raise TypeError("Briefing payload must be an object.")
    raw_statuses = source.get("sourceStatus")
    if raw_statuses is None:
        return []
    if not isinstance(raw_statuses, list):
        raise TypeError("sourceStatus must be a list.")

    fallback_observed_at = parse_datetime(source.get("updatedAt"), field_name="snapshot.updatedAt")
    ttl_overrides = dict(ttl_by_source or {})
    observations: list[Observation] = []
    for index, candidate in enumerate(raw_statuses):
        if not isinstance(candidate, Mapping):
            raise TypeError(f"sourceStatus[{index}] must be an object.")
        source_id = str(candidate.get("id") or candidate.get("source") or "").strip()
        if not source_id:
            raise ValueError(f"sourceStatus[{index}] requires id or source.")
        raw_status = str(candidate.get("status") or "unknown").strip().lower()
        observed_at = parse_datetime(
            candidate.get("updatedAt") or candidate.get("observedAt"),
            field_name=f"sourceStatus[{index}].updatedAt",
        ) or fallback_observed_at
        availability, freshness, connection = _status_dimensions(raw_status, observed_at)
        ttl_seconds = ttl_overrides.get(source_id, default_ttl_seconds)
        _validate_ttl(f"ttl_by_source[{source_id}]", ttl_seconds)
        valid_until = (
            observed_at + timedelta(seconds=ttl_seconds)
            if observed_at is not None and freshness is FreshnessStatus.CURRENT
            else None
        )
        limitations = _limitations(candidate)
        fingerprint = json.dumps(
            {
                "source": source_id,
                "status": raw_status,
                "observed_at": observed_at.isoformat() if observed_at else None,
                "limitations": limitations,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        idempotency_key = f"legacy:{hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()[:32]}"
        observations.append(
            Observation.create(
                integration_id=f"legacy.{_safe_identifier(source_id)}",
                kind="source_status",
                source_ref=f"briefing:source_status:{source_id}",
                title=f"{source_id} source status",
                summary=f"Legacy source reported status '{raw_status or 'unknown'}'.",
                observed_at=observed_at,
                received_at=received_at,
                valid_until=valid_until,
                availability=availability,
                declared_freshness=freshness,
                connection=connection,
                idempotency_key=idempotency_key,
                limitations=limitations,
                details={
                    "legacyStatus": raw_status or "unknown",
                    "snapshotDate": str(source.get("date") or "")[:40],
                },
            )
        )
    return observations


def _status_dimensions(
    raw_status: str,
    observed_at: datetime | None,
) -> tuple[AvailabilityStatus, FreshnessStatus, ConnectionStatus]:
    current = FreshnessStatus.CURRENT if observed_at is not None else FreshnessStatus.UNKNOWN
    if raw_status in {"connected", "healthy", "ok", "ready", "current"}:
        connection = (
            ConnectionStatus.CONNECTED
            if raw_status in {"connected", "healthy", "ok", "ready"}
            else ConnectionStatus.UNKNOWN
        )
        return AvailabilityStatus.AVAILABLE, current, connection
    if raw_status == "stale":
        return AvailabilityStatus.AVAILABLE, FreshnessStatus.STALE, ConnectionStatus.UNKNOWN
    if raw_status in {"partial", "warning"}:
        return AvailabilityStatus.PARTIAL, current, ConnectionStatus.UNKNOWN
    if raw_status == "missing":
        return AvailabilityStatus.MISSING, current, ConnectionStatus.UNKNOWN
    if raw_status in {"offline", "disconnected", "error", "failed"}:
        return AvailabilityStatus.OFFLINE, FreshnessStatus.UNKNOWN, ConnectionStatus.DISCONNECTED
    if raw_status in {"auth", "auth_required", "unauthorized"}:
        return (
            AvailabilityStatus.AUTH_REQUIRED,
            FreshnessStatus.UNKNOWN,
            ConnectionStatus.AUTH_REQUIRED,
        )
    return AvailabilityStatus.UNKNOWN, FreshnessStatus.UNKNOWN, ConnectionStatus.UNKNOWN


def _limitations(candidate: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[object] = []
    for key in ("limitations", "warnings"):
        value = candidate.get(key)
        if isinstance(value, list):
            values.extend(value)
        elif value:
            values.append(value)
    error = candidate.get("errorReason") or candidate.get("error")
    if error:
        values.append(error)
    return tuple(str(value).strip()[:500] for value in values if str(value).strip())


def _validate_ttl(field_name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    if value < 1 or value > MAX_TTL_SECONDS:
        raise ValueError(f"{field_name} must be between 1 and {MAX_TTL_SECONDS} seconds.")


def _safe_identifier(value: str) -> str:
    normalized = "".join(
        char.lower() if (char.isascii() and char.isalnum()) or char in "._:-" else "-"
        for char in value.strip()
    ).strip("-.")
    if not normalized:
        raise ValueError("Source id does not contain a safe identifier.")
    return normalized[:120]
