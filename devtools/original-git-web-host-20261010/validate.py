"""Bounded source checks; offline tests only, never starts production services."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FRONTEND = HERE / "frontend"
RUNTIME = HERE / ".runtime/validation"
BOOTSTRAP = """import socket,sys,unittest
original=socket.socket.connect
def bounded(self,address):
 if isinstance(address,tuple):
  host,port=address[:2]
  if host not in {'127.0.0.1','localhost','::1'} or port in {1188,18890,23456,23567,23568,23569}:
   raise AssertionError('Live network prohibited in original renderer validation')
 return original(self,address)
socket.socket.connect=bounded
result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover('tests',pattern=sys.argv[1]))
sys.exit(not result.wasSuccessful())
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="+")
    args = parser.parse_args()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(TEMP=str(RUNTIME), TMP=str(RUNTIME), QT_QPA_PLATFORM="offscreen",
               PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8",
               PYTHONPATH=os.pathsep.join([str(ROOT / "Open-LLM-VTuber/src"), str(ROOT / "Open-LLM-VTuber"), str(ROOT)]))
    env.pop("NODE_COMPILE_CACHE", None)
    qt_python = ROOT / "envs/kuro-llm310/python.exe"
    jobs = [("preview-protocol", [sys.executable, "-B", str(HERE / "test_preview_protocol.py")], ROOT),
            ("preview-bridge", ["node", "--test", str(HERE / "preview_bridge.test.cjs")], ROOT),
            ("frontend-typecheck", ["node", str(ROOT / "pet-electron/node_modules/typescript/bin/tsc"), "--project", "tsconfig.json", "--noEmit"], FRONTEND),
            ("frontend-build", ["node", str(ROOT / "pet-electron/node_modules/vite/bin/vite.js"), "build", "--config", "vite.config.mjs"], FRONTEND)]
    for name in ["test_g3_conversation.py", "test_g4_qt_core.py", "test_g5_desktop.py", "test_g6_pet_boundary.py", "test_g8_runtime.py"]:
        jobs.append((name, [str(qt_python), "-B", "-c", BOOTSTRAP, name], ROOT))
    jobs.extend([
        ("pet-owner-regression", ["node", "--test", "tests/g3_presentation.test.cjs", "tests/g5_desktop_owner.test.cjs", "tests/g6_pet_shell.test.cjs"], ROOT),
        ("pet-renderer-typecheck", ["node", "node_modules/typescript/bin/tsc", "--project", "tsconfig.renderer.json", "--noEmit"], ROOT / "pet-electron"),
        # Preserve the existing renderer-dist and Live2D assets. Only output moves.
        ("pet-renderer-build-isolated-output", ["node", "node_modules/vite/bin/vite.js", "build", "--config", "vite.renderer.config.ts", "--outDir", str(RUNTIME / "pet-renderer-dist")], ROOT / "pet-electron")
    ])
    receipt = HERE / ("ValidationFollowup.json" if args.only else "Validation.json")
    results = json.loads(receipt.read_text(encoding="utf-8")) if args.only and receipt.exists() else []
    if args.only:
        unknown = set(args.only) - {name for name, _, _ in jobs}
        if unknown:
            parser.error("Unknown checks: " + ", ".join(sorted(unknown)))
        jobs = [job for job in jobs if job[0] in args.only]
    for name, command, cwd in jobs:
        try:
            process = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True,
                                     encoding="utf-8", errors="replace", timeout=90,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            row = {"name": name, "command": command, "cwd": str(cwd), "exit": process.returncode,
                   "stdout": process.stdout, "stderr": process.stderr}
        except (OSError, subprocess.TimeoutExpired) as exc:
            row = {"name": name, "command": command, "cwd": str(cwd), "exit": "BLOCKED", "error": str(exc)}
        results = [previous for previous in results if previous["name"] != name] + [row]
        receipt.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({key: row[key] for key in ["name", "exit"]}), flush=True)
    return int(any(row["exit"] != 0 for row in results))


if __name__ == "__main__":
    raise SystemExit(main())
