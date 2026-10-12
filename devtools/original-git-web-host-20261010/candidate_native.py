"""Visible SYNTHETIC QMainWindow + actual feature-off candidate, never launcher.

Requires the existing task Qt environment. A hidden disposable sidecar uses the
existing test interpreter for Core/Memory and synthetic WS; no package installs.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import traceback
from types import SimpleNamespace
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TEST_PYTHON = ROOT/'envs/kuro-llm310/python.exe'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=900)
    parser.add_argument('--checkpoint', choices=['W3','W5'], default='W5')
    args = parser.parse_args(); output = args.output.resolve()
    if not output.is_relative_to(HERE/'.runtime') or output.exists(): parser.error('New task-local output required')
    if not 15 <= args.seconds <= 1200: parser.error('Duration must be 15..1200 seconds')
    output.mkdir(parents=True)
    (output/'SYNTHETIC-attachment.txt').write_text('SYNTHETIC attachment; no private information.\n',encoding='utf-8')
    result = {'synthetic':True,'checkpoint':args.checkpoint,'pid':os.getpid(),'executable':sys.executable,
        'native':'UNVERIFIED','humanReview':'UNVERIFIED','ime':'UNVERIFIED','productionAdoption':False,
        'createdUtc':datetime.now(timezone.utc).isoformat(),'actions':[]}
    process = None; service_log = None; window = None; exit_code = 2
    lock = threading.Lock()
    def audit(kind, **fields):
        with lock: result['actions'].append({'kind':kind, **fields})
    try:
        if Path(sys.prefix).resolve() != HERE/'.venv': raise RuntimeError('Use existing task .venv')
        sys.path.insert(0,str(HERE))
        from w1_smoke import check_environment
        check_environment(os.environ)
        from PySide6.QtCore import QTimer, QUrl, qVersion
        from PySide6.QtWidgets import QApplication, QMainWindow
        from PySide6.QtWebEngineWidgets import QWebEngineView
        # Qt import must succeed first. Load only the existing pure-Python WS
        # package, not another interpreter's site-packages or PySide DLLs.
        ws_package = ROOT/'envs/kuro-llm310/Lib/site-packages/websocket'
        spec = importlib.util.spec_from_file_location('websocket', ws_package/'__init__.py', submodule_search_locations=[str(ws_package)])
        module = importlib.util.module_from_spec(spec); sys.modules['websocket'] = module; spec.loader.exec_module(module)
        result['websocketSource'] = {str(p.relative_to(ws_package)):hashlib.sha256(p.read_bytes()).hexdigest() for p in ws_package.rglob('*.py')}
        sys.path[:0] = [str(ROOT),str(ROOT/'tests')]
        from kuro_launcher.qt_chat_client import QtRuntimeChatClient
        from kuro_launcher.qt_web_host import create_candidate, register_candidate_scheme, ENTRY
        from web_candidate_fixtures import controller_fixture
        env = os.environ.copy(); env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',TEMP=str(output),TMP=str(output))
        service_log = (output/'service.log').open('w',encoding='utf-8')
        process = subprocess.Popen([str(TEST_PYTHON),'-B',str(HERE/'candidate_fixture_service.py'),'--output',str(output)],
            cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=service_log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        deadline = time.monotonic()+15
        while not (output/'ServiceReady.json').exists():
            if process.poll() is not None or time.monotonic()>deadline: raise RuntimeError('Disposable service unavailable; see service.log')
            time.sleep(.05)
        info = json.loads((output/'ServiceReady.json').read_text(encoding='utf-8'))
        if not info['synthetic'] or info['pid'] != process.pid or info['schedulerStarted']: raise RuntimeError('Fixture identity mismatch')
        allowed_ports = {info['httpPort'],info['wsPort']}
        if allowed_ports & {1188,18890,23456,23567,23568,23569}: raise RuntimeError('Fixture chose reserved production port')
        original_connect = socket.socket.connect
        def connect(sock,address):
            if not isinstance(address,tuple) or address[0]!='127.0.0.1' or address[1] not in allowed_ports:
                raise PermissionError('Native fixture permits only its own two ports')
            return original_connect(sock,address)
        socket.socket.connect = connect
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def rpc(method,*a,**kw):
            body = json.dumps({'method':method,'args':a,'kwargs':kw}).encode()
            req = urllib.request.Request(f"http://127.0.0.1:{info['httpPort']}/fixture/call",data=body,
                headers={'Content-Type':'application/json','Authorization':'Bearer '+info['fixtureToken']})
            with opener.open(req,timeout=5) as response: reply=json.load(response)
            if reply.get('ok') is not True: raise RuntimeError('Fixture owner rejected request')
            value=reply['value']
            return [SimpleNamespace(**row) for row in value] if method=='read_memory_records' else value
        controller = controller_fixture()
        for name in ('read_memory_records','add_memory','set_memory_status','delete_memory','compact_memory',
                'read_today','read_core_status','read_schedule_view','read_schedule_item','prepare_schedule',
                'mutate_schedule','read_schedule_notifications','schedule_notification_command'):
            setattr(controller,name,lambda *a,_name=name,**kw:rpc(_name,*a,**kw))
        # No mock-success device/lifecycle writes in the visible fixture.
        for name in ('start_profile','run_pet_command','set_pet_toggle','set_expression'):
            getattr(controller,name).return_value={'ok':False,'error':'synthetic_device_or_lifecycle_unavailable'}
        register_candidate_scheme(); app=QApplication([])
        class Owner(QMainWindow):
            synthetic_disposable_owner=True
            candidate_audit=staticmethod(audit)
            def closeEvent(self,event):
                self.work_web_candidate.shutdown_candidate()
                self.chat_client.disconnect()
                super().closeEvent(event)
        window=Owner(); window.controller=controller; window.chat_client=QtRuntimeChatClient(window)
        window.setWindowTitle('SYNTHETIC · '+args.checkpoint+f' · 原版 Qt Web candidate · {args.seconds}s bounded review')
        view=create_candidate(window,HERE/'.runtime/candidate-dist',enabled=True,fixture=True)
        window.setCentralWidget(view); window.resize(1280,720); window.show()
        QTimer.singleShot(0,lambda:window.resize(1280,720))
        window.chat_client.connect_to(f"ws://127.0.0.1:{info['wsPort']}/client-ws?client_role=qt-primary")
        profile,page,_,_,_,port=view._candidate_refs
        result.update(qt=qVersion(),offTheRecord=profile.isOffTheRecord(),servicePid=process.pid)
        manifest=HERE/'.runtime/candidate-dist/candidate-manifest.json'
        result['assetManifestSha256']=hashlib.sha256(manifest.read_bytes()).hexdigest()
        result['sourceSha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [Path(__file__),HERE/'candidate_fixture_service.py',ROOT/'kuro_launcher/qt_web_host.py',
             ROOT/'kuro_launcher/qt_web_adapter.py',ROOT/'kuro_launcher/qt_web_protocol.py',ROOT/'kuro_launcher/qt_chat_client.py',
             ROOT/'tests/web_candidate_fixtures.py']}
        def response(raw):
            reply=json.loads(raw)
            audit('channel_response',id=reply.get('id'),ok=reply.get('result',{}).get('ok'),error=reply.get('result',{}).get('error'))
        port.wire.response.connect(response)
        port.wire.event.connect(lambda raw:audit('channel_event',name=json.loads(raw).get('name')))
        started=time.monotonic(); probe_started=False
        def observed(raw):
            nonlocal probe_started
            if not raw: return
            data=json.loads(raw)
            if data.get('bridge') and data.get('shell') and window.chat_client.history_ready:
                if not probe_started:
                    probe_started=True; result['native']='BOOTSTRAP_OBSERVED'
                    page.runJavaScript("document.querySelector('[data-mode=chat]')?.click()")
                    QTimer.singleShot(800,lambda:view.grab().save(str(output/'native-chat.png')))
                    page.runJavaScript("""(() => {
                      window.__candidateProbe = {};
                      for (const key of ['sessionStorage','indexedDB','caches']) {
                        try { void window[key]; __candidateProbe[key]='EXPOSED'; }
                        catch(e) { __candidateProbe[key]=e.name; }
                      }
                      try { localStorage.setItem('secret','SYNTHETIC_SECRET_CANARY'); __candidateProbe.secret='EXPOSED'; }
                      catch(e) { __candidateProbe.secret=e.name; }
                      fetch('kuro-work://app/forbidden').then(()=>__candidateProbe.fetch='EXPOSED',()=>__candidateProbe.fetch='denied');
                      if (typeof Notification !== 'undefined') Notification.requestPermission().then(v=>__candidateProbe.notification=v);
                      __candidateProbe.popup = window.open('kuro-work://denied/popup') === null ? 'denied' : 'EXPOSED';
                      const link=document.createElement('a');
                      link.href=URL.createObjectURL(new Blob(['SYNTHETIC DOWNLOAD CANARY'],{type:'text/plain'}));
                      link.download='SYNTHETIC-must-not-download.txt';link.click();URL.revokeObjectURL(link.href);
                      __candidateProbe.download='attempted; native download denial signal required';
                      return true;
                    })()""")
                    # Navigation stays inside the custom scheme; no private file/network read.
                    QTimer.singleShot(1500,lambda:page.setUrl(QUrl('kuro-work://denied/forbidden')))
                result['dom']=data
                (output/'NativeResult.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            elif time.monotonic()-started>20 and not probe_started:
                result['native']='FAIL_BOOTSTRAP'; window.close()
        def poll():
            page.runJavaScript("JSON.stringify({bridge:!!window.kuroWorkPanel,shell:!!document.querySelector('.rail'),url:location.href,focus:document.activeElement?.tagName,probe:window.__candidateProbe||null})",observed)
        timer=QTimer(window);timer.timeout.connect(poll);timer.start(500)
        QTimer.singleShot(args.seconds*1000,window.close)
        app.exec()
        window.chat_client.disconnect()
        if window.chat_client._thread: window.chat_client._thread.join(4)
        result['chatThreadStopped']=not(window.chat_client._thread and window.chat_client._thread.is_alive())
        result['brokerClosed']=port.broker.closed
        checks_failed = (result.get('offTheRecord') is not True or result.get('dom',{}).get('url') != ENTRY
            or any(v == 'EXPOSED' for v in (result.get('dom',{}).get('probe') or {}).values())
            or any(a.get('guiThread') is False for a in result['actions']))
        result['nativeChecksFailed']=checks_failed
        exit_code = 0 if result['native']=='BOOTSTRAP_OBSERVED' and result['chatThreadStopped'] and not checks_failed else 1
    except Exception as exc:
        result.update(native='BLOCKED',errorType=type(exc).__name__,error=str(exc))
        (output/'native-error.log').write_text(traceback.format_exc(),encoding='utf-8')
        exit_code = 2
    finally:
        if window is not None:
            view=getattr(window,'work_web_candidate',None)
            if view is not None: view.shutdown_candidate()
            window.chat_client.disconnect()
        if process is not None:
            if process.poll() is None:
                try: process.stdin.write(b'close\n');process.stdin.flush();process.wait(timeout=15)
                except (OSError,subprocess.TimeoutExpired):
                    process.terminate();process.wait(timeout=5);result['serviceForcedStop']=True;exit_code=1
            result['serviceExit']=process.returncode
            if process.returncode != 0: exit_code=1
        if service_log: service_log.close()
        result['exit']=exit_code
        (output/'NativeResult.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(str(output/'NativeResult.json'))
    return exit_code


if __name__=='__main__': raise SystemExit(main())
