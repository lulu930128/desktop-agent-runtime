"""Ownership regression fixtures; real pip roundtrip uses only a disposable venv."""
import csv
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("w6_ownership_gate", HERE / "w6_package_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
INFO = "pyside6_addons-6.11.1.dist-info"
OWNER = "pyside6_essentials-6.11.1.dist-info"
SHARED = "PySide6/__init__.py"


def csv_data(rows):
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rows)
    return output.getvalue().encode()


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=HERE / ".runtime", prefix="w6-ownership-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.site = self.root / "env/Lib/site-packages"
        self.site.mkdir(parents=True)
        self.run = self.root / "run"
        self.run.mkdir()
        (self.run / "wheelhouse").mkdir()
        self.wheel = self.run / "wheelhouse" / gate.FILENAME
        self.payload = {
            SHARED: b"# shared synthetic package\n",
            "PySide6/QtWebChannel.pyi": b"# synthetic shared stub\n",
            "PySide6/addon_payload.txt": b"synthetic addon payload\n",
            INFO + "/METADATA": b"Metadata-Version: 2.1\nName: PySide6-Addons\nVersion: 6.11.1\nRequires-Python: >=3.10\nRequires-Dist: PySide6-Essentials==6.11.1\n",
            INFO + "/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: cp310-abi3-win_amd64\n",
        }
        self.make_wheel()
        for name in (SHARED, "PySide6/QtWebChannel.pyi"):
            path = self.site / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(self.payload[name])
        self.make_owner()
        self.pin = patch.object(gate, "SHA256", gate.sha(self.wheel.read_bytes()))
        self.pin.start()
        self.addCleanup(self.pin.stop)

    def make_wheel(self):
        with zipfile.ZipFile(self.wheel, "w") as z:
            rows = []
            for name, data in self.payload.items():
                z.writestr(name, data)
                rows.append([name, gate.record_hash(data), str(len(data))])
            rows.append([INFO + "/RECORD", "", ""])
            z.writestr(INFO + "/RECORD", csv_data(rows))

    def make_owner(self, directory=OWNER, version="6.11.1", row_change=None):
        folder = self.site / directory
        folder.mkdir(exist_ok=True)
        data = ("Metadata-Version: 2.1\nName: PySide6-Essentials\nVersion: " + version + "\n").encode()
        (folder / "METADATA").write_bytes(data)
        rows = [[n, gate.record_hash(self.payload[n]), str(len(self.payload[n]))]
                for n in (SHARED, "PySide6/QtWebChannel.pyi")]
        rows.extend([[directory + "/METADATA", gate.record_hash(data), str(len(data))],
                     [directory + "/RECORD", "", ""]])
        if row_change:
            row_change(rows)
        (folder / "RECORD").write_bytes(csv_data(rows))

    def audit(self):
        return gate.wheel_contents(self.wheel, self.site)

    def prepare(self):
        receipt = self.audit()
        gate.write(self.run, "WheelReceipt.json", receipt)
        derived = gate.build_install_wheel(self.run, self.wheel, receipt)
        return receipt, derived

    def test_identical_owned_overlap_is_excluded_not_dual_owned(self):
        result = self.audit()
        self.assertEqual({r["path"] for r in result["overlaps"]}, {SHARED, "PySide6/QtWebChannel.pyi"})
        self.assertTrue(all(r["identical"] for r in result["overlaps"]))

    def test_unknown_multiple_and_missing_owners_rejected(self):
        record = self.site / OWNER / "RECORD"
        original = record.read_bytes()
        rows = list(csv.reader(io.StringIO(original.decode())))
        record.write_bytes(csv_data(rows[1:]))
        with self.assertRaisesRegex(RuntimeError, "Unknown or multiple"):
            self.audit()
        record.write_bytes(original)
        self.make_owner(directory="unknown-1.dist-info")
        with self.assertRaisesRegex(RuntimeError, "Unknown or multiple"):
            self.audit()

    def test_owned_missing_file_rejected(self):
        (self.site / SHARED).unlink()
        with self.assertRaisesRegex(RuntimeError, "Missing owned"):
            self.audit()

    def test_optional_duplicate_pyc_is_retained_but_never_shared(self):
        name = "PySide6/support/__pycache__/fixture.cpython-310.pyc"
        self.make_owner(row_change=lambda rows: rows.extend([[name, "", ""], [name, "sha256=legacy", "2"]]))
        owners, _ = gate.ownership_index(self.site)
        self.assertEqual(len(owners[str((self.site / name).absolute()).casefold()]), 2)
        self.assertEqual(len(self.audit()["overlaps"]), 2)

    def test_unknown_legacy_owner_cannot_claim_pyside(self):
        legacy = self.site / "legacy-1.egg-info"
        legacy.mkdir()
        (legacy / "top_level.txt").write_text("PySide6\n")
        with self.assertRaisesRegex(RuntimeError, "Unknown legacy ownership"):
            self.audit()

    def test_local_wheel_redirect_refuses_before_snapshot_or_copy(self):
        with patch.object(gate, "no_redirect", side_effect=RuntimeError("Path redirects")), \
             patch.object(gate, "snapshot") as snapshot, patch.object(gate.shutil, "copyfile") as copy:
            with self.assertRaisesRegex(RuntimeError, "Path redirects"):
                gate.prepare(self.run, self.wheel)
            snapshot.assert_not_called()
            copy.assert_not_called()

    def test_new_python_payload_rejects_preexisting_or_owned_bytecode(self):
        self.payload["PySide6/new_module.py"] = b"# new module\n"
        self.make_wheel()
        bytecode = self.site / "PySide6/__pycache__/new_module.cpython-310.pyc"
        bytecode.parent.mkdir()
        bytecode.write_bytes(b"unrelated")
        with patch.object(gate, "SHA256", gate.sha(self.wheel.read_bytes())):
            with self.assertRaisesRegex(RuntimeError, "implicit bytecode"):
                self.audit()
            bytecode.unlink()
            self.make_owner(row_change=lambda rows: rows.append(["PySide6/new_module.pyc", "", ""]))
            with self.assertRaisesRegex(RuntimeError, "bytecode ownership"):
                self.audit()

    def test_different_bytes_even_same_record_claim_rejected(self):
        (self.site / SHARED).write_bytes(b"different payload")
        with self.assertRaisesRegex(RuntimeError, "Different bytes"):
            self.audit()

    def test_owner_hash_size_version_and_record_alias_rejected(self):
        for field, value, reason in ((1, "", "hash/size"), (1, "sha256=bad", "hash/size"),
                                     (2, "1", "hash/size"), (0, "pyside6/__init__.py", "owner/version/path")):
            with self.subTest(field=field, value=value):
                self.make_owner(row_change=lambda rows: rows[0].__setitem__(field, value))
                with self.assertRaisesRegex(RuntimeError, reason):
                    self.audit()
        self.make_owner(version="6.11.0")
        with self.assertRaisesRegex(RuntimeError, "owner/version/path"):
            self.audit()

    def test_duplicate_and_malformed_installed_record_rejected(self):
        self.make_owner(row_change=lambda rows: rows.append(rows[0]))
        with self.assertRaisesRegex(RuntimeError, "Duplicate RECORD"):
            self.audit()
        self.make_owner(row_change=lambda rows: rows.append(["bad", "bad"]))
        with self.assertRaisesRegex(RuntimeError, "Malformed RECORD"):
            self.audit()

    def test_case_collision_in_existing_parent_rejected(self):
        (self.site / "PySide6").rename(self.site / "pyside6")
        with self.assertRaisesRegex(RuntimeError, "Case collision"):
            self.audit()

    def test_reparse_and_symlink_ancestors_rejected(self):
        original = Path.lstat
        for mode, attributes in ((stat.S_IFLNK, 0), (stat.S_IFDIR, stat.FILE_ATTRIBUTE_REPARSE_POINT)):
            def lstat(path):
                if path == self.site / "PySide6":
                    return SimpleNamespace(st_mode=mode, st_file_attributes=attributes)
                return original(path)
            with self.subTest(mode=mode), patch.object(Path, "lstat", lstat):
                with self.assertRaisesRegex(RuntimeError, "Path redirects"):
                    self.audit()

    def test_wheel_record_hash_missing_duplicate_and_symlink_rejected(self):
        for defect in ("hash", "coverage", "duplicate", "symlink", "case", "traversal"):
            self.make_wheel()
            with zipfile.ZipFile(self.wheel) as z:
                values = {n: z.read(n) for n in z.namelist()}
            rows = list(csv.reader(io.StringIO(values[INFO + "/RECORD"].decode())))
            if defect == "hash": rows[0][1] = "sha256=bad"
            if defect == "coverage": rows.pop(0)
            if defect == "duplicate": rows.append(rows[0])
            values[INFO + "/RECORD"] = csv_data(rows)
            if defect == "case": values[SHARED.lower()] = values[SHARED]
            if defect == "traversal": values["../escape"] = b"bad"
            with zipfile.ZipFile(self.wheel, "w") as z:
                for name, data in values.items():
                    if defect == "symlink" and name == SHARED:
                        item = zipfile.ZipInfo(name)
                        item.external_attr = (stat.S_IFLNK | 0o777) << 16
                        z.writestr(item, data)
                    else:
                        z.writestr(name, data)
            with self.subTest(defect=defect), patch.object(gate, "SHA256", gate.sha(self.wheel.read_bytes())):
                with self.assertRaises(RuntimeError):
                    self.audit()

    def test_derivative_exact_payload_record_and_provenance(self):
        original_hash = gate.sha(self.wheel.read_bytes())
        receipt, derived = self.prepare()
        target = self.run / "install-wheel" / gate.DERIVED_FILENAME
        with zipfile.ZipFile(target) as z:
            self.assertNotIn(SHARED, z.namelist())
            self.assertNotIn(SHARED, derived["records"])
            self.assertEqual(json.loads(z.read(gate.PROVENANCE))["officialSha256"], original_hash)
            self.assertEqual(z.read("PySide6/addon_payload.txt"), self.payload["PySide6/addon_payload.txt"])
        self.assertEqual(gate.sha(self.wheel.read_bytes()), original_hash)
        with self.assertRaises(FileExistsError):
            gate.build_install_wheel(self.run, self.wheel, receipt)

    def test_derivative_tamper_rejected_even_with_updated_receipt_hash(self):
        receipt, derived = self.prepare()
        target = self.run / "install-wheel" / gate.DERIVED_FILENAME
        with zipfile.ZipFile(target) as z:
            values = {n: z.read(n) for n in z.namelist()}
        values["PySide6/addon_payload.txt"] = b"tampered"
        rows = [[n, gate.record_hash(data), str(len(data))] for n, data in values.items() if n != INFO + "/RECORD"]
        rows.append([INFO + "/RECORD", "", ""])
        values[INFO + "/RECORD"] = csv_data(rows)
        with zipfile.ZipFile(target, "w") as z:
            for name, data in values.items(): z.writestr(name, data)
        derived["sha256"] = gate.sha(target.read_bytes())
        derived["records"] = {r[0]: r[1:] for r in rows}
        with self.assertRaisesRegex(RuntimeError, "Derived payload changed"):
            gate.validate_install_wheel(target, self.wheel, receipt, derived)

    def test_command_receipts_refuse_overwrite_before_process(self):
        for suffix in (".json", ".stdout", ".stderr"):
            path = self.run / ("case" + suffix)
            path.write_bytes(b"old")
            with patch.object(gate.subprocess, "run") as process:
                with self.assertRaisesRegex(RuntimeError, "receipt already exists"):
                    gate.command(self.run, "case", ["never"])
                process.assert_not_called()
            self.assertEqual(path.read_bytes(), b"old")
            path.unlink()

    def install_baseline(self):
        backup = b"synthetic backup; package_files mocked only for stage sequencing"
        (self.run / "QtPreimage.zip").write_bytes(backup)
        gate.write(self.run, "Baseline.json", {"files": {}, "backupSha256": gate.sha(backup)})

    def test_changed_owner_between_prepare_install_refuses_before_pip(self):
        self.prepare()
        self.install_baseline()
        self.make_owner(version="6.11.0")
        with patch.object(gate, "FORMAL", self.site.parents[1]), \
             patch.object(gate, "package_files", return_value={}), patch.object(gate, "pip") as pip:
            with self.assertRaisesRegex(RuntimeError, "owner/version/path"):
                gate.install(self.run)
            pip.assert_not_called()

    def test_write_denial_stops_before_pip_and_keeps_evidence(self):
        self.prepare()
        self.install_baseline()
        with patch.object(gate, "FORMAL", self.site.parents[1]), \
             patch.object(gate, "package_files", return_value={}), patch.object(gate, "pip") as pip, \
             patch.object(gate.tempfile, "NamedTemporaryFile", side_effect=PermissionError("synthetic denied")):
            with self.assertRaises(PermissionError):
                gate.install(self.run)
            pip.assert_not_called()
        self.assertEqual(json.loads((self.run / "WriteAccess.json").read_text())["status"], "BLOCKED_BEFORE_PIP")
        self.assertFalse((self.run / "install.json").exists())

    def test_real_write_probe_then_only_derived_wheel_passed_to_pip(self):
        self.prepare()
        self.install_baseline()
        with patch.object(gate, "FORMAL", self.site.parents[1]), \
             patch.object(gate, "package_files", return_value={}), \
             patch.object(gate, "installed_ownership", return_value={"mode": "SYNTHETIC"}), \
             patch.object(gate, "pip", return_value=SimpleNamespace(returncode=0)) as pip:
            gate.install(self.run)
            self.assertEqual(Path(pip.call_args.args[-1]).name, gate.DERIVED_FILENAME)
            self.assertIn("--no-compile", pip.call_args.args)
        self.assertEqual(json.loads((self.run / "WriteAccess.json").read_text())["status"], "PASS")
        self.assertFalse(list(self.site.rglob(".w6-write-probe-*")))

    def test_real_pip_install_and_uninstall_preserve_essentials(self):
        # A venv WITHOUT pip: host pip explicitly targets its Python, never formal.
        env = self.root / "pip-fixture"
        subprocess.run([sys.executable, "-I", "-B", "-m", "venv", "--without-pip", str(env)], check=True, capture_output=True)
        self.site = env / "Lib/site-packages"
        for name in (SHARED, "PySide6/QtWebChannel.pyi"):
            path = self.site / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(self.payload[name])
        self.make_owner()
        receipt, derived = self.prepare()
        cache = self.site / "PySide6/__pycache__"
        cache.mkdir()
        for name in ("__init__.cpython-310.pyc", "__init__.cpython-310.opt-1.pyc"):
            (cache / name).write_bytes(b"synthetic Essentials bytecode; must survive Addons uninstall")
        before = {p.relative_to(self.site).as_posix(): p.read_bytes() for p in self.site.rglob("*") if p.is_file()}
        python = env / "Scripts/python.exe"
        self.assertNotEqual(python.resolve(), Path(sys.executable).resolve())
        argv = [sys.executable, "-I", "-B", "-m", "pip", "--isolated", "--disable-pip-version-check", "--python", str(python)]
        local_env = {**os.environ, "TEMP": str(self.root), "TMP": str(self.root)}
        target = self.run / "install-wheel" / gate.DERIVED_FILENAME
        result = subprocess.run(argv + ["install", "--no-index", "--no-deps", "--no-compile", "--no-cache-dir", str(target)], capture_output=True, env=local_env)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        with patch.object(gate, "FORMAL", env):
            proof = gate.installed_ownership(self.run)
            self.assertEqual(proof["sharedEssentialsFiles"], 2)
            # An old/raw-wheel RECORD would be unsafe even if pip install exited 0.
            record = self.site / INFO / "RECORD"
            saved = record.read_bytes()
            record.write_bytes(saved + csv_data([[SHARED, gate.record_hash(self.payload[SHARED]), str(len(self.payload[SHARED]))]]))
            gate.write(self.run, "install.json", {"exit": 0})
            gate.write(self.run, "Baseline.json", {"files": {}})
            with patch.object(gate, "package_files", return_value={}), patch.object(gate, "pip") as pip:
                with self.assertRaisesRegex(RuntimeError, "file set mismatch"):
                    gate.rollback(self.run)
                pip.assert_not_called()
            record.write_bytes(saved)
        result = subprocess.run(argv + ["uninstall", "--yes", "PySide6-Addons"], capture_output=True, env=local_env)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        after = {p.relative_to(self.site).as_posix(): p.read_bytes() for p in self.site.rglob("*") if p.is_file()}
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
