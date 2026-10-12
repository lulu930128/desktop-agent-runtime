"""Offline tests: collection never converts observed drift into acceptance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from capture_parity import HERE, ValidationError, finish_capture, record_comparison, verify_context


class CollectionTests(unittest.TestCase):
    def setUp(self):
        parent = HERE / ".runtime" / "parity-unit-tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.receipt = {"results": [], "captureStatus": "BLOCKED", "gateW1": "UNVERIFIED", "exit": 1}

    def row(self, view="today", width=1280, geometry=False, tokens=True):
        return {"view": view, "viewport": [width, 720 if width == 1280 else 860],
                "geometryEqual": geometry, "tokensEqual": tokens}

    def test_early_drift_keeps_all_six_comparisons_and_failure(self):
        for width in (1280, 1380):
            for view in ("chat", "settings", "today"):
                record_comparison(self.output, self.receipt,
                                  self.row(view, width, geometry=not (view == "today" and width == 1280)), True)
        finish_capture(self.receipt)
        self.assertEqual((self.receipt["captureStatus"], self.receipt["gateW1"], self.receipt["exit"]),
                         ("FAIL", "FAIL", 1))
        self.assertEqual(len(json.loads((self.output / "Comparison.json").read_text())), 6)
        self.assertEqual(len(self.receipt["comparisonFailures"]), 1)
        # Failure is durable even before finalization (e.g. process interruption).
        persisted = json.loads((self.output / "ParityResult.json").read_text())
        self.assertEqual(persisted["gateW1"], "FAIL")

    def test_default_still_stops_and_preserves_original_png(self):
        image = self.output / "today-1280x720-qt.png"
        image.write_bytes(b"existing evidence sentinel")
        with self.assertRaisesRegex(ValidationError, "Geometry mismatch"):
            record_comparison(self.output, self.receipt, self.row())
        self.assertEqual(image.read_bytes(), b"existing evidence sentinel")
        self.assertEqual(len(json.loads((self.output / "Comparison.json").read_text())), 1)
        self.assertEqual(json.loads((self.output / "ParityResult.json").read_text())["gateW1"], "FAIL")

    def test_token_failure_is_fatal_even_with_collection(self):
        with self.assertRaisesRegex(ValidationError, "Token mismatch"):
            record_comparison(self.output, self.receipt, self.row(tokens=False), True)
        self.assertEqual(self.receipt["gateW1"], "FAIL")

    def test_later_infrastructure_failure_cannot_downgrade_observed_failure(self):
        record_comparison(self.output, self.receipt, self.row(), True)
        finish_capture(self.receipt, RuntimeError("child unavailable"))
        self.assertEqual(self.receipt["gateW1"], "FAIL")
        self.assertIn("child unavailable", self.receipt["error"])
        self.assertEqual(len(self.receipt["results"]), 1)

    def test_success_is_still_unverified_and_fatal_errors_never_pass(self):
        finish_capture(self.receipt)
        self.assertEqual((self.receipt["captureStatus"], self.receipt["gateW1"]), ("PASS", "UNVERIFIED"))
        finish_capture(self.receipt, ValidationError("security/render/context"))
        self.assertEqual((self.receipt["gateW1"], self.receipt["exit"]), ("FAIL", 1))
        unavailable = {"results": []}
        finish_capture(unavailable, RuntimeError("unavailable"))
        self.assertEqual((unavailable["gateW1"], unavailable["exit"]), ("BLOCKED", 1))

    def test_missing_or_empty_non_smoke_minimum_token_cannot_pass(self):
        original = {"viewport": {}, "language": "ja", "timezone": "Asia/Taipei", "fontStatus": "loaded",
                    "tokens": {"--iris": "#65b3a6", "--ui-font": "font stack"}}
        verify_context(original, original, original["tokens"])
        for value in ("", None, "other font"):
            measured = copy.deepcopy(original)
            if value is None:
                del measured["tokens"]["--ui-font"]
            else:
                measured["tokens"]["--ui-font"] = value
            with self.assertRaisesRegex(ValidationError, "canonical tokens"):
                verify_context(measured, measured, original["tokens"])


if __name__ == "__main__":
    unittest.main()
