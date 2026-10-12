from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from kuro_core.shadow_probe import (
    build_study_shadow_report,
    main,
)


UTC = timezone.utc


class KuroCoreShadowProbeTests(unittest.TestCase):


    def test_study_shadow_report_exposes_only_bounded_metrics(self) -> None:
        as_of = datetime(2026, 10, 7, 1, 30, tzinfo=UTC)
        marker = "SYNTHETIC_PRIVATE_STUDY_TEXT"
        payload = {
            "schemaVersion": 1,
            "updatedAt": "2026-10-07T01:00:00Z",
            "source": "study",
            "studyType": "japanese",
            "vocab": {
                "stats": {
                    "total": 100,
                    "due": 3,
                    "withMistakes": 4,
                },
                "today": {
                    "review": [{"word_id": "r1", "kanji": marker}],
                    "focus": [],
                    "new": [{"word_id": "n1", "meaning": marker}],
                },
            },
            "today": {
                "items": [{"title": marker, "summary": marker}],
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "study_snapshot.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            report = build_study_shadow_report(
                path,
                as_of=as_of,
                ttl_seconds=3600,
            )

        self.assertEqual(report["contract"], "kuro.core.shadow.study.v1")
        self.assertEqual(report["sourceCount"], 1)
        item = report["items"][0]
        self.assertEqual(item["status"], "current")
        self.assertEqual(item["availability"], "available")
        self.assertEqual(item["connection"], "unknown")
        self.assertEqual(item["metrics"]["vocabTotal"], 100)
        self.assertEqual(item["metrics"]["vocabDue"], 3)
        self.assertEqual(item["metrics"]["todayReview"], 1)
        self.assertEqual(item["metrics"]["todayNew"], 1)
        self.assertNotIn(marker, json.dumps(report, ensure_ascii=False))

    def test_study_shadow_cli_does_not_require_legacy_briefing(self) -> None:
        payload = {
            "schemaVersion": 1,
            "updatedAt": "2026-10-07T01:00:00Z",
            "source": "study",
            "studyType": "japanese",
            "vocab": {
                "stats": {
                    "total": 10,
                    "due": 1,
                    "withMistakes": 2,
                },
                "today": {
                    "review": [{"word_id": "r1"}],
                    "focus": [],
                    "new": [],
                },
            },
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "study_snapshot.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(
                    [
                        "--study-snapshot",
                        str(path),
                        "--default-ttl-seconds",
                        "3600",
                    ]
                )

        report = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(report["contract"], "kuro.core.shadow.study.v1")
        self.assertEqual(report["items"][0]["connection"], "unknown")
        self.assertEqual(report["items"][0]["metrics"]["vocabTotal"], 10)

    def test_study_shadow_report_preserves_missing_without_fake_counts(self) -> None:
        as_of = datetime(2026, 10, 7, 1, 30, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as temp_dir:
            report = build_study_shadow_report(
                Path(temp_dir) / "missing.json",
                as_of=as_of,
                ttl_seconds=3600,
            )

        item = report["items"][0]
        self.assertEqual(item["status"], "missing")
        self.assertEqual(item["availability"], "missing")
        self.assertEqual(item["connection"], "unknown")
        self.assertEqual(item["metrics"], {"snapshotPresent": False})



if __name__ == "__main__":
    unittest.main()
