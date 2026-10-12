"""W1 installed-dependency proof, without network or production imports."""
import argparse
from datetime import datetime, timezone
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if Path(sys.prefix).resolve() != HERE / ".venv":
        parser.error("Use this task's isolated .venv")
    if not output.is_relative_to(HERE) or output.exists():
        parser.error("Use a new task-local evidence file")
    result = {"utc": datetime.now(timezone.utc).isoformat(), "executable": sys.executable,
              "prefix": sys.prefix, "basePrefix": sys.base_prefix, "python": sys.version,
              "platform": platform.platform(), "imports": {}, "versions": {},
              "environment": {key: os.environ.get(key) for key in ["QT_QPA_PLATFORM", "QT_SCALE_FACTOR", "QTWEBENGINE_DISABLE_SANDBOX", "QTWEBENGINE_CHROMIUM_FLAGS"]}}
    for module, attribute in [("PySide6.QtWebChannel", "QWebChannel"),
                              ("PySide6.QtWebEngineWidgets", "QWebEngineView"),
                              ("PIL.Image", "open"),
                              ("playwright.sync_api", "sync_playwright")]:
        try:
            imported = importlib.import_module(module)
            value = getattr(imported, attribute)
            result["imports"][module] = {"status": "PASS", "file": imported.__file__, "attribute": attribute,
                                         "callable": callable(value)}
        except Exception as exc:
            result["imports"][module] = {"status": "BLOCKED", "type": type(exc).__name__,
                                         "error": str(exc), "errno": getattr(exc, "errno", None)}
    for name in ["PySide6", "PySide6_Addons", "PySide6_Essentials", "shiboken6", "Pillow", "playwright"]:
        try:
            version = importlib.metadata.version(name)
            result["versions"][name] = {"status": "PASS" if isinstance(version, str) and version else "UNVERIFIED",
                                        "version": version}
        except Exception as exc:
            result["versions"][name] = {"status": "UNVERIFIED", "type": type(exc).__name__, "error": str(exc)}
    try:
        from PySide6.QtCore import qVersion
        result["qtVersion"] = qVersion()
    except Exception as exc:
        result["qtVersion"] = None
        result["qtVersionError"] = str(exc)
    complete = (all(row["status"] == "PASS" for row in result["imports"].values())
                and all(row["status"] == "PASS" for row in result["versions"].values())
                and isinstance(result["qtVersion"], str))
    result["status"] = "PASS" if complete else "BLOCKED"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
