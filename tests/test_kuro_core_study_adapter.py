from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kuro_core import (
    AvailabilityStatus,
    ConnectionStatus,
    DataStatus,
    FreshnessStatus,
)
from kuro_core.study_adapter import (
    study_snapshot_file_observation,
    study_snapshot_observation,
)


UTC = timezone.utc


def valid_snapshot(updated_at: str = "2026-10-07T01:00:00Z") -> dict:
    return {
        "schemaVersion": 1,
        "updatedAt": updated_at,
        "source": "study",
        "studyType": "japanese",
        "vocab": {
            "stats": {
                "total": 120,
                "due": 4,
                "withMistakes": 7,
                "statuses": {"new": 30},
            },
            "today": {
                "review": [{"word_id": "review-1", "kanji": "秘密單字"}],
                "focus": [{"word_id": "focus-1", "kanji": "不要外流"}],
                "new": [],
            },
        },
        "today": {
            "items": [
                {
                    "title": "私人學習內容",
                    "summary": "這些文字不應進 observation",
                }
            ]
        },
    }


class StudyObservationAdapterTests(unittest.TestCase):
    def test_timestamp_overflow_is_partial_without_claiming_freshness(self) -> None:
        now = datetime(2026, 10, 9, tzinfo=UTC)
        for stamp in ("9999-12-31T23:59:59Z", "0001-01-01T00:00:00+01:00"):
            with self.subTest(timestamp=stamp):
                observation = study_snapshot_observation(
                    valid_snapshot(stamp), received_at=now, ttl_seconds=3600)
                self.assertEqual(observation.availability, AvailabilityStatus.PARTIAL)
                self.assertEqual(observation.declared_freshness, FreshnessStatus.UNKNOWN)
                self.assertIsNone(observation.observed_at)
                self.assertIsNone(observation.valid_until)
                self.assertIn("study_updated_at_invalid", observation.limitations)

    def test_valid_snapshot_projects_only_bounded_counts(self) -> None:
        received_at = datetime(2026, 10, 7, 1, 30, tzinfo=UTC)
        observation = study_snapshot_observation(
            valid_snapshot(),
            received_at=received_at,
            ttl_seconds=3600,
        )

        self.assertEqual(observation.availability, AvailabilityStatus.AVAILABLE)
        self.assertEqual(observation.declared_freshness, FreshnessStatus.CURRENT)
        self.assertEqual(observation.connection, ConnectionStatus.UNKNOWN)
        self.assertEqual(observation.details["vocabTotal"], 120)
        self.assertEqual(observation.details["vocabDue"], 4)
        self.assertEqual(observation.details["todayReview"], 1)
        self.assertEqual(observation.details["todayFocus"], 1)
        self.assertEqual(observation.details["todayNew"], 0)

        serialized = str(observation.semantic_payload())
        self.assertNotIn("秘密單字", serialized)
        self.assertNotIn("不要外流", serialized)
        self.assertNotIn("私人學習內容", serialized)
        self.assertNotIn("statuses", serialized)

    def test_freshness_expires_without_changing_connection(self) -> None:
        received_at = datetime(2026, 10, 7, 1, 30, tzinfo=UTC)
        observation = study_snapshot_observation(
            valid_snapshot(),
            received_at=received_at,
            ttl_seconds=3600,
        )

        self.assertEqual(
            observation.data_status(as_of=datetime(2026, 10, 7, 1, 59, tzinfo=UTC)),
            DataStatus.CURRENT,
        )
        self.assertEqual(
            observation.data_status(as_of=datetime(2026, 10, 7, 2, 1, tzinfo=UTC)),
            DataStatus.STALE,
        )
        self.assertEqual(observation.connection, ConnectionStatus.UNKNOWN)

    def test_missing_snapshot_does_not_infer_zero_counts(self) -> None:
        now = datetime(2026, 10, 7, 1, 0, tzinfo=UTC)
        observation = study_snapshot_observation(
            None,
            received_at=now,
            ttl_seconds=3600,
        )

        self.assertEqual(observation.availability, AvailabilityStatus.MISSING)
        self.assertEqual(observation.declared_freshness, FreshnessStatus.UNKNOWN)
        self.assertEqual(observation.connection, ConnectionStatus.UNKNOWN)
        self.assertEqual(observation.details, {"snapshotPresent": False})
        self.assertNotIn("todayReview", observation.details)
        self.assertNotIn("vocabTotal", observation.details)

    def test_missing_updated_at_is_not_reported_current_or_connected(self) -> None:
        payload = valid_snapshot()
        payload.pop("updatedAt")
        now = datetime(2026, 10, 7, 1, 0, tzinfo=UTC)

        observation = study_snapshot_observation(
            payload,
            received_at=now,
            ttl_seconds=3600,
        )

        self.assertEqual(observation.availability, AvailabilityStatus.AVAILABLE)
        self.assertEqual(observation.declared_freshness, FreshnessStatus.UNKNOWN)
        self.assertEqual(observation.data_status(as_of=now), DataStatus.UNKNOWN)
        self.assertEqual(observation.connection, ConnectionStatus.UNKNOWN)
        self.assertIn("study_updated_at_missing", observation.limitations)

    def test_malformed_counts_do_not_become_zero(self) -> None:
        payload = valid_snapshot()
        payload["vocab"]["stats"]["due"] = "4"
        payload["vocab"]["today"].pop("focus")
        now = datetime(2026, 10, 7, 1, 30, tzinfo=UTC)

        observation = study_snapshot_observation(
            payload,
            received_at=now,
            ttl_seconds=3600,
        )

        self.assertEqual(observation.availability, AvailabilityStatus.PARTIAL)
        self.assertEqual(observation.data_status(as_of=now), DataStatus.PARTIAL)
        self.assertNotIn("vocabDue", observation.details)
        self.assertNotIn("todayFocus", observation.details)
        self.assertIn("study_due_invalid", observation.limitations)
        self.assertIn("study_today_focus_missing", observation.limitations)

    def test_invalid_word_items_are_not_counted_and_mark_partial(self) -> None:
        payload = valid_snapshot()
        payload["vocab"]["today"]["review"].extend(
            [
                {"kanji": "missing id"},
                "not-an-object",
            ]
        )
        now = datetime(2026, 10, 7, 1, 30, tzinfo=UTC)

        observation = study_snapshot_observation(
            payload,
            received_at=now,
            ttl_seconds=3600,
        )

        self.assertEqual(observation.availability, AvailabilityStatus.PARTIAL)
        self.assertEqual(observation.details["todayReview"], 1)
        self.assertIn(
            "study_today_review_invalid_items:2",
            observation.limitations,
        )

    def test_invalid_schema_is_partial(self) -> None:
        payload = valid_snapshot()
        payload["schemaVersion"] = 2
        now = datetime(2026, 10, 7, 1, 30, tzinfo=UTC)

        observation = study_snapshot_observation(
            payload,
            received_at=now,
            ttl_seconds=3600,
        )

        self.assertEqual(observation.availability, AvailabilityStatus.PARTIAL)
        self.assertIn("study_schema_version_unsupported:2", observation.limitations)
        self.assertEqual(observation.data_status(as_of=now), DataStatus.PARTIAL)

    def test_idempotency_depends_on_sanitized_semantics_not_private_words(self) -> None:
        now = datetime(2026, 10, 7, 1, 30, tzinfo=UTC)
        first = valid_snapshot()
        second = valid_snapshot()
        second["vocab"]["today"]["review"][0]["kanji"] = "另一個私人單字"
        second["today"]["items"][0]["summary"] = "另一段私人內容"

        left = study_snapshot_observation(first, received_at=now, ttl_seconds=3600)
        right = study_snapshot_observation(second, received_at=now, ttl_seconds=3600)

        self.assertEqual(left.idempotency_key, right.idempotency_key)
        self.assertEqual(left.semantic_hash(), right.semantic_hash())

    def test_file_adapter_reads_valid_snapshot_without_mutating_file(self) -> None:
        now = datetime(2026, 10, 7, 1, 30, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "study_snapshot.json"
            payload = valid_snapshot()
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            before = path.read_bytes()

            observation = study_snapshot_file_observation(
                path,
                received_at=now,
                ttl_seconds=3600,
            )

            self.assertEqual(observation.availability, AvailabilityStatus.AVAILABLE)
            self.assertEqual(observation.details["todayReview"], 1)
            self.assertEqual(path.read_bytes(), before)

    def test_file_adapter_missing_file_reports_missing_without_fake_counts(self) -> None:
        now = datetime(2026, 10, 7, 1, 30, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as temp_dir:
            observation = study_snapshot_file_observation(
                Path(temp_dir) / "missing.json",
                received_at=now,
                ttl_seconds=3600,
            )

        self.assertEqual(observation.availability, AvailabilityStatus.MISSING)
        self.assertEqual(observation.connection, ConnectionStatus.UNKNOWN)
        self.assertNotIn("vocabTotal", observation.details)
        self.assertIn("study_snapshot_missing", observation.limitations)

    def test_file_adapter_invalid_json_is_partial_and_private_data_free(self) -> None:
        now = datetime(2026, 10, 7, 1, 30, tzinfo=UTC)
        marker = "SYNTHETIC_PRIVATE_INVALID_JSON"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "invalid.json"
            path.write_text('{"value":"' + marker + '"', encoding="utf-8")
            observation = study_snapshot_file_observation(
                path,
                received_at=now,
                ttl_seconds=3600,
            )

        self.assertEqual(observation.availability, AvailabilityStatus.PARTIAL)
        self.assertEqual(observation.declared_freshness, FreshnessStatus.UNKNOWN)
        self.assertIn("study_snapshot_invalid_json", observation.limitations)
        self.assertNotIn(marker, str(observation.semantic_payload()))

    def test_file_adapter_invalid_utf8_and_shape_are_partial(self) -> None:
        now = datetime(2026, 10, 7, 1, 30, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_utf8 = Path(temp_dir) / "invalid-utf8.json"
            invalid_utf8.write_bytes(b"\xff\xfe")
            utf8_observation = study_snapshot_file_observation(
                invalid_utf8,
                received_at=now,
                ttl_seconds=3600,
            )

            invalid_shape = Path(temp_dir) / "invalid-shape.json"
            invalid_shape.write_text("[]", encoding="utf-8")
            shape_observation = study_snapshot_file_observation(
                invalid_shape,
                received_at=now,
                ttl_seconds=3600,
            )

        self.assertEqual(utf8_observation.availability, AvailabilityStatus.PARTIAL)
        self.assertIn("study_snapshot_invalid_utf8", utf8_observation.limitations)
        self.assertEqual(shape_observation.availability, AvailabilityStatus.PARTIAL)
        self.assertIn("study_snapshot_invalid_shape", shape_observation.limitations)

    def test_file_adapter_enforces_bounded_read_size(self) -> None:
        now = datetime(2026, 10, 7, 1, 30, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "oversized.json"
            path.write_bytes(b"x" * 32)
            observation = study_snapshot_file_observation(
                path,
                received_at=now,
                ttl_seconds=3600,
                max_bytes=16,
            )

        self.assertEqual(observation.availability, AvailabilityStatus.PARTIAL)
        self.assertIn("study_snapshot_too_large", observation.limitations)

    def test_file_adapter_rejects_invalid_max_bytes(self) -> None:
        now = datetime(2026, 10, 7, 1, 30, tzinfo=UTC)
        with self.assertRaisesRegex(TypeError, "max_bytes must be an integer"):
            study_snapshot_file_observation(
                "unused.json",
                received_at=now,
                ttl_seconds=3600,
                max_bytes=True,
            )
        with self.assertRaisesRegex(ValueError, "max_bytes must be between"):
            study_snapshot_file_observation(
                "unused.json",
                received_at=now,
                ttl_seconds=3600,
                max_bytes=0,
            )

    def test_ttl_rejects_boolean_and_out_of_range_values(self) -> None:
        now = datetime(2026, 10, 7, 1, 30, tzinfo=UTC)
        with self.assertRaisesRegex(TypeError, "must be an integer"):
            study_snapshot_observation(valid_snapshot(), received_at=now, ttl_seconds=True)
        with self.assertRaisesRegex(ValueError, "between 1 and"):
            study_snapshot_observation(valid_snapshot(), received_at=now, ttl_seconds=0)
        with self.assertRaisesRegex(ValueError, "between 1 and"):
            study_snapshot_observation(
                valid_snapshot(),
                received_at=now,
                ttl_seconds=31 * 24 * 60 * 60,
            )


if __name__ == "__main__":
    unittest.main()
