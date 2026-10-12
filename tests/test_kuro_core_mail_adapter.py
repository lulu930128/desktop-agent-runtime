"""Synthetic handoff tests; paths and payloads are never production data."""
import ast
import copy
import errno
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from kuro_core.handoff import HandoffReadError, read_json_handoff
from kuro_core.mail_adapter import (COUNT_KEYS, build_mail_status, mail_status_observation)

NOW = datetime(2026, 10, 8, 10, tzinfo=timezone.utc)


def status_payload():
    return {"schemaVersion": 1, "source": "gmail_briefing",
            "lastAttemptAt": "2026-10-08T09:59:00Z", "lastAttemptOk": True,
            "lastSuccessAt": "2026-10-08T09:59:01Z", "errorType": "",
            "counts": dict.fromkeys(COUNT_KEYS, 2),
            "privacy": {"bodyFetched": True, "attachmentsFetched": False, "mailboxModified": False}}


class MailAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic-status.json"

    def project(self, payload, as_of=NOW):
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        before = (self.path.read_bytes(), self.path.stat().st_mtime_ns)
        with patch("sqlite3.connect", side_effect=AssertionError("No DB")), \
                patch("socket.socket", side_effect=AssertionError("No network")):
            result = build_mail_status(self.path, as_of=as_of)
        self.assertEqual(before, (self.path.read_bytes(), self.path.stat().st_mtime_ns))
        self.assertEqual(result["contract"], "kuro.core.integration.mail.v1")
        return result["item"]

    def test_current_and_stale_derive_only_from_success(self):
        payload = status_payload()
        for as_of, freshness in ((NOW, "current"), (NOW + timedelta(hours=1), "stale")):
            item = self.project(payload, as_of)
            self.assertEqual((item["availability"], item["connection"], item["freshness"]),
                             ("available", "connected", freshness))
            self.assertEqual(item["observedAt"], "2026-10-08T09:59:01.000000Z")
            self.assertTrue(item["metrics"]["privacy"]["bodyFetched"])

    def test_failed_attempt_retains_current_or_stale_good_data(self):
        payload = status_payload()
        payload.update(lastAttemptAt="2026-10-08T10:00:00Z", lastAttemptOk=False,
                       errorType="provider_error")
        for as_of, freshness in ((NOW, "current"), (NOW + timedelta(hours=1), "stale")):
            item = self.project(payload, as_of)
            self.assertEqual((item["availability"], item["freshness"], item["connection"]),
                             ("available", freshness, "disconnected"))
            self.assertEqual(item["metrics"]["fetched"], 2)

    def test_never_success_does_not_invent_zero_or_current(self):
        for error, availability in (("provider_error", "offline"), ("auth_required", "auth_required")):
            payload = status_payload()
            payload.update(lastAttemptOk=False, lastSuccessAt="", counts={}, privacy={}, errorType=error)
            item = self.project(payload)
            self.assertEqual((item["availability"], item["freshness"], item["connection"]),
                             (availability, "unknown", "disconnected"))
            self.assertIsNone(item["observedAt"])
            self.assertNotIn("fetched", item["metrics"])

    def test_missing_unreadable_invalid_and_oversize(self):
        item = build_mail_status(self.path, as_of=NOW)["item"]
        self.assertEqual((item["availability"], item["connection"]), ("missing", "unknown"))
        for raw in (b"{", b"\xff", b"[]", b"null", b"{}", b"x" * 65537,
                    b'{"schemaVersion":true,"source":"gmail_briefing"}'):
            self.path.write_bytes(raw)
            item = build_mail_status(self.path, as_of=NOW)["item"]
            self.assertEqual((item["availability"], item["connection"]), ("partial", "unknown"))
        with patch("pathlib.Path.stat", side_effect=PermissionError("PRIVATE PATH")):
            result = build_mail_status(self.path, as_of=NOW)
        self.assertEqual(result["item"]["availability"], "offline")
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_incomplete_counts_invalid_types_and_schema_are_partial(self):
        for value in (None, True, -1, 1000001, "2", float("nan")):
            payload = status_payload()
            payload["counts"]["unread"] = value
            item = self.project(payload)
            self.assertEqual(item["availability"], "partial")
            self.assertNotIn("unread", item["metrics"])
        for key, value in (("schemaVersion", 2), ("source", "PRIVATE"),
                           ("lastSuccessAt", "bad"), ("lastSuccessAt", "9999-12-31T23:59:59Z"),
                           ("lastAttemptAt", "bad"), ("lastAttemptOk", 1),
                           ("privacy", {}), ("errorType", "PRIVATE")):
            payload = status_payload()
            payload[key] = value
            item = self.project(payload)
            self.assertEqual(item["availability"], "partial")
            self.assertNotIn("PRIVATE", json.dumps(item))

    def test_whitelist_privacy_and_idempotency(self):
        payload = status_payload()
        for key in ("account", "query", "message", "subject", "sender", "snippet", "body",
                    "rules", "preferences", "token", "privatePath"):
            payload[key] = "PRIVATE-CONTENT"
            payload["counts"][key] = "PRIVATE-CONTENT"
        original = copy.deepcopy(payload)
        first = mail_status_observation(payload, received_at=NOW)
        second = mail_status_observation(payload, received_at=NOW + timedelta(seconds=1))
        self.assertEqual(first.idempotency_key, second.idempotency_key)
        self.assertEqual(payload, original)
        self.assertNotIn("PRIVATE", json.dumps(self.project(payload)))

    def test_timestamp_timezone_overflow_is_partial(self):
        for key in ("lastAttemptAt", "lastSuccessAt"):
            payload = status_payload()
            payload[key] = "0001-01-01T00:00:00+01:00"
            with self.subTest(field=key):
                item = self.project(payload)
                self.assertEqual(item["availability"], "partial")
                self.assertGreater(item["limitationCount"], 0)

    def test_limits_reject_bool_string_and_out_of_range(self):
        for key, values in (("ttl_seconds", (True, "1", 0, 2592001)),
                            ("max_bytes", (True, "1", 0, 65537))):
            for value in values:
                with self.assertRaises(ValueError):
                    build_mail_status(self.path, as_of=NOW, **{key: value})

    def test_reader_limits_actual_read_after_stat_race(self):
        self.path.write_bytes(b"x" * 2048)
        from types import SimpleNamespace
        with patch("pathlib.Path.stat", return_value=SimpleNamespace(st_size=1)):
            with self.assertRaises(HandoffReadError) as caught:
                read_json_handoff(self.path, max_bytes=32)
        self.assertEqual(caught.exception.code, "too_large")

    def test_reader_retries_sharing_errors_on_stat_and_open(self):
        self.path.write_text('{"schemaVersion":1}', encoding="utf-8")
        real_stat, real_open = self.path.stat, self.path.open
        calls = []

        def stat():
            calls.append("stat")
            if len(calls) == 1:
                raise PermissionError(errno.EACCES, "PRIVATE")
            return real_stat()

        def open_file(*args):
            calls.append("open")
            if calls.count("open") == 1:
                raise OSError(errno.EBUSY, "PRIVATE")
            return real_open(*args)

        with patch("kuro_core.handoff.Path.stat", side_effect=stat), \
                patch("kuro_core.handoff.Path.open", side_effect=open_file), \
                patch("kuro_core.handoff.time.monotonic", side_effect=[0, .1, .2]), \
                patch("kuro_core.handoff.time.sleep") as sleep:
            result = read_json_handoff(self.path, max_bytes=64)
        self.assertEqual(result, {"schemaVersion": 1})
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(calls, ["stat", "stat", "open", "stat", "open"])

    def test_reader_permission_timeout_is_bounded_and_sanitized(self):
        self.path.write_bytes(b"{}")
        with patch("kuro_core.handoff.Path.open", side_effect=PermissionError(errno.EACCES, "PRIVATE")) as open_file, \
                patch("kuro_core.handoff.time.monotonic", side_effect=[0, .1, .6]), \
                patch("kuro_core.handoff.time.sleep") as sleep:
            with self.assertRaises(HandoffReadError) as caught:
                read_json_handoff(self.path, max_bytes=64)
        self.assertEqual(str(caught.exception), "read_failed")
        self.assertEqual(open_file.call_count, 2)
        sleep.assert_called_once_with(.01)

    def test_reader_nonretryable_and_missing_errors_fail_immediately(self):
        for error, code in ((OSError(errno.EIO, "PRIVATE"), "read_failed"),
                            (FileNotFoundError(errno.ENOENT, "PRIVATE"), "missing")):
            with self.subTest(code=code), \
                    patch("kuro_core.handoff.Path.stat", side_effect=error) as stat, \
                    patch("kuro_core.handoff.time.sleep") as sleep:
                with self.assertRaises(HandoffReadError) as caught:
                    read_json_handoff(self.path, max_bytes=64)
                self.assertEqual(str(caught.exception), code)
                stat.assert_called_once()
                sleep.assert_not_called()

    def test_no_provider_store_or_schedule_imports(self):
        root = Path(__file__).resolve().parents[1] / "kuro_core"
        forbidden = {"mail_tools_server", "mail_status_handoff", "sqlite3", "storage",
                     "schedule_store", "httpx", "requests", "urllib"}
        for name in ("mail_adapter.py", "handoff.py"):
            tree = ast.parse((root / name).read_text(encoding="utf-8"))
            imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
            imports |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
            self.assertTrue(imports.isdisjoint(forbidden))


if __name__ == "__main__":
    unittest.main()
