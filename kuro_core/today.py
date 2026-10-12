"""Pure G1 Today composition. Callers supply evidence, status and evaluation time."""
from datetime import datetime, timezone as dt_timezone

from .attention import decide_attention, quality_codes
from .contracts import AvailabilityStatus, ConnectionStatus, FreshnessStatus, Observation, normalize_datetime
from .work_contracts import (
    AttentionLevel, LEVEL_RANK, MAX_SOURCES, MAX_WORK_ITEMS, ReasonCode, SECTION_LEVELS,
    SectionKind, SourceEvidence, SourceState, TodayItem, TodaySection, TodayView,
    bounded_tuple, identifier, timezone_info,
)
from .work_projection import deduplicate_candidates, materialize_work, project_evidence


def _source_state(observation, as_of):
    return SourceState(integration_id=observation.integration_id,
        availability=observation.availability,
        freshness=observation.effective_freshness(as_of=as_of), connection=observation.connection,
        observed_at=observation.observed_at, valid_until=observation.valid_until,
        limitation_count=len(observation.limitations))


def _source_states(observations, sources, as_of):
    grouped = {source: [] for source in sources}
    for observation in observations:
        if observation.kind != "source_status":
            raise ValueError("Today source health requires source_status Observations.")
        # Historical projections must not use observations received in the future.
        if observation.received_at > as_of or (observation.observed_at is not None and observation.observed_at > as_of):
            continue
        state = _source_state(observation, as_of)
        grouped[observation.integration_id].append((observation, state))
    states = []
    minimum = datetime.min.replace(tzinfo=dt_timezone.utc)
    for source in sorted(sources):
        snapshots = grouped[source]
        if not snapshots:
            states.append(SourceState(integration_id=source, availability=AvailabilityStatus.MISSING,
                freshness=FreshnessStatus.UNKNOWN, connection=ConnectionStatus.UNKNOWN,
                observed_at=None, valid_until=None, limitation_count=0))
            continue
        # Latest received status includes recent failures retaining last-good observedAt.
        # Equal-time conflicts prefer degraded status, then a stable safe-state ordering.
        _, state = max(snapshots, key=lambda pair: (pair[0].received_at,
            pair[0].observed_at or minimum, not pair[1].healthy,
            pair[1].limitation_count, pair[1].to_json()))
        states.append(state)
    return tuple(states)


def build_today_view(evidence, source_observations, *, as_of: datetime, timezone: str,
                     expected_sources, generated_at: datetime | None = None) -> TodayView:
    """Expected sources are explicit; () means no configured sources, not default Mail/Study.

    complete describes supplied source/evidence quality, not actionable-producer coverage.
    Aggregate status never proves that all real-world work has been enumerated.
    """
    as_of = normalize_datetime(as_of, field_name="as_of")
    zone = timezone_info(timezone)
    generated_at = as_of if generated_at is None else normalize_datetime(generated_at, field_name="generated_at")
    evidence = bounded_tuple("evidence", evidence, SourceEvidence, MAX_WORK_ITEMS)
    observations = bounded_tuple("source_observations", source_observations, Observation, MAX_WORK_ITEMS)
    expected = bounded_tuple("expected_sources", expected_sources, str, MAX_SOURCES)
    sources = {identifier("expected_source", s) for s in expected}
    sources.update(e.integration_id for e in evidence)
    sources.update(o.integration_id for o in observations)
    if len(sources) > MAX_SOURCES:
        raise ValueError("Too many sources.")
    if any(e.received_at > as_of for e in evidence):
        raise ValueError("Evidence cannot come from after as_of.")
    states = _source_states(observations, sources, as_of)
    candidates = tuple(c for e in evidence if (c := project_evidence(e)) is not None)
    dedup = deduplicate_candidates(candidates, as_of=as_of)
    duplicate_counts = {}
    for candidate in dedup.suppressed:
        duplicate_counts[candidate.dedup_key] = duplicate_counts.get(candidate.dedup_key, 0) + 1
    items, muted = [], 0
    limitations = set()
    for state in states:
        limitations.update(quality_codes(state.availability, state.freshness, state.connection))
        if state.limitation_count:
            limitations.add(ReasonCode.SOURCE_LIMITATIONS)
    # Even suppressed/non-actionable evidence must not hide degraded input quality.
    for fact in evidence:
        limitations.update(quality_codes(fact.availability, fact.effective_freshness(as_of=as_of), fact.connection))
    for candidate in dedup.winners:
        work = materialize_work(candidate)
        decision = decide_attention(work, as_of=as_of, timezone=timezone)
        if not decision.included:
            muted += 1
            continue
        codes = tuple(r.code for r in decision.reasons)
        if work.dedup_key in duplicate_counts:
            codes += (ReasonCode.DUPLICATE_SUPPRESSED,)
        items.append(TodayItem(work_id=work.work_id, source=work.integration_id, kind=work.kind,
            dedup_key=work.dedup_key, title=work.title, summary=work.summary, action_kind=work.action_kind,
            due_at=work.due_at, level=decision.level, reason_codes=codes, evidence_ref=work.evidence_id,
            stale=work.effective_freshness(as_of=as_of) is FreshnessStatus.STALE,
            partial=work.availability is AvailabilityStatus.PARTIAL))
    maximum = datetime.max.replace(tzinfo=dt_timezone.utc)
    items = tuple(sorted(items, key=lambda i: (LEVEL_RANK[i.level], i.due_at or maximum, i.work_id)))
    sections = tuple(TodaySection(kind=kind, item_ids=tuple(i.work_id for i in items if i.level in levels))
                     for kind, levels in SECTION_LEVELS.items())
    counts = {level.value: sum(i.level is level for i in items) for level in AttentionLevel}
    counts.update(total=len(items), muted=muted, suppressed=muted + len(dedup.suppressed),
                  duplicateSuppressed=len(dedup.suppressed))
    return TodayView(generated_at=generated_at, as_of=as_of, local_date=as_of.astimezone(zone).date(),
        timezone=timezone, complete=all(s.healthy for s in states) and not limitations,
        items=items, sections=sections, counts=counts, source_states=states,
        limitations=tuple(sorted(limitations, key=lambda code: code.value)))
