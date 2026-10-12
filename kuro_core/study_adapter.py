from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from .handoff import HandoffReadError, read_json_handoff

from .contracts import (
    AvailabilityStatus,
    ConnectionStatus,
    FreshnessStatus,
    Observation,
    isoformat_utc,
    parse_datetime,
)

STUDY_SNAPSHOT_SCHEMA_VERSION = 1
STUDY_STATUS_CONTRACT = "kuro.core.integration.study.v1"
MAX_TTL_SECONDS = 30 * 24 * 60 * 60
DEFAULT_MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024
STUDY_SAFE_DETAIL_KEYS = (
    "snapshotPresent",
    "schemaVersion",
    "studyType",
    "vocabTotal",
    "vocabDue",
    "vocabWithMistakes",
    "todayReview",
    "todayFocus",
    "todayNew",
)


def study_snapshot_observation(
    payload: Mapping[str, Any] | None,
    *,
    received_at: datetime,
    ttl_seconds: int,
) -> Observation:
    """Project one external study snapshot into a privacy-bounded Core observation.

    Shared by the shadow probe and read-only Core integration. It does not read files, persist observations,
    classify Today priorities, or imply that the external study system is
    connected. Presence of a local snapshot proves data availability, not live
    provider connectivity.

    Missing fields are never defaulted to zero. Only counts explicitly present
    in a structurally valid snapshot are copied into details.
    """

    _validate_ttl(ttl_seconds)

    if not isinstance(payload, Mapping) or not payload:
        details = {"snapshotPresent": False}
        limitations = ("study_snapshot_missing",)
        return _build_observation(
            availability=AvailabilityStatus.MISSING,
            declared_freshness=FreshnessStatus.UNKNOWN,
            observed_at=None,
            valid_until=None,
            received_at=received_at,
            limitations=limitations,
            details=details,
            summary="Study snapshot is missing; no task or progress counts were inferred.",
        )

    limitations: list[str] = []
    availability = AvailabilityStatus.AVAILABLE
    details: dict[str, Any] = {"snapshotPresent": True}

    schema_version = _integer(payload.get("schemaVersion"))
    if schema_version is None:
        limitations.append("study_schema_version_missing")
        availability = AvailabilityStatus.PARTIAL
    else:
        details["schemaVersion"] = schema_version
        if schema_version != STUDY_SNAPSHOT_SCHEMA_VERSION:
            limitations.append(f"study_schema_version_unsupported:{schema_version}")
            availability = AvailabilityStatus.PARTIAL

    source = _text(payload.get("source"))
    if not source:
        limitations.append("study_source_missing")
        availability = AvailabilityStatus.PARTIAL
    elif source != "study":
        limitations.append(f"study_source_unexpected:{source[:80]}")
        availability = AvailabilityStatus.PARTIAL

    study_type = _text(payload.get("studyType"))
    if study_type:
        details["studyType"] = study_type[:80]

    observed_at = None
    valid_until = None
    raw_updated_at = payload.get("updatedAt")
    if raw_updated_at not in (None, ""):
        try:
            observed_at = parse_datetime(raw_updated_at, field_name="study.updatedAt")
            if observed_at is not None:
                valid_until = observed_at + timedelta(seconds=ttl_seconds)
        except (TypeError, ValueError, OverflowError):
            observed_at = None
            limitations.append("study_updated_at_invalid")
            availability = AvailabilityStatus.PARTIAL
    else:
        limitations.append("study_updated_at_missing")

    declared_freshness = (
        FreshnessStatus.CURRENT if observed_at is not None else FreshnessStatus.UNKNOWN
    )

    vocab = payload.get("vocab")
    if not isinstance(vocab, Mapping):
        limitations.append("study_vocab_missing")
        availability = AvailabilityStatus.PARTIAL
        vocab = {}

    stats = vocab.get("stats")
    if not isinstance(stats, Mapping):
        limitations.append("study_vocab_stats_missing")
        availability = AvailabilityStatus.PARTIAL
        stats = {}

    content_complete = True
    content_complete = _copy_nonnegative_count(
        stats, "total", details, "vocabTotal", limitations
    ) and content_complete
    content_complete = _copy_nonnegative_count(
        stats, "due", details, "vocabDue", limitations
    ) and content_complete
    content_complete = _copy_nonnegative_count(
        stats,
        "withMistakes",
        details,
        "vocabWithMistakes",
        limitations,
    ) and content_complete

    today = vocab.get("today")
    if not isinstance(today, Mapping):
        limitations.append("study_vocab_today_missing")
        availability = AvailabilityStatus.PARTIAL
        today = {}

    content_complete = _copy_list_count(
        today, "review", details, "todayReview", limitations
    ) and content_complete
    content_complete = _copy_list_count(
        today, "focus", details, "todayFocus", limitations
    ) and content_complete
    content_complete = _copy_list_count(
        today, "new", details, "todayNew", limitations
    ) and content_complete

    if not content_complete:
        availability = AvailabilityStatus.PARTIAL

    summary = _summary(availability, details)
    return _build_observation(
        availability=availability,
        declared_freshness=declared_freshness,
        observed_at=observed_at,
        valid_until=valid_until,
        received_at=received_at,
        limitations=tuple(limitations),
        details=details,
        summary=summary,
    )



