from __future__ import annotations

from datetime import datetime
from typing import Any

from .contracts import DecisionTrace, Observation, isoformat_utc, normalize_datetime, utc_now
from .storage import IngestResult, KuroCoreStore


CONTEXT_CONTRACT = "kuro.core.context.v1"


class KuroCore:
    """Small application boundary around the shadow Kuro Core store."""

    def __init__(self, store: KuroCoreStore) -> None:
        self.store = store

    def initialize(self) -> None:
        self.store.initialize()

    def ingest(self, observation: Observation) -> IngestResult:
        return self.store.ingest_observation(observation)

    def record_decision(self, trace: DecisionTrace) -> None:
        self.store.append_decision_trace(trace)

    def context_snapshot(
        self,
        *,
        as_of: datetime | None = None,
        integration_id: str = "",
        limit: int = 100,
        include_details: bool = False,
    ) -> dict[str, Any]:
        effective_at = normalize_datetime(as_of or utc_now(), field_name="as_of")
        observations = self.store.list_observations(
            integration_id=integration_id,
            limit=limit,
        )
        items: list[dict[str, Any]] = []
        for observation in observations:
            item: dict[str, Any] = {
                "observationId": observation.observation_id,
                "integrationId": observation.integration_id,
                "kind": observation.kind,
                "sourceRef": observation.source_ref,
                "title": observation.title,
                "summary": observation.summary,
                "observedAt": isoformat_utc(observation.observed_at),
                "receivedAt": isoformat_utc(observation.received_at),
                "validUntil": isoformat_utc(observation.valid_until),
                "availability": observation.availability.value,
                "freshness": observation.effective_freshness(as_of=effective_at).value,
                "connection": observation.connection.value,
                "status": observation.data_status(as_of=effective_at).value,
                "limitations": list(observation.limitations),
            }
            if include_details:
                item["details"] = observation.details
            items.append(item)
        return {
            "contract": CONTEXT_CONTRACT,
            "generatedAt": isoformat_utc(utc_now()),
            "asOf": isoformat_utc(effective_at),
            "count": len(items),
            "items": items,
        }
