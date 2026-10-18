"""W7 source/Qt offscreen evidence, never a Windows gesture acceptance claim."""
import ast
import importlib.util
from contextlib import ExitStack
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QMenuBar, QWidget
from kuro_launcher.qt_web_protocol import CONTRACT, RequestBroker, Rejected, WINDOW_EDGES, error, validate
from kuro_launcher.qt_web_adapter import QtOwnerAdapter
from web_candidate_fixtures import ChatFixture, controller_fixture

ROOT = Path(__file__).resolve().parents[1]


class W7BundleTests(unittest.TestCase):
    def test_new_source_gate_passes_and_refuses_source_or_pin_drift(self):
        task = ROOT/'devtools/original-git-web-host-20261010'
        spec = importlib.util.spec_from_file_location('w7_gate', task/'w7_window_chrome_gate.py')
        gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
        result = gate.verify()
        self.assertEqual(result['status'], 'W7_SOURCE_PIN_VERIFIED')
        self.assertEqual(result['nativeGestures'], 'UNVERIFIED')
        self.assertFalse(result['productionAdoption'])
        with patch.dict(gate.EXPECTED_SOURCES, {'kuro_launcher/qt_app.py': '0'*64}):
            with self.assertRaisesRegex(ValueError, 'W7 source drift'): gate.verify()
        with patch('kuro_launcher.qt_web_release.RELEASE_PIN', None):
            with self.assertRaisesRegex(ValueError, 'W7 source pin mismatch'): gate.verify()

    def test_w7_profile_requires_full_release_coverage_except_historical_w6_gate(self):
        task = ROOT/'devtools/original-git-web-host-20261010'
        spec = importlib.util.spec_from_file_location('w7_validator', task/'validate_candidate.py')
        validator = importlib.util.module_from_spec(spec); spec.loader.exec_module(validator)
        self.assertEqual(validator.WINDOW_CHROME_SUITES,
                         (validator.RELEASE_SUITES - {'qt_web_release_candidate'}) | {'qt_web_window_chrome'})
        self.assertNotIn('qt_web_window_chrome', validator.RELEASE_SUITES)
        commands = [(name, [], ROOT) for name in validator.WINDOW_CHROME_SUITES]
        selected = validator.select_commands(commands, 'w7-window-chrome', None)
        self.assertEqual({row[0] for row in selected}, validator.WINDOW_CHROME_SUITES)
        for only in ([], ['qt_web_window_chrome']):
            with self.assertRaises(ValueError): validator.select_commands(commands, 'w7-window-chrome', only)
        with self.assertRaises(ValueError): validator.select_commands(commands[1:], 'w7-window-chrome', None)

    def test_w7_pin_matches_current_builder_and_originals_without_reusing_w6_acceptance(self):
        from kuro_launcher.qt_web_release import RELEASE_PIN, VerifiedOwnerBundle
        task = ROOT/'devtools/original-git-web-host-20261010'
        spec = importlib.util.spec_from_file_location('w7_builder', task/'build_owner_bundle.py')
        builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
        lineage = builder.lineage()  # byte-compares all six ORIGINALS to Git
        self.assertEqual(RELEASE_PIN.fingerprint, '8ba8ea29313601f944f760b901410efb8fc92bc801199d3b0b72ba22b7fa9b14')
        self.assertEqual(RELEASE_PIN.fingerprint, builder.fingerprint(lineage))
        bundle = VerifiedOwnerBundle.load(ROOT/'assets/qt-owner'/RELEASE_PIN.fingerprint, RELEASE_PIN)
        self.assertIn(b"connect-src 'none'", bundle.assets['/work-panel.html'])
        self.assertEqual(len(builder.ORIGINALS), 6)
        spec = importlib.util.spec_from_file_location('w6_review', task/'w6_release_candidate.py')
        review = importlib.util.module_from_spec(spec); spec.loader.exec_module(review)
        from kuro_launcher.qt_web_release import OwnerBundlePin
        old = OwnerBundlePin(**review.PIN_VALUES)
        VerifiedOwnerBundle.load(ROOT/'assets/qt-owner'/old.fingerprint, old)
        self.assertNotEqual(old, RELEASE_PIN)
        with self.assertRaisesRegex(ValueError, 'release source drift'):
            review.release_preimage()


