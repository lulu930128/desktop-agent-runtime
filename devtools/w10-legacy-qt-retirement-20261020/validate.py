"""Bounded W10 current-source acceptance. Never launch production services."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "docs/agent-runs/w10-legacy-qt-retirement-20261020/SourceBaseline.json"
PYTHON_SUITES = (
    "test_qt_web_w10", "test_launcher_entrypoint", "test_work_companion_source_encoding",
    "test_qt_web_candidate", "test_qt_web_transport", "test_qt_web_disposable",
    "test_qt_web_existing_window", "test_qt_web_security", "test_qt_web_w4_w5",
    "test_r1_history_parity", "test_r2_settings_parity", "test_r3_today_schedule_parity",
    "test_r4_history_transport", "test_g3_conversation", "test_g4_qt_core",
    "test_g5_desktop", "test_g6_pet_boundary", "test_g8_runtime",
    "test_schedule_core", "test_schedule_notifications", "test_schedule_api",
    "test_schedule_runtime", "test_web_notification_commands", "test_v1_work_companion_view",
    "test_qt_web_window_chrome.GestureProtocolTests",
)
HISTORICAL_EXCLUSIONS = {
    "test_qt_web_w6": "W6 source graph and explicit Widgets rollback checkpoint; W10 replaces both.",
    "test_qt_web_release_candidate": "W6 exact source SHA/receipt proposal; not a current W10 gate.",
    "test_qt_web_window_chrome.W7BundleTests": "W7 fixed source SHA; source drift is expected.",
    "test_qt_web_window_chrome.ChromeWindowTests": "Historical constructor/Widgets rollback fixture.",
    "test_qt_web_w8": "W8 fixed source SHA/Widgets rollback; current tray/chrome tests ported to W10.",
    "test_r1_production_view": "Retired Widgets drawer; Web WS CRUD/timeline is in r4_history_transport.",
    "work_companion_fixture": "Retired private-QSettings Widgets constructor fixture.",
}
BOOTSTRAP = r"""
import os,socket,sys,unittest
from pathlib import Path
root=Path.cwd()
sys.path[:0]=[str(root/'tests'),str(root/'Open-LLM-VTuber/src'),str(root/'Open-LLM-VTuber')]
original=socket.socket.connect
def bounded(self,address):
 if isinstance(address,tuple):
  host,port=address[:2]
  if host not in {'127.0.0.1','localhost','::1'} or port in {1188,18890,23456,23567,23568,23569}:
   raise AssertionError('Live network prohibited in W10 validation')
 return original(self,address)
socket.socket.connect=bounded
suite=unittest.defaultTestLoader.loadTestsFromName(sys.argv[1])
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful() or result.testsRun == 0 or bool(result.skipped))
"""


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_source():
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    for relative, expected in baseline["sha256"].items():
        path = ROOT / relative
        if not path.is_file() or digest(path) != expected:
            raise ValueError("W10 source drift: " + relative)
    for relative in baseline["removed"]:
        if (ROOT / relative).exists():
            raise ValueError("W10 retired source restored: " + relative)
    # Syntax is checked without __pycache__ or imports of runtime/private state.
    for relative in baseline["syntaxSources"]:
        compile((ROOT / relative).read_bytes().decode("utf-8-sig"), relative, "exec")
    return digest(BASELINE)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", choices=PYTHON_SUITES, nargs="+",
                        help="Development-only subset; can never produce W10 profile PASS")
    args = parser.parse_args()
    output = args.output.resolve()
    temp_root = (ROOT / ".tmp").resolve()
    if not output.is_relative_to(temp_root):
        parser.error("Evidence must stay in the approved repo .tmp directory")
    output.mkdir(parents=True, exist_ok=False)
    baseline_digest = None if args.target else verify_source()
    names = args.target or PYTHON_SUITES
    commands = [(name, [sys.executable, "-B", "-c", BOOTSTRAP, name]) for name in names]
    if not args.target:
        commands.append(("qt_web_frontend", ["node", "--test", "tests/qt_web_frontend.test.cjs"]))
    scope = dict(profile="targeted-development" if args.target else "w10-current",
                 baselineSha256=baseline_digest, nativeAcceptance=False,
                 productionAdoption=False, historicalExclusions=HISTORICAL_EXCLUSIONS,
                 suites=[n for n, _ in commands])
    (output / "Scope.json").write_text(json.dumps(scope, indent=2), encoding="utf-8")
    records = []
    with tempfile.TemporaryDirectory(prefix="isolated-", dir=output) as folder:
        env = os.environ.copy()
        env.update(TEMP=folder, TMP=folder, QT_QPA_PLATFORM="offscreen",
                   PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8",
                   KURO_MEMORY_ROOT=str(Path(folder) / "memory"),
                   PYTHONPATH=os.pathsep.join([str(ROOT), str(ROOT / "Open-LLM-VTuber/src"),
                                              str(ROOT / "Open-LLM-VTuber")]))
        env.pop("NODE_COMPILE_CACHE", None)
        # No sandbox/GPU overrides. These tests use inert surfaces and real
        # Qt signal queues/loopback owners, not a production Chromium renderer.
        for name, command in commands:
            started = time.monotonic()
            try:
                run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                    text=True, encoding="utf-8", errors="replace", timeout=120,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                log, code = run.stdout + run.stderr, run.returncode
            except subprocess.TimeoutExpired:
                log, code = "Bounded suite timed out after 120 seconds", "TIMEOUT"
            (output / (name + ".log")).write_text(log, encoding="utf-8")
            match = re.search(r"Ran (\d+) tests?", log) or re.search(r"(?:# )?tests (\d+)", log)
            row = dict(suite=name, exit=code, tests=int(match[1]) if match else 0,
                       elapsed_ms=round((time.monotonic() - started) * 1000))
            if not row["tests"] and code == 0:
                row["exit"] = "NO_TESTS"
            records.append(row)
            (output / "Results.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
            print(json.dumps(row), flush=True)
    unchanged = bool(args.target) or verify_source() == baseline_digest
    passed = unchanged and all(r["exit"] == 0 for r in records)
    receipt = dict(scope, status=("TARGETED_PASS" if args.target else "W10_SOURCE_ISOLATED_PASS") if passed else "FAIL",
                   sourceUnchangedDuringRun=unchanged if not args.target else None,
                   tests=sum(r["tests"] for r in records), results=records)
    (output / "Receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
