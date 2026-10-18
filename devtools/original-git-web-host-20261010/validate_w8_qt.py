"""Bounded Qt-only regressions; no production start, reload or Pet candidate run."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BOOTSTRAP = """import socket,sys,unittest
original=socket.socket.connect
def bounded(self,address):
 if isinstance(address,tuple):
  host,port=address[:2]
  if host not in {'127.0.0.1','localhost','::1'} or port in {1188,18890,23456,23567,23568,23569}:
   raise AssertionError('Live network prohibited in W8 validation')
 return original(self,address)
socket.socket.connect=bounded
suite=unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])
r=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not r.wasSuccessful() or r.testsRun == 0)
"""
QT_SUITES = [
    'test_qt_web_w8', 'test_g5_desktop', 'test_g4_qt_core',
    'test_qt_web_transport', 'test_qt_web_w6',
    'test_qt_web_window_chrome.ChromeWindowTests',
    'test_qt_web_window_chrome.GestureProtocolTests',
    'test_qt_web_window_chrome.W7BundleTests.test_w7_profile_requires_full_release_coverage_except_historical_w6_gate',
    'test_qt_web_window_chrome.W7BundleTests.test_w7_pin_matches_current_builder_and_originals_without_reusing_w6_acceptance',
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        parser.error('Evidence output must be inside this repository')
    output.mkdir(parents=True, exist_ok=False)
    temp = output / 'temp'
    temp.mkdir()
    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen', PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8',
               TEMP=str(temp), TMP=str(temp),
               PYTHONPATH=os.pathsep.join([str(ROOT), str(ROOT / 'tests'), str(ROOT / 'Open-LLM-VTuber/src')]))
    env.pop('NODE_COMPILE_CACHE', None)
    commands = [
        ('qt', [sys.executable, '-B', '-c', BOOTSTRAP, *QT_SUITES]),
        ('qt-frontend', ['node', '--test', 'tests/qt_web_frontend.test.cjs']),
        ('source-gate', [sys.executable, '-I', '-B', str(HERE / 'w8_qt_tray_gate.py')]),
        ('syntax', [sys.executable, '-B', '-c',
                    "from pathlib import Path; [compile(Path(n).read_text(encoding='utf-8'),n,'exec') for n in "
                    + repr(['kuro_launcher/qt_app.py', 'kuro_launcher/qt_branding.py', 'tests/test_qt_web_w8.py',
                            str(HERE / 'w8_qt_tray_gate.py'), str(HERE / 'validate_w8_qt.py')]) + "]"]),
        ('diff-check', ['git', 'diff', '--check']),
    ]
    records = []
    for name, command in commands:
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=120)
        text = result.stdout + result.stderr
        (output / (name + '.log')).write_text(text, encoding='utf-8')
        match = re.search(r'Ran (\d+) tests?', text) or re.search(r'(?:# )?tests (\d+)', text)
        record = dict(suite=name, exit=result.returncode, tests=int(match[1]) if match else None,
                      command=command)
        records.append(record)
        (output / 'Results.json').write_text(json.dumps(dict(
            records=records, qtSuites=QT_SUITES, nativeAcceptance='UNVERIFIED',
            petRepair='BLOCKED_PERMISSION_DENIED', productionAdoption=False), indent=2), encoding='utf-8')
        print(json.dumps({k: record[k] for k in ('suite', 'exit', 'tests')}), flush=True)
    return int(any(record['exit'] != 0 for record in records))


if __name__ == '__main__':
    raise SystemExit(main())
