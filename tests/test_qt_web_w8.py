"""W8 offscreen evidence only: no native taskbar or production acceptance."""
from contextlib import contextmanager, ExitStack
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QImageReader
from PySide6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QWidget

from kuro_launcher import qt_app, qt_branding, qt_web_host
from test_qt_web_window_chrome import window_action

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def web_window():
    def surface(owner, bundle):
        host = QWidget(owner)
        host.owner_port = Mock()
        host.shutdown_candidate = Mock()
        owner.work_web_candidate = host
        return host

    with ExitStack() as stack:
        stack.enter_context(patch.object(qt_app, 'QtLauncherController', return_value=Mock()))
        stack.enter_context(patch.object(qt_web_host, 'create_existing_window_host', side_effect=surface))
        for name in ('_start_notification_delivery', '_schedule_startup_auto_start'):
            stack.enter_context(patch.object(qt_app.KuroQtLauncherWindow, name))
        stack.enter_context(patch.object(qt_app, 'QSettings', side_effect=AssertionError('Private state')))
        stack.enter_context(patch.object(QSystemTrayIcon, 'show'))
        window = qt_app.KuroQtLauncherWindow(SimpleNamespace(), web_bundle=object())
        window.status_timer.stop()
        window.runtime_timer.stop()
        try:
            yield window
        finally:
            window.cleanup()
            window.deleteLater()


