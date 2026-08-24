from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping


CONTRACT_VERSION = 1
MAX_IDENTIFIER_LENGTH = 160
MAX_TITLE_LENGTH = 240
MAX_SUMMARY_LENGTH = 4000
MAX_LIMITATIONS = 24
MAX_LIMITATION_LENGTH = 500
MAX_DETAILS_BYTES = 32 * 1024
MAX_TRACE_METRICS_BYTES = 16 * 1024

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SENSITIVE_JSON_KEYS = {
    "accesstoken",
    "apikey",
    "authorization",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "password",
    "passwd",
    "privatekey",
    "refreshtoken",
    "secret",
    "token",
}


class FrozenJsonDict(dict[str, Any]):
    """JSON-serializable dict that prevents post-validation mutation."""

    def _immutable(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("Validated JSON metadata is immutable.")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable


class AvailabilityStatus(str, Enum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    MISSING = "missing"
    OFFLINE = "offline"
    AUTH_REQUIRED = "auth_required"
    UNKNOWN = "unknown"


class FreshnessStatus(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"


class ConnectionStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    AUTH_REQUIRED = "auth_required"
    UNKNOWN = "unknown"


class DataStatus(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    PARTIAL = "partial"
    MISSING = "missing"
    OFFLINE = "offline"
    AUTH_REQUIRED = "auth_required"
    UNKNOWN = "unknown"


class DecisionTraceStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_datetime(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone.")
    return value.astimezone(timezone.utc)


def parse_datetime(value: object, *, field_name: str = "timestamp") -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return normalize_datetime(value, field_name=field_name)
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be an ISO-8601 string or datetime.")
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid ISO-8601 timestamp.") from exc
    return normalize_datetime(parsed, field_name=field_name)


def isoformat_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_datetime(value, field_name="timestamp")
    return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _identifier(field_name: str, value: object) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    if len(normalized) > MAX_IDENTIFIER_LENGTH or not _IDENTIFIER_RE.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must be at most {MAX_IDENTIFIER_LENGTH} characters and use "
            "letters, digits, period, underscore, colon, or hyphen."
        )
    return normalized


def _text(field_name: str, value: object, max_length: int, *, required: bool = False) -> str:
    normalized = str(value or "").strip()
    if required and not normalized:
        raise ValueError(f"{field_name} is required.")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} exceeds the {max_length} character limit.")
    return normalized


def _string_tuple(
    field_name: str,
    values: Iterable[object],
    *,
    max_items: int,
    max_length: int,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be a collection of strings, not one string.")
    normalized: list[str] = []
    for value in values:
        item = _text(field_name, value, max_length)
        if item and item not in normalized:
            normalized.append(item)
    if len(normalized) > max_items:
        raise ValueError(f"{field_name} exceeds the {max_items} item limit.")
    return tuple(normalized)


def _json_copy(field_name: str, value: Mapping[str, Any], *, max_bytes: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be an object.")
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must contain JSON-serializable values.") from exc
    if len(encoded.encode("utf-8")) > max_bytes:
        raise ValueError(f"{field_name} exceeds the {max_bytes} byte limit.")
    copied = json.loads(encoded)
    _reject_sensitive_json_keys(field_name, copied)
    return _freeze_json(copied)


def _freeze_json(value: object) -> Any:
    if isinstance(value, dict):
        return FrozenJsonDict({str(key): _freeze_json(nested) for key, nested in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(nested) for nested in value)
    return value


def _reject_sensitive_json_keys(field_name: str, value: object, *, path: str = "") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = re.sub(r"[^a-z0-9]", "", str(key).lower())
            nested_path = f"{path}.{key}" if path else str(key)
            if normalized_key in _SENSITIVE_JSON_KEYS:
                raise ValueError(
                    f"{field_name} cannot contain sensitive field '{nested_path}'. "
                    "Store only a non-sensitive reference or digest."
                )
            _reject_sensitive_json_keys(field_name, nested, path=nested_path)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            nested_path = f"{path}[{index}]" if path else f"[{index}]"
            _reject_sensitive_json_keys(field_name, nested, path=nested_path)


@dataclass(frozen=True)
class Observation:
    observation_id: str
    integration_id: str
    kind: str
    source_ref: str
    title: str
    summary: str
    received_at: datetime
    availability: AvailabilityStatus
    declared_freshness: FreshnessStatus
    connection: ConnectionStatus = ConnectionStatus.UNKNOWN
    observed_at: datetime | None = None
    valid_until: datetime | None = None
    idempotency_key: str = ""
    limitations: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)
    schema_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_id", _identifier("observation_id", self.observation_id))
        object.__setattr__(self, "integration_id", _identifier("integration_id", self.integration_id))
        object.__setattr__(self, "kind", _identifier("kind", self.kind))
        object.__setattr__(self, "source_ref", _text("source_ref", self.source_ref, 500, required=True))
        object.__setattr__(self, "title", _text("title", self.title, MAX_TITLE_LENGTH, required=True))
        object.__setattr__(self, "summary", _text("summary", self.summary, MAX_SUMMARY_LENGTH))
        object.__setattr__(self, "idempotency_key", _identifier("idempotency_key", self.idempotency_key))
        object.__setattr__(
            self,
            "received_at",
            normalize_datetime(self.received_at, field_name="received_at"),
        )
        if self.observed_at is not None:
            object.__setattr__(
                self,
                "observed_at",
                normalize_datetime(self.observed_at, field_name="observed_at"),
            )
        if self.valid_until is not None:
            object.__setattr__(
                self,
                "valid_until",
                normalize_datetime(self.valid_until, field_name="valid_until"),
            )
        if self.declared_freshness is FreshnessStatus.CURRENT:
            if self.observed_at is None or self.valid_until is None:
                raise ValueError(
                    "A current observation requires observed_at and valid_until; "
                    "unbounded current data is not allowed."
                )
        if (
            self.observed_at is not None
            and self.valid_until is not None
            and self.valid_until < self.observed_at
        ):
            raise ValueError("valid_until cannot be earlier than observed_at.")
        object.__setattr__(
            self,
            "limitations",
            _string_tuple(
                "limitations",
                self.limitations,
                max_items=MAX_LIMITATIONS,
                max_length=MAX_LIMITATION_LENGTH,
            ),
        )
        object.__setattr__(
            self,
            "details",
            _json_copy("details", self.details, max_bytes=MAX_DETAILS_BYTES),
        )
        if self.schema_version != CONTRACT_VERSION:
            raise ValueError(f"Unsupported observation schema_version: {self.schema_version}")

    @classmethod
    def create(
        cls,
        *,
        integration_id: str,
        kind: str,
        source_ref: str,
        title: str,
        summary: str,
        received_at: datetime,
        availability: AvailabilityStatus,
        declared_freshness: FreshnessStatus,
        idempotency_key: str,
        connection: ConnectionStatus = ConnectionStatus.UNKNOWN,
        observed_at: datetime | None = None,
        valid_until: datetime | None = None,
        limitations: Iterable[object] = (),
        details: Mapping[str, Any] | None = None,
        observation_id: str | None = None,
    ) -> "Observation":
        return cls(
            observation_id=observation_id or f"obs:{uuid.uuid4().hex}",
            integration_id=integration_id,
            kind=kind,
            source_ref=source_ref,
            title=title,
            summary=summary,
            received_at=received_at,
            availability=availability,
            declared_freshness=declared_freshness,
            connection=connection,
            observed_at=observed_at,
            valid_until=valid_until,
            idempotency_key=idempotency_key,
            limitations=tuple(limitations),
            details=dict(details or {}),
        )

    def effective_freshness(self, *, as_of: datetime) -> FreshnessStatus:
        current_time = normalize_datetime(as_of, field_name="as_of")
        if self.declared_freshness is not FreshnessStatus.CURRENT:
            return self.declared_freshness
        if self.valid_until is None:
            return FreshnessStatus.UNKNOWN
        return (
            FreshnessStatus.CURRENT
            if current_time <= self.valid_until
            else FreshnessStatus.STALE
        )

    def data_status(self, *, as_of: datetime) -> DataStatus:
        if self.availability is AvailabilityStatus.PARTIAL:
            return DataStatus.PARTIAL
        if self.availability is AvailabilityStatus.MISSING:
            return DataStatus.MISSING
        if self.availability is AvailabilityStatus.OFFLINE:
            return DataStatus.OFFLINE
        if self.availability is AvailabilityStatus.AUTH_REQUIRED:
            return DataStatus.AUTH_REQUIRED
        if self.availability is AvailabilityStatus.UNKNOWN:
            return DataStatus.UNKNOWN
        freshness = self.effective_freshness(as_of=as_of)
        return DataStatus(freshness.value)

    def semantic_payload(self) -> dict[str, Any]:
        """Return immutable event semantics, excluding retry-local identity/time."""

        return {
            "integration_id": self.integration_id,
            "kind": self.kind,
            "source_ref": self.source_ref,
            "title": self.title,
            "summary": self.summary,
            "availability": self.availability.value,
            "declared_freshness": self.declared_freshness.value,
            "connection": self.connection.value,
            "observed_at": isoformat_utc(self.observed_at),
            "valid_until": isoformat_utc(self.valid_until),
            "limitations": list(self.limitations),
            "details": self.details,
            "schema_version": self.schema_version,
        }

    def semantic_hash(self) -> str:
        encoded = json.dumps(
            self.semantic_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class DecisionTrace:
    trace_id: str
    run_id: str
    decision_kind: str
    status: DecisionTraceStatus
    created_at: datetime
    observation_ids: tuple[str, ...] = ()
    selected_ids: tuple[str, ...] = ()
    model_provider: str = ""
    model_name: str = ""
    policy_version: str = ""
    config_digest: str = ""
    output_summary: str = ""
    duration_ms: int | None = None
    metrics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "trace_id", _identifier("trace_id", self.trace_id))
        object.__setattr__(self, "run_id", _identifier("run_id", self.run_id))
        object.__setattr__(self, "decision_kind", _identifier("decision_kind", self.decision_kind))
        object.__setattr__(
            self,
            "created_at",
            normalize_datetime(self.created_at, field_name="created_at"),
        )
        object.__setattr__(
            self,
            "observation_ids",
            _string_tuple("observation_ids", self.observation_ids, max_items=256, max_length=160),
        )
        object.__setattr__(
            self,
            "selected_ids",
            _string_tuple("selected_ids", self.selected_ids, max_items=64, max_length=160),
        )
        object.__setattr__(self, "model_provider", _text("model_provider", self.model_provider, 80))
        object.__setattr__(self, "model_name", _text("model_name", self.model_name, 160))
        object.__setattr__(self, "policy_version", _text("policy_version", self.policy_version, 80))
        object.__setattr__(self, "config_digest", _text("config_digest", self.config_digest, 160))
        object.__setattr__(
            self,
            "output_summary",
            _text("output_summary", self.output_summary, MAX_SUMMARY_LENGTH),
        )
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValueError("duration_ms cannot be negative.")
        object.__setattr__(
            self,
            "metrics",
            _json_copy("metrics", self.metrics, max_bytes=MAX_TRACE_METRICS_BYTES),
        )

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        decision_kind: str,
        status: DecisionTraceStatus,
        created_at: datetime,
        observation_ids: Iterable[object] = (),
        selected_ids: Iterable[object] = (),
        model_provider: str = "",
        model_name: str = "",
        policy_version: str = "",
        config_digest: str = "",
        output_summary: str = "",
        duration_ms: int | None = None,
        metrics: Mapping[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> "DecisionTrace":
        return cls(
            trace_id=trace_id or f"trace:{uuid.uuid4().hex}",
            run_id=run_id,
            decision_kind=decision_kind,
            status=status,
            created_at=created_at,
            observation_ids=tuple(str(value) for value in observation_ids),
            selected_ids=tuple(str(value) for value in selected_ids),
            model_provider=model_provider,
            model_name=model_name,
            policy_version=policy_version,
            config_digest=config_digest,
            output_summary=output_summary,
            duration_ms=duration_ms,
            metrics=dict(metrics or {}),
        )
