"""SYNTHETIC negative/property checks; no native acceptance or user state."""
import copy
import itertools
import json
import unittest
from unittest.mock import Mock

from kuro_launcher.qt_web_adapter import QtOwnerAdapter, today_projection
from kuro_launcher.qt_web_protocol import CONTRACT, RequestBroker
from web_candidate_fixtures import ChatFixture, controller_fixture, core_today


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.chat, self.controller = ChatFixture(), controller_fixture()
        self.adapter = QtOwnerAdapter(self.controller, self.chat, lambda w, d: d(w()), window_action=Mock())
        self.adapter.state = "idle"
        self.replies = []
        self.confirm = Mock(return_value=True)
        self.broker = RequestBroker(self.adapter, self.confirm, self.replies.append)
        self.sequence = 0

    def call(self, method, payload=None):
        self.sequence += 1
        self.broker.submit(json.dumps(dict(contract=CONTRACT, id=f"negative-{self.sequence}",
            method=method, payload=payload or {}, expected=self.adapter.identity())))
        return self.replies[-1]["result"] if self.replies else None

    def test_failed_memory_refresh_revokes_previous_review(self):
        self.call("getMemories")
        self.controller.read_memory_records.side_effect = OSError("SYNTHETIC offline")
        self.assertFalse(self.call("getMemories")["ok"])
        self.assertFalse(self.call("memoryAction", {"action": "delete", "payload": {"entry_id": "m1"}})["ok"])
        self.controller.delete_memory.assert_not_called()
        self.confirm.assert_not_called()

    def test_memory_offline_denies_read_and_cached_review_write(self):
        self.call("getMemories")
        self.controller.reset_mock()
        self.chat.connected = self.chat.history_ready = False
        result = self.call("getMemories")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "memory_actor_not_ready")
        self.assertEqual(self.call("memoryAction", {"action":"delete", "payload":{"entry_id":"m1"}})["error"], "memory_actor_not_ready")
        self.assertEqual(self.controller.mock_calls, [])
        self.confirm.assert_not_called()

    def test_memory_partial_disconnect_revokes_review_before_read_or_write(self):
        for connected, ready in ((False, True), (True, False)):
            for first_method in ("getMemories", "memoryAction"):
                with self.subTest(connected=connected, history_ready=ready, first_method=first_method):
                    self.chat.connected = self.chat.history_ready = True
                    self.call("getMemories")
                    self.assertIsNotNone(self.adapter.memory_snapshot)
                    self.controller.reset_mock()
                    self.chat.connected, self.chat.history_ready = connected, ready
                    mutation = {"action":"delete", "payload":{"entry_id":"m1"}}
                    result = self.call(first_method, mutation if first_method == "memoryAction" else {})
                    self.assertFalse(result["ok"])
                    self.assertEqual(result["error"], "memory_actor_not_ready")
                    self.assertIsNone(self.adapter.memory_snapshot)
                    self.chat.connected = self.chat.history_ready = True
                    result = self.call("memoryAction", mutation)
                    self.assertEqual(result["error"], "read_memory_before_confirming")
                    self.assertEqual(self.controller.mock_calls, [])
                    self.confirm.assert_not_called()

    def test_failed_status_refresh_revokes_capture_availability(self):
        self.controller.read_runtime_status.return_value.capture_available = True
        self.call("getState")
        self.controller.read_runtime_status.side_effect = OSError("SYNTHETIC device offline")
        self.assertFalse(self.call("getState")["ok"])
        self.assertFalse(self.call("control", {"action": "mic-start", "payload": {}})["ok"])
        self.controller.run_pet_command.assert_not_called()

    def test_profile_matching_but_disconnected_is_not_effective(self):
        self.call("applyProfile", {"character_id": "actor", "project_id": "project",
            "model": "synthetic-model", "thinking_power": "normal"})
        self.chat.context_id = "new-context"
        self.chat.connected = False
        self.adapter.receive({"type": "set-model-and-conf"})
        self.assertEqual(self.replies, [])
        self.chat.connected = True
        self.chat.history_ready = False
        self.adapter.receive({"type": "set-model-and-conf"})
        self.assertEqual(self.replies, [])
        self.chat.history_ready = True
        self.adapter.receive({"type": "set-model-and-conf"})
        self.assertTrue(self.replies[-1]["result"]["effective"])

    def test_nested_capture_failure_cannot_submit_conversation(self):
        self.controller.read_runtime_status.return_value.capture_available = True
        self.call("getState")
        self.call("control", {"action": "mic-start", "payload": {}})
        self.controller.run_pet_command.return_value = {"ok": True, "result": {
            "ok": False, "capture": {"data": "SYNTHETIC"}, "error": "device_offline"}}
        self.assertFalse(self.call("control", {"action": "mic-submit", "payload": {}})["ok"])
        self.assertEqual(self.chat.calls, [])

    def test_memory_actor_changes_during_confirmation(self):
        self.call("getMemories")
        def change(*_):
            self.chat.conf_uid = "other"
            return True
        self.confirm.side_effect = change
        self.assertFalse(self.call("memoryAction", {"action": "compact", "payload": {}})["ok"])
        self.controller.compact_memory.assert_not_called()

    def test_tool_failure_is_unavailable_without_discovery(self):
        self.controller.read_tool_policy_summary.side_effect = OSError("SYNTHETIC missing")
        self.assertFalse(self.call("getTools")["ok"])
        self.assertEqual([c[0] for c in self.controller.mock_calls], ["read_tool_policy_summary"])

    def test_pet_failure_does_not_persist_outfit_or_claim_success(self):
        self.controller.run_pet_command.return_value = {"ok": False, "error": "device_offline"}
        self.assertFalse(self.call("control", {"action": "set-outfit", "payload": {"outfitId": "hoodie"}})["ok"])
        self.controller.set_outfit.assert_not_called()

    def test_materialize_and_delivery_authority_always_denied(self):
        for action in ("materialize", "notification-action"):
            for confirmed in (False, True, None):
                payload = {"confirmed": confirmed, "action": "claim", "expectedRevision": "a"*64, "idempotencyKey": "synthetic"}
                self.assertFalse(self.call("schedule", {"action": action, "payload": payload})["ok"])
        self.assertEqual(self.controller.mock_calls, [])

    def test_today_permutation_and_freshness_properties(self):
        # Exhaustive small product: 6 orders x 3 freshness states x 2 completeness states.
        for order, freshness, complete in itertools.product(itertools.permutations(range(3)), ("current", "stale", "missing"), (True, False)):
            raw = core_today()
            raw["items"] = [raw["items"][i] for i in order]
            raw["complete"] = complete
            raw["sourceStates"][0]["freshness"] = freshness
            before = copy.deepcopy(raw)
            projected = today_projection(raw)
            self.assertEqual(projected["canonical"], before)
            self.assertEqual([r["id"] for r in projected["snapshot"]["today"]["items"]], [r["workId"] for r in raw["items"]])
            self.assertEqual(projected["snapshot"]["sourceStatus"][0]["status"], freshness)
            projected["canonical"]["limitations"].append("not shared")
            self.assertEqual(raw, before)


if __name__ == "__main__":
    unittest.main()
