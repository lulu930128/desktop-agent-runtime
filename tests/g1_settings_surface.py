"""Explicit isolated signed Qt Web surface probe. No formal Launcher/WS startup.

Uses disposable Core storage and automatic answers to this fixture's real Qt
dialogs. This proves DOM/transport behavior, not physical gestures or adoption.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests'), str(ROOT/'Open-LLM-VTuber/src')]


def owned_children():
    """Read PID/parent identity only; no command lines or process termination."""
    import ctypes
    from ctypes import wintypes as w
    class Entry(ctypes.Structure):
        _fields_=[('size',w.DWORD),('usage',w.DWORD),('pid',w.DWORD),('heap',ctypes.c_size_t),
                  ('module',w.DWORD),('threads',w.DWORD),('parent',w.DWORD),('priority',w.LONG),
                  ('flags',w.DWORD),('exe',w.WCHAR*260)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD]
    kernel.CreateToolhelp32Snapshot.restype=w.HANDLE
    kernel.Process32FirstW.argtypes=kernel.Process32NextW.argtypes=[w.HANDLE,ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes=[w.HANDLE]
    handle=kernel.CreateToolhelp32Snapshot(2,0)
    if handle==ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
    rows=[]; entry=Entry(); entry.size=ctypes.sizeof(entry)
    try:
        more=kernel.Process32FirstW(handle,ctypes.byref(entry))
        while more:
            rows.append(dict(pid=entry.pid,parentPid=entry.parent,name=entry.exe))
            more=kernel.Process32NextW(handle,ctypes.byref(entry))
    finally: kernel.CloseHandle(handle)
    parents={os.getpid()}; children=[]
    while True:
        found=[row for row in rows if row['parentPid'] in parents and row['pid'] not in parents]
        if not found: return children
        children.extend(found); parents.update(row['pid'] for row in found)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    if output.resolve() != output or not output.is_relative_to(ROOT/'.tmp') or output.exists():
        parser.error('New repo .tmp directory required')
    output.mkdir()
    result = dict(status='RUNNING', pid=os.getpid(), parentPid=os.getppid(),
        started=datetime.now(timezone.utc).isoformat(), synthetic=True, productionAdoption=False,
        physicalGestures='UNVERIFIED', checks=[], confirmations=[])
    core = view = owner = None
    record = json.loads(args.bundle_receipt.read_text(encoding='utf-8'))
    from kuro_launcher.qt_web_release import OwnerBundlePin, VerifiedOwnerBundle
    from kuro_launcher.qt_web_host import register_candidate_scheme, create_existing_window_host
    pin = OwnerBundlePin(record['fingerprint'], record['manifestSha256'], record['publicKey'], record['signature'])
    bundle = VerifiedOwnerBundle.load(ROOT/'assets/qt-owner'/pin.fingerprint, pin)
    result['fingerprint'] = pin.fingerprint
    register_candidate_scheme()
    from PySide6.QtCore import QTimer, QEvent
    from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
    from kuro_core.core_app import CoreApplication
    from kuro_launcher.qt_controller import QtLauncherController
    from kuro_launcher.qt_chat_client import QtRuntimeChatClient
    from kuro_launcher.core_runtime import CoreRuntime
    from web_candidate_fixtures import controller_fixture
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    decision = [QMessageBox.StandardButton.No]
    seen = set()

    def answer_fixture_dialog():
        for widget in app.topLevelWidgets():
            if isinstance(widget, QMessageBox) and widget.isVisible() and id(widget) not in seen:
                seen.add(id(widget))
                result['confirmations'].append(dict(method=widget.text().split('\n')[0],
                    defaultNo=widget.defaultButton()==widget.button(QMessageBox.StandardButton.No),
                    accepted=decision[0]==QMessageBox.StandardButton.Yes, automatedFixture=True))
                widget.button(decision[0]).click()

    timer = QTimer(); timer.timeout.connect(answer_fixture_dialog); timer.start(20)
    original_connect = socket.socket.connect
    def bounded_connect(sock, address):
        if not core or address[0] != '127.0.0.1' or address[1] != core.port:
            raise RuntimeError('Synthetic Core endpoint only')
        return original_connect(sock, address)
    socket.socket.connect = bounded_connect

    def check(name, value):
        result['checks'].append(dict(name=name, passed=bool(value)))
        if not value: raise AssertionError(name)

    def js(code):
        values = []
        view.page().runJavaScript('JSON.stringify((()=>{'+code+'})())', values.append)
        end = time.monotonic()+5
        while not values and time.monotonic()<end:
            app.processEvents(); time.sleep(.005)
        if not values: raise TimeoutError('JavaScript callback')
        return json.loads(values[0]) if values[0] else None

    def until(code):
        end = time.monotonic()+12
        while time.monotonic()<end:
            if js('return ('+code+');'): return
            app.processEvents(); time.sleep(.02)
        raise TimeoutError('DOM condition: '+code)

    def section(label):
        js("[...document.querySelectorAll('.settings-nav-item')].find(n=>n.querySelector('strong')?.textContent==="+json.dumps(label)+").click();")
        until("!!document.querySelector('[data-owner-assistant-settings] input:not(:disabled)')")

    try:
        token='synthetic-g1-surface-core-token-0000'
        core=CoreApplication(output/'synthetic.sqlite3',port=0,token=token,instance_id='synthetic-g1-surface')
        core.api.start()  # No schedule worker or provider integrations.
        result['corePort']=core.port
        actual=QtLauncherController.__new__(QtLauncherController)
        actual.core_runtime=CoreRuntime(SimpleNamespace(core_enabled=True,core_port=core.port),lambda _:None)
        actual.core_runtime.token=token
        controller=controller_fixture()
        controller.read_assistant_settings=actual.read_assistant_settings
        controller.update_assistant_settings=actual.update_assistant_settings
        controller.presentation_state.return_value={'ok':False,'state':'unavailable'}
        controller.read_companion_diagnostics.return_value={'ok':False,'state':'unavailable'}
        owner=QMainWindow(); owner.resize(1100,820)
        owner.controller=controller; owner.chat_client=QtRuntimeChatClient(owner)
        owner._apply_lifecycle_status=Mock()
        view=create_existing_window_host(owner,bundle)
        owner.setCentralWidget(view); owner.show()
        until("!!document.querySelector('.rail-button[data-mode=settings]')")
        js("document.querySelector('.rail-button[data-mode=settings]').click();")
        section('語音與感知')
        check('voice-default-off', js("return document.querySelector('[name=proactiveVoice]').checked === false;"))
        section('工具與權限')
        check('omi-default-off',js("return !document.querySelector('[name=omiEnabled]').checked;"))
        check('utf8-and-inactive-status',js("const p=document.querySelector('[data-owner-assistant-settings]'); return p.textContent.includes('觀測間隔（分鐘，5–1440）') && p.textContent.includes('G1 execution unavailable') && !p.textContent.includes('\ufffd');"))
        js("window.__g1Panel=document.querySelector('[data-owner-assistant-settings]'); document.querySelector('[name=omiEnabled]').checked=true; document.querySelector('[name=intervalMinutes]').value='17'; document.querySelector('[name=dailyQueryBudget]').value='3';")
        view.owner_port.publish('onState',view.owner_port.adapter.chat_state())
        until("document.querySelector('[data-owner-assistant-settings]')===window.__g1Panel")
        check('polling-keeps-same-form-and-draft',js("return document.querySelector('[name=intervalMinutes]').value==='17' && document.querySelector('[name=omiEnabled]').checked;"))
        section('語音與感知'); section('工具與權限')
        check('tab-switch-keeps-draft',js("return document.querySelector('[name=intervalMinutes]').value==='17';"))
        js("document.querySelector('[data-settings-save]').click();")
        until("document.querySelector('[data-settings-status]').textContent.includes('已取消')")
        check('native-cancel-no-sidecar',not core.assistant_settings.path.exists())
        js("document.querySelector('[data-settings-reload]').click();")
        until("!document.querySelector('[name=omiEnabled]').disabled")
        decision[0]=QMessageBox.StandardButton.Yes; seen.clear()
        js("document.querySelector('[name=omiEnabled]').checked=true; document.querySelector('[name=intervalMinutes]').value='17'; document.querySelector('[name=dailyQueryBudget]').value='3'; document.querySelector('[data-settings-save]').click();")
        until("document.querySelector('[data-settings-status]').textContent.includes('偏好已儲存並由 Core 讀回')")
        saved=core.assistant_settings.read({})
        check('omi-real-core-json-readback',saved['settings']['omi']==dict(enabled=True,intervalMinutes=17,dailyQueryBudget=3))
        check('omi-saved-ui-check',js("return document.querySelector('[name=omiEnabled]').checked && document.querySelector('[name=intervalMinutes]').value==='17';"))
        view.grab().save(str(output/'omi.png'))
        section('語音與感知'); seen.clear()
        js("document.querySelector('[name=proactiveVoice]').checked=true; document.querySelector('[data-settings-save]').click();")
        until("!document.querySelector('[data-settings-save]').disabled && document.querySelector('[data-settings-status]').textContent.includes('偏好已儲存並由 Core 讀回')")
        saved=core.assistant_settings.read({})
        check('independent-voice-and-omi-persistence',saved['settings']==dict(proactiveVoice=True,omi=dict(enabled=True,intervalMinutes=17,dailyQueryBudget=3)))
        check('execution-still-closed',not saved['runtime']['omi']['allowed'] and not saved['runtime']['proactiveVoice']['allowed'])
        view.grab().save(str(output/'voice.png'))
        result['visualAcceptance']='UNVERIFIED: offscreen D3D context lost; captures are not visual proof'
        check('real-native-confirmation-default-no',len(result['confirmations'])==3 and all(c['defaultNo'] for c in result['confirmations']))
        check('private-web-profile',view.page().profile().isOffTheRecord())
        result['settingsReadback']=saved
        result['ownedChildren']=owned_children()
        result['status']='ISOLATED_SURFACE_PASS'
    except Exception as exc:
        result['status']='FAILED'; result['errorType']=type(exc).__name__; result['error']=str(exc)
        raise
    finally:
        timer.stop()
        if view is not None: view.shutdown_candidate(); owner.close(); view.deleteLater()
        app.sendPostedEvents(None,QEvent.Type.DeferredDelete); app.processEvents()
        if core: core.stop()
        socket.socket.connect=original_connect
        result['ended']=datetime.now(timezone.utc).isoformat()
        (output/'Result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(dict(status=result['status'],checks=len(result['checks']),pid=os.getpid())))
    return 0


if __name__=='__main__': raise SystemExit(main())
