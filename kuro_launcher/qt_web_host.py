"""Single-owner Qt Web host. Importing this module does not load Addons."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, unquote

ORIGIN = "kuro-work://app"
ENTRY = ORIGIN + "/work-panel.html"


class AssetBundle:
    """Fixed in-memory allowlist, verified before the renderer can load anything."""
    def __init__(self, directory, *, manifest_bytes=None):
        root = Path(directory).resolve(strict=True)
        manifest = json.loads(manifest_bytes if manifest_bytes is not None else (root / "candidate-manifest.json").read_bytes())
        if manifest.get("contract") != "kuro.qt.assets.v1" or not isinstance(manifest.get("files"), dict):
            raise ValueError("Invalid candidate asset manifest")
        self.assets = {}
        for name, digest in manifest["files"].items():
            if (not isinstance(name, str) or not name or "\\" in name or "%" in name
                    or name.startswith("/") or any(p in {"", ".", ".."} for p in name.split("/"))):
                raise ValueError("Invalid asset allowlist name")
            path = (root / name).resolve(strict=True)
            if path != root / name or not path.is_relative_to(root) or path.suffix not in {".html", ".css", ".js"} or path.stat().st_size > 4 * 1024 * 1024:
                raise ValueError("Asset outside local allowlist")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != digest: raise ValueError("Asset hash mismatch")
            self.assets["/" + name] = data
        if "/work-panel.html" not in self.assets: raise ValueError("Candidate entry absent")

    def allowed(self, url):
        parsed = urlsplit(url)
        return (parsed.scheme == "kuro-work" and parsed.netloc == "app"
                and not parsed.query and not parsed.fragment and "%" not in parsed.path
                and unquote(parsed.path) in self.assets)


def register_candidate_scheme():
    """Register in the process before any QCoreApplication, never after startup."""
    from PySide6.QtCore import QCoreApplication
    if QCoreApplication.instance() is not None:
        raise RuntimeError("Register the local scheme before QApplication")
    from PySide6.QtWebEngineCore import QWebEngineUrlScheme
    existing = QWebEngineUrlScheme.schemeByName(b"kuro-work")
    if bytes(existing.name()):
        if (existing.syntax() != QWebEngineUrlScheme.Syntax.Host
                or existing.flags() != QWebEngineUrlScheme.Flag.SecureScheme):
            raise RuntimeError("Conflicting local scheme registration")
        return
    scheme = QWebEngineUrlScheme(b"kuro-work")
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    scheme.setFlags(QWebEngineUrlScheme.Flag.SecureScheme)
    QWebEngineUrlScheme.registerScheme(scheme)


def create_candidate(owner, directory, *, enabled=False, readiness=None, fixture=False):
    """Return a child view, never another MainWindow/client/tray/notification owner.

    A caller-provided readiness dict is not native acceptance evidence. W6 is
    blocked on formal dependencies and existing-window lifecycle proof, so no
    production attachment path is exposed. Keep readiness for caller compatibility
    only; it can never grant authority. Fixtures require a synthetic owner marker.
    """
    if not enabled: return None  # Do not import Addons on default Widget startup.
    if fixture:
        if getattr(owner, "synthetic_disposable_owner", False) is not True:
            raise ValueError("Disposable synthetic owner required")
    else:
        raise RuntimeError("Formal W6 adoption BLOCKED: exact runtime and native owner handoff required")
    return _create_host(owner, AssetBundle(directory), fixture=True)


def create_existing_window_host(owner, bundle):
    from .qt_web_release import VerifiedOwnerBundle
    if not isinstance(bundle, VerifiedOwnerBundle):
        raise TypeError("Verified immutable owner bundle required")
    # Reuse the exact request/security implementation used by the candidate.
    assets = AssetBundle.__new__(AssetBundle)
    assets.assets = dict(bundle.assets)
    return _create_host(owner, assets, fixture=False)


def _create_host(owner, bundle, *, fixture):
    if any(os.environ.get(name) for name in ("QTWEBENGINE_DISABLE_SANDBOX", "QTWEBENGINE_CHROMIUM_FLAGS",
            "QTWEBENGINE_REMOTE_DEBUGGING", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH",
            "QTWEBENGINEPROCESS_PATH", "QTWEBENGINE_RESOURCES_PATH", "QTWEBENGINE_LOCALES_PATH")):
        raise RuntimeError("Unsafe WebEngine overrides are prohibited")
    if getattr(owner, "work_web_candidate", None) is not None:
        raise RuntimeError("Only one candidate view per Qt owner")
    from concurrent.futures import ThreadPoolExecutor
    from PySide6.QtCore import QObject, QBuffer, QByteArray, QIODevice, QFile, QTimer, QUrl, QThread, Qt, Signal, Slot
    from PySide6.QtWidgets import QMessageBox, QMainWindow, QFileDialog
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor, QWebEngineUrlSchemeHandler, QWebEngineUrlRequestJob
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from .qt_web_protocol import RequestBroker, CONTRACT, error
    from .qt_web_adapter import QtOwnerAdapter
    if not isinstance(owner, QMainWindow): raise TypeError("Existing Qt MainWindow owner required")
    if QThread.currentThread() != owner.thread(): raise RuntimeError("Candidate must be created on owner GUI thread")
    def audit(kind, **values):
        # Optional, fixture-only metadata observer; never expose payload or authority.
        observer = getattr(owner, "candidate_audit", None) if fixture else None
        if callable(observer): observer(kind, **values)
    from types import MappingProxyType
    from collections import Counter
    from threading import Lock
    # Bounded counters only: no URLs, payloads or authority exposed to HTML.
    security_counts = Counter()
    security_lock = Lock()
    def security_count(name):
        with security_lock: security_counts[name] += 1
    def security_snapshot():
        with security_lock: return dict(security_counts)
    channel_js = QFile(":/qtwebchannel/qwebchannel.js")
    if not channel_js.open(QIODevice.OpenModeFlag.ReadOnly): raise RuntimeError("Qt WebChannel resource absent")
    bundle.assets["/qwebchannel.js"] = bytes(channel_js.readAll())
    bundle.assets = MappingProxyType(bundle.assets)
    channel_js.close()

    class Requests(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info):
            allowed = bundle.allowed(info.requestUrl().toString())
            info.block(not allowed)
            if not allowed:
                security_count("assetBlocked" if info.requestUrl().scheme() == "kuro-work" else "networkBlocked")
            audit("resource", allowed=allowed, scheme=info.requestUrl().scheme())

    class LocalFiles(QWebEngineUrlSchemeHandler):
        def requestStarted(self, request):
            url = request.requestUrl().toString()
            if request.requestMethod() != b"GET" or not bundle.allowed(url):
                security_count("handlerDenied")
                request.fail(QWebEngineUrlRequestJob.Error.RequestDenied); return
            path = urlsplit(url).path
            data = QBuffer(request)
            data.setData(QByteArray(bundle.assets[path]))
            data.open(QIODevice.OpenModeFlag.ReadOnly)
            mime = {".html": b"text/html", ".js": b"text/javascript", ".css": b"text/css"}[Path(path).suffix]
            request.reply(QByteArray(mime), data)
            security_count("assetReplied")

    class Page(QWebEnginePage):
        def acceptNavigationRequest(self, url, kind, main):
            allowed = main and url.toString() == ENTRY
            security_count("navigationAllowed" if allowed else "navigationDenied")
            audit("navigation", allowed=allowed, scheme=url.scheme())
            return allowed

        def createWindow(self, kind):
            security_count("popupDenied")
            return None
        def chooseFiles(self, mode, old, accepted):
            selected, _ = QFileDialog.getOpenFileNames(owner, "選擇本次訊息附件", "",
                "支援的附件 (*.png *.jpg *.jpeg *.webp *.txt *.pdf *.wav)")
            if len(selected) > 6: return []
            try:
                paths = [Path(value).resolve(strict=True) for value in selected]
                if any(not p.is_file() or p.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".txt", ".pdf", ".wav"}
                       or not 0 < p.stat().st_size <= 4 * 1024 * 1024 for p in paths): return []
                if sum(p.stat().st_size for p in paths) > 8 * 1024 * 1024: return []
                return [str(p) for p in paths]
            except OSError: return []
        def javaScriptConsoleMessage(self, level, message, line, source):
            # Do not leak DOM/private payloads into native console logs.
            pass

    class Wire(QObject):
        response = Signal(str)
        event = Signal(str)

        def __init__(self, driver):
            super().__init__(driver)
            self.driver = driver

        @Slot(str)
        def submit(self, raw): self.driver.broker.submit(raw)

    class Port(QObject):
        delivered = Signal(object, object)

        def __init__(self, parent):
            super().__init__(parent)
            self.wire = Wire(self)
            self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="kuro-web-owner")
            self.delivered.connect(self.finish_worker, Qt.ConnectionType.QueuedConnection)
            self.adapter = QtOwnerAdapter(owner.controller, owner.chat_client, self.run_worker,
                window_action=self.window_action, event=self.publish,
                request_status=self.request_status,
                request_data=self.request_data,
                profile_action=getattr(owner, "_submit_web_profile", None))
            self.status_waiters = []
            self.status_inflight = False
            self.data_waiters = []
            self.data_inflight = False
            self.broker = RequestBroker(self.adapter, self.confirm, lambda reply: self.wire.response.emit(json.dumps(reply, ensure_ascii=False)))
            self.bindings = [(owner.chat_client.message_received, self.receive),
                (owner.chat_client.state_changed, self.state_changed)]
            self.connections = [signal.connect(callback, Qt.ConnectionType.QueuedConnection)
                                for signal, callback in self.bindings]
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.broker.expire)
            self.timer.start(250)

        @Slot(dict)
        def receive(self, payload):
            if not self.broker.closed: self.adapter.receive(payload)

        @Slot(str, bool)
        def state_changed(self, state, connected):
            if not self.broker.closed: self.adapter.on_state(state, connected)

        def publish(self, name, value):
            if self.broker.closed: return
            self.wire.event.emit(json.dumps({"contract": CONTRACT, "name": name,
                "identity": self.adapter.identity(), "value": value}, ensure_ascii=False))

        def run_worker(self, work, callback):
            if self.broker.closed: return
            def execute():
                try: result = work()
                except Exception: result = error("owner_exception", unknown=True)
                try: self.delivered.emit(callback, result)
                except RuntimeError: return
            self.pool.submit(execute)

        def request_status(self, callback):
            if self.broker.closed: return
            self.status_waiters.append(callback)
            if self.status_inflight: return
            self.status_inflight = True
            def complete(result):
                self.status_inflight = False
                waiters, self.status_waiters = self.status_waiters, []
                lifecycle = getattr(owner, "_apply_lifecycle_status", None)
                if result.get("ok") is True and callable(lifecycle): lifecycle(result["status"])
                for waiter in waiters: waiter(result)
            self.run_worker(self.adapter.read_status, complete)

        def refresh_status(self):
            context = {"chat": self.adapter.chat_state()}
            expected = self.adapter.identity()
            def complete(raw):
                if expected != self.adapter.identity(): return
                result = self.adapter._state_result(raw, context)
                self.adapter.runtime_snapshot = result if result.get("ok") else None
                self.publish("onState", result)
            self.request_status(complete)

        def request_data(self, callback):
            if self.broker.closed: return
            self.data_waiters.append(callback)
            if self.data_inflight: return
            self.data_inflight = True
            def complete(result):
                self.data_inflight = False
                waiters, self.data_waiters = self.data_waiters, []
                for waiter in waiters: waiter(result)
            self.run_worker(lambda: self.adapter._owned_call("getData", {}, {}), complete)

        def refresh_data(self):
            if not owner.isVisible(): return
            expected = self.adapter.identity()
            def complete(result):
                if expected == self.adapter.identity(): self.publish("onData", result)
            self.request_data(complete)

        @Slot(object, object)
        def finish_worker(self, callback, result):
            audit("worker_delivery", guiThread=QThread.currentThread() == owner.thread(), closed=self.broker.closed)
            if not self.broker.closed: callback(result)

        def confirm(self, method, payload):
            # No HTML, no renderer confirmed flag; exact prepared payload bound.
            box = QMessageBox(owner)
            box.setWindowTitle("確認 Work Companion 操作")
            box.setTextFormat(Qt.TextFormat.PlainText)
            review = {k: v for k, v in payload.items() if not k.startswith("_")}
            if method == "sendText":
                review["attachments"] = [{k: a[k] for k in ("name", "size", "mime_type")} for a in payload["attachments"]]
            box.setText(f"{method}\n\n{json.dumps(review, ensure_ascii=False, indent=2)}\n\n僅授權本次內容；逾時不會自動重送。")
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            box.setDefaultButton(QMessageBox.StandardButton.No)
            accepted = box.exec() == QMessageBox.StandardButton.Yes
            audit("confirmation", method=method, accepted=accepted)
            return accepted

        def window_action(self, method):
            if self.broker.closed: return
            if method == "closeWindow": owner.close()
            elif method == "minimizeWindow": owner.showMinimized()
            elif owner.isMaximized(): owner.showNormal()
            else: owner.showMaximized()

        def shutdown(self):
            if self.broker.closed: return
            self.broker.close()
            self.status_waiters.clear()
            self.data_waiters.clear()
            self.timer.stop()
            for connection in self.connections:
                try: QObject.disconnect(connection)
                except RuntimeError: pass
            self.connections.clear()
            self.pool.shutdown(wait=False, cancel_futures=True)

    view = QWebEngineView(owner)
    view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
    profile = QWebEngineProfile(view)
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
    profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
    interceptor = Requests(profile)
    handler = LocalFiles(profile)
    profile.setUrlRequestInterceptor(interceptor)
    profile.installUrlSchemeHandler(b"kuro-work", handler)
    def deny_download(download):
        download.cancel()
        audit("download", denied=True)
    profile.downloadRequested.connect(deny_download)
    page = Page(profile, view)
    # No openIn() recipient: Qt discards an unhandled new-window request.
    page.newWindowRequested.connect(lambda _: security_count("popupRequestDiscarded"))
    def deny_permission(permission):
        permission.deny()
        audit("permission", denied=True)
    def deny_filesystem(request):
        request.reject()
        audit("filesystem", denied=True)
    page.permissionRequested.connect(deny_permission)
    page.fileSystemAccessRequested.connect(deny_filesystem)
    for name in ("LocalContentCanAccessRemoteUrls", "LocalContentCanAccessFileUrls", "JavascriptCanOpenWindows",
                 "JavascriptCanAccessClipboard", "AllowRunningInsecureContent", "PluginsEnabled", "FullScreenSupportEnabled", "LocalStorageEnabled"):
        page.settings().setAttribute(getattr(QWebEngineSettings.WebAttribute, name), False)
    view.setPage(page)
    channel = QWebChannel(page)
    port = Port(page)
    channel.registerObject("workPort", port.wire)  # Only submit + response/event; worker slots stay private.
    page.setWebChannel(channel)
    page.renderProcessTerminated.connect(lambda *_: port.shutdown())
    view.destroyed.connect(lambda *_: port.shutdown())
    view._candidate_refs = (profile, page, interceptor, handler, channel, port)
    view.shutdown_candidate = port.shutdown
    view.owner_port = port
    view.security_snapshot = security_snapshot
    owner.work_web_candidate = view
    view.load(QUrl(ENTRY))
    return view
