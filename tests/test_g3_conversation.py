"""Synthetic G3 boundary tests; no service, private history, model or voice IO."""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Open-LLM-VTuber" / "src"))
sys.path.insert(0, str(ROOT / "Open-LLM-VTuber"))

from open_llm_vtuber.websocket_handler import WebSocketHandler, PrimaryConversationOutput
from open_llm_vtuber.conversations.conversation_utils import finalize_conversation_turn
from kuro_launcher.qt_chat_client import QtRuntimeChatClient
from kuro_launcher.qt_app import KuroQtLauncherWindow


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.context = SimpleNamespace(
            live2d_model=SimpleNamespace(model_info={}),
            character_config=SimpleNamespace(conf_name="fixture", conf_uid="fixture"),
        )
        self.handler = WebSocketHandler(self.context)
        self.qt = SimpleNamespace(send_text=AsyncMock())
        self.pet = SimpleNamespace(send_text=AsyncMock())
        self.handler.client_connections = {"qt": self.qt, "pet": self.pet}
        self.handler.client_roles = {"qt": "qt-primary", "pet": "pet-presentation"}
        self.handler.client_contexts = {"qt": self.context}

    async def test_roles_and_hot_switch(self):
        self.assertEqual(self.handler._normalize_client_role(" Qt-Primary "), "qt-primary")
        self.assertEqual(self.handler._normalize_client_role("pet-presentation"), "pet-presentation")
        self.assertEqual(self.handler._controllable_client_uids(["qt", "pet"]), ["qt"])
        self.assertEqual(self.handler._resolve_launcher_target()[0], "qt")
        self.assertIsNotNone(self.handler._resolve_launcher_target("pet")[2])

    async def test_pet_connection_has_no_context_or_group(self):
        self.handler._init_service_context = AsyncMock()
        await self.handler.handle_new_connection(self.pet, "pet2", client_role="pet-presentation")
        self.handler._init_service_context.assert_not_called()
        self.assertNotIn("pet2", self.handler.client_contexts)
        self.assertNotIn("pet2", self.handler.chat_group_manager.client_group_map)

    async def test_second_controller_rejected(self):
        for role in ("frontend", "qt-primary"):
            with self.assertRaises(ValueError):
                await self.handler.handle_new_connection(self.pet, "other", client_role=role)

    async def test_pet_inbound_fail_closed(self):
        for kind in ("text-input", "interrupt-signal", "fetch-history-list", "fetch-and-set-history",
                     "create-new-history", "delete-history", "switch-config", "fetch-configs",
                     "ai-speak-signal", "mic-audio-data", "mic-audio-end", "add-client-to-group", "unknown"):
            with self.subTest(kind=kind):
                callback = AsyncMock()
                self.handler._message_handlers[kind] = callback
                await self.handler._route_message(self.pet, "pet", {"type": kind})
                callback.assert_not_called()
        self.assertFalse(self.handler.current_conversation_tasks)

    async def test_primary_fanout_is_allowlisted(self):
        output = PrimaryConversationOutput(self.qt.send_text, lambda: {"pet": self.pet})
        for kind in ("history-list", "history-data", "config-files", "admin", "error", "tool-call"):
            await output(json.dumps({"type": kind, "private": "synthetic"}))
        await output(json.dumps({"type": "control", "text": "start-mic"}))
        self.pet.send_text.assert_not_called()
        payload = {"type": "audio", "audio": "fixture", "display_text": {"text": "hello"},
                   "actions": {"expressions": [1]}, "private": "not-mirrored"}
        await output(json.dumps(payload))
        self.assertEqual(json.loads(self.qt.send_text.call_args.args[0]), payload)
        mirrored = json.loads(self.pet.send_text.call_args.args[0])
        self.assertNotIn("private", mirrored)
        self.assertEqual(mirrored["actions"], payload["actions"])

    async def test_ack_correlated_to_primary_and_ignores_qt(self):
        output = PrimaryConversationOutput(self.qt.send_text, lambda: {"pet": self.pet})
        self.handler.primary_outputs["qt"] = output
        await output(json.dumps({"type": "backend-synth-complete"}))
        await self.handler._route_message(self.qt, "qt", {"type": "frontend-playback-complete", "request_id": output.request_id})
        await self.handler._route_message(self.pet, "pet", {"type": "frontend-playback-complete", "request_id": "old-turn"})
        self.assertFalse(output.completed.is_set())
        await self.handler._route_message(self.pet, "pet", {"type": "frontend-playback-complete", "request_id": output.request_id})
        await asyncio.wait_for(output.wait_for_playback(), .2)

    async def test_no_pet_finalizes_without_legacy_wait(self):
        output = PrimaryConversationOutput(self.qt.send_text, lambda: {})
        manager = SimpleNamespace(task_list=[asyncio.create_task(asyncio.sleep(0))],
                                  _payload_queue=asyncio.Queue(), audio_output_count=1)
        with patch("open_llm_vtuber.conversations.conversation_utils.message_handler.wait_for_response", new_callable=AsyncMock) as wait:
            await asyncio.wait_for(finalize_conversation_turn(manager, output, "qt"), .3)
            wait.assert_not_called()
        self.assertEqual(json.loads(self.qt.send_text.call_args.args[0])["text"], "conversation-chain-end")

    async def test_disconnect_and_immediate_ack_complete_wait(self):
        output = PrimaryConversationOutput(self.qt.send_text, lambda: {"pet": self.pet})
        self.handler.primary_outputs["qt"] = output
        await output(json.dumps({"type": "backend-synth-complete"}))
        await self.handler.handle_disconnect("pet")
        await asyncio.wait_for(output.wait_for_playback(), .2)
        self.assertIn("qt", self.handler.client_contexts)

    async def test_pet_send_failure_does_not_fail_primary(self):
        self.pet.send_text.side_effect = ConnectionError()
        output = PrimaryConversationOutput(self.qt.send_text, lambda: {"pet": self.pet})
        await output(json.dumps({"type": "backend-synth-complete"}))
        await asyncio.wait_for(output.wait_for_playback(), .2)

    async def test_ack_received_during_marker_send_is_not_lost(self):
        output = PrimaryConversationOutput(self.qt.send_text, lambda: {"pet": self.pet})
        async def immediate_ack(raw):
            output.acknowledge("pet", json.loads(raw).get("request_id"))
        self.pet.send_text.side_effect = immediate_ack
        await output(json.dumps({"type": "backend-synth-complete"}))
        await asyncio.wait_for(output.wait_for_playback(), .2)

    async def test_all_presentations_finish_before_primary_wait_completes(self):
        other = SimpleNamespace(send_text=AsyncMock())
        output = PrimaryConversationOutput(self.qt.send_text, lambda: {"pet": self.pet, "other": other})
        await output(json.dumps({"type": "backend-synth-complete"}))
        output.acknowledge("pet", output.request_id)
        self.assertFalse(output.completed.is_set())
        output.acknowledge("other", output.request_id)
        await asyncio.wait_for(output.wait_for_playback(), .2)

    async def test_primary_cannot_join_group(self):
        callback = AsyncMock()
        self.handler._message_handlers["add-client-to-group"] = callback
        await self.handler._route_message(self.qt, "qt", {"type": "add-client-to-group", "invitee_uid": "pet"})
        callback.assert_not_called()

    async def test_concurrent_primary_admission_is_exclusive(self):
        self.handler.client_connections.clear()
        self.handler.client_roles.clear()
        entered, release = asyncio.Event(), asyncio.Event()
        async def init(*args):
            entered.set()
            await release.wait()
            return self.context
        self.handler._init_service_context = init
        self.handler._send_initial_messages = AsyncMock()
        first = asyncio.create_task(self.handler.handle_new_connection(self.qt, "one", client_role="qt-primary"))
        await entered.wait()
        try:
            with self.assertRaises(ValueError):
                await self.handler.handle_new_connection(self.pet, "two", client_role="qt-primary")
        finally:
            release.set()
            await first
        self.assertFalse(self.handler._connecting_roles)

    async def test_busy_primary_rejects_duplicate_turn(self):
        task = asyncio.create_task(asyncio.sleep(60))
        self.handler.current_conversation_tasks["qt"] = task
        try:
            with patch("open_llm_vtuber.websocket_handler.handle_conversation_trigger", new_callable=AsyncMock) as trigger:
                await self.handler._route_message(self.qt, "qt", {"type": "text-input", "text": "duplicate"})
                trigger.assert_not_called()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_text_trigger_one_turn_with_or_without_pet(self):
        for pet_present in (False, True):
            self.handler.current_conversation_tasks.clear()
            self.handler.client_connections = {"qt": self.qt, **({"pet": self.pet} if pet_present else {})}
            async def synthetic_turn(**kwargs):
                await kwargs["websocket_send"](json.dumps({"type": "full-text", "text": "fixture response"}))
            with patch("open_llm_vtuber.conversations.conversation_handler.process_single_conversation", side_effect=synthetic_turn) as single:
                await self.handler._route_message(self.qt, "qt", {"type": "text-input", "text": "fixture"})
                await self.handler.current_conversation_tasks["qt"]
                single.assert_called_once()
                self.assertIs(single.call_args.kwargs["context"], self.context)
            self.assertEqual(list(self.handler.client_contexts), ["qt"])


