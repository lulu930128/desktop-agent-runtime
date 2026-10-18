"""W6 dry-run guards; no Qt app construction, process or production writes."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from kuro_launcher.qt_web_host import create_candidate

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("w6_inventory", ROOT/"devtools/original-git-web-host-20261010/w6_inventory.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
build_spec = importlib.util.spec_from_file_location("w6_build", ROOT/"devtools/original-git-web-host-20261010/build_owner_bundle.py")
builder = importlib.util.module_from_spec(build_spec)
build_spec.loader.exec_module(builder)


class DryRunTests(unittest.TestCase):
    def test_inventory_is_blocked_and_preserves_owners(self):
        value = module.inventory()
        self.assertEqual(value["gate"], "BLOCKED")
        self.assertFalse(value["deletionAuthorized"])
        self.assertFalse(value["cutoverExecuted"])
        self.assertFalse(value["w7Started"])
        self.assertEqual(len(value["g7Absent"]), 35)
        self.assertIn("kuro_launcher/qt_notifications.py", [r["path"] for r in value["preserve"]])

    def test_formal_entry_uses_reviewed_pin_and_retains_explicit_widgets_rollback(self):
        from kuro_launcher.qt_web_release import RELEASE_PIN, OwnerBundlePin, prepare_owner_presentation
        app = (ROOT/"kuro_launcher/qt_app.py").read_text(encoding="utf-8")
        self.assertIn("self.work_companion = WorkCompanionView(", app)
        self.assertIsInstance(RELEASE_PIN, OwnerBundlePin)
        # W7 versions the active source pin. Historical W6 native SHA/pin
        # assertions remain in test_qt_web_release_candidate, unchanged.
        self.assertEqual(RELEASE_PIN.fingerprint, builder.fingerprint(builder.lineage()))
        from kuro_launcher.qt_web_release import VerifiedOwnerBundle
        VerifiedOwnerBundle.load(ROOT/'assets/qt-owner'/RELEASE_PIN.fingerprint, RELEASE_PIN)
        with patch('kuro_launcher.qt_web_release.RELEASE_PIN', None):
            self.assertIsNone(prepare_owner_presentation(ROOT))
        self.assertNotIn("qt_web_host", (ROOT/"桌寵啟動器.vbs").read_text(encoding="utf-8-sig"))
        launcher = (ROOT/"launcher_qt.py").read_text(encoding="utf-8")
        self.assertLess(launcher.index("web_bundle = prepare_owner_presentation"), launcher.index("app = QApplication"))

    def test_readiness_strings_cannot_authorize_formal_attachment(self):
        owner = SimpleNamespace(web_presentation_exclusive=True)
        with self.assertRaisesRegex(RuntimeError, "Formal W6 adoption BLOCKED"):
            create_candidate(owner, "unused", enabled=True, readiness={"W1": "PASS", "W2": "PASS"})
        with self.assertRaisesRegex(ValueError, "synthetic owner"):
            create_candidate(owner, "unused", enabled=True, fixture=True)

    def test_graph_includes_actual_widget_observers_and_attributes(self):
        graph = module.source_graph()["kuro_launcher/qt_app.py"]
        observers = [r["expression"] for r in graph["observers"]]
        self.assertIn("self.chat_client.message_received.connect(self._on_chat_protocol_message)", observers)
        self.assertIn("self.status_timer.timeout.connect(self._refresh_core_pages)", observers)
        self.assertTrue(any(r["name"] == "today_page" and r["access"] == "Store" for r in graph["attributes"]))
        self.assertTrue(graph["reverseSelfCalls"]["_build_ui"])

    def test_scheme_registration_after_real_qt_application_is_rejected(self):
        code = """from PySide6.QtCore import QCoreApplication
from kuro_launcher.qt_web_host import register_candidate_scheme
app = QCoreApplication([])
try:
 register_candidate_scheme()
except RuntimeError as exc:
 assert 'before QApplication' in str(exc)
else:
 raise AssertionError('Late registration must fail before WebEngine import')
"""
        process = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_owner_package_has_pinned_source_and_stable_location(self):
        result = builder.build(verify_only=True)
        self.assertFalse(result["productionAdoption"])
        self.assertTrue(Path(result["directory"]).is_relative_to(ROOT / "assets/qt-owner"))
        self.assertEqual(len([n for n in builder.lineage()["sources"] if n in builder.ORIGINALS]), 6)

    def test_owner_package_rejects_asset_manifest_and_lineage_tamper(self):
        expected = builder.lineage()
        source = builder.ASSETS / builder.fingerprint(expected)
        for target in ("work-panel.html", "candidate-manifest.json", "owner-build.json"):
            with self.subTest(target=target), tempfile.TemporaryDirectory(prefix=".validation-w6-", dir=ROOT) as folder:
                copied = Path(folder) / "bundle"
                shutil.copytree(source, copied)
                path = copied / target
                if target == "owner-build.json":
                    value = json.loads(path.read_text(encoding="utf-8"))
                    value["lineage"]["originalCommit"] = "forged"
                    path.write_text(json.dumps(value), encoding="utf-8")
                else:
                    path.write_bytes(path.read_bytes() + b" ")
                with self.assertRaises(ValueError):
                    builder.verify(copied, expected)

    def test_owner_package_rejects_extra_file(self):
        expected = builder.lineage()
        with tempfile.TemporaryDirectory(prefix=".validation-w6-", dir=ROOT) as folder:
            copied = Path(folder) / "bundle"
            shutil.copytree(builder.ASSETS / builder.fingerprint(expected), copied)
            (copied / "extra.js").write_text("unexpected", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unexpected"):
                builder.verify(copied, expected)

    def test_preflight_wrong_interpreter_fails_closed_without_app(self):
        task = ROOT / "devtools/original-git-web-host-20261010"
        with tempfile.TemporaryDirectory(prefix="w6-probe-", dir=task / ".runtime") as folder:
            output = Path(folder) / "Probe.json"
            process = subprocess.run([sys.executable, "-I", "-B", str(task / "w6_preflight.py"),
                                      "--expected-prefix", str(Path(folder) / "not-an-env"),
                                      "--output", str(output)], cwd=ROOT, capture_output=True, timeout=20)
            self.assertEqual(process.returncode, 2, process.stderr)
            value = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(value["applicationCreated"])
            self.assertFalse(value["productionAdoption"])
            self.assertIn("Interpreter/prefix does not match expected environment", value["blockers"])


if __name__ == "__main__":
    unittest.main()
