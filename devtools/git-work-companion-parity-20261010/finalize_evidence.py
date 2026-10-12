"""Freeze allowlisted source/diff evidence and audit the original WIP hashes."""
from pathlib import Path
import ast
from datetime import datetime, timezone
import difflib
import hashlib
import json
import re
import struct
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def write_json(name, data):
    (HERE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

baseline = json.loads((HERE / "Baseline.json").read_text(encoding="utf-8"))
before = {item["path"]: item for item in baseline["entries"]}
backups = {p.relative_to(HERE / "rollback").as_posix()[:-7]: p
           for p in (HERE / "rollback").rglob("*.before")}
changed_test_without_original_bytes = "tests/test_g3_conversation.py"
new_source = ["tests/run_work_companion_parity.py", "tests/work_companion_fixture.py",
              "tests/test_work_companion_source_encoding.py",
              *[p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "tests").glob("test_r[1234]_*.py"))]]
allowlist = set(backups) | {changed_test_without_original_bytes} | set(new_source)
audit, unexpected = [], []
for path, entry in before.items():
    current = ROOT / path
    actual = digest(current.read_bytes()) if current.is_file() else None
    changed = actual != entry["sha256"]
    if changed and path not in allowlist:
        unexpected.append(path)
    audit.append({**entry, "after_sha256": actual, "changed": changed,
                  "authorized_task_file": path in allowlist})
head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, check=True).stdout.decode().strip()
assert head == baseline["head"], "HEAD changed; do not freeze misleading evidence"
assert not unexpected, unexpected
write_json("WIPIntegrity.json", {"head": head, "initial_entries": len(audit),
    "unchanged": sum(not i["changed"] for i in audit), "authorized_changes": sum(i["changed"] for i in audit),
    "unexpected_changes": unexpected, "entries": audit})

deltas = []
for path in sorted(allowlist):
    target = ROOT / path
    backup = backups.get(path)
    original = backup.read_bytes() if backup else None
    current = target.read_bytes() if target.is_file() else None
    if path in before and original is not None:
        assert digest(original) == before[path]["sha256"], f"Baseline mismatch: {path}"
    if current is not None:
        source = current.decode("utf-8-sig", errors="strict")
        if target.suffix == ".py":
            ast.parse(source, filename=path)
            compile(source, path, "exec")
        snapshot = HERE / "after-source" / path
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(current)
    record = {"path": path,
        "before_sha256": digest(original) if original is not None else before.get(path, {}).get("sha256"),
        "after_sha256": digest(current) if current is not None else None,
        "before_bytes_available": original is not None,
        "new_file": path in new_source and path not in before,
        "retired": current is None}
    if original is not None or record["new_file"]:
        difference = "".join(difflib.unified_diff(
            (original or b"").decode("utf-8-sig").splitlines(keepends=True),
            (current or b"").decode("utf-8-sig").splitlines(keepends=True),
            fromfile="before/" + path, tofile="after/" + path))
        patch = HERE / "delta" / (path + ".patch")
        patch.parent.mkdir(parents=True, exist_ok=True)
        patch.write_bytes(difference.encode("utf-8"))
        record["patch"] = patch.relative_to(HERE).as_posix()
    deltas.append(record)
write_json("DeltaManifest.json", {"head": head, "files": deltas,
    "rollback_gap": {"path": changed_test_without_original_bytes,
        "reason": "Before hash retained, but exact pre-edit bytes were not captured. Do not claim byte-exact test-file rollback."}})

manifest = json.loads((ROOT / "docs/agent-runs/qt-ui-convergence-20261007/G7DeletionManifest.json").read_text(encoding="utf-8-sig"))
g7 = [{"path": item["path"], "absent": not (ROOT / item["path"]).exists()} for item in manifest["files"]]
assert len(g7) == 35 and all(item["absent"] for item in g7)
write_json("G7Absence.json", {"total": 35, "absent": 35, "files": g7})

latest = {}
dpi = {}
for report_path in sorted((HERE / "test-runs").glob("*/results.json")):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for suite in report["suites"]:
        entry = {**suite, "evidence": report_path.relative_to(HERE).as_posix(),
                 "scale": report.get("qt_scale_factor", "1"), "start_dir": report["start_dir"]}
        if entry["scale"] == "1":
            latest[report["start_dir"], suite["suite"]] = entry
        else:
            dpi[entry["scale"], entry["start_dir"], entry["suite"]] = entry
assert latest and all(item["exit"] == 0 and item["tests"] for item in latest.values())
assert all(item["exit"] == 0 for item in dpi.values())
node = (HERE / "NodeOwnerRegression.txt").read_text(encoding="utf-8")
node_count = int(re.search(r"(?:# |ℹ )tests (\d+)", node).group(1))
assert re.search(r"(?:# |ℹ )fail 0\b", node)
write_json("ValidationSummary.json", {"scope": "SOURCE_AND_ISOLATED_ONLY", "desktop": "UNVERIFIED",
    "reviewer": "PENDING_STATIC_REVIEW", "python_unique_tests": sum(i["tests"] for i in latest.values()),
    "python_suites": len(latest), "node_tests": node_count, "node_output_sha256": digest(node.encode("utf-8")),
    "latest_suites": list(latest.values()), "additional_dpi_runs": list(dpi.values())})

images = []
for path in sorted(HERE.glob("R*-offscreen.png")):
    raw = path.read_bytes()
    width, height = struct.unpack(">II", raw[16:24])
    images.append({"path": path.name, "sha256": digest(raw), "physical_pixels": [width, height],
                   "surface": "Production WorkCompanionView", "data": "SYNTHETIC_FIXTURE",
                   "desktop_and_exact_screenshot_fidelity": "UNVERIFIED"})
write_json("OffscreenEvidence.json", images)
status = subprocess.run(["git", "-c", "core.quotepath=false", "status", "--short", "--branch", "--untracked-files=normal"],
                        cwd=ROOT, capture_output=True, check=True).stdout
(HERE / "FinalGitStatus.txt").write_bytes(status)
check = subprocess.run(["git", "diff", "--check", "--", *sorted(allowlist)], cwd=ROOT, capture_output=True)
(HERE / "DiffCheck.txt").write_bytes(check.stdout + check.stderr)
assert check.returncode == 0, "Diff check failed"
print(json.dumps({"python_unique_tests": sum(i["tests"] for i in latest.values()), "node_tests": node_count,
                  "wip_unchanged": sum(not i["changed"] for i in audit), "unexpected": unexpected,
                  "g7_absent": 35, "delta_files": len(deltas), "rollback_bytes": len(backups),
                  "rollback_test_gap": changed_test_without_original_bytes}))
