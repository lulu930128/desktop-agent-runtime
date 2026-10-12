"""Real disposable sidecar IO. These tests do not claim native WebEngine proof."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
import websocket

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


class RelayTests(unittest.TestCase):
    def test_sidecar_uses_disposable_memory_core_and_reconnecting_ws(self):
        with tempfile.TemporaryDirectory(prefix='relay-test-',dir=HERE/'.runtime') as directory:
            output=Path(directory)
            with (output/'service.log').open('w',encoding='utf-8') as log:
                process=subprocess.Popen([sys.executable,'-B',str(HERE/'candidate_fixture_service.py'),'--output',str(output)],
                    cwd=ROOT,env={**os.environ,'PYTHONIOENCODING':'utf-8'},stdin=subprocess.PIPE,stdout=log,stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                try:
                    deadline=time.monotonic()+10
                    while not (output/'ServiceReady.json').exists():
                        if process.poll() is not None or time.monotonic()>deadline:
                            self.fail((output/'service.log').read_text(encoding='utf-8'))
                        time.sleep(.02)
                    info=json.loads((output/'ServiceReady.json').read_text())
                    self.assertFalse(info['schedulerStarted'])
                    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    def rpc(method,*a,**kw):
                        request=urllib.request.Request(f"http://127.0.0.1:{info['httpPort']}/fixture/call",
                            data=json.dumps(dict(method=method,args=a,kwargs=kw)).encode(),
                            headers={'Content-Type':'application/json','Authorization':'Bearer '+info['fixtureToken']})
                        with opener.open(request,timeout=3) as response: return json.load(response)['value']
                    self.assertEqual(rpc('read_memory_records',strict=True),[])
                    self.assertTrue(rpc('add_memory','SYNTHETIC relay preference',expected_conf_uid='actor'))
                    memory=rpc('read_memory_records',strict=True)[0]
                    self.assertTrue(rpc('delete_memory',memory['entry_id'],expected_conf_uid='actor',expected_digest=memory['content_digest']))
                    self.assertEqual(rpc('read_memory_records',strict=True),[])
                    self.assertTrue((output/'memories/character_memory.sqlite3').is_file())
                    before=(output/'synthetic-core.sqlite3').read_bytes()
                    self.assertEqual(rpc('read_today')['contract'],'kuro.core.today.v1')
                    item={'title':'SYNTHETIC relay','kind':'deadline','allDay':True,'due':'2026-10-11','timezone':'UTC'}
                    self.assertTrue(rpc('prepare_schedule',item)['ok'])
                    self.assertEqual((output/'synthetic-core.sqlite3').read_bytes(),before)
                    payload={'action':'create','item':item,'idempotencyKey':'relay','confirmed':True}
                    first=rpc('mutate_schedule',payload)
                    self.assertTrue(first['ok']);self.assertEqual(first,rpc('mutate_schedule',payload))
                    contexts=[]
                    for attempt in range(2):
                        ws=websocket.create_connection(f"ws://127.0.0.1:{info['wsPort']}/client-ws?client_role=qt-primary",timeout=3,http_proxy_host=None)
                        try:
                            hello=json.loads(ws.recv());contexts.append(hello['context_id'])
                            identity={k:hello[k] for k in ('client_uid','conf_uid','context_id')}
                            ws.send(json.dumps(dict(type='fetch-history-list',request_id='list',**identity)))
                            listing=json.loads(ws.recv());self.assertEqual(listing['type'],'history-list')
                            ws.send(json.dumps(dict(type='text-input',text='SYNTHETIC probe',history_uid=listing['current_history_uid'],**identity)))
                            events=[json.loads(ws.recv()) for _ in range(5)]
                            self.assertEqual(events[1]['text'],'SYNTHETIC reply')
                            self.assertEqual(events[-1]['conversation_scope']['history_uid'],'old')
                        finally: ws.close()
                    self.assertNotEqual(*contexts)
                finally:
                    if process.poll() is None:
                        process.stdin.write(b'close\n');process.stdin.flush()
                        try: process.wait(timeout=12)
                        except subprocess.TimeoutExpired: process.terminate();process.wait(timeout=5)
                    self.assertEqual(process.returncode,0,(output/'service.log').read_text(encoding='utf-8'))
                service=json.loads((output/'ServiceResult.json').read_text())
                self.assertFalse(service['schedulerStarted']);self.assertEqual(service['connections'],2)


if __name__=='__main__': unittest.main()
