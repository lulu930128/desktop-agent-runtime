from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .contracts import (
    AvailabilityStatus,
    ConnectionStatus,
    DecisionTrace,
    DecisionTraceStatus,
    FreshnessStatus,
    Observation,
    isoformat_utc,
    parse_datetime,
    utc_now,
)


SCHEMA_VERSION = 1


class IdempotencyConflictError(RuntimeError):
    """Raised when one idempotency key is reused for different semantics."""


@dataclass(frozen=True)
class IngestResult:
    created: bool
    observation_id: str


class KuroCoreStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        with self._connect() as conn:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Kuro Core database schema {version} is newer than supported {SCHEMA_VERSION}."
                )
            if version == 0:
                with conn:
                    conn.executescript(
                        """
                        CREATE TABLE observations (
                            observation_id TEXT PRIMARY KEY,
                            integration_id TEXT NOT NULL,
                            kind TEXT NOT NULL,
                            source_ref TEXT NOT NULL,
                            title TEXT NOT NULL,
                            summary TEXT NOT NULL,
                            observed_at TEXT,
                            received_at TEXT NOT NULL,
                            availability_status TEXT NOT NULL,
                            declared_freshness TEXT NOT NULL,
                            connection_status TEXT NOT NULL,
                            valid_until TEXT,
                            idempotency_key TEXT NOT NULL,
                            limitations_json TEXT NOT NULL,
                            details_json TEXT NOT NULL,
                            semantic_hash TEXT NOT NULL,
                            schema_version INTEGER NOT NULL,
                            created_at TEXT NOT NULL,
                            UNIQUE (integration_id, idempotency_key)
                        );

                        CREATE INDEX idx_observations_integration_received
                            ON observations (integration_id, received_at DESC);
                        CREATE INDEX idx_observations_kind_received
                            ON observations (kind, received_at DESC);

                        CREATE TABLE decision_traces (
                            trace_id TEXT PRIMARY KEY,
                            run_id TEXT NOT NULL,
                            decision_kind TEXT NOT NULL,
                            status TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            observation_ids_json TEXT NOT NULL,
                            selected_ids_json TEXT NOT NULL,
                            model_provider TEXT NOT NULL,
                            model_name TEXT NOT NULL,
                            policy_version TEXT NOT NULL,
                            config_digest TEXT NOT NULL,
                            output_summary TEXT NOT NULL,
                            duration_ms INTEGER,
                            metrics_json TEXT NOT NULL
                        );

                        CREATE INDEX idx_decision_traces_run_created
                            ON decision_traces (run_id, created_at DESC);
                        CREATE INDEX idx_decision_traces_kind_created
                            ON decision_traces (decision_kind, created_at DESC);
                        """
                    )
                    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            elif version != SCHEMA_VERSION:
                raise RuntimeError(f"Unsupported Kuro Core database schema: {version}")

    def schema_version(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("PRAGMA user_version").fetchone()[0])

    def ingest_observation(self, observation: Observation) -> IngestResult:
        record = self._observation_record(observation)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    """
                    SELECT observation_id, semantic_hash
                    FROM observations
                    WHERE integration_id = ? AND idempotency_key = ?
                    """,
                    (observation.integration_id, observation.idempotency_key),
                ).fetchone()
                if existing is not None:
                    if str(existing["semantic_hash"]) != observation.semantic_hash():
                        raise IdempotencyConflictError(
                            "Observation idempotency key was reused for different semantics: "
                            f"{observation.integration_id}/{observation.idempotency_key}"
                        )
                    conn.commit()
                    return IngestResult(
                        created=False,
                        observation_id=str(existing["observation_id"]),
                    )
                conn.execute(
                    """
                    INSERT INTO observations (
                        observation_id, integration_id, kind, source_ref, title, summary,
                        observed_at, received_at, availability_status, declared_freshness,
                        connection_status, valid_until, idempotency_key, limitations_json,
                        details_json, semantic_hash, schema_version, created_at
                    ) VALUES (
                        :observation_id, :integration_id, :kind, :source_ref, :title,
                        :summary, :observed_at, :received_at, :availability_status,
                        :declared_freshness, :connection_status, :valid_until,
                        :idempotency_key, :limitations_json, :details_json,
                        :semantic_hash, :schema_version, :created_at
                    )
                    """,
                    record,
                )
                conn.commit()
                return IngestResult(created=True, observation_id=observation.observation_id)
            except Exception:
                conn.rollback()
                raise

    def get_observation(self, observation_id: str) -> Observation | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
        return self._row_to_observation(row) if row is not None else None

    def list_observations(
        self,
        *,
        integration_id: str = "",
        limit: int = 100,
    ) -> list[Observation]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500.")
        sql = "SELECT * FROM observations"
        args: list[object] = []
        if integration_id:
            sql += " WHERE integration_id = ?"
            args.append(integration_id)
        sql += " ORDER BY received_at DESC, observation_id DESC LIMIT ?"
        args.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [self._row_to_observation(row) for row in rows]

    def append_decision_trace(self, trace: DecisionTrace) -> None:
        record = {
            "trace_id": trace.trace_id,
            "run_id": trace.run_id,
            "decision_kind": trace.decision_kind,
            "status": trace.status.value,
            "created_at": isoformat_utc(trace.created_at),
            "observation_ids_json": json.dumps(list(trace.observation_ids), separators=(",", ":")),
            "selected_ids_json": json.dumps(list(trace.selected_ids), separators=(",", ":")),
            "model_provider": trace.model_provider,
            "model_name": trace.model_name,
            "policy_version": trace.policy_version,
            "config_digest": trace.config_digest,
            "output_summary": trace.output_summary,
            "duration_ms": trace.duration_ms,
            "metrics_json": json.dumps(
                trace.metrics,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
        with self._connect() as conn, conn:
            conn.execute(
                """
                INSERT INTO decision_traces (
                    trace_id, run_id, decision_kind, status, created_at,
                    observation_ids_json, selected_ids_json, model_provider, model_name,
                    policy_version, config_digest, output_summary, duration_ms, metrics_json
                ) VALUES (
                    :trace_id, :run_id, :decision_kind, :status, :created_at,
                    :observation_ids_json, :selected_ids_json, :model_provider, :model_name,
                    :policy_version, :config_digest, :output_summary, :duration_ms, :metrics_json
                )
                """,
                record,
            )

    def list_decision_traces(self, *, run_id: str = "", limit: int = 100) -> list[DecisionTrace]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500.")
        sql = "SELECT * FROM decision_traces"
        args: list[object] = []
        if run_id:
            sql += " WHERE run_id = ?"
            args.append(run_id)
        sql += " ORDER BY created_at DESC, trace_id DESC LIMIT ?"
        args.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [self._row_to_decision_trace(row) for row in rows]

    def _observation_record(self, observation: Observation) -> dict[str, object]:
        return {
            "observation_id": observation.observation_id,
            "integration_id": observation.integration_id,
            "kind": observation.kind,
            "source_ref": observation.source_ref,
            "title": observation.title,
            "summary": observation.summary,
            "observed_at": isoformat_utc(observation.observed_at),
            "received_at": isoformat_utc(observation.received_at),
            "availability_status": observation.availability.value,
            "declared_freshness": observation.declared_freshness.value,
            "connection_status": observation.connection.value,
            "valid_until": isoformat_utc(observation.valid_until),
            "idempotency_key": observation.idempotency_key,
            "limitations_json": json.dumps(
                list(observation.limitations),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "details_json": json.dumps(
                observation.details,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "semantic_hash": observation.semantic_hash(),
            "schema_version": observation.schema_version,
            "created_at": isoformat_utc(utc_now()),
        }

    def _row_to_observation(self, row: sqlite3.Row) -> Observation:
        return Observation(
            observation_id=str(row["observation_id"]),
            integration_id=str(row["integration_id"]),
            kind=str(row["kind"]),
            source_ref=str(row["source_ref"]),
            title=str(row["title"]),
            summary=str(row["summary"]),
            observed_at=parse_datetime(row["observed_at"], field_name="observed_at"),
            received_at=parse_datetime(row["received_at"], field_name="received_at"),  # type: ignore[arg-type]
            availability=AvailabilityStatus(str(row["availability_status"])),
            declared_freshness=FreshnessStatus(str(row["declared_freshness"])),
            connection=ConnectionStatus(str(row["connection_status"])),
            valid_until=parse_datetime(row["valid_until"], field_name="valid_until"),
            idempotency_key=str(row["idempotency_key"]),
            limitations=tuple(json.loads(str(row["limitations_json"]))),
            details=json.loads(str(row["details_json"])),
            schema_version=int(row["schema_version"]),
        )

    def _row_to_decision_trace(self, row: sqlite3.Row) -> DecisionTrace:
        return DecisionTrace(
            trace_id=str(row["trace_id"]),
            run_id=str(row["run_id"]),
            decision_kind=str(row["decision_kind"]),
            status=DecisionTraceStatus(str(row["status"])),
            created_at=parse_datetime(row["created_at"], field_name="created_at"),  # type: ignore[arg-type]
            observation_ids=tuple(json.loads(str(row["observation_ids_json"]))),
            selected_ids=tuple(json.loads(str(row["selected_ids_json"]))),
            model_provider=str(row["model_provider"]),
            model_name=str(row["model_name"]),
            policy_version=str(row["policy_version"]),
            config_digest=str(row["config_digest"]),
            output_summary=str(row["output_summary"]),
            duration_ms=int(row["duration_ms"]) if row["duration_ms"] is not None else None,
            metrics=json.loads(str(row["metrics_json"])),
        )
