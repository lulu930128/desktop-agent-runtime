"""Producer writer tests using synthetic snapshots and disposable private dirs."""
import importlib.util
import errno
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from kuro_core.handoff import read_json_handoff
from g2_fixtures import work_writer

ROOT = Path(__file__).resolve().parents[1]
WRITER_FILE = ROOT / "Open-LLM-VTuber/local_mcp/mail_status_handoff.py"
spec = importlib.util.spec_from_file_location("synthetic_mail_status_writer", WRITER_FILE)
writer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(writer)


def snapshot():
    return {"updatedAt": "2026-10-08T10:00:01Z",
            "mail": {**dict.fromkeys(writer.COUNT_FIELDS.values(), 3),
                     "privacy": {"bodyFetched": True, "attachmentsFetched": False,
                                 "mailboxModified": False},
                     "account": "PRIVATE", "query": "PRIVATE", "messages": [
                         {"id": "PRIVATE", "subject": "PRIVATE", "sender": "PRIVATE",
                          "snippet": "PRIVATE", "body": "PRIVATE"}],
                     "rules": "PRIVATE", "preferences": "PRIVATE", "token": "PRIVATE"}}


class MailStatusWriterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.private = Path(self.temp.name) / "private" / "gmail"
        self.path = self.private / "mail_status.json"

    def write(self, attempt="2026-10-08T10:00:00Z", **kwargs):
        return writer.write_status(self.path, private_root=self.private, attempt_at=attempt, **kwargs)

    def read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_success_exact_bounded_whitelist_and_actual_privacy(self):
        self.assertEqual(self.write(snapshot=snapshot()), "written")
        raw = self.path.read_bytes()
        self.assertLessEqual(len(raw), writer.MAX_BYTES)
        self.assertNotIn(b"PRIVATE", raw)
        result = self.read()
        self.assertEqual(set(result), {"schemaVersion", "source", "lastAttemptAt", "lastAttemptOk",
                                      "lastSuccessAt", "counts", "privacy", "errorType"})
        self.assertEqual(set(result["counts"]), set(writer.COUNT_FIELDS))
        self.assertEqual(result["lastSuccessAt"], "2026-10-08T10:00:01.000000Z")
        self.assertTrue(result["lastAttemptOk"])
        self.assertTrue(result["privacy"]["bodyFetched"])
        self.assertFalse(result["privacy"]["mailboxModified"])
        self.assertEqual(list(self.private.glob(".mail-status-*.tmp")), [])

    def test_failure_preserves_last_good_and_sanitizes_error(self):
        self.write(snapshot=snapshot())
        good = self.read()
        self.write("2026-10-08T10:05:00Z", error_type="PRIVATE RAW ERROR")
        result = self.read()
        self.assertFalse(result["lastAttemptOk"])
        self.assertEqual(result["errorType"], "provider_error")
        for key in ("counts", "lastSuccessAt", "privacy"):
            self.assertEqual(result[key], good[key])
        self.assertNotIn("PRIVATE", self.path.read_text(encoding="utf-8"))
        self.write("2026-10-08T10:10:00Z", snapshot=snapshot())
        self.assertEqual(self.read()["errorType"], "")

    def test_first_failure_does_not_invent_success_or_zero(self):
        self.write(error_type="auth_required")
        result = self.read()
        self.assertEqual(result["counts"], {})
        self.assertEqual(result["privacy"], {})
        self.assertEqual(result["lastSuccessAt"], "")
        self.assertEqual(result["errorType"], "auth_required")

    def test_failed_replace_preserves_good_file_and_removes_temp(self):
        self.write(snapshot=snapshot())
        previous = self.path.read_bytes()
        real_replace = os.replace
        seen = []

        def replace(source, target):
            self.assertEqual(Path(source).parent, self.path.parent)
            self.assertEqual(Path(target), self.path)
            self.assertEqual(self.path.read_bytes(), previous)
            json.loads(Path(source).read_text(encoding="utf-8"))
            seen.append(True)
            raise PermissionError("PRIVATE PATH")

        with patch.object(writer.os, "replace", side_effect=replace):
            with self.assertRaisesRegex(writer.MailStatusWriteError, "^mail_status_write_failed$"):
                self.write("2026-10-08T10:05:00Z")
        self.assertTrue(seen)
        self.assertIs(writer.os.replace, real_replace)
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertEqual(list(self.private.glob(".mail-status-*.tmp")), [])

    def test_reader_never_observes_truncated_json(self):
        self.write(snapshot=snapshot())
        stop = threading.Event()
        errors = []
        reads = []

        def read_loop():
            while not stop.is_set():
                try:
                    payload = read_json_handoff(self.path, max_bytes=writer.MAX_BYTES)
                    self.assertIsInstance(payload, dict)
                    self.assertEqual(payload["schemaVersion"], 1)
                    self.assertEqual(payload["source"], "gmail_briefing")
                    self.assertEqual(set(payload["counts"]), set(writer.COUNT_FIELDS))
                    reads.append(True)
                except Exception as exc:
                    errors.append(type(exc).__name__)

        thread = threading.Thread(target=read_loop)
        thread.start()
        try:
            for second in range(2, 22):
                self.write(f"2026-10-08T10:01:{second:02d}Z", snapshot=snapshot())
        finally:
            stop.set()
            thread.join(timeout=3)
        self.assertFalse(thread.is_alive())
        self.assertTrue(reads)
        self.assertEqual(errors, [])

    def test_atomic_replace_retries_only_sharing_errors_then_commits(self):
        self.write(snapshot=snapshot())
        previous = self.path.read_bytes()
        pending = self.private/"synthetic.tmp"
        pending.write_bytes(b'{"synthetic":true}')
        real_replace = os.replace
        attempts = []
        errors = [PermissionError(errno.EACCES, "synthetic reader"),
                  OSError(errno.EBUSY, "synthetic busy")]

        def replace(source, target):
            self.assertEqual(Path(source).parent, Path(target).parent)
            self.assertEqual(self.path.read_bytes(), previous)
            attempts.append(True)
            if errors:
                raise errors.pop(0)
            real_replace(source, target)

        with patch.object(writer.os, "replace", side_effect=replace), \
                patch.object(writer.time, "monotonic", side_effect=[0, .1, .2]), \
                patch.object(writer.time, "sleep") as sleep:
            writer._atomic_replace(pending, self.path)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(self.path.read_bytes(), b'{"synthetic":true}')
        self.assertFalse(pending.exists())

    def test_atomic_replace_timeout_preserves_target_and_pending_file(self):
        self.write(snapshot=snapshot())
        previous = self.path.read_bytes()
        pending = self.private/"synthetic.tmp"
        pending.write_bytes(b"pending")
        error = PermissionError(errno.EACCES, "synthetic reader")
        with patch.object(writer.os, "replace", side_effect=error) as replace, \
                patch.object(writer.time, "monotonic", side_effect=[0, .1, .6]), \
                patch.object(writer.time, "sleep") as sleep:
            with self.assertRaises(PermissionError):
                writer._atomic_replace(pending, self.path)
        self.assertEqual(replace.call_count, 2)
        sleep.assert_called_once_with(.01)
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertEqual(pending.read_bytes(), b"pending")

    def test_atomic_replace_nonretryable_error_fails_immediately(self):
        error = OSError(errno.ENOSPC, "synthetic disk full")
        with patch.object(writer.os, "replace", side_effect=error) as replace, \
                patch.object(writer.time, "sleep") as sleep:
            with self.assertRaises(OSError) as caught:
                writer._atomic_replace(self.private/"synthetic.tmp", self.path)
        self.assertIs(caught.exception, error)
        replace.assert_called_once()
        sleep.assert_not_called()

    def test_cross_process_ordering_old_attempt_cannot_replace_newer(self):
        # Different interpreter processes share only the file and OS lock.
        code = '''import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("writer", sys.argv[1])
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
print(w.write_status(Path(sys.argv[2]), private_root=Path(sys.argv[3]), attempt_at=sys.argv[4]))
'''
        self.write(snapshot=snapshot())
        children = []
        try:
            for minute in (4, 1, 5, 2, 3):
                children.append(subprocess.Popen(
                    [sys.executable, "-B", "-c", code, str(WRITER_FILE), str(self.path),
                     str(self.private), f"2026-10-08T10:{minute:02d}:00Z"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
            for child in children:
                stdout, stderr = child.communicate(timeout=10)
                self.assertEqual(child.returncode, 0, stderr.decode(errors="replace"))
                self.assertIn(stdout.strip(), (b"written", b"superseded"))
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
                    child.communicate(timeout=3)
        newest = self.path.read_bytes()
        self.assertEqual(self.read()["lastAttemptAt"], "2026-10-08T10:05:00.000000Z")
        self.assertEqual(self.write("2026-10-08T10:04:00Z", snapshot=snapshot()), "superseded")
        self.assertEqual(self.path.read_bytes(), newest)
        self.assertEqual(self.read()["counts"]["fetched"], 3)

    def test_lock_contention_has_bounded_timeout(self):
        self.private.mkdir(parents=True)
        lock = self.private / "mail_status.json.lock"
        with writer._commit_lock(lock):
            with self.assertRaisesRegex(writer.MailStatusWriteError, "mail_status_lock_timeout"):
                with writer._commit_lock(lock, timeout=0.05):
                    self.fail("Concurrent lock was acquired")

    def test_invalid_metrics_or_prior_file_fail_closed(self):
        for value in (True, -1, 1000001, "3", None):
            data = snapshot()
            data["mail"]["fetchedCount"] = value
            with self.assertRaises(writer.MailStatusWriteError):
                self.write(snapshot=data)
            self.assertFalse(self.path.exists())
        self.path.write_bytes(b"invalid")
        with self.assertRaises(writer.MailStatusWriteError):
            self.write()
        self.assertEqual(self.path.read_bytes(), b"invalid")

    def test_private_root_escape_is_rejected_without_write(self):
        outside = Path(self.temp.name) / "outside.json"
        with self.assertRaisesRegex(writer.MailStatusWriteError, "mail_status_write_failed"):
            writer.write_status(outside, private_root=self.private,
                                attempt_at="2026-10-08T10:00:00Z", snapshot=snapshot())
        self.assertFalse(outside.exists())


class MailUpdateHandoffTests(unittest.TestCase):
    """Exercise the production refresh function with no provider or private IO."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.private = Path(self.temp.name)/"private"/"gmail"
        self.path = self.private/"mail_status.json"
        env = patch.dict(os.environ, {"KURO_GMAIL_PRIVATE_DIR": str(self.private),
                                      "KURO_MAIL_STATUS_FILE": str(self.path)})
        env.start()
        self.addCleanup(env.stop)
        spec = importlib.util.spec_from_file_location(
            "synthetic_mail_tools_server", ROOT/"Open-LLM-VTuber/local_mcp/mail_tools_server.py")
        self.server = importlib.util.module_from_spec(spec)
        modules = patch.dict(sys.modules, {spec.name: self.server, "mail_status_handoff": writer,
                                          "mail_work_handoff": work_writer})
        modules.start()
        self.addCleanup(modules.stop)
        spec.loader.exec_module(self.server)
        for name, kwargs in (
            ("_load_mail_preferences", {"return_value": dict(self.server.DEFAULT_MAIL_PREFERENCES)}),
            ("_build_daily_brief_payload", {"return_value": {"mail_snapshot": snapshot()}}),
        ):
            mock = patch.object(self.server, name, **kwargs)
            setattr(self, name, mock.start())
            self.addCleanup(mock.stop)

    def test_provider_failure_writes_bounded_auth_or_provider_error(self):
        for error_class, expected in ((self.server.MailAuthError, "auth_required"),
                                      (RuntimeError, "provider_error")):
            with self.subTest(error=expected):
                self._build_daily_brief_payload.side_effect = error_class("PRIVATE RAW EXCEPTION")
                result = json.loads(self.server.mail_refresh())
                self.assertFalse(result["ok"])
                self.assertEqual(result["handoff"], {"state": "written"})
                raw = self.path.read_text(encoding="utf-8")
                status = json.loads(raw)
                self.assertEqual(status["errorType"], expected)
                self.assertFalse(status["lastAttemptOk"])
                self.assertEqual(status["lastSuccessAt"], "")
                self.assertEqual(status["counts"], {})
                self.assertNotIn("PRIVATE", raw)

    def test_auth_failure_preserves_last_good_counts_and_success_time(self):
        self.assertTrue(json.loads(self.server.mail_refresh())["ok"])
        good = json.loads(self.path.read_text(encoding="utf-8"))
        self._build_daily_brief_payload.side_effect = self.server.MailAuthError("PRIVATE")
        self.server.mail_refresh()
        failed = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(failed["errorType"], "auth_required")
        for key in ("counts", "privacy", "lastSuccessAt"):
            self.assertEqual(failed[key], good[key])

    def test_provider_success_needs_no_electron_delivery(self):
        result = json.loads(self.server.mail_refresh())
        self.assertTrue(result["ok"])
        self.assertFalse(hasattr(self.server, "_post_briefing_snapshot"))
        self.assertEqual(result["handoff"], {"state": "written"})
        status = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertTrue(status["lastAttemptOk"])
        self.assertEqual(status["errorType"], "")

    def test_disabled_handoff_does_not_write_on_auth_failure(self):
        self._build_daily_brief_payload.side_effect = self.server.MailAuthError("PRIVATE")
        with patch.dict(os.environ, {"KURO_MAIL_STATUS_FILE": ""}):
            result = json.loads(self.server.mail_refresh())
        self.assertEqual(result["handoff"], {"state": "disabled"})
        self.assertFalse(self.private.exists())


if __name__ == "__main__":
    unittest.main()
