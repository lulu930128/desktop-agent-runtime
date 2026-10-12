from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import launcher_qt


class LauncherEntrypointTests(unittest.TestCase):
    def test_desktop_vbs_targets_qt_without_work_panel_build(self):
        script = (Path(__file__).resolve().parents[1] / '桌寵啟動器.vbs').read_text(encoding='ascii')
        self.assertNotIn('work-panel.html', script)
        self.assertNotIn('workPanelEntry', script)
        self.assertIn('launcherArgs = """" & launcherScript & """"', script)
        self.assertIn('WScript.Arguments.Named.Exists("check")', script)
        self.assertNotIn('--work-panel', script)
        self.assertNotIn('cmd = "pyw ', script)

    def test_repeated_launch_signals_primary_qt(self):
        with patch.object(launcher_qt, '_signal_existing_qt', return_value=True) as signal:
            self.assertTrue(launcher_qt._activate_existing_launcher())
        signal.assert_called_once_with()

    def test_failed_activation_reports_failure(self):
        with patch.object(launcher_qt, '_signal_existing_qt', return_value=False) as signal:
            self.assertFalse(launcher_qt._activate_existing_launcher())
        signal.assert_called_once_with()

    def test_activation_event_targets_qt_and_entrypoint_has_no_listener(self):
        self.assertEqual(launcher_qt.WINDOWS_QT_ACTIVATE_EVENT_NAME,
                         'Local\\KuroDesktopAgentQtActivate')
        source = Path(launcher_qt.__file__).read_text(encoding='utf-8')
        for legacy in ('WorkPanelControlServer', '23568', 'request_work_panel_activation',
                       'work_panel_api', 'WorkPanelActivate'):
            self.assertNotIn(legacy, source)

    def test_first_launch_visible_with_auto_start(self):
        self.check_first_launch(True)

    def test_first_launch_visible_without_auto_start(self):
        self.check_first_launch(False)

    def test_explicit_none_pin_is_widgets_rollback_fixture(self):
        with patch('kuro_launcher.qt_web_release.RELEASE_PIN', None):
            self.check_first_launch(False, widgets=True)

    def test_invalid_pin_stops_before_application_or_owner(self):
        cfg = SimpleNamespace(root=Path.cwd(), logs_dir=Path.cwd() / 'unused-test-log')
        with patch.object(launcher_qt, '_load_env'), \
             patch.object(launcher_qt, '_set_windows_app_user_model_id'), \
             patch.object(launcher_qt, '_acquire_launcher_instance', return_value=True), \
             patch.object(launcher_qt, '_create_qt_activation_event'), \
             patch.object(launcher_qt, '_close_launcher_activation_event') as close, \
             patch('kuro_launcher.config.load_config', return_value=cfg), \
             patch('kuro_launcher.utils.build_logs_dir', return_value=cfg.logs_dir), \
             patch('kuro_launcher.runtime_logging.setup_runtime_logging'), \
             patch('kuro_launcher.qt_web_release.prepare_owner_presentation', side_effect=ValueError('tampered')), \
             patch('PySide6.QtWidgets.QApplication') as app, \
             patch('kuro_launcher.qt_app.KuroQtLauncherWindow') as window:
            self.assertEqual(launcher_qt.main(), 2)
        app.assert_not_called()
        window.assert_not_called()
        close.assert_called_once_with()

    def check_first_launch(self, auto_start, widgets=False):
        cfg = SimpleNamespace(root=Path.cwd(), logs_dir=Path.cwd() / 'launcher_logs',
                              startup_auto_start=auto_start)
        app = Mock()
        app.exec.return_value = 0
        with patch.object(launcher_qt, '_load_env'), \
             patch.object(launcher_qt, '_set_windows_app_user_model_id'), \
             patch.object(launcher_qt, '_acquire_launcher_instance', return_value=True), \
             patch.object(launcher_qt, '_create_qt_activation_event'), \
             patch('kuro_launcher.config.load_config', return_value=cfg), \
             patch('kuro_launcher.utils.build_logs_dir', return_value=cfg.logs_dir), \
             patch('kuro_launcher.runtime_logging.setup_runtime_logging'), \
             patch('PySide6.QtWidgets.QApplication', return_value=app), \
             patch('PySide6.QtCore.QTimer') as timer, \
             patch('kuro_launcher.qt_app.KuroQtLauncherWindow') as window:
            self.assertEqual(launcher_qt.main(), 0)
            window.return_value.reveal.assert_called_once_with()
            with patch.object(launcher_qt, '_consume_qt_activation_event', return_value=True):
                timer.return_value.timeout.connect.call_args.args[0]()
            self.assertEqual(window.return_value.reveal.call_count, 2)
        from kuro_launcher.qt_web_release import RELEASE_PIN, VerifiedOwnerBundle
        window.assert_called_once()
        self.assertEqual(window.call_args.args, (cfg,))
        bundle = window.call_args.kwargs['web_bundle']
        if widgets:
            self.assertIsNone(bundle)
        else:
            self.assertIsInstance(bundle, VerifiedOwnerBundle)
            self.assertEqual(bundle.pin, RELEASE_PIN)
            self.assertIn('/work-panel.html', bundle.assets)
        window.return_value.hide.assert_not_called()
        app.setQuitOnLastWindowClosed.assert_called_once_with(False)


if __name__ == '__main__':
    unittest.main()
