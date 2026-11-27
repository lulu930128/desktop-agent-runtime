"""Opt-in isolated signed Qt DOM + real speech-settings Port. No Kuro startup."""
import json
import os
from pathlib import Path
import socket
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "Open-LLM-VTuber/src")]


def main():
    output = ROOT / ".tmp/kuro-multilingual-speech-20261031/surface"
    output.mkdir(parents=True, exist_ok=False)
    result = {"status": "RUNNING", "checks": [], "productionAdoption": False}
    from kuro_launcher.qt_web_release import prepare_owner_presentation, RELEASE_PIN
    from kuro_launcher.qt_web_host import create_existing_window_host
    bundle = prepare_owner_presentation(ROOT)  # Register scheme before QApplication.
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication, QMainWindow
    from kuro_launcher.qt_controller import QtLauncherController
    from kuro_launcher.qt_chat_client import QtRuntimeChatClient
    from web_candidate_fixtures import controller_fixture
    app = QApplication([]); app.setQuitOnLastWindowClosed(False)
    path = output / "synthetic-launcher.yaml"; path.write_text("fixture: true\n", encoding="utf-8")
    actual = QtLauncherController.__new__(QtLauncherController)
    actual.cfg = SimpleNamespace(config_path=path)
    controller = controller_fixture()
    controller.read_chat_speech_settings = actual.read_chat_speech_settings
    controller.update_chat_speech_settings = actual.update_chat_speech_settings
    controller.read_assistant_settings.side_effect = OSError("synthetic Core offline")
    owner = QMainWindow(); owner.resize(1100, 820)
    owner.controller = controller; owner.chat_client = QtRuntimeChatClient(owner)
    view = None
    original_connect = socket.socket.connect
    def no_network(*args, **kwargs): raise AssertionError("No service/network IO in speech settings fixture")
    socket.socket.connect = no_network
    def js(code):
        values = []
        view.page().runJavaScript("JSON.stringify((()=>{" + code + "})())", values.append)
        end = time.monotonic() + 5
        while not values and time.monotonic() < end: app.processEvents(); time.sleep(.005)
        if not values: raise TimeoutError("JavaScript callback")
        return json.loads(values[0]) if values[0] else None
    def until(code):
        end = time.monotonic() + 12
        while time.monotonic() < end:
            if js("return (" + code + ");"): return
            app.processEvents(); time.sleep(.02)
        raise TimeoutError(code)
    def check(name, passed):
        result["checks"].append({"name": name, "passed": bool(passed)})
        if not passed: raise AssertionError(name)
    def section(label):
        js("[...document.querySelectorAll('.settings-nav-item')].find(n=>n.querySelector('strong')?.textContent===" + json.dumps(label) + ").click();")
    try:
        view = create_existing_window_host(owner, bundle); owner.setCentralWidget(view); owner.show()
        until("!!document.querySelector('.rail-button[data-mode=settings]')")
        js("document.querySelector('.rail-button[data-mode=settings]').click();")
        section("語音與感知")
        until("!!document.querySelector('[name=chatSpeechPolicy]:not(:disabled)')")
        check("signed-source-pin", bundle.pin == RELEASE_PIN)
        check("default-values", js("return document.querySelector('[name=chatSpeechPolicy]').value==='summary' && document.querySelector('[name=chatSpeechLocale]').value==='ja-JP';"))
        check("three-policies", js("return [...document.querySelector('[name=chatSpeechPolicy]').options].map(o=>o.value).join(',')==='brief,summary,detailed';"))
        check("locale-capability-truth", js("return [...document.querySelector('[name=chatSpeechLocale]').options].filter(o=>o.value!=='ja-JP').every(o=>o.textContent.includes('未驗證')) && document.querySelector('[data-owner-chat-speech]').textContent.includes('暫不送合成');"))
        check("separate-Core-proactiveVoice", js("return !!document.querySelector('[name=proactiveVoice]') && document.querySelector('[name=proactiveVoice]').disabled && !document.querySelector('[name=chatSpeechPolicy]').disabled;"))
        js("window.__speechPanel=document.querySelector('[data-owner-chat-speech]'); document.querySelector('[name=chatSpeechPolicy]').value='detailed'; document.querySelector('[name=chatSpeechLocale]').value='en-US';")
        view.owner_port.publish("onState", view.owner_port.adapter.chat_state())
        until("document.querySelector('[data-owner-chat-speech]')===window.__speechPanel")
        check("polling-keeps-draft", js("return document.querySelector('[name=chatSpeechPolicy]').value==='detailed';"))
        js("document.querySelector('[data-chat-speech-save]').click();")
        until("document.querySelector('[data-chat-speech-status]').textContent.includes('已儲存並讀回')")
        check("real-Launcher-YAML-roundtrip", actual.read_chat_speech_settings()["settings"] == {"locale":"en-US", "policy":"detailed", "route":"dual_lane"})
        section("工具與權限"); section("語音與感知")
        check("navigation-retains-values", js("return document.querySelector('[name=chatSpeechLocale]').value==='en-US' && document.querySelector('[name=chatSpeechPolicy]').value==='detailed';"))
        read = actual.read_chat_speech_settings()
        actual.update_chat_speech_settings({"locale":"ja-JP", "policy":"brief", "route":"dual_lane"}, read["revision"])
        js("document.querySelector('[data-chat-speech-reload]').click();")
        until("!document.querySelector('[name=chatSpeechPolicy]').disabled && document.querySelector('[name=chatSpeechPolicy]').value==='brief'")
        check("reload-reads-owner", js("return document.querySelector('[name=chatSpeechLocale]').value==='ja-JP';"))
        check("no-input-language-control", js("return ![...document.querySelectorAll('select,input')].some(n=>/inputLanguage|asrLanguage/.test(n.name));"))
        check("private-web-profile", view.page().profile().isOffTheRecord())
        result.update(status="ISOLATED_DOM_PASS", fingerprint=RELEASE_PIN.fingerprint)
    except Exception as exc:
        result.update(status="FAIL", errorType=type(exc).__name__, error=str(exc))
        raise
    finally:
        socket.socket.connect = original_connect
        if view is not None: view.shutdown_candidate(); owner.close(); view.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete); app.processEvents()
        (output / "Result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__": raise SystemExit(main())
