import ast
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from kuro_core.core_app import CoreApplication
from kuro_core.mail_adapter import mail_status_observation
from kuro_core.mail_work_adapter import mail_work_evidence, read_mail_work
from kuro_core.study_work_adapter import study_work_evidence, read_study_work
from kuro_core.work_contracts import ActionKind, Importance
from g2_fixtures import ROOT, study, mail_snapshot, mail_status, message, work_writer
from test_kuro_core_api_host import TOKEN, request

NOW = datetime(2026, 10, 9, 0, 5, tzinfo=timezone.utc)


class StudyWorkTests(unittest.TestCase):
    def project(self, payload):
        return study_work_evidence(payload, received_at=NOW)

    def test_review_focus_new_and_explicit_action(self):
        payload = study()
        payload["today"]["items"] = [{"id": "i1", "title": "Synthetic item", "actionKind": "study"}]
        result = self.project(payload)
        review, focus, new, explicit = result.evidence
        self.assertTrue(review.required)
        self.assertTrue(focus.attention_requested)
        self.assertEqual(focus.importance, Importance.HIGH)
        self.assertFalse(new.required)
        self.assertEqual(new.importance, Importance.NORMAL)
        self.assertEqual(explicit.title, "Synthetic item")
        self.assertTrue(all(item.action_kind is ActionKind.STUDY for item in result.evidence))

    def test_no_fake_work_from_aggregate_or_invalid_ids_and_action(self):
        payload = study()
        payload["vocab"]["today"] = {"review": [], "focus": [], "new": []}
        self.assertEqual(self.project(payload).evidence, ())
        for invalid in (None, "", "x" * 121, True, {}, [], "bad\nidentity"):
            payload["vocab"]["today"]["review"] = [{"id": invalid}]
            result = self.project(payload)
            self.assertEqual(result.evidence, ())
            self.assertEqual(result.observation.availability.value, "partial")
        payload["vocab"]["today"]["review"] = []
        payload["today"]["items"] = [{"id": "aggregate", "title": "4 words"},
                                      {"id": "item", "title": "Action", "actionKind": "delete"}]
        self.assertEqual(self.project(payload).evidence, ())

    def test_overflow_fails_closed_without_silent_truncation(self):
        payload = study()
        payload["vocab"]["today"]["review"] = [{"id": str(i)} for i in range(501)]
        result = self.project(payload)
        self.assertEqual(result.evidence, ())
        self.assertIn("study_work_too_many_items", result.observation.limitations)

    def test_unknown_future_invalid_timestamp_and_schema_do_not_invent_time(self):
        for stamp in (None, "bad", "2027-01-01T00:00:00Z", "9999-12-31T23:59:59Z"):
            result = self.project(study(stamp))
            self.assertEqual(result.evidence, ())
            self.assertEqual(result.observation.effective_freshness(as_of=NOW).value, "unknown")
        payload = study()
        payload["schemaVersion"] = 2
        self.assertEqual(self.project(payload).evidence, ())

    def test_identity_determinism_bounds_quality_and_no_mutation(self):
        payload = study("2026-10-08T00:00:00Z")
        payload["vocab"]["today"]["review"][0].update(kanji="x" * 1000, meaning="y" * 1000)
        previous = copy.deepcopy(payload)
        first = self.project(payload)
        second = self.project(payload)
        self.assertEqual(first.evidence, second.evidence)
        self.assertEqual(first.observation.idempotency_key, second.observation.idempotency_key)
        self.assertEqual(payload, previous)
        self.assertLessEqual(len(first.evidence[0].title), 80)
        self.assertEqual(first.evidence[0].freshness.value, "stale")
        self.assertEqual(first.evidence[0].observed_at, first.observation.observed_at)

    def test_bounded_file_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "study.json"
            self.assertEqual(read_study_work(path, received_at=NOW).observation.availability.value, "missing")
            for raw in (b"{", b"\xff", b"[]", b" " * 33):
                path.write_bytes(raw)
                result = read_study_work(path, received_at=NOW, max_bytes=32)
                self.assertEqual(result.evidence, ())
                self.assertEqual(result.observation.availability.value, "partial")
                self.assertEqual(path.read_bytes(), raw)


