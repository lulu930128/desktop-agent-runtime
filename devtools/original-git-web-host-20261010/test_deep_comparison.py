"""Empty selectors must never look like measured parity."""
import copy
import unittest
from compare_deep_geometry import compare, REQUIRED


class DeepComparisonTests(unittest.TestCase):
    def fixture(self):
        return dict(viewport={}, language="zh-TW", timezone="UTC", fontStatus="loaded", tokens={},
                    deepGeometry={s: [{"y": 10}] for s in REQUIRED},
                    deepCoverage={"required": {s: 1 for s in REQUIRED}}, fontChecks={}, intl={})

    def test_every_required_selector_missing_is_fail(self):
        for selector in REQUIRED:
            left, right = self.fixture(), self.fixture()
            right["deepGeometry"][selector] = []
            self.assertEqual(compare(left, right)["gateW1"], "FAIL", selector)
            self.assertTrue(compare(left, right)["emptyRequiredSelectors"])

    def test_three_pixel_difference_is_fail(self):
        left, right = self.fixture(), self.fixture()
        right["deepGeometry"][".local-schedule"][0]["y"] += 3
        self.assertEqual(compare(left, right)["gateW1"], "FAIL")

    def test_even_equal_measurements_cannot_pass_gate(self):
        left = self.fixture()
        self.assertEqual(compare(left, {"status": "PASS", "geometry": copy.deepcopy(left)})["gateW1"], "UNVERIFIED")


if __name__ == "__main__": unittest.main()
