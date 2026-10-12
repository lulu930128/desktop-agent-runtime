"""Synthetic-only Core transport/capability acceptance; no production stack."""
import ast
import http.client
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from kuro_core.api_server import CoreApiServer
from kuro_core.core_app import CoreApplication
from kuro_core.integrations import IntegrationRegistry, StudyIntegration
from kuro_core.schedule_contract import ScheduleConflict
def valid_snapshot(updated_at="2026-10-08T10:00:00Z"):
    return {
        "schemaVersion": 1,
        "updatedAt": updated_at,
        "source": "study",
        "studyType": "japanese",
        "vocab": {
            "stats": {"total": 120, "due": 4, "withMistakes": 7},
            "today": {
                "review": [{"word_id": "review-1", "kanji": "PRIVATE"}],
                "focus": [{"word_id": "focus-1", "meaning": "PRIVATE"}],
                "new": [],
            },
        },
        "today": {"items": [{"title": "PRIVATE"}]},
    }

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "synthetic-core-token-" * 3


def request(port, route, *, method="GET", body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request(method, route, body=body, headers={
            "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json",
            **(headers or {}),
        })
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


class CoreHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "core.sqlite3"
        self.snapshot = self.root / "private-handoff.json"

    def app(self, **kwargs):
        app = CoreApplication(self.db, port=0, token=TOKEN, instance_id="synthetic", **kwargs)
        self.addCleanup(app.stop)
        # Run transport without a background writer for deterministic GET-purity tests.
        app.api.start()
        return app

    def state(self):
        with sqlite3.connect(self.db.as_uri() + "?mode=ro", uri=True) as conn:
            return list(conn.iterdump())

    def test_process_identity_and_nested_schedule_contract(self):
        app = self.app(default_timezone="Asia/Taipei")
        code, result = request(app.port, "/status")
        self.assertEqual(code, 200)
        self.assertEqual(result["contract"], "kuro.core.api.v1")
        self.assertEqual(result["service"], "kuro-core")
        self.assertEqual(result["instanceId"], "synthetic")
        self.assertEqual(result["pid"], os.getpid())
        self.assertEqual(Path(result["sourceRoot"]), ROOT)
        self.assertNotIn("schema", result)
        self.assertNotIn("timezone", result)
        schedule = result["capabilities"]["schedule"]
        self.assertEqual(schedule["contract"], "kuro.core.schedule.v1")
        self.assertEqual(schedule["schema"], 3)
        self.assertEqual(schedule["timezone"], "Asia/Taipei")
        self.assertEqual(schedule["materialization"], "pending")
        self.assertEqual(result["capabilities"]["integrations"], {
            "contract": "kuro.core.integrations.v1", "configured": []})

    def test_auth_origin_unknown_method_and_query_rejection(self):
        app = self.app(study_enabled=True, study_snapshot_path=self.snapshot)
        for route in ("/status", "/v1/integrations/study", "/v1/schedule/notifications"):
            for headers in ({"Authorization": "Bearer wrong"}, {"Origin": ""}, {"Origin": "null"}):
                with self.subTest(route=route, headers=headers):
                    self.assertEqual(request(app.port, route, headers=headers)[0], 401)
        for route in ("/unknown", "/v1/integrations/mail", "/shutdown"):
            self.assertEqual(request(app.port, route)[0], 404)
        self.assertEqual(request(app.port, "/v1/integrations/study", method="POST", body="{}")[0], 404)
        for suffix in ("?x=1", "?x=1&x=2", "?x", "?x="):
            self.assertEqual(request(app.port, "/v1/integrations/study" + suffix)[0], 400)
        self.assertEqual(request(app.port, "/v1/schedule/view?start=a&start=b")[0], 400)

    def test_body_bounds_invalid_json_and_transfer_encoding(self):
        app = self.app()
        for body in ("{", "[]", "null", "", b"\xff", " " * 65537):
            with self.subTest(body_type=type(body).__name__, length=len(body)):
                self.assertEqual(request(app.port, "/v1/schedule/mutate", method="POST", body=body)[0], 400)
        self.assertEqual(request(app.port, "/shutdown?x=1", method="POST", body="{}")[0], 400)
        self.assertEqual(request(app.port, "/shutdown", method="POST", body="{}",
                                 headers={"Transfer-Encoding": "chunked"})[0], 400)
        self.assertEqual(request(app.port, "/shutdown", method="POST", body="{}",
                                 headers={"Content-Type": "text/plain"})[0], 400)

    def test_duplicate_auth_and_length_rejected(self):
        app = self.app()
        for duplicate, expected in (("Authorization", 401), ("Content-Length", 400)):
            conn = http.client.HTTPConnection("127.0.0.1", app.port, timeout=3)
            try:
                conn.putrequest("POST", "/shutdown")
                conn.putheader("Authorization", f"Bearer {TOKEN}")
                conn.putheader("Content-Length", "2")
                conn.putheader("Content-Type", "application/json")
                conn.putheader(duplicate, f"Bearer {TOKEN}" if duplicate == "Authorization" else "2")
                conn.endheaders(b"{}")
                response = conn.getresponse()
                self.assertEqual(response.status, expected)
                response.read()
            finally:
                conn.close()
        self.assertFalse(app.stop_event.is_set())

    def test_study_privacy_and_all_gets_leave_file_and_database_unchanged(self):
        payload = valid_snapshot(datetime.now(timezone.utc).isoformat())
        self.snapshot.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        app = self.app(study_enabled=True, study_snapshot_path=self.snapshot)
        before = self.snapshot.read_bytes(), self.state()
        with patch.object(app.schedule.store, "advance", side_effect=AssertionError("GET write")), \
             patch.object(app.schedule.notifications, "tick", side_effect=AssertionError("GET tick")):
            code, result = request(app.port, "/v1/integrations/study")
            self.assertEqual(code, 200)
            self.assertEqual(result["contract"], "kuro.core.integration.study.v1")
            self.assertEqual(result["item"]["availability"], "available")
            self.assertEqual(result["item"]["freshness"], "current")
            self.assertEqual(result["item"]["connection"], "unknown")
            for route in ("/status", "/v1/schedule/view", "/v1/schedule/notifications"):
                self.assertEqual(request(app.port, route)[0], 200)
        serialized = json.dumps(result, ensure_ascii=False)
        for private in (str(self.snapshot), "秘密單字", "不要外流", "私人學習內容", "word_id", "summary"):
            self.assertNotIn(private, serialized)
        self.assertEqual((self.snapshot.read_bytes(), self.state()), before)

    def test_study_missing_stale_partial_and_oversize_remain_runtime_states(self):
        app = self.app(study_enabled=True, study_snapshot_path=self.snapshot, study_max_bytes=2048)
        self.assertFalse(self.snapshot.exists())
        for content, availability, freshness in (
            (None, "missing", "unknown"),
            (json.dumps(valid_snapshot()), "available", "stale"),
            ("{", "partial", "unknown"),
            (" " * 2049, "partial", "unknown"),
        ):
            with self.subTest(availability=availability, freshness=freshness):
                if content is not None:
                    self.snapshot.write_text(content, encoding="utf-8")
                code, result = request(app.port, "/v1/integrations/study")
                self.assertEqual(code, 200)
                self.assertEqual(result["item"]["availability"], availability)
                self.assertEqual(result["item"]["freshness"], freshness)
                self.assertEqual(result["item"]["connection"], "unknown")

    def test_startup_status_and_disabled_integration_never_read_handoff(self):
        with patch("kuro_core.integrations.build_study_status", side_effect=AssertionError("startup read")):
            app = self.app(study_enabled=True, study_snapshot_path=self.snapshot)
            code, status = request(app.port, "/status")
            self.assertEqual(code, 200)
            self.assertEqual(status["capabilities"]["integrations"]["configured"], ["study"])
            self.assertNotIn(str(self.snapshot), json.dumps(status))
            app.stop()
            disabled = self.app(study_enabled=False, study_snapshot_path=self.snapshot)
            self.assertEqual(request(disabled.port, "/v1/integrations/study")[0], 404)

    def test_enabled_missing_or_unresolved_path_rejected_before_bind_and_db(self):
        for path in (None, "", "  ", "relative.json", "${UNKNOWN}/study.json", "C:\\bad\x00.json"):
            with self.subTest(path=path), patch("kuro_core.core_app.CoreApiServer") as bind:
                with self.assertRaises(ValueError):
                    CoreApplication(self.db, port=0, token=TOKEN, instance_id="test",
                                    study_enabled=True, study_snapshot_path=path)
                bind.assert_not_called()
                self.assertFalse(self.db.exists())

    def test_port_collision_does_not_create_db_or_lease(self):
        app = self.app()
        other = self.root / "untouched" / "other.sqlite3"
        with self.assertRaises(OSError):
            CoreApplication(other, port=app.port, token=TOKEN, instance_id="second")
        self.assertFalse(other.parent.exists())

    def test_same_db_lease_rejects_second_port_and_releases_listener(self):
        self.app()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with self.assertRaises(OSError):
            CoreApplication(self.db, port=port, token=TOKEN, instance_id="second")
        api = CoreApiServer(port=port, token=TOKEN)
        api.stop()

    def test_schema_failure_releases_listener_and_lease(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with patch("kuro_core.schedule_api.KuroCoreStore.initialize", side_effect=RuntimeError("schema")):
            with self.assertRaisesRegex(RuntimeError, "schema"):
                CoreApplication(self.db, port=port, token=TOKEN, instance_id="bad")
        app = CoreApplication(self.db, port=port, token=TOKEN, instance_id="recovered")
        app.stop()

    def test_worker_failure_keeps_process_identity_and_reports_capability_failure(self):
        app = self.app()
        with patch.object(app.schedule.store, "advance", side_effect=RuntimeError("synthetic")), \
             patch.object(app.schedule.stop_event, "wait", side_effect=lambda _: app.schedule.stop_event.set()), \
             self.assertLogs("kuro_core.schedule_api", level="ERROR"):
            app.schedule._materialize()
        code, result = request(app.port, "/status")
        self.assertEqual(code, 200)
        self.assertEqual(result["contract"], "kuro.core.api.v1")
        self.assertEqual(result["capabilities"]["schedule"]["materialization"], "failed")
        self.assertEqual(result["capabilities"]["schedule"]["notificationScheduler"], "failed")

    def test_start_failure_closes_listener_and_database_lease(self):
        app = CoreApplication(self.db, port=0, token=TOKEN, instance_id="start-failure")
        port = app.port
        with patch.object(app.schedule, "start", side_effect=RuntimeError("worker start")):
            with self.assertRaisesRegex(RuntimeError, "worker start"):
                app.start()
        replacement = CoreApplication(self.db, port=port, token=TOKEN, instance_id="replacement")
        replacement.stop()

    def test_live_worker_retains_lease_until_it_stops(self):
        app = self.app()
        app.schedule.worker = Mock()
        app.schedule.worker.is_alive.return_value = True
        with self.assertRaisesRegex(RuntimeError, "retain the database lease"):
            app.stop()
        self.assertIsNotNone(app.schedule._lease)
        with self.assertRaises(OSError):
            CoreApplication(self.db, port=0, token=TOKEN, instance_id="second")
        app.schedule.worker = None
        app.stop()

    def test_schedule_routes_preserve_write_conflicts_and_read_contract(self):
        app = self.app()
        command = {"action": "create", "confirmed": True, "idempotencyKey": "one", "item": {
            "title": "Synthetic", "kind": "deadline", "timezone": "UTC", "allDay": True, "due": "2026-09-12"}}
        code, saved = request(app.port, "/v1/schedule/mutate", method="POST", body=json.dumps(command))
        self.assertEqual(code, 200)
        self.assertEqual(request(app.port, "/v1/schedule/mutate", method="POST", body=json.dumps(command))[1], saved)
        conflict = {"action": "cancel", "id": saved["id"], "expectedRevision": 99,
                    "confirmed": True, "idempotencyKey": "two"}
        self.assertEqual(request(app.port, "/v1/schedule/mutate", method="POST", body=json.dumps(conflict))[0], 409)
        self.assertEqual(request(app.port, "/v1/schedule/mutate", method="POST", body='{"action":"create"}')[0], 403)
        code, item = request(app.port, "/v1/schedule/item?id=" + saved["id"])
        self.assertEqual(code, 200)
        self.assertEqual(item["item"]["title"], "Synthetic")
        with patch.object(app.schedule.notifications, "action", side_effect=ScheduleConflict("lease")):
            self.assertEqual(request(app.port, "/v1/schedule/notification-action", method="POST", body="{}")[0], 409)

    def test_saved_schedule_survives_projection_failure(self):
        app = self.app()
        command = {"action": "create", "confirmed": True, "idempotencyKey": "projection", "item": {
            "title": "Saved", "kind": "deadline", "timezone": "UTC", "allDay": True, "due": "2026-09-12"}}
        with patch.object(app.schedule.store, "advance", side_effect=RuntimeError("projection")), \
             self.assertLogs("kuro_core.schedule_api", level="ERROR"):
            code, saved = request(app.port, "/v1/schedule/mutate", method="POST", body=json.dumps(command))
        self.assertEqual(code, 200)
        self.assertEqual(saved["projection"], "pending")
        self.assertEqual(request(app.port, "/v1/schedule/item?id=" + saved["id"])[1]["item"]["title"], "Saved")

    def test_entrypoint_isolated_child_missing_file_status_and_graceful_shutdown(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        command = [sys.executable, "-B", str(ROOT / "kuro_core_service.py"), "--db", str(self.db),
                   "--port", str(port), "--instance", "synthetic-child", "--study-enabled",
                   "--study-snapshot", str(self.snapshot), "--study-ttl-seconds", "123", "--study-max-bytes", "2048"]
        env = {**os.environ, "KURO_CORE_TOKEN": TOKEN, "PYTHONDONTWRITEBYTECODE": "1"}
        child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            deadline = time.monotonic() + 8
            while True:
                try:
                    code, status = request(port, "/status")
                    break
                except OSError:
                    if child.poll() is not None or time.monotonic() > deadline:
                        self.fail("Isolated child failed readiness")
                    time.sleep(.05)
            self.assertEqual(code, 200)
            self.assertEqual(status["contract"], "kuro.core.api.v1")
            self.assertEqual(status["pid"], child.pid)
            self.assertEqual(status["instanceId"], "synthetic-child")
            self.assertEqual(status["sourceRoot"], str(ROOT))
            self.assertNotIn(TOKEN, " ".join(command))
            self.assertEqual(request(port, "/v1/integrations/study")[1]["item"]["availability"], "missing")
            self.assertFalse(self.snapshot.exists())
            self.assertEqual(request(port, "/shutdown", method="POST", body="{}")[0], 200)
            self.assertEqual(child.wait(timeout=6), 0)
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=6)


class IntegrationInvariantTests(unittest.TestCase):
    def test_registry_and_wrapper_require_explicit_resolved_path(self):
        for path in (None, "", " ", "relative.json", "${UNRESOLVED}/study.json", "C:\\bad\x00.json"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    IntegrationRegistry(study_enabled=True, study_snapshot_path=path)
                with self.assertRaises(ValueError):
                    StudyIntegration(path)

    def test_registry_validates_ttl_and_max_bytes(self):
        for key, invalid in (("study_ttl_seconds", (0, -1, True, "3600", 1.5, 2592001)),
                             ("study_max_bytes", (0, -1, True, "10", 1.5, 16777217))):
            for value in invalid:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    IntegrationRegistry(**{key: value})

    def test_host_and_schedule_import_boundaries(self):
        def imports(name):
            tree = ast.parse((ROOT / "kuro_core" / name).read_text(encoding="utf-8"))
            return {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertTrue(imports("api_server.py").isdisjoint({"schedule_store", "study_adapter", "integrations", "schedule_api"}))
        self.assertTrue(imports("schedule_api.py").isdisjoint({"study_adapter", "integrations"}))
        self.assertTrue(imports("integrations.py").isdisjoint({"storage", "schedule_store", "schedule_api"}))


if __name__ == "__main__":
    unittest.main()
