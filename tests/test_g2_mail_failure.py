"""G2 Mail failures use only synthetic existing-owner handoffs."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from g2_fixtures import mail_snapshot, mail_status, work_writer
from kuro_core.mail_adapter import mail_status_observation
from kuro_core.integrations import IntegrationRegistry
from kuro_core.today_capability import TodayCapability

NOW = datetime(2026, 10, 9, 0, 5, tzinfo=timezone.utc)


class MailFailureTests(unittest.TestCase):
    def test_invalid_schema_cannot_promote_auth_status(self):
        status = mail_status(ok=False)
        status.update(schemaVersion=2, errorType='auth_required')
        observation = mail_status_observation(status, received_at=NOW)
        self.assertEqual(observation.availability.value, 'partial')
        self.assertEqual(observation.connection.value, 'unknown')

    def test_existing_handoff_to_today_preserves_auth_and_stale_without_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            status_path, work_path = Path(tmp)/'status.json', Path(tmp)/'work.json'
            status = mail_status(ok=False)
            status['errorType'] = 'auth_required'
            status_path.write_text(json.dumps(status), encoding='utf-8')
            work = work_writer.build_work_handoff(mail_snapshot(), attempt_at='2026-10-09T00:00:00Z')
            work_path.write_text(json.dumps(work), encoding='utf-8')
            before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (status_path, work_path)}
            sources = IntegrationRegistry(mail_enabled=True, mail_status_path=status_path)
            today = TodayCapability(sources, mail_work_path=work_path)
            with patch('sqlite3.connect', side_effect=AssertionError('No DB')), \
                    patch('socket.socket', side_effect=AssertionError('No mailbox/network')):
                for time, freshness in ((NOW, 'current'), (NOW+timedelta(hours=1), 'stale')):
                    view = today.view(as_of=time)
                    self.assertEqual(len(view.items), 1)
                    self.assertEqual(len(view.source_states), 1)
                    state = view.source_states[0]
                    self.assertEqual(state.integration_id, 'mail')
                    self.assertEqual(state.availability.value, 'auth_required')
                    self.assertEqual(state.freshness.value, freshness)
                    self.assertFalse(view.complete)
            self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before})

    def test_missing_work_does_not_hide_auth_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'status.json'
            status = mail_status(ok=False); status['errorType'] = 'auth_required'
            path.write_text(json.dumps(status), encoding='utf-8')
            view = TodayCapability(IntegrationRegistry(mail_enabled=True, mail_status_path=path),
                mail_work_path=Path(tmp)/'missing.json').view(as_of=NOW)
            self.assertEqual(view.items, ())
            self.assertEqual(view.source_states[0].availability.value, 'auth_required')
            self.assertFalse(view.complete)


if __name__ == '__main__': unittest.main()
