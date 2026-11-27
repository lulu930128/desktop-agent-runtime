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
    parser.add_argument('--refinement', action='store_true', help='Presentation-only compact UI checks and zoom captures')
    parser.add_argument('--banner-regression', action='store_true', help='Require RELEASE_PIN and check banner removal/layout in real Qt')
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
    from kuro_launcher.qt_web_release import OwnerBundlePin, VerifiedOwnerBundle, RELEASE_PIN, prepare_owner_presentation
    from kuro_launcher.qt_web_host import register_candidate_scheme, create_existing_window_host
    pin = OwnerBundlePin(record['fingerprint'], record['manifestSha256'], record['publicKey'], record['signature'])
    if args.banner_regression:
        if pin != RELEASE_PIN: raise ValueError('Banner regression requires the authoritative RELEASE_PIN')
        bundle = prepare_owner_presentation(ROOT)
    else:
        bundle = VerifiedOwnerBundle.load(ROOT/'assets/qt-owner'/pin.fingerprint, pin)
        register_candidate_scheme()
    result['fingerprint'] = pin.fingerprint
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

    def capture(name):
        # Chromium paint is asynchronous even after its DOM callback completes.
        for _ in range(20): app.processEvents(); time.sleep(.01)
        view.grab().save(str(output/name))

    def check_banner_layout(label):
        layout = js("""const w=document.querySelector('.workspace'),h=w.querySelector('.chrome'),s=w.querySelector('.stage');
          const wr=w.getBoundingClientRect(),hr=h.getBoundingClientRect(),sr=s.getBoundingClientRect();
          return {bannerCount:document.querySelectorAll('[data-runtime-status]').length,
            statusButtons:[...document.querySelectorAll('button')].filter(n=>n.textContent.trim()==='查看狀態').length,
            rows:getComputedStyle(w).gridTemplateRows,stageRow:getComputedStyle(s).gridRowStart,
            gap:sr.top-hr.bottom,bottomGap:wr.bottom-sr.bottom,stageHeight:sr.height};""")
        result.setdefault('bannerLayouts', []).append(dict(label=label, **layout))
        check(label+'-banner-and-action-absent',layout['bannerCount']==0 and layout['statusButtons']==0)
        check(label+'-two-rows-no-empty-track',len(layout['rows'].split())==2 and layout['stageRow']=='2'
            and abs(layout['gap'])<=1 and abs(layout['bottomGap'])<=1 and layout['stageHeight']>100)

    try:
        from unittest.mock import patch
        from test_g2_integration_boundaries import LifecycleTests, parts
        from kuro_launcher.tool_policy_settings import ToolPolicySettings, CATALOG, GROUPS
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
            if args.refinement and name=='japanese_study':
                payload[1]['items']=[{**payload[1]['items'][0], 'item_id':'fixture-'+str(i),
                    'title':'Synthetic review '+str(i+1), 'meaning_tc':'Source example '+str(i+1)} for i in range(5)]
                payload[1]['count']=5
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
        if args.banner_regression: check_banner_layout('initial-render')
        js("document.querySelector('.rail-button[data-mode=settings]').click();")
        js("[...document.querySelectorAll('.settings-nav-item')].find(n=>n.querySelector('strong')?.textContent==='\u5de5\u5177\u8207\u6b0a\u9650').click();")
        expected_tools = len(CATALOG)
        until(f"document.querySelectorAll('[data-tool-toggle]:not(:disabled)').length==={expected_tools}")
        check('registered-labelled-tools-and-native-fold-groups',js(f"return document.querySelectorAll('[data-tool-service]').length==={len(GROUPS)} && [...document.querySelectorAll('[data-tool-toggle]')].every(n=>n.getAttribute('aria-label').includes('\u555f\u7528'));"))
        check('workspace-chinese-purposes',js("return document.querySelector('[data-owner-tool-settings]').textContent.includes('專案工作區') && document.querySelector('[data-owner-tool-settings]').textContent.includes('批次讀取檔案');"))
        check('raw-original-list-removed',js("return !document.querySelector('.tool-list');"))
        if args.refinement:
            check('groups-default-collapsed-with-enabled-count',js("return [...document.querySelectorAll('[data-tool-service]')].every(n=>!n.open && /[0-9]+ \\/ [0-9]+/.test(n.querySelector('summary').textContent));"))
            capture('tools-folded.png')
            for zoom in (1.25,1.5):
                view.setZoomFactor(zoom)
                capture('tools-folded-zoom-'+str(zoom)+'.png')
                check('tool-groups-fit-zoom-'+str(zoom),js("return [...document.querySelectorAll('[data-tool-service]')].every(n=>n.scrollWidth<=n.clientWidth+1) && parseFloat(getComputedStyle(document.querySelector('[data-tool-status]')).fontSize)>=12;"))
            view.setZoomFactor(1)
        check('omi-independent-inactive-section',js("return document.querySelector('[data-owner-assistant-settings]').textContent.includes('\u80cc\u666f\u89c0\u6e2c\u5c1a\u672a\u53ef\u7528');"))
        js("window.__tools=document.querySelector('[data-owner-tool-settings]'); document.querySelector('[data-tool-service]').open=false;")
        view.owner_port.publish('onState',view.owner_port.adapter.chat_state())
        until("document.querySelector('[data-owner-tool-settings]')===window.__tools")
        check('polling-preserves-fold-and-panel',js("return document.querySelector('[data-tool-service]').open===false;"))
        js("document.querySelector('[data-tool-service]').open=true; document.querySelector('[data-tool-toggle]').click();")
        until("document.querySelector('[data-tool-status]').textContent.includes('\u5df2\u53d6\u6d88')")
        check('native-cancel-no-write',(output/'tool_policy.json').read_bytes()==original)
        js("document.querySelector('[data-tool-reload]').click();")
        until(f"document.querySelectorAll('[data-tool-toggle]:not(:disabled)').length==={expected_tools}")
        decision[0]=QMessageBox.StandardButton.Yes; seen.clear()
        js("document.querySelector('[data-tool-toggle]').click();")
        until("document.querySelector('[data-tool-status]').textContent.includes('\u5132\u5b58\u6210\u529f\u4e26\u5df2\u8b80\u56de')")
        read=ToolPolicySettings(output/'tool_policy.json').read()
        check('native-confirm-persisted-and-ui-readback',read['tools'][0]['enabled'] is False and js("return !document.querySelector('[data-tool-toggle]').checked;"))
        for name in CATALOG:
            if not name.split('::')[0] in {'project-workspace', 'omi-search', 'japanese-study', 'english-study', 'listening-audio', 'memory-core', 'personal-asset-os'}: continue
            selector = '[data-tool-toggle="' + name + '"]'
            js(f"document.querySelector({json.dumps(selector)}).closest('details').open=true;")
            for enabled in (False, True):
                seen.clear()
                js(f"document.querySelector({json.dumps(selector)}).click();")
                until("document.querySelector('[data-tool-status]').textContent.includes('\u5132\u5b58\u6210\u529f\u4e26\u5df2\u8b80\u56de')")
                readback = ToolPolicySettings(output/'tool_policy.json').read()
                check(name+'-persisted-'+str(enabled),next(r for r in readback['tools'] if r['name']==name)['enabled'] is enabled
                    and js(f"return document.querySelector({json.dumps(selector)}).checked=== {'true' if enabled else 'false'};"))
        check('no-hot-adoption-claim',js("return document.querySelector('[data-tool-status]').textContent.includes('\u57f7\u884c\u74b0\u5883\u5c1a\u672a\u9a57\u8b49\u63a1\u7528');"))
        check('confirm-tools-still-blocked',all(not r['allowed'] for r in read['tools'] if r['mode']=='confirm'))
        capture('tools.png')
        js("document.querySelector('.rail-button[data-mode=today]').click();")
        until("document.querySelectorAll('[data-owner-source-overview] article').length===4")
        check('english-empty-with-time-limitation',js("return document.querySelector('[data-owner-source-overview]').textContent.includes('\u672c\u6b21\u53d6\u5f97\u7684\u6e05\u55ae\u6c92\u6709\u5f85\u8fa6') && document.querySelector('[data-owner-source-overview]').textContent.includes('\u4f86\u6e90\u672a\u63d0\u4f9b\u89c0\u5bdf\u6642\u9593');"))
        check('mail-auth-and-omi-blocked-visible',js("const t=document.querySelector('[data-owner-source-overview]').textContent; return t.includes('\u9700\u8981\u6388\u6b0a') && t.includes('\u80cc\u666f\u81ea\u52d5\u89c0\u6e2c\u5c1a\u672a\u53ef\u7528');"))
        check('independent-study-filters',js("return [...document.querySelectorAll('.source-filter')].some(n=>n.textContent.includes('\u82f1\u6587\u5b78\u7fd2'));"))
        js("[...document.querySelectorAll('.source-filter')].find(n=>n.textContent.includes('\u82f1\u6587\u5b78\u7fd2')).click();")
        check('english-filter-is-selectable',js("return document.querySelector('.source-filter.is-active').textContent.includes('\u82f1\u6587\u5b78\u7fd2');"))
        check('no-invented-tasks',len(core.today.read({})['items'])==(5 if args.refinement else 1))
        expected_confirmations = 2 + 2 * sum(name.split('::')[0] in {'project-workspace', 'omi-search', 'japanese-study', 'english-study', 'listening-audio', 'memory-core', 'personal-asset-os'} for name in CATALOG)
        check('native-default-no',len(result['confirmations'])==expected_confirmations and all(c['defaultNo'] for c in result['confirmations']))
        capture('today.png')
        if args.refinement:
            check('priority-before-folded-diagnostics',js("const h=document.querySelector('.today-frame>header'),s=h.nextElementSibling,p=s.nextElementSibling,d=p.nextElementSibling; return s.hasAttribute('data-owner-source-strip') && p.classList.contains('today-primary') && d.hasAttribute('data-owner-source-overview') && !d.open;"))
            check('raw-times-retained',js("return [...document.querySelectorAll('.owner-source-detail')].every(n=>n.querySelector('pre').textContent.includes('receivedAt') && n.querySelector('.owner-source-time').textContent.length>0);"))
            from PySide6.QtCore import Qt
            from PySide6.QtTest import QTest
            from kuro_launcher.qt_web_adapter import today_projection
            view.setFocus()
            js("window.__overview=document.querySelector('[data-owner-source-overview]'); window.__overview.querySelector('summary').focus();")
            QTest.keyClick(view.focusProxy(),Qt.Key.Key_Space)
            until("window.__overview.open")
            check('details-keyboard-and-visible-focus',js("return document.activeElement===window.__overview.querySelector('summary') && getComputedStyle(document.activeElement).outlineStyle==='solid';"))
            js("window.__overview.querySelector('details').open=true;")
            view.owner_port.publish('onData',today_projection(actual.read_today()))
            until("document.querySelector('[data-owner-source-overview]')===window.__overview")
            check('source-folds-survive-poll',js("return window.__overview.open && window.__overview.querySelector('details').open;"))
            capture('today-details.png')
            js("window.__overview.open=false; document.querySelector('.source-filter').click();")
            result['zoomChecks']=[]
            for zoom in (1,1.25,1.5):
                view.setZoomFactor(zoom)
                for _ in range(15): app.processEvents(); time.sleep(.01)
                layout=js("const s=document.querySelector('[data-owner-source-strip]'),p=document.querySelector('.today-primary'); return {width:innerWidth,stripHeight:s.getBoundingClientRect().height,priorityTop:p.getBoundingClientRect().top,overflow:s.scrollWidth>s.clientWidth+1,fontSize:getComputedStyle(s.querySelector('li')).fontSize};")
                result['zoomChecks'].append(dict(zoom=zoom,**layout))
                check('compact-strip-zoom-'+str(zoom),not layout['overflow'] and layout['stripHeight']<150 and float(layout['fontSize'].replace('px',''))>=12)
                capture('today-zoom-'+str(zoom)+'.png')
            view.setZoomFactor(1)
            js("document.querySelector('.rail-button[data-mode=chat]').click();")
            until("!!document.querySelector('[data-owner-attachment-help]')")
            check('attachment-help-on-demand-accessible',js("const h=document.querySelector('[data-owner-attachment-help]'),a=document.querySelector('[data-attach]'); return !h.open && !document.querySelector('[data-owner-attachment-caps]') && a.title.includes('4 MiB') && a.getAttribute('aria-describedby')===h.querySelector('p').id && !!document.querySelector('[data-model-select]') && !!document.querySelector('[data-composer-input]');"))
            capture('chat-folded.png')
            js("document.querySelector('[data-owner-attachment-help]').open=true;")
            check('attachment-full-limits-reachable',js("return document.querySelector('[data-owner-attachment-help] p').textContent.includes('8 MiB');"))
            capture('chat-help.png')
        if args.banner_regression:
            for mode in ('chat','today','chat','today'):
                js("document.querySelector('.rail-button[data-mode="+mode+"]').click();")
                until("document.querySelector('.rail-button[data-mode="+mode+"]').classList.contains('is-active')")
                # Reproduce connected + cold voice + visible Pet without a real WS/service.
                state=view.owner_port.adapter.chat_state()
                state.update(wsConnected=True,capabilities={'pet':{'state':'ready'},
                    'launcher':{'phase':'ready','voice':{'state':'cold','reason':'SYNTHETIC cold voice'},'restartRequired':False}})
                view.owner_port.publish('onState',state)
                until("document.querySelector('[data-presence-label]').textContent==='對話已連線'")
                check_banner_layout(mode+'-state-render')
                # A later shell insertion must also be removed, including its button.
                js("""window.__bannerMutations=0;
                  window.__bannerObserver=new MutationObserver(rows=>{window.__bannerMutations+=rows.length;});
                  const w=document.querySelector('.workspace');
                  window.__bannerObserver.observe(w,{childList:true,attributes:true});
                  const n=document.createElement('div');n.setAttribute('data-runtime-status','');
                  n.textContent='對話已連線 · 首次發聲需載入語音 · 角色可見';
                  const b=document.createElement('button');b.textContent='查看狀態';n.append(b);
                  w.insertBefore(n,w.querySelector('.stage'));""")
                until("!document.querySelector('[data-runtime-status]')")
                js("window.__bannerSettled=false;requestAnimationFrame(()=>requestAnimationFrame(()=>{window.__bannerSettled=true;}));")
                until("window.__bannerSettled")
                check(mode+'-observer-settles-after-removal',js("window.__bannerObserver.disconnect();return window.__bannerMutations===2;"))
                for zoom in (1,1.25,1.5):
                    view.setZoomFactor(zoom)
                    capture(mode+'-no-banner-'+str(zoom)+'.png')
                    check_banner_layout(mode+'-zoom-'+str(zoom))
                view.setZoomFactor(1)
            js("document.querySelector('.rail-button[data-mode=settings]').click();")
            js("[...document.querySelectorAll('.settings-nav-item')].find(n=>n.querySelector('strong')?.textContent==='進階診斷').click();")
            until("[...document.querySelectorAll('.diagnostic-row dt')].some(n=>n.textContent==='功能狀態')")
            check('settings-diagnostics-still-reachable',js("return document.querySelector('.settings-content').textContent.includes('目前 Runtime') && [...document.querySelectorAll('.diagnostic-row dt')].some(n=>n.textContent==='語音狀態');"))
            capture('diagnostics.png')
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
