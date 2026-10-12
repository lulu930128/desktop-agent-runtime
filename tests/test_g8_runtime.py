"""G8 isolated transport evidence: real loopback IO, synthetic provider and tray."""
import asyncio
import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"Open-LLM-VTuber"))
import launcher_qt
import websocket
from websockets.legacy.server import serve
from PySide6.QtWidgets import QApplication
from kuro_launcher.qt_chat_client import QtRuntimeChatClient
from kuro_launcher.qt_controller import QtLauncherController
from kuro_launcher.qt_notifications import QtScheduleDelivery
from kuro_launcher.core_runtime import CoreRuntime
from kuro_core.core_app import CoreApplication
from open_llm_vtuber.websocket_handler import WebSocketHandler

ROOT = Path(__file__).resolve().parents[1]


class G8RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def until(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.qt.processEvents()
            if predicate():
                return
            time.sleep(.005)
        self.fail("Synthetic transport timed out")

    def test_qt_core_http_claim_authorize_display_ack_and_no_duplicate(self):
        # API and DB are real; the tray is deliberately synthetic.
        with tempfile.TemporaryDirectory() as folder:
            token = "synthetic-g8-token-" * 3
            core = CoreApplication(Path(folder)/"work.sqlite3", port=0, token=token,
                                   instance_id="g8", default_timezone="UTC")
            core.api.start()
            self.addCleanup(core.stop)
            runtime = CoreRuntime(SimpleNamespace(core_enabled=True, core_port=core.port), lambda _: None)
            runtime.token = token
            controller = QtLauncherController.__new__(QtLauncherController)
            controller.core_runtime = runtime
            self.assertEqual(controller.read_today()["contract"], "kuro.core.today.v1")
            controller.schedule_notification_action({"action": "preferences", "confirmed": True,
                "preferences": {"timezone": "UTC", "quietEnabled": False,
                                "quietStart": "22:00", "quietEnd": "08:00"}})
            now = datetime.now(timezone.utc).replace(microsecond=0)
            item = {"title": "SYNTHETIC G8", "kind": "study", "timezone": "UTC",
                    "start": (now+timedelta(seconds=20)).isoformat(),
                    "end": (now+timedelta(minutes=5)).isoformat(),
                    "notification": {"enabled": True, "minutesBefore": 1, "channel": "desktop"}}
            controller.mutate_schedule({"action": "create", "confirmed": True,
                "idempotencyKey": "g8-notification", "item": item})
            tray = Mock()
            actions = []
            original = controller.schedule_notification_action
            def request(payload):
                actions.append(payload["action"])
                return original(payload)
            controller.schedule_notification_action = request
            delivery = QtScheduleDelivery(controller, tray, lambda _: None)
            try:
                with patch.object(delivery, "available", return_value=True):
                    delivery.poll()
                    self.until(lambda: not delivery.busy)
                    self.assertEqual(actions, ["claim", "authorize", "ack"])
                    tray.showMessage.assert_called_once()
                    delivery.poll()
                    self.until(lambda: not delivery.busy)
                    self.assertEqual(actions, ["claim", "authorize", "ack", "claim"])
                    tray.showMessage.assert_called_once()
            finally:
                delivery.stop()
                delivery.deleteLater()
                core.stop()

    def test_real_ws_qt_without_pet_then_pet_role_fencing_and_ack(self):
        context = SimpleNamespace(live2d_model=SimpleNamespace(model_info={}),
            character_config=SimpleNamespace(conf_uid="synthetic", conf_name="synthetic"))
        handler = WebSocketHandler(context)
        handler._init_service_context = AsyncMock(return_value=context)
        handler._send_initial_messages = AsyncMock()
        loop = asyncio.new_event_loop()
        ready = threading.Event()
        ended = threading.Event()
        port = []
        errors = []
        turns = []

        class Socket:
            def __init__(self, ws):
                self.ws = ws
            async def send_text(self, text):
                await self.ws.send(text)
            async def send_json(self, value):
                await self.ws.send(json.dumps(value))

        async def connection(ws, path):
            role = parse_qs(urlsplit(path).query).get("client_role", ["frontend"])[0]
            uid = "pet" if role == "pet-presentation" else "qt"
            adapter = Socket(ws)
            try:
                await handler.handle_new_connection(adapter, uid, client_role=role)
                async for raw in ws:
                    await handler._route_message(adapter, uid, json.loads(raw))
            except Exception as exc:
                if type(exc).__name__ not in {"ConnectionClosedOK", "ConnectionClosedError"}:
                    errors.append(type(exc).__name__)
            finally:
                # No real service teardown or history IO in this fixture.
                for output in handler.primary_outputs.values():
                    output.disconnect(uid)
                handler.client_connections.pop(uid, None)
                handler.client_roles.pop(uid, None)
                handler.client_contexts.pop(uid, None)

        async def run_server():
            async with serve(connection, "127.0.0.1", 0) as server:
                port.append(server.sockets[0].getsockname()[1])
                ready.set()
                while not ended.is_set():
                    await asyncio.sleep(.01)

        def runner():
            asyncio.set_event_loop(loop)
            loop.run_until_complete(run_server())
            loop.close()
        thread = threading.Thread(target=runner, daemon=True)
        async def turn(**kwargs):
            turns.append(kwargs["client_uid"] if "client_uid" in kwargs else "qt")
            await kwargs["websocket_send"](json.dumps({"type": "full-text", "text": "SYNTHETIC reply"}))
            await kwargs["websocket_send"](json.dumps({"type": "backend-synth-complete"}))
        client = QtRuntimeChatClient()
        pet = None
        with patch("open_llm_vtuber.conversations.conversation_handler.process_single_conversation", side_effect=turn):
            thread.start()
            self.assertTrue(ready.wait(3))
            url = f"ws://127.0.0.1:{port[0]}/client-ws"
            try:
                client.connect_to(url+"?client_role=qt-primary")
                self.until(lambda: client.connected and "qt" in handler.client_contexts)
                self.assertTrue(client.send_text("SYNTHETIC no Pet"))
                self.until(lambda: len(turns) == 1 and not any(not t.done() for t in handler.current_conversation_tasks.values()))
                self.assertEqual(set(handler.client_contexts), {"qt"})
                pet = websocket.create_connection(url+"?client_role=pet-presentation", timeout=3,
                                                  http_proxy_host=None)
                self.assertEqual(json.loads(pet.recv())["type"], "set-model-and-conf")
                for kind in ["text-input", "mic-audio-data", "mic-audio-end", "interrupt-signal",
                             "create-new-history", "fetch-history-list", "switch-config"]:
                    pet.send(json.dumps({"type": kind, "text": "SYNTHETIC forbidden"}))
                pet.send(json.dumps({"type": "heartbeat"}))
                while json.loads(pet.recv()).get("type") != "heartbeat-ack":
                    pass
                self.assertEqual(len(turns), 1)
                self.assertEqual(set(handler.client_contexts), {"qt"})
                self.assertTrue(client.send_text("SYNTHETIC with Pet"))
                while True:
                    frame = json.loads(pet.recv())
                    if frame.get("type") == "backend-synth-complete":
                        break
                output = handler.primary_outputs["qt"]
                self.assertFalse(output.completed.is_set())
                pet.send(json.dumps({"type": "frontend-playback-complete", "request_id": "wrong"}))
                pet.send(json.dumps({"type": "heartbeat"}))
                while json.loads(pet.recv()).get("type") != "heartbeat-ack":
                    pass
                self.assertFalse(output.completed.is_set())
                pet.send(json.dumps({"type": "frontend-playback-complete", "request_id": frame["request_id"]}))
                self.until(output.completed.is_set)
                self.assertEqual(len(turns), 2)
                self.assertEqual(errors, [])
            finally:
                if pet:
                    pet.close()
                client.disconnect()
                if client._thread:
                    client._thread.join(3)
                ended.set()
                thread.join(5)
                self.assertFalse(thread.is_alive())

    def test_removed_ui_has_no_external_production_consumer(self):
        manifest = json.loads((ROOT/"docs/agent-runs/qt-ui-convergence-20261007/G7DeletionManifest.json").read_text())
        excluded = {entry["path"] for entry in manifest["files"]}
        forbidden = ["work_panel", "work-panel", "WorkPanelControlServer", "/briefing",
            "briefing-store", "today-classifier", "study-briefing", "mail-briefing-service",
            "legacy_briefing_adapter", "23568", "mail_briefing_poller"]
        matches = []
        for folder in ["kuro_launcher", "kuro_core", "pet-electron/src", "pet-electron/renderer/src",
                       "Open-LLM-VTuber/local_mcp", "Open-LLM-VTuber/src"]:
            for path in (ROOT/folder).rglob("*"):
                if path.suffix not in {".py", ".js", ".ts", ".html"}:
                    continue
                relative = path.relative_to(ROOT).as_posix()
                if relative in excluded:
                    continue
                source = path.read_text(encoding="utf-8-sig")
                if relative in {"kuro_launcher/qt_web_host.py", "kuro_launcher/qt_web_release.py"}:
                    # W2 preserves the archived HTML filename in an opt-in Qt
                    # custom scheme. Exempt only these two exact path literals;
                    # every other legacy consumer/port token is still forbidden.
                    self.assertEqual(source.count('"/work-panel.html"'), 2 if relative.endswith("qt_web_host.py") else 1)
                    if relative.endswith("qt_web_host.py"):
                        self.assertIn('ORIGIN = "kuro-work://app"', source)
                    source = source.replace('"/work-panel.html"', '"/candidate-entry.html"')
                    from kuro_launcher.qt_web_release import RELEASE_PIN
                    self.assertIsNotNone(RELEASE_PIN)
                    self.assertEqual(RELEASE_PIN.fingerprint,
                        'dc7ad8b776312ab6c40102591d2bbe822707af44c776032cb041ae2bbfa2402e')
                matches.extend((relative, term) for term in forbidden if term in source)
        self.assertEqual(matches, [])
        self.assertFalse(hasattr(QtLauncherController, "ensure_work_panel"))
        self.assertFalse(hasattr(QtLauncherController, "send_pet_text"))
