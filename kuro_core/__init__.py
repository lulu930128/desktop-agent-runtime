"""Kuro Core shadow runtime contracts and persistence.

The package is intentionally not wired into the live launcher yet.  It provides
the backend-owned contract boundary that existing producers and consumers can
adopt incrementally.
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
