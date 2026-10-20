"""Current Web/Core parity; no legacy page or private/running Core IO."""
import copy
import json
import unittest
from unittest.mock import Mock

from kuro_launcher.qt_web_adapter import QtOwnerAdapter
from kuro_launcher.qt_web_protocol import CONTRACT, RequestBroker
from web_candidate_fixtures import ChatFixture, controller_fixture, core_today


class CoreWebTests(unittest.TestCase):
    def setUp(self):
        self.controller = controller_fixture()
        self.chat = ChatFixture()
        self.adapter = QtOwnerAdapter(self.controller, self.chat, lambda w, d: d(w()), window_action=Mock())
        self.confirm = Mock(return_value=True)
        self.replies = []
        self.broker = RequestBroker(self.adapter, self.confirm, self.replies.append)
        self.addCleanup(self.broker.close)

    def call(self, method, payload=None):
        self.broker.submit(json.dumps(dict(contract=CONTRACT, id=f"core-{len(self.replies)}",
            method=method, payload=payload or {}, expected=self.adapter.identity())))
        return self.replies[-1]["result"]

    def test_today_repeated_reads_preserve_core_order_evidence_and_limitations(self):
        data = core_today()
        for _ in range(5):
            self.controller.read_today.return_value = copy.deepcopy(data)
            result = self.call("getData")
            self.assertEqual(result["canonical"], data)
            self.assertEqual([r["id"] for r in result["snapshot"]["today"]["items"]],
                             [r["workId"] for r in data["items"]])
            self.assertIn("synthetic-evidence", result["snapshot"]["today"]["items"][0]["evidence"])
        self.assertEqual(self.chat.calls, [])
        self.controller.mutate_schedule.assert_not_called()

    def test_invalid_and_offline_today_never_promote_cached_evidence_to_success(self):
        self.assertTrue(self.call("getData")["ok"])
        for data in ({}, dict(core_today(), complete="true"), dict(core_today(), items=None)):
            self.controller.read_today.return_value = data
            self.assertFalse(self.call("getData")["ok"])
        self.controller.read_today.side_effect = ConnectionError("SYNTHETIC private detail")
        result = self.call("getData")
        self.assertFalse(result["ok"])
        self.assertNotIn("snapshot", result)
        self.assertNotIn("private detail", json.dumps(result))

    def test_schedule_scope_revision_and_retry_key_reach_core_unchanged(self):
        for action in ("update", "complete", "reopen", "skip", "cancel"):
            for scope in ("this", "future", "all"):
                command = dict(action=action, id="fixture", expectedRevision=7, scope=scope,
                    idempotencyKey=f"synthetic-{action}-{scope}", occurrenceDate="2026-10-10")
                if action == "update":
                    command["item"] = {"title": "SYNTHETIC"}
                result = self.call("schedule", {"action": "mutate", "payload": command})
                self.assertTrue(result["ok"], result)
                self.controller.mutate_schedule.assert_called_with({**command, "confirmed": True})

    def test_schedule_cancel_and_core_materialize_do_not_dispatch(self):
        self.confirm.return_value = False
        command = dict(action="cancel", id="fixture", expectedRevision=7, scope="this",
            occurrenceDate="2026-10-10", idempotencyKey="cancel-once")
        self.assertTrue(self.call("schedule", {"action": "mutate", "payload": command})["cancelled"])
        result = self.call("schedule", {"action": "materialize", "payload": {"through": "2026-10-17"}})
        self.assertEqual(result["error"], "materialize_owned_by_core_scheduler")
        self.controller.mutate_schedule.assert_not_called()
        self.controller.materialize_schedule.assert_not_called()

    def test_schedule_prepare_failure_and_offline_reads_remain_explicit(self):
        self.controller.prepare_schedule.side_effect = ValueError("invalid wall time")
        self.assertFalse(self.call("schedule", {"action": "prepare", "payload": {"item": {}}})["ok"])
        self.controller.mutate_schedule.assert_not_called()
        self.controller.read_schedule_view.side_effect = ConnectionError("offline")
        result = self.call("schedule", {"action": "view", "payload": {
            "start": "2026-10-10", "end": "2026-10-17", "timezone": "Asia/Taipei"}})
        self.assertFalse(result["ok"])
        self.assertNotIn("items", result)
