"""Small shared boundary for bounded, ephemeral integration evidence reads."""
from dataclasses import dataclass, replace
import hashlib

from .contracts import AvailabilityStatus, FreshnessStatus, Observation
from .work_contracts import SourceEvidence

MAX_SOURCE_ITEMS = 500  # Two configured sources fit G1's 1000-item bound.


@dataclass(frozen=True)
class WorkEvidenceRead:
    evidence: tuple[SourceEvidence, ...]
    observation: Observation


def bounded_text(value, maximum, fallback=""):
    return value.strip()[:maximum] if isinstance(value, str) and value.strip() else fallback


def stable_id(value):
    # Never truncate identities or coerce containers/bools into synthetic IDs.
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 120:
        return None
    value = value.strip()
    return value if all(ord(c) >= 32 and ord(c) != 127 for c in value) else None


def identity(source, kind, value):
    return f"{source}:{kind}:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def degraded(observation, code, availability=AvailabilityStatus.PARTIAL):
    return replace(observation, availability=availability,
                   limitations=tuple(dict.fromkeys((*observation.limitations, code))))


def evidence_quality(observation):
    return dict(observed_at=observation.observed_at, received_at=observation.received_at,
                valid_until=observation.valid_until, availability=observation.availability,
                freshness=observation.effective_freshness(as_of=observation.received_at),
                connection=observation.connection)


def invalid_time(observation):
    if observation.observed_at is None or observation.observed_at > observation.received_at:
        return replace(degraded(observation, "work_timestamp_invalid"), observed_at=None,
                       valid_until=None, declared_freshness=FreshnessStatus.UNKNOWN)
    return None
