"""Pure bounded read of Mail work metadata and existing provider-status evidence."""
from dataclasses import replace
from datetime import timedelta

from .contracts import AvailabilityStatus, FreshnessStatus
from .handoff import HandoffReadError, read_json_handoff
from .mail_adapter import _timestamp, mail_status_file_observation, validate_mail_limits
from .work_contracts import ActionKind, EvidenceKind, Importance, SourceEvidence
from .work_evidence import (MAX_SOURCE_ITEMS, WorkEvidenceRead, degraded,
                            evidence_quality, identity, stable_id)

DEFAULT_MAX_WORK_BYTES = 2 * 1024 * 1024
MAX_WORK_BYTES = DEFAULT_MAX_WORK_BYTES
TEXT_FIELDS = {"id": 120, "threadId": 120, "subject": 240, "from": 240,
               "senderEmail": 240, "date": 80}
BOOL_FIELDS = ("unread", "requiredEvent", "muted", "attention", "gmailImportant")
PRIORITIES = {"low", "normal", "medium", "high", "critical", "urgent", "muted"}


def validate_work_max_bytes(value):
    if type(value) is not int or not 1 <= value <= MAX_WORK_BYTES:
        raise ValueError(f"Mail work_max_bytes must be an integer between 1 and {MAX_WORK_BYTES}")


def mail_work_evidence(payload, observation, *, ttl_seconds=1800):
    validate_mail_limits(ttl_seconds, 65536)
    if (not isinstance(payload, dict) or set(payload) != {
            "schemaVersion", "source", "contract", "updatedAt", "attemptAt", "items"}
            or type(payload.get("schemaVersion")) is not int or payload["schemaVersion"] != 1
            or payload.get("source") != "gmail_briefing" or payload.get("contract") != "kuro.mail.work.v1"):
        return WorkEvidenceRead((), degraded(observation, "mail_work_schema_invalid"))
    stamp, attempt = _timestamp(payload.get("updatedAt")), _timestamp(payload.get("attemptAt"))
    if stamp is None or attempt is None or max(stamp, attempt) > observation.received_at:
        return WorkEvidenceRead((), degraded(observation, "mail_work_timestamp_invalid"))
    try:
        valid_until = stamp + timedelta(seconds=ttl_seconds)
    except OverflowError:
        return WorkEvidenceRead((), degraded(observation, "mail_work_timestamp_invalid"))
    # Files are independently atomic. Detect split generations instead of showing
    # old work as freshly fetched while the producer is between its two writes.
    if observation.observed_at != stamp:
        observation = degraded(observation, "mail_work_status_generation_mismatch")
    observation = replace(observation, observed_at=stamp, valid_until=valid_until,
                          declared_freshness=FreshnessStatus.CURRENT)
    items = payload.get("items")
    if not isinstance(items, list) or len(items) > MAX_SOURCE_ITEMS:
        return WorkEvidenceRead((), degraded(observation, "mail_work_items_invalid"))
    facts, seen = [], set()
    for item in items:
        if (not isinstance(item, dict) or set(item) != set(TEXT_FIELDS) | set(BOOL_FIELDS) | {"priorityLevel", "event"}
                or any(not isinstance(item.get(k), str) or len(item[k]) > limit for k, limit in TEXT_FIELDS.items())
                or not stable_id(item.get("id"))
                or any(type(item.get(k)) is not bool for k in BOOL_FIELDS)
                or not isinstance(item.get("priorityLevel"), str) or item["priorityLevel"] not in PRIORITIES):
            return WorkEvidenceRead((), degraded(observation, "mail_work_item_invalid"))
        message_id = item["id"].strip()
        if message_id in seen:
            return WorkEvidenceRead((), degraded(observation, "mail_work_duplicate_id"))
        seen.add(message_id)
        event = item.get("event")
        if (not isinstance(event, dict) or set(event) != {"id", "name", "category"}
                or any(not isinstance(event[k], str) or len(event[k]) > limit
                       for k, limit in (("id", 120), ("name", 120), ("category", 80)))):
            return WorkEvidenceRead((), degraded(observation, "mail_work_event_invalid"))
        key = identity("mail", "message", message_id)
        facts.append(dict(evidence_id=key, integration_id="mail", kind=EvidenceKind.MAIL_MESSAGE,
            source_ref=f"mail:{message_id}", dedup_key=key, title=item["subject"].strip() or "Mail message",
            summary=item["from"].strip() or item["senderEmail"].strip(), action_kind=ActionKind.OPEN,
            required=item["requiredEvent"], muted=item["muted"], attention_requested=item["attention"],
            importance={"high": Importance.HIGH, "critical": Importance.CRITICAL,
                        "urgent": Importance.CRITICAL}.get(item["priorityLevel"], Importance.NORMAL)))
    return WorkEvidenceRead(tuple(SourceEvidence(**fact, **evidence_quality(observation))
                                  for fact in facts), observation)


def read_mail_work(work_path, status_path, *, received_at, ttl_seconds=1800,
                   max_bytes=DEFAULT_MAX_WORK_BYTES, status_max_bytes=65536):
    validate_work_max_bytes(max_bytes)
    observation = mail_status_file_observation(status_path, received_at=received_at,
                                              ttl_seconds=ttl_seconds, max_bytes=status_max_bytes)
    try:
        payload = read_json_handoff(work_path, max_bytes=max_bytes)
    except HandoffReadError as exc:
        availability = {"missing": AvailabilityStatus.MISSING, "read_failed": AvailabilityStatus.OFFLINE}.get(
            exc.code, AvailabilityStatus.PARTIAL)
        return WorkEvidenceRead((), degraded(observation, f"mail_work_{exc.code}", availability))
    return mail_work_evidence(payload, observation, ttl_seconds=ttl_seconds)
