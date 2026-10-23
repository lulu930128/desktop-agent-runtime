"""First-wave config composition; only synthetic handoffs and ephemeral Hub IO."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import yaml
from g2_fixtures import mail_snapshot, mail_status, work_writer
from kuro_core.core_app import CoreApplication
from kuro_core.hub_integration import HUBS
from kuro_launcher.config import load_config
from kuro_launcher.core_runtime import CoreRuntime
from kuro_launcher.mail_poller_runtime import MailPollerRuntime
from kuro_launcher.qt_controller import QtLauncherController
from kuro_launcher.qt_web_adapter import QtOwnerAdapter
from test_g2_hub_transport import synthetic_hub
from test_g2_integration_boundaries import LifecycleTests
from test_kuro_core_api_host import TOKEN

ROOT = Path(__file__).resolve().parents[1]


def isolated_config(directory, *, enabled=True):
    # Read only the public Core section, never copy private launcher settings.
    text = (ROOT / 'kuro_launcher.settings.yaml').read_text(encoding='utf-8')
    core = yaml.safe_load('core:\n' + text.split('\ncore:\n', 1)[1].split('\nbridge:\n', 1)[0])['core']
    assert core['enabled'] and not core['integrations']['study']['enabled']
    assert all(core['integrations'][s]['enabled'] is True for s in (*HUBS, 'mail'))
    core.update(port=12345, db_path=str(directory / 'unused.db'))
    for source in (*HUBS, 'mail'):
        core['integrations'][source]['enabled'] = enabled
    core['integrations']['study']['snapshot_path'] = str(directory / 'unused-study.json')
    core['integrations']['mail'].update(status_path=str(directory / 'status.json'),
                                      work_path=str(directory / 'work.json'))
    path = directory / 'fixture.yaml'
    path.write_text(yaml.safe_dump({'paths': {'ROOT': str(directory), 'logs_dir': str(directory)},
                                   'core': core}), encoding='utf-8')
    return load_config(path)


class ManualReadinessTests(unittest.TestCase):
    def setUp(self):
        temporary = ROOT / '.tmp/g2-manual-ready-tests'
        temporary.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=temporary)
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)

    def application(self, cfg):
        schedule = LifecycleTests().schedule(self.directory / 'unused.db')
        with patch('kuro_core.core_app.ScheduleCapability', return_value=schedule):
            app = CoreApplication(self.directory / 'unused.db', port=0, token=TOKEN,
                instance_id='synthetic-first-wave', hubs=cfg.core_hubs,
                mail_enabled=cfg.core_mail_enabled, mail_status_path=cfg.core_mail_status_path,
                mail_work_path=cfg.core_mail_work_path)
        return app, schedule

    def test_three_sources_config_worker_today_qt_and_inactive_omi(self):
        cfg = isolated_config(self.directory)
        stamp = datetime.now(timezone.utc).isoformat()
        cfg.core_mail_status_path.write_text(json.dumps(mail_status(stamp)), encoding='utf-8')
        cfg.core_mail_work_path.write_text(json.dumps(work_writer.build_work_handoff(
            mail_snapshot(stamp), attempt_at=stamp)), encoding='utf-8')
        before = {p: p.read_bytes() for p in (cfg.core_mail_status_path, cfg.core_mail_work_path)}
        app, schedule = self.application(cfg)
        with synthetic_hub(service='japanese-study-hub') as jp, \
                synthetic_hub(service='english-study-hub') as en, \
                patch.dict(HUBS, {
                    'japanese_study': ('japanese-study-hub', jp[0], 'SYNTHETIC_NO_TOKEN'),
                    'english_study': ('english-study-hub', en[0], 'SYNTHETIC_NO_TOKEN')}), \
                patch('sqlite3.connect', side_effect=AssertionError('No DB')):
            try:
                app.start()
                deadline = time.monotonic() + 12
                while time.monotonic() < deadline:
                    if all(app.integrations.readonly_sources[s].snapshot for s in HUBS):
                        break
                    threading.Event().wait(.05)
                self.assertTrue(all(app.integrations.readonly_sources[s].snapshot for s in HUBS))
                runtime = CoreRuntime(SimpleNamespace(core_port=app.port), Mock())
                runtime.token = TOKEN
                controller = SimpleNamespace(_core_request=runtime.request)
                controller._assistant_settings_result = QtLauncherController._assistant_settings_result
                controller.read_today = lambda: QtLauncherController.read_today(controller)
                controller.read_assistant_settings = lambda: QtLauncherController.read_assistant_settings(controller)
                owner = SimpleNamespace(controller=controller)
                result = QtOwnerAdapter._owned_call(owner, 'getData', {}, {})
                self.assertTrue(result['ok'])
                self.assertEqual({row['source'] for row in result['snapshot']['today']['items']},
                                 {*HUBS, 'mail'})
                self.assertEqual({row['integrationId'] for row in result['canonical']['sourceStates']},
                                 {*HUBS, 'mail'})
                self.assertNotIn('sourceObservations', result['canonical'])
                settings = QtOwnerAdapter._owned_call(owner, 'getAssistantSettings', {}, {})
                self.assertTrue(settings['ok'])
                self.assertFalse(settings['runtime']['executionAvailable'])
                self.assertFalse(settings['runtime']['omi']['allowed'])
                self.assertLessEqual(len(json.dumps(runtime.request('/v1/observations'),
                    ensure_ascii=False).encode('utf-8')), 65536)
                self.assertEqual((len(jp[3]), len(en[3])), (4, 4))
                self.assertFalse(schedule.stop_event.is_set())
            finally:
                app.stop()
        self.assertFalse(app.integration_worker.is_alive())
        self.assertFalse(schedule.worker.is_alive())
        self.assertFalse(app.api.thread.is_alive())
        self.assertFalse((self.directory / 'unused.db').exists())
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_config_rollback_disables_all_source_io_and_mail_child(self):
        cfg = isolated_config(self.directory, enabled=False)
        app, schedule = self.application(cfg)
        with patch('kuro_core.hub_integration.HubClient.get', side_effect=AssertionError('Disabled Hub IO')) as get, \
                patch('kuro_launcher.mail_poller_runtime.subprocess.Popen') as spawn:
            try:
                app.start()
                for _ in range(4):
                    app.integrations.background_read(app.integration_stop)
                view = app.today.read({})
                self.assertTrue(view['complete'])
                self.assertEqual(view['sourceStates'], [])
                self.assertEqual(view['items'], [])
                self.assertFalse(MailPollerRuntime(cfg, Mock()).start())
                get.assert_not_called()
                spawn.assert_not_called()
            finally:
                app.stop()
        self.assertFalse(app.integration_worker.is_alive())
        self.assertFalse(schedule.worker.is_alive())


if __name__ == '__main__':
    unittest.main()
