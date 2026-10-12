"""Concrete Study facts from the existing snapshot; never infer work from counts."""
from .contracts import AvailabilityStatus
from .handoff import HandoffReadError, read_json_handoff
from .study_adapter import (study_snapshot_observation, _read_failure_observation,
                            _validate_ttl, _validate_max_bytes, DEFAULT_MAX_SNAPSHOT_BYTES)
from .work_contracts import ActionKind, EvidenceKind, Importance, SourceEvidence
from .work_evidence import (MAX_SOURCE_ITEMS, WorkEvidenceRead, bounded_text, degraded,
                            evidence_quality, identity, invalid_time, stable_id)


def study_work_evidence(payload, *, received_at, ttl_seconds=3600):
    observation = study_snapshot_observation(payload, received_at=received_at, ttl_seconds=ttl_seconds)
    if not isinstance(payload, dict) or not payload:
        return WorkEvidenceRead((), observation)
    if (type(payload.get("schemaVersion")) is not int or payload["schemaVersion"] != 1
            or payload.get("source") != "study"):
        return WorkEvidenceRead((), degraded(observation, "study_work_schema_invalid"))
    time_error = invalid_time(observation)
    if time_error:
        return WorkEvidenceRead((), time_error)
    vocab = payload.get("vocab")
    today = vocab.get("today") if isinstance(vocab, dict) else None
    today = today if isinstance(today, dict) else {}
    explicit = payload.get("today", {})
    explicit = explicit if isinstance(explicit, dict) else {}
    buckets = [(name, today.get(name, [])) for name in ("review", "focus", "new")]
    buckets.append(("item", explicit.get("items", [])))
    if any(not isinstance(items, list) for _, items in buckets):
        return WorkEvidenceRead((), degraded(observation, "study_work_shape_invalid"))
    if sum(len(items) for _, items in buckets) > MAX_SOURCE_ITEMS:
        return WorkEvidenceRead((), degraded(observation, "study_work_too_many_items"))
    facts, invalid = [], False
    for bucket, items in buckets:
        for item in items:
            if not isinstance(item, dict):
                invalid = True
                continue
            word_id = stable_id(item.get("word_id") or item.get("wordId"))
            item_id = word_id or stable_id(item.get("id"))
            title = bounded_text(item.get("title") or item.get("text") or item.get("label"), 240)
            if not item_id or (bucket == "item" and (
                    item.get("actionKind") != "study" or not title)):
                invalid = True
                continue
            if any(key in item and type(item[key]) is not bool
                   for key in ("required", "muted", "attentionRequested")):
                invalid = True
                continue
            if bucket != "item":
                title = bounded_text(item.get("kanji") or item.get("reading"), 80, "Study word")
                summary = " / ".join(filter(None, (bounded_text(item.get("reading"), 80),
                                                   bounded_text(item.get("meaning"), 160))))
            else:
                summary = bounded_text(item.get("summary"), 240)
            key = identity("study", "word" if bucket != "item" or word_id else "item", item_id)
            facts.append(dict(evidence_id=identity("study", bucket, key), integration_id="study",
                kind=EvidenceKind.STUDY_ITEM, source_ref=f"study:{item_id}", dedup_key=key,
                title=title, summary=summary, action_kind=ActionKind.STUDY,
                required=bucket == "review" or item.get("required", False),
                muted=item.get("muted", False),
                attention_requested=bucket == "focus" or item.get("attentionRequested", False),
                importance=Importance.HIGH if bucket == "focus" else Importance.NORMAL))
    if invalid:
        observation = degraded(observation, "study_work_invalid_items")
    evidence = tuple(SourceEvidence(**fact, **evidence_quality(observation)) for fact in facts)
    return WorkEvidenceRead(evidence, observation)


def read_study_work(file_path, *, received_at, ttl_seconds=3600, max_bytes=DEFAULT_MAX_SNAPSHOT_BYTES):
    _validate_ttl(ttl_seconds)
    _validate_max_bytes(max_bytes)
    try:
        payload = read_json_handoff(file_path, max_bytes=max_bytes)
    except HandoffReadError as exc:
        if exc.code == "missing":
            return WorkEvidenceRead((), study_snapshot_observation(
                None, received_at=received_at, ttl_seconds=ttl_seconds))
        return WorkEvidenceRead((), _read_failure_observation(received_at=received_at,
            limitation=f"study_snapshot_{exc.code}", availability=(
                AvailabilityStatus.OFFLINE if exc.code == "read_failed" else AvailabilityStatus.PARTIAL)))
    return study_work_evidence(payload, received_at=received_at, ttl_seconds=ttl_seconds)
