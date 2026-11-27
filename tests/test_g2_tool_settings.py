"""Synthetic policy files and Qt broker only; never modify the live policy."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from open_llm_vtuber.mcpp.tool_policy_manager import ToolPolicy
from kuro_launcher.tool_policy_settings import ToolPolicySettings, CATALOG, validate_change
from kuro_launcher.qt_web_protocol import RequestBroker, CONTRACT, requires_confirmation
from kuro_launcher.qt_web_adapter import QtOwnerAdapter
from web_candidate_fixtures import ChatFixture

ROOT = Path(__file__).resolve().parents[1]


class ToolSettingsTests(unittest.TestCase):
    def setUp(self):
        directory = ROOT / '.tmp/g2-tool-tests'
        directory.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=directory)
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'tool_policy.json'
        self.original = (ROOT / 'Open-LLM-VTuber/tool_policy.json').read_bytes()
        self.path.write_bytes(self.original)
        self.store = ToolPolicySettings(self.path)
        self.name = 'kuro-web::search_web'

    def payload(self, enabled=False, name=None):
        return {'name': name or self.name, 'enabled': enabled, 'expectedDigest': self.store.read()['digest']}

    def test_all_registered_disable_restore_preserves_modes_constraints_and_reload_contract(self):
        original = json.loads(self.original)
        self.assertGreaterEqual(len(CATALOG), 24)
        self.assertEqual(set(CATALOG), set(original['tools']))
        with patch.dict(os.environ, KURO_TOOL_POLICY_PATH=str(self.path)):
            prior_runtime = ToolPolicy.load_default()
            for name in CATALOG:
                disabled = self.store.update(self.payload(False, name), confirmed=True)
                self.assertFalse(ToolPolicy.load_default().check(name, {}).allowed)
                self.assertEqual(ToolPolicy.load_default().check(name, {}).reason_code, 'tool_disabled')
                restored = self.store.update(self.payload(True, name), confirmed=True)
                decision = ToolPolicy.load_default().check(name, {})
                self.assertEqual(decision.allowed, original['tools'][name]['mode'] == 'read_only')
                if original['tools'][name]['mode'] == 'confirm':
                    self.assertEqual(decision.reason_code, 'confirmation_required')
                self.assertEqual(restored['runtime_adoption'], 'UNVERIFIED')
                self.assertTrue(restored['restart_required'])
                self.assertNotEqual(restored['digest'], disabled['digest'])
            self.store.update(self.payload(False), confirmed=True)
            self.assertTrue(prior_runtime.check(self.name, {}).allowed)  # no fake hot adoption
            self.assertFalse(ToolPolicy.load_default().check(self.name, {}).allowed)
        current = json.loads(self.path.read_bytes())
        for row in current['tools'].values(): row.pop('enabled', None)
        self.assertEqual(current, original)

    def test_false_and_invalid_enabled_fail_closed_including_legacy_alias(self):
        for value in (0, 1, 'true', None, [], {}):
            policy = json.loads(self.original)
            policy['tools'][self.name]['enabled'] = value
            self.assertFalse(ToolPolicy(policy).check(self.name, {}).allowed)
        policy = json.loads(self.original)
        policy['tools']['search_web'] = {'mode': 'read_only', 'enabled': False}
        self.assertFalse(ToolPolicy(policy).check(self.name, {}).allowed)
        self.assertFalse(ToolPolicy(policy).check('unknown::tool', {}).allowed)

    def test_original_argument_guards_survive_disable_and_restore(self):
        for name, arguments in (
            ('kuro-web::fetch_content', {'url':'http://127.0.0.1/private'}),
            ('kuro-mail::mail.list_unread', {'include_spam_trash':True})):
            self.store.update(self.payload(False,name), confirmed=True)
            self.store.update(self.payload(True,name), confirmed=True)
            self.assertFalse(ToolPolicy(json.loads(self.path.read_bytes())).check(name, arguments).allowed)
        name = 'omi-search::omi_ask'
        observed = {'tools': [{'name': name, 'service': 'omi-search', 'allowed': True}]}
        with self.assertRaisesRegex(ValueError, 'unknown_tool'):
            self.store.update(self.payload(False,name), confirmed=True)
        self.store.update(self.payload(False,name), confirmed=True, inventory=observed)
        self.assertFalse(ToolPolicy(json.loads(self.path.read_bytes())).check(name, {}).allowed)
        self.store.update(self.payload(True,name), confirmed=True, inventory=observed)
        self.assertTrue(ToolPolicy(json.loads(self.path.read_bytes())).check(name, {'refresh_if_missing':True}).allowed)

    def test_cas_acl_atomic_failure_and_unconfirmed_preserve_original(self):
        change = self.payload()
        with self.assertRaises(PermissionError): self.store.update(change)
        self.assertEqual(self.path.read_bytes(), self.original)
        with patch('kuro_launcher.tool_policy_settings.os.replace', side_effect=PermissionError('synthetic ACL deny')):
            with self.assertRaises(PermissionError): self.store.update(change, confirmed=True)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ['tool_policy.json'])
        self.store.update(change, confirmed=True)
        saved = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError,'stale_digest'):
            self.store.update({**change,'enabled':True}, confirmed=True)
        self.assertEqual(self.path.read_bytes(), saved)

    def test_unknown_elevation_corrupt_and_lock_conflict_rejected(self):
        for extra in ({'mode':'read_only'}, {'enabled':1}, {'name':'other::tool'}, {'confirmed':True}):
            with self.assertRaises(ValueError): validate_change({**self.payload(), **extra})
        change = self.payload()
        lock = self.path.with_name(self.path.name+'.settings.lock')
        lock.write_bytes(b'synthetic-other-owner')
        with self.assertRaises(FileExistsError): self.store.update(change, confirmed=True)
        self.assertEqual(lock.read_bytes(), b'synthetic-other-owner')
        lock.unlink()
        for raw in (b'{bad',b'{"tools":{},"tools":{}}'):
            self.path.write_bytes(raw)
            with self.assertRaises(ValueError): self.store.read()
            with self.assertRaises(ValueError): self.store.update(change, confirmed=True)
            self.assertEqual(self.path.read_bytes(), raw)

    def test_real_qt_broker_confirmation_cancel_persist_and_get_readback(self):
        controller = Mock()
        controller.read_tool_policy_summary.side_effect = lambda uid: self.store.read()
        controller.update_tool_policy.side_effect = lambda p,uid:self.store.update(p, confirmed=True)
        adapter = QtOwnerAdapter(controller, ChatFixture(), lambda work,done:done(work()), window_action=Mock())
        responses=[]; confirm=Mock(return_value=False)
        broker=RequestBroker(adapter,confirm,responses.append)
        sequence=0
        def send(method,payload):
            nonlocal sequence
            sequence+=1
            broker.submit(json.dumps({'contract':CONTRACT,'id':f't{sequence}', 'expected':adapter.identity(),
                                      'method':method,'payload':payload}))
            return responses[-1]['result']
        before=send('getTools',{})
        self.assertTrue(before['ok']); self.assertEqual(len(before['tools']),len(CATALOG))
        payload={'name':self.name,'enabled':False,'expectedDigest':before['digest']}
        self.assertTrue(requires_confirmation('updateToolPolicy',payload))
        self.assertTrue(send('updateToolPolicy',payload)['cancelled'])
        self.assertEqual(self.path.read_bytes(),self.original)
        controller.update_tool_policy.assert_not_called()
        confirm.return_value=True
        written=send('updateToolPolicy',payload)
        self.assertTrue(written['persisted'])
        read=send('getTools',{})
        self.assertEqual(written['digest'],read['digest'])
        self.assertFalse(next(r for r in read['tools'] if r['name']==self.name)['enabled'])
        self.assertEqual(confirm.call_count,2)


if __name__ == '__main__': unittest.main()
