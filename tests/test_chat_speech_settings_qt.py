"""Actual Qt owner Port, temporary Launcher YAML; no window/service/runtime."""
import json
from pathlib import Path
import tempfile
import time
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Open-LLM-VTuber/src"), str(ROOT / "Open-LLM-VTuber")]

from PySide6.QtCore import QCoreApplication, QObject
from kuro_launcher.config import CHAT_SPEECH_DEFAULTS
from kuro_launcher.qt_controller import QtLauncherController
from kuro_launcher.qt_chat_client import QtRuntimeChatClient
from kuro_launcher.qt_web_protocol import CONTRACT
from test_qt_web_existing_window import actual_port

ROOT = Path(__file__).resolve().parents[1]


class ChatSpeechPortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".tmp"); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "launcher.yaml"; self.path.write_text("fixture: true\n", encoding="utf-8")
        controller = QtLauncherController.__new__(QtLauncherController)
        controller.cfg = SimpleNamespace(config_path=self.path)
        controller._core_request = Mock(side_effect=AssertionError("Core settings must remain independent"))
        self.owner = QObject(); self.owner.controller = controller
        self.owner.chat_client = QtRuntimeChatClient(self.owner)
        self.port = actual_port(self.owner, []); self.addCleanup(self.port.shutdown)
        self.port.broker.confirm = Mock(side_effect=AssertionError("Ordinary speech preferences need no lifecycle approval"))
        self.replies = []
        self.port.wire.response.connect(lambda raw: self.replies.append(json.loads(raw)))
        self.sequence = 0

    def call(self, method, payload=None):
        self.sequence += 1; before = len(self.replies)
        self.port.wire.submit(json.dumps(dict(contract=CONTRACT, id=f"speech-{self.sequence}", method=method,
            payload=payload or {}, expected=self.port.adapter.identity())))
        end = time.monotonic() + 4
        while len(self.replies) == before and time.monotonic() < end:
            self.app.processEvents(); time.sleep(.005)
        self.assertEqual(len(self.replies), before + 1)
        return self.replies[-1]["result"]

    def test_owner_write_readback_and_new_controller_reopen(self):
        first = self.call("getChatSpeechSettings")
        self.assertTrue(first["ok"]); self.assertEqual(first["settings"], CHAT_SPEECH_DEFAULTS)
        desired = dict(CHAT_SPEECH_DEFAULTS, locale="en-US", policy="detailed")
        written = self.call("updateChatSpeechSettings", dict(settings=desired, expectedRevision=first["revision"]))
        self.assertTrue(written["ok"]); self.assertTrue(written["persisted"])
        self.assertEqual(self.call("getChatSpeechSettings"), written)
        fresh = QtLauncherController.__new__(QtLauncherController); fresh.cfg = SimpleNamespace(config_path=self.path)
        self.assertEqual(fresh.read_chat_speech_settings()["settings"], desired)
        self.owner.controller._core_request.assert_not_called()

    def test_invalid_renderer_fields_and_locale_cannot_write(self):
        first = self.call("getChatSpeechSettings"); before = self.path.read_bytes()
        for desired, extra in [(dict(CHAT_SPEECH_DEFAULTS, locale="fr-FR"), {}),
                               (dict(CHAT_SPEECH_DEFAULTS, policy=[]), {}),
                               (CHAT_SPEECH_DEFAULTS, {"confirmed": True})]:
            result = self.call("updateChatSpeechSettings", dict(settings=desired, expectedRevision=first["revision"], **extra))
            self.assertFalse(result["ok"]); self.assertEqual(self.path.read_bytes(), before)

    def test_failed_write_is_unknown_and_never_retried(self):
        first = self.call("getChatSpeechSettings")
        with patch.object(self.owner.controller, "update_chat_speech_settings", side_effect=OSError("fixture")) as update:
            result = self.call("updateChatSpeechSettings", dict(settings=CHAT_SPEECH_DEFAULTS, expectedRevision=first["revision"]))
        self.assertFalse(result["ok"]); self.assertTrue(result["unknownResult"]); self.assertEqual(update.call_count, 1)

    def test_versioned_display_deltas_preserve_repeat_code_and_whitespace(self):
        chat = self.owner.chat_client
        parts = ["未驗證。\n", "```python\n", "x = {\"a\": 1}\n", "```\n", "重複文字", "重複文字", "\n價格 100.5，停損 95。"]
        for part in parts:
            chat._handle_payload({"type":"audio", "display_text":{"text":part},
                                  "display_contract":"kuro.speech-lanes.v1", "display_append":True})
        self.assertEqual(chat._assistant_text, "".join(parts))


if __name__ == "__main__": unittest.main()
