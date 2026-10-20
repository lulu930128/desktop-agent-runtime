"""Web owner + real ephemeral WS + canonical history in a temp cwd."""
import asyncio
from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from websockets.legacy.server import serve
import launcher_qt  # runtime import bootstrap
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication
from kuro_launcher.qt_chat_client import QtRuntimeChatClient
from kuro_launcher.qt_web_protocol import CONTRACT
from test_qt_web_existing_window import actual_port
from web_candidate_fixtures import controller_fixture
from open_llm_vtuber.websocket_handler import WebSocketHandler
from open_llm_vtuber import chat_history_manager as histories
from open_llm_vtuber.chat_event_manager import store_history_event, read_history_events

APP = QApplication.instance() or QApplication([])


class HistoryTransportTests(unittest.TestCase):
    def until(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            APP.processEvents()
            if predicate():
                return
            time.sleep(.005)
        self.fail("Isolated History transport timed out")

    def test_real_web_owner_crud_and_tool_timeline_through_ws(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory, ExitStack() as cleanup:
            os.chdir(directory)
            cleanup.callback(os.chdir, previous)
            conf = "synthetic-role"
            uid = histories.create_new_history(conf)
            histories.store_message(conf, uid, "human", "SYNTHETIC question\n  code")
            store_history_event(conf_uid=conf, history_uid=uid, event_type="tool_call",
                                title="SYNTHETIC tool", status="completed", summary="fixture evidence")
            context = SimpleNamespace(character_config=SimpleNamespace(conf_uid=conf, conf_name="SYNTHETIC"),
                                      history_uid="", agent_engine=Mock())
            handler = WebSocketHandler(context)
            handler._init_service_context = AsyncMock(return_value=context)
            async def initial(ws, client_uid, _context):
                await ws.send_text(json.dumps({"type": "set-model-and-conf", "client_uid": client_uid,
                    "conf_name": "SYNTHETIC", **handler._history_identity(_context)}))
            handler._send_initial_messages = initial
            ready, ended = threading.Event(), threading.Event()
            ports, errors, received = [], [], []

            class Socket:
                def __init__(self, ws):
                    self.ws = ws
                async def send_text(self, raw):
                    await self.ws.send(raw)

            async def connection(ws, path):
                self.assertIn("client_role=qt-primary", path)
                adapter = Socket(ws)
                try:
                    await handler.handle_new_connection(adapter, "qt-temp", client_role="qt-primary")
                    async for raw in ws:
                        payload = json.loads(raw)
                        received.append(payload)
                        await handler._route_message(adapter, "qt-temp", payload)
                except Exception as exc:
                    if type(exc).__name__ not in {"ConnectionClosedOK", "ConnectionClosedError"}:
                        errors.append(type(exc).__name__)

            async def server():
                async with serve(connection, "127.0.0.1", 0) as instance:
                    ports.append(instance.sockets[0].getsockname()[1])
                    ready.set()
                    while not ended.is_set():
                        await asyncio.sleep(.01)

            thread = threading.Thread(target=lambda: asyncio.run(server()), daemon=True)
            thread.start()
            def stop_server():
                ended.set()
                thread.join(5)
                self.assertFalse(thread.is_alive())
            cleanup.callback(stop_server)
            self.assertTrue(ready.wait(3))
            owner = QObject()
            owner.controller = controller_fixture()
            owner.chat_client = client = QtRuntimeChatClient(owner)
            owner.isVisible = lambda: True
            port = actual_port(owner, [])
            cleanup.callback(lambda: port.pool.shutdown(wait=True, cancel_futures=True))
            cleanup.callback(port.shutdown)
            replies = []
            port.wire.response.connect(lambda raw: replies.append(json.loads(raw)))
            port.broker.confirm = Mock(return_value=True)
            sequence = 0
            def call(method, payload=None):
                nonlocal sequence
                sequence += 1
                request_id = f"r4-web-{sequence}"
                port.wire.submit(json.dumps(dict(contract=CONTRACT, id=request_id,
                    expected=port.adapter.identity(), method=method, payload=payload or {})))
                self.until(lambda: any(r["id"] == request_id for r in replies))
                return next(r["result"] for r in replies if r["id"] == request_id)
            def disconnect():
                client.disconnect()
                if client._thread:
                    client._thread.join(3)
                    self.assertFalse(client._thread.is_alive())
            cleanup.callback(disconnect)
            client.connect_to(f"ws://127.0.0.1:{ports[0]}/client-ws?client_role=qt-primary")
            self.until(lambda: client.history_ready)
            listing = call("getHistories")
            self.assertTrue(listing["ok"], listing)
            self.assertEqual(len(listing["histories"]), 1)
            self.assertIn("SYNTHETIC question", listing["histories"][0]["last_preview"])
            selected = call("selectHistory", {"historyUid": uid})
            self.assertTrue(selected["ok"], selected)
            transcript = "\n".join(row["content"] for row in selected["messages"])
            self.assertIn("SYNTHETIC tool", transcript)
            self.assertEqual(context.history_uid, uid)
            self.assertEqual(client.current_history_uid, uid)
            self.assertIn("  code", transcript)
            calls = context.agent_engine.set_memory_from_history.call_count
            self.assertTrue(call("selectHistory", {"historyUid": uid})["ok"])
            self.assertEqual(context.agent_engine.set_memory_from_history.call_count, calls)

            self.assertTrue(call("createHistory")["ok"])
            new_uid = client.current_history_uid
            self.assertEqual(len(histories.get_history_list(conf, strict=True)), 2)
            self.assertEqual(len(call("getHistories")["histories"]), 2)
            port.broker.confirm.return_value = False
            self.assertTrue(call("deleteHistory", {"historyUid": new_uid})["cancelled"])
            self.assertTrue(Path(histories._get_safe_history_path(conf, new_uid)).exists())
            port.broker.confirm.return_value = True
            self.assertTrue(call("deleteHistory", {"historyUid": new_uid})["ok"])
            self.until(lambda: not Path(histories._get_safe_history_path(conf, new_uid)).exists()
                       and not client.history_pending)
            self.assertEqual(client.current_history_uid, "")
            self.assertEqual(context.history_uid, None)
            # One malformed file must be an error, never a false empty success.
            Path(histories._get_safe_history_path(conf, "broken")).write_text("{", encoding="utf-8")
            failed = call("getHistories")
            self.assertFalse(failed["ok"])
            self.assertEqual(failed["error"], "history_owner_rejected")
            self.assertTrue(any(p["type"] == "create-new-history" and p.get("context_id") for p in received))
            self.assertEqual(sum(p["type"] == "delete-history" for p in received), 1)
            self.assertEqual(errors, [])
            owner.controller.read_history_records.assert_not_called()
            owner.controller.read_history_timeline.assert_not_called()

    def test_strict_owner_read_errors_and_event_sidecar_delete(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            os.chdir(directory)
            try:
                uid = histories.create_new_history("fixture")
                path = Path(histories._get_safe_history_path("fixture", uid))
                events = path.with_suffix(".events.jsonl")
                events.write_text("{", encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_history_events("fixture", uid, strict=True)
                self.assertEqual(read_history_events("fixture", uid), [])
                path.write_text("{", encoding="utf-8")
                with self.assertRaises(ValueError):
                    histories.get_history("fixture", uid, strict=True)
                self.assertEqual(histories.get_history("fixture", uid), [])
                self.assertTrue(histories.delete_history("fixture", uid))
                self.assertFalse(path.exists())
                self.assertFalse(events.exists())
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
