"""Deterministic G1 attention rules; no notification delivery or opaque score."""
from datetime import datetime, timedelta

from .contracts import AvailabilityStatus, ConnectionStatus, FreshnessStatus, normalize_datetime
from .work_contracts import (
    AttentionDecision, AttentionLevel, AttentionReason, Importance, LEVEL_RANK,
    ReasonCategory, ReasonCode, WorkItem, timezone_info,
)

DUE_SOON_WINDOW = timedelta(hours=24)  # Elapsed UTC time, including across DST.


def quality_codes(availability, freshness, connection) -> tuple[ReasonCode, ...]:
    codes = set()
    availability_code = {
        AvailabilityStatus.PARTIAL: ReasonCode.SOURCE_PARTIAL,
        AvailabilityStatus.MISSING: ReasonCode.SOURCE_MISSING,
        AvailabilityStatus.OFFLINE: ReasonCode.SOURCE_OFFLINE,
        AvailabilityStatus.AUTH_REQUIRED: ReasonCode.SOURCE_AUTH_REQUIRED,
        AvailabilityStatus.UNKNOWN: ReasonCode.SOURCE_UNKNOWN,
    }.get(availability)
    if availability_code:
        codes.add(availability_code)
    if freshness is FreshnessStatus.STALE:
        codes.add(ReasonCode.SOURCE_STALE)
    elif freshness is FreshnessStatus.UNKNOWN:
        codes.add(ReasonCode.SOURCE_UNKNOWN)
    if connection is ConnectionStatus.DISCONNECTED:
        codes.add(ReasonCode.SOURCE_OFFLINE)
    elif connection is ConnectionStatus.AUTH_REQUIRED:
        codes.add(ReasonCode.SOURCE_AUTH_REQUIRED)
    return tuple(sorted(codes, key=lambda c: c.value))


def decide_attention(work: WorkItem, *, as_of: datetime, timezone: str) -> AttentionDecision:
    """Work contains its immutable evidence/quality snapshot; no second truth input."""
    if not isinstance(work, WorkItem):
        raise TypeError("Expected WorkItem.")
    as_of = normalize_datetime(as_of, field_name="as_of")
    zone = timezone_info(timezone)
    if work.received_at > as_of:
        raise ValueError("Work cannot come from after as_of.")
    overdue = work.due_at is not None and work.due_at < as_of
    due_today = work.due_at is not None and work.due_at.astimezone(zone).date() == as_of.astimezone(zone).date()
    due_soon = work.due_at is not None and timedelta(0) <= work.due_at - as_of <= DUE_SOON_WINDOW
    reminder_due = work.remind_at is not None and work.remind_at <= as_of
    suppressed = work.muted and not work.required
    if suppressed:
        level = AttentionLevel.MUTED
    elif work.required and overdue:
        level = AttentionLevel.URGENT
    elif work.required:
        level = AttentionLevel.MUST
    elif work.importance is Importance.CRITICAL:
        level = AttentionLevel.URGENT
    elif work.importance is Importance.HIGH or work.attention_requested or overdue:
        level = AttentionLevel.FOCUS
    elif due_today or due_soon or reminder_due:
        level = AttentionLevel.WATCH
    else:
        level = AttentionLevel.NORMAL

    reasons = [AttentionReason(code=ReasonCode.CONCRETE_ACTION, category=ReasonCategory.INCLUSION)]
    for condition, code in (
        (work.required, ReasonCode.REQUIRED), (overdue, ReasonCode.OVERDUE),
        (due_today, ReasonCode.DUE_TODAY), (due_soon and not due_today, ReasonCode.DUE_SOON),
        (reminder_due, ReasonCode.REMINDER_DUE),
        (work.attention_requested, ReasonCode.ATTENTION_REQUESTED),
        (work.importance is Importance.HIGH, ReasonCode.IMPORTANCE_HIGH),
        (work.importance is Importance.CRITICAL, ReasonCode.IMPORTANCE_CRITICAL),
        (level is AttentionLevel.NORMAL, ReasonCode.DEFAULT),
    ):
        if condition:
            reasons.append(AttentionReason(code=code, category=ReasonCategory.PRIORITY))
    if work.muted:
        reasons.append(AttentionReason(code=ReasonCode.MUTED, category=ReasonCategory.SUPPRESSION,
                                       detail={"overriddenByRequired": work.required}))
    reasons.extend(AttentionReason(code=code, category=ReasonCategory.QUALITY)
                   for code in quality_codes(work.availability, work.effective_freshness(as_of=as_of), work.connection))
    return AttentionDecision(work_id=work.work_id, level=level, included=not suppressed,
                             reasons=tuple(reasons), rank=LEVEL_RANK[level])
