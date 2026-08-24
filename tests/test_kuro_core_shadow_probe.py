from __future__ import annotations

import unittest
from datetime import datetime, timezone

from kuro_core.shadow_probe import (
    build_shadow_report,
    parse_ttl_overrides,
    require_loopback_url,
)


UTC = timezone.utc


class KuroCoreShadowProbeTests(unittest.TestCase):
    def test_probe_url_is_loopback_only_and_credential_free(self) -> None:
        self.assertEqual(
            require_loopback_url("http://127.0.0.1:23567/briefing"),
            "http://127.0.0.1:23567/briefing",
        )
        self.assertEqual(
            require_loopback_url("http://localhost:23567/briefing"),
            "http://localhost:23567/briefing",
        )
        with self.assertRaisesRegex(ValueError, "loopback"):
            require_loopback_url("http://example.com/briefing")
        with self.assertRaisesRegex(ValueError, "credentials"):
            require_loopback_url("http://user:pass@127.0.0.1:23567/briefing")
        with self.assertRaisesRegex(ValueError, "exact /briefing path"):
            require_loopback_url("http://127.0.0.1:23567/status")
        with self.assertRaisesRegex(ValueError, "exact /briefing path"):
            require_loopback_url("http://127.0.0.1:23567/status")

    def test_shadow_report_contains_health_metadata_not_source_payload(self) -> None:
        as_of = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
        report = build_shadow_report(
            {
                "snapshot": {
                    "date": "2026-08-23",
                    "sourceStatus": [
                        {
                            "id": "mail",
                            "status": "connected",
                            "updatedAt": "2026-08-23T08:00:00Z",
                            "privateMessages": ["must not be copied"],
                        }
                    ],
                    "mail": {"messages": [{"body": "must not be copied"}]},
                }
            },
            as_of=as_of,
            default_ttl_seconds=3600,
        )

        self.assertEqual(report["contract"], "kuro.core.shadow.source-status.v1")
        self.assertEqual(report["items"][0]["status"], "stale")
        serialized = str(report)
        self.assertNotIn("must not be copied", serialized)
        self.assertNotIn("privateMessages", serialized)

    def test_source_ttl_overrides_are_explicit(self) -> None:
        self.assertEqual(parse_ttl_overrides(["mail=300", "study=7200"]), {"mail": 300, "study": 7200})
        with self.assertRaisesRegex(ValueError, "SOURCE=SECONDS"):
            parse_ttl_overrides(["mail"])


if __name__ == "__main__":
    unittest.main()
