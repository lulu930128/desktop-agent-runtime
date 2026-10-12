import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from g2_fixtures import ROOT, load_producer, mail_snapshot, message, work_writer, status_writer


class MailWorkWriterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.private = Path(self.tmp.name) / "private"
        self.path = self.private / "work.json"

    def write(self, snapshot=None, attempt="2026-10-09T00:00:00Z"):
        return work_writer.write_work(self.path, private_root=self.private, attempt_at=attempt, snapshot=snapshot)

    def test_allowlist_privacy_bounded_text_and_event(self):
        snapshot = mail_snapshot(messages=[message(subject="x" * 300, snippet="SECRET_SNIPPET",
            body="SECRET_BODY", attachments=["SECRET_ATTACHMENT"], token="SECRET_TOKEN",
            oauth={"secret": "SECRET_OAUTH"}, event={"id": "e1", "name": "event", "category": "action",
            "body": "SECRET_EVENT_BODY", "extracted": "SECRET_EXTRACTED"})])
        previous = copy.deepcopy(snapshot)
        self.assertEqual(self.write(snapshot), "written")
        raw = self.path.read_bytes()
        self.assertNotIn(b"SECRET_", raw)
        self.assertEqual(snapshot, previous)
        payload = json.loads(raw)
        self.assertEqual(len(payload["items"][0]["subject"]), 240)
        self.assertEqual(set(payload["items"][0]["event"]), {"id", "name", "category"})
        self.assertLessEqual(len(raw), work_writer.MAX_BYTES)
        self.assertEqual(list(self.private.glob(".mail-work-*.tmp")), [])

    def test_failure_and_old_attempt_preserve_last_good_bytes(self):
        self.assertEqual(self.write(), "preserved")
        self.assertFalse(self.private.exists())
        self.write(mail_snapshot())
        original = self.path.read_bytes()
        self.assertEqual(self.write(attempt="2026-10-09T00:01:00Z"), "preserved")
        self.assertEqual(self.write(mail_snapshot(messages=[]), attempt="2026-10-08T23:59:00Z"), "superseded")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.write(mail_snapshot(messages=[]), attempt="2026-10-09T00:02:00Z"), "written")
        self.assertEqual(json.loads(self.path.read_bytes())["items"], [])

    def test_invalid_bounds_or_failed_replace_never_erase_last_good(self):
        self.write(mail_snapshot())
        original = self.path.read_bytes()
        for messages in ([message(id="")], [message(id="x" * 121)], [message(), message()],
                         [message(id=str(i)) for i in range(501)], [message(requiredEvent=1)]):
            with self.assertRaisesRegex(work_writer.MailWorkWriteError, "^mail_work_write_failed$"):
                self.write(mail_snapshot(messages=messages), attempt="2026-10-09T00:01:00Z")
            self.assertEqual(self.path.read_bytes(), original)
        with patch.object(work_writer, "_atomic_replace", side_effect=OSError("PRIVATE")):
            with self.assertRaises(work_writer.MailWorkWriteError):
                self.write(mail_snapshot(), attempt="2026-10-09T00:02:00Z")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.private.glob(".mail-work-*.tmp")), [])

    def test_root_escape_and_relative_paths_fail_closed(self):
        for path in (Path(self.tmp.name) / "outside.json", Path("relative.json"), self.private):
            with self.assertRaises(work_writer.MailWorkWriteError):
                work_writer.write_work(path, private_root=self.private,
                    attempt_at="2026-10-09T00:00:00Z", snapshot=mail_snapshot())
        self.assertFalse(self.private.exists())


class MailUpdateWorkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.private = Path(self.tmp.name) / "private"
        self.status, self.work = self.private / "status.json", self.private / "work.json"
        env = patch.dict(os.environ, {"KURO_GMAIL_PRIVATE_DIR": str(self.private),
            "KURO_MAIL_STATUS_FILE": str(self.status), "KURO_MAIL_WORK_FILE": str(self.work)})
        env.start()
        self.addCleanup(env.stop)
        self.server = load_producer("mail_tools_server")
        for name, value in (("_load_mail_preferences", dict(self.server.DEFAULT_MAIL_PREFERENCES)),
                            ("_build_daily_brief_payload", {"mail_snapshot": mail_snapshot()})):
            mock = patch.object(self.server, name, return_value=value)
            setattr(self, name, mock.start())
            self.addCleanup(mock.stop)

    def refresh(self):
        return json.loads(self.server.mail_refresh())

    def test_producer_snapshot_contains_mail_evidence_without_legacy_ui_or_fake_tasks(self):
        payload = self.server._build_mail_snapshot(messages=[], result_estimate=0,
            account="synthetic", query="synthetic", preferences=dict(self.server.DEFAULT_MAIL_PREFERENCES), rules=[])
        self.assertEqual(set(payload), {"schemaVersion", "source", "updatedAt", "mail"})
        self.assertEqual(payload["mail"]["messages"], [])
        self.assertEqual(payload["mail"]["fetchedCount"], 0)
        self.assertNotIn("sections", payload)
        self.assertNotIn("today", payload)

    def test_one_fetch_writes_both_handoffs_without_electron(self):
        result = self.refresh()
        self._build_daily_brief_payload.assert_called_once()
        self.assertEqual(result["handoff"]["state"], "written")
        self.assertEqual(result["workHandoff"]["state"], "written")
        status, work = json.loads(self.status.read_bytes()), json.loads(self.work.read_bytes())
        self.assertEqual(status_writer._timestamp(status["lastSuccessAt"]), status_writer._timestamp(work["updatedAt"]))
        self.assertEqual(status_writer._timestamp(status["lastAttemptAt"]), status_writer._timestamp(work["attemptAt"]))

    def test_provider_failure_preserves_last_good_and_recovers(self):
        self.refresh()
        good = self.work.read_bytes()
        self._build_daily_brief_payload.side_effect = self.server.MailAuthError("PRIVATE")
        result = self.refresh()
        self.assertEqual(result["workHandoff"]["state"], "preserved")
        self.assertEqual(self.work.read_bytes(), good)
        self.assertFalse(json.loads(self.status.read_bytes())["lastAttemptOk"])
        self._build_daily_brief_payload.side_effect = None
        result = self.refresh()
        self.assertTrue(result["ok"])
        self.assertEqual(result["workHandoff"]["state"], "written")
        self.assertTrue(json.loads(self.status.read_bytes())["lastAttemptOk"])

    def test_disabled_work_has_no_write_and_local_write_failure_is_reported(self):
        with patch.dict(os.environ, {"KURO_MAIL_WORK_FILE": ""}):
            self.assertEqual(self.refresh()["workHandoff"]["state"], "disabled")
            self.assertFalse(self.work.exists())
        with patch.object(self.server, "write_work", side_effect=work_writer.MailWorkWriteError("mail_work_write_failed")):
            result = self.refresh()
            self.assertEqual(result["workHandoff"], {"state": "failed", "errorType": "mail_work_write_failed"})
            self.assertTrue(json.loads(self.status.read_bytes())["lastAttemptOk"])