class W8IconTrayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_canonical_ico_decodes_and_app_window_tray_share_pixels(self):
        self.assertEqual(qt_branding.ICON_PATH, ROOT / 'pet-electron/src/assets/favicon.ico')
        self.assertTrue(QImageReader(str(qt_branding.ICON_PATH)).canRead())
        expected = QIcon(str(qt_branding.ICON_PATH))
        self.assertFalse(expected.isNull())
        with web_window() as window:
            for icon in (self.app.windowIcon(), window.windowIcon(), window.tray.icon()):
                self.assertEqual(icon.cacheKey(), window.windowIcon().cacheKey())
                for size in (16, 32, 64, 256):
                    self.assertFalse(icon.pixmap(size, size).isNull())
                    self.assertEqual(icon.pixmap(size, size).toImage(), expected.pixmap(size, size).toImage())
            self.assertEqual(window.tray.toolTip(), 'Kuro')
            self.assertEqual([a.text() for a in window.tray.contextMenu().actions()],
                             ['Show Kuro', 'Restart Kuro', 'Quit Kuro'])

    def test_missing_and_corrupt_icon_warn_and_keep_tray_usable(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.tmp') as folder:
            missing = Path(folder) / 'missing.ico'
            corrupt = Path(folder) / 'corrupt.ico'
            corrupt.write_bytes(b'not an icon')
            for path in (missing, corrupt):
                with self.subTest(path=path.name), self.assertLogs('kuro_launcher.qt_branding', level='WARNING'):
                    icon = qt_branding.load_kuro_icon(path)
                self.assertFalse(icon.isNull())
                self.assertFalse(icon.pixmap(32, 32).isNull())

    def test_visible_web_tool_has_no_topmost_or_no_focus_flags(self):
        with web_window() as window:
            window.reveal()
            self.assertTrue(window.isVisible())
            self.assertEqual(window.windowType(), Qt.WindowType.Tool)
            self.assertTrue(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
            self.assertFalse(window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
            self.assertFalse(window.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus)
            self.assertIsNone(window.parent())
            self.assertIs(window.centralWidget(), window.work_web_candidate)

    def test_minimize_and_x_hide_same_owner_tray_and_second_launch_reveal(self):
        import launcher_qt
        with web_window() as window, patch.object(window.tray, 'isVisible', return_value=True), \
                patch.object(QSystemTrayIcon, 'isSystemTrayAvailable', return_value=True):
            window.reveal()
            self.assertTrue(window_action(window)('minimizeWindow')['ok'])
            self.app.processEvents()
            self.assertFalse(window.isVisible())
            window._tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
            self.assertTrue(window.isVisible())
            self.assertFalse(window.isMinimized())
            window.close()
            self.assertFalse(window.isVisible())
            window._tray_activated(QSystemTrayIcon.ActivationReason.DoubleClick)
            self.assertTrue(window.isVisible())
            window.hide()
            with patch.object(launcher_qt, '_consume_qt_activation_event', return_value=True):
                timer = launcher_qt._start_activation_timer(window)
                timer.stop()
                timer.timeout.emit()
            self.assertTrue(window.isVisible())
            self.assertEqual(window.windowType(), Qt.WindowType.Tool)
            window.controller.close.assert_not_called()
            window.tray.messageClicked.emit()
            self.assertTrue(window.isVisible())

    def test_missing_tray_minimize_keeps_web_reachable(self):
        with web_window() as window, patch.object(QSystemTrayIcon, 'isSystemTrayAvailable', return_value=False), \
                patch.object(window, '_set_action_status') as report:
            window.reveal()
            window.showMinimized()
            self.app.processEvents()
            self.assertTrue(window.isVisible())
            self.assertFalse(window.isMinimized())
            report.assert_called_once()
            window.controller.close.assert_not_called()

    def test_maximize_restore_and_modal_owner_use_existing_window(self):
        with web_window() as window:
            window.reveal()
            action = window_action(window)
            self.assertTrue(action('toggleMaximizeWindow')['ok'])
            self.assertTrue(window.isMaximized())
            self.assertTrue(action('toggleMaximizeWindow')['ok'])
            self.assertFalse(window.isMaximized())
            self.assertEqual(window.windowType(), Qt.WindowType.Tool)
            with patch.object(qt_app.QMessageBox, 'question', return_value=qt_app.QMessageBox.StandardButton.No) as question:
                window._confirm_restart_launcher()
                self.assertIs(question.call_args.args[0], window)

    def test_widgets_minimize_retains_native_behavior(self):
        window = qt_app.KuroQtLauncherWindow.__new__(qt_app.KuroQtLauncherWindow)
        QMainWindow.__init__(window)
        window._web_mode = False
        window.explicit_quitting = False
        try:
            with patch.object(window, 'close') as close:
                window.show()
                window.showMinimized()
                self.assertTrue(window.isVisible())
                self.assertTrue(window.isMinimized())
                self.assertEqual(window.windowType(), Qt.WindowType.Window)
                close.assert_not_called()
        finally:
            window.hide()
            window.deleteLater()

    def test_pending_minimize_does_not_hide_revealed_or_quitting_window(self):
        with web_window() as window, patch.object(window, 'close') as close:
            window.reveal()
            window.showMinimized()
            window.reveal()
            self.app.processEvents()
            close.assert_not_called()
            self.assertTrue(window.isVisible())
            window.showMinimized()
            window.explicit_quitting = True
            self.app.processEvents()
            close.assert_not_called()


class W8SourceGateTests(unittest.TestCase):
    def test_w8_qt_gate_versions_drift_without_claiming_pet_or_native_pass(self):
        task = ROOT / 'devtools/original-git-web-host-20261010'
        spec = importlib.util.spec_from_file_location('w8_gate_test', task / 'w8_qt_tray_gate.py')
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        result = gate.verify()
        self.assertEqual(result['status'], 'W8_QT_SOURCE_PIN_VERIFIED')
        self.assertEqual(result['petRepair'], 'BLOCKED_PERMISSION_DENIED')
        self.assertEqual(result['nativeAcceptance'], 'UNVERIFIED')
        self.assertFalse(result['productionAdoption'])
        with patch.dict(gate.EXPECTED_SOURCES, {'kuro_launcher/qt_app.py': '0' * 64}):
            with self.assertRaisesRegex(ValueError, 'W8 source drift'):
                gate.verify()
        with patch('kuro_launcher.qt_web_release.RELEASE_PIN', None):
            with self.assertRaisesRegex(ValueError, 'W8 source pin mismatch'):
                gate.verify()
        historical = gate.load_module('w8_old_gate_test', 'w7_window_chrome_gate.py')
        with self.assertRaisesRegex(ValueError, 'W7 source drift: kuro_launcher/qt_app.py'):
            historical.verify()


if __name__ == '__main__':
    unittest.main()
