from __future__ import annotations

import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kuro_core import (
    AvailabilityStatus,
    DecisionTrace,
    DecisionTraceStatus,
    FreshnessStatus,
    IdempotencyConflictError,
    KuroCore,
    KuroCoreStore,
    Observation,
)


UTC = timezone.utc


class KuroCoreStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "kuro-core.sqlite3"
        self.store = KuroCoreStore(self.db_path)
        self.core = KuroCore(self.store)
        self.core.initialize()
        self.now = datetime(2026, 8, 23, 12, 0, 0, 123456, tzinfo=UTC)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def observation(self, *, summary: str = "Study snapshot ready.") -> Observation:
        return Observation.create(
            integration_id="study",
            kind="source_status",
            source_ref="study:daily",
            title="Study source",
            summary=summary,
            observed_at=self.now,
            received_at=self.now,
            valid_until=self.now + timedelta(hours=1),
            availability=AvailabilityStatus.AVAILABLE,
            declared_freshness=FreshnessStatus.CURRENT,
            idempotency_key="study:2026-08-23T12",
        )

    def test_initializes_versioned_schema(self) -> None:
        self.assertEqual(self.store.schema_version(), 3)
        with sqlite3.connect(self.db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        self.assertIn("observations", tables)
        self.assertIn("decision_traces", tables)

    def test_idempotent_ingest_returns_original_identity(self) -> None:
        first = self.observation()
        second = self.observation()

        first_result = self.core.ingest(first)
        second_result = self.core.ingest(second)

        self.assertTrue(first_result.created)
        self.assertFalse(second_result.created)
        self.assertEqual(second_result.observation_id, first_result.observation_id)
        self.assertEqual(len(self.store.list_observations()), 1)
        restored = self.store.get_observation(first_result.observation_id)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.observed_at if restored else None, self.now)

    def test_idempotency_conflict_fails_closed(self) -> None:
        self.core.ingest(self.observation())
        with self.assertRaises(IdempotencyConflictError):
            self.core.ingest(self.observation(summary="Different semantics."))

    def test_concurrent_duplicate_ingest_creates_one_record(self) -> None:
        observations = [self.observation() for _ in range(8)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(self.core.ingest, observations))

        self.assertEqual(sum(1 for result in results if result.created), 1)
        self.assertEqual(len({result.observation_id for result in results}), 1)
        self.assertEqual(len(self.store.list_observations()), 1)

    def test_context_snapshot_recomputes_freshness_at_read_time(self) -> None:
        self.core.ingest(self.observation())

        current = self.core.context_snapshot(as_of=self.now + timedelta(minutes=30))
        stale = self.core.context_snapshot(as_of=self.now + timedelta(hours=2))

        self.assertEqual(current["contract"], "kuro.core.context.v1")
        self.assertEqual(current["items"][0]["status"], "current")
        self.assertEqual(stale["items"][0]["status"], "stale")
        self.assertNotIn("details", stale["items"][0])

    def test_decision_trace_round_trip_keeps_bounded_research_metadata(self) -> None:
        observation = self.observation()
        result = self.core.ingest(observation)
        trace = DecisionTrace.create(
            run_id="run:today:2026-08-23",
            decision_kind="today_priority",
            status=DecisionTraceStatus.COMPLETED,
            created_at=self.now,
            observation_ids=[result.observation_id],
            selected_ids=[result.observation_id],
            model_provider="openai",
            model_name="test-model",
            policy_version="attention.v1",
            config_digest="sha256:test",
            output_summary="Selected one current study item.",
            duration_ms=42,
            metrics={"candidateCount": 1, "selectedCount": 1},
        )

        self.core.record_decision(trace)
        restored = self.store.list_decision_traces(run_id=trace.run_id)

        self.assertEqual(restored, [trace])


if __name__ == "__main__":
    unittest.main()
