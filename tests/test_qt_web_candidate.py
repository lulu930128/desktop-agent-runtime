"""W2-W5 synthetic contracts; tests passing do not imply a release gate PASS."""
import copy
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock

from kuro_launcher.qt_web_adapter import QtOwnerAdapter, today_projection
from kuro_launcher.qt_web_protocol import CONTRACT, RequestBroker, Rejected, validate
from kuro_launcher.qt_web_host import AssetBundle, create_candidate
from web_candidate_fixtures import ChatFixture, controller_fixture, core_today


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.chat, self.controller = ChatFixture(), controller_fixture()
        self.events, self.replies = [], []
        self.worker = lambda work, done: done(work())
        self.adapter = QtOwnerAdapter(self.controller, self.chat, lambda work, done: self.worker(work, done),
            window_action=Mock(), event=lambda *a: self.events.append(a))
        self.adapter.state = "idle"
        self.confirm = Mock(return_value=True)
        self.clock = 0
        self.broker = RequestBroker(self.adapter, self.confirm, self.replies.append, clock=lambda: self.clock)
        self.sequence = 0

    def send(self, method, payload=None, **overrides):
        self.sequence += 1
        req = dict(contract=CONTRACT, id=f"r{self.sequence}", method=method,
            payload=payload or {}, expected=self.adapter.identity())
        req.update(overrides)
        self.broker.submit(json.dumps(req))
        return self.replies[-1]["result"] if self.replies else None

    def test_default_host_import_needs_no_addons(self):
        self.assertIsNone(create_candidate(None, "does-not-exist"))
        with self.assertRaises(RuntimeError): create_candidate(None, "", enabled=True)

    def test_hello_requires_contract_and_has_identity(self):
        self.assertTrue(self.send("hello", expected=None)["ok"])
        self.assertEqual(self.replies[-1]["identity"]["actor"], "actor")
        self.assertFalse(self.send("hello", contract="legacy")["ok"])

    def test_unknown_method_no_owner_call(self):
        self.assertFalse(self.send("eval", {"code": "anything"})["ok"])
        self.assertEqual(self.controller.mock_calls, [])

    def test_stale_context_denies_all_owner_io(self):
        expected = self.adapter.identity(); expected["actor"] = "old"
        self.assertEqual(self.send("getData", expected=expected)["error"], "stale_context")
        self.controller.read_today.assert_not_called()

    def test_invalid_payloads(self):
        for raw in ("[]", "null", "{}", "{", json.dumps({"id": []})):
            self.broker.submit(raw)
            self.assertFalse(self.replies[-1]["result"]["ok"])

    def test_duplicate_send_does_not_replay(self):
        p = {"text": "SYNTHETIC", "attachments": []}
        self.send("sendText", p, id="same"); self.send("sendText", p, id="same")
        self.assertEqual(len(self.chat.calls), 1)
        self.assertEqual(self.replies[-1]["result"]["error"], "duplicate_request_no_replay")

    def test_chat_send_has_no_native_confirmation(self):
        self.assertTrue(self.send("sendText", {"text": "SYNTHETIC", "attachments": []})["accepted"])
        self.confirm.assert_not_called()

    def test_history_create_select_have_no_native_confirmation(self):
        for method, payload in (("createHistory", {}), ("selectHistory", {"historyUid": "selected"})):
            with self.subTest(method=method):
                self.setUp(); self.send(method, payload); self.confirm.assert_not_called()
                self.assertIsNotNone(self.adapter.history_wait)

    def test_duplicate_pending_request_does_not_release_mutation_fence(self):
        self.send("createHistory", id="pending")
        self.send("createHistory", id="pending")
        self.send("createHistory", id="pending", contract="invalid")
        self.assertEqual(self.replies, [])
        self.assertEqual(self.chat.calls, [("create",)])
        self.assertIn("pending", self.broker.pending)
        self.assertTrue(self.broker.mutation_pending)
        self.assertEqual(self.send("sendText", {"text": "retry", "attachments": []})["error"], "busy_or_unknown_result")

    def test_history_delete_cancel_never_dispatches(self):
        self.confirm.return_value = False
        self.assertTrue(self.send("deleteHistory", {"historyUid": "h"})["cancelled"])
        self.assertEqual(self.chat.calls, [])

    def test_confirmation_is_bound_to_actor_after_modal(self):
        def change(*_): self.chat.conf_uid = "other"; return True
        self.confirm.side_effect = change
        self.assertEqual(self.send("deleteHistory", {"historyUid": "h"})["error"], "confirmation_context_changed")
        self.assertEqual(self.chat.calls, [])

    def test_confirmation_time_is_not_operation_timeout(self):
        def wait(*_): self.clock = 100; self.broker.expire(); return False
        self.confirm.side_effect = wait
        self.send("deleteHistory", {"historyUid": "h"})
        self.assertEqual(len(self.replies), 1); self.assertTrue(self.replies[0]["result"]["cancelled"])

    def test_history_completion_awaits_correlated_owner_result(self):
        self.send("createHistory")
        self.assertEqual(self.replies, [])
        data = {"type": "new-history-created", "request_id": "wrong", "client_uid": "client", "conf_uid": "actor", "context_id": "context"}
        self.adapter.receive(data); self.assertEqual(self.replies, [])
        self.chat.current_history_uid = "new"; self.chat.history_pending = False
        self.adapter.receive({**data, "request_id": "ws-id", "history_uid": "new"})
        self.assertEqual(self.replies[-1]["result"]["historyUid"], "new")

    def test_timeout_mutation_poison_prevents_retries(self):
        self.send("createHistory"); self.clock = 21; self.broker.expire()
        self.assertTrue(self.replies[-1]["result"]["unknownResult"])
        self.chat.history_pending = False
        self.assertEqual(self.send("sendText", {"text": "retry", "attachments": []})["error"], "busy_or_unknown_result")
        self.assertEqual(len(self.chat.calls), 1)

    def test_late_read_result_does_not_replace_timeout(self):
        tasks = []; self.worker = lambda w, d: tasks.append((w, d))
        self.send("getData"); self.clock = 21; self.broker.expire()
        count = len(self.replies); tasks[0][1](tasks[0][0]())
        self.assertEqual(len(self.replies), count)

    def test_attachment_rejects_wrong_size_mime_count_and_paths(self):
        good = {"kind": "text", "name": "a.txt", "mime_type": "text/plain", "size": 1, "data": "data:text/plain;base64,YQ=="}
        for values in ([{**good, "size": 2}], [{**good, "mime_type": "text/html"}], [good]*7, [{**good, "data": "file:///private"}]):
            with self.subTest(values=values):
                self.assertFalse(self.send("sendText", {"text": "x", "attachments": values})["ok"])
        self.assertEqual(self.chat.calls, [])

    def test_valid_attachment_stays_bounded(self):
        value = {"kind": "text", "name": "SYNTHETIC.txt", "mime_type": "text/plain", "size": 1, "data": "data:text/plain;base64,YQ=="}
        self.assertTrue(self.send("sendText", {"text": "", "attachments": [value]})["ok"])

    def test_busy_and_offline_chat(self):
        self.adapter.state = "thinking"
        self.assertEqual(self.send("sendText", {"text": "x", "attachments": []})["error"], "turn_busy")
        self.chat.history_ready = False
        self.assertEqual(self.send("createHistory")["error"], "conversation_not_ready")

    def test_interrupt_uses_only_chat_owner(self):
        self.send("control", {"action": "interrupt", "payload": {}})
        self.assertEqual(self.chat.calls, [("interrupt",)])
        self.controller.interrupt_pet.assert_not_called(); self.confirm.assert_not_called()

    def test_tool_timeline_is_separate_from_assistant(self):
        self.adapter.on_assistant("assistant")
        scope = dict(zip(("client_uid", "conf_uid", "context_id", "history_uid"), self.chat.history_identity()))
        self.adapter.receive({"type": "tool_call_status", "tool_id": "t", "tool_name": "synthetic", "status": "running", "conversation_scope": scope})
        self.adapter.receive({"type": "tool_call_status", "tool_id": "t", "tool_name": "synthetic", "status": "denied", "conversation_scope": scope})
        state = self.adapter.chat_state()
        self.assertEqual(state["latestAssistantText"], "assistant")
        self.assertEqual(len(state["timeline"]), 1); self.assertEqual(state["timeline"][0]["status"], "denied")

    def test_unscoped_and_wrong_history_stream_cannot_render(self):
        for scope in (None, {"client_uid": "client", "conf_uid": "actor", "context_id": "context", "history_uid": "old"}):
            self.adapter.receive({"type": "full-text", "text": "must not render", "conversation_scope": scope})
            self.adapter.receive({"type": "tool_call_status", "tool_name": "must not render", "conversation_scope": scope})
        self.assertEqual(self.adapter.latest_assistant, ""); self.assertEqual(self.adapter.timeline, [])

    def test_profile_options_from_controller(self):
        result = self.send("getProfile")
        self.assertEqual(result["thinking_options"], ["fast", "normal", "deep"])
        self.assertEqual(result["models"], ["synthetic-model"])

    def test_profile_waits_for_effective_runtime_identity(self):
        self.send("applyProfile", {"character_id": "actor", "project_id": "project", "model": "synthetic-model", "thinking_power": "normal"})
        self.assertEqual(self.replies, []); self.confirm.assert_called_once()
        self.chat.context_id = "new-context"
        self.adapter.receive({"type": "set-model-and-conf"})
        self.assertTrue(self.replies[-1]["result"]["effective"])

    def test_profile_cancel_and_invalid_option(self):
        p = {"character_id": "actor", "project_id": "project", "model": "synthetic-model", "thinking_power": "normal"}
        self.confirm.return_value = False
        self.assertTrue(self.send("applyProfile", p)["cancelled"])
        self.controller.start_profile.assert_not_called()
        self.assertFalse(self.send("applyProfile", {**p, "model": "unregistered"})["ok"])

    def test_memory_digest_and_actor_from_displayed_snapshot(self):
        self.send("getMemories")
        self.send("memoryAction", {"action": "delete", "payload": {"entry_id": "m1"}})
        self.controller.delete_memory.assert_called_once_with("m1", expected_conf_uid="actor", expected_digest="digest1")
        self.assertEqual(self.confirm.call_args.args[1]["review_content"], "SYNTHETIC memory")

    def test_memory_without_review_and_oversize_rejected(self):
        self.assertFalse(self.send("memoryAction", {"action": "delete", "payload": {"entry_id": "m1"}})["ok"])
        self.assertFalse(self.send("memoryAction", {"action": "add", "payload": {"content": "x"*261}})["ok"])
        self.controller.delete_memory.assert_not_called(); self.controller.add_memory.assert_not_called()

    def test_memory_cancel_and_stale_digest(self):
        self.send("getMemories"); self.confirm.return_value = False
        self.assertTrue(self.send("memoryAction", {"action": "compact", "payload": {}})["cancelled"])
        self.controller.compact_memory.assert_not_called()
        self.assertFalse(self.send("memoryAction", {"action": "status", "payload": {"entry_id": "m1", "status": "active", "content_digest": "old"}})["ok"])

    def test_policy_is_read_only(self):
        self.assertFalse(self.send("getTools")["confirmation_available"])
        self.assertFalse(self.send("control", {"action": "set-tool-policy", "payload": {}})["ok"])

    def test_pet_uses_existing_gateway(self):
        self.assertTrue(self.send("control", {"action": "set-expression", "payload": {"expressionId": "neutral"}})["ok"])
        self.controller.set_expression.assert_called_once_with("neutral")
        self.controller.launch_pet_electron.assert_not_called()

    def test_perception_context_changed_submit_denied(self):
        self.controller.read_runtime_status.return_value.capture_available = True
        self.send("getState")
        self.send("control", {"action": "mic-start", "payload": {}})
        self.chat.current_history_uid = "other"
        self.assertFalse(self.send("control", {"action": "mic-submit", "payload": {}})["ok"])
        self.assertEqual(self.controller.run_pet_command.call_count, 1)

    def test_today_preserves_order_calendar_normal_and_provenance(self):
        result = self.send("getData")
        self.assertEqual([r["id"] for r in result["snapshot"]["today"]["items"]], ["first-normal", "second-watch", "third-urgent"])
        self.assertEqual(result["canonical"], core_today())
        self.assertEqual(result["snapshot"]["sourceStatus"][0]["canonical"]["connection"], "offline")

    def test_today_invalid_and_offline_remain_failures(self):
        self.controller.read_today.return_value = {"contract": "legacy"}
        self.assertFalse(self.send("getData")["ok"])
        self.controller.read_today.side_effect = TimeoutError("private path must not leak")
        result = self.send("getData"); self.assertFalse(result["ok"]); self.assertNotIn("private", json.dumps(result))

    def test_materialize_is_denied_even_with_renderer_confirmation(self):
        for body in ({"through": "2026-10-11"}, {"through": "2026-10-11", "confirmed": True}):
            result = self.send("schedule", {"action": "materialize", "payload": body})
            self.assertEqual(result["error"], "materialize_owned_by_core_scheduler")
        self.controller.materialize_schedule.assert_not_called(); self.confirm.assert_not_called()

    def test_original_refresh_sequence_never_writes(self):
        for action, payload in (("status", {}), ("materialize", {"through": "2026-10-12"}),
                ("view", {"start": "2026-10-10", "end": "2026-10-11", "timezone": "Asia/Taipei"}), ("notifications", {})):
            self.send("schedule", {"action": action, "payload": payload})
        self.controller.materialize_schedule.assert_not_called()
        self.controller.mutate_schedule.assert_not_called(); self.controller.schedule_notification_action.assert_not_called()

    def test_schedule_mutate_requires_native_confirmation_revision_and_key(self):
        body = {"action": "update", "id": "s", "expectedRevision": 1, "idempotencyKey": "synthetic-key", "item": {}, "confirmed": True}
        self.confirm.return_value = False
        self.assertTrue(self.send("schedule", {"action": "mutate", "payload": body})["cancelled"])
        self.controller.mutate_schedule.assert_not_called()
        self.confirm.return_value = True
        self.assertTrue(self.send("schedule", {"action": "mutate", "payload": body})["ok"])
        self.assertEqual(self.controller.mutate_schedule.call_args.args[0], body)
        del body["expectedRevision"]
        self.assertFalse(self.send("schedule", {"action": "mutate", "payload": body})["ok"])

    def test_notifications_claim_ack_and_unversioned_writes_denied(self):
        for action in ("claim", "authorize", "ack", "dismiss", "snooze", "preferences"):
            self.assertFalse(self.send("schedule", {"action": "notification-action", "payload": {"action": action, "confirmed": True}})["ok"])
        self.controller.schedule_notification_action.assert_not_called()

    def test_notification_versioned_write_native_cancel_and_owner_route(self):
        body = {"action": "dismiss", "id": "fixture", "expectedRevision": "a"*64,
                "idempotencyKey": "synthetic-notice", "confirmed": True}
        self.confirm.return_value = False
        self.assertTrue(self.send("schedule", {"action": "notification-action", "payload": body})["cancelled"])
        self.controller.schedule_notification_command.assert_not_called()
        self.confirm.return_value = True
        self.controller.schedule_notification_command.return_value = {"state": "dismissed"}
        self.assertTrue(self.send("schedule", {"action": "notification-action", "payload": body})["ok"])
        self.controller.schedule_notification_command.assert_called_once_with({
            "command": {"action": "dismiss", "id": "fixture", "confirmed": True},
            "expectedRevision": "a"*64, "idempotencyKey": "synthetic-notice"})
        self.assertNotIn("confirmed", self.confirm.call_args.args[1]["payload"])
        self.controller.schedule_notification_action.assert_not_called()

    def test_first_send_waits_for_new_history_without_native_confirm(self):
        self.chat.current_history_uid = ""
        self.send("sendText", {"text": "SYNTHETIC", "attachments": []})
        self.assertEqual(self.chat.calls, [("create",)])
        self.assertEqual(self.replies, [])
        self.chat.current_history_uid = "new"; self.chat.history_pending = False
        self.adapter.receive({"type": "new-history-created", "request_id": "ws-id", "client_uid": "client",
                              "conf_uid": "actor", "context_id": "context", "history_uid": "new"})
        self.assertTrue(self.replies[-1]["result"]["ok"])
        self.assertTrue(self.replies[-1]["result"]["createdHistory"])
        self.assertEqual(self.chat.calls[-1], ("send", "SYNTHETIC", []))
        self.confirm.assert_not_called()

    def test_mail_and_study_no_provider_or_legacy_fallback(self):
        self.assertFalse(self.send("refreshMail")["ok"])
        self.assertFalse(self.send("getMailMessage", {"messageId": "fixture"})["ok"])
        self.assertFalse(self.send("control", {"action": "study-jump", "payload": {}})["ok"])
        self.assertEqual(self.controller.mock_calls, [])

    def test_worker_never_reads_chat_qobject(self):
        gui_thread = threading.get_ident()
        original = self.chat.history_identity
        def guarded():
            self.assertEqual(threading.get_ident(), gui_thread)
            return original()
        self.chat.history_identity = guarded
        def worker(work, done):
            values = []
            thread = threading.Thread(target=lambda: values.append(work())); thread.start(); thread.join()
            done(values[0])
        self.worker = worker
        for method in ("getState", "getData", "getProfile", "getMemories", "getTools"):
            self.assertTrue(self.send(method)["ok"], method)

    def test_stale_worker_completion_cannot_publish_new_actor_data(self):
        tasks = []; self.worker = lambda w, d: tasks.append((w, d))
        self.send("getMemories"); value = tasks[0][0](); self.chat.conf_uid = "other"; tasks[0][1](value)
        self.assertFalse(self.replies[-1]["result"]["ok"])
        self.assertIsNone(self.adapter.memory_snapshot)


if __name__ == "__main__": unittest.main()
