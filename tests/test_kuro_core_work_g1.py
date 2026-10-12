"""Synthetic G1 contracts/policy. Never open handoffs, providers or production state."""
import ast
import json
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
from itertools import permutations
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from kuro_core.attention import decide_attention
from kuro_core.contracts import AvailabilityStatus as A, ConnectionStatus as C, FreshnessStatus as F, Observation
from kuro_core.mail_adapter import COUNT_KEYS, mail_status_observation
from kuro_core.study_adapter import study_snapshot_observation
from kuro_core.today import build_today_view
from kuro_core.today_shadow import compare_today_shadow
from kuro_core.work_contracts import (
    ActionKind, AttentionDecision, AttentionLevel as L, AttentionReason, EvidenceKind,
    Importance, ReasonCategory, ReasonCode as R, SectionKind, SourceEvidence, SourceState,
    TaskCandidate, TodayItem, TodaySection, TodayView, WorkItem,
)
from kuro_core.work_projection import deduplicate_candidates, materialize_work, project_evidence

UTC = timezone.utc
NOW = datetime(2026, 10, 9, 1, tzinfo=UTC)


def evidence(**changes):
    values = dict(evidence_id="mail:one", integration_id="mail", kind=EvidenceKind.MAIL_MESSAGE,
        source_ref="mail:message/one", dedup_key="mail:one", title="Synthetic action",
        summary="Synthetic bounded summary", observed_at=NOW - timedelta(minutes=1),
        received_at=NOW, valid_until=NOW + timedelta(hours=1), availability=A.AVAILABLE,
        freshness=F.CURRENT, connection=C.CONNECTED, action_kind=ActionKind.REVIEW)
    values.update(changes)
    return SourceEvidence(**values)


def status(source="mail", **changes):
    values = dict(observation_id=f"obs:{source}", integration_id=source, kind="source_status",
        source_ref=f"{source}:status", title="Synthetic aggregate", summary="Not a task",
        observed_at=NOW - timedelta(minutes=1), received_at=NOW,
        valid_until=NOW + timedelta(hours=1), availability=A.AVAILABLE,
        declared_freshness=F.CURRENT, connection=C.CONNECTED, idempotency_key=f"status:{source}",
        details={"highPriority": 3, "todayReview": 8})
    values.update(changes)
    return Observation(**values)


def view(items=(), observations=None, **changes):
    values = dict(as_of=NOW, timezone="Asia/Taipei", expected_sources=("mail",))
    values.update(changes)
    return build_today_view(items, (status(),) if observations is None else observations, **values)


def decision(**changes):
    return decide_attention(materialize_work(project_evidence(evidence(**changes))),
                            as_of=NOW, timezone="Asia/Taipei")


