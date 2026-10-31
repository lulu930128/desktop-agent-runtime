"""Bounded signed-bundle Qt DOM probe; synthetic list, no production services."""
import argparse
import json
from pathlib import Path
import socket
import sys
import time
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / ".tmp") or output.exists():
        parser.error("New repo .tmp directory required")
    output.mkdir(parents=True)
    from kuro_launcher.qt_web_release import OwnerBundlePin, VerifiedOwnerBundle
    from kuro_launcher.qt_web_host import register_candidate_scheme, create_existing_window_host
    record = json.loads(args.bundle_receipt.read_text(encoding="utf-8"))
    pin = OwnerBundlePin(record["fingerprint"], record["manifestSha256"], record["publicKey"], record["signature"])
    bundle = VerifiedOwnerBundle.load(ROOT / "assets/qt-owner" / pin.fingerprint, pin)
    register_candidate_scheme()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMainWindow
    from kuro_launcher.qt_chat_client import QtRuntimeChatClient
    from web_candidate_fixtures import controller_fixture
    app = QApplication([])
    owner = QMainWindow()
    owner.setWindowTitle("SYNTHETIC History list acceptance")
    owner.resize(1100, 820)
    owner.controller = controller_fixture()
    owner.chat_client = chat = QtRuntimeChatClient(owner)
    sent, replies, checks = [], [], []
    fail = [False]
    # Any accidental external IO is a failing test, including loopback services.
    def denied(*_args, **_kwargs):
        raise AssertionError("History surface must not connect to a service")
    socket.socket.connect = denied

    def send(payload):
        assert payload["type"] == "fetch-history-list", "Only list reads are authorized"
        sent.append(payload["type"])
        body = {key: payload[key] for key in ("request_id", "client_uid", "conf_uid", "context_id")}
        body.update(type="history-error" if fail[0] else "history-list", current_history_uid="",
            error="history_operation_failed" if fail[0] else "",
            histories=[{"uid": f"anonymous-{i}", "title": f"SYNTHETIC {i}", "last_preview": "SYNTHETIC", "is_empty": False} for i in range(22)])
        QTimer.singleShot(10, lambda: chat._on_message(chat._ws_app, json.dumps(body)))
        return True

    chat._send_json = send
    chat._ws_app = Mock()
    view = create_existing_window_host(owner, bundle)
    port = view.owner_port
    port.adapter.read_status = lambda: {"ok": False, "error": "synthetic-offline"}
    port.adapter._owned_call = lambda method, *_: {"ok": False, "error": "synthetic-unavailable"}
    port.wire.response.connect(lambda raw: replies.append(json.loads(raw)))
    owner.setCentralWidget(view)
    owner.show()

    def js(code):
        result = []
        view.page().runJavaScript("JSON.stringify((()=>{" + code + "})())", result.append)
        deadline = time.monotonic() + 3
        while not result and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.005)
        if not result:
            raise TimeoutError("DOM callback")
        return json.loads(result[0]) if result[0] else None

    def until(condition):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if js("return (" + condition + ");"):
                return
            app.processEvents()
            time.sleep(.01)
        raise TimeoutError(condition)

    def check(name, condition):
        passed = bool(js("return (" + condition + ");"))
        checks.append({"name": name, "passed": passed})
        if not passed:
            raise AssertionError(name)

    def ready(connected=True):
        chat._connected = connected
        if connected:
            chat.client_uid, chat.conf_uid, chat.context_id = "synthetic-client", "synthetic-actor", "synthetic-context"
            chat.history_protocol = "kuro.conversation.history.v1"
        port.adapter.on_state("idle" if connected else "offline", connected)

    result = {"synthetic": True, "productionAdoption": False, "fingerprint": pin.fingerprint}
    try:
        until("window.__kuroWorkPanelReady === true")
        js("document.querySelector('[data-mode=chat]').click(); document.querySelector('[data-history-toggle]').click();")
        until("!!document.querySelector('[data-owner-history-progress]')")
        check("startup-loading-visible", "document.querySelector('[data-owner-history-progress]').textContent.includes('正在讀取')")
        ready()
        until("document.querySelectorAll('.history-row').length === 22 && document.querySelector('[data-stage]').classList.contains('has-history')")
        check("ready-list-22-empty-selection", "document.querySelectorAll('.history-row.is-active').length === 0 && !document.querySelector('.history-list').hidden")
        before = len(sent)
        js("document.querySelector('[data-history-drawer] .icon-button').click(); document.querySelector('[data-history-toggle]').click();")
        until("document.querySelector('[data-stage]').classList.contains('has-history') && document.querySelectorAll('.history-row').length === 22")
        assert len(sent) == before + 1
        checks.append({"name": "drawer-reopen-fresh-read", "passed": True})
        fail[0] = True
        js("document.querySelector('[data-history-drawer] .icon-button').click(); document.querySelector('[data-history-toggle]').click();")
        until("document.querySelector('[data-owner-history-status]')?.textContent.includes('讀取失敗')")
        check("failed-read-not-empty", "!document.querySelector('.history-list').textContent.includes('目前沒有對話紀錄') && document.querySelector('.history-list').hidden")
        fail[0] = False
        ready(False)
        ready()
        until("document.querySelectorAll('.history-row').length === 22 && !document.querySelector('.history-list').hidden")
        check("reconnect-recovered-22", "document.querySelector('[data-stage]').classList.contains('has-history')")
        successful = [r["result"] for r in replies if len(r["result"].get("histories", [])) == 22]
        assert successful and all(r["current_history_uid"] == "" for r in successful)
        assert all(method == "fetch-history-list" for method in sent)
        result.update(status="PASS", checks=checks, listReadCount=len(sent), ownerPayloadCount=len(successful), uiRowCount=22)
        # DOM completion precedes Chromium paint and the drawer's CSS transition.
        deadline = time.monotonic() + .6
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        view.grab().save(str(output / "synthetic-history-22.png"))
    except Exception as exc:
        result.update(status="FAIL", checks=checks, errorType=type(exc).__name__, error=str(exc))
    finally:
        port.shutdown()
        owner.close()
        view.deleteLater()
        for _ in range(10):
            app.processEvents()
        (output / "Result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