def study_snapshot_file_observation(
    file_path: str | Path,
    *,
    received_at: datetime,
    ttl_seconds: int,
    max_bytes: int = DEFAULT_MAX_SNAPSHOT_BYTES,
) -> Observation:
    """Read one bounded Study handoff for the Core integration or shadow probe.

    The file is treated as an integration handoff, not as proof of provider
    connectivity. This function performs no persistence and does not expose raw
    study content in error observations.
    """

    _validate_ttl(ttl_seconds)
    _validate_max_bytes(max_bytes)
    try:
        payload = read_json_handoff(file_path, max_bytes=max_bytes)
    except HandoffReadError as exc:
        if exc.code == "missing":
            return study_snapshot_observation(
                None, received_at=received_at, ttl_seconds=ttl_seconds)
        return _read_failure_observation(
            received_at=received_at,
            limitation=f"study_snapshot_{exc.code}",
            availability=(AvailabilityStatus.OFFLINE if exc.code == "read_failed"
                          else AvailabilityStatus.PARTIAL),
        )

    return study_snapshot_observation(
        payload,
        received_at=received_at,
        ttl_seconds=ttl_seconds,
    )



def study_observation_status(
    observation: Observation,
    *,
    as_of: datetime,
) -> dict[str, Any]:
    metrics = {
        key: observation.details[key]
        for key in STUDY_SAFE_DETAIL_KEYS
        if key in observation.details
    }
    return {
        "integrationId": observation.integration_id,
        "connection": observation.connection.value,
        "availability": observation.availability.value,
        "freshness": observation.effective_freshness(as_of=as_of).value,
        "status": observation.data_status(as_of=as_of).value,
        "observedAt": isoformat_utc(observation.observed_at),
        "validUntil": isoformat_utc(observation.valid_until),
        "limitationCount": len(observation.limitations),
        "metrics": metrics,
    }


def build_study_status(
    file_path: str | Path,
    *,
    as_of: datetime,
    ttl_seconds: int = 3600,
    max_bytes: int = DEFAULT_MAX_SNAPSHOT_BYTES,
) -> dict[str, Any]:
    observation = study_snapshot_file_observation(
        file_path,
        received_at=as_of,
        ttl_seconds=ttl_seconds,
        max_bytes=max_bytes,
    )
    return {
        "contract": STUDY_STATUS_CONTRACT,
        "generatedAt": isoformat_utc(as_of),
        "item": study_observation_status(observation, as_of=as_of),
    }


