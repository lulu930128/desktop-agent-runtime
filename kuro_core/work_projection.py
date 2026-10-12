"""Pure concrete-evidence projection and canonical-key deduplication."""
from dataclasses import dataclass, fields
from datetime import datetime, timezone
import hashlib
import json

from .contracts import AvailabilityStatus, ConnectionStatus, FreshnessStatus, Observation, normalize_datetime
from .work_contracts import (
    ActionKind, EvidenceKind, MAX_WORK_ITEMS, SourceEvidence, TaskCandidate, WorkItem,
    _WorkFacts, bounded_tuple,
)


def stable_id(prefix: str, *parts: str) -> str:
    encoded = json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()}"


def _facts(value):
    return {f.name: getattr(value, f.name) for f in fields(_WorkFacts)}


def project_evidence(evidence: SourceEvidence | Observation) -> TaskCandidate | None:
    # Current aggregate adapters only produce Observations. Counts are not actions.
    if isinstance(evidence, Observation):
        return None
    if not isinstance(evidence, SourceEvidence):
        raise TypeError("Expected SourceEvidence or a non-actionable Observation.")
    if evidence.kind is EvidenceKind.REFERENCE or evidence.action_kind is ActionKind.NONE:
        return None
    return TaskCandidate(**_facts(evidence), candidate_id=stable_id(
        "candidate", evidence.integration_id, evidence.evidence_id))


def materialize_work(candidate: TaskCandidate) -> WorkItem:
    if not isinstance(candidate, TaskCandidate):
        raise TypeError("Expected TaskCandidate.")
    return WorkItem(**_facts(candidate), candidate_id=candidate.candidate_id,
                    work_id=stable_id("work", candidate.dedup_key))


@dataclass(frozen=True)
class DedupResult:
    winners: tuple[TaskCandidate, ...]
    suppressed: tuple[TaskCandidate, ...]


def _winner_key(candidate, as_of):
    # Lexicographic precedence, not a blended priority score. Quality comes first.
    availability = (AvailabilityStatus.AVAILABLE, AvailabilityStatus.PARTIAL,
                    AvailabilityStatus.UNKNOWN, AvailabilityStatus.MISSING,
                    AvailabilityStatus.OFFLINE, AvailabilityStatus.AUTH_REQUIRED)
    freshness = (FreshnessStatus.CURRENT, FreshnessStatus.STALE, FreshnessStatus.UNKNOWN)
    connection = (ConnectionStatus.CONNECTED, ConnectionStatus.UNKNOWN,
                  ConnectionStatus.DISCONNECTED, ConnectionStatus.AUTH_REQUIRED)
    age = datetime.max.replace(tzinfo=timezone.utc) - candidate.observed_at
    return (availability.index(candidate.availability),
            freshness.index(candidate.effective_freshness(as_of=as_of)),
            connection.index(candidate.connection), not candidate.required, age,
            candidate.evidence_id, candidate.integration_id, candidate.to_json())


def deduplicate_candidates(candidates, *, as_of: datetime) -> DedupResult:
    as_of = normalize_datetime(as_of, field_name="as_of")
    candidates = bounded_tuple("candidates", candidates, TaskCandidate, MAX_WORK_ITEMS)
    if any(c.received_at > as_of for c in candidates):
        raise ValueError("Candidates cannot come from after as_of.")
    ordered = sorted(candidates, key=lambda c: (c.dedup_key, _winner_key(c, as_of)))
    seen, winners, suppressed = set(), [], []
    for candidate in ordered:
        if candidate.dedup_key in seen:
            suppressed.append(candidate)
        else:
            seen.add(candidate.dedup_key)
            winners.append(candidate)
    return DedupResult(tuple(winners), tuple(suppressed))