def window_action(owner):
    # Execute the actual nested Port method without constructing Chromium.
    tree = ast.parse((ROOT / 'kuro_launcher/qt_web_host.py').read_text(encoding='utf-8'))
    host = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_create_host')
    port = next(n for n in host.body if isinstance(n, ast.ClassDef) and n.name == 'Port')
    method = next(n for n in port.body if isinstance(n, ast.FunctionDef) and n.name == 'window_action')
    scope = dict(__package__='kuro_launcher', owner=owner, Qt=Qt, error=error)
    exec(compile(ast.Module(body=[method], type_ignores=[]), 'actual-w7-port', 'exec'), scope)
    driver = SimpleNamespace(broker=SimpleNamespace(closed=False))
    return lambda name, payload=None: scope['window_action'](driver, name, payload)


class GestureProtocolTests(unittest.TestCase):
    def test_edges_are_exact_and_payloads_bounded(self):
        for edge in WINDOW_EDGES:
            self.assertFalse(validate('startWindowResize', {'edge': edge}))
        for payload in ({}, {'edge': 'left-right'}, {'edge': 'top-bottom'}, {'edge': []}, {'edge': 3},
                        {'edge': 'left', 'confirmed': True}, {'edge': 'left', 'windowId': 1}):
            with self.assertRaises(Rejected): validate('startWindowResize', payload)
        for method in ('startWindowMove', 'getWindowState'):
            self.assertFalse(validate(method, {}))
            with self.assertRaises(Rejected): validate(method, {'confirmed': True})

    def test_existing_identity_and_duplicate_fences_apply_to_gestures(self):
        action = Mock(return_value={'ok': True})
        adapter = QtOwnerAdapter(controller_fixture(), ChatFixture(), lambda w, d: d(w()), window_action=action)
        replies = []
        broker = RequestBroker(adapter, Mock(side_effect=AssertionError('No service authority')), replies.append)
        request = dict(contract=CONTRACT, id='resize', expected=adapter.identity(),
                       method='startWindowResize', payload={'edge': 'top-left'})
        broker.submit(json.dumps(request)); broker.submit(json.dumps(request))
        action.assert_called_once_with('startWindowResize', {'edge': 'top-left'})
        self.assertEqual(replies[-1]['result']['error'], 'duplicate_request_no_replay')
        request['id'] = 'stale'; request['expected']['revision'] += 1
        broker.submit(json.dumps(request))
        self.assertEqual(replies[-1]['result']['error'], 'stale_context')
        self.assertEqual(action.call_count, 1)
        broker.close()

    def test_actual_port_uses_same_qwindow_and_maps_all_eight_edges(self):
        owner = Mock()
        owner.isVisible.return_value = True
        owner.isMaximized.return_value = owner.isMinimized.return_value = owner.isFullScreen.return_value = False
        handle = owner.windowHandle.return_value
        action = window_action(owner)
        edges = {'top': Qt.Edge.TopEdge, 'bottom': Qt.Edge.BottomEdge, 'left': Qt.Edge.LeftEdge, 'right': Qt.Edge.RightEdge}
        with patch.object(QApplication, 'mouseButtons', return_value=Qt.MouseButton.LeftButton), patch.object(QApplication, 'activeModalWidget', return_value=None):
            self.assertTrue(action('startWindowMove')['ok'])
            handle.startSystemMove.assert_called_once_with()
            for edge in WINDOW_EDGES:
                self.assertTrue(action('startWindowResize', {'edge': edge})['ok'])
                flags = Qt.Edge(0)
                for part in edge.split('-'): flags |= edges[part]
                handle.startSystemResize.assert_called_with(flags)
            count = handle.startSystemResize.call_count
            owner.isMaximized.return_value = True
            self.assertEqual(action('startWindowResize', {'edge': 'right'})['error'], 'window_maximized')
            self.assertEqual(handle.startSystemResize.call_count, count)
            owner.isMaximized.return_value = False
            handle.startSystemMove.return_value = False
            self.assertEqual(action('startWindowMove')['error'], 'native_window_gesture_unsupported')
            self.assertEqual(action('startWindowResize', {'edge': 'top-bottom'})['error'], 'invalid_window_edge')
        with patch.object(QApplication, 'mouseButtons', return_value=Qt.MouseButton.NoButton):
            self.assertEqual(action('startWindowMove')['error'], 'window_gesture_unavailable')
        for method, called in [('closeWindow', 'close'), ('minimizeWindow', 'showMinimized'), ('toggleMaximizeWindow', 'showMaximized')]:
            self.assertTrue(action(method)['ok']); getattr(owner, called).assert_called_once()
        owner.isMaximized.return_value = True
        action('toggleMaximizeWindow'); owner.showNormal.assert_called_once()
        self.assertEqual(action('unknown')['error'], 'unsupported_method')


class ChromeWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def test_web_constructor_is_frameless_without_menubar_and_retains_lifecycle(self):
        from kuro_launcher import qt_app, qt_web_host
        controller = Mock()
        def surface(owner, bundle):
            host = QWidget(owner); host.owner_port = Mock(); host.shutdown_candidate = Mock()
            owner.work_web_candidate = host
            return host
        with ExitStack() as stack:
            stack.enter_context(patch.object(qt_app, 'QtLauncherController', return_value=controller))
            stack.enter_context(patch.object(qt_web_host, 'create_existing_window_host', side_effect=surface))
            for name in ('_start_notification_delivery', '_schedule_startup_auto_start'):
                stack.enter_context(patch.object(qt_app.KuroQtLauncherWindow, name))
            stack.enter_context(patch.object(qt_app, 'QSettings', side_effect=AssertionError('Private settings')))
            stack.enter_context(patch.object(qt_app.QSystemTrayIcon, 'show'))
            window = qt_app.KuroQtLauncherWindow(SimpleNamespace(), web_bundle=object())
            try:
                self.assertTrue(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
                self.assertEqual(window.findChildren(QMenuBar), [])
                self.assertIs(window.controller, controller)
                self.assertIs(window.centralWidget(), window.work_web_candidate)
                actions = {a.text(): a for a in window.tray.contextMenu().actions()}
                self.assertEqual(set(actions), {'Show Kuro', 'Restart Kuro', 'Quit Kuro'})
                with patch.object(window, '_restart_launcher') as restart, patch.object(qt_app.QMessageBox, 'question', return_value=qt_app.QMessageBox.StandardButton.No):
                    actions['Restart Kuro'].trigger(); restart.assert_not_called()
                with patch.object(window, '_restart_launcher') as restart, patch.object(qt_app.QMessageBox, 'question', return_value=qt_app.QMessageBox.StandardButton.Yes):
                    actions['Restart Kuro'].trigger(); restart.assert_called_once()
                window.show()
                with patch.object(window.tray, 'isVisible', return_value=True), patch.object(qt_app.QSystemTrayIcon, 'isSystemTrayAvailable', return_value=True):
                    window.close(); self.assertFalse(window.isVisible())
                actions['Show Kuro'].trigger(); self.assertTrue(window.isVisible())
                controller.close.assert_not_called()
                with patch.object(self.app, 'quit') as quit_app:
                    actions['Quit Kuro'].trigger(); quit_app.assert_called_once()
                window.cleanup()
                controller.close.assert_called_once()
                window.work_web_candidate.shutdown_candidate.assert_called_once()
            finally:
                window.cleanup(); window.deleteLater()

    def test_widgets_tray_path_retains_native_frame_and_kuro_menu(self):
        from kuro_launcher.qt_app import KuroQtLauncherWindow
        # Existing Widgets constructor coverage lives in the Qt UI regressions;
        # isolate its actual shared tray method without opening private state.
        window = QMainWindow()
        window._web_mode = False
        for name in ('reveal', '_confirm_restart_launcher', 'quit_application', '_tray_activated'):
            setattr(window, name, Mock())
        with patch('kuro_launcher.qt_app.QSystemTrayIcon.show'):
            KuroQtLauncherWindow._create_tray(window)
        self.assertFalse(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
        menu_actions = window.menuBar().actions()
        self.assertEqual([a.text() for a in menu_actions], ['Kuro'])
        menu = menu_actions[0].menu()
        self.assertEqual([a.text() for a in menu.actions()], ['Restart Kuro', 'Quit Kuro'])
        window.tray.hide(); window.deleteLater()


if __name__ == '__main__': unittest.main()
