"""Bounded normal-user relay for two sequential isolated native lifecycles.

No install, environment override, production entry, process kill or adoption.
Captures actual OS exits separately from each child's reported test verdict.
"""
import argparse
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FORMAL = ROOT / "envs/kuro-llm310"


def read_receipt(path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError): return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt" or Path(sys.prefix).resolve() != FORMAL or not sys.flags.isolated or not sys.dont_write_bytecode:
        parser.error("Use formal Windows Python -I -B")
    output = args.output.absolute()
    if output.resolve() != output or not output.is_relative_to(HERE / ".runtime") or output.exists():
        parser.error("New task-local output required")
    output.mkdir(parents=True)
    result = {"contract": "kuro.w6.native-relay.v1", "productionAdoption": False, "w7Started": False,
        "humanApproval": "UNVERIFIED", "status": "BLOCKED", "processes": []}
    def save(): (output / "RelayResult.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    save()
    with (output / "NativeConsole.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-I", "-B", str(HERE / "w6_existing_window.py"),
            "--output", str(output / "first")], cwd=ROOT, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        entry = {"role": "first", "pid": process.pid, "actualExit": None}; result["processes"].append(entry); save()
        try: entry["actualExit"] = process.wait(timeout=200)
        except subprocess.TimeoutExpired:
            result["error"] = "Owned harness deadline; no process was killed"; save(); return 2
    first = read_receipt(output / "first/NativeResult.json")
    entry["receipt"] = str(output / "first/NativeResult.json")
    entry["reportedExit"] = (first or {}).get("exit")
    save()
    if not first or not first.get("restartLaunched"):
        result["error"] = "First lifecycle did not reach isolated restart"; save(); return 2
    deadline = time.monotonic() + 200
    child_path = output / "first/restarted/NativeResult.json"
    second = None
    while time.monotonic() < deadline:
        second = read_receipt(child_path)
        if second and second.get("pid"): break
        time.sleep(.1)
    if not second:
        result["error"] = "Restart receipt unavailable"; save(); return 2
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; kernel.OpenProcess.restype = w.HANDLE
    kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    kernel.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.OpenProcess(0x00101000, False, second["pid"])
    restarted = {"role": "restarted", "pid": second["pid"], "actualExit": None, "receipt": str(child_path)}
    result["processes"].append(restarted); save()
    if handle:
        try:
            while time.monotonic() < deadline:
                if kernel.WaitForSingleObject(handle, 100) == 0:
                    code = w.DWORD()
                    if kernel.GetExitCodeProcess(handle, ctypes.byref(code)): restarted["actualExit"] = code.value
                    break
        finally: kernel.CloseHandle(handle)
    else: restarted["exitObservationError"] = ctypes.get_last_error()
    second = read_receipt(child_path) or second
    restarted["reportedExit"] = second.get("exit")
    result["verdicts"] = {"first": first.get("native"), "restarted": second.get("native")}
    result["restartObserved"] = first.get("namespace") == second.get("namespace") and any(
        row["name"] == "restart-parent-exited" and row["pass"] for row in second.get("checks", []))
    if (all(p["actualExit"] == 0 and p["reportedExit"] == 0 for p in result["processes"])
            and result["restartObserved"] and all(r.get("coverage", {}).get("pass") for r in (first, second))
            and all(r.get("sourceUnchangedDuringRun") for r in (first, second))
            and all(v == "AUTOMATED_EXISTING_WINDOW_PASS" for v in result["verdicts"].values())):
        result["status"] = "AUTOMATED_NATIVE_PAIR_PASS"
    save(); print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["status"] == "AUTOMATED_NATIVE_PAIR_PASS" else 2


if __name__ == "__main__": raise SystemExit(main())
