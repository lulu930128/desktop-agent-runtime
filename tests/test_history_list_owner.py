"""Read-only History list owner regression; no live Qt or history mutations."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

from kuro_launcher.qt_web_adapter import QtOwnerAdapter
from kuro_launcher.qt_web_protocol import CONTRACT, RequestBroker
from web_candidate_fixtures import ChatFixture, controller_fixture


class HistoryListOwnerTests(unittest.TestCase):
    def setUp(self):
        self.chat = ChatFixture()
        self.chat.current_history_uid = ""
        self.adapter = QtOwnerAdapter(controller_fixture(), self.chat, lambda w, d: d(w()), window_action=Mock())
        self.replies = []
        self.broker = RequestBroker(self.adapter, Mock(side_effect=AssertionError("read must not confirm")), self.replies.append)
        self.sequence = 0

    def call(self, method):
        self.sequence += 1
        self.broker.submit(json.dumps({"contract": CONTRACT, "id": f"history-list-{self.sequence}",
            "expected": self.adapter.identity(), "method": method,
            "payload": {"historyUid": ""} if method == "getHistories" else {}}))

    def reply(self, **changes):
        self.chat.history_pending = False
        self.adapter.receive({"type": "history-list", "request_id": self.chat.history_request_id,
            "client_uid": self.chat.client_uid, "conf_uid": self.chat.conf_uid,
            "context_id": self.chat.context_id, "current_history_uid": "",
            "histories": [{"uid": f"anonymous-{i}"} for i in range(22)], **changes})

    def test_empty_selected_uid_returns_all_22_without_select_create_or_delete(self):
        self.call("getHistories")
        self.reply()
        result = self.replies[-1]["result"]
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["histories"]), 22)
        self.assertEqual(result["historyUid"], "")
        self.assertEqual(self.chat.calls, [("list",)])
        self.assertEqual(self.replies[-1]["identity"]["history"], "")

    def test_not_ready_list_fails_while_transcript_snapshot_is_ok_and_empty(self):
        self.chat.history_ready = False
        self.call("getHistories")
        self.assertEqual(self.replies[-1]["result"]["error"], "conversation_not_ready")
        self.call("getChatHistory")
        self.assertTrue(self.replies[-1]["result"]["ok"])
        self.assertEqual(self.replies[-1]["result"]["histories"], [])
        self.assertFalse(self.chat.calls)

    def test_wrong_context_reply_cannot_complete_or_adopt_list(self):
        self.call("getHistories")
        self.reply(context_id="old-context")
        self.assertFalse(self.replies)
        self.assertEqual(self.adapter.histories, [])
        self.reply()
        self.assertEqual(len(self.replies[-1]["result"]["histories"]), 22)

    def test_history_error_is_a_failure_not_an_empty_list(self):
        self.call("getHistories")
        self.reply(type="history-error")
        self.assertEqual(self.replies[-1]["result"]["error"], "history_owner_rejected")
        self.assertNotIn("histories", self.replies[-1]["result"])


if __name__ == "__main__":
    unittest.main()
