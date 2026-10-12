"""No-install Qt import/registration probe. Never constructs an app or owner.

Run with the exact interpreter's -I -B flags. Output is new task-local evidence;
exit 0 is prerequisite evidence only, never formal adoption authorization.
"""
import argparse
from datetime import datetime, timezone
import importlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FORMAL = ROOT / "envs/kuro-llm310"
MODULES = ("PySide6", "shiboken6", "PySide6.QtCore", "PySide6.QtWidgets",
           "PySide6.QtWebChannel", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets")
PACKAGES = ("PySide6-Essentials", "PySide6-Addons", "shiboken6")


def probe(expected_prefix):
    expected = Path(expected_prefix).resolve()
    result = dict(utc=datetime.now(timezone.utc).isoformat(), executable=sys.executable,
                  prefix=sys.prefix, python=sys.version, expectedPrefix=str(expected),
                  formalInterpreter=Path(sys.prefix).resolve() == FORMAL.resolve(), modules={}, packages={},
                  applicationCreated=False, productionAdoption=False, w7Started=False)
    blockers = []
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        blockers.append("Run this probe with -I -B")
    if Path(sys.prefix).resolve() != expected or not Path(sys.executable).resolve().is_relative_to(expected):
        blockers.append("Interpreter/prefix does not match expected environment")
    # Record names only: environment values may contain private paths or tokens.
    overrides = [n for n in ("QTWEBENGINE_DISABLE_SANDBOX", "QTWEBENGINE_CHROMIUM_FLAGS",
                             "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH",
                             "QTWEBENGINEPROCESS_PATH", "QTWEBENGINE_RESOURCES_PATH",
                             "QTWEBENGINE_LOCALES_PATH", "QT_QPA_PLATFORM") if os.environ.get(n)]
    result["overrideNames"] = overrides
    if overrides:
        blockers.append("Qt runtime overrides present; run in a clean normal-user shell")
    for name in MODULES:
        try:
            module = importlib.import_module(name)
            origin = Path(module.__file__).resolve(strict=True)
            result["modules"][name] = dict(status="PASS", origin=str(origin))
            if not origin.is_relative_to(expected):
                blockers.append("Module outside expected environment: " + name)
        except Exception as exc:
            result["modules"][name] = dict(status="BLOCKED", errorType=type(exc).__name__, error=str(exc))
            blockers.append("Import failed: " + name)
    for name in PACKAGES:
        try:
            dist = importlib.metadata.distribution(name)
            location = Path(dist.locate_file("")).resolve()
            result["packages"][name] = dict(version=dist.version, location=str(location))
            if not location.is_relative_to(expected):
                blockers.append("Distribution outside expected environment: " + name)
        except Exception as exc:
            result["packages"][name] = dict(errorType=type(exc).__name__, error=str(exc))
            blockers.append("Distribution unavailable: " + name)
    versions = [r.get("version") for r in result["packages"].values()]
    if None in versions or len(set(versions)) != 1:
        blockers.append("Essentials/Addons/shiboken versions must exactly match")
    try:
        from PySide6.QtCore import qVersion, QLibraryInfo
        result["qtVersion"] = qVersion()
        result["qtLibraryPath"] = QLibraryInfo.path(QLibraryInfo.LibraryPath.LibrariesPath)
        if result["qtVersion"] != versions[0]:
            blockers.append("Loaded Qt version differs from installed package")
        if not Path(result["qtLibraryPath"]).resolve().is_relative_to(expected):
            blockers.append("Qt library directory outside expected environment")
    except Exception as exc:
        result["qtError"] = dict(errorType=type(exc).__name__, error=str(exc))
        blockers.append("Qt library identity unavailable")
    if os.name == "nt":
        # Query only already-loaded Qt DLLs; do not load or search other versions.
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        kernel.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
        kernel.GetModuleFileNameW.restype = wintypes.DWORD
        result["loadedQtLibraries"] = {}
        for name in ("Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6WebChannel.dll",
                     "Qt6WebEngineCore.dll", "Qt6WebEngineWidgets.dll"):
            handle = kernel.GetModuleHandleW(name)
            if not handle:
                result["loadedQtLibraries"][name] = dict(status="NOT_LOADED")
                blockers.append("Qt DLL not loaded: " + name)
                continue
            buffer = ctypes.create_unicode_buffer(32768)
            size = kernel.GetModuleFileNameW(handle, buffer, len(buffer))
            if not size or size >= len(buffer):
                blockers.append("Loaded Qt DLL origin unavailable: " + name)
                continue
            result["loadedQtLibraries"][name] = dict(status="OBSERVED", origin=buffer.value)
            if not Path(buffer.value).resolve().is_relative_to(expected):
                blockers.append("Loaded Qt DLL outside expected environment: " + name)
    result["schemeRegistration"] = "NOT_RUN"
    if not blockers:
        try:
            # Import only this source module; never qt_app/config/launcher/env files.
            spec = importlib.util.spec_from_file_location("w6_host_probe", ROOT / "kuro_launcher/qt_web_host.py")
            host = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(host)
            host.register_candidate_scheme()
            host.register_candidate_scheme()  # repeat is safe before app creation
            result["schemeRegistration"] = "PASS_BEFORE_APPLICATION"
        except Exception as exc:
            result["schemeRegistration"] = dict(errorType=type(exc).__name__, error=str(exc))
            blockers.append("Pre-application scheme registration failed")
    result.update(blockers=blockers, status="BLOCKED" if blockers else "PREREQUISITES_PASS")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-prefix", type=Path, default=FORMAL)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(HERE / ".runtime") or output.exists():
        parser.error("Use a new task .runtime JSON output")
    result = probe(args.expected_prefix)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 2 if result["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
