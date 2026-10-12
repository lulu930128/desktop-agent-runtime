"""Independent offline diagnostics tests; never count as native W1 evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import w1_smoke
import w1_preflight
import contextlib
import io

from capture_parity import record_comparison, finish_capture, stable_browser_geometry
from summarize_w1 import HERE, summarize
from w1_geometry_diagnostics import fractional_diagnosis, measurement_stable, viewport_diagnosis
from w1_smoke import ValidationError, validate_metadata
from test_w1_smoke import metadata


class ViewportTests(unittest.TestCase):
    def test_711_is_failure_and_capacity_comes_from_measured_frame(self):
        sample = {"frameGeometry": {"width": 1296, "height": 740},
                  "widgetSize": {"width": 1280, "height": 711},
                  "screen": {"availableGeometry": {"width": 1400, "height": 740}}}
        result = viewport_diagnosis((1280, 720), {"width": 1280, "height": 711}, sample)
        self.assertFalse(result["exact"])
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["requestedDecoratedWindowFitsAvailableArea"])
        m = metadata(dpr=2)
        m["geometry"]["viewport"]["height"] = 711
        with self.assertRaises(ValidationError):
            validate_metadata(m, 1280, 720, "chat", 2)

    def test_no_screen_evidence_cannot_diagnose_clamp(self):
        result = viewport_diagnosis((1280, 720), {"width": 1280, "height": 711}, {})
        self.assertIsNone(result["requestedDecoratedWindowFitsAvailableArea"])
        self.assertFalse(result["exact"])

    def test_exact_dimensions_do_not_assert_visual_acceptance(self):
        result = viewport_diagnosis((1280, 720), {"width": 1280, "height": 720}, {})
        self.assertTrue(result["exact"])
        self.assertNotIn("gateW1", result)

    def test_history_requires_visible_drawer(self):
        m = metadata("history")
        with self.assertRaises(ValidationError):
            validate_metadata(m, 1280, 720, "history")
        m["geometry"]["geometry"][".history-drawer"] = {"width": 320, "height": 550, "display": "grid"}
        with self.assertRaisesRegex(ValidationError, "opened drawer"):
            validate_metadata(m, 1280, 720, "history")
        m["geometry"]["history"] = {"opened": True, "animationsSettled": True, "visibleIntersection": {"width":320,"height":550}}
        self.assertEqual(validate_metadata(m, 1280, 720, "history"), 1.25)

    def test_stable_geometry_alone_cannot_accept_running_or_offscreen_drawer(self):
        current = {"fontStatus":"loaded", "history":{"opened":True,"animationsSettled":False}}
        self.assertFalse(measurement_stable(copy.deepcopy(current), current, 'history'))
        current['history'].update(opened=False, animationsSettled=True)
        self.assertFalse(measurement_stable(copy.deepcopy(current), current, 'history'))
        current['history']['opened'] = True
        self.assertTrue(measurement_stable(copy.deepcopy(current), current, 'history'))
        previous = copy.deepcopy(current); previous['geometry'] = {'drawer':{'x':1}}
        current['geometry'] = {'drawer':{'x':2}}
        self.assertFalse(measurement_stable(previous, current, 'history'))


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        parent = HERE / ".runtime" / "convergence-tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def test_quantization_signature_never_erases_small_or_large_drift(self):
        left = {"viewport": {"devicePixelRatio": 1.25}, "geometry": {"stage": {"y": 103.0}},
                "deepGeometry": {"kicker": [{"rect": {"height": 12}}]}}
        right = copy.deepcopy(left)
        right["geometry"]["stage"]["y"] = 102.80000305175781
        right["deepGeometry"]["kicker"][0]["rect"]["height"] = 15
        saved = copy.deepcopy((left, right))
        diagnosis = fractional_diagnosis(left, right)
        self.assertFalse(diagnosis["strictGeometryEqual"])
        self.assertFalse(diagnosis["strictDeepEqual"])
        self.assertEqual((left, right), saved)
        stage = next(r for r in diagnosis["rows"] if r["path"] == "geometry.stage.y")
        self.assertLess(stage["qtDevice64Residual"], 0.001)
        self.assertGreater(stage["qtCss64Residual"], 0.1)
        receipt = {"results": []}
        record_comparison(self.directory, receipt, {"view": "chat", "viewport": [1280,720],
                          "tokensEqual": True, "geometryEqual": diagnosis["strictGeometryEqual"]}, True)
        finish_capture(receipt)
        self.assertEqual(receipt["gateW1"], "FAIL")

    def test_deep_only_text_change_is_strict_failure(self):
        receipt = {"results": []}
        with self.assertRaises(ValidationError):
            record_comparison(self.directory, receipt, {"view": "today", "viewport": [1280,720],
                              "tokensEqual": True, "geometryEqual": True, "deepGeometryEqual": False})
        self.assertEqual(receipt["gateW1"], "FAIL")

    def test_summary_preserves_case_sensitive_keys_bom_and_failed_first_pair(self):
        receipt = self.directory / "ParityResult.json"
        receipt.write_text(json.dumps({"captureStatus":"FAIL", "gateW1":"FAIL", "results":[],
                                      "Font":"one", "font":"two"}), encoding="utf-8-sig")
        baseline = {"viewport":{"width":1280,"height":720,"devicePixelRatio":2}, "geometry":{}}
        qt = copy.deepcopy(baseline); qt["viewport"]["height"] = 711
        (self.directory / "chat-1280x720-baseline.json").write_text(json.dumps(baseline), encoding="utf-8")
        (self.directory / "chat-1280x720-qt.json").write_text(json.dumps({"geometry":qt,"status":"FAIL"}), encoding="utf-8")
        preimage = receipt.read_bytes()
        result = summarize(receipt)
        self.assertEqual(result["gateW1"], "FAIL")
        self.assertEqual(len(result["pairs"]), 1)
        self.assertFalse(result["pairs"][0]["fractional"]["viewportEqual"])
        self.assertEqual(receipt.read_bytes(), preimage)

    def test_summary_missing_receipt_and_outside_scope(self):
        self.assertEqual(summarize(self.directory / "absent.json")["status"], "UNVERIFIED")
        with self.assertRaises(ValueError):
            summarize(HERE / "SourceVerification.json")

    def test_nonfinite_dpr_does_not_manufacture_grid_alignment(self):
        result = fractional_diagnosis({"geometry":{"y":1}}, {"geometry":{"y":2},"viewport":{"devicePixelRatio":float('nan')}})
        self.assertNotIn("qtDevice64Residual", result["rows"][0])

    def test_execution_manifest_covers_entries_and_rejects_missing_helper(self):
        required = {'typography.js', 'w1_geometry_diagnostics.py', 'capture_parity.py',
                    'Invoke-W1WindowsRelay.ps1', 'summarize_w1.py', 'w1_smoke.py', 'w1_preflight.py',
                    'w1_import_probe.py', 'qt_preview_host.py', 'preview_protocol.py', 'geometry.js'}
        self.assertEqual(set(w1_smoke.execution_fingerprint()), required)
        self.assertTrue(required <= set(w1_smoke.fingerprint()))
        for name in required:
            (self.directory / name).write_text('fixture', encoding='utf-8')
        with patch.object(w1_smoke, 'HERE', self.directory):
            before = w1_smoke.fingerprint()
            # Old smoke binding must reject changes before opening captures.
            receipt = self.directory / 'SmokeResult.json'
            receipt.write_text(json.dumps({'smokeStatus':'PASS','sourceFingerprint':before}), encoding='utf-8')
            for name in required:
                with self.subTest(name=name):
                    (self.directory / name).write_text('changed helper', encoding='utf-8')
                    self.assertNotEqual(before, w1_smoke.fingerprint())
                    with self.assertRaisesRegex(w1_smoke.EvidenceError, 'source/build changed'):
                        w1_smoke.read_smoke(receipt)
                    (self.directory / name).write_text('fixture', encoding='utf-8')
            (self.directory / 'typography.js').unlink()
            with self.assertRaises(FileNotFoundError):
                w1_smoke.execution_fingerprint()

    def test_preflight_rejects_execution_manifest_drift_even_inside_task(self):
        before, after = self.directory / 'before.json', self.directory / 'after.json'
        with patch('sys.argv', ['w1_preflight.py', str(before)]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(w1_preflight.main(), 0)
        manifest = w1_smoke.execution_fingerprint()
        manifest['capture_parity.py'] = '0'*64
        with patch('sys.argv', ['w1_preflight.py', str(after), '--compare', str(before)]), \
             patch.object(w1_preflight, 'execution_fingerprint', return_value=manifest), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(w1_preflight.main(), 1)
        result = json.loads(after.read_text(encoding='utf-8'))
        self.assertFalse(result['w1ExecutionUnchanged'])
        self.assertTrue(result['indexUnchanged'])
        self.assertEqual(result['outsideTaskChanges'], [])

    def test_browser_rejects_stable_offscreen_drawer_and_retains_raw_attempts(self):
        raw = {'fontStatus':'loaded', 'geometry':{'.history-drawer':{'x':1500}},
               'history':{'opened':False, 'animationsSettled':True}}
        class Page:
            def evaluate(self, script): return json.dumps(raw)
            def wait_for_timeout(self, duration): pass
        receipt = self.directory / 'stability.json'
        with self.assertRaises(ValidationError):
            stable_browser_geometry(Page(), 'history', receipt)
        result = json.loads(receipt.read_text(encoding='utf-8'))
        self.assertFalse(result['stable'])
        self.assertEqual(len(result['measurements']),8)
        self.assertEqual(result['measurements'][-1]['geometry']['.history-drawer']['x'],1500)


if __name__ == "__main__":
    unittest.main()
