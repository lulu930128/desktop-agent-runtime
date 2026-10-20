"""Source/real Qt event-queue regression; explicitly not native WebEngine proof."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QObject, QCoreApplication, QTimer, QThread, Qt, Signal, Slot
from kuro_launcher.qt_chat_client import QtRuntimeChatClient
from kuro_launcher.qt_web_adapter import QtOwnerAdapter
from kuro_launcher.qt_web_protocol import CONTRACT, RequestBroker, error
from kuro_launcher.qt_web_release import OwnerBundlePin, VerifiedOwnerBundle, prepare_owner_presentation
from web_candidate_fixtures import ChatFixture, controller_fixture

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "devtools/original-git-web-host-20261010"


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.chat, self.controller = ChatFixture(), controller_fixture()
        self.adapter = QtOwnerAdapter(self.controller, self.chat, lambda w, d: d(w()), window_action=Mock())
        self.replies = []
        self.clock = 0
        self.broker = RequestBroker(self.adapter, lambda *_: True, self.replies.append, clock=lambda: self.clock)
        self.count = 0

    def call(self, method, payload=None):
        self.count += 1
        self.broker.submit(json.dumps({"contract": CONTRACT, "id": f"r{self.count}", "method": method,
            "payload": payload or {}, "expected": self.adapter.identity()}))

    def test_read_timeout_releases_wait_and_allows_reread(self):
        self.call("getHistories", {"historyUid": ""})
        self.chat.history_pending = False
        self.clock = 21; self.broker.expire()
        self.assertEqual(self.replies[-1]["result"]["error"], "read_timeout")
        self.assertIsNone(self.adapter.history_wait)
        self.call("getHistories", {"historyUid": ""})
        self.assertEqual(len(self.chat.calls), 2)
        self.assertIsNotNone(self.adapter.history_wait)

    def test_disconnect_releases_read_and_revokes_memory(self):
        self.call("getMemories")
        self.call("getHistories", {"historyUid": ""})
        self.chat.connected = False; self.chat.history_pending = False
        self.adapter.on_state("offline", False)
        self.assertIsNone(self.adapter.history_wait)
        self.assertIsNone(self.adapter.memory_snapshot)
        self.assertEqual(self.replies[-1]["result"]["error"], "history_connection_lost")
        self.assertFalse(self.broker.uncertain)

    def test_disconnect_after_history_mutation_retains_unknown_fence(self):
        self.call("createHistory")
        self.chat.connected = False
        self.adapter.on_state("offline", False)
        self.assertTrue(self.replies[-1]["result"]["unknownResult"])
        self.assertTrue(self.broker.uncertain)

    def test_old_connecting_signal_cannot_cancel_new_connected_history(self):
        self.call("getHistories", {"historyUid": ""})
        self.adapter.on_state("connecting", False)
        self.assertEqual(self.replies, [])
        self.assertIsNotNone(self.adapter.history_wait)

    def test_fast_history_response_does_not_destroy_submission_correlation(self):
        def rapid(**_):
            self.chat.history_request_id = "fast-request"
            self.chat._history_pending = None
            return True
        self.chat.create_history = rapid
        self.call("createHistory")
        self.assertEqual(self.replies, [])
        self.adapter.receive({"type": "new-history-created", "request_id": "fast-request",
            "client_uid": "client", "conf_uid": "actor", "context_id": "context", "history_uid": "history"})
        self.assertTrue(self.replies[-1]["result"]["ok"])
        self.assertFalse(self.broker.uncertain)

    def test_actual_client_keeps_correlation_after_synchronous_accept(self):
        chat = QtRuntimeChatClient()
        chat._connected = True
        chat.client_uid, chat.conf_uid, chat.context_id = "client", "actor", "context"
        chat.history_protocol = "kuro.conversation.history.v1"
        def send(payload):
            self.assertTrue(chat._accept_history_response({**payload, "type": "new-history-created"}))
            return True
        chat._send_json = send
        self.assertTrue(chat.create_history(force_new=True))
        self.assertFalse(chat.history_pending)
        self.assertTrue(chat.history_request_id)

    def test_confirmation_quit_is_silent_and_never_dispatches(self):
        self.call("getMemories")
        self.replies.clear(); self.controller.reset_mock()
        self.broker.confirm = lambda *_: (self.broker.close(), True)[1]
        self.call("memoryAction", {"action": "compact", "payload": {}})
        self.assertEqual(self.replies, [])
        self.controller.compact_memory.assert_not_called()
        self.call("getState")
        self.assertEqual(self.replies, [])

    def test_profile_timeout_releases_presentation_wait_keeps_mutation_fence(self):
        self.call("applyProfile", {"character_id": "actor", "project_id": "project", "model": "synthetic-model", "thinking_power": "normal"})
        self.assertIsNotNone(self.adapter.profile_wait)
        self.clock = 96; self.broker.expire()
        self.assertIsNone(self.adapter.profile_wait)
        self.assertTrue(self.broker.uncertain)
        self.call("getHistories", {"historyUid": ""})
        self.assertIsNotNone(self.adapter.history_wait)

    def test_busy_profile_does_not_change_selections(self):
        lock = threading.Lock(); lock.acquire()
        self.controller.lifecycle.lock = lock
        self.call("applyProfile", {"character_id": "actor", "project_id": "project", "model": "synthetic-model", "thinking_power": "normal"})
        self.assertEqual(self.replies[-1]["result"]["error"], "lifecycle_busy")
        self.controller.set_selected_character.assert_not_called()
        self.controller.start_profile.assert_not_called()
        lock.release()

    def test_expired_worker_cannot_recreate_profile_wait_or_read_snapshots(self):
        for method, payload, timeout, attribute in (
            ("applyProfile", {"character_id": "actor", "project_id": "project", "model": "synthetic-model", "thinking_power": "normal"}, 96, "profile_wait"),
            ("getMemories", {}, 21, "memory_snapshot"), ("getState", {}, 21, "runtime_snapshot")):
            with self.subTest(method=method):
                self.setUp(); jobs = []
                self.adapter.run_worker = lambda w, d: jobs.append((w, d))
                self.call(method, payload)
                work, done = jobs.pop(); result = work()
                self.clock = timeout; self.broker.expire()
                replies = copy.deepcopy(self.replies)
                done(result)
                self.assertIsNone(getattr(self.adapter, attribute))
                self.assertEqual(self.replies, replies)

    def test_expired_queued_mutation_never_starts_owner_work(self):
        self.call("getMemories"); jobs = []
        self.adapter.run_worker = lambda w, d: jobs.append((w, d))
        self.call("memoryAction", {"action": "add", "payload": {"content": "SYNTHETIC"}})
        self.clock = 21; self.broker.expire()
        work, done = jobs.pop(); done(work())
        self.controller.add_memory.assert_not_called()
        self.assertTrue(self.broker.uncertain)

    def test_expired_capture_cannot_later_submit_chat(self):
        jobs = []; self.adapter.runtime_snapshot = {"cameraEnabled": True}
        self.adapter.run_worker = lambda w, d: jobs.append((w, d))
        self.call("sendText", {"text": "SYNTHETIC", "attachments": []})
        self.clock = 21; self.broker.expire()
        _, done = jobs.pop()
        done({"ok": True, "result": {"ok": True, "images": []}})
        self.assertFalse(any(row[0] == "send" for row in self.chat.calls))
        self.assertTrue(self.broker.uncertain)

    def test_changed_scope_revokes_queued_confirmed_device_work(self):
        self.adapter.runtime_snapshot = {"captureAvailable": True}
        jobs = []; self.adapter.run_worker = lambda w, d: jobs.append((w, d))
        self.call("control", {"action": "toggle-screen", "payload": {"enabled": True}})
        self.chat.context_id = "changed"; self.adapter.on_state("idle", True)
        work, done = jobs.pop(); done(work())
        self.controller.set_pet_toggle.assert_not_called()
        self.assertFalse(self.replies[-1]["result"]["ok"])


def actual_port(owner, audits):
    tree = ast.parse((ROOT / "kuro_launcher/qt_web_host.py").read_text(encoding="utf-8"))
    host = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_create_host")
    classes = [n for n in host.body if isinstance(n, ast.ClassDef) and n.name in {"Wire", "Port"}]
    scope = dict(QObject=QObject, QTimer=QTimer, QThread=QThread, Qt=Qt, Signal=Signal, Slot=Slot,
        ThreadPoolExecutor=ThreadPoolExecutor, QtOwnerAdapter=QtOwnerAdapter, RequestBroker=RequestBroker,
        CONTRACT=CONTRACT, error=error, json=json, owner=owner, audit=lambda *a, **kw: audits.append(kw))
    exec(compile(ast.Module(body=classes, type_ignores=[]), "actual-host-port", "exec"), scope)
    return scope["Port"](owner)


class QueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.owner = QObject()
        self.owner.controller = controller_fixture()
        self.owner.chat_client = QtRuntimeChatClient(self.owner)
        self.owner._apply_lifecycle_status = Mock()
        self.owner.isVisible = lambda: True
        self.audits = []
        self.port = actual_port(self.owner, self.audits)
        self.addCleanup(self.port.shutdown)

    def wait(self, predicate):
        end = time.monotonic() + 3
        while time.monotonic() < end and not predicate():
            self.app.processEvents(); time.sleep(.005)
        self.assertTrue(predicate())

    def test_queued_message_state_and_worker_are_silent_after_close(self):
        events = []; self.port.wire.event.connect(events.append)
        self.owner.chat_client.message_received.emit({"type": "set-model-and-conf"})
        self.owner.chat_client.state_changed.emit("idle", True)
        self.port.delivered.emit(lambda _: events.append("late"), {})
        self.port.shutdown(); self.app.processEvents()
        self.assertEqual(events, [])
        self.assertTrue(self.port.adapter.closed)

    def test_status_coalesces_requests_and_delivers_on_gui_thread(self):
        release = threading.Event()
        original = self.owner.controller.read_runtime_status.return_value
        self.owner.controller.read_runtime_status.side_effect = lambda: (release.wait(2), original)[1]
        values = []
        self.port.request_status(values.append); self.port.request_status(values.append)
        release.set(); self.wait(lambda: len(values) == 2)
        self.owner.controller.read_runtime_status.assert_called_once()
        self.owner._apply_lifecycle_status.assert_called_once_with(original)
        self.assertTrue(all(r["guiThread"] for r in self.audits if "guiThread" in r))
        self.port.request_status(values.append); self.wait(lambda: len(values) == 3)
        self.assertEqual(self.owner.controller.read_runtime_status.call_count, 2)

    def test_today_coalesces_without_second_cache_or_write(self):
        release = threading.Event(); data = self.owner.controller.read_today.return_value
        self.owner.controller.read_today.side_effect = lambda: (release.wait(2), data)[1]
        values = []
        self.port.request_data(values.append); self.port.request_data(values.append)
        release.set(); self.wait(lambda: len(values) == 2)
        self.owner.controller.read_today.assert_called_once()
        self.owner.controller.mutate_schedule.assert_not_called()
        self.assertEqual(values[0]["canonical"], data)
        self.assertEqual(self.port.data_waiters, [])

    def test_missing_live2d_and_diagnostics_do_not_block_chat_lifecycle(self):
        self.owner.controller.presentation_state.side_effect = FileNotFoundError("synthetic missing model")
        self.owner.controller.read_companion_diagnostics.side_effect = RuntimeError("synthetic diagnostics unavailable")
        values = []; self.port.request_status(values.append)
        self.wait(lambda: bool(values))
        self.owner._apply_lifecycle_status.assert_called_once_with(self.owner.controller.read_runtime_status.return_value)
        self.assertTrue(values[0]["ok"])
        self.assertEqual(values[0]["presentation"]["state"], "unavailable")
        self.assertEqual(values[0]["diagnostics"]["error"], "diagnostics_unavailable")
        state = self.port.adapter._state_result(values[0], {"chat": {"ok": True}})
        self.assertIsNone(state["capabilities"]["launcher"])
        self.assertEqual(state["presentation"]["state"], "unavailable")

    def test_worker_in_flight_at_shutdown_cannot_emit_result(self):
        started, release = threading.Event(), threading.Event(); values = []
        def work(): started.set(); release.wait(2); return {"ok": True}
        self.port.run_worker(work, values.append)
        self.assertTrue(started.wait(1)); self.port.shutdown(); release.set()
        self.wait(lambda: bool(self.audits))
        self.assertEqual(values, [])

    def test_transport_identity_change_revokes_work_before_gui_delivery(self):
        chat = self.owner.chat_client
        chat._connected = True; chat._ws_app = Mock()
        chat._handle_payload({"type": "set-model-and-conf", "client_uid": "client", "conf_uid": "actor",
            "context_id": "old", "history_protocol": "kuro.conversation.history.v1"})
        self.port.adapter.runtime_snapshot = {"captureAvailable": True}
        self.port.adapter.identity()
        self.port.adapter.runtime_snapshot = {"captureAvailable": True}
        jobs = []; self.port.adapter.run_worker = lambda w, d: jobs.append((w, d))
        broker = RequestBroker(self.port.adapter, lambda *_: True, lambda _: None)
        broker.submit(json.dumps({"contract": CONTRACT, "id": "queued-scope", "expected": self.port.adapter.identity(),
            "method": "control", "payload": {"action": "toggle-camera", "payload": {"enabled": True}}}))
        token = chat.history_scope_snapshot()[1]
        thread = threading.Thread(target=lambda: chat._on_message(chat._ws_app, json.dumps({
            "type": "set-model-and-conf", "client_uid": "client", "conf_uid": "actor", "context_id": "new",
            "history_protocol": "kuro.conversation.history.v1"})))
        thread.start(); thread.join(1)
        self.assertFalse(thread.is_alive()); self.assertTrue(token.is_set())
        # Deliberately do NOT deliver GUI queued signals before starting work.
        work, done = jobs.pop(); done(work())
        self.owner.controller.set_pet_toggle.assert_not_called()
        broker.close()

    def test_client_token_and_identity_are_published_atomically(self):
        chat = self.owner.chat_client
        old = chat.history_scope_snapshot()[1]
        inside, release, sampled = threading.Event(), threading.Event(), []
        def rotate():
            with chat._changing_scope():
                chat.context_id = "half-written"; inside.set(); release.wait(2)
                chat.conf_uid = "new-actor"; chat.context_id = "new-context"
        thread = threading.Thread(target=rotate); thread.start(); self.assertTrue(inside.wait(1))
        reader = threading.Thread(target=lambda: sampled.append(chat.history_scope_snapshot()))
        reader.start(); self.assertTrue(old.is_set()); self.assertEqual(sampled, [])
        release.set(); thread.join(1); reader.join(1)
        self.assertEqual(sampled[0][0][1:3], ("new-actor", "new-context"))
        self.assertFalse(sampled[0][1].is_set())
        chat._set_history("new-history", "SYNTHETIC"); self.assertTrue(sampled[0][1].is_set())
        token = chat.history_scope_snapshot()[1]; chat.disconnect(); self.assertTrue(token.is_set())


class WiringAndBundleTests(unittest.TestCase):
    def test_security_probe_records_each_axis_before_combined_assertion(self):
        tree = ast.parse((TASK / "w6_existing_window.py").read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        probes = [n for n in calls if isinstance(n.func, ast.Name) and n.func.id == "run_security_probe"]
        self.assertEqual(len(probes), 1, "Native security needs settled, per-axis side-effect receipts")
        combined = next(n for n in calls if isinstance(n.func, ast.Name) and n.func.id == "check"
                        and n.args and isinstance(n.args[0], ast.Constant)
                        and n.args[0].value == "scheme-network-storage-denied")
        self.assertLess(probes[0].lineno, combined.lineno)
        self.assertTrue(any(k.arg == "defer" and isinstance(k.value, ast.Constant) and k.value.value is True
                            for k in combined.keywords), "Do not skip navigation/listeners on security failure")

    def test_native_gate_is_fail_closed_on_missing_coverage(self):
        spec = importlib.util.spec_from_file_location("w6_native_test", TASK / "w6_existing_window.py")
        native = importlib.util.module_from_spec(spec); spec.loader.exec_module(native)
        self.assertFalse(native.coverage([])["pass"])
        checks = [{"name": name, "pass": True} for name in native.REQUIRED_CHECKS]
        self.assertTrue(native.coverage(checks)["pass"])
        checks.pop()
        self.assertFalse(native.coverage(checks)["pass"])
        code = ast.parse((TASK / "w6_existing_window.py").read_text(encoding="utf-8"))
        literal_checks = {node.args[0].value for node in ast.walk(code) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name) and node.func.id == "check" and node.args and isinstance(node.args[0], ast.Constant)}
        dynamic = {"schedule-status", "schedule-view", "schedule-notifications", "screenshot-chat", "screenshot-today", "screenshot-settings"}
        self.assertEqual(native.REQUIRED_CHECKS - literal_checks - dynamic, set())
        # Keep the native Live2D check aligned with the distinct presentation
        # descriptor; launcher now carries the authoritative lifecycle contract.
        check = next(n for n in ast.walk(code) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name) and n.func.id == "check" and n.args
            and isinstance(n.args[0], ast.Constant) and n.args[0].value == "live2d-unavailable-chat-independent")
        self.assertIn("['presentation']['state']", ast.unparse(check.args[1]))

    def test_web_constructor_has_no_widget_build_or_read(self):
        tree = ast.parse((ROOT / "kuro_launcher/qt_app.py").read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "KuroQtLauncherWindow")
        methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
        self.assertNotIn("_web_mode", ast.unparse(cls))
        self.assertEqual(methods["__init__"].args.kw_defaults, [None])
        source = ast.unparse(methods["_init_web_presentation"])
        for name in ("WorkCompanionView", "TodayPage", "SchedulePage", "QSettings", "_wire_signals",
                "_refresh_workspace_data", "_refresh_profile_controls", "_on_chat_protocol_message", "_on_task_finished"):
            self.assertNotIn(name, source)
        for name in ("QtLauncherController", "QtRuntimeChatClient", "QtScheduleDelivery", "QSystemTrayIcon"):
            self.assertEqual(sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name for n in ast.walk(cls)), 1)

    def test_missing_pin_fails_closed_without_fallback(self):
        with patch('kuro_launcher.qt_web_release.RELEASE_PIN', None):
            with self.assertRaisesRegex(TypeError, "pin required"):
                prepare_owner_presentation(ROOT / "not-an-asset-root")

    def test_formal_pin_missing_assets_fails_closed(self):
        with self.assertRaises(FileNotFoundError):
            prepare_owner_presentation(ROOT / "not-an-asset-root")

    def test_signed_bundle_bytes_are_frozen_and_wrong_pin_is_rejected(self):
        spec = importlib.util.spec_from_file_location("w6_builder_test", TASK / "build_owner_bundle.py")
        builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
        built = builder.build(verify_only=True)
        pin = OwnerBundlePin(built["fingerprint"], built["manifestSha256"], built["publicKey"], built["signature"])
        bundle = VerifiedOwnerBundle.load(built["directory"], pin)
        with self.assertRaises(TypeError): bundle.assets["/evil.js"] = b"evil"
        with self.assertRaises(ValueError):
            VerifiedOwnerBundle.load(built["directory"], OwnerBundlePin(pin.fingerprint, "0" * 64, pin.public_key, pin.signature))
        from cryptography.exceptions import InvalidSignature
        with self.assertRaises(InvalidSignature):
            VerifiedOwnerBundle.load(built["directory"], OwnerBundlePin(pin.fingerprint, pin.manifest_sha256, pin.public_key, "0" * 128))
        original_read = Path.read_bytes
        manifests = []
        def one_manifest(path):
            if path.name == "candidate-manifest.json":
                manifests.append(path)
                if len(manifests) > 1: raise AssertionError("Unverified manifest reread")
            return original_read(path)
        with patch.object(Path, "read_bytes", one_manifest):
            self.assertEqual(dict(VerifiedOwnerBundle.load(built["directory"], pin).assets), dict(bundle.assets))
        self.assertEqual(len(manifests), 1)
        with tempfile.TemporaryDirectory(prefix=".validation-w6-pin-", dir=ROOT) as folder:
            copied = Path(folder) / pin.fingerprint; shutil.copytree(built["directory"], copied)
            (copied / "work-panel.html").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "hash mismatch"): VerifiedOwnerBundle.load(copied, pin)


class RealOwnerIOTests(unittest.TestCase):
    """Real Controller/client/Core/Memory with synthetic IO, no QApplication."""
    @classmethod
    def setUpClass(cls): cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        from web_existing_window_fixtures import ExistingWindowFixture
        self.temp = tempfile.TemporaryDirectory(prefix=".validation-w6-owner-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.fixture = ExistingWindowFixture(Path(self.temp.name) / "state")
        self.addCleanup(self.fixture.close)
        self.fixture.start()
        self.owner = QObject()
        self.owner.controller = self.fixture.make_controller(self.fixture.cfg, lambda _: None)
        self.owner.chat_client = QtRuntimeChatClient(self.owner)
        self.owner.isVisible = lambda: True
        self.owner._apply_lifecycle_status = lambda status: self.owner.chat_client.connect_to(
            f"ws://127.0.0.1:{self.fixture.ws.port}/client-ws?client_role=qt-primary") if status.llm and not self.owner.chat_client.running else None
        self.port = actual_port(self.owner, [])
        self.fixture.trace_port(self.port)
        self.port.broker.confirm = lambda *_: True
        self.replies = []; self.port.wire.response.connect(lambda raw: self.replies.append(json.loads(raw)))
        self.sequence = 0
        self.addCleanup(self.close_owner)
        self.port.request_status(lambda _: None)
        self.wait(lambda: self.owner.chat_client.history_ready)

    def close_owner(self):
        self.port.shutdown(); self.owner.chat_client.disconnect()
        self.port.pool.shutdown(wait=True, cancel_futures=True)
        if self.owner.chat_client._thread: self.owner.chat_client._thread.join(4)
        self.fixture.controller.close()

    def wait(self, predicate):
        end = time.monotonic() + 7
        while time.monotonic() < end and not predicate():
            self.app.processEvents(); time.sleep(.005)
        self.assertTrue(predicate())

    def call(self, method, payload=None):
        self.sequence += 1; rid = f"real-{self.sequence}"
        self.port.wire.submit(json.dumps({"contract": CONTRACT, "id": rid, "expected": self.port.adapter.identity(),
            "method": method, "payload": payload or {}}))
        self.wait(lambda: any(r["id"] == rid for r in self.replies))
        return next(r["result"] for r in self.replies if r["id"] == rid)

    def test_full_constructor_reads_keep_core_bytes_and_single_chat(self):
        before = self.fixture.capability.store.path.read_bytes()
        state = self.call("getState")
        self.assertTrue(state["ok"]); self.assertEqual(state["presentation"]["state"], "unavailable")
        self.assertTrue(self.call("getProfile")["ok"])
        self.assertEqual(self.call("getData")["canonical"]["sourceStates"][0]["freshness"], "stale")
        for action, p in (("status", {}), ("notifications", {}),
                ("view", {"start": "2026-10-10", "end": "2026-10-12", "timezone": "Asia/Taipei"})):
            self.assertTrue(self.call("schedule", {"action": action, "payload": p})["ok"])
        self.assertEqual(self.fixture.capability.store.path.read_bytes(), before)
        self.assertEqual(self.fixture.ws.connections, 1)
        self.assertFalse(self.call("getTools")["confirmation_available"])

    def test_second_state_with_synthetic_pet_preserves_launcher_contract(self):
        # Actual Controller/Port/Adapter and queued worker; no renderer or device.
        first = self.call("getState")
        self.assertEqual(first["capabilities"]["pet"]["state"], "unavailable")
        self.fixture.enable_synthetic_pet()
        self.port.refresh_status()  # Periodic refresh and explicit read share work.
        second = self.call("getState")
        self.assertTrue(second["captureAvailable"])
        self.assertEqual(second["capabilities"]["pet"]["state"], "ready")
        self.assertFalse(self.port.status_inflight)
        self.assertEqual(self.port.status_waiters, [])
        phases = [row["phase"] for row in self.fixture.timing]
        for phase in ("pet_lock:acquired", "pet_lock:released", "read_status:exit", "queued_delivery", "broker_response"):
            self.assertIn(phase, phases)
        self.assertTrue(all(row["gui"] for row in self.fixture.timing if row["phase"] == "queued_delivery"))
        self.assertTrue(second["capabilities"]["launcher"] == self.owner.controller.read_companion_diagnostics(),
            "Launcher capability must come from the lifecycle owner, not Live2D presentation")
        self.assertIn("voice", second["capabilities"]["launcher"])
        self.assertEqual(self.fixture.ws.connections, 1)

    def test_real_memory_profile_history_and_synthetic_capture(self):
        history = self.call("getHistories")
        self.assertTrue(history["ok"], history)
        self.assertTrue(self.call("getMemories")["ok"])
        self.assertTrue(self.call("memoryAction", {"action": "add", "payload": {"content": "SYNTHETIC owner preference"}})["changed"])
        self.assertEqual(len(self.call("getMemories")["memories"]), 1)
        result = self.call("applyProfile", {"character_id": "actor", "project_id": "project", "model": "synthetic-model", "thinking_power": "normal"})
        self.assertTrue(result["effective"])
        self.assertEqual(self.fixture.ws.connections, 1)
        self.assertTrue(self.call("createHistory")["ok"])
        self.assertTrue(self.call("sendText", {"text": "SYNTHETIC", "attachments": []})["accepted"])
        self.wait(lambda: self.port.adapter.latest_assistant == "SYNTHETIC reply")
        self.fixture.enable_synthetic_pet(); self.call("getState")
        self.assertTrue(self.call("control", {"action": "mic-start", "payload": {}})["ok"])
        self.assertTrue(self.call("control", {"action": "mic-submit", "payload": {}})["accepted"])
        self.wait(lambda: any(row["type"] == "mic-audio-end" for row in self.fixture.ws.received))
        history = self.owner.chat_client.current_history_uid
        self.assertTrue(self.call("deleteHistory", {"historyUid": history})["ok"])
        self.assertNotIn(history, self.fixture.ws.histories)

    def test_real_schedule_replay_and_sole_delivery_dedup(self):
        from kuro_launcher.qt_notifications import QtScheduleDelivery
        c = self.owner.controller
        c.schedule_notification_action({"action": "preferences", "confirmed": True, "preferences": {
            "timezone": "UTC", "quietEnabled": False, "quietStart": "22:00", "quietEnd": "08:00"}})
        now = datetime.now(timezone.utc).replace(microsecond=0)
        payload = {"action": "mutate", "payload": {"action": "create", "idempotencyKey": "real-once", "item": {
            "title": "SYNTHETIC", "kind": "study", "timezone": "UTC", "start": now.isoformat(),
            "end": (now + timedelta(hours=1)).isoformat(), "notification": {"enabled": True, "minutesBefore": 0, "channel": "desktop"}}}}
        first = self.call("schedule", payload)
        self.assertTrue(first["ok"]); self.assertEqual(self.call("schedule", payload), first)
        tray = Mock(); delivery = QtScheduleDelivery(c, tray, lambda _: None, self.owner)
        try:
            with patch.object(delivery, "available", return_value=True):
                delivery.poll(); self.wait(lambda: not delivery.busy)
                delivery.poll(); self.wait(lambda: not delivery.busy)
            tray.showMessage.assert_called_once()
        finally: delivery.stop()


if __name__ == "__main__": unittest.main()
