from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from kuro_core import (
    AvailabilityStatus,
    ConnectionStatus,
    DataStatus,
    FreshnessStatus,
    Observation,
)
from kuro_core.legacy_briefing_adapter import source_status_observations


UTC = timezone.utc


class KuroCoreContractTests(unittest.TestCase):
    def test_current_observation_requires_bounded_freshness(self) -> None:
        now = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
        with self.assertRaisesRegex(ValueError, "unbounded current data"):
            Observation.create(
                integration_id="study",
                kind="progress",
                source_ref="study:daily",
                title="Study progress",
                summary="",
                observed_at=now,
                received_at=now,
                availability=AvailabilityStatus.AVAILABLE,
                declared_freshness=FreshnessStatus.CURRENT,
                idempotency_key="study:2026-08-23",
            )

    def test_connection_and_freshness_are_independent(self) -> None:
        observed_at = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
        observation = Observation.create(
            integration_id="mail",
            kind="source_status",
            source_ref="mail:status",
            title="Mail source",
            summary="Connected transport with bounded data validity.",
            observed_at=observed_at,
            received_at=observed_at,
            valid_until=observed_at + timedelta(hours=1),
            availability=AvailabilityStatus.AVAILABLE,
            declared_freshness=FreshnessStatus.CURRENT,
            connection=ConnectionStatus.CONNECTED,
            idempotency_key="mail:status:1",
        )

        self.assertEqual(
            observation.data_status(as_of=observed_at + timedelta(minutes=30)),
            DataStatus.CURRENT,
        )
        self.assertEqual(
            observation.data_status(as_of=observed_at + timedelta(hours=2)),
            DataStatus.STALE,
        )
        self.assertEqual(observation.connection, ConnectionStatus.CONNECTED)

    def test_missing_is_not_converted_to_zero_or_current(self) -> None:
        now = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
        observation = Observation.create(
            integration_id="calendar",
            kind="source_status",
            source_ref="calendar:status",
            title="Calendar source",
            summary="Expected schedule data is missing.",
            observed_at=now,
            received_at=now,
            valid_until=now + timedelta(hours=1),
            availability=AvailabilityStatus.MISSING,
            declared_freshness=FreshnessStatus.CURRENT,
            idempotency_key="calendar:missing:1",
            details={"eventCount": 0},
        )

        self.assertEqual(observation.data_status(as_of=now), DataStatus.MISSING)
        self.assertEqual(observation.details["eventCount"], 0)
        with self.assertRaisesRegex(TypeError, "immutable"):
            observation.details["eventCount"] = 1

    def test_legacy_connected_status_becomes_stale_without_losing_connection(self) -> None:
        observed_at = datetime(2026, 8, 23, 8, 0, tzinfo=UTC)
        received_at = observed_at + timedelta(hours=3)
        observations = source_status_observations(
            {
                "snapshot": {
                    "date": "2026-08-23",
                    "updatedAt": observed_at.isoformat(),
                    "sourceStatus": [
                        {
                            "id": "study",
                            "status": "connected",
                            "updatedAt": observed_at.isoformat(),
                        }
                    ],
                }
            },
            received_at=received_at,
            default_ttl_seconds=3600,
        )

        self.assertEqual(len(observations), 1)
        observation = observations[0]
        self.assertEqual(observation.connection, ConnectionStatus.CONNECTED)
        self.assertEqual(observation.data_status(as_of=received_at), DataStatus.STALE)

    def test_naive_timestamps_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "include a timezone"):
            Observation.create(
                integration_id="study",
                kind="progress",
                source_ref="study:daily",
                title="Study progress",
                summary="",
                observed_at=datetime(2026, 8, 23, 12, 0),
                received_at=datetime(2026, 8, 23, 12, 0),
                valid_until=datetime(2026, 8, 23, 13, 0),
                availability=AvailabilityStatus.AVAILABLE,
                declared_freshness=FreshnessStatus.CURRENT,
                idempotency_key="study:naive",
            )

    def test_legacy_ttl_rejects_boolean_values(self) -> None:
        now = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
        with self.assertRaisesRegex(TypeError, "must be an integer"):
            source_status_observations(
                {
                    "sourceStatus": [
                        {"id": "study", "status": "connected", "updatedAt": now.isoformat()}
                    ]
                },
                received_at=now,
                ttl_by_source={"study": True},
            )

    def test_observation_details_reject_sensitive_fields(self) -> None:
        now = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
        with self.assertRaisesRegex(ValueError, "sensitive field 'provider.access_token'"):
            Observation.create(
                integration_id="mail",
                kind="source_status",
                source_ref="mail:status",
                title="Mail source",
                summary="",
                observed_at=now,
                received_at=now,
                valid_until=now + timedelta(hours=1),
                availability=AvailabilityStatus.AVAILABLE,
                declared_freshness=FreshnessStatus.CURRENT,
                idempotency_key="mail:sensitive",
                details={"provider": {"access_token": "must-not-persist"}},
            )


if __name__ == "__main__":
    unittest.main()
