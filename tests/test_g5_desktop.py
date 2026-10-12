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
from kuro_launcher.qt_controller import QtLauncherController
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
        w._web_mode = False
        w.work_web_candidate = None
        w.tray = Mock()
        w.controller = Mock()
        w.chat_client = Mock()
        w.status_timer = Mock()
        w.runtime_timer = Mock()
        w.schedule_delivery = Mock()
        w._discard_auto_empty_history_if_safe = Mock()
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
        calls.attach_mock(w.schedule_delivery.stop, "delivery")
        calls.attach_mock(w.chat_client.disconnect, "disconnect")
        calls.attach_mock(w.controller.close, "controller")
        calls.attach_mock(w.tray.hide, "tray")
        with patch.object(QApplication, "instance") as app:
            calls.attach_mock(app.return_value.quit, "quit")
            w.quit_application()
            w.cleanup()  # aboutToQuit callback
        self.assertEqual([c[0] for c in calls.mock_calls],
                         ["delivery", "disconnect", "controller", "tray", "quit"])
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
        self.assertEqual([a.text() for a in menu.actions()], ["Show Kuro", "Quit Kuro"])
        w.hide()
        menu.actions()[0].trigger()
        self.assertTrue(w.isVisible())
        w.hide()
        w.tray.messageClicked.connect.call_args.args[0]()
        self.assertTrue(w.isVisible())
        with patch.object(QApplication, "instance") as app:
            menu.actions()[1].trigger()
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