class MailWorkAdapterTests(unittest.TestCase):
    def project(self, messages=None, status=None):
        payload = work_writer.build_work_handoff(mail_snapshot(messages=messages), attempt_at="2026-10-09T00:00:00Z")
        observation = mail_status_observation(status or mail_status(), received_at=NOW)
        return mail_work_evidence(payload, observation)

    def test_mapping_and_stable_per_message_dedup(self):
        result = self.project([message(requiredEvent=True, muted=True, attention=True, priorityLevel="urgent"),
                               message(id="m2", priorityLevel="high")])
        first, second = result.evidence
        self.assertTrue(first.required and first.muted and first.attention_requested)
        self.assertEqual(first.importance, Importance.CRITICAL)
        self.assertEqual(second.importance, Importance.HIGH)
        self.assertEqual(first.action_kind, ActionKind.OPEN)
        self.assertNotEqual(first.dedup_key, second.dedup_key)
        self.assertEqual(first.evidence_id, self.project().evidence[0].evidence_id)

    def test_no_numeric_priority_or_gmail_important_inference(self):
        fact = self.project([message(priorityLevel="medium", priorityScore=99999)]).evidence[0]
        self.assertEqual(fact.importance, Importance.NORMAL)
        self.assertFalse(fact.attention_requested or fact.required)

    def test_provider_failure_retains_work_with_disconnected_quality(self):
        result = self.project(status=mail_status(ok=False))
        self.assertEqual(len(result.evidence), 1)
        self.assertEqual(result.evidence[0].connection.value, "disconnected")
        self.assertEqual(result.observation.connection.value, "disconnected")

    def test_split_generation_is_partial_and_uses_work_time(self):
        result = self.project(status=mail_status("2026-10-09T00:04:00Z"))
        self.assertEqual(result.observation.availability.value, "partial")
        self.assertEqual(result.evidence[0].availability.value, "partial")
        self.assertEqual(result.evidence[0].observed_at.minute, 0)

    def test_raw_fields_invalid_schema_and_duplicate_fail_closed(self):
        good = work_writer.build_work_handoff(mail_snapshot(), attempt_at="2026-10-09T00:00:00Z")
        obs = mail_status_observation(mail_status(), received_at=NOW)
        mutations = [lambda p: p.update(token="FORBIDDEN"),
                     lambda p: p["items"][0].update(body="FORBIDDEN"),
                     lambda p: p["items"][0].update(requiredEvent="yes"),
                     lambda p: p["items"].append(copy.deepcopy(p["items"][0])),
                     lambda p: p.update(updatedAt="2027-01-01T00:00:00Z")]
        for mutate in mutations:
            payload = copy.deepcopy(good)
            mutate(payload)
            result = mail_work_evidence(payload, obs)
            self.assertEqual(result.evidence, ())
            self.assertEqual(result.observation.availability.value, "partial")
            self.assertNotIn("FORBIDDEN", repr(result.observation))


class TodayCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.study = self.root / "study.json"
        self.status = self.root / "status.json"
        self.work = self.root / "work.json"
        self.db = self.root / "db.sqlite3"

    def app(self, enabled=True):
        app = CoreApplication(self.db, port=0, token=TOKEN, instance_id="g2-synthetic",
            default_timezone="Asia/Taipei", study_enabled=enabled, study_snapshot_path=self.study,
            mail_enabled=enabled, mail_status_path=self.status, mail_work_path=self.work)
        app.api.start()
        self.addCleanup(app.stop)
        return app

    def write(self, *, failed=False):
        stamp = datetime.now(timezone.utc).isoformat()
        self.study.write_text(json.dumps(study(stamp)), encoding="utf-8")
        self.status.write_text(json.dumps(mail_status(stamp, ok=not failed)), encoding="utf-8")
        self.work.write_text(json.dumps(work_writer.build_work_handoff(mail_snapshot(stamp), attempt_at=stamp)), encoding="utf-8")

    def test_route_healthy_and_status_configured_independent_of_schedule_schema(self):
        self.write()
        app = self.app()
        code, view = request(app.port, "/v1/today")
        self.assertEqual(code, 200)
        self.assertEqual(view["contract"], "kuro.core.today.v1")
        self.assertTrue(view["complete"])
        self.assertEqual(len(view["items"]), 4)
        self.assertEqual(view["timezone"], "Asia/Taipei")
        self.assertEqual({i["source"] for i in view["items"]}, {s["integrationId"] for s in view["sourceStates"]})
        status = request(app.port, "/status")[1]
        self.assertEqual(status["capabilities"]["today"], {
            "contract": "kuro.core.today.v1", "configured": ["mail", "study"], "timezone": "Asia/Taipei"})
        self.assertNotIn("Synthetic", json.dumps(status))
        self.assertNotIn(str(self.work), json.dumps(status))

    def test_missing_then_degraded_last_good_and_malformed(self):
        app = self.app()
        view = request(app.port, "/v1/today")[1]
        self.assertFalse(view["complete"])
        self.assertEqual(view["items"], [])
        self.assertEqual({s["availability"] for s in view["sourceStates"]}, {"missing"})
        self.assertFalse(self.work.exists())
        self.write(failed=True)
        view = request(app.port, "/v1/today")[1]
        self.assertFalse(view["complete"])
        self.assertEqual(len(view["items"]), 4)
        mail = next(i for i in view["items"] if i["source"] == "mail")
        self.assertIn("source_offline", mail["reasonCodes"])
        self.work.write_bytes(b"{")
        view = request(app.port, "/v1/today")[1]
        self.assertFalse(view["complete"])
        self.assertEqual(len(view["items"]), 3)

    def test_timezone_is_core_config_and_disabled_does_not_read(self):
        app = self.app(enabled=False)
        with patch("kuro_core.today_capability.read_mail_work", side_effect=AssertionError), \
             patch("kuro_core.today_capability.read_study_work", side_effect=AssertionError):
            view = app.today.view(as_of=datetime(2026, 10, 9, 17, tzinfo=timezone.utc))
            self.assertEqual(str(view.local_date), "2026-10-10")
            self.assertTrue(view.complete)
            self.assertEqual(view.items, ())
            self.assertEqual(app.today.status()["configured"], [])

    def test_get_has_no_file_db_provider_side_effects_or_refresh_commands(self):
        self.write()
        app = self.app()
        before_files = {p.name: p.read_bytes() for p in (self.study, self.status, self.work)}
        with sqlite3.connect(self.db) as conn:
            before_db = list(conn.iterdump())
        with patch.object(app.schedule.store, "advance", side_effect=AssertionError("write")), \
             patch.object(app.schedule.notifications, "tick", side_effect=AssertionError("tick")), \
             patch("subprocess.Popen", side_effect=AssertionError("spawn")):
            for _ in range(2):
                self.assertEqual(request(app.port, "/v1/today")[0], 200)
            self.assertEqual(request(app.port, "/v1/today?refresh=1")[0], 400)
            self.assertEqual(request(app.port, "/v1/today", method="POST", body="{}")[0], 404)
            self.assertEqual(request(app.port, "/v1/today", headers={"Authorization": "wrong"})[0], 401)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(list(conn.iterdump()), before_db)
        self.assertEqual({p.name: p.read_bytes() for p in (self.study, self.status, self.work)}, before_files)

    def test_core_work_modules_never_import_provider_or_storage(self):
        forbidden = {"mail_tools_server", "mail_work_handoff", "sqlite3", "storage", "httpx", "requests", "urllib"}
        for name in ("study_work_adapter.py", "mail_work_adapter.py", "today_capability.py", "work_evidence.py"):
            tree = ast.parse((ROOT / "kuro_core" / name).read_text(encoding="utf-8"))
            imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
            imports |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
            self.assertTrue(imports.isdisjoint(forbidden), name)
