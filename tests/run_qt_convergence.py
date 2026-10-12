"""Bounded, offline Qt convergence regression runner. Never boots the user desktop."""
from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", choices=["python", "node"], required=True)
    args = parser.parse_args()
    records = []
    with tempfile.TemporaryDirectory(prefix=".validation-temp-convergence-", dir=ROOT) as folder:
        env = os.environ.copy()
        env.update(TEMP=folder, TMP=folder, QT_QPA_PLATFORM="offscreen",
                   PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8",
                   PYTHONPATH=os.pathsep.join([str(ROOT/"Open-LLM-VTuber/src"), str(ROOT/"Open-LLM-VTuber"), str(ROOT)]))
        env.pop("NODE_COMPILE_CACHE", None)
        if args.group == "python":
            # Refuse all non-loopback outbound sockets and the user's shared/live ports.
            bootstrap = """import socket,sys,unittest
original=socket.socket.connect
def bounded(self,address):
 if isinstance(address,tuple):
  host,port=address[:2]
  if host not in {'127.0.0.1','localhost','::1'} or port in {18890,23456,23567,23568,23569}:
   raise AssertionError('Live network prohibited in convergence validation')
 return original(self,address)
socket.socket.connect=bounded
result=unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.discover('tests',pattern=sys.argv[1]))
sys.exit(not result.wasSuccessful())
"""
            commands = [(path.name, [sys.executable, "-B", "-c", bootstrap, path.name])
                        for path in sorted((ROOT/"tests").glob("test_*.py"))]
        else:
            # Electron/manual model smokes are separate and never implicitly executed.
            paths = sorted([*(ROOT/"tests").glob("*.test.cjs"), *(ROOT/"tests").glob("*.test.mjs")])
            commands = [("node-regression", ["node", "--test", *map(str, paths)])]
        for label, command in commands:
            started = time.monotonic()
            try:
                process = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                    text=True, encoding="utf-8", errors="replace", timeout=90,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                output = process.stdout + process.stderr
                match = re.search(r"Ran (\d+) tests?", output) if args.group == "python" else re.search(r"(?:tests |# tests )(\d+)", output)
                count = int(match.group(1)) if match else None
                record = {"suite": label, "tests": count, "exit": process.returncode,
                          "elapsed_ms": round((time.monotonic()-started)*1000)}
                if process.returncode:
                    print(output[-14000:], flush=True)
            except subprocess.TimeoutExpired:
                record = {"suite": label, "tests": None, "exit": "TIMEOUT", "elapsed_ms": 90000}
            records.append(record)
            print(json.dumps(record), flush=True)
    total = sum(record["tests"] or 0 for record in records)
    ok = all(record["exit"] == 0 for record in records)
    print(json.dumps({"group": args.group, "tests": total, "ok": ok, "suites": len(records)}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
