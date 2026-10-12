"""Offline installer refusal/owner-plan tests; no download or environment writes."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load("w6_package_gate")
plan = load("w6_owner_plan")


class PackageTests(unittest.TestCase):
    def test_same_version_existing_addons_refuses_before_backup_or_pip(self):
        with patch.object(gate.metadata, "distribution", return_value=SimpleNamespace(version="6.11.1")), \
             patch.object(gate, "pip") as pip, patch.object(gate, "package_files") as files:
            with self.assertRaisesRegex(RuntimeError, "already present"):
                gate.snapshot(Path("unused"))
            pip.assert_not_called()
            files.assert_not_called()

    def test_essentials_version_mismatch_refuses_before_reads(self):
        with patch.object(gate.metadata, "distribution", return_value=SimpleNamespace(version="6.11.0")):
            with self.assertRaisesRegex(RuntimeError, "version mismatch"):
                gate.package_files()

    def test_only_addons_delta_allowed(self):
        before = [{"name": "PySide6-Essentials", "version": "6.11.1"}, {"name": "shiboken6", "version": "6.11.1"}]
        addon = {"name": "PySide6-Addons", "version": "6.11.1"}
        gate.package_delta(before, before + [addon])
        for after in (before, before + [{**addon, "version": "6.12.0"}],
                      [{**before[0], "version": "6.12.0"}, before[1], addon],
                      before + [addon, {"name": "unrelated", "version": "1"}]):
            with self.subTest(after=after), self.assertRaises(RuntimeError):
                gate.package_delta(before, after)

    def test_wheel_hash_metadata_tag_overlap_and_traversal_refuse(self):
        with tempfile.TemporaryDirectory(dir=HERE / ".runtime", prefix="w6-negative-") as folder:
            root = Path(folder)
            site = root / "site"
            site.mkdir()
            wheel = root / gate.FILENAME
            def build(version="6.11.1", tag="cp310-abi3-win_amd64", extra="PySide6/new.dll"):
                with zipfile.ZipFile(wheel, "w") as z:
                    z.writestr("pyside6_addons-6.11.1.dist-info/METADATA", "Name: PySide6-Addons\nVersion: " + version + "\nRequires-Python: >=3.10,<3.15\n")
                    z.writestr("pyside6_addons-6.11.1.dist-info/WHEEL", "Tag: " + tag + "\n")
                    z.writestr(extra, "synthetic")
                    rows = [[n, gate.record_hash(z.read(n)), str(len(z.read(n)))] for n in z.namelist()]
                    rows.append([gate.DIST_INFO + "/RECORD", "", ""])
                    z.writestr(gate.DIST_INFO + "/RECORD", gate.csv_bytes(rows))
            build()
            with self.assertRaisesRegex(RuntimeError, "SHA/name mismatch"):
                gate.wheel_contents(wheel, site)
            # Synthetic ZIPs test inner guards independently of the outer pinned hash.
            with patch.object(gate, "sha", return_value=gate.SHA256):
                self.assertEqual(gate.wheel_contents(wheel, site)["metadataVersion"], "6.11.1")
                for kwargs, reason in (({"version": "6.12.0"}, "METADATA"),
                                       ({"tag": "cp313-cp313-win_amd64"}, "internal tag"),
                                       ({"extra": "../escape.dll"}, "Unsafe wheel path")):
                    build(**kwargs)
                    with self.subTest(kwargs=kwargs), self.assertRaisesRegex(RuntimeError, reason):
                        gate.wheel_contents(wheel, site)
                build(extra="occupied.dll")
                (site / "occupied.dll").write_bytes(b"preexisting")
                with self.assertRaisesRegex(RuntimeError, "overlap"):
                    gate.wheel_contents(wheel, site)
                self.assertEqual((site / "occupied.dll").read_bytes(), b"preexisting")

    def test_install_refuses_changed_qt_before_pip(self):
        with tempfile.TemporaryDirectory(dir=HERE / ".runtime", prefix="w6-negative-") as folder:
            run = Path(folder)
            (run / "Baseline.json").write_text(json.dumps({"files": {"a": "old"}}))
            with patch.object(gate, "package_files", return_value={"a": "changed"}), patch.object(gate, "pip") as pip:
                with self.assertRaisesRegex(RuntimeError, "changed since snapshot"):
                    gate.install(run)
                pip.assert_not_called()


class PreflightReceiptTests(unittest.TestCase):
    """Exercise the real snapshot/verify/command writers with synthetic processes."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory(dir=HERE / ".runtime", prefix="w6-receipts-")
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.run = self.root / "receipts"
        self.run.mkdir()
        self.formal = self.root / "synthetic-env"
        self.formal.mkdir()
        self.before = [{"name": name, "version": gate.VERSION} for name in gate.EXISTING]
        self.probe_exit = 2
        self.probe = {
            "mode": "SYNTHETIC_NO_INSTALL", "status": "BLOCKED",
            "schemeRegistration": "NOT_RUN", "overrideNames": [],
            "formalInterpreter": True, "qtVersion": gate.VERSION,
            "modules": {name: {"status": "PASS", "origin": str(self.formal / (name + ".pyd"))}
                        for name in ("PySide6", "shiboken6", "PySide6.QtCore", "PySide6.QtWidgets")},
        }
        for target, name, kwargs in (
            (gate, "FORMAL", {"new": self.formal}),
            (gate, "package_files", {"return_value": {}}),
            (gate, "installed_ownership", {"return_value": {"mode": "SYNTHETIC"}}),
            (gate.metadata, "distribution", {"side_effect": self.distribution}),
            (gate.metadata, "version", {"return_value": gate.VERSION}),
            (gate.subprocess, "run", {"side_effect": self.process}),
            (gate.urllib.request, "urlopen", {"side_effect": AssertionError("Network forbidden")}),
        ):
            mock = patch.object(target, name, **kwargs)
            mock.start()
            self.addCleanup(mock.stop)

    def distribution(self, name):
        if name == "PySide6-Addons":
            raise gate.metadata.PackageNotFoundError(name)
        return SimpleNamespace(locate_file=lambda _: self.formal)

    def process(self, argv, **kwargs):
        self.assertEqual(kwargs, {"cwd": gate.ROOT, "capture_output": True, "timeout": 600})
        if "--output" in argv:
            self.assertEqual(argv[:5], [gate.sys.executable, "-I", "-B", str(HERE / "w6_preflight.py"), "--output"])
            with Path(argv[-1]).open("x", encoding="utf-8") as stream:
                json.dump(self.probe, stream)
            return SimpleNamespace(returncode=self.probe_exit, stdout=b"synthetic preflight\n", stderr=b"")
        self.assertEqual(argv[3:7], ["-m", "pip", "--isolated", "--disable-pip-version-check"])
        self.assertIn(argv[7], ("list", "freeze", "check", "--version"))
        rows = self.before + [{"name": "PySide6-Addons", "version": gate.VERSION}]
        return SimpleNamespace(returncode=0, stdout=json.dumps(rows).encode(), stderr=b"")

    def verify_baseline(self):
        gate.write(self.run, "Baseline.json", {"files": {}})
        (self.run / "list-before.stdout").write_text(json.dumps(self.before), encoding="utf-8")

    def assert_receipts(self, phase):
        probe_name = "Preflight-" + phase + ".json"
        process_name = "preflight-" + phase + "-process"
        names = [p.name for p in self.run.iterdir()]
        self.assertEqual(len(names), len({n.casefold() for n in names}), names)
        self.assertEqual(json.loads((self.run / probe_name).read_text(encoding="utf-8")), self.probe)
        receipt = json.loads((self.run / (process_name + ".json")).read_text(encoding="utf-8"))
        self.assertEqual(receipt["exit"], self.probe_exit)
        self.assertEqual(receipt["argv"][-1], str(self.run / probe_name))
        self.assertTrue(receipt["utc"])
        self.assertEqual((self.run / (process_name + ".stdout")).read_bytes(), b"synthetic preflight\n")
        self.assertEqual((self.run / (process_name + ".stderr")).read_bytes(), b"")

    def test_before_blocked_probe_keeps_distinct_casefold_receipts(self):
        gate.snapshot(self.run)
        self.assert_receipts("before")
        self.assertFalse((self.run / "PackageGate.json").exists())

    def test_after_blocked_probe_keeps_distinct_casefold_receipts(self):
        self.verify_baseline()
        with self.assertRaisesRegex(RuntimeError, "Formal WebEngine preflight failed"):
            gate.verify(self.run)
        self.assert_receipts("after")
        self.assertFalse((self.run / "PackageGate.json").exists())

    def test_after_synthetic_success_reads_probe_not_process_receipt(self):
        self.verify_baseline()
        self.probe_exit = 0
        self.probe.update(status="PREREQUISITES_PASS", schemeRegistration="PASS_BEFORE_APPLICATION")
        gate.verify(self.run)
        self.assert_receipts("after")
        self.assertFalse(json.loads((self.run / "PackageGate.json").read_text())["productionAdoption"])

    def test_probe_and_process_json_refuse_overwrite(self):
        gate.snapshot(self.run)
        original = {p.name: p.read_bytes() for p in self.run.iterdir()}
        for name in ("Preflight-before.json", "preflight-before-process.json"):
            with self.subTest(name=name), self.assertRaises(FileExistsError):
                gate.write(self.run, name, {"overwrite": True})
        self.assertEqual(original, {p.name: p.read_bytes() for p in self.run.iterdir()})