class WorkContractTests(unittest.TestCase):
    def test_versions_and_detached_deterministic_serialization(self):
        fact = evidence(metadata={"b": 1, "a": ["safe"]})
        candidate = project_evidence(fact)
        work = materialize_work(candidate)
        today = view((fact,))
        values = (fact, candidate, work, decision(), decision().reasons[0],
                  today.items[0], today.sections[0], today, today.source_states[0])
        self.assertEqual(len({v.CONTRACT for v in values}), 9)
        for value in values:
            with self.subTest(contract=value.CONTRACT):
                self.assertTrue(value.CONTRACT.endswith(".v1"))
                self.assertEqual(json.loads(value.to_json()), value.to_dict())
                self.assertEqual(value.to_json(), value.to_json())
        self.assertEqual(fact.to_json(), replace(fact, metadata={"a": ["safe"], "b": 1}).to_json())
        wire = fact.to_dict()
        wire["metadata"]["a"].append("changed")
        self.assertEqual(fact.metadata["a"], ("safe",))
        self.assertEqual(today.to_dict()["contract"], "kuro.core.today.v1")

    def test_all_contract_values_are_frozen(self):
        fact = evidence()
        today = view((fact,))
        values = (fact, project_evidence(fact), materialize_work(project_evidence(fact)),
                  decision(), decision().reasons[0], today.items[0], today.sections[0],
                  today, today.source_states[0])
        for value in values:
            with self.subTest(type=type(value).__name__), self.assertRaises(FrozenInstanceError):
                value.unexpected = "mutation"

    def test_metadata_is_copied_and_deeply_frozen(self):
        metadata = {"labels": [{"safe": "value"}]}
        fact = evidence(metadata=metadata)
        metadata["labels"][0]["safe"] = "mutation"
        self.assertEqual(fact.metadata["labels"][0]["safe"], "value")
        with self.assertRaises(TypeError):
            fact.metadata["labels"][0]["safe"] = "mutation"
        with self.assertRaises(TypeError):
            fact.metadata.update({"new": 1})
        with self.assertRaises(TypeError):
            view().counts["total"] = 99

    def test_source_ref_is_required_bounded_opaque_text_with_slash(self):
        ref = "provider://mail/messages/a/b?opaque=reference"
        fact = evidence(source_ref=ref)
        self.assertEqual(materialize_work(project_evidence(fact)).source_ref, ref)
        self.assertEqual(evidence(source_ref="x" * 500).source_ref, "x" * 500)
        for ref in ("", "   ", "x" * 501):
            with self.subTest(ref_length=len(ref)), self.assertRaises(ValueError):
                evidence(source_ref=ref)

    def test_canonical_identifiers_are_strict(self):
        for name in ("evidence_id", "integration_id", "dedup_key"):
            for value in ("", "bad/id", "x" * 161, "private@example.test", 4):
                with self.subTest(field=name, value=value), self.assertRaises((ValueError, TypeError)):
                    evidence(**{name: value})

    def test_text_bounds_and_types(self):
        for changes in ({"title": "x" * 241}, {"title": " "}, {"summary": "x" * 1001},
                        {"title": []}, {"summary": {"raw": "value"}}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                evidence(**changes)

    def test_all_timestamp_fields_require_timezone(self):
        naive = NOW.replace(tzinfo=None)
        for name in ("observed_at", "received_at", "valid_until", "due_at", "remind_at"):
            with self.subTest(field=name), self.assertRaises(ValueError):
                evidence(**{name: naive})
        with self.assertRaises(ValueError):
            view(as_of=naive)
        with self.assertRaises(ValueError):
            view(generated_at=naive)

    def test_normalizes_utc_and_validates_time_order(self):
        taipei = NOW.astimezone(ZoneInfo("Asia/Taipei"))
        self.assertEqual(evidence(received_at=taipei).received_at, NOW)
        self.assertIs(evidence(received_at=taipei).received_at.tzinfo, UTC)
        for changes in ({"valid_until": None}, {"observed_at": NOW + timedelta(seconds=1)},
                        {"valid_until": NOW - timedelta(hours=1)}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                evidence(**changes)
        self.assertIsNone(evidence(freshness=F.UNKNOWN, valid_until=None).valid_until)

    def test_enum_and_boolean_validation(self):
        for name in ("kind", "availability", "freshness", "connection", "action_kind", "importance"):
            with self.subTest(field=name), self.assertRaises(ValueError):
                evidence(**{name: "invalid"})
        for name in ("required", "muted", "attention_requested"):
            for invalid in (1, "false", None):
                with self.subTest(field=name), self.assertRaises(TypeError):
                    evidence(**{name: invalid})
        self.assertIs(evidence(importance="high").importance, Importance.HIGH)

    def test_sensitive_keys_rejected_recursively(self):
        for key in ("access_token", "API-KEY", "Authorization", "Cookie", "credentials",
                    "Password", "private_key", "refreshToken", "secret", "token"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                evidence(metadata={"nested": [{key: "SYNTHETIC_SECRET"}]})
            with self.subTest(detail=key), self.assertRaises(ValueError):
                AttentionReason(code=R.DEFAULT, category=ReasonCategory.PRIORITY, detail={key: "secret"})

    def test_metadata_limits_and_raw_content_rejection(self):
        cases = ({"raw_mail": "SYNTHETIC"}, {"body": "SYNTHETIC"}, {"snippet": "SYNTHETIC"},
                 {"n": float("nan")}, {"n": float("inf")}, {"n": object()}, {"n": "x" * 241},
                 {"list": [0] * 33}, {str(i): 1 for i in range(33)},
                 {"a": {"b": {"c": {"d": {"e": 1}}}}},
                 {f"k{i}": "x" * 240 for i in range(20)}, {1: "invalid"})
        for metadata in cases:
            with self.subTest(case=type(metadata).__name__), self.assertRaises((ValueError, TypeError)):
                evidence(metadata=metadata)

    def test_candidate_work_decision_invariants(self):
        candidate = project_evidence(evidence())
        work = materialize_work(candidate)
        for value, changes in ((candidate, {"action_kind": ActionKind.NONE}),
                (candidate, {"candidate_id": "bad/id"}), (candidate, {"inclusion_reasons": ()}),
                (work, {"status": "completed"}), (work, {"work_id": "bad/id"}),
                (decision(), {"rank": 999}), (decision(), {"included": False}),
                (decision(), {"reasons": ()})):
            with self.subTest(type=type(value).__name__), self.assertRaises(ValueError):
                replace(value, **changes)

    def test_today_contract_consistency_and_collection_bounds(self):
        today = view((evidence(),))
        for changes in ({"items": today.items * 2}, {"sections": ()},
                {"source_states": today.source_states * 2}, {"source_states": ()},
                {"local_date": date(2000, 1, 1)}, {"generated_at": NOW - timedelta(seconds=1)},
                {"counts": {**today.counts, "total": 3}}, {"counts": {**today.counts, "total": True}},
                {"limitations": (R.SOURCE_STALE,)}, {"items": today.items * 1001}):
            with self.subTest(fields=list(changes)), self.assertRaises(ValueError):
                replace(today, **changes)
        with self.assertRaises(ValueError):
            replace(today.sections[0], item_ids=("same", "same"))
        with self.assertRaises(ValueError):
            replace(today.items[0], level=L.MUTED)
        with self.assertRaises(ValueError):
            replace(today.source_states[0], limitation_count=True)


class WorkProjectionTests(unittest.TestCase):
    def test_concrete_mail_and_study_preserve_lineage(self):
        for source, kind in (("mail", EvidenceKind.MAIL_MESSAGE), ("study", EvidenceKind.STUDY_ITEM)):
            fact = evidence(integration_id=source, kind=kind, required=True, muted=True,
                            remind_at=NOW, due_at=NOW, metadata={"safe": "bounded"})
            candidate = project_evidence(fact)
            self.assertIsInstance(candidate, TaskCandidate)
            work = materialize_work(candidate)
            self.assertEqual(work.evidence_id, fact.evidence_id)
            self.assertEqual(work.source_ref, fact.source_ref)
            self.assertEqual(work.metadata, fact.metadata)
            self.assertEqual(work.remind_at, NOW)
            self.assertTrue(work.required and work.muted)
            self.assertEqual(work.status, "open")
            self.assertEqual(candidate.inclusion_reasons, (R.CONCRETE_ACTION,))
            self.assertEqual(work, materialize_work(project_evidence(fact)))

    def test_current_aggregate_adapters_cannot_create_candidates(self):
        stamp = "2026-10-09T00:59:00Z"
        mail = mail_status_observation({"schemaVersion": 1, "source": "gmail_briefing",
            "lastAttemptAt": stamp, "lastSuccessAt": stamp, "lastAttemptOk": True, "errorType": "",
            "counts": dict.fromkeys(COUNT_KEYS, 3),
            "privacy": {"bodyFetched": True, "attachmentsFetched": False, "mailboxModified": False}}, received_at=NOW)
        study = study_snapshot_observation({"schemaVersion": 1, "updatedAt": stamp,
            "source": "study", "studyType": "japanese", "vocab": {
                "stats": {"total": 120, "due": 4, "withMistakes": 7, "statuses": {"new": 30}},
                "today": {"review": [{"word_id": "synthetic"}], "focus": [], "new": []}},
            "today": {"items": [{"title": "SYNTHETIC PRIVATE WORD"}]}}, received_at=NOW, ttl_seconds=3600)
        for observation in (mail, study):
            self.assertIsNone(project_evidence(observation))
            self.assertEqual(observation.availability, A.AVAILABLE)
        result = view((), (mail, study), expected_sources=("mail", "study"))
        self.assertEqual(result.items, ())
        self.assertEqual(result.counts["total"], 0)
        self.assertTrue(result.complete)
        self.assertNotIn("highPriority", result.to_json())
        self.assertNotIn("SYNTHETIC PRIVATE WORD", result.to_json())

    def test_nonactionable_evidence_is_not_work(self):
        self.assertIsNone(project_evidence(evidence(action_kind=ActionKind.NONE)))
        self.assertIsNone(project_evidence(evidence(kind=EvidenceKind.REFERENCE)))
        with self.assertRaises(TypeError):
            project_evidence({"highPriority": 3})
        with self.assertRaises(TypeError):
            materialize_work(status())
        with self.assertRaises(ValueError):
            view((status(),))

    def test_work_identity_comes_only_from_canonical_key(self):
        first = materialize_work(project_evidence(evidence()))
        second = materialize_work(project_evidence(evidence(evidence_id="changed", title="Changed")))
        self.assertEqual(first.work_id, second.work_id)
        self.assertNotEqual(first.candidate_id, second.candidate_id)
        self.assertNotEqual(first.work_id, materialize_work(project_evidence(evidence(dedup_key="different"))).work_id)


class AttentionTests(unittest.TestCase):
    def test_rule_precedence(self):
        cases = (({}, L.NORMAL, R.DEFAULT),
            ({"muted": True, "importance": Importance.CRITICAL}, L.MUTED, R.MUTED),
            ({"required": True, "muted": True}, L.MUST, R.REQUIRED),
            ({"required": True, "due_at": NOW - timedelta(seconds=1)}, L.URGENT, R.OVERDUE),
            ({"required": True, "importance": Importance.CRITICAL}, L.MUST, R.REQUIRED),
            ({"importance": Importance.CRITICAL}, L.URGENT, R.IMPORTANCE_CRITICAL),
            ({"importance": Importance.HIGH}, L.FOCUS, R.IMPORTANCE_HIGH),
            ({"attention_requested": True}, L.FOCUS, R.ATTENTION_REQUESTED),
            ({"due_at": NOW - timedelta(days=2)}, L.FOCUS, R.OVERDUE),
            ({"due_at": NOW + timedelta(hours=1)}, L.WATCH, R.DUE_TODAY),
            ({"due_at": NOW + timedelta(hours=24)}, L.WATCH, R.DUE_SOON),
            ({"remind_at": NOW}, L.WATCH, R.REMINDER_DUE))
        for changes, level, reason in cases:
            with self.subTest(changes=changes):
                result = decision(**changes)
                self.assertEqual(result.level, level)
                self.assertIn(reason, [r.code for r in result.reasons])
                self.assertEqual(result.included, level is not L.MUTED)

    def test_mute_override_is_explicit(self):
        result = decision(required=True, muted=True)
        reason = next(r for r in result.reasons if r.code is R.MUTED)
        self.assertEqual(reason.detail, {"overriddenByRequired": True})
        self.assertTrue(result.included)

    def test_expiry_and_quality_never_elevate_priority(self):
        cases = (({"freshness": F.STALE}, R.SOURCE_STALE),
            ({"valid_until": NOW - timedelta(seconds=1)}, R.SOURCE_STALE),
            ({"availability": A.PARTIAL}, R.SOURCE_PARTIAL),
            ({"availability": A.OFFLINE}, R.SOURCE_OFFLINE),
            ({"availability": A.AUTH_REQUIRED}, R.SOURCE_AUTH_REQUIRED),
            ({"availability": A.MISSING}, R.SOURCE_MISSING),
            ({"connection": C.DISCONNECTED}, R.SOURCE_OFFLINE),
            ({"connection": C.AUTH_REQUIRED}, R.SOURCE_AUTH_REQUIRED),
            ({"freshness": F.UNKNOWN}, R.SOURCE_UNKNOWN))
        for changes, code in cases:
            with self.subTest(changes=changes):
                result = decision(**changes)
                self.assertEqual(result.level, L.NORMAL)
                self.assertIn(code, [r.code for r in result.reasons if r.category is ReasonCategory.QUALITY])

    def test_due_and_validity_exact_boundaries(self):
        result = decision(due_at=NOW, valid_until=NOW)
        codes = [r.code for r in result.reasons]
        self.assertNotIn(R.OVERDUE, codes)
        self.assertNotIn(R.SOURCE_STALE, codes)
        self.assertIn(R.DUE_TODAY, codes)
        self.assertEqual(decision(due_at=NOW + timedelta(hours=24, microseconds=1)).level, L.NORMAL)

    def test_taipei_day_boundary_differs_from_utc(self):
        as_of = datetime(2026, 10, 8, 16, tzinfo=UTC)
        fact = evidence(observed_at=as_of, received_at=as_of, valid_until=as_of + timedelta(days=1),
                        due_at=as_of + timedelta(hours=23))
        work = materialize_work(project_evidence(fact))
        taipei = decide_attention(work, as_of=as_of, timezone="Asia/Taipei")
        utc = decide_attention(work, as_of=as_of, timezone="UTC")
        self.assertIn(R.DUE_TODAY, [r.code for r in taipei.reasons])
        self.assertIn(R.DUE_SOON, [r.code for r in utc.reasons])
        self.assertEqual(view((fact,), (), as_of=as_of).local_date, date(2026, 10, 9))

    def test_dst_spring_forward_uses_local_date_and_elapsed_utc(self):
        as_of = datetime(2026, 3, 8, 5, tzinfo=UTC)  # midnight EST
        fact = evidence(observed_at=as_of, received_at=as_of, valid_until=as_of + timedelta(days=2),
                        due_at=datetime(2026, 3, 9, 3, 59, tzinfo=UTC))  # 23:59 EDT
        result = view((fact,), (), as_of=as_of, timezone="America/New_York")
        self.assertEqual(result.local_date, date(2026, 3, 8))
        self.assertIn(R.DUE_TODAY, result.items[0].reason_codes)
        tomorrow = replace(fact, due_at=datetime(2026, 3, 9, 4, tzinfo=UTC))
        self.assertIn(R.DUE_SOON, view((tomorrow,), (), as_of=as_of,
                                      timezone="America/New_York").items[0].reason_codes)

    def test_dst_fall_back_fold_is_ordered_by_instant(self):
        zone = ZoneInfo("America/New_York")
        early = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)
        late = early.replace(fold=1)
        fact = evidence(observed_at=early, received_at=early, valid_until=late + timedelta(days=1), due_at=late)
        result = decide_attention(materialize_work(project_evidence(fact)), as_of=early, timezone=zone.key)
        self.assertNotIn(R.OVERDUE, [r.code for r in result.reasons])
        self.assertIn(R.DUE_TODAY, [r.code for r in result.reasons])
        reverse = replace(fact, due_at=early)
        result = decide_attention(materialize_work(project_evidence(reverse)), as_of=late, timezone=zone.key)
        self.assertIn(R.OVERDUE, [r.code for r in result.reasons])

    def test_explicit_timezone_and_no_future_evidence(self):
        for zone in ("", "not/a-zone", "+08:00", "../UTC"):
            with self.subTest(zone=zone), self.assertRaises(ValueError):
                view(timezone=zone)
        with self.assertRaises(ValueError):
            decision(received_at=NOW + timedelta(seconds=1))
        with self.assertRaises(ValueError):
            view((evidence(received_at=NOW + timedelta(seconds=1)),))


class DedupTests(unittest.TestCase):
    def test_quality_required_time_identity_precedence(self):
        first = evidence(evidence_id="a", title="First")
        comparisons = (
            (replace(first, availability=A.PARTIAL, required=True), replace(first, evidence_id="b")),
            (replace(first, freshness=F.STALE, required=True), replace(first, evidence_id="b")),
            (first, replace(first, evidence_id="b", required=True)),
            (first, replace(first, evidence_id="b", observed_at=NOW)),
            (replace(first, evidence_id="z"), first),
        )
        for loser, winner in comparisons:
            for order in permutations((loser, winner)):
                with self.subTest(winner=winner.evidence_id):
                    result = deduplicate_candidates(tuple(map(project_evidence, order)), as_of=NOW)
                    self.assertEqual(result.winners[0].evidence_id, winner.evidence_id)
                    self.assertEqual(len(result.suppressed), 1)

    def test_all_permutations_produce_identical_view(self):
        facts = (evidence(), evidence(evidence_id="mail:two", title="Different title", required=True),
                 evidence(evidence_id="study:one", integration_id="study", kind=EvidenceKind.STUDY_ITEM,
                          dedup_key="study:one", title="Synthetic Study"))
        serializations = {view(order, (status(), status("study"))).to_json() for order in permutations(facts)}
        self.assertEqual(len(serializations), 1)
        today = view(facts, (status(), status("study")))
        self.assertEqual(today.counts["duplicateSuppressed"], 1)
        self.assertEqual(today.counts["total"], 2)
        self.assertIn(R.DUPLICATE_SUPPRESSED, today.items[0].reason_codes)

    def test_same_id_conflicting_payload_still_has_stable_winner(self):
        first, second = evidence(title="A"), evidence(title="B")
        self.assertEqual(view((first, second)), view((second, first)))

    def test_no_fuzzy_dedup_or_cross_source_identity_guessing(self):
        first = evidence(title="Same title")
        second = evidence(evidence_id="two", dedup_key="two", title="Same title")
        self.assertEqual(view((first, second)).counts["total"], 2)
        shared = replace(second, integration_id="study", kind=EvidenceKind.STUDY_ITEM, dedup_key=first.dedup_key)
        self.assertEqual(view((first, shared)).counts["total"], 1)

    def test_expired_current_loses_to_current(self):
        old = evidence(evidence_id="old", valid_until=NOW - timedelta(seconds=1), required=True)
        new = evidence(evidence_id="new")
        result = deduplicate_candidates(tuple(map(project_evidence, (old, new))), as_of=NOW)
        self.assertEqual(result.winners[0].evidence_id, "new")


class TodayTests(unittest.TestCase):
    def test_required_wire_fields_and_healthy_empty(self):
        today = view()
        self.assertEqual(set(today.to_dict()), {"contract", "generatedAt", "asOf", "localDate", "timezone",
            "complete", "items", "sections", "counts", "sourceStates", "limitations"})
        self.assertTrue(today.complete)
        self.assertEqual(today.items, ())
        self.assertEqual(today.generated_at, NOW)
        self.assertEqual(today.as_of, NOW)
        self.assertEqual(today.local_date, date(2026, 10, 9))
        self.assertEqual(tuple(s.kind for s in today.sections), tuple(SectionKind))

    def test_missing_expected_source_is_degraded_empty(self):
        result = view((), ())
        self.assertFalse(result.complete)
        self.assertEqual(result.items, ())
        self.assertEqual(result.source_states[0].availability, A.MISSING)
        self.assertIn(R.SOURCE_MISSING, result.limitations)
        self.assertNotEqual(result, view())

    def test_all_quality_degradations_set_incomplete_without_fake_task(self):
        changes = ({"availability": A.MISSING}, {"availability": A.OFFLINE},
            {"availability": A.AUTH_REQUIRED}, {"availability": A.PARTIAL}, {"availability": A.UNKNOWN},
            {"declared_freshness": F.STALE}, {"declared_freshness": F.UNKNOWN},
            {"connection": C.DISCONNECTED}, {"connection": C.AUTH_REQUIRED},
            {"limitations": ("SYNTHETIC_PRIVATE_ERROR",)}, {"valid_until": NOW - timedelta(seconds=1)})
        for change in changes:
            with self.subTest(change=change):
                result = view((), (status(**change),))
                self.assertFalse(result.complete)
                self.assertEqual(result.items, ())
                self.assertTrue(result.limitations)
                self.assertNotIn("SYNTHETIC_PRIVATE_ERROR", result.to_json())

    def test_unknown_connection_does_not_claim_study_provider_connectivity(self):
        result = view((), (status("study", connection=C.UNKNOWN),), expected_sources=("study",))
        self.assertTrue(result.complete)
        self.assertEqual(result.source_states[0].connection, C.UNKNOWN)

    def test_item_quality_flags_and_health_are_independent(self):
        result = view((evidence(availability=A.PARTIAL, freshness=F.STALE),))
        self.assertTrue(result.source_states[0].healthy)
        self.assertFalse(result.complete)
        self.assertTrue(result.items[0].partial and result.items[0].stale)
        self.assertEqual(result.items[0].level, L.NORMAL)

    def test_included_evidence_does_not_prove_source_health(self):
        result = view((evidence(),), ())
        self.assertEqual(len(result.items), 1)
        self.assertFalse(result.complete)
        self.assertEqual(result.source_states[0].availability, A.MISSING)

    def test_sections_counts_sorting_and_suppression(self):
        facts = (evidence(evidence_id="critical", dedup_key="critical", importance=Importance.CRITICAL),
            evidence(evidence_id="required", dedup_key="required", required=True),
            evidence(evidence_id="focus", dedup_key="focus", attention_requested=True),
            evidence(evidence_id="watch", dedup_key="watch", due_at=NOW), evidence(),
            evidence(evidence_id="muted", dedup_key="muted", muted=True),
            evidence(evidence_id="duplicate", dedup_key="muted", muted=True))
        result = view(facts)
        self.assertEqual([i.level for i in result.items], [L.URGENT, L.MUST, L.FOCUS, L.WATCH, L.NORMAL])
        self.assertEqual([len(s.item_ids) for s in result.sections], [2, 1, 1, 1])
        self.assertEqual(result.counts["total"], 5)
        self.assertEqual(result.counts["muted"], 1)
        self.assertEqual(result.counts["duplicateSuppressed"], 1)
        self.assertEqual(result.counts["suppressed"], 2)
        self.assertEqual(result, view(tuple(reversed(facts))))

    def test_due_then_stable_id_order_within_same_level(self):
        facts = tuple(evidence(evidence_id=f"e{i}", dedup_key=f"key{i}", importance=Importance.HIGH,
                              due_at=due) for i, due in enumerate((None, NOW + timedelta(hours=1), NOW)))
        self.assertEqual([i.due_at for i in view(facts).items], [NOW, NOW + timedelta(hours=1), None])

    def test_latest_status_uses_received_time_including_failure(self):
        older = status(received_at=NOW - timedelta(seconds=1))
        failed = status(connection=C.DISCONNECTED, observed_at=NOW - timedelta(days=1), declared_freshness=F.STALE)
        result = view((), (older, failed))
        self.assertEqual(result.source_states[0].connection, C.DISCONNECTED)
        self.assertFalse(result.complete)
        self.assertEqual(result, view((), (failed, older)))

    def test_equal_timestamp_status_conflicts_are_conservative(self):
        healthy, stale = status(), status(declared_freshness=F.STALE)
        self.assertEqual(view((), (healthy, stale)), view((), (stale, healthy)))
        self.assertFalse(view((), (healthy, stale)).complete)

    def test_future_status_is_not_historical_truth(self):
        future = status(received_at=NOW + timedelta(seconds=1))
        result = view((), (future,))
        self.assertFalse(result.complete)
        self.assertEqual(result.source_states[0].availability, A.MISSING)
        with self.assertRaises(ValueError):
            view((), (status(kind="not_source_status"),))

    def test_source_state_does_not_copy_private_aggregate_details(self):
        raw = "SYNTHETIC_PRIVATE_MARKER"
        result = view((), (status(title=raw, summary=raw, source_ref=raw,
                                  details={"raw_message": raw}, limitations=(raw,)),))
        self.assertNotIn(raw, result.to_json())
        self.assertEqual(result.source_states[0].limitation_count, 1)
        self.assertEqual(set(result.to_dict()["sourceStates"][0]), {"contract", "integrationId", "availability",
            "freshness", "connection", "observedAt", "validUntil", "limitationCount"})

    def test_no_configured_sources_is_explicit_empty(self):
        result = view((), (), expected_sources=())
        self.assertTrue(result.complete)
        self.assertEqual(result.source_states, ())
        with self.assertRaises(TypeError):
            build_today_view((), (), as_of=NOW, timezone="Asia/Taipei")

    def test_evidence_and_source_count_caps_fail_without_truncation(self):
        with self.assertRaises(ValueError):
            view((evidence(),) * 1001)
        with self.assertRaises(ValueError):
            view((), (status(),) * 1001)
        with self.assertRaises(ValueError):
            view(expected_sources=tuple(f"source{i}" for i in range(65)))


class TodayShadowTests(unittest.TestCase):
    def compare(self, new=None, legacy=None, mapping=None, **kwargs):
        return compare_today_shadow(view((evidence(),)) if new is None else new,
            {"items": [{"id": "old-1", "source": "mail", "level": "normal"}]} if legacy is None else legacy,
            legacy_identity_map={"old-1": "mail:one"} if mapping is None else mapping,
            hash_key=b"synthetic-comparison-scope", **kwargs)

    def test_overlap_level_changes_and_unmatched_counts(self):
        new = view((evidence(importance=Importance.HIGH), evidence(evidence_id="new", dedup_key="new")))
        old = {"items": [{"id": "old-1", "source": "mail", "level": "normal"},
                         {"id": "old-2", "source": "study", "level": "watch"}]}
        report = self.compare(new, old, {"old-1": "mail:one", "old-2": "study:old"})
        self.assertEqual((report["overlap"], report["newOnly"], report["legacyOnly"], report["levelChanged"]), (1, 1, 1, 1))
        self.assertEqual(report["levelTransitions"], {"normal->focus": 1})
        self.assertEqual(report["new"]["bySource"], {"mail": 2})
        self.assertEqual(report["legacy"]["byLevel"]["watch"], 1)

    def test_private_text_and_source_labels_never_leave_report(self):
        secret = "SYNTHETIC_PRIVATE_MESSAGE"
        new = view((evidence(title=secret, summary=secret, source_ref=secret, metadata={"safe": secret}),))
        legacy = {"items": [{"id": secret, "source": secret, "level": "normal", "title": secret,
                             "text": secret, "snippet": secret, "body": secret, "rawStudy": secret}], "rawMail": secret}
        report = self.compare(new, legacy, {secret: "mail:one"})
        encoded = json.dumps(report)
        for forbidden in (secret, "mail:one", "synthetic-comparison-scope", "snippet", "rawMail", "rawStudy"):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual(report["legacy"]["bySource"], {"other": 1})
        self.assertEqual(report["overlap"], 1)

    def test_hash_samples_are_bounded_and_order_independent(self):
        facts = tuple(evidence(evidence_id=f"e{i}", dedup_key=f"key{i}") for i in range(30))
        result = self.compare(view(facts), {"items": []}, {}, sample_limit=3)
        self.assertEqual(len(result["identitySamples"]["newOnly"]), 3)
        for sample in result["identitySamples"]["newOnly"]:
            self.assertRegex(sample, r"^[0-9a-f]{64}$")
        self.assertEqual(result, self.compare(view(tuple(reversed(facts))), {"items": []}, {}, sample_limit=3))
        self.assertEqual(self.compare(sample_limit=0)["identitySamples"]["overlap"], [])

    def test_keyed_identity_scope_changes_hashes(self):
        new = view((evidence(),))
        old = {"items": [{"id": "old-1", "level": "normal", "source": "mail"}]}
        first = self.compare(new, old)
        second = compare_today_shadow(new, old, legacy_identity_map={"old-1": "mail:one"}, hash_key=b"different-synthetic-scope")
        self.assertNotEqual(first["identitySamples"], second["identitySamples"])
        self.assertEqual(first["overlap"], second["overlap"])

    def test_no_title_identity_fallback_and_sanitized_errors(self):
        for legacy in ({"items": [{"title": "PRIVATE"}]},
                {"items": [{"id": "missing-map", "level": "normal"}]},
                {"items": [{"id": "old-1", "level": "PRIVATE_INVALID_LEVEL"}]}):
            with self.assertRaises(ValueError) as raised:
                self.compare(legacy=legacy)
            self.assertNotIn("PRIVATE", str(raised.exception))

    def test_bounds_and_unknown_source_sanitization(self):
        for limit in (-1, 17, True, "1"):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.compare(sample_limit=limit)
        with self.assertRaises(ValueError):
            compare_today_shadow(view(), {"items": []}, legacy_identity_map={}, hash_key=b"short")
        with self.assertRaises(ValueError):
            self.compare(legacy={"items": [{}] * 1001})
        new = view((evidence(integration_id="private-source-label"),))
        self.assertNotIn("private-source-label", json.dumps(self.compare(new)))

    def test_duplicate_legacy_logical_items_are_order_independent(self):
        rows = [{"id": "one", "level": "normal", "source": "mail"},
                {"id": "two", "level": "focus", "source": "mail"}]
        mapping = {"one": "mail:one", "two": "mail:one"}
        report = self.compare(legacy={"items": rows}, mapping=mapping)
        self.assertEqual(report, self.compare(legacy={"items": list(reversed(rows))}, mapping=mapping))
        self.assertEqual(report["overlap"], 1)
        self.assertEqual(report["legacy"]["byLevel"]["focus"], 1)


class G1BoundaryTests(unittest.TestCase):
    def test_pipeline_has_no_provider_file_db_or_process_io(self):
        # Warm standard-library timezone data before denying all domain IO.
        ZoneInfo("Asia/Taipei")
        fact, observation = evidence(), status()
        with patch("builtins.open", side_effect=AssertionError("No file IO")), \
                patch("pathlib.Path.open", side_effect=AssertionError("No path IO")), \
                patch("socket.socket", side_effect=AssertionError("No network")), \
                patch("sqlite3.connect", side_effect=AssertionError("No DB")), \
                patch("subprocess.Popen", side_effect=AssertionError("No processes")):
            today = view((fact,), (observation,))
            report = compare_today_shadow(today, {"items": []}, legacy_identity_map={}, hash_key=b"synthetic-boundary-key")
            self.assertEqual(report["newOnly"], 1)

    def test_g1_imports_only_pure_modules(self):
        root = Path(__file__).resolve().parents[1] / "kuro_core"
        allowed = {"__future__", "json", "math", "dataclasses", "datetime", "enum", "typing", "zoneinfo",
                   "hashlib", "hmac", "collections", "contracts", "work_contracts", "work_projection", "attention"}
        for name in ("work_contracts", "work_projection", "attention", "today", "today_shadow"):
            tree = ast.parse((root / f"{name}.py").read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(all(n.name in allowed for n in node.names), name)
                elif isinstance(node, ast.ImportFrom):
                    self.assertIn(node.module, allowed, name)


if __name__ == "__main__":
    unittest.main()
