"""Bounded source validation, including the W6 existing-window Web branch."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BOOTSTRAP = """import socket,sys,unittest
original=socket.socket.connect
def bounded(self,address):
 if isinstance(address,tuple):
  host,port=address[:2]
  if host not in {'127.0.0.1','localhost','::1'} or port in {1188,18890,23456,23567,23568,23569}:
   raise AssertionError('Live network prohibited in candidate validation')
 return original(self,address)
socket.socket.connect=bounded
r=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover(sys.argv[1],pattern=sys.argv[2]))
sys.exit(not r.wasSuccessful() or r.testsRun == 0)
"""

RELEASE_SUITES = frozenset({
    'typecheck', 'qt_web_candidate', 'qt_web_assets', 'qt_web_transport',
    'qt_web_w4_w5', 'qt_web_disposable', 'qt_web_w6', 'qt_web_existing_window',
    'qt_web_security', 'qt_web_release_candidate', 'web_notification_commands',
    'schedule_core', 'schedule_notifications', 'schedule_api', 'schedule_runtime',
    'g3_conversation', 'g4_qt_core', 'g5_desktop', 'g6_pet_boundary', 'g8_runtime',
    'r1_history_parity', 'r2_settings_parity', 'r3_today_schedule_parity',
    'r4_history_transport', 'qt_web_frontend', 'g3_presentation',
    'g5_desktop_owner', 'g6_pet_shell',
})


def select_commands(commands, profile, only):
    available = {name for name, *_ in commands}
    if profile == 'release-candidate' and only is not None:
        raise ValueError('Release profile cannot omit required suites with --only')
    selected = RELEASE_SUITES if profile == 'release-candidate' else (set(only) if only is not None else available)
    if not selected or selected - available:
        raise ValueError('Empty or unknown validation suite selection')
    return [row for row in commands if row[0] in selected]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--only', nargs='*')
    parser.add_argument('--profile', choices=('default', 'release-candidate'), default='default')
    args = parser.parse_args()
    commands = [
        ('typecheck', ['node', '../../../pet-electron/node_modules/typescript/bin/tsc', '--project', 'tsconfig.json', '--noEmit'], HERE/'frontend'),
        ('original-build', ['node', '../../../pet-electron/node_modules/vite/bin/vite.js', 'build', '--config', 'vite.config.mjs'], HERE/'frontend'),
        ('candidate-build', ['node', '../../../pet-electron/node_modules/vite/bin/vite.js', 'build', '--config', 'vite.owner.config.mjs'], HERE/'frontend'),
        ('formal-addons', [sys.executable, '-B', '-c', 'from PySide6.QtWebChannel import QWebChannel; from PySide6.QtWebEngineWidgets import QWebEngineView; from PySide6.QtCore import qVersion; print(qVersion())'], ROOT),
    ]
    suites = ['qt_web_candidate', 'qt_web_assets', 'qt_web_transport', 'qt_web_w4_w5', 'qt_web_disposable', 'qt_web_w6', 'qt_web_existing_window', 'qt_web_security', 'qt_web_release_candidate', 'web_notification_commands',
              'schedule_core', 'schedule_notifications', 'schedule_api', 'schedule_runtime',
              'g3_conversation', 'g4_qt_core', 'g5_desktop', 'g6_pet_boundary', 'g8_runtime',
              'r1_history_parity', 'r2_settings_parity', 'r3_today_schedule_parity', 'r4_history_transport']
    commands += [(s, [sys.executable, '-B', '-c', BOOTSTRAP, 'tests', 'test_'+s+'.py'], ROOT) for s in suites]
    commands += [(s, [sys.executable, '-B', '-c', BOOTSTRAP, str(HERE), 'test_'+s+'.py'], ROOT)
                 for s in ['parity_collection', 'parity_diagnosis', 'w1_smoke', 'deep_comparison', 'w1_convergence', 'preview_protocol', 'candidate_native_relay']]
    commands += [(s, ['node', '--test', str(ROOT/'tests'/ (s+'.test.cjs'))], ROOT)
                 for s in ['qt_web_frontend', 'g3_presentation', 'g5_desktop_owner', 'g6_pet_shell']]
    commands += [(s, ['node', '--test', str(HERE/(s+'.cjs'))], ROOT)
                 for s in ['test_geometry', 'test_deep_geometry', 'test_typography', 'preview_bridge.test']]
    try:
        commands = select_commands(commands, args.profile, args.only)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'Scope.json').write_text(json.dumps(dict(profile=args.profile,
        suites=[name for name, *_ in commands], productionAdoption=False,
        nativeAcceptance=False, note='Isolated source regressions; raw user native receipts are reviewed separately'), indent=2), encoding='utf-8')
    records = []
    with tempfile.TemporaryDirectory(prefix='.validation-web-final-', dir=ROOT) as folder:
        env = os.environ.copy()
        env.update(TEMP=folder, TMP=folder, QT_QPA_PLATFORM='offscreen', PYTHONDONTWRITEBYTECODE='1',
                   PYTHONIOENCODING='utf-8', PYTHONPATH=os.pathsep.join([str(ROOT/'Open-LLM-VTuber/src'), str(ROOT/'Open-LLM-VTuber'), str(ROOT)]))
        env.pop('NODE_COMPILE_CACHE', None)
        for name, command, cwd in commands:
            started = time.monotonic()
            try:
                p = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True,
                    encoding='utf-8', errors='replace', timeout=120,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                output, code = p.stdout+p.stderr, p.returncode
            except subprocess.TimeoutExpired as exc:
                output, code = str(exc), 'TIMEOUT'
            (args.output/(name+'.log')).write_text(output, encoding='utf-8')
            match = re.search(r'Ran (\d+) tests?', output) or re.search(r'(?:# )?tests (\d+)', output)
            record = dict(suite=name, command=command, cwd=str(cwd), exit=code,
                          tests=int(match[1]) if match else None, elapsed_ms=round((time.monotonic()-started)*1000))
            records.append(record)
            (args.output/'Results.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
            print(json.dumps(record), flush=True)
    return int(any(r['exit'] != 0 for r in records))


if __name__ == '__main__': raise SystemExit(main())
