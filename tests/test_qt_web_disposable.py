"""Real owner IO in disposable directories/loopback; never native UI acceptance."""
import copy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from kuro_core.api_server import CoreApiServer
from kuro_core.schedule_api import ScheduleCapability
from kuro_launcher.core_runtime import CoreRuntime
from kuro_launcher.qt_controller import QtLauncherController
from kuro_launcher.qt_web_adapter import QtOwnerAdapter
from kuro_launcher.qt_web_protocol import CONTRACT, RequestBroker
from web_candidate_fixtures import ChatFixture

ROOT = Path(__file__).resolve().parents[1]


class DisposableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".validation-web-isolated-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.controller = QtLauncherController.__new__(QtLauncherController)
        self.chat = ChatFixture()
        self.confirm = Mock(return_value=True)
        self.adapter = QtOwnerAdapter(self.controller, self.chat, lambda w, d: d(w()), window_action=Mock())
        self.replies = []
        self.broker = RequestBroker(self.adapter, self.confirm, self.replies.append)
        self.sequence = 0

    def call(self, method, payload=None):
        self.sequence += 1
        self.broker.submit(json.dumps(dict(contract=CONTRACT, id=f"disposable-{self.sequence}", method=method,
            payload=payload or {}, expected=self.adapter.identity())))
        return self.replies[-1]["result"]

    def memory(self):
        environment = patch.dict(os.environ, {"KURO_MEMORY_ROOT": str(self.path/"memories")})
        environment.start()
        self.addCleanup(environment.stop)
        self.controller.cfg = SimpleNamespace(open_llm_dir=self.path)
        self.controller.selected_character = Mock(return_value=SimpleNamespace(conf_uid="actor", conf_name="SYNTHETIC"))
        self.controller.log = Mock()
        # Preserve the actual canonical store/index; disable only external runtime refresh.
        self.controller._maybe_refresh_memory_prompt = Mock()

    def test_real_memory_digest_conflict_preserves_concurrent_content(self):
        self.memory()
        from open_llm_vtuber import character_memory_manager as memory
        self.assertTrue(self.controller.add_memory("SYNTHETIC alpha preference", expected_conf_uid="actor"))
        reviewed = self.call("getMemories")["memories"][0]
        path = memory._store_path("actor")
        self.assertTrue(path.resolve().is_relative_to(self.path.resolve()))
        store = memory._load_store("actor")
        store["entries"][0]["content"] = "SYNTHETIC changed concurrently"
        memory._save_store("actor", store)
        before = path.read_bytes()
        result = self.call("memoryAction", {"action": "delete", "payload": {"entry_id": reviewed["id"]}})
        self.assertFalse(result["ok"])
        self.assertEqual(path.read_bytes(), before)
        self.confirm.assert_called_once()
        self.assertTrue((self.path/"memories/character_memory.sqlite3").is_file())

    def test_real_memory_cancel_then_add_disable_delete(self):
        self.memory()
        self.call("getMemories")
        self.confirm.return_value = False
        payload = {"action": "add", "payload": {"content": "SYNTHETIC alpha preference"}}
        self.assertTrue(self.call("memoryAction", payload)["cancelled"])
        self.assertEqual(list(self.path.rglob("*.json")), [])
        self.confirm.return_value = True
        self.assertTrue(self.call("memoryAction", payload)["changed"])
        reviewed = self.call("getMemories")["memories"][0]
        self.assertTrue(self.call("memoryAction", {"action": "status", "payload": {"entry_id": reviewed["id"], "status": "disabled"}})["changed"])
        self.assertEqual(self.call("getMemories")["memories"][0]["status"], "disabled")
        self.assertTrue(self.call("memoryAction", {"action": "delete", "payload": {"entry_id": reviewed["id"]}})["changed"])
        self.assertEqual(self.call("getMemories")["memories"], [])

    def core(self):
        self.capability = ScheduleCapability(self.path/"synthetic.sqlite3", default_timezone="UTC")
        self.addCleanup(self.capability.stop)
        self.api = CoreApiServer(port=0, token="synthetic-w4-w6-disposable-token-0000")
        self.capability.register_routes(self.api)
        self.api.register("GET", "/status", lambda _: {"contract": "kuro.core.api.v1", "capabilities": {"schedule": self.capability.status()}})
        self.api.start()
        self.addCleanup(self.api.stop)
        self.controller.core_runtime = CoreRuntime(SimpleNamespace(core_enabled=True, core_port=self.api.port), lambda _: None)
        self.controller.core_runtime.token = "synthetic-w4-w6-disposable-token-0000"
        self.assertIsNone(self.capability.worker)

    def schedule(self, action, payload=None):
        return self.call("schedule", {"action": action, "payload": payload or {}})

    def test_http_reads_prepare_cancel_and_materialize_do_not_write(self):
        self.core()
        before = self.capability.store.path.read_bytes()
        item = {"title": "SYNTHETIC", "kind": "deadline", "timezone": "UTC", "allDay": True, "due": "2026-10-11"}
        for action, payload in (("status", {}), ("notifications", {}),
                ("view", {"start": "2026-10-10", "end": "2026-10-12", "timezone": "UTC"}), ("prepare", {"item": item})):
            self.assertTrue(self.schedule(action, payload)["ok"])
        self.assertFalse(self.schedule("materialize", {"through": "2026-10-12", "confirmed": True})["ok"])
        self.confirm.return_value = False
        self.assertTrue(self.schedule("mutate", {"action": "create", "item": item, "idempotencyKey": "cancel", "confirmed": True})["cancelled"])
        self.assertEqual(self.capability.store.path.read_bytes(), before)
        self.assertIsNone(self.capability.worker)

    def test_http_mutation_replay_and_revision_conflict(self):
        self.core()
        payload = {"action": "create", "idempotencyKey": "replay", "item": {
            "title": "SYNTHETIC", "kind": "deadline", "timezone": "UTC", "allDay": True, "due": "2026-10-11"}}
        first = self.schedule("mutate", copy.deepcopy(payload))
        self.assertTrue(first["ok"])
        second = self.schedule("mutate", copy.deepcopy(payload))
        self.assertEqual(first, second)
        with self.capability.store.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM schedule_items").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM schedule_mutations").fetchone()[0], 1)
        before = self.capability.store.path.read_bytes()
        stale = self.schedule("mutate", {"action": "cancel", "id": first["id"], "expectedRevision": first["revision"]+1, "idempotencyKey": "stale"})
        self.assertFalse(stale["ok"])
        self.assertEqual(self.capability.store.path.read_bytes(), before)
        # Unknown results remain blocked, never automatically retried.
        self.assertEqual(self.schedule("mutate", payload)["error"], "busy_or_unknown_result")


if __name__ == "__main__":
    unittest.main()
