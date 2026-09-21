"""Kuro Core: production schedule state and shadow observation contracts.

The launcher-owned ScheduleServer serves the Work Panel. KuroCore observations
and decision traces remain shadow-only; they do not own Today or Briefing.
Storage initialization is shared production infrastructure, not a research DB
boundary. See docs/architecture/CorePersistence.md before changing migrations.
"""

from .contracts import (
    AvailabilityStatus,
    ConnectionStatus,
    DataStatus,
    DecisionTrace,
    DecisionTraceStatus,
    FreshnessStatus,
    Observation,
    parse_datetime,
    utc_now,
)
from .service import KuroCore
from .storage import IdempotencyConflictError, IngestResult, KuroCoreStore

__all__ = [
    "AvailabilityStatus",
    "ConnectionStatus",
    "DataStatus",
    "DecisionTrace",
    "DecisionTraceStatus",
    "FreshnessStatus",
    "IdempotencyConflictError",
    "IngestResult",
    "KuroCore",
    "KuroCoreStore",
    "Observation",
    "parse_datetime",
    "utc_now",
]
