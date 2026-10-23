"""Disposable Core HTTP + actual Qt Port queue; never production startup/data."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication, QObject
from kuro_core.assistant_settings import AssistantSettings, DEFAULTS
from kuro_core.api_server import ApiConflict
from kuro_core.core_app import CoreApplication
from kuro_launcher.core_runtime import CoreRuntime
from kuro_launcher.qt_chat_client import QtRuntimeChatClient
from kuro_launcher.qt_controller import QtLauncherController
from kuro_launcher.qt_web_protocol import CONTRACT, requires_confirmation
from test_qt_web_existing_window import actual_port

ROOT = Path(__file__).resolve().parents[1]


class SettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / '.tmp')
        self.addCleanup(self.temp.cleanup)
        self.store = AssistantSettings(Path(self.temp.name) / 'synthetic.sqlite3')

    def command(self, **settings):
        return dict(settings={**copy.deepcopy(DEFAULTS), **settings},
                    expectedRevision=self.store.read({})['revision'], confirmed=True)

    def test_default_read_is_nonwriting_and_both_consumers_closed(self):
        read = self.store.read({})
        self.assertNotIn('ok', read)  # Qt owns the presentation envelope.
        self.assertEqual(read['settings'], DEFAULTS)
        self.assertFalse(read['persisted'])
        self.assertFalse(self.store.path.exists())
        self.assertFalse(read['runtime']['executionAvailable'])

    def test_confirmed_atomic_readback_restart_and_stale_revision(self):
        command = self.command(proactiveVoice=True, omi=dict(enabled=True, intervalMinutes=5, dailyQueryBudget=2))
        written = self.store.update(command)
        # Preserve the same canonical database stem across a recreated owner.
        other = AssistantSettings(Path(self.temp.name) / 'synthetic.sqlite3')
        self.assertEqual(other.read({}), written)
        self.assertEqual(other.admission('omi-observation')['reason'], 'execution_not_available_g1')
        self.assertFalse(other.admission('proactive-voice')['allowed'])
        with self.assertRaises(ApiConflict): self.store.update(command)

    def test_unconfirmed_and_invalid_inputs_never_write(self):
        for field, value in [('confirmed', False), ('confirmed', 1), ('expectedRevision', 'bad')]:
            command = self.command(); command[field] = value
            with self.assertRaises((ValueError, PermissionError)): self.store.update(command)
        for value in [None, {'proactiveVoice': 1, 'omi': DEFAULTS['omi']},
                      {**DEFAULTS, 'extra': True},
                      {**DEFAULTS, 'omi': {'enabled': True, 'intervalMinutes': True, 'dailyQueryBudget': 1}},
                      {**DEFAULTS, 'omi': {'enabled': True, 'intervalMinutes': 4, 'dailyQueryBudget': 25}}]:
            command = self.command(); command['settings'] = value
            with self.assertRaises(ValueError): self.store.update(command)
        self.assertFalse(self.store.path.exists())

    def test_corrupt_record_never_overwritten_and_admission_closed(self):
        command = self.command()
        for data in [b'', b'{', b'x' * 4097, b'{"schema":2}']:
            self.store.path.write_bytes(data)
            with self.assertRaises(ValueError): self.store.update(command)
            self.assertEqual(self.store.path.read_bytes(), data)
            self.assertEqual(self.store.admission('omi-observation')['reason'], 'settings_unavailable')

    def test_atomic_replace_failure_preserves_old_record_and_cleans_temp(self):
        self.store.update(self.command())
        before = self.store.path.read_bytes()
        with patch('kuro_core.assistant_settings.os.replace', side_effect=OSError('synthetic IO failure')):
            with self.assertRaises(OSError): self.store.update(self.command(proactiveVoice=True))
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(list(self.store.path.parent.glob('.assistant-settings-*')), [])

    def test_zero_budget_and_unknown_actions_stay_closed(self):
        self.store.update(self.command(omi=dict(enabled=True, intervalMinutes=30, dailyQueryBudget=0)))
        self.assertEqual(self.store.admission('omi-observation')['reason'], 'query_budget_zero')
        self.assertEqual(self.store.admission('provider-refresh')['reason'], 'unknown_action')


class SettingsPortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=ROOT / '.tmp')
        self.addCleanup(temp.cleanup)
        token = 'synthetic-g1-settings-token-000000'
        self.core = CoreApplication(Path(temp.name) / 'synthetic.sqlite3', port=0,
                                    token=token, instance_id='synthetic-g1')
        self.addCleanup(self.core.stop)
        self.core.api.start()  # Deliberately do not start scheduler/materialization.
        controller = QtLauncherController.__new__(QtLauncherController)
        controller.core_runtime = CoreRuntime(SimpleNamespace(core_enabled=True, core_port=self.core.port), lambda _: None)
        controller.core_runtime.token = token
        self.owner = QObject()
        self.owner.controller = controller
        self.owner.chat_client = QtRuntimeChatClient(self.owner)  # No WS connection.
        self.port = actual_port(self.owner, [])
        self.addCleanup(self.port.shutdown)
        self.confirm = Mock(return_value=True)
        self.port.broker.confirm = self.confirm
        self.replies = []
        self.port.wire.response.connect(lambda raw: self.replies.append(json.loads(raw)))
        self.sequence = 0

    def call(self, method, payload=None):
        self.sequence += 1
        before = len(self.replies)
        self.port.wire.submit(json.dumps(dict(contract=CONTRACT, id=f'g1-{self.sequence}', method=method,
            payload=payload or {}, expected=self.port.adapter.identity())))
        end = time.monotonic() + 5
        while len(self.replies) == before and time.monotonic() < end:
            self.app.processEvents(); time.sleep(.005)
        self.assertEqual(len(self.replies), before + 1)
        return self.replies[-1]['result']

    def test_actual_port_http_and_frontend_contract_read_write_readback(self):
        first = self.call('getAssistantSettings')
        self.assertTrue(first['ok'])
        self.confirm.assert_not_called()
        settings = dict(proactiveVoice=True, omi=dict(enabled=True, intervalMinutes=17, dailyQueryBudget=3))
        written = self.call('updateAssistantSettings', dict(settings=settings, expectedRevision=first['revision']))
        self.assertTrue(written['ok'])
        self.assertTrue(written['persisted'])
        self.confirm.assert_called_once()
        self.assertEqual(self.confirm.call_args.args[0], 'updateAssistantSettings')
        readback = self.call('getAssistantSettings')
        self.assertEqual(readback, written)
        status = self.owner.controller.read_core_status()
        self.assertEqual(status['capabilities']['assistantSettings'], written['runtime'])
        result = subprocess.run(['node', 'tests/g1_frontend_contract.cjs'], cwd=ROOT,
            input=json.dumps([first, written, readback]), capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cancel_never_reaches_controller_or_creates_sidecar(self):
        first = self.call('getAssistantSettings'); self.confirm.return_value = False
        self.assertTrue(requires_confirmation('updateAssistantSettings', {}))
        with patch.object(self.owner.controller, 'update_assistant_settings') as write:
            result = self.call('updateAssistantSettings', dict(settings=DEFAULTS, expectedRevision=first['revision']))
        self.assertTrue(result['cancelled']); write.assert_not_called()
        self.assertFalse(self.core.assistant_settings.path.exists())

    def test_renderer_confirmed_flag_rejected_before_native_or_http(self):
        first = self.call('getAssistantSettings')
        result = self.call('updateAssistantSettings', dict(settings=DEFAULTS,
            expectedRevision=first['revision'], confirmed=True))
        self.assertFalse(result['ok']); self.confirm.assert_not_called()
        self.assertFalse(self.core.assistant_settings.path.exists())

    def test_context_change_during_confirmation_never_writes(self):
        first = self.call('getAssistantSettings')
        def change(*_): self.owner.chat_client.conf_uid = 'changed'; return True
        self.confirm.side_effect = change
        result = self.call('updateAssistantSettings', dict(settings=DEFAULTS, expectedRevision=first['revision']))
        self.assertEqual(result['error'], 'confirmation_context_changed')
        self.assertFalse(self.core.assistant_settings.path.exists())


if __name__ == '__main__': unittest.main()