class RollbackReceiptTests(unittest.TestCase):
    def test_missing_or_failed_install_json_refuses_before_uninstall(self):
        with tempfile.TemporaryDirectory(dir=HERE / ".runtime", prefix="w6-rollback-") as folder:
            run = Path(folder)
            # An alternate receipt must never authorize rollback.
            gate.write(run, "install-process.json", {"exit": 0})
            with patch.object(gate, "pip") as pip, patch.object(gate, "package_files") as files:
                with self.assertRaises(FileNotFoundError):
                    gate.rollback(run)
                gate.write(run, "install.json", {"exit": 2})
                with self.assertRaisesRegex(RuntimeError, "Partial install needs manual review"):
                    gate.rollback(run)
                pip.assert_not_called()
                files.assert_not_called()

    def test_successful_install_json_allows_only_mocked_rollback(self):
        with tempfile.TemporaryDirectory(dir=HERE / ".runtime", prefix="w6-rollback-") as folder:
            run = Path(folder)
            with patch.object(gate.subprocess, "run", return_value=SimpleNamespace(
                    returncode=0, stdout=b"synthetic", stderr=b"")):
                gate.pip(run, "install", "install", "synthetic-wheel")
            self.assertEqual(json.loads((run / "install.json").read_text())["exit"], 0)
            gate.write(run, "Baseline.json", {"files": {}})
            gate.write(run, "InstallWheelReceipt.json", {"files": []})
            (run / "list-before.stdout").write_bytes(b"[]")
            with patch.object(gate, "package_files", return_value={}), \
                 patch.object(gate, "installed_ownership", return_value={"mode": "SYNTHETIC"}), \
                 patch.object(gate.metadata, "distribution", return_value=SimpleNamespace(version=gate.VERSION, files=[])), \
                 patch.object(gate, "pip", return_value=SimpleNamespace(returncode=0, stdout=b"[]")) as pip:
                gate.rollback(run)
                self.assertEqual(pip.call_args_list[0].args, (run, "rollback", "uninstall", "--yes", "PySide6-Addons"))
                self.assertEqual(pip.call_count, 3)
            self.assertEqual(json.loads((run / "RollbackReceipt.json").read_text())["status"], "BASELINE_RESTORED")


