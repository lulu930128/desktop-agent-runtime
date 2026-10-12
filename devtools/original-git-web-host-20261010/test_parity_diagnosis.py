"""Bounded unit checks for the independent stdlib pixel calculations."""
import unittest

from diagnose_parity import metrics, value_diffs


class DiagnosisTests(unittest.TestCase):
    def test_rgb_mae_rms_and_fraction(self):
        a = (2, 1, bytes([0, 0, 0, 255, 255, 255]))
        b = (2, 1, bytes([0, 0, 0, 253, 251, 247]))
        result = metrics(a, b, [0, 0, 2, 1])
        self.assertEqual(result["changedPixelFraction"], 0.5)
        self.assertEqual(result["meanAbsoluteErrorRGB"], [1, 2, 4])
        self.assertEqual(result["rmsRGB"], [2 ** 0.5, 8 ** 0.5, 32 ** 0.5])
        self.assertEqual(result["maxChannelDeltaGreaterThan8"], 0)

    def test_translation_is_diagnostic_and_does_not_replace_raw_metric(self):
        a = (1, 3, bytes([12, 24, 36, 6, 8, 10, 0, 0, 0]))
        b = (1, 3, bytes([0, 0, 0, 12, 24, 36, 6, 8, 10]))
        raw = metrics(a, b, [0, 0, 1, 2])
        aligned = metrics(a, b, [0, 0, 1, 2], 1)
        self.assertEqual(raw["changedPixelFraction"], 1)
        self.assertEqual(aligned["changedPixelFraction"], 0)
        with self.assertRaises(ValueError):
            metrics(a, b, [0, 0, 1, 3], 1)

    def test_exact_selector_delta_including_missing_fields(self):
        self.assertEqual(value_diffs({".local-schedule": {"y": 493.921875}},
                                     {".local-schedule": {"y": 496.921875}}),
                         [{"path": "/.local-schedule/y", "baseline": 493.921875,
                           "qt": 496.921875, "qtMinusBaseline": 3.0}])
        self.assertEqual(value_diffs({"token": "x"}, {}),
                         [{"path": "/token", "baseline": "x", "qt": None}])


if __name__ == "__main__":
    unittest.main()
