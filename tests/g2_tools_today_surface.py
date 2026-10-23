"""G2 isolated tools and source overview surface probe. No formal Launcher/WS startup.

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
        result['failedDom'] = js("return {text:document.getElementById('app')?.textContent, toggles:document.querySelectorAll('[data-tool-toggle]').length};")
        result['directTools'] = actual.read_tool_policy_summary()
        raise TimeoutError('DOM condition: '+code)

    try:
        from unittest.mock import patch
        from test_g2_integration_boundaries import LifecycleTests, parts
        from kuro_launcher.tool_policy_settings import ToolPolicySettings
        from g2_fixtures import mail_status
        schedule = LifecycleTests().schedule(output/'unused.db')
        stamp=datetime.now(timezone.utc)
        status=mail_status(stamp.isoformat(),ok=False); status['errorType']='auth_required'
        (output/'mail-status.json').write_text(json.dumps(status),encoding='utf-8')
        with patch('kuro_core.core_app.ScheduleCapability',return_value=schedule):
            core=CoreApplication(output/'unused.db',port=0,token='synthetic-g2-tools-surface-token-0000',
                instance_id='synthetic-g2-tools-surface',hubs={s:{'enabled':True} for s in ('japanese_study','english_study')},
                mail_enabled=True,mail_status_path=output/'mail-status.json',mail_work_path=output/'absent-work.json')
        for name in ('japanese_study','english_study'):
            payload=parts(name,rows=name=='japanese_study')
            core.integrations.readonly_sources[name].snapshot=(payload,stamp)
        core.api.start()  # No integration/Schedule workers or provider calls.
        result['corePort']=core.port
        (output/'tool_policy.json').write_bytes((ROOT/'Open-LLM-VTuber/tool_policy.json').read_bytes())
        original=(output/'tool_policy.json').read_bytes()
        actual=QtLauncherController.__new__(QtLauncherController)
        actual.cfg=SimpleNamespace(open_llm_dir=output)
        actual.core_runtime=CoreRuntime(SimpleNamespace(core_enabled=True,core_port=core.port),lambda _:None)
        actual.core_runtime.token='synthetic-g2-tools-surface-token-0000'
        controller=controller_fixture()
        controller.read_today=actual.read_today
        controller.read_tool_policy_summary=actual.read_tool_policy_summary
        controller.update_tool_policy=actual.update_tool_policy
        controller.read_assistant_settings=actual.read_assistant_settings
        controller.update_assistant_settings=actual.update_assistant_settings
        controller.presentation_state.return_value={'ok':False,'state':'unavailable'}
        controller.read_companion_diagnostics.return_value={'ok':False,'state':'unavailable'}
        owner=QMainWindow(); owner.setWindowTitle('SYNTHETIC G2 acceptance'); owner.resize(1100,820)
        owner.controller=controller; owner.chat_client=QtRuntimeChatClient(owner)
        owner._apply_lifecycle_status=Mock()
        view=create_existing_window_host(owner,bundle)
        owner.setCentralWidget(view); owner.show()
        until("!!document.querySelector('.rail-button[data-mode=settings]')")
        js("document.querySelector('.rail-button[data-mode=settings]').click();")
        js("[...document.querySelectorAll('.settings-nav-item')].find(n=>n.querySelector('strong')?.textContent==='\u5de5\u5177\u8207\u6b0a\u9650').click();")
        until("document.querySelectorAll('[data-tool-toggle]:not(:disabled)').length===21")
        check('21-labelled-tools-4-native-fold-groups',js("return document.querySelectorAll('[data-tool-service]').length===4 && [...document.querySelectorAll('[data-tool-toggle]')].every(n=>n.getAttribute('aria-label').includes('\u555f\u7528'));"))
        check('raw-original-list-removed',js("return !document.querySelector('.tool-list');"))
        check('omi-independent-inactive-section',js("return document.querySelector('[data-owner-assistant-settings]').textContent.includes('\u80cc\u666f\u89c0\u6e2c\u5c1a\u672a\u53ef\u7528');"))
        js("window.__tools=document.querySelector('[data-owner-tool-settings]'); document.querySelector('[data-tool-service]').open=false;")
        view.owner_port.publish('onState',view.owner_port.adapter.chat_state())
        until("document.querySelector('[data-owner-tool-settings]')===window.__tools")
        check('polling-preserves-fold-and-panel',js("return document.querySelector('[data-tool-service]').open===false;"))
        js("document.querySelector('[data-tool-service]').open=true; document.querySelector('[data-tool-toggle]').click();")
        until("document.querySelector('[data-tool-status]').textContent.includes('\u5df2\u53d6\u6d88')")
        check('native-cancel-no-write',(output/'tool_policy.json').read_bytes()==original)
        js("document.querySelector('[data-tool-reload]').click();")
        until("document.querySelectorAll('[data-tool-toggle]:not(:disabled)').length===21")
        decision[0]=QMessageBox.StandardButton.Yes; seen.clear()
        js("document.querySelector('[data-tool-toggle]').click();")
        until("document.querySelector('[data-tool-status]').textContent.includes('\u5132\u5b58\u6210\u529f\u4e26\u5df2\u8b80\u56de')")
        read=ToolPolicySettings(output/'tool_policy.json').read()
        check('native-confirm-persisted-and-ui-readback',read['tools'][0]['enabled'] is False and js("return !document.querySelector('[data-tool-toggle]').checked;"))
        check('no-hot-adoption-claim',js("return document.querySelector('[data-tool-status]').textContent.includes('\u57f7\u884c\u74b0\u5883\u5c1a\u672a\u9a57\u8b49\u63a1\u7528');"))
        check('confirm-tools-still-blocked',all(not r['allowed'] for r in read['tools'] if r['mode']=='confirm'))
        view.grab().save(str(output/'tools.png'))
        js("document.querySelector('.rail-button[data-mode=today]').click();")
        until("document.querySelectorAll('[data-owner-source-overview] article').length===4")
        check('english-empty-with-time-limitation',js("return document.querySelector('[data-owner-source-overview]').textContent.includes('\u672c\u6b21\u53d6\u5f97\u7684\u6e05\u55ae\u6c92\u6709\u5f85\u8fa6') && document.querySelector('[data-owner-source-overview]').textContent.includes('\u4f86\u6e90\u672a\u63d0\u4f9b\u89c0\u5bdf\u6642\u9593');"))
        check('mail-auth-and-omi-blocked-visible',js("const t=document.querySelector('[data-owner-source-overview]').textContent; return t.includes('\u9700\u8981\u6388\u6b0a') && t.includes('\u80cc\u666f\u81ea\u52d5\u89c0\u6e2c\u5c1a\u672a\u53ef\u7528');"))
        check('independent-study-filters',js("return [...document.querySelectorAll('.source-filter')].some(n=>n.textContent.includes('\u82f1\u6587\u5b78\u7fd2'));"))
        js("[...document.querySelectorAll('.source-filter')].find(n=>n.textContent.includes('\u82f1\u6587\u5b78\u7fd2')).click();")
        check('english-filter-is-selectable',js("return document.querySelector('.source-filter.is-active').textContent.includes('\u82f1\u6587\u5b78\u7fd2');"))
        check('no-invented-tasks',len(core.today.read({})['items'])==1)
        check('native-default-no',len(result['confirmations'])==2 and all(c['defaultNo'] for c in result['confirmations']))
        view.grab().save(str(output/'today.png'))
        result['visualAcceptance']='UNVERIFIED until screenshot inspection; physical gestures not tested'
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
