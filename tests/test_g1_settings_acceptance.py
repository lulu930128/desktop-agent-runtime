"""Supplementary G1 settings acceptance; not G2 integration implementation."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from kuro_core.assistant_settings import DEFAULTS
from kuro_core.core_app import CoreApplication
from kuro_launcher.core_runtime import CoreRuntime
from kuro_launcher.qt_controller import QtLauncherController
from kuro_launcher.qt_web_adapter import QtOwnerAdapter
from web_candidate_fixtures import ChatFixture

ROOT = Path(__file__).resolve().parents[1]
TOKEN = 'synthetic-g1-acceptance-token-0000'


class G1SettingsAcceptance(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=ROOT/'.tmp')
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name)/'synthetic.sqlite3'
        self.start_owner()

    def start_owner(self):
        self.core = CoreApplication(self.path, port=0, token=TOKEN, instance_id='synthetic-g1-acceptance')
        self.addCleanup(self.core.stop)
        self.core.api.start()  # No schedule worker, providers, Voice or WS.
        self.controller = QtLauncherController.__new__(QtLauncherController)
        self.controller.core_runtime = CoreRuntime(SimpleNamespace(core_enabled=True,core_port=self.core.port),lambda _:None)
        self.controller.core_runtime.token = TOKEN

    def test_owner_reconstruction_reads_same_persisted_policy_without_execution(self):
        initial = self.controller.read_assistant_settings()
        desired = dict(proactiveVoice=True,omi=dict(enabled=True,intervalMinutes=30,dailyQueryBudget=2))
        saved = self.controller.update_assistant_settings(desired,initial['revision'])
        self.core.stop()
        self.start_owner()
        self.assertEqual(self.controller.read_assistant_settings(),saved)
        status = self.controller.read_core_status()['capabilities']['assistantSettings']
        self.assertFalse(status['executionAvailable'])
        self.assertFalse(status['omi']['allowed'])
        self.assertFalse(status['proactiveVoice']['allowed'])
        self.assertIsNone(status['queriesUsedToday'])

    def test_unauthenticated_browser_origin_and_unconfirmed_writes_are_rejected(self):
        initial = self.controller.read_assistant_settings()
        command = dict(settings=DEFAULTS,expectedRevision=initial['revision'],confirmed=True)
        url = f'http://127.0.0.1:{self.core.port}/v1/assistant-settings'
        for headers,payload,want in [({},command,401),
                ({'Authorization':f'Bearer {TOKEN}','Origin':'http://synthetic.invalid'},command,401),
                ({'Authorization':f'Bearer {TOKEN}'},{**command,'confirmed':False},403)]:
            request=Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json',**headers})
            with self.assertRaises(HTTPError) as error: urlopen(request,timeout=3)
            self.assertEqual(error.exception.code,want)
            error.exception.close()
        self.assertFalse(self.core.assistant_settings.path.exists())

    def test_concurrent_same_revision_has_one_commit_and_one_conflict(self):
        revision=self.controller.read_assistant_settings()['revision']
        def write(enabled):
            desired=copy.deepcopy(DEFAULTS); desired['proactiveVoice']=enabled
            try: return self.controller.update_assistant_settings(desired,revision)
            except RuntimeError as exc: return str(exc)
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(write,[True,False]))
        committed=[r for r in results if isinstance(r,dict)]
        rejected=[r for r in results if isinstance(r,str)]
        self.assertEqual(len(committed),1); self.assertEqual(len(rejected),1)
        self.assertIn('409',rejected[0])
        self.assertEqual(self.controller.read_assistant_settings(),committed[0])
        self.assertEqual(json.loads(self.core.assistant_settings.path.read_text())['generation'],1)

    def test_corrupt_json_refuses_read_write_but_status_reports_closed_consumer(self):
        revision=self.controller.read_assistant_settings()['revision']
        self.core.assistant_settings.path.write_bytes(b'{synthetic-corrupt')
        with self.assertRaisesRegex(RuntimeError,'400'): self.controller.read_assistant_settings()
        with self.assertRaisesRegex(RuntimeError,'400'): self.controller.update_assistant_settings(DEFAULTS,revision)
        self.assertEqual(self.core.assistant_settings.path.read_bytes(),b'{synthetic-corrupt')
        status=self.controller.read_core_status()['capabilities']['assistantSettings']
        self.assertEqual(status['omi'],dict(allowed=False,reason='settings_unavailable'))

    def test_adapter_owns_ok_even_when_core_handler_returns_no_http_envelope(self):
        controller=Mock()
        controller.read_assistant_settings.side_effect=lambda:self.core.assistant_settings.read({})
        controller.update_assistant_settings.side_effect=lambda settings,revision:self.core.assistant_settings.update(
            dict(settings=settings,expectedRevision=revision,confirmed=True))
        adapter=QtOwnerAdapter(controller,ChatFixture(),lambda work,done:done(work()),window_action=Mock())
        read=adapter._owned_call('getAssistantSettings',{}, {})
        self.assertTrue(read['ok'])
        written=adapter._owned_call('updateAssistantSettings',dict(settings=DEFAULTS,expectedRevision=read['revision']),{})
        self.assertTrue(written['ok']); self.assertTrue(written['persisted'])
        self.assertNotIn('ok',self.core.assistant_settings.read({}))


if __name__=='__main__': unittest.main()
