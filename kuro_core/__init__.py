"""Kuro Core shadow runtime contracts and persistence.

Observations remain a shadow path. Local schedule infrastructure has an opt-in
launcher service; production Work Panel adoption is a separate acceptance gate.
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
