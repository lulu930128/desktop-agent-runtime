import json
import unittest

from preview_protocol import PreviewProtocol, READS


class PreviewProtocolTests(unittest.TestCase):
    def setUp(self):
        self.port = PreviewProtocol()
        self.seq = 0

    def call(self, command, payload=None, **changes):
        self.seq += 1
        value = {"id": self.seq, "context": self.port.fixture["context"], "revision": 1,
                 "command": command, "payload": payload or {}}
        value.update(changes)
        return json.loads(self.port.request(json.dumps(value)))

    def test_fixture_reads_are_detached_and_bounded(self):
        for command in READS:
            self.assertEqual(self.call(command)["result"], self.port.fixture[command])
        self.call("getProfile")["result"]["models"].clear()
        self.assertTrue(self.call("getProfile")["result"]["models"])

    def test_all_mutations_and_owner_calls_fail_closed(self):
        for command in ["sendText", "applyProfile", "deleteHistory", "memoryAction", "control",
                        "refreshMail", "getMailMessage", "schedule.mutate", "schedule.materialize",
                        "schedule.prepare", "schedule.notification-action", "__proto__"]:
            self.assertFalse(self.call(command)["result"]["ok"])

    def test_identity_revision_duplicate_and_payload_fences(self):
        self.assertEqual(self.call("getState", context="private")["result"]["error"], "stale_context")
        self.assertEqual(self.call("getState", revision=2)["result"]["error"], "stale_context")
        self.assertFalse(self.call("getState", id=1)["result"]["ok"])
        self.assertFalse(self.call("getState", id=True)["result"]["ok"])
        self.assertFalse(self.call("getState", {"path": "private"})["result"]["ok"])
        self.assertFalse(self.call("getHistories", {"historyUid": "private"})["result"]["ok"])
        self.assertFalse(self.call("schedule.view", {"limit": 101})["result"]["ok"])

    def test_malformed_and_oversized_requests(self):
        for raw in ["not json", "[]", "null", "{}", "x" * 8193, "\"" + "字" * 4000 + "\""]:
            self.assertFalse(json.loads(self.port.request(raw))["result"]["ok"])


if __name__ == "__main__":
    unittest.main()