class OwnerTests(unittest.TestCase):
    def test_current_owner_and_hidden_widget_paths_are_explicit(self):
        result = plan.analyze((plan.ROOT / "kuro_launcher/qt_app.py").read_text(encoding="utf-8-sig"))
        self.assertEqual(set(result["ownerCounts"].values()), {1})
        bindings = {b["expression"]: b for b in result["bindings"]}
        status = bindings["self.task_finished.connect(self._on_task_finished)"]
        self.assertIn("runtime_detail", status["widgetAttributes"])
        self.assertIn("_apply_status", status["reachableMethods"])
        self.assertIn("self.status_timer.timeout.connect(self._refresh_core_pages)", bindings)
        self.assertFalse(result["productionAdoption"])

    def test_duplicate_owner_and_indirect_widget_mutation_detected(self):
        result = plan.analyze('''class KuroQtLauncherWindow:
 def __init__(self):
  self.chat = QtRuntimeChatClient(self)
  self.other = QtRuntimeChatClient(self)
  self.timer.connect(self.callback)
 def callback(self): self.render()
 def render(self):
  self.runtime_detail.setText('ghost')
  self.chat.create_history()
''')
        self.assertEqual(result["ownerCountViolations"]["QtRuntimeChatClient"], 2)
        self.assertEqual(result["bindings"][0]["widgetAttributes"], ["runtime_detail"])
        self.assertIn("self.chat.create_history", result["bindings"][0]["ownerMutationCalls"])

    def test_cycles_terminate_without_losing_callbacks(self):
        self.assertEqual(plan.reachable("a", {"a": {"b"}, "b": {"a", "c"}}), {"a", "b", "c"})


if __name__ == "__main__":
    unittest.main()