class QtTests(unittest.TestCase):
    def test_no_fake_playback_ack_or_early_idle(self):
        client = QtRuntimeChatClient()
        client._send_json = Mock()
        states = []
        client.state_changed.connect(lambda *args: states.append(args))
        client._handle_payload({"type": "backend-synth-complete"})
        client._send_json.assert_not_called()
        self.assertEqual(states, [])

    def test_attachment_wire_payload(self):
        client = QtRuntimeChatClient()
        client._send_json = Mock(return_value=True)
        self.assertTrue(client.send_text("fixture", [{"kind": "image", "data": "data:image/png;base64,AA=="},
                                                    {"kind": "file", "data": "data:text/plain;base64,AA==", "name": "fixture.txt"}]))
        sent = client._send_json.call_args.args[0]
        self.assertEqual(sent["type"], "text-input")
        self.assertEqual(len(sent["images"]), 1)
        self.assertEqual(len(sent["files"]), 1)





    def test_primary_url(self):
        window = SimpleNamespace(cfg=SimpleNamespace(llm_host="localhost", llm_port=12345))
        self.assertTrue(KuroQtLauncherWindow._runtime_chat_url(window).endswith("client_role=qt-primary"))



    def test_history_listing_does_not_switch_primary(self):
        client = QtRuntimeChatClient()
        client.current_history_uid = "selected"
        client._handle_payload({"type": "history-list", "histories": [{"uid": "other"}]})
        self.assertEqual(client.current_history_uid, "selected")

    def test_history_response_updates_client_before_window_receives_it(self):
        client = QtRuntimeChatClient()
        client._connected = True
        client._ws_app = Mock()
        identity = {"client_uid": "fixture", "conf_uid": "synthetic", "context_id": "fixture-context"}
        client._handle_payload({"type": "set-model-and-conf", **identity,
                                "history_protocol": "kuro.conversation.history.v1"})
        observed = []
        client.message_received.connect(lambda payload: observed.append(client.current_history_uid))
        self.assertTrue(client.create_history())
        client._on_message(client._ws_app, json.dumps({"type": "new-history-created", "history_uid": "new",
                           **identity, "request_id": client._history_pending["request_id"]}))
        self.assertEqual(observed, ["new"])




if __name__ == "__main__":
    unittest.main()
