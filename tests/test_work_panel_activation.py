from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import launcher_qt  # noqa: F401
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Qt
from kuro_launcher.qt_app import KuroQtLauncherWindow
from kuro_launcher.work_panel_recovery import WorkPanelRecoveryDialog
from kuro_launcher.utils import get_listening_pid_windows


class ActivationHarness:
    request_work_panel_activation = KuroQtLauncherWindow.request_work_panel_activation
    _run_pending_work_panel_activation = KuroQtLauncherWindow._run_pending_work_panel_activation
    _on_task_finished = KuroQtLauncherWindow._on_task_finished
    _on_task_failed = KuroQtLauncherWindow._on_task_failed

    def __init__(self):
        self.work_panel_activation_pending = False
        self.work_panel_activation_inflight = False
        self.work_panel_has_been_revealed = False
        self.work_panel_pending_request = None
        self.work_panel_recovery_dialog = Mock()
        self.controller = SimpleNamespace(ensure_work_panel=Mock(return_value={"ok": True, "instance_id": "pet-1"}))
        self.controller.reconcile_runtime = Mock()
        self._run_task = Mock()
        self._append_log = Mock()
        self._set_action_status = Mock()
        self._show_work_panel_recovery = Mock()
        self.refresh_status = Mock()


class WorkPanelActivationTests(unittest.TestCase):
    def test_restart_releases_hidden_qt_application_after_close(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory(dir=Path.cwd() / 'launcher_logs') as directory:
            fake = SimpleNamespace(cfg=SimpleNamespace(root=Path.cwd(), logs_dir=Path(directory)),
                                   status_timer=Mock(), runtime_timer=Mock(), close=Mock(),
                                   controller=SimpleNamespace(lifecycle=SimpleNamespace(desired_running=True)))
            app = Mock()
            with patch('subprocess.Popen') as spawn, patch('PySide6.QtWidgets.QApplication.instance', return_value=app):
                KuroQtLauncherWindow._restart_launcher(fake)
            self.assertFalse(fake.controller.lifecycle.desired_running)
            spawn.assert_called_once()
            fake.close.assert_called_once()
            app.quit.assert_called_once()

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_signal_coalesces_and_keeps_latest_intent_until_completion(self):
        window = ActivationHarness()
        with redirect_stdout(io.StringIO()), patch("kuro_launcher.qt_app.QTimer.singleShot") as schedule:
            for _ in range(10):
                window.request_work_panel_activation("second-launch")
            window._run_task.assert_called_once()
            self.assertFalse(window.work_panel_has_been_revealed)
            callback = window._run_task.call_args.args[1]
            result = callback()
            self.assertEqual(window.controller.ensure_work_panel.call_args.kwargs["source"], "second-launch")
            window._on_task_finished("ensure-work-panel", result)
            self.assertTrue(window.work_panel_has_been_revealed)
            schedule.assert_called_once()
            schedule.call_args.args[1]()
            self.assertEqual(sum(call.args[0] == 'ensure-work-panel' for call in window._run_task.call_args_list), 2)
            self.assertEqual(sum(call.args[0] == 'runtime-reconcile' for call in window._run_task.call_args_list), 1)
            self.assertFalse(window.work_panel_activation_pending)

    def test_failure_unblocks_queue_without_marking_revealed_or_modal_warning(self):
        window = ActivationHarness()
        window.work_panel_activation_inflight = True
        with patch("kuro_launcher.qt_app.QMessageBox.warning") as modal:
            window._on_task_failed("ensure-work-panel", "WP_RENDERER_NOT_READY / request_id=test")
        self.assertFalse(window.work_panel_activation_inflight)
        self.assertFalse(window.work_panel_has_been_revealed)
        window._show_work_panel_recovery.assert_called_once()
        modal.assert_not_called()

    def test_recovery_dialog_visible_without_console_and_retry_is_explicit(self):
        retry = Mock()
        dialog = WorkPanelRecoveryDialog(retry)
        try:
            dialog.reveal("WP_RENDERER_NOT_READY / request_id=test")
            self.app.processEvents()
            self.assertIsNone(dialog.parent())
            self.assertTrue(dialog.isVisible())
            self.assertFalse(dialog.isModal())
            self.assertFalse(dialog.testAttribute(Qt.WidgetAttribute.WA_QuitOnClose))
            retry.assert_not_called()
            dialog.retry_button.click()
            self.app.processEvents()
            retry.assert_called_once()
            self.assertFalse(dialog.isVisible())
        finally:
            dialog.close()

    def test_closing_recovery_does_not_exit_background_launcher(self):
        dialog = WorkPanelRecoveryDialog(Mock())
        resumed = []
        dialog.reveal("WP_TEST")
        QTimer.singleShot(0, dialog.close)
        QTimer.singleShot(40, lambda: (resumed.append(True), self.app.quit()))
        self.app.exec()
        self.assertEqual(resumed, [True])

    def test_listener_match_is_exact_and_bounded(self):
        output = "  TCP  127.0.0.1:235670  0.0.0.0:0  LISTENING  7\n  TCP  127.0.0.1:23567  0.0.0.0:0  LISTENING  8\n"
        with patch("kuro_launcher.utils.os.name", "nt"), \
             patch("kuro_launcher.utils.subprocess.check_output", return_value=output) as netstat:
            self.assertEqual(get_listening_pid_windows(23567, "127.0.0.1"), 8)
        self.assertEqual(netstat.call_args.kwargs["timeout"], 2.0)


if __name__ == "__main__":
    unittest.main()
