"""W10 current offscreen evidence only: no native taskbar or production acceptance."""
from contextlib import contextmanager, ExitStack
import ast
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QImageReader
from PySide6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QWidget

from kuro_launcher import qt_app, qt_branding, qt_web_host
from test_qt_web_window_chrome import window_action
from kuro_launcher.qt_web_release import VerifiedOwnerBundle, RELEASE_PIN

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
        stack.enter_context(patch.object(QSystemTrayIcon, 'show'))
        window = qt_app.KuroQtLauncherWindow(SimpleNamespace(), web_bundle=VerifiedOwnerBundle.load(ROOT / 'assets/qt-owner' / RELEASE_PIN.fingerprint, RELEASE_PIN))
        window.status_timer.stop()
        window.runtime_timer.stop()
        try:
            yield window
        finally:
            window.cleanup()
            window.deleteLater()


class W10IconTrayTests(unittest.TestCase):
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

    def test_invalid_or_missing_bundle_cannot_construct_native_owner_or_controller(self):
        with patch.object(qt_app, 'QtLauncherController') as controller, \
                patch.object(QMainWindow, '__init__') as native:
            for value in (None, object(), {}, 'file:///preview.html'):
                with self.subTest(value=type(value).__name__), self.assertRaises(TypeError):
                    qt_app.KuroQtLauncherWindow(SimpleNamespace(), web_bundle=value)
            with self.assertRaises(TypeError):
                qt_app.KuroQtLauncherWindow(SimpleNamespace())
        native.assert_not_called()
        controller.assert_not_called()

    def test_timers_and_single_client_retain_owner_routes(self):
        with web_window() as window:
            self.assertEqual(window.status_timer.interval(), 2500)
            self.assertEqual(window.runtime_timer.interval(), 10000)
            port = window.work_web_candidate.owner_port
            with patch.object(window.chat_client, 'expire_history_request'):
                window.status_timer.timeout.emit()
            port.refresh_status.assert_called_once()
            port.refresh_data.assert_called_once()
            window.runtime_timer.timeout.emit()
            work, done = port.run_worker.call_args.args
            done(work())
            window.controller.reconcile_runtime.assert_called_once()
            self.assertEqual(window._lifecycle_tasks, set())
            self.assertEqual(len(window.findChildren(qt_app.QtRuntimeChatClient)), 1)
            self.assertEqual(len(window.findChildren(QSystemTrayIcon)), 1)

    def test_auto_start_schedules_once_and_single_delivery_uses_same_owners(self):
        schedule = qt_app.KuroQtLauncherWindow._schedule_startup_auto_start
        start_delivery = qt_app.KuroQtLauncherWindow._start_notification_delivery
        with web_window() as window:
            window.cfg.startup_auto_start = True
            with patch.object(qt_app.QTimer, 'singleShot') as timer:
                schedule(window)
                schedule(window)
            timer.assert_called_once_with(900, window._run_startup_auto_start)
            with patch.object(qt_app, 'QtScheduleDelivery') as delivery:
                start_delivery(window)
            delivery.assert_called_once_with(window.controller, window.tray, window._append_log, window)
            delivery.return_value.start.assert_called_once()
            window.cleanup()
            delivery.return_value.stop.assert_called_once()
            self.assertFalse(window.status_timer.isActive())
            self.assertFalse(window.runtime_timer.isActive())

    def test_startup_profile_offline_and_busy_reconcile_use_existing_worker(self):
        with web_window() as window:
            window.controller.selected_character.return_value = SimpleNamespace(conf_name='SYNTHETIC')
            window.controller.selected_project.return_value = SimpleNamespace(display_name='SYNTHETIC')
            port = window.work_web_candidate.owner_port
            window._run_startup_auto_start()
            self.assertEqual(window._lifecycle_tasks, {'start-profile'})
            window._run_task('runtime-reconcile', window.controller.reconcile_runtime)
            port.run_worker.assert_called_once()
            work, done = port.run_worker.call_args.args
            done(work())
            window.controller.start_profile.assert_called_once_with()
            window.controller.reconcile_runtime.assert_not_called()
            self.assertEqual(window._lifecycle_tasks, set())
            window.controller.selected_character.return_value = None
            with patch.object(window, 'reveal') as reveal:
                window._run_startup_auto_start()
            reveal.assert_called_once()
            self.assertEqual(port.run_worker.call_count, 1)

    def test_auto_connect_only_single_primary_and_shutdown_revokes_callbacks(self):
        with web_window() as window:
            window.cfg.llm_host, window.cfg.llm_port = '127.0.0.1', 1
            with patch.object(window.chat_client, 'connect_to') as connect:
                window._apply_lifecycle_status(SimpleNamespace(llm=False))
                connect.assert_not_called()
                window._apply_lifecycle_status(SimpleNamespace(llm=True))
                connect.assert_called_once_with('ws://127.0.0.1:1/client-ws?client_role=qt-primary')
                window.chat_auto_connect_paused = True
                window._apply_lifecycle_status(SimpleNamespace(llm=True))
                self.assertEqual(connect.call_count, 1)
            port = window.work_web_candidate.owner_port
            window._run_web_task('synthetic', lambda: {'ok': True})
            work, done = port.run_worker.call_args.args
            window.cleanup()
            with patch.object(window, 'refresh_status') as refresh:
                done(work())
            refresh.assert_not_called()
            window.controller.close.assert_called_once()
            window.work_web_candidate.shutdown_candidate.assert_called_once()


