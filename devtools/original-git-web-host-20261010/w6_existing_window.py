"""Exact formal-Python native existing-window test, with disposable owners' IO.

No production main(), configuration, data, profile, package writes or Qt overrides.
Native observations, synthetic device IO and human approval are reported separately.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FORMAL = ROOT / "envs/kuro-llm310"

# Missing checks are NOT pass. Device/notification fixtures remain distinct
# from the physical IME, OS toast and Live2D/Voice human release checklist.
REQUIRED_CHECKS = frozenset({
    "isolated-instance-owner", "native-platform", "real-existing-window", "native-visible-exposed",
    "bootstrap-and-chat-auto-connect", "single-owners", "zero-widget-presentation", "off-the-record",
    "startup-profile-disabled", "chat-state", "history-list", "history-snapshot", "profile-options",
    "today-canonical-stale", "schedule-status", "schedule-view", "schedule-notifications", "materialize-denied",
    "core-read-no-write", "tools-policy", "mail-refresh-gap", "mail-read-gap", "memory-ready",
    "memory-native-confirm-cancel", "memory-native-confirm-write", "memory-review", "profile-native-confirm-cancel",
    "profile-effective-same-client", "history-create", "history-select", "send-text", "scoped-chat-reply",
    "interrupt", "history-delete-cancel", "history-delete-confirm", "native-modal-observed", "state-read",
    "subscription-methods", "screenshot-chat", "screenshot-today", "screenshot-settings", "dom-input-focus",
    "composition-enter-not-sent", "injected-ime-value", "scheme-network-storage-denied", "navigation-denied",
    "loopback-probe-reachable", "native-owner-count-before-load", "X-tray-or-visible-fallback",
    "second-launch-existing-activation", "reveal-same-window", "late-results-silent", "idempotent-cleanup",
    "chat-thread-stopped", "quit-owner", "restart-boundary", "schedule-mutate-replay", "schedule-item",
    "notification-dedup-synthetic-display", "capture-unavailable-without-pet", "capture-synthetic-owner",
    "live2d-unavailable-chat-independent", "stale-request-rejected", "unknown-mutation-fenced",
    "synthetic-state-lifecycle-contract", "presentation-listeners-no-error",
    "security-network-no-hit", "security-asset-denied", "security-popup-no-creation", "security-storage-no-persistence",
})


def coverage(checks):
    passed = {row["name"] for row in checks if row["pass"]}
    return {"required": sorted(REQUIRED_CHECKS), "missing": sorted(REQUIRED_CHECKS - passed),
            "pass": REQUIRED_CHECKS <= passed and all(row["pass"] for row in checks)}


def process_exited(pid):
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; kernel.OpenProcess.restype = w.HANDLE
    kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle: return ctypes.get_last_error() == 87
    try: return kernel.WaitForSingleObject(handle, 0) == 0
    finally: kernel.CloseHandle(handle)


def desktop_probe():
    from ctypes import wintypes as w
    if os.name != "nt": raise RuntimeError("Native Windows desktop required")
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.OpenInputDesktop.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    user.OpenInputDesktop.restype = w.HANDLE
    user.CloseDesktop.argtypes = [w.HANDLE]
    handle = user.OpenInputDesktop(0, False, 1)
    if not handle: raise OSError(ctypes.get_last_error(), "Native input desktop unavailable")
    user.CloseDesktop(handle)
    return {"inputDesktopReadable": True}


def source_hashes():
    names = ["launcher_qt.py", "kuro_launcher/qt_app.py", "kuro_launcher/qt_web_host.py",
        "kuro_launcher/qt_web_release.py", "kuro_launcher/qt_web_adapter.py", "kuro_launcher/qt_web_protocol.py",
        "kuro_launcher/qt_chat_client.py", "kuro_launcher/qt_controller.py", "kuro_launcher/qt_notifications.py",
        "tests/web_existing_window_fixtures.py", "tests/web_candidate_fixtures.py",
        "devtools/original-git-web-host-20261010/w6_existing_window.py",
        "devtools/original-git-web-host-20261010/w6_security_probe.py"]
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in names}


def activation_child(namespace):
    import launcher_qt as launcher
    launcher.WINDOWS_INSTANCE_MUTEX_NAME = "Local\\W6Fixture-" + namespace
    launcher.WINDOWS_QT_ACTIVATE_EVENT_NAME = "Local\\W6FixtureActivate-" + namespace
    duplicate = not launcher._acquire_launcher_instance()
    activated = launcher._activate_existing_launcher() if duplicate else False
    print(json.dumps({"duplicate": duplicate, "activated": activated, "applicationCreated": False}))
    return 0 if duplicate and activated else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--activate")
    parser.add_argument("--namespace")
    parser.add_argument("--restarted-from", type=int)
    parser.add_argument("--seconds", type=int, default=120)
    args = parser.parse_args()
    if Path(sys.prefix).resolve() != FORMAL or not sys.flags.isolated or not sys.dont_write_bytecode:
        parser.error("Use exact formal Python with -I -B")
    sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "Open-LLM-VTuber/src"), str(HERE)]
    if args.activate: return activation_child(args.activate)
    if args.namespace and (len(args.namespace) != 32 or any(c not in "0123456789abcdef" for c in args.namespace)):
        parser.error("Isolated namespace must be UUID hex")
    if args.output is None: parser.error("New task-local output required")
    output = args.output.absolute()
    if output.resolve() != output or not output.is_relative_to(HERE / ".runtime") or output.exists():
        parser.error("New task-local output required")
    if not 30 <= args.seconds <= 180: parser.error("Duration must be 30..180 seconds")
    output.mkdir(parents=True)
    result = {"contract": "kuro.w6.existing-window.v1", "utc": datetime.now(timezone.utc).isoformat(),
        "synthetic": True, "pid": os.getpid(), "executable": sys.executable, "python": sys.version,
        "argv": sys.argv, "sourceSha256": source_hashes(), "checks": [], "native": "UNVERIFIED",
        "productionAdoption": False, "humanReview": "UNVERIFIED", "physicalIme": "UNVERIFIED",
        "voiceLive2D": "UNVERIFIED", "osNotificationDelivery": "UNVERIFIED"}
    result["security"] = {"contract": "kuro.w6.security.v1", "synthetic": True,
                          "status": "NOT_REACHED", "axes": {k: None for k in ("network", "asset", "popup", "storage")}}
    window = fixture = app = None
    code = 2
    def save():
        result["coverage"] = coverage(result["checks"])
        (output / "NativeResult.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "SecurityEvidence.json").write_text(json.dumps(result["security"], indent=2), encoding="utf-8")
    def check(name, condition, *, defer=False, **details):
        result["checks"].append({"name": name, "pass": bool(condition), **details}); save()
        if not condition and not defer: raise AssertionError(name)
    try:
        from w6_preflight import probe
        preflight = probe(FORMAL)
        (output / "FormalPreflight.json").write_text(json.dumps(preflight, indent=2), encoding="utf-8")
        if preflight["status"] != "PREREQUISITES_PASS": raise RuntimeError("Formal prerequisite failed")
        result["desktop"] = desktop_probe()
        from build_owner_bundle import build
        built = build(verify_only=True)
        from kuro_launcher.qt_web_release import OwnerBundlePin, VerifiedOwnerBundle
        bundle = VerifiedOwnerBundle.load(built["directory"], OwnerBundlePin(built["fingerprint"],
            built["manifestSha256"], built["publicKey"], built["signature"]))
        result["bundle"] = built
        from PySide6.QtCore import QTimer, Qt, QUrl
        from PySide6.QtGui import QInputMethodEvent
        from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QSystemTrayIcon
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebChannel import QWebChannel
        from kuro_launcher.qt_chat_client import QtRuntimeChatClient
        from kuro_launcher.qt_notifications import QtScheduleDelivery
        from web_existing_window_fixtures import ExistingWindowFixture
        from unittest.mock import patch
        import launcher_qt as launcher
        import kuro_launcher.qt_app as qt_app
        app = QApplication([])
        app.setQuitOnLastWindowClosed(False)
        app.setApplicationName("SYNTHETIC W6 isolated existing-window")
        app.setOrganizationName("SYNTHETIC W6")
        fixture = ExistingWindowFixture(output / "state")
        fixture.start()
        namespace = args.namespace or uuid.uuid4().hex
        result["namespace"] = namespace
        if args.restarted_from:
            check("restart-parent-exited", process_exited(args.restarted_from), parentPid=args.restarted_from)
        launcher.WINDOWS_INSTANCE_MUTEX_NAME = "Local\\W6Fixture-" + namespace
        launcher.WINDOWS_QT_ACTIVATE_EVENT_NAME = "Local\\W6FixtureActivate-" + namespace
        check("isolated-instance-owner", launcher._acquire_launcher_instance() and launcher._create_qt_activation_event())
        # Only Controller IO is injected. Do not replace/patch the window,
        # WebEngine view, Port, broker, Qt client, tray or delivery constructor.
        with patch.object(qt_app, "QtLauncherController", fixture.make_controller):
            window = qt_app.KuroQtLauncherWindow(fixture.cfg, web_bundle=bundle)
        window.setWindowTitle("SYNTHETIC · W6 · existing KuroQtLauncherWindow")
        app.aboutToQuit.connect(window.cleanup)
        app.aboutToQuit.connect(launcher._close_launcher_activation_event)
        launcher._start_activation_timer(window)
        view = window.work_web_candidate
        page = view.page(); port = view.owner_port
        fixture.trace_port(port)
        result["webEngineEvents"] = []
        page.loadFinished.connect(lambda ok: result["webEngineEvents"].append({"loadFinished": ok}))
        page.renderProcessTerminated.connect(lambda status, exit_code: result["webEngineEvents"].append(
            {"termination": str(status), "exit": exit_code}))
        page.renderProcessPidChanged.connect(lambda pid: result["webEngineEvents"].append({"renderPid": pid}))
        result["windowClass"] = type(window).__name__
        result["platform"] = app.platformName()
        result["processId"] = page.renderProcessPid()
        window.reveal()
        def exercise():
            nonlocal code
            started = time.monotonic()
            def pump(seconds=.03):
                end = time.monotonic() + seconds
                while time.monotonic() < end:
                    app.processEvents(); time.sleep(.005)
                    if time.monotonic() - started > args.seconds: raise TimeoutError("Native harness deadline")
            def until(predicate, seconds=15):
                end = time.monotonic() + seconds
                while time.monotonic() < end:
                    if predicate(): return True
                    pump()
                return bool(predicate())
            def lifecycle():
                # Exercise the true native owner even when Chromium cannot
                # render; this never upgrades the missing Web interaction gate.
                check("native-owner-count-before-load", len([w for w in app.topLevelWidgets() if isinstance(w, QMainWindow)]) == 1
                    and len(window.findChildren(QtRuntimeChatClient)) == 1 and len(window.findChildren(QtScheduleDelivery)) == 1
                    and len(window.findChildren(QSystemTrayIcon)) == 1 and len(window.findChildren(QWebEngineView)) == 1)
                window.showMinimized(); pump(.1); window.reveal(); window.close(); pump(.1)
                tray_available = QSystemTrayIcon.isSystemTrayAvailable()
                check("X-tray-or-visible-fallback", not window.isVisible() if tray_available else window.isVisible(), trayAvailable=tray_available)
                child = subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--activate", namespace], cwd=ROOT,
                    capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                (output / "SecondLaunch.log").write_text(child.stdout + child.stderr, encoding="utf-8")
                check("second-launch-existing-activation", child.returncode == 0 and until(lambda: window.isVisible()))
                check("reveal-same-window", window.isVisible() and fixture.ws.connections <= 1 and window.activation_timer.isActive())
                notifications = []; port.wire.event.connect(notifications.append)
                window.chat_client.message_received.emit({"type": "set-model-and-conf"})
                port.delivered.emit(lambda _: notifications.append("LATE WORKER"), {"ok": True})
                if args.restarted_from:
                    window.quit_application()
                    check("restart-boundary", process_exited(args.restarted_from))
                else:
                    child_output = output / "restarted"
                    check("restart-helper-byte-identical", fixture.stage_restart(Path(__file__).resolve(), child_output, namespace, os.getpid()))
                    (output / "RestartPlan.json").write_text(json.dumps({"childOutput": str(child_output), "parentPid": os.getpid(),
                        "namespace": namespace, "helperSha256": hashlib.sha256((ROOT / "kuro_launcher/relaunch.py").read_bytes()).hexdigest()}), encoding="utf-8")
                    window._restart_launcher()
                    result["restartLaunched"] = True
                    check("restart-boundary", window.explicit_quitting and not window.controller.lifecycle.desired_running)
                window.cleanup(); pump(.2)
                check("late-results-silent", notifications == [])
                check("idempotent-cleanup", port.broker.closed and port.adapter.closed and fixture.calls.count("close") == 1
                    and not window.status_timer.isActive() and not window.runtime_timer.isActive()
                    and not window.activation_timer.isActive() and window.schedule_delivery.stopped.is_set())
                if window.chat_client._thread: window.chat_client._thread.join(4)
                check("chat-thread-stopped", not window.chat_client.running)
                check("quit-owner", window.explicit_quitting and not window.tray.isVisible())
            try:
                from w6_security_probe import ERROR_CAPTURE_SCRIPT, capture_javascript_errors, run_security_probe
                def js(expression):
                    values = []
                    page.runJavaScript(expression, values.append)
                    if not until(lambda: bool(values), 5): raise TimeoutError("Native JavaScript callback timeout")
                    return values[0]
                sequence = 0
                def call(method, *values):
                    nonlocal sequence
                    sequence += 1; key = "probe" + str(sequence)
                    expression = f"window.kuroWorkPanel[{json.dumps(method)}](...{json.dumps(values)})"
                    fixture.mark("bridge_call:start", method=method)
                    js(f"window.{key}=null; Promise.resolve({expression}).then(v=>window.{key}=JSON.stringify(v===undefined?{{ok:true}}:v), e=>window.{key}=JSON.stringify({{ok:false,error:'javascript_rejection'}})); true")
                    if not until(lambda: js(f"window.{key} !== null"), 25): raise TimeoutError("Bridge method timeout: " + method)
                    value = json.loads(js(f"window.{key}"))
                    fixture.mark("bridge_call:resolved", method=method)
                    result.setdefault("methods", []).append({"name": method, "ok": value.get("ok"), "error": value.get("error")})
                    return value
                check("native-platform", app.platformName() == "windows")
                check("real-existing-window", type(window) is qt_app.KuroQtLauncherWindow and isinstance(view, QWebEngineView))
                check("native-visible-exposed", until(lambda: window.isVisible() and window.windowHandle().isExposed()))
                check("bootstrap-and-chat-auto-connect", until(lambda: js("!!window.kuroWorkPanel && !!document.querySelector('.rail')") and window.chat_client.history_ready))
                js(ERROR_CAPTURE_SCRIPT + "true")
                check("single-owners", len([w for w in app.topLevelWidgets() if isinstance(w, QMainWindow)]) == 1
                    and len(window.findChildren(QtRuntimeChatClient)) == 1 and len(window.findChildren(QtScheduleDelivery)) == 1
                    and len(window.findChildren(QSystemTrayIcon)) == 1 and len(window.findChildren(QWebEngineView)) == 1
                    and len(window.findChildren(QWebChannel)) == 1 and fixture.ws.connections == 1)
                check("zero-widget-presentation", all(not hasattr(window, name) for name in
                    ("work_companion", "today_page", "schedule_page", "settings_surface", "ui_preferences", "chat_input")))
                check("off-the-record", page.profile().isOffTheRecord())
                check("startup-profile-disabled", not fixture.cfg.startup_auto_start and not window.controller.lifecycle.desired_running)
                pump(.6)  # Drain original renderer's bounded startup History refresh.
                check("chat-state", call("getChatState")["ok"])
                check("history-list", call("getHistories")["ok"])
                check("history-snapshot", call("getChatHistory")["ok"])
                check("profile-options", call("getProfile")["ok"])
                before = fixture.capability.store.path.read_bytes()
                check("today-canonical-stale", call("getData")["canonical"]["sourceStates"][0]["freshness"] == "stale")
                for action, payload in (("status", {}), ("view", {"start": "2026-10-10", "end": "2026-10-12", "timezone": "Asia/Taipei"}), ("notifications", {})):
                    check("schedule-" + action, call("schedule", action, payload)["ok"])
                check("materialize-denied", not call("schedule", "materialize", {"through": "2026-10-12"})["ok"])
                check("core-read-no-write", before == fixture.capability.store.path.read_bytes() and fixture.capability.worker is None)
                check("tools-policy", call("getTools").get("confirmation_available") is False)
                check("mail-refresh-gap", call("refreshMail").get("ok") is False)
                check("mail-read-gap", call("getMailMessage", "synthetic").get("ok") is False)
                check("memory-ready", call("getMemories")["ok"])
                modal_decision = QMessageBox.StandardButton.No
                modal_count = 0
                def answer_synthetic_modal():
                    nonlocal modal_count
                    modal = app.activeModalWidget()
                    if isinstance(modal, QMessageBox):
                        modal_count += 1; modal.done(modal_decision)
                modal_timer = QTimer(window); modal_timer.timeout.connect(answer_synthetic_modal); modal_timer.start(20)
                check("memory-native-confirm-cancel", call("memoryAction", "add", {"content": "SYNTHETIC W6 memory"}).get("cancelled") is True)
                modal_decision = QMessageBox.StandardButton.Yes
                check("memory-native-confirm-write", call("memoryAction", "add", {"content": "SYNTHETIC W6 memory"}).get("changed") is True)
                check("memory-review", len(call("getMemories")["memories"]) == 1)
                modal_decision = QMessageBox.StandardButton.No
                check("profile-native-confirm-cancel", call("applyProfile", {"character_id": "actor", "project_id": "project", "model": "synthetic-model", "thinking_power": "normal"}).get("cancelled") is True)
                check("history-create", call("createHistory")["ok"])
                history_uid = window.chat_client.current_history_uid
                check("history-select", call("selectHistory", history_uid)["ok"])
                check("send-text", call("sendText", "SYNTHETIC W6 input", [])["accepted"])
                check("scoped-chat-reply", until(lambda: port.adapter.latest_assistant == "SYNTHETIC reply"))
                check("interrupt", call("control", "interrupt", {})["ok"])
                check("history-delete-cancel", call("deleteHistory", history_uid, "SYNTHETIC").get("cancelled") is True)
                check("native-modal-observed", modal_count >= 4, count=modal_count)
                check("state-read", call("getState")["ok"])
                check("capture-unavailable-without-pet", call("control", "mic-start", {}).get("error") == "capture_unavailable_read_status_first")
                check("live2d-unavailable-chat-independent", call("getState")["presentation"]["state"] == "unavailable"
                    and window.chat_client.history_ready and fixture.ws.connections == 1)
                modal_decision = QMessageBox.StandardButton.Yes
                check("history-delete-confirm", call("deleteHistory", history_uid, "SYNTHETIC")["ok"] and history_uid not in fixture.ws.histories)
                call("getHistories"); pump(.4)
                context_before = window.chat_client.context_id
                profile_result = call("applyProfile", {"character_id": "actor", "project_id": "project", "model": "synthetic-model", "thinking_power": "normal"})
                check("profile-effective-same-client", profile_result.get("effective") is True
                    and window.chat_client.context_id != context_before and fixture.ws.connections == 1)
                pump(.6); call("getHistories"); pump(.2)
                if not window.chat_client.current_history_uid: call("createHistory")
                fixture.enable_synthetic_pet()
                synthetic_state = call("getState")
                check("synthetic-state-lifecycle-contract", synthetic_state.get("ok") is True
                    and isinstance((synthetic_state.get("capabilities", {}).get("launcher") or {}).get("voice"), dict))
                check("capture-synthetic-owner", call("control", "mic-start", {})["ok"]
                    and call("control", "mic-submit", {}).get("accepted") is True
                    and until(lambda: any(row["type"] == "mic-audio-end" for row in fixture.ws.received)))
                window.schedule_delivery.timer.stop()  # Suppress OS toast; below uses the sole real delivery owner.
                now = datetime.now(timezone.utc).replace(microsecond=0)
                call("schedule", "notifications", {})
                preferences = {"timezone": "UTC", "quietEnabled": False, "quietStart": "22:00", "quietEnd": "08:00"}
                check("notification-preferences", call("schedule", "notification-action", {"action": "preferences", "preferences": preferences})["ok"])
                mutation = {"action": "create", "idempotencyKey": "synthetic-native-once", "item": {
                    "title": "SYNTHETIC native reminder", "kind": "study", "timezone": "UTC", "start": now.isoformat(),
                    "end": (now + timedelta(hours=1)).isoformat(), "notification": {"enabled": True, "minutesBefore": 0, "channel": "desktop"}}}
                schedule_first = call("schedule", "mutate", mutation)
                check("schedule-mutate-replay", schedule_first["ok"] and call("schedule", "mutate", mutation) == schedule_first)
                check("schedule-item", call("schedule", "item", {"id": schedule_first["id"]})["ok"])
                shown = []
                with patch.object(window.schedule_delivery, "available", return_value=True), patch.object(window.tray, "showMessage", side_effect=lambda *_: shown.append("SYNTHETIC")):
                    window.schedule_delivery.poll(); check("notification-first-completed", until(lambda: not window.schedule_delivery.busy, 5))
                    window.schedule_delivery.poll(); check("notification-second-completed", until(lambda: not window.schedule_delivery.busy, 5))
                check("notification-dedup-synthetic-display", shown == ["SYNTHETIC"])
                from kuro_launcher.qt_web_protocol import CONTRACT
                stale = dict(port.adapter.identity(), context="SYNTHETIC-stale")
                replies = []
                connection = port.wire.response.connect(lambda raw: replies.append(json.loads(raw)))
                port.wire.submit(json.dumps({"contract": CONTRACT, "id": "native-stale-request", "expected": stale, "method": "getMemories", "payload": {}}))
                check("stale-request-rejected", replies[-1]["result"]["error"] == "stale_context")
                from PySide6.QtCore import QObject
                QObject.disconnect(connection)
                rejected = call("schedule", "mutate", {"action": "cancel", "idempotencyKey": "synthetic-stale-revision",
                    "id": schedule_first["id"], "expectedRevision": schedule_first["revision"] + 1})
                check("unknown-mutation-fenced", rejected.get("unknownResult") is True
                    and call("schedule", "mutate", mutation).get("error") == "busy_or_unknown_result")
                check("subscription-methods", js("['onState','onData','onChatState'].every(name => {const off=window.kuroWorkPanel[name](()=>{});const ok=typeof off==='function';off();return ok})"))
                for mode in ("chat", "today", "settings"):
                    js(f"document.querySelector('[data-mode={mode}]').click(); true"); pump(.3)
                    check("screenshot-" + mode, view.grab().save(str(output / (mode + ".png"))))
                js("document.querySelector('[data-mode=chat]').click(); document.querySelector('textarea')?.focus(); true")
                pump(.1)
                check("dom-input-focus", js("document.activeElement?.tagName === 'TEXTAREA'"))
                before_sends = len([r for r in fixture.ws.received if r["type"] == "text-input"])
                js("document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',isComposing:true,bubbles:true})); true")
                pump(.1)
                check("composition-enter-not-sent", before_sends == len([r for r in fixture.ws.received if r["type"] == "text-input"]))
                event = QInputMethodEvent(); event.setCommitString("合成輸入")
                QApplication.sendEvent(view.focusProxy(), event); pump(.1)
                check("injected-ime-value", js("document.activeElement?.value.includes('合成輸入')"))
                result["injectedIme"] = "Qt event injected; physical IME/manual acceptance remains unverified"
                import urllib.request
                probe_url = f"http://127.0.0.1:{fixture.probe_port}/w6-probe"
                with urllib.request.urlopen(probe_url, timeout=2) as response:
                    check("loopback-probe-reachable", response.status == 200 and response.read() == b"SYNTHETIC reachable")
                def security_record(evidence):
                    result["security"] = evidence
                    (output / "SecurityEvidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
                    save()
                security = run_security_probe(app=app, view=view, fixture=fixture, js=js, pump=pump,
                    until=until, namespace=namespace, record=security_record)
                axes = security["axes"]
                check("security-network-no-hit", axes["network"], defer=True)
                check("security-asset-denied", axes["asset"], defer=True)
                check("security-popup-no-creation", axes["popup"], defer=True)
                check("security-storage-no-persistence", axes["storage"], defer=True)
                check("scheme-network-storage-denied", all(axes.values()), defer=True)
                nav_before = view.security_snapshot().get("navigationDenied", 0)
                nav_hits = fixture.probe_hits
                for denied_url in ("kuro-work://denied/forbidden", "kuro-work://app/denied", probe_url):
                    page.setUrl(QUrl(denied_url)); pump(.2)
                check("navigation-denied", page.url().toString() == "kuro-work://app/work-panel.html"
                    and view.security_snapshot().get("navigationDenied", 0) >= nav_before + 3
                    and fixture.probe_hits == nav_hits, defer=True,
                    deniedCallbacks=view.security_snapshot().get("navigationDenied", 0)-nav_before,
                    probeHitsBefore=nav_hits, probeHitsAfter=fixture.probe_hits)
                call("toggleMaximizeWindow"); pump(.1); call("toggleMaximizeWindow")
                call("minimizeWindow"); pump(.1); window.reveal()
                call("closeWindow"); pump(.1)
                check("presentation-listeners-no-error", security.get("javascriptErrorsComplete") is True
                    and security.get("javascriptErrors") == []
                    and js("Array.isArray(window.w6Errors)&&window.w6Errors.length===0") is True, defer=True)
                result["native"] = "CHECKING_LIFECYCLE" if all(r["pass"] for r in result["checks"]) else "FAIL"
            except Exception as exc:
                result.update(native="FAIL" if isinstance(exc, AssertionError) else "BLOCKED", errorType=type(exc).__name__, error=str(exc))
                (output / "NativeError.log").write_text(traceback.format_exc(), encoding="utf-8")
            finally:
                try:
                    final_errors = {"javascriptErrors": [], "javascriptErrorSamples": {}}
                    capture_javascript_errors(final_errors, "final", json.loads(js("JSON.stringify(window.w6Errors)")))
                    result["javascriptErrors"] = final_errors["javascriptErrors"]
                    result["javascriptErrorsObserved"] = final_errors["javascriptErrorSamples"]["final"]
                except Exception: result["javascriptErrors"] = "UNVERIFIED"
                try:
                    lifecycle()
                    if coverage(result["checks"])["pass"]:
                        result["native"] = "AUTOMATED_EXISTING_WINDOW_PASS"
                        code = 0
                    elif result["native"] == "CHECKING_LIFECYCLE":
                        result.update(native="BLOCKED", error="Required native coverage missing")
                except Exception as exc:
                    result["lifecycleError"] = {"type": type(exc).__name__, "error": str(exc)}
                    (output / "LifecycleError.log").write_text(traceback.format_exc(), encoding="utf-8")
                app.quit()
        QTimer.singleShot(100, exercise)
        QTimer.singleShot(args.seconds * 1000, app.quit)
        app.exec()
    except Exception as exc:
        result.update(native="FAIL" if isinstance(exc, AssertionError) else "BLOCKED",
            errorType=type(exc).__name__, error=str(exc))
        (output / "NativeError.log").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        if window is not None:
            result["finalRenderPid"] = window.work_web_candidate.page().renderProcessPid()
            result["failureScreenshotSaved"] = window.work_web_candidate.grab().save(str(output / "last-window.png"))
            window.cleanup()
            result["brokerClosed"] = window.work_web_candidate.owner_port.broker.closed
            result["controllerCloseCount"] = fixture.calls.count("close")
        if fixture is not None:
            result["syntheticTiming"] = fixture.timing
            result["ownerCalls"] = fixture.calls
            result["wsRequests"] = fixture.ws.received
            result["connections"] = fixture.ws.connections
            fixture.close(restore=False)
        result["sourceUnchangedDuringRun"] = result["sourceSha256"] == source_hashes()
        result["exit"] = code
        save()
        print(json.dumps({k: result.get(k) for k in ("native", "errorType", "error", "exit")}), flush=True)
    return code


if __name__ == "__main__": raise SystemExit(main())
