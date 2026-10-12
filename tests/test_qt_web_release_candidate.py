"""W6 release review regressions; no renderer, formal main, or private state."""
from contextlib import ExitStack
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT/'devtools/original-git-web-host-20261010'


def load(name):
    spec = importlib.util.spec_from_file_location(name, TASK/(name+'.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class ReleaseReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = load('w6_release_candidate')

    def round(self):
        return [self.review.read(self.review.RECEIPTS/'first'/name)
                for name in ['NativeResult.json', 'SecurityEvidence.json', 'FormalPreflight.json']]

    def test_exact_raw_pair_source_and_security(self):
        result = self.review.verify_receipts()
        self.assertEqual(result['status'], 'AUTOMATED_NATIVE_PASS')
        self.assertFalse(result['productionAdoption'])
        self.assertEqual(result['humanApproval'], 'UNVERIFIED')

    def test_review_calls_canonical_security_evaluator(self):
        probe = load('w6_security_probe')
        evaluator = Mock(wraps=probe.evaluate_security)
        # No alias named evaluate: the previous call fails with AttributeError.
        with patch.object(self.review, 'module', return_value=SimpleNamespace(evaluate_security=evaluator)):
            native, security, preflight = self.round()
            self.review.verify_round(native, security, preflight)
        evaluator.assert_called_once_with(security)

    def test_pass_string_cannot_replace_coverage_source_or_preflight(self):
        for case in ['missing', 'failed', 'duplicate', 'source', 'source-key', 'dll', 'dll-key', 'module-key', 'module-origin', 'package-key', 'override', 'navigation']:
            with self.subTest(case=case):
                n, s, p = self.round()
                if case == 'missing': n['checks'].pop()
                if case == 'failed': n['checks'][0]['pass'] = False
                if case == 'duplicate': n['checks'][0] = copy.deepcopy(n['checks'][1])
                if case == 'source': n['sourceSha256']['kuro_launcher/qt_app.py'] = '0'*64
                if case == 'source-key':
                    del n['sourceSha256']['kuro_launcher/qt_app.py']
                    n['sourceSha256']['requirements-qt.txt'] = self.review.sha(ROOT/'requirements-qt.txt')
                if case == 'dll': p['loadedQtLibraries']['Qt6Core.dll']['origin'] = str(ROOT/'wrong/Qt6Core.dll')
                if case == 'dll-key': p['loadedQtLibraries']['unrelated'] = p['loadedQtLibraries'].pop('Qt6Core.dll')
                if case == 'module-key': p['modules']['unrelated'] = p['modules'].pop('PySide6.QtWebEngineWidgets')
                if case == 'module-origin': p['modules']['PySide6.QtWebEngineWidgets']['origin'] = p['modules']['PySide6.QtWidgets']['origin']
                if case == 'package-key': p['packages']['unrelated'] = p['packages'].pop('PySide6-Addons')
                if case == 'override': p['overrideNames'] = ['QTWEBENGINE_DISABLE_SANDBOX']
                if case == 'navigation':
                    row = next(r for r in n['checks'] if r['name'] == 'navigation-denied')
                    row.update(deniedCallbacks=0, probeHitsAfter=2)
                with self.assertRaises(ValueError): self.review.verify_round(n, s, p)

    def test_forged_security_pass_cannot_hide_side_effect_or_missing_samples(self):
        for case in ['network', 'popup', 'storage', 'errors', 'split']:
            with self.subTest(case=case):
                n, s, p = self.round()
                if case == 'network': s['probeHitsAfter'] += 1
                if case == 'popup': s['popup']['newObjects'] = 1
                if case == 'storage': s['storage']['nativeReload']['after']['absent'] = False
                if case == 'errors': s['javascriptErrorSamples'].pop('nativeReload')
                if case == 'split': s['legacyPredicates']['popup'] = True
                else: n['security'] = copy.deepcopy(s)
                with self.assertRaises(ValueError): self.review.verify_round(n, s, p)

    def test_formal_source_is_exact_reviewed_proposal(self):
        from kuro_launcher.qt_web_release import RELEASE_PIN, OwnerBundlePin
        source = self.review.proposed_source(OwnerBundlePin(**self.review.PIN_VALUES))
        self.assertLess(source.index('class OwnerBundlePin'), source.index('RELEASE_PIN = OwnerBundlePin('))
        self.assertEqual(RELEASE_PIN, OwnerBundlePin(**self.review.PIN_VALUES))
        self.assertEqual(source.encode(), (ROOT/'kuro_launcher/qt_web_release.py').read_bytes())
        self.assertEqual(self.review.sha(ROOT/'kuro_launcher/qt_web_release.py'), self.review.ADOPTED_SHA)

    def test_full_pin_validation_emits_exact_reversible_reviewed_patch(self):
        before = (ROOT/'kuro_launcher/qt_web_release.py').read_bytes()
        with tempfile.TemporaryDirectory(prefix='pin-regression-', dir=TASK/'.runtime') as folder:
            output = Path(folder)/'evidence'
            process = subprocess.run([sys.executable, '-I', '-B', str(TASK/'w6_release_candidate.py'),
                '--output', str(output)], cwd=ROOT, capture_output=True, timeout=30)
            self.assertEqual(process.returncode, 0, process.stderr)
            candidate = json.loads((output/'ReleaseCandidate.json').read_text())
            self.assertEqual(len(candidate['negativeRejected']), 8)
            self.assertEqual(candidate['status'], 'SOURCE_PIN_ACTIVE_VALIDATION_PASS')
            self.assertTrue(candidate['sourceCutover'])
            self.assertFalse(candidate['productionAdoption'])
            patch_path = output/'ReleasePin.proposed.patch'
            self.assertNotIn(b'\r\n', patch_path.read_bytes())
            check = subprocess.run(['git', 'apply', '--reverse', '--check', '--', str(patch_path)],
                cwd=ROOT, capture_output=True, timeout=15)
            self.assertEqual(check.returncode, 0, check.stderr)
        self.assertEqual((ROOT/'kuro_launcher/qt_web_release.py').read_bytes(), before)

    def test_unreviewed_source_delta_and_forged_native_pin_are_rejected(self):
        with patch.object(self.review, 'ADOPTED_SHA', '0'*64):
            with self.assertRaisesRegex(ValueError, 'source drift'):
                self.review.release_preimage()
        n, s, p = self.round()
        n['sourceSha256'][self.review.RELEASE_SOURCE] = self.review.ADOPTED_SHA
        with self.assertRaisesRegex(ValueError, 'Native release preimage'):
            self.review.verify_round(n, s, p)

    def test_native_receipt_remains_pre_cutover_evidence(self):
        result = self.review.verify_receipts()
        for row in result['rounds']:
            self.assertEqual(row['reviewedSourceDelta'], {
                self.review.RELEASE_SOURCE: dict(native=self.review.PREIMAGE_SHA, current=self.review.ADOPTED_SHA)})

    def test_release_profile_cannot_silently_skip_security_or_existing_window(self):
        validator = load('validate_candidate')
        commands = [(name, [], ROOT) for name in validator.RELEASE_SUITES]
        selected = validator.select_commands(commands, 'release-candidate', None)
        self.assertEqual({r[0] for r in selected}, validator.RELEASE_SUITES)
        for names in [[], ['typo'], ['qt_web_security']]:
            with self.assertRaises(ValueError): validator.select_commands(commands, 'release-candidate', names)
        for names in [[], ['typo']]:
            with self.assertRaises(ValueError): validator.select_commands(commands, 'default', names)
        with self.assertRaises(ValueError): validator.select_commands(commands[1:], 'release-candidate', None)


class ExistingWebConstructorTests(unittest.TestCase):
    def test_existing_constructor_web_branch_and_cleanup_without_renderer(self):
        # Exercise the actual window constructor. Only the WebEngine surface is
        # inert: this proves source wiring, never native rendering or acceptance.
        from PySide6.QtWidgets import QApplication, QWidget
        from kuro_launcher import qt_app, qt_web_host
        from kuro_launcher.qt_web_release import OwnerBundlePin, VerifiedOwnerBundle
        from web_existing_window_fixtures import ExistingWindowFixture
        app = QApplication.instance() or QApplication([])
        review = load('w6_release_candidate')
        pin = OwnerBundlePin(**review.PIN_VALUES)
        bundle = VerifiedOwnerBundle.load(ROOT/'assets/qt-owner'/pin.fingerprint, pin)
        with tempfile.TemporaryDirectory(prefix='.validation-w6-constructor-', dir=ROOT) as folder:
            fixture = ExistingWindowFixture(Path(folder)/'state')
            window = None
            port = Mock()
            def surface(owner, verified):
                self.assertIs(verified, bundle)
                host = QWidget(owner)
                host.owner_port = port
                host.shutdown_candidate = Mock()
                owner.work_web_candidate = host
                return host
            try:
                fixture.start()
                with ExitStack() as patches:
                    controller = patches.enter_context(patch.object(qt_app, 'QtLauncherController', side_effect=fixture.make_controller))
                    host_factory = patches.enter_context(patch.object(qt_web_host, 'create_existing_window_host', side_effect=surface))
                    patches.enter_context(patch.object(qt_app.QSystemTrayIcon, 'show'))
                    patches.enter_context(patch.object(qt_app, 'QSettings', side_effect=AssertionError('Private QSettings')))
                    for method in ['_build_ui', '_wire_signals', '_refresh_workspace_data', '_refresh_profile_controls']:
                        patches.enter_context(patch.object(qt_app.KuroQtLauncherWindow, method, side_effect=AssertionError('Widgets branch')))
                    window = qt_app.KuroQtLauncherWindow(fixture.cfg, web_bundle=bundle)
                    self.assertIs(window.controller, fixture.controller)
                    self.assertIs(window.centralWidget(), window.work_web_candidate)
                    controller.assert_called_once(); host_factory.assert_called_once()
                    for attribute in ['ui_preferences', 'work_companion', 'today_page', 'schedule_page', 'settings_surface']:
                        self.assertFalse(hasattr(window, attribute), attribute)
                    self.assertFalse(window.startup_auto_start_fired)
                    window.status_timer.timeout.emit()
                    port.refresh_status.assert_called_once(); port.refresh_data.assert_called_once()
                    window.task_finished.emit('synthetic', {})
                    self.assertEqual(port.refresh_status.call_count, 2)
                    window.cleanup(); window.cleanup()
                    window.work_web_candidate.shutdown_candidate.assert_called_once()
                    self.assertEqual(fixture.calls.count('close'), 1)
                    self.assertFalse(window.status_timer.isActive())
                    self.assertFalse(window.runtime_timer.isActive())
                    self.assertEqual(fixture.ws.connections, 0)
            finally:
                if window is not None:
                    window.cleanup(); window.deleteLater()
                fixture.close()


if __name__ == '__main__':
    unittest.main()