class W10SourceTests(unittest.TestCase):
    def test_late_scheme_registration_is_rejected(self):
        code = """from PySide6.QtCore import QCoreApplication
from kuro_launcher.qt_web_host import register_candidate_scheme
app = QCoreApplication([])
try:
 register_candidate_scheme()
except RuntimeError as exc:
 assert 'before QApplication' in str(exc)
else:
 raise AssertionError('Late scheme registration accepted')
"""
        process = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT,
                                 capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_current_signed_bundle_lineage_and_every_asset_reject_tampering(self):
        task = ROOT / 'devtools/original-git-web-host-20261010'
        spec = importlib.util.spec_from_file_location('w10_builder', task / 'build_owner_bundle.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        built = builder.build(verify_only=True)
        self.assertEqual(built['fingerprint'], RELEASE_PIN.fingerprint)
        self.assertEqual(built['manifestSha256'], RELEASE_PIN.manifest_sha256)
        self.assertEqual(len(builder.ORIGINALS), 6)
        bundle = VerifiedOwnerBundle.load(built['directory'], RELEASE_PIN)
        targets = [p.lstrip('/') for p in bundle.assets] + ['candidate-manifest.json', 'owner-build.json', 'extra.js']
        for target in targets:
            with self.subTest(target=target), tempfile.TemporaryDirectory(dir=ROOT / '.tmp') as folder:
                copied = Path(folder) / RELEASE_PIN.fingerprint
                shutil.copytree(built['directory'], copied)
                path = copied / target
                if target == 'owner-build.json':
                    record = json.loads(path.read_text(encoding='utf-8'))
                    record['lineage']['originalCommit'] = 'forged'
                    path.write_text(json.dumps(record), encoding='utf-8')
                else:
                    path.write_bytes((path.read_bytes() if path.exists() else b'') + b'tampered')
                with self.assertRaises(ValueError):
                    VerifiedOwnerBundle.load(copied, RELEASE_PIN)

    def test_retired_modules_and_observers_are_absent_from_current_source(self):
        for name in ('qt_work_companion_view', 'qt_work_companion_theme', 'qt_core_pages'):
            self.assertFalse((ROOT / 'kuro_launcher' / (name + '.py')).exists())
        source = (ROOT / 'kuro_launcher/qt_app.py').read_text(encoding='utf-8')
        for retired in ('_web_mode', 'APP_STYLE', 'QSettings', 'WorkCompanionView',
                        'TodayPage', 'SchedulePage', '_build_ui', '_on_chat_protocol_message',
                        'threading.Thread', 'history_records_by_uid'):
            self.assertNotIn(retired, source)
        tree = ast.parse(source)
        for name in ('QtLauncherController', 'QtRuntimeChatClient', 'QSystemTrayIcon', 'QtScheduleDelivery'):
            self.assertEqual(sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == name for n in ast.walk(tree)), 1, name)
        host = ast.parse((ROOT / 'kuro_launcher/qt_web_host.py').read_text(encoding='utf-8'))
        for name in ('QWebEngineView', 'QWebChannel'):
            self.assertEqual(sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == name for n in ast.walk(host)), 1, name)

    def test_none_pin_fails_before_scheme_registration(self):
        from kuro_launcher import qt_web_release
        with patch.object(qt_web_release, 'RELEASE_PIN', None), \
                patch.object(qt_web_host, 'register_candidate_scheme') as register:
            with self.assertRaisesRegex(TypeError, 'pin required'):
                qt_web_release.prepare_owner_presentation(ROOT)
        register.assert_not_called()

    def test_registered_scheme_remains_before_application_construction(self):
        source = (ROOT / 'launcher_qt.py').read_text(encoding='utf-8')
        self.assertLess(source.index('web_bundle = prepare_owner_presentation(BASE_DIR)'),
                        source.index('app = QApplication(sys.argv)'))
        self.assertIn('web_bundle=web_bundle', source)




if __name__ == '__main__':
    unittest.main()