def _read_failure_observation(
    *,
    received_at: datetime,
    limitation: str,
    availability: AvailabilityStatus,
) -> Observation:
    return _build_observation(
        availability=availability,
        declared_freshness=FreshnessStatus.UNKNOWN,
        observed_at=None,
        valid_until=None,
        received_at=received_at,
        limitations=(limitation,),
        details={"snapshotPresent": True},
        summary="Study snapshot handoff is not usable; raw content was not copied.",
    )


def _build_observation(
    *,
    availability: AvailabilityStatus,
    declared_freshness: FreshnessStatus,
    observed_at: datetime | None,
    valid_until: datetime | None,
    received_at: datetime,
    limitations: tuple[str, ...],
    details: Mapping[str, Any],
    summary: str,
) -> Observation:
    fingerprint = json.dumps(
        {
            "availability": availability.value,
            "freshness": declared_freshness.value,
            "observedAt": isoformat_utc(observed_at),
            "validUntil": isoformat_utc(valid_until),
            "limitations": list(limitations),
            "details": dict(details),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:32]
    return Observation.create(
        integration_id="study",
        kind="source_status",
        source_ref="study:snapshot",
        title="Study snapshot",
        summary=summary,
        observed_at=observed_at,
        received_at=received_at,
        valid_until=valid_until,
        availability=availability,
        declared_freshness=declared_freshness,
        connection=ConnectionStatus.UNKNOWN,
        idempotency_key=f"study:snapshot:{digest}",
        limitations=limitations,
        details=details,
    )



def _validate_max_bytes(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("max_bytes must be an integer.")
    if value < 1 or value > MAX_SNAPSHOT_BYTES:
        raise ValueError(f"max_bytes must be between 1 and {MAX_SNAPSHOT_BYTES} bytes.")


def _validate_ttl(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("ttl_seconds must be an integer.")
    if value < 1 or value > MAX_TTL_SECONDS:
        raise ValueError(f"ttl_seconds must be between 1 and {MAX_TTL_SECONDS} seconds.")


def _text(value: object) -> str:
    return str(value or "").strip()


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _nonnegative_integer(value: object) -> int | None:
    parsed = _integer(value)
    if parsed is None or parsed < 0:
        return None
    return parsed


def _copy_nonnegative_count(
    source: Mapping[str, Any],
    source_key: str,
    target: dict[str, Any],
    target_key: str,
    limitations: list[str],
) -> bool:
    if source_key not in source:
        limitations.append(f"study_{source_key}_missing")
        return False
    value = _nonnegative_integer(source.get(source_key))
    if value is None:
        limitations.append(f"study_{source_key}_invalid")
        return False
    target[target_key] = value
    return True


def _copy_list_count(
    source: Mapping[str, Any],
    source_key: str,
    target: dict[str, Any],
    target_key: str,
    limitations: list[str],
) -> bool:
    if source_key not in source:
        limitations.append(f"study_today_{source_key}_missing")
        return False
    value = source.get(source_key)
    if not isinstance(value, list):
        limitations.append(f"study_today_{source_key}_invalid")
        return False

    valid_count = 0
    invalid_count = 0
    for item in value:
        if not isinstance(item, Mapping):
            invalid_count += 1
            continue
        word_id = _text(item.get("word_id") or item.get("wordId") or item.get("id"))
        if not word_id:
            invalid_count += 1
            continue
        valid_count += 1

    target[target_key] = valid_count
    if invalid_count:
        limitations.append(f"study_today_{source_key}_invalid_items:{invalid_count}")
        return False
    return True


def _summary(availability: AvailabilityStatus, details: Mapping[str, Any]) -> str:
    parts = [f"Study snapshot {availability.value}."]
    count_labels = (
        ("vocabTotal", "total vocabulary"),
        ("vocabDue", "due"),
        ("vocabWithMistakes", "with mistakes"),
        ("todayReview", "review today"),
        ("todayFocus", "focus today"),
        ("todayNew", "new today"),
    )
    present = [
        f"{label}={details[key]}"
        for key, label in count_labels
        if key in details
    ]
    if present:
        parts.append(", ".join(present) + ".")
    return " ".join(parts)
