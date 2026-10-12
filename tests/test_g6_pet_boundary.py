"""G6 synthetic boundary checks. No devices, provider, private state or desktop."""
import base64
import json
import os
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import launcher_qt
from kuro_launcher.qt_chat_client import QtRuntimeChatClient
from kuro_launcher.qt_controller import QtLauncherController
from kuro_launcher.qt_app import KuroQtLauncherWindow


class CaptureTests(unittest.TestCase):
    def client(self):
        client = QtRuntimeChatClient()
        client._connected = True
        client._ws_app = Mock()
        return client

    def capture(self, pcm=b"\x00\x00\xff\x7f\x00\x80"):
        return dict(format="pcm16le", sampleRate=16000,
                    data=base64.b64encode(pcm).decode("ascii"))

    def test_qt_alone_sends_audio_chunks_then_one_trigger(self):
        client = self.client()
        self.assertTrue(client.send_capture(self.capture(), [
            dict(kind="image", source="camera", data="data:image/png;base64,AA==", mime_type="image/png")]))
        sent = [json.loads(c.args[0]) for c in client._ws_app.send.call_args_list]
        self.assertEqual([p["type"] for p in sent], ["mic-audio-data", "mic-audio-end"])
        self.assertEqual(sent[0]["audio"], [0, 32767 / 32768, -1])
        self.assertEqual(sent[1]["images"][0]["source"], "camera")

    def test_bad_or_oversized_capture_never_sends(self):
        client = self.client()
        for capture in (self.capture(b"x"), self.capture(b""), {**self.capture(), "sampleRate":8000},
                        {**self.capture(), "data":"?"}, {**self.capture(), "data":"A" * 2560001}):
            self.assertFalse(client.send_capture(capture, []))
        client._ws_app.send.assert_not_called()

    def test_offline_capture_does_not_trigger_or_fallback(self):
        client = self.client()
        client._connected = False
        self.assertFalse(client.send_capture(self.capture(), []))
        client._ws_app.send.assert_not_called()

    def test_uncertain_audio_send_closes_without_replay(self):
        client = self.client()
        client._ws_app.send.side_effect = OSError("synthetic")
        self.assertFalse(client.send_capture(self.capture(), []))
        client._ws_app.send.assert_called_once()
        client._ws_app.close.assert_called_once()

    def test_camera_result_for_old_history_is_discarded(self):
        window = SimpleNamespace(pending_chat_submit=dict(capture_pending=True, history_uid="old"),
            chat_client=Mock(current_history_uid="new"), _set_chat_status=Mock(),
            _update_chat_send_button=Mock(), _queue_chat_submit=Mock())
        KuroQtLauncherWindow._on_task_finished(window, "chat-capture",
            {"result":{"ok":True,"images":[]}})
        window._queue_chat_submit.assert_not_called()
        self.assertIsNone(window.pending_chat_submit)

    def test_mic_result_for_old_history_is_discarded(self):
        client = Mock()
        client.history_identity.return_value = ("qt", "role", "context", "new")
        window = SimpleNamespace(_capture_identity=("qt", "role", "context", "old"), pending_chat_submit=None,
            chat_client=client, _set_chat_status=Mock(), _queue_chat_submit=Mock(),
            perception_status=Mock(), refresh_status=Mock())
        KuroQtLauncherWindow._on_task_finished(window, "microphone:submit",
            {"result":{"ok":True,"capture":self.capture()}})
        window._queue_chat_submit.assert_not_called()

    def test_mic_result_is_submitted_via_qt_with_existing_history_binding(self):
        identity = ("qt", "role", "context", "same")
        client = Mock()
        client.history_identity.return_value = identity
        window = SimpleNamespace(_capture_identity=identity, pending_chat_submit=None,
            chat_client=client, _queue_chat_submit=Mock(), _chat_response_active=Mock(return_value=False),
            perception_status=Mock(), refresh_status=Mock())
        capture = self.capture()
        KuroQtLauncherWindow._on_task_finished(window, "microphone:submit",
            {"result":{"ok":True,"capture":capture}})
        window._queue_chat_submit.assert_called_once_with("[語音輸入]", [], capture)


class OwnershipTests(unittest.TestCase):
    def test_malformed_or_failed_pet_commands_are_not_success(self):
        c = QtLauncherController.__new__(QtLauncherController)
        c.cfg = SimpleNamespace(pet_control_url="http://127.0.0.1:1")
        c.log = Mock()
        for value in ({}, None, {"ok": False, "result": {"error": "renderer-unavailable"}}):
            with patch("kuro_launcher.qt_controller.http_post_json", return_value=value):
                with self.assertRaises(RuntimeError):
                    c.run_pet_command("stop-playback")
        c.log.assert_not_called()

    def test_failed_backend_configuration_does_not_report_applied(self):
        c = QtLauncherController.__new__(QtLauncherController)
        c.cfg = SimpleNamespace(pet_control_url="http://127.0.0.1:1")
        c.log = Mock()
        with patch("kuro_launcher.qt_controller.http_post_json", return_value={"ok": False}):
            with self.assertRaises(RuntimeError):
                c.apply_pet_backend_config(base_url="http://127.0.0.1:1", ws_url="ws://127.0.0.1:1")
        c.log.assert_not_called()

    def test_launcher_services_start_without_pet(self):
        c = QtLauncherController.__new__(QtLauncherController)
        c.core_runtime, c.mail_poller_runtime, c.log = Mock(), Mock(), Mock()
        c.core_runtime.start.side_effect = RuntimeError("fixture")
        c.launch_pet_electron = Mock()
        c.start_desktop_services()
        c.core_runtime.start.assert_called_once()
        c.mail_poller_runtime.start.assert_called_once()
        c.launch_pet_electron.assert_not_called()

    def test_existing_pet_receives_profile_presentation_from_launcher(self):
        import threading
        c = QtLauncherController.__new__(QtLauncherController)
        c._pet_lifecycle_lock = threading.RLock()
        c._ensure_pet_shell_ready_locked = Mock(return_value={"pid":7,"instanceId":"same"})
        c.presentation_state = Mock(return_value={"presentation":{"confUid":"new"}})
        c.run_pet_command, c.log = Mock(), Mock()
        c.launch_pet_electron()
        c.run_pet_command.assert_called_once_with("set-presentation",
            {"presentation":{"confUid":"new"}, "expectedInstanceId":"same"})


if __name__ == "__main__":
    unittest.main()
