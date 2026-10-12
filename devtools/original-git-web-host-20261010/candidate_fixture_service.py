"""SYNTHETIC native-review sidecar. Existing Core/Memory owners, no scheduler.

Launched only by candidate_native.py using the existing test interpreter.
No production configuration, provider, history or Pet service is constructed.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict, is_dataclass
import json
import os
from pathlib import Path
import socket
import sys
import threading
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests'), str(ROOT/'Open-LLM-VTuber/src')]


def guard_network():
    original = socket.socket.connect
    def connect(sock, address):
        if not isinstance(address, tuple) or address[0] != '127.0.0.1' or address[1] in {1188, 18890, 23456, 23567, 23568, 23569}:
            raise PermissionError('Fixture permits only disposable IPv4 loopback')
        return original(sock, address)
    socket.socket.connect = connect



def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); output = args.output.resolve()
    if not output.is_relative_to(HERE/'.runtime') or not output.is_dir(): parser.error('Existing task-local output required')
    guard_network()
    # The directory was exclusively created by the native runner, before imports.
    memory_root = output/'memories'; memory_root.mkdir(exist_ok=False)
    os.environ['KURO_MEMORY_ROOT'] = str(memory_root)
    from types import SimpleNamespace
    from unittest.mock import Mock
    from kuro_core.api_server import CoreApiServer
    from kuro_core.schedule_api import ScheduleCapability
    from kuro_launcher.qt_controller import QtLauncherController
    from kuro_launcher.core_runtime import CoreRuntime
    from web_candidate_fixtures import core_today, SyntheticConversation
    token = 'synthetic-native-candidate-' + uuid.uuid4().hex
    capability = ScheduleCapability(output/'synthetic-core.sqlite3', default_timezone='Asia/Taipei')
    api = CoreApiServer(port=0, token=token)
    capability.register_routes(api)
    api.register('GET', '/status', lambda _: {'contract':'kuro.core.api.v1','capabilities':{'schedule':capability.status()}})
    api.register('GET', '/v1/today', lambda _: core_today())
    c = QtLauncherController.__new__(QtLauncherController)
    c.cfg = SimpleNamespace(open_llm_dir=output)
    c.selected_character = lambda: SimpleNamespace(conf_uid='actor', conf_name='SYNTHETIC actor')
    c.log = lambda _: None
    c._maybe_refresh_memory_prompt = Mock()  # No external runtime prompt refresh.
    c.core_runtime = CoreRuntime(SimpleNamespace(core_enabled=True, core_port=api.port), lambda _: None)
    c.core_runtime.token = token
    names = {'read_memory_records','add_memory','set_memory_status','delete_memory','compact_memory',
        'read_today','read_core_status','read_schedule_view','read_schedule_item','prepare_schedule',
        'mutate_schedule','read_schedule_notifications','schedule_notification_command'}
    calls = []; lock = threading.RLock()
    def call(p):
        if set(p) != {'method','args','kwargs'} or p['method'] not in names: raise ValueError('Fixture method denied')
        with lock:
            result = getattr(c, p['method'])(*p['args'], **p['kwargs'])
            if p['method'] == 'read_memory_records': result = [asdict(r) if is_dataclass(r) else vars(r) for r in result]
            calls.append({'method':p['method']})
            return {'value':result}
    api.register('POST', '/fixture/call', call)
    ws = SyntheticConversation()
    try:
        api.start(); ws.start()
        (output/'ServiceReady.json').write_text(json.dumps({'pid':os.getpid(),'httpPort':api.port,'wsPort':ws.port,
            'fixtureToken':token,'synthetic':True,'schedulerStarted':capability.worker is not None}),encoding='utf-8')
        stop = threading.Event()
        threading.Thread(target=lambda: (sys.stdin.readline(), stop.set()), daemon=True).start()
        stop.wait(1200)
    finally:
        if hasattr(ws, 'thread'): ws.close()
        api.stop(); capability.stop()
        (output/'ServiceResult.json').write_text(json.dumps({'synthetic':True,'calls':calls,
            'wsRequests':ws.received,'connections':ws.connections,'schedulerStarted':False},indent=2),encoding='utf-8')
    return 0


if __name__ == '__main__': raise SystemExit(main())
