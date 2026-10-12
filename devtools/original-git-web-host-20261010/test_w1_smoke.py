"""Stdlib-only contract tests. Never import Qt/PIL/Playwright or start a GUI."""
import copy
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

import w1_smoke as smoke
from capture_parity import verify_context


def metadata(view="chat", dpr=1.25):
    return {"status": "PASS", "offTheRecord": True, "platform": "windows", "view": view,
            "bridgeRequests": 8, "geometry": {"ready": True,
                "viewport": {"width": 1280, "height": 720, "devicePixelRatio": dpr},
                "fontStatus": "loaded", "language": "zh-TW", "timezone": "Asia/Taipei",
                "tokens": {"--rail-width": "78px", "--chrome-height": "50px", "--iris": "#65b3a6"},
                "geometry": {".composer": {"width": 900, "height": 80, "display": "block"},
                             ".settings-shell": {"width": 900, "height": 600, "display": "grid"}},
                "categories": ["assistant", "conversation", "perception", "tools", "pet", "diagnostics"]}}


class EvidenceTests(unittest.TestCase):
    def test_node_measurement_missing_token_still_fails_smoke(self):
        # Actual geometry.js in a mock DOM, then the unchanged Python validator.
        raw = subprocess.check_output(["node", str(smoke.HERE / "test_geometry.cjs"), "--json"],
                                      cwd=smoke.HERE, timeout=10)
        measured = json.loads(raw)
        candidate = metadata()
        candidate["geometry"]["tokens"] = measured["complete"]["tokens"]
        smoke.validate_metadata(candidate, 1280, 720, "chat")
        candidate["geometry"]["tokens"] = measured["missing"]["tokens"]
        self.assertEqual(candidate["geometry"]["tokens"]["--iris"], "")
        with self.assertRaisesRegex(smoke.ValidationError, "Original visual tokens differ"):
            smoke.validate_metadata(candidate, 1280, 720, "chat")

    def test_parity_stops_on_locale_timezone_font_or_dpr_mismatch(self):
        baseline = metadata()["geometry"]
        verify_context(baseline, copy.deepcopy(baseline))
        for key, value in [("language", "en-US"), ("timezone", "UTC"), ("fontStatus", "loading"),
                           ("viewport", {"width": 1280, "height": 720, "devicePixelRatio": 2})]:
            candidate = copy.deepcopy(baseline)
            candidate[key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                verify_context(baseline, candidate)

    def test_actual_dpr_not_assumed_100_percent(self):
        self.assertEqual(smoke.validate_metadata(metadata(), 1280, 720, "chat"), 1.25)
        with self.assertRaises(smoke.ValidationError):
            smoke.validate_metadata(metadata(), 1280, 720, "chat", 1)

    def test_rejects_render_security_viewport_and_font_failures(self):
        original = metadata()
        mutations = [lambda m: m.update(status="UNVERIFIED"), lambda m: m.update(offTheRecord=False),
                     lambda m: m.update(platform="offscreen"), lambda m: m.update(bridgeRequests=0),
                     lambda m: m.update(bridgeRequests=101), lambda m: m.update(bridgeRequests=True),
                     lambda m: m["geometry"].update(ready=False),
                     lambda m: m["geometry"].update(fontStatus="loading"),
                     lambda m: m["geometry"]["viewport"].update(width=1278),
                     lambda m: m["geometry"]["viewport"].update(devicePixelRatio=float("nan")),
                     lambda m: m["geometry"]["tokens"].update({"--rail-width": "80px"}),
                     lambda m: m["geometry"]["geometry"][".composer"].update(height=0)]
        for mutate in mutations:
            candidate = copy.deepcopy(original)
            mutate(candidate)
            with self.subTest(candidate=candidate), self.assertRaises(smoke.ValidationError):
                smoke.validate_metadata(candidate, 1280, 720, "chat")

    def test_requires_all_six_settings_groups(self):
        candidate = metadata("settings")
        smoke.validate_metadata(candidate, 1280, 720, "settings")
        candidate["geometry"]["categories"].pop()
        with self.assertRaises(smoke.ValidationError):
            smoke.validate_metadata(candidate, 1280, 720, "settings")

    def test_refuses_inherited_overrides_without_mutating_environment(self):
        for key in smoke.OVERRIDES:
            values = {key: "1"}
            with self.subTest(key=key), self.assertRaises(smoke.EvidenceError):
                smoke.check_environment(values)
            self.assertEqual(values, {key: "1"})

    def test_first_chat_failure_stops_settings_and_preserves_receipt(self):
        parent = smoke.HERE / ".runtime" / "relay-unit-tests"
        parent.mkdir(parents=True, exist_ok=True)
        # This disposable subtree is owned by this test; no production paths.
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            task = Path(directory).resolve()
            output = task / ".runtime" / "run"
            called = []

            def fake_command(command, destination, name, **kwargs):
                called.append(name)
                if name == "qt-chat":
                    smoke.write_json(destination / "chat.json", {"status": "FAIL", "error": "load_failed"})
                    raise smoke.EvidenceError("qt-chat: child exit 1")
                return {"exit": 0}

            with patch.object(smoke, "HERE", task), patch.object(smoke.sys, "prefix", str(task / ".venv")), \
                 patch.object(smoke.sys, "argv", ["w1_smoke.py", "--output", str(output)]), \
                 patch.object(smoke, "check_environment"), patch.object(smoke, "run_logged", side_effect=fake_command), \
                 patch.object(smoke, "fingerprint", return_value={"fixture": "digest"}):
                self.assertEqual(smoke.main(), 1)
            self.assertNotIn("qt-settings", called)
            self.assertEqual(called[-1], "source-after")
            result = json.loads((output / "SmokeResult.json").read_text(encoding="utf-8"))
            self.assertEqual(result["smokeStatus"], "FAIL")
            self.assertEqual(result["gateW1"], "FAIL")
            self.assertFalse(result["w2Started"])

    def test_stale_smoke_rejected_before_pixel_import(self):
        parent = smoke.HERE / ".runtime" / "relay-unit-tests"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            receipt = Path(directory) / "SmokeResult.json"
            smoke.write_json(receipt, {"smokeStatus": "PASS", "sourceFingerprint": {"old": "bytes"}})
            with self.assertRaises(smoke.EvidenceError):
                smoke.read_smoke(receipt)


if __name__ == "__main__":
    unittest.main()
