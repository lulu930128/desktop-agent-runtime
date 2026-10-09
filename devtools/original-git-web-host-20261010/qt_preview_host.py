"""Isolated candidate only. Never imported by launcher_qt or the production UI.

Run with the isolated venv after WebEngine is actually installed. No controller,
tray, WS, DB, provider, private configuration or persistent browser profile.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from preview_protocol import FRONTEND, PreviewProtocol


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--view", choices=["chat", "settings", "today"], default="chat")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--capture", type=Path)
    args = parser.parse_args()
    task_root = Path(__file__).resolve().parent
    if Path(sys.prefix).resolve() != (task_root / ".venv").resolve():
        print("BLOCKED: run with this task's isolated .venv/Scripts/python.exe")
        return 2
    if not 320 <= args.width <= 2560 or not 240 <= args.height <= 1440:
        parser.error("Capture dimensions outside bounded preview range")
    if args.capture:
        args.capture = args.capture.resolve()
        if not args.capture.is_relative_to(task_root) or args.capture.suffix != ".png":
            parser.error("Capture must be a PNG inside this task directory")
        if args.capture.exists() or args.capture.with_suffix(".json").exists():
            parser.error("Capture already exists; preserve evidence and choose a new name")
    # Refuse unsafe inherited overrides, rather than concealing startup failures.
    if os.environ.get("QTWEBENGINE_DISABLE_SANDBOX") or os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS"):
        print("BLOCKED: remove inherited WebEngine security/GPU overrides before isolated proof")
        return 2
    try:
        import PySide6
        from PySide6.QtCore import QObject, QTimer, QUrl, Slot
        from PySide6.QtWidgets import QApplication
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError as exc:
        print(json.dumps({"gate": "WEBENGINE", "status": "BLOCKED", "error": str(exc), "python": sys.executable}))
        return 2

    dist = (FRONTEND / "dist").resolve()
    entry = dist / "qt-preview.html"
    if not entry.is_file():
        print("BLOCKED: build isolated frontend first")
        return 2

    class Requests(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info):
            url = info.requestUrl()
            allowed = url.toString() == "qrc:///qtwebchannel/qwebchannel.js"
            if url.isLocalFile():
                target = Path(url.toLocalFile()).resolve()
                allowed = target.is_relative_to(dist) and target.is_file()
            info.block(not allowed)

    class Page(QWebEnginePage):
        def acceptNavigationRequest(self, url, kind, is_main):
            return bool(is_main and url.isLocalFile() and Path(url.toLocalFile()).resolve() == entry)

        def createWindow(self, kind):
            return None

        def chooseFiles(self, mode, old_files, accepted_mimes):
            return []

    class Port(QObject):
        def __init__(self, parent):
            super().__init__(parent)
            self.protocol = PreviewProtocol()
            self.requests = 0

        @Slot(str, result=str)
        def request(self, raw):
            self.requests += 1
            return self.protocol.request(raw)

    app = QApplication([])
    app.setApplicationName("Kuro-SYNTHETIC-WebEngine-proof")
    view = QWebEngineView()
    profile = QWebEngineProfile(view)  # unnamed: off-the-record, no private profile reuse
    interceptor = Requests(profile)
    profile.setUrlRequestInterceptor(interceptor)
    profile.downloadRequested.connect(lambda download: download.cancel())
    page = Page(profile, view)
    page.permissionRequested.connect(lambda permission: permission.deny())
    page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
    page.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
    page.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, False)
    view.setPage(page)
    port = Port(page)
    channel = QWebChannel(page)
    channel.registerObject("previewPort", port)
    page.setWebChannel(channel)
    view.resize(args.width, args.height)
    view.setWindowTitle("SYNTHETIC Git renderer / Qt host — NOT ACCEPTED")
    result = {"gate": "WEBENGINE", "status": "UNVERIFIED", "qt": PySide6.__version__,
              "python": sys.executable, "view": args.view, "offTheRecord": profile.isOffTheRecord(),
              "platform": app.platformName(), "logicalDpi": view.screen().logicalDotsPerInch(),
              "physicalDpi": view.screen().physicalDotsPerInch()}

    def finish(code):
        if args.capture:
            args.capture.parent.mkdir(parents=True, exist_ok=True)
            args.capture.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False), flush=True)
        app.exit(code)

    def inspect():
        # A loaded document alone is not a render or WebChannel pass.
        script = (Path(__file__).parent / "geometry.js").read_text(encoding="utf-8")
        def measured(raw):
            try:
                result["geometry"] = json.loads(raw)
                result["bridgeRequests"] = port.requests
                ok = result["geometry"]["ready"] and port.requests >= 6
                result["status"] = "PASS" if ok else "FAIL"
                if args.capture and ok:
                    args.capture.parent.mkdir(parents=True, exist_ok=True)
                    if not view.grab().save(str(args.capture)):
                        result["status"] = "FAIL"
                        result["error"] = "screenshot_write_failed"
                        ok = False
                finish(0 if ok else 1)
            except (ValueError, KeyError, TypeError) as exc:
                result.update(status="FAIL", error=str(exc)); finish(1)
        page.runJavaScript(script, measured)

    def loaded(ok):
        if not ok:
            result.update(status="FAIL", error="load_failed"); finish(1)
        elif args.capture:
            QTimer.singleShot(1500, inspect)
    page.loadFinished.connect(loaded)
    if args.capture:
        QTimer.singleShot(20000, lambda: (result.update(status="BLOCKED", error="render_timeout"), finish(2)))
    url = QUrl.fromLocalFile(str(entry)); url.setQuery("view=" + args.view)
    view.load(url)
    view.show()
    code = app.exec()
    # Page must be destroyed before its profile.
    view.close()
    page.deleteLater()
    app.processEvents()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
