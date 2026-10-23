"""Independent transport negatives against disposable loopback HTTP servers only."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading
import time
import unittest
from unittest.mock import patch

from kuro_core.hub_integration import HUBS, PATHS, MAX_BYTES, HubClient, HubReadError, project_hub


@contextmanager
def synthetic_hub(mode='ok', service='japanese-study-hub'):
    entered=threading.Event(); release=threading.Event(); calls=[]
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args): pass
        def do_GET(self):
            calls.append(self.path)
            payload={'ok':True,'service':service}
            if self.path==PATHS[1]:
                payload={'ok':True,'summary':{'items':{'total':1,'by_kind':{}} if service.startswith('japanese') else 1}}
            elif self.path in PATHS[2:]:
                payload={'ok':True,'count':1,'items':[{'item_id':'synthetic','title':'Synthetic',
                    'kind':'word','meaning_tc':'Synthetic','cefr_level':'B1','jlpt_level':'N3'}]}
                if service.startswith('japanese'): payload['as_of']=datetime.now(timezone.utc).isoformat()
            raw=json.dumps(payload).encode()
            if mode=='oversize': raw=b' '* (MAX_BYTES+1)
            if mode=='deadline': release.wait(.8)
            self.send_response(302 if mode=='redirect' else 200)
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Connection','close')
            self.end_headers(); entered.set()
            try:
                if mode=='blocked': release.wait(4)
                if mode=='deadline':
                    for value in raw:
                        if release.wait(.15): break
                        self.wfile.write(bytes([value])); self.wfile.flush()
                else: self.wfile.write(raw); self.wfile.flush()
            except (OSError,ValueError): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=False
    worker=threading.Thread(target=server.serve_forever)
    worker.start()
    try: yield server.server_port,entered,release,calls
    finally:
        release.set(); server.shutdown(); server.server_close(); worker.join(2)
        assert not worker.is_alive()


class HubTransportTests(unittest.TestCase):
    def client_call(self,port,client,stop):
        with patch.dict(HUBS,japanese_study=('japanese-study-hub',port,'SYNTHETIC_UNSET_TOKEN')):
            return client.get('japanese_study',PATHS[0],stop)

    def test_total_deadline_includes_headers_and_body(self):
        with synthetic_hub('deadline') as (port,entered,release,calls):
            client=HubClient(); started=time.monotonic()
            try:
                with self.assertRaises(HubReadError): self.client_call(port,client,threading.Event())
                self.assertLess(time.monotonic()-started,1.9)
                self.assertEqual(len(calls),1)
            finally: client.close()

    def test_close_cancels_detached_response_socket_and_joins(self):
        with synthetic_hub('blocked') as (port,entered,release,calls):
            client=HubClient(); errors=[]
            def read():
                try: self.client_call(port,client,threading.Event())
                except HubReadError as exc: errors.append(str(exc))
            worker=threading.Thread(target=read); worker.start()
            try:
                self.assertTrue(entered.wait(2))
                # Ensure HTTPConnection handed its socket to the Connection: close response.
                time.sleep(.05)
                client.close(); worker.join(.5)
                self.assertFalse(worker.is_alive())
                self.assertEqual(len(errors),1)
            finally:
                client.close(); release.set(); worker.join(2)
            self.assertEqual(len(calls),1)

    def test_payload_cap_and_redirect_do_not_retry(self):
        for mode in ('oversize','redirect'):
            with self.subTest(mode=mode), synthetic_hub(mode) as (port,entered,release,calls):
                client=HubClient()
                try:
                    with self.assertRaises(HubReadError): self.client_call(port,client,threading.Event())
                    self.assertEqual(len(calls),1)
                finally: client.close()

    def test_stop_before_get_performs_zero_socket_io(self):
        stop=threading.Event(); stop.set(); client=HubClient()
        with patch('socket.create_connection',side_effect=AssertionError('No socket IO')):
            with self.assertRaises(HubReadError): client.get('japanese_study',PATHS[0],stop)
        client.close()

    def test_stale_source_with_missing_item_time_preserves_unknown(self):
        now=datetime.now(timezone.utc)
        payload=[{'ok':True,'summary':{'items':{'total':1}}},
            {'ok':True,'as_of':(now-timedelta(hours=1)).isoformat(),'count':0,'items':[]},
            {'ok':True,'count':1,'items':[{'item_id':'one','title':'Synthetic'}]}]
        result=project_hub('japanese_study',payload,now,now,60)
        self.assertEqual(result.observation.declared_freshness.value,'stale')
        self.assertEqual(result.evidence[0].freshness.value,'unknown')
        self.assertEqual(result.evidence[0].metadata['sourceObservedAt'],None)


if __name__=='__main__': unittest.main()
