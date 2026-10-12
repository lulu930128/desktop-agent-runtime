"""Versioned, immutable G1 values. No persistence, permissions or UI ownership."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from enum import Enum
from typing import Any, ClassVar, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .contracts import (
    AvailabilityStatus, ConnectionStatus, FreshnessStatus, MAX_TITLE_LENGTH,
    _identifier, _json_copy, isoformat_utc, normalize_datetime,
)

MAX_WORK_ITEMS = 1000
MAX_SOURCES = 64
MAX_METADATA_BYTES = 4096
MAX_WORK_SUMMARY = 1000


class EvidenceKind(str, Enum):
    MAIL_MESSAGE = "mail_message"
    STUDY_ITEM = "study_item"
    REFERENCE = "reference"


class ActionKind(str, Enum):
    NONE = "none"
    OPEN = "open"
    REVIEW = "review"
    REPLY = "reply"
    STUDY = "study"


class Importance(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class AttentionLevel(str, Enum):
    URGENT = "urgent"
    MUST = "must"
    FOCUS = "focus"
    WATCH = "watch"
    NORMAL = "normal"
    MUTED = "muted"


class ReasonCode(str, Enum):
    CONCRETE_ACTION = "concrete_action"
    REQUIRED = "required"
    OVERDUE = "overdue"
    DUE_TODAY = "due_today"
    DUE_SOON = "due_soon"
    REMINDER_DUE = "reminder_due"
    ATTENTION_REQUESTED = "attention_requested"
    IMPORTANCE_HIGH = "importance_high"
    IMPORTANCE_CRITICAL = "importance_critical"
    SOURCE_STALE = "source_stale"
    SOURCE_PARTIAL = "source_partial"
    SOURCE_MISSING = "source_missing"
    SOURCE_OFFLINE = "source_offline"
    SOURCE_AUTH_REQUIRED = "source_auth_required"
    SOURCE_UNKNOWN = "source_unknown"
    SOURCE_LIMITATIONS = "source_limitations"
    MUTED = "muted"
    DUPLICATE_SUPPRESSED = "duplicate_suppressed"
    DEFAULT = "default"


class ReasonCategory(str, Enum):
    INCLUSION = "inclusion"
    PRIORITY = "priority"
    QUALITY = "quality"
    SUPPRESSION = "suppression"


class SectionKind(str, Enum):
    IMMEDIATE = "immediate"
    FOCUS = "focus"
    WATCH = "watch"
    NORMAL = "normal"


LEVEL_RANK = {level: index for index, level in enumerate(AttentionLevel)}
SECTION_LEVELS = {
    SectionKind.IMMEDIATE: (AttentionLevel.URGENT, AttentionLevel.MUST),
    SectionKind.FOCUS: (AttentionLevel.FOCUS,),
    SectionKind.WATCH: (AttentionLevel.WATCH,),
    SectionKind.NORMAL: (AttentionLevel.NORMAL,),
}


def identifier(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string.")
    return _identifier(name, value)


def text(name: str, value: object, limit: int, *, required: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string.")
    value = value.strip()
    if len(value) > limit or (required and not value):
        raise ValueError(f"Invalid bounded {name}.")
    return value


def boolean(name: str, value: object) -> None:
    if type(value) is not bool:
        raise TypeError(f"{name} must be a bool.")


def bounded_tuple(name: str, values, item_type, maximum: int) -> tuple:
    if not isinstance(values, (tuple, list)):
        raise TypeError(f"{name} must be a tuple or list.")
    if len(values) > maximum or any(not isinstance(v, item_type) for v in values):
        raise ValueError(f"Invalid bounded {name}.")
    return tuple(values)


def timezone_info(name: str) -> ZoneInfo:
    name = text("timezone", name, 80, required=True)
    # An explicit IANA key is required; never use datetime.astimezone() without it.
    try:
        return ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError("timezone must be an installed IANA timezone.") from exc


def safe_metadata(value: Mapping[str, Any]):
    def check(node, depth=0):
        if depth > 4:
            raise ValueError("Metadata nesting exceeds limit.")
        if isinstance(node, Mapping):
            if len(node) > 32:
                raise ValueError("Metadata object exceeds limit.")
            for key, child in node.items():
                identifier("metadata key", key)
                normalized = "".join(c for c in key.lower() if c.isalnum())
                if normalized in {"body", "rawbody", "rawmail", "rawmessage", "snippet",
                                  "messages", "attachments", "rawstudy", "payload"}:
                    raise ValueError("Raw content metadata is not allowed.")
                check(child, depth + 1)
        elif isinstance(node, (list, tuple)):
            if len(node) > 32:
                raise ValueError("Metadata array exceeds limit.")
            for child in node:
                check(child, depth + 1)
        elif isinstance(node, str):
            text("metadata text", node, 240)
        elif node is not None and type(node) not in (bool, int, float):
            raise ValueError("Metadata must contain JSON values.")
        elif isinstance(node, float) and not math.isfinite(node):
            raise ValueError("Metadata numbers must be finite.")
    check(value)
    # Reuse Core's recursive sensitive-key rejection and immutable JSON copy.
    return _json_copy("metadata", value, max_bytes=MAX_METADATA_BYTES)


def _camel(name):
    first, *rest = name.split("_")
    return first + "".join(part.title() for part in rest)


def _wire(value):
    if isinstance(value, _Contract):
        return value.to_dict()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return isoformat_utc(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {key: _wire(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [_wire(v) for v in value]
    return value


class _Contract:
    CONTRACT: ClassVar[str]

    def to_dict(self) -> dict:
        return {"contract": self.CONTRACT,
                **{_camel(f.name): _wire(getattr(self, f.name)) for f in fields(self)}}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True, kw_only=True)
class _WorkFacts(_Contract):
    evidence_id: str
    integration_id: str
    kind: EvidenceKind
    source_ref: str
    dedup_key: str
    title: str
    summary: str
    observed_at: datetime
    received_at: datetime
    valid_until: datetime | None
    availability: AvailabilityStatus
    freshness: FreshnessStatus
    connection: ConnectionStatus
    action_kind: ActionKind
    due_at: datetime | None = None
    remind_at: datetime | None = None
    required: bool = False
    muted: bool = False
    attention_requested: bool = False
    importance: Importance = Importance.NORMAL
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        for name in ("evidence_id", "integration_id", "dedup_key"):
            object.__setattr__(self, name, identifier(name, getattr(self, name)))
        for name, limit, required in (("title", MAX_TITLE_LENGTH, True),
                                      ("summary", MAX_WORK_SUMMARY, False),
                                      ("source_ref", 500, True)):
            object.__setattr__(self, name, text(name, getattr(self, name), limit, required=required))
        for name, enum in (("kind", EvidenceKind), ("availability", AvailabilityStatus),
                           ("freshness", FreshnessStatus), ("connection", ConnectionStatus),
                           ("action_kind", ActionKind), ("importance", Importance)):
            object.__setattr__(self, name, enum(getattr(self, name)))
        for name in ("required", "muted", "attention_requested"):
            boolean(name, getattr(self, name))
        for name in ("observed_at", "received_at", "valid_until", "due_at", "remind_at"):
            value = getattr(self, name)
            if value is not None or name in ("observed_at", "received_at"):
                object.__setattr__(self, name, normalize_datetime(value, field_name=name))
        if self.observed_at > self.received_at:
            raise ValueError("observed_at cannot follow received_at.")
        if self.valid_until is not None and self.valid_until < self.observed_at:
            raise ValueError("valid_until cannot precede observed_at.")
        if self.freshness is FreshnessStatus.CURRENT and self.valid_until is None:
            raise ValueError("Current evidence requires valid_until.")
        object.__setattr__(self, "metadata", safe_metadata(self.metadata))

    def effective_freshness(self, *, as_of: datetime) -> FreshnessStatus:
        as_of = normalize_datetime(as_of, field_name="as_of")
        if self.freshness is FreshnessStatus.CURRENT and as_of > self.valid_until:
            return FreshnessStatus.STALE
        return self.freshness


@dataclass(frozen=True, kw_only=True)
class SourceEvidence(_WorkFacts):
    """One concrete source fact; source_ref/action_kind grant no permission."""
    CONTRACT: ClassVar[str] = "kuro.core.source-evidence.v1"


@dataclass(frozen=True, kw_only=True)
class TaskCandidate(_WorkFacts):
    CONTRACT: ClassVar[str] = "kuro.core.task-candidate.v1"
    candidate_id: str
    inclusion_reasons: tuple[ReasonCode, ...] = (ReasonCode.CONCRETE_ACTION,)

    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(self, "candidate_id", identifier("candidate_id", self.candidate_id))
        reasons = bounded_tuple("inclusion_reasons", self.inclusion_reasons, ReasonCode, 24)
        if reasons != (ReasonCode.CONCRETE_ACTION,) or self.action_kind is ActionKind.NONE or self.kind is EvidenceKind.REFERENCE:
            raise ValueError("A candidate requires concrete actionable evidence.")
        object.__setattr__(self, "inclusion_reasons", reasons)


@dataclass(frozen=True, kw_only=True)
class WorkItem(_WorkFacts):
    CONTRACT: ClassVar[str] = "kuro.core.work-item.v1"
    work_id: str
    candidate_id: str
    status: str = "open"

    def __post_init__(self):
        super().__post_init__()
        for name in ("work_id", "candidate_id"):
            object.__setattr__(self, name, identifier(name, getattr(self, name)))
        if self.status != "open" or self.action_kind is ActionKind.NONE or self.kind is EvidenceKind.REFERENCE:
            raise ValueError("G1 work is an open, in-memory actionable projection only.")


@dataclass(frozen=True, kw_only=True)
class AttentionReason(_Contract):
    CONTRACT: ClassVar[str] = "kuro.core.attention-reason.v1"
    code: ReasonCode
    category: ReasonCategory
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "code", ReasonCode(self.code))
        object.__setattr__(self, "category", ReasonCategory(self.category))
        object.__setattr__(self, "detail", safe_metadata(self.detail))


@dataclass(frozen=True, kw_only=True)
class AttentionDecision(_Contract):
    CONTRACT: ClassVar[str] = "kuro.core.attention-decision.v1"
    work_id: str
    level: AttentionLevel
    included: bool
    reasons: tuple[AttentionReason, ...]
    rank: int

    def __post_init__(self):
        object.__setattr__(self, "work_id", identifier("work_id", self.work_id))
        object.__setattr__(self, "level", AttentionLevel(self.level))
        boolean("included", self.included)
        object.__setattr__(self, "reasons", bounded_tuple("reasons", self.reasons, AttentionReason, 24))
        if not self.reasons or type(self.rank) is not int or self.rank != LEVEL_RANK[self.level]:
            raise ValueError("Decision requires reasons and the level's ordinal rank.")
        if self.included != (self.level is not AttentionLevel.MUTED):
            raise ValueError("Only muted decisions are excluded in G1.")


@dataclass(frozen=True, kw_only=True)
class TodayItem(_Contract):
    CONTRACT: ClassVar[str] = "kuro.core.today-item.v1"
    work_id: str
    source: str
    kind: EvidenceKind
    dedup_key: str
    title: str
    summary: str
    action_kind: ActionKind
    due_at: datetime | None
    level: AttentionLevel
    reason_codes: tuple[ReasonCode, ...]
    evidence_ref: str
    stale: bool
    partial: bool

    def __post_init__(self):
        for name in ("work_id", "source", "dedup_key", "evidence_ref"):
            object.__setattr__(self, name, identifier(name, getattr(self, name)))
        for name, limit in (("title", MAX_TITLE_LENGTH), ("summary", MAX_WORK_SUMMARY)):
            object.__setattr__(self, name, text(name, getattr(self, name), limit, required=name == "title"))
        for name, enum in (("kind", EvidenceKind), ("action_kind", ActionKind), ("level", AttentionLevel)):
            object.__setattr__(self, name, enum(getattr(self, name)))
        if self.level is AttentionLevel.MUTED or self.action_kind is ActionKind.NONE or self.kind is EvidenceKind.REFERENCE:
            raise ValueError("Default Today items must be included actionable work.")
        if self.due_at is not None:
            object.__setattr__(self, "due_at", normalize_datetime(self.due_at, field_name="due_at"))
        object.__setattr__(self, "reason_codes", bounded_tuple("reason_codes", self.reason_codes, ReasonCode, 24))
        if not self.reason_codes:
            raise ValueError("Today items require reasons.")
        boolean("stale", self.stale)
        boolean("partial", self.partial)


@dataclass(frozen=True, kw_only=True)
class TodaySection(_Contract):
    CONTRACT: ClassVar[str] = "kuro.core.today-section.v1"
    kind: SectionKind
    item_ids: tuple[str, ...]

    def __post_init__(self):
        object.__setattr__(self, "kind", SectionKind(self.kind))
        ids = bounded_tuple("item_ids", self.item_ids, str, MAX_WORK_ITEMS)
        ids = tuple(identifier("item_id", value) for value in ids)
        if len(ids) != len(set(ids)):
            raise ValueError("Section item IDs must be unique.")
        object.__setattr__(self, "item_ids", ids)


@dataclass(frozen=True, kw_only=True)
class SourceState(_Contract):
    CONTRACT: ClassVar[str] = "kuro.core.today-source-state.v1"
    integration_id: str
    availability: AvailabilityStatus
    freshness: FreshnessStatus
    connection: ConnectionStatus
    observed_at: datetime | None
    valid_until: datetime | None
    limitation_count: int

    def __post_init__(self):
        object.__setattr__(self, "integration_id", identifier("integration_id", self.integration_id))
        for name, enum in (("availability", AvailabilityStatus), ("freshness", FreshnessStatus), ("connection", ConnectionStatus)):
            object.__setattr__(self, name, enum(getattr(self, name)))
        for name in ("observed_at", "valid_until"):
            if getattr(self, name) is not None:
                object.__setattr__(self, name, normalize_datetime(getattr(self, name), field_name=name))
        if type(self.limitation_count) is not int or not 0 <= self.limitation_count <= 24:
            raise ValueError("Invalid limitation_count.")
        if self.freshness is FreshnessStatus.CURRENT and (self.observed_at is None or self.valid_until is None):
            raise ValueError("Current source states require bounded timestamps.")
        if self.observed_at is not None and self.valid_until is not None and self.valid_until < self.observed_at:
            raise ValueError("Invalid source time order.")

    @property
    def healthy(self):
        # Unknown connection is normal for a current, local Study handoff.
        return (self.availability is AvailabilityStatus.AVAILABLE
                and self.freshness is FreshnessStatus.CURRENT
                and self.connection in (ConnectionStatus.CONNECTED, ConnectionStatus.UNKNOWN)
                and self.limitation_count == 0)


@dataclass(frozen=True, kw_only=True)
class TodayView(_Contract):
    CONTRACT: ClassVar[str] = "kuro.core.today.v1"
    generated_at: datetime
    as_of: datetime
    local_date: date
    timezone: str
    complete: bool
    items: tuple[TodayItem, ...]
    sections: tuple[TodaySection, ...]
    counts: Mapping[str, int]
    source_states: tuple[SourceState, ...]
    limitations: tuple[ReasonCode, ...]

    def __post_init__(self):
        for name in ("generated_at", "as_of"):
            object.__setattr__(self, name, normalize_datetime(getattr(self, name), field_name=name))
        zone = timezone_info(self.timezone)
        if self.generated_at < self.as_of or type(self.local_date) is not date or self.local_date != self.as_of.astimezone(zone).date():
            raise ValueError("Today time boundary is inconsistent.")
        boolean("complete", self.complete)
        for name, item_type, maximum in (("items", TodayItem, MAX_WORK_ITEMS),
                ("sections", TodaySection, 4), ("source_states", SourceState, MAX_SOURCES),
                ("limitations", ReasonCode, 24)):
            object.__setattr__(self, name, bounded_tuple(name, getattr(self, name), item_type, maximum))
        if len({i.work_id for i in self.items}) != len(self.items) or len({i.dedup_key for i in self.items}) != len(self.items):
            raise ValueError("Today identities must be unique.")
        if len({s.integration_id for s in self.source_states}) != len(self.source_states):
            raise ValueError("Source states must be unique.")
        if not {i.source for i in self.items} <= {s.integration_id for s in self.source_states}:
            raise ValueError("Items require source health coverage.")
        if tuple(s.kind for s in self.sections) != tuple(SectionKind):
            raise ValueError("Today requires canonical attention sections.")
        for section in self.sections:
            if section.item_ids != tuple(i.work_id for i in self.items if i.level in SECTION_LEVELS[section.kind]):
                raise ValueError("Section membership is inconsistent.")
        counts = dict(self.counts)
        expected_keys = {level.value for level in AttentionLevel} | {"total", "suppressed", "duplicateSuppressed"}
        if set(counts) != expected_keys or any(type(v) is not int or not 0 <= v <= MAX_WORK_ITEMS for v in counts.values()):
            raise ValueError("Invalid Today counts.")
        if counts["total"] != len(self.items) or counts["suppressed"] != counts["muted"] + counts["duplicateSuppressed"]:
            raise ValueError("Inconsistent Today counts.")
        for level in AttentionLevel:
            if level is not AttentionLevel.MUTED and counts[level.value] != sum(i.level is level for i in self.items):
                raise ValueError("Inconsistent attention counts.")
        object.__setattr__(self, "counts", _json_copy("counts", counts, max_bytes=1024))
        if self.complete != (all(s.healthy for s in self.source_states) and not self.limitations):
            raise ValueError("Today completeness must preserve source limitations.")
