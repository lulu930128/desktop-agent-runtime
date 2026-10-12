"""Pure-read projection of producer Mail status; no mailbox or persistence IO."""
import hashlib
import json
from datetime import timedelta

from .contracts import (AvailabilityStatus, ConnectionStatus, FreshnessStatus,
                        Observation, isoformat_utc, parse_datetime)
from .handoff import HandoffReadError, read_json_handoff

MAIL_STATUS_CONTRACT = "kuro.core.integration.mail.v1"
DEFAULT_MAX_STATUS_BYTES = 65536
MAX_STATUS_BYTES = 65536
MAX_TTL_SECONDS = 30 * 24 * 60 * 60
COUNT_KEYS = ("resultSizeEstimate", "fetched", "unread", "requiredEvents",
              "highPriority", "mediumPriority", "muted", "ordinary", "gmailImportant")
PRIVACY_KEYS = ("bodyFetched", "attachmentsFetched", "mailboxModified")


def validate_mail_limits(ttl_seconds, max_bytes):
    for name, value, maximum in (("ttl_seconds", ttl_seconds, MAX_TTL_SECONDS),
                                 ("max_bytes", max_bytes, MAX_STATUS_BYTES)):
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError(f"Mail {name} must be an integer between 1 and {maximum}")


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        return parse_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None


def mail_status_observation(payload, *, received_at, ttl_seconds=1800,
                            read_error=None):
    validate_mail_limits(ttl_seconds, DEFAULT_MAX_STATUS_BYTES)
    availability = AvailabilityStatus.PARTIAL
    connection = ConnectionStatus.UNKNOWN
    observed = None
    valid_until = None
    details = {"snapshotPresent": read_error != "missing"}
    limitations = []
    if read_error:
        limitations.append(f"mail_status_{read_error}")
        availability = {"missing": AvailabilityStatus.MISSING,
                        "read_failed": AvailabilityStatus.OFFLINE}.get(
                            read_error, AvailabilityStatus.PARTIAL)
    elif (not isinstance(payload, dict) or type(payload.get("schemaVersion")) is not int
          or payload.get("schemaVersion") != 1 or payload.get("source") != "gmail_briefing"):
        limitations.append("mail_status_invalid_schema")
    else:
        details["schemaVersion"] = 1
        attempt = _timestamp(payload.get("lastAttemptAt"))
        ok = payload.get("lastAttemptOk")
        if attempt is not None and type(ok) is bool and attempt <= received_at:
            connection = ConnectionStatus.CONNECTED if ok else ConnectionStatus.DISCONNECTED
            details.update(lastAttemptAt=isoformat_utc(attempt), lastAttemptOk=ok)
        else:
            limitations.append("mail_attempt_invalid")
        error = payload.get("errorType")
        if error in ("", "provider_error", "auth_required"):
            details["errorType"] = error
        else:
            limitations.append("mail_error_type_invalid")
        observed = _timestamp(payload.get("lastSuccessAt"))
        if observed is not None:
            if observed > received_at:
                observed = None
                limitations.append("mail_success_time_invalid")
            else:
                try:
                    valid_until = observed + timedelta(seconds=ttl_seconds)
                except OverflowError:
                    observed = None
                    limitations.append("mail_success_time_invalid")
        if observed is not None:
            counts = payload.get("counts")
            counts = counts if isinstance(counts, dict) else {}
            for key in COUNT_KEYS:
                value = counts.get(key)
                if type(value) is int and 0 <= value <= 1_000_000:
                    details[key] = value
                else:
                    limitations.append(f"mail_{key}_invalid")
            privacy = payload.get("privacy")
            if (isinstance(privacy, dict)
                    and all(type(privacy.get(key)) is bool for key in PRIVACY_KEYS)
                    and privacy["mailboxModified"] is False
                    and privacy["attachmentsFetched"] is False):
                details["privacy"] = {key: privacy[key] for key in PRIVACY_KEYS}
            else:
                limitations.append("mail_privacy_invalid")
            if attempt is not None and (observed > attempt and ok is False):
                limitations.append("mail_time_order_invalid")
            availability = AvailabilityStatus.PARTIAL if limitations else AvailabilityStatus.AVAILABLE
        elif connection == ConnectionStatus.DISCONNECTED and payload.get("lastSuccessAt") in (None, ""):
            availability = (AvailabilityStatus.AUTH_REQUIRED if error == "auth_required"
                            else AvailabilityStatus.OFFLINE)
        else:
            limitations.append("mail_success_missing_or_invalid")
    fingerprint = json.dumps([availability.value, connection.value, isoformat_utc(observed),
                              isoformat_utc(valid_until), details, limitations], sort_keys=True)
    digest = hashlib.sha256(fingerprint.encode()).hexdigest()[:32]
    return Observation.create(
        integration_id="mail", kind="source_status", source_ref="mail:status",
        title="Mail status", summary="Producer Mail status; mailbox content is not included.",
        observed_at=observed, received_at=received_at, valid_until=valid_until,
        availability=availability, connection=connection,
        declared_freshness=FreshnessStatus.CURRENT if observed else FreshnessStatus.UNKNOWN,
        idempotency_key=f"mail:status:{digest}", limitations=tuple(limitations), details=details)


def mail_status_file_observation(file_path, *, received_at, ttl_seconds=1800,
                                 max_bytes=DEFAULT_MAX_STATUS_BYTES):
    validate_mail_limits(ttl_seconds, max_bytes)
    try:
        payload = read_json_handoff(file_path, max_bytes=max_bytes)
    except HandoffReadError as exc:
        return mail_status_observation(None, received_at=received_at,
                                       ttl_seconds=ttl_seconds, read_error=exc.code)
    return mail_status_observation(payload, received_at=received_at, ttl_seconds=ttl_seconds)


def build_mail_status(file_path, *, as_of, ttl_seconds=1800, max_bytes=DEFAULT_MAX_STATUS_BYTES):
    observation = mail_status_file_observation(file_path, received_at=as_of,
                                              ttl_seconds=ttl_seconds, max_bytes=max_bytes)
    return {"contract": MAIL_STATUS_CONTRACT, "generatedAt": isoformat_utc(as_of), "item": {
        "integrationId": "mail", "connection": observation.connection.value,
        "availability": observation.availability.value,
        "freshness": observation.effective_freshness(as_of=as_of).value,
        "status": observation.data_status(as_of=as_of).value,
        "observedAt": isoformat_utc(observation.observed_at),
        "validUntil": isoformat_utc(observation.valid_until),
        "limitationCount": len(observation.limitations), "metrics": dict(observation.details)}}
