from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import launcher_qt


class LauncherEntrypointTests(unittest.TestCase):
    def test_desktop_vbs_targets_only_work_panel_with_repo_python(self):
        script = (Path(__file__).resolve().parents[1] / '桌寵啟動器.vbs').read_text(encoding='ascii')
        self.assertIn('pet-electron\\renderer-dist\\work-panel.html', script)
        self.assertIn('launcherArgs = """" & launcherScript & """"', script)
        self.assertIn('WScript.Arguments.Named.Exists("check")', script)
        self.assertNotIn('--work-panel', script)
        self.assertNotIn('cmd = "pyw ', script)

    def test_repeated_launch_signals_primary_work_panel(self):
        with patch.object(launcher_qt, '_signal_existing_work_panel', return_value=True) as signal:
            self.assertTrue(launcher_qt._activate_existing_launcher())
        signal.assert_called_once_with()

    def test_failed_activation_reports_failure(self):
        with patch.object(launcher_qt, '_signal_existing_work_panel', return_value=False) as signal:
            self.assertFalse(launcher_qt._activate_existing_launcher())
        signal.assert_called_once_with()

    def test_console_activation_entry_is_removed(self):
        self.assertFalse(hasattr(launcher_qt, '_signal_existing_launcher_console'))
        self.assertFalse(hasattr(launcher_qt, '_create_launcher_activation_event'))

    def test_no_argument_start_keeps_background_owner_hidden_and_opens_panel(self):
        cfg = SimpleNamespace(root=Path.cwd(), logs_dir=Path.cwd() / 'launcher_logs',
                              startup_auto_start=True, launcher_control_host='127.0.0.1',
                              launcher_control_port=0)
        app = Mock()
        app.exec.return_value = 0
        with patch.object(launcher_qt, '_load_env'), \
             patch.object(launcher_qt, '_set_windows_app_user_model_id'), \
             patch.object(launcher_qt, '_acquire_launcher_instance', return_value=True), \
             patch.object(launcher_qt, '_create_work_panel_activation_event'), \
             patch('kuro_launcher.config.load_config', return_value=cfg), \
             patch('kuro_launcher.utils.build_logs_dir', return_value=cfg.logs_dir), \
             patch('kuro_launcher.runtime_logging.setup_runtime_logging'), \
             patch('PySide6.QtWidgets.QApplication', return_value=app), \
             patch('PySide6.QtCore.QTimer') as timer, \
             patch('kuro_launcher.qt_app.KuroQtLauncherWindow') as window, \
             patch('kuro_launcher.work_panel_api.WorkPanelControlServer'):
            self.assertEqual(launcher_qt.main(), 0)
            timer.singleShot.call_args.args[1]()
        window.assert_called_once_with(cfg, open_work_panel_on_start=True)
        window.return_value.request_work_panel_activation.assert_called_once_with('startup')
        window.return_value.hide.assert_called_once()
        window.return_value.show.assert_not_called()
        app.setQuitOnLastWindowClosed.assert_called_once_with(False)


if __name__ == '__main__':
    unittest.main()
