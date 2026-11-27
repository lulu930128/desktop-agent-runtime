"""Synthetic desktop ownership tests: no real services or OS notifications."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import launcher_qt  # bootstrap runtime imports
from PySide6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QMessageBox
from kuro_launcher.qt_app import KuroQtLauncherWindow
from kuro_launcher.qt_controller import QtLauncherController, RuntimeStatus
from kuro_launcher.qt_notifications import QtScheduleDelivery


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = KuroQtLauncherWindow.__new__(KuroQtLauncherWindow)
        QMainWindow.__init__(self.window)
        w = self.window
        w.explicit_quitting = False
        w._cleanup_done = False
        w.work_web_candidate = Mock()
        w.tray = Mock()
        w.controller = Mock()
        w.chat_client = Mock()
        w.chat_client.connected = False
        w.last_status = None
        w.status_timer = Mock()
        w.runtime_timer = Mock()
        w.schedule_delivery = Mock()
        w._append_log = Mock()
        w._set_action_status = Mock()

    def tearDown(self):
        self.window.deleteLater()
        self.app.processEvents()

    def test_close_hides_without_cleanup_and_reveal_restores(self):
        w = self.window
        w.reveal()
        event = Mock()
        with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=True):
            w.closeEvent(event)
        event.ignore.assert_called_once()
        self.assertFalse(w.isVisible())
        w.controller.close.assert_not_called()
        w.chat_client.disconnect.assert_not_called()
        w.reveal()
        self.assertTrue(w.isVisible())
        self.assertFalse(w.isMinimized())

    def test_no_tray_keeps_window_reachable_even_after_tray_disappears(self):
        w = self.window
        with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=False):
            w.closeEvent(Mock())
            self.assertTrue(w.isVisible())
            w.hide()
            w._ensure_desktop_entry()
            self.assertTrue(w.isVisible())
        w.controller.close.assert_not_called()
        w._set_action_status.assert_called_once()

    def test_quit_cleanup_once_order_and_explicit_close(self):
        w = self.window
        calls = Mock()
        calls.attach_mock(w.work_web_candidate.shutdown_candidate, "web")
        calls.attach_mock(w.schedule_delivery.stop, "delivery")
        calls.attach_mock(w.chat_client.disconnect, "disconnect")
        calls.attach_mock(w.controller.close, "controller")
        calls.attach_mock(w.tray.hide, "tray")
        with patch.object(QApplication, "instance") as app:
            calls.attach_mock(app.return_value.quit, "quit")
            w.quit_application()
            w.cleanup()  # aboutToQuit callback
        self.assertEqual([c[0] for c in calls.mock_calls],
                         ["web", "delivery", "disconnect", "controller", "tray", "quit"])
        event = Mock()
        w.closeEvent(event)
        event.accept.assert_called_once()
        w.controller.close.assert_called_once()

    def test_cleanup_errors_do_not_skip_later_resources(self):
        w = self.window
        w.chat_client.disconnect.side_effect = RuntimeError("fixture")
        w.controller.close.side_effect = RuntimeError("fixture")
        with patch.object(QApplication, "instance") as app:
            w.quit_application()
            app.return_value.quit.assert_called_once()
        w.tray.hide.assert_called_once()
        self.assertEqual(w._append_log.call_count, 2)

    def test_tray_actions_and_message_click_reveal_qt(self):
        w = self.window
        with patch("kuro_launcher.qt_app.QSystemTrayIcon") as tray:
            w._create_tray()
        tray.assert_called_once_with(w)
        menu = w.tray.setContextMenu.call_args.args[0]
        actions = {a.text(): a for a in menu.actions() if a.isEnabled() and not a.isSeparator()}
        self.assertEqual(list(actions), ["將 Kuro 帶到最前面", "顯示桌寵", "重新定位桌寵",
                                        "開啟日誌資料夾", "重新啟動 Kuro", "結束 Kuro"])
        w.hide()
        actions["將 Kuro 帶到最前面"].trigger()
        self.assertTrue(w.isVisible())
        w.hide()
        w.tray.messageClicked.connect.call_args.args[0]()
        self.assertTrue(w.isVisible())
        with patch.object(QApplication, "instance") as app:
            actions["結束 Kuro"].trigger()
            app.return_value.quit.assert_called_once()

    def test_restart_native_confirmation_cancel_and_accept(self):
        w = self.window
        w._restart_launcher = Mock()
        with patch("kuro_launcher.qt_app.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
            w._confirm_restart_launcher()
        w._restart_launcher.assert_not_called()
        with patch("kuro_launcher.qt_app.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            w._confirm_restart_launcher()
        w._restart_launcher.assert_called_once()

    def create_tray_menu(self):
        with patch("kuro_launcher.qt_app.QSystemTrayIcon.show"):
            self.window._create_tray()
        return self.window.tray.contextMenu()

    def test_tray_status_uses_only_observed_snapshot_without_io(self):
        w = self.window
        menu = self.create_tray_menu()
        self.assertEqual([a.text() for a in menu.actions()[:2]], ["對話：未連線", "桌寵：尚未確認"])
        for connected, snapshot, expected in (
            (True, RuntimeStatus(False, False, False, True), ["對話：已連線", "桌寵：已啟動"]),
            (False, RuntimeStatus(True, True, True, False), ["對話：未連線", "桌寵：未啟動"]),
            (None, None, ["對話：尚未確認", "桌寵：尚未確認"]),
            (False, SimpleNamespace(pet_shell=True), ["對話：未連線", "桌寵：尚未確認"]),
        ):
            w.chat_client.connected, w.last_status = connected, snapshot
            menu.aboutToShow.emit()
            self.assertEqual([a.text() for a in menu.actions()[:2]], expected)
        self.assertTrue(all(not a.isEnabled() for a in menu.actions()[:2]))
        self.assertEqual([i for i, a in enumerate(menu.actions()) if a.isSeparator()], [2, 6])
        self.assertIn('QMenu#kuroTrayMenu', menu.styleSheet())
        self.assertEqual(w.styleSheet(), '')
        self.assertEqual(w.controller.mock_calls, [])
        self.assertEqual(w.work_web_candidate.owner_port.mock_calls, [])

    def test_pet_actions_dispatch_off_gui_thread_and_do_not_invent_status(self):
        w = self.window
        menu = self.create_tray_menu()
        actions = {a.text(): a for a in menu.actions()}
        port = w.work_web_candidate.owner_port
        for label, method, args in (("顯示桌寵", w.controller.show_pet, ()),
                                    ("重新定位桌寵", w.controller.run_pet_command, ("reset-pet-position",))):
            with self.subTest(label=label):
                port.reset_mock()
                worker_threads = []
                def operation(*_):
                    worker_threads.append(threading.get_ident())
                    return {"ok": True}
                method.side_effect = operation
                actions[label].trigger()
                self.assertEqual(worker_threads, [])
                self.assertFalse(actions[label].isEnabled())
                w._run_tray_operation(label, method, pet=True)
                port.run_worker.assert_called_once()
                work, done = port.run_worker.call_args.args
                results = []
                thread = threading.Thread(target=lambda: results.append(work()))
                thread.start(); thread.join(timeout=2)
                self.assertFalse(thread.is_alive())
                self.assertNotEqual(worker_threads, [threading.get_ident()])
                method.assert_called_once_with(*args)
                with patch.object(QMessageBox, 'warning') as warning:
                    done(results[0])
                    warning.assert_not_called()
                self.assertTrue(actions[label].isEnabled())
                self.assertIsNone(w.last_status)
                port.refresh_status.assert_not_called()

    def test_tray_failure_is_visible_sanitized_and_retryable(self):
        w = self.window
        menu = self.create_tray_menu()
        action = next(a for a in menu.actions() if a.text() == "重新定位桌寵")
        for outcome in (TimeoutError('private fixture payload'), {"ok": False}, None, {"ok": "true"}):
            with self.subTest(outcome=type(outcome).__name__):
                w.controller.run_pet_command.side_effect = outcome if isinstance(outcome, Exception) else None
                w.controller.run_pet_command.return_value = outcome
                action.trigger()
                work, done = w.work_web_candidate.owner_port.run_worker.call_args.args
                with patch.object(QMessageBox, 'warning') as warning:
                    done(work())
                    warning.assert_called_once()
                    message = warning.call_args.args[2]
                    self.assertIn('重新定位桌寵未完成', message)
                    self.assertNotIn('private fixture payload', message)
                self.assertTrue(action.isEnabled())

    def test_logs_dispatch_failure_and_late_completion_after_cleanup(self):
        w = self.window
        menu = self.create_tray_menu()
        action = next(a for a in menu.actions() if a.text() == "開啟日誌資料夾")
        w.controller.open_logs_dir.return_value = None
        action.trigger()
        w.controller.open_logs_dir.assert_not_called()
        work, done = w.work_web_candidate.owner_port.run_worker.call_args.args
        with patch.object(QMessageBox, 'warning') as warning:
            done(work())
            warning.assert_not_called()
        w.controller.open_logs_dir.assert_called_once_with()
        w.work_web_candidate.owner_port.run_worker.side_effect = RuntimeError('pool closed')
        with patch.object(QMessageBox, 'warning') as warning:
            action.trigger()
            self.assertIn('無法開啟日誌資料夾', warning.call_args.args[2])
        self.assertTrue(action.isEnabled())
        w.cleanup()
        with patch.object(QMessageBox, 'warning') as warning:
            done({"ok": False})
            action.trigger()
            warning.assert_not_called()

    def test_pet_spawn_overrides_inherited_desktop_owner(self):
        c = QtLauncherController.__new__(QtLauncherController)
        c.cfg = SimpleNamespace(llm_url="http://fixture", llm_host="fixture", llm_port=1,
            pet_control_host="127.0.0.1", pet_control_port=2,
            pet_electron_dir=Path.cwd(), logs_dir=Path.cwd())
        c.log = Mock()
        c.core_runtime = Mock()
        c.core_runtime.child_environment.return_value = {}
        with patch.dict(os.environ, {"KURO_DESKTOP_OWNER": "electron", "KURO_LAUNCHER_CONTROL_TOKEN": "stale"}), \
             patch.object(c, "_pet_electron_runtime", return_value=(Path("fixture.exe"), "")), \
             patch.object(c, "presentation_state", return_value={"presentation": {}}), \
             patch.object(Path, "mkdir"), patch.object(Path, "open"), \
             patch("kuro_launcher.qt_controller.subprocess.Popen") as spawn:
            c._spawn_pet_electron_locked()
        env = spawn.call_args.kwargs["env"]
        self.assertEqual(env["KURO_DESKTOP_OWNER"], "qt")
        self.assertNotIn("KURO_MAIL_POLLER_OWNER", env)
        self.assertNotIn("KURO_CORE_TOKEN", env)
        self.assertNotIn("KURO_LAUNCHER_CONTROL_URL", env)
        self.assertNotIn("KURO_LAUNCHER_CONTROL_TOKEN", env)
        self.assertIn("client_role=pet-presentation", env["KURO_BACKEND_WS_URL"])


class NotificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.controller = Mock()
        self.tray = Mock()
        self.log = Mock()
        self.delivery = QtScheduleDelivery(self.controller, self.tray, self.log)
        self.availability = patch.object(self.delivery, "available", return_value=True)
        self.availability.start()
        self.calls = []
        self.thread_ids = []

        def request(payload):
            self.calls.append(payload)
            self.thread_ids.append(threading.get_ident())
            if payload["action"] == "claim":
                return {"ok": True, "delivery": {"id": "fixture", "leaseToken": "synthetic"}}
            if payload["action"] == "authorize":
                return {"ok": True, "state": "dispatching", "title": "Fixture reminder"}
            return {"ok": True}
        self.request = request
        self.controller.schedule_notification_action.side_effect = request

    def tearDown(self):
        self.delivery.stop()
        self.app.processEvents()
        self.delivery.deleteLater()
        self.app.processEvents()
        self.availability.stop()

    def wait_idle(self):
        deadline = time.monotonic() + 4
        while self.delivery.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()
        self.assertFalse(self.delivery.busy)

    def test_claim_authorize_main_thread_show_then_background_ack(self):
        main_thread = threading.get_ident()
        shows = []
        self.tray.showMessage.side_effect = lambda *args: shows.append(threading.get_ident())
        self.delivery.poll()
        self.wait_idle()
        self.assertEqual([c["action"] for c in self.calls], ["claim", "authorize", "ack"])
        self.assertEqual(self.calls[-1]["result"], "delivered")
        self.assertEqual(self.calls[-1]["leaseToken"], "synthetic")
        self.assertEqual(shows, [main_thread])
        self.assertTrue(all(t != main_thread for t in self.thread_ids))

    def test_no_delivery_when_tray_or_messages_unavailable(self):
        self.availability.stop()
        for tray_available, messages in ((False, True), (True, False)):
            with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=tray_available), \
                 patch.object(QSystemTrayIcon, "supportsMessages", return_value=messages):
                self.delivery.poll()
        self.controller.schedule_notification_action.assert_not_called()

    def test_authorize_false_never_shows_or_acks(self):
        self.controller.schedule_notification_action.side_effect = [
            {"delivery": {"id": "fixture", "leaseToken": "synthetic"}}, {"ok": False}]
        self.delivery.poll()
        self.wait_idle()
        self.tray.showMessage.assert_not_called()
        self.assertEqual(self.controller.schedule_notification_action.call_count, 2)

    def test_authorize_conflict_never_shows(self):
        self.controller.schedule_notification_action.side_effect = [
            {"delivery": {"id": "fixture", "leaseToken": "synthetic"}}, RuntimeError("conflict")]
        self.delivery.poll()
        self.wait_idle()
        self.tray.showMessage.assert_not_called()
        self.log.assert_called_once()

    def test_show_failure_is_acked_failed(self):
        self.tray.showMessage.side_effect = RuntimeError("fixture")
        self.delivery.poll()
        self.wait_idle()
        self.assertEqual(self.calls[-1]["result"], "failed")

    def test_ack_failure_bounded_no_redisplay(self):
        def request(payload):
            result = self.request(payload)
            if payload["action"] == "ack":
                raise TimeoutError("synthetic private title/token")
            return result
        self.controller.schedule_notification_action.side_effect = request
        self.delivery.poll()
        self.wait_idle()
        self.assertEqual(len(self.calls), 3)
        self.tray.showMessage.assert_called_once()
        self.log.assert_called_once_with("Schedule notification delivery failed: TimeoutError")

    def test_single_inflight_including_ack(self):
        entered, release = threading.Event(), threading.Event()
        def request(payload):
            result = self.request(payload)
            if payload["action"] == "ack":
                entered.set()
                release.wait(2)
            return result
        self.controller.schedule_notification_action.side_effect = request
        self.delivery.poll()
        for _ in range(10):
            self.delivery.poll()
        deadline = time.monotonic() + 2
        while not entered.is_set() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        try:
            self.assertTrue(entered.is_set())
            self.delivery.poll()
            self.assertEqual(len(self.calls), 3)
        finally:
            release.set()
        self.wait_idle()

    def test_ui_timeout_unknown_and_queued_signal_cannot_show_later(self):
        self.delivery.DISPLAY_TIMEOUT = .03
        self.delivery.poll()
        self.delivery.worker.join(timeout=1)  # deliberately withhold Qt dispatch
        self.wait_idle()
        self.tray.showMessage.assert_not_called()
        self.assertEqual(self.calls[-1]["result"], "unknown")

    def test_stop_cancels_pending_show_and_stops_future_claims(self):
        self.delivery.poll()
        deadline = time.monotonic() + 1
        while self.delivery.pending is None and time.monotonic() < deadline:
            time.sleep(.005)
        self.delivery.stop()
        self.wait_idle()
        self.delivery.poll()
        self.tray.showMessage.assert_not_called()
        self.assertEqual([c["action"] for c in self.calls], ["claim", "authorize", "ack"])
        self.assertEqual(self.calls[-1]["result"], "unknown")

    def test_claim_failure_releases_inflight_without_local_retry(self):
        self.controller.schedule_notification_action.side_effect = TimeoutError("fixture")
        self.delivery.poll()
        self.wait_idle()
        self.controller.schedule_notification_action.assert_called_once()
        self.tray.showMessage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
