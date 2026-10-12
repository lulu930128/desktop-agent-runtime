"""Bounded dependency/network diagnostics; no production endpoints or settings."""
from datetime import datetime, timezone
import argparse
import importlib
import json
from pathlib import Path
import socket
import sys
import urllib.request

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=HERE / ".runtime/w1-20261010-retry/environment.json")
    args = parser.parse_args()
    if Path(sys.prefix).resolve() != HERE / ".venv":
        raise SystemExit("Use the task-local .venv")
    output = args.output.resolve()
    if not output.is_relative_to(HERE) or output.exists():
        parser.error("Use a new output file inside the isolated task")
    result = {"utc": datetime.now(timezone.utc).isoformat(), "python": sys.executable,
              "version": sys.version, "prefix": sys.prefix, "probes": {}}

    def probe(name, operation):
        try:
            result["probes"][name] = {"status": "PASS", "result": operation()}
        except Exception as exc:
            result["probes"][name] = {"status": "BLOCKED", "type": type(exc).__name__,
                                       "error": str(exc), "errno": getattr(exc, "errno", None),
                                       "winerror": getattr(exc, "winerror", None)}

    probe("QWebEngineView", lambda: str(importlib.import_module("PySide6.QtWebEngineWidgets").QWebEngineView))
    probe("QWebChannel", lambda: str(importlib.import_module("PySide6.QtWebChannel").QWebChannel))

    def loopback():
        with socket.socket() as listener:
            listener.settimeout(3)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            with socket.create_connection(listener.getsockname(), timeout=3) as client:
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(3)
                    client.sendall(b"W1-SYNTHETIC")
                    assert connection.recv(32) == b"W1-SYNTHETIC"
            return {"ephemeralLoopback": True}

    probe("ephemeralLoopback", loopback)

    def package_index():
        # Explicit official package endpoint, no environment proxy or credentials.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("https://pypi.org/pypi/PySide6/6.11.1/json", timeout=10) as response:
            value = json.loads(response.read(2_000_000))
            return {"status": response.status, "version": value["info"]["version"],
                    "windowsWheels": [item["filename"] for item in value["urls"] if "win_amd64.whl" in item["filename"]]}

    probe("officialPyPI", package_index)
    result["status"] = "PASS" if all(p["status"] == "PASS" for p in result["probes"].values()) else "BLOCKED"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
