from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from loguru import logger

from .character_memory_repository import CharacterMemoryRepository
from .character_memory_retriever import (
    KeywordMemoryIndex,
    MemorySearchHit,
    clean_text,
    entry_scope_level,
    entry_status,
    keyword_terms,
)


class SQLiteMemoryIndex:
    """SQLite-backed memory index with an FTS5 fast path.

    The JSON store remains the source of truth for now. This index is a
    rebuildable sidecar that gives retrieval a real SQL boundary and prepares
    the system for a future database-backed repository.
    """

    def __init__(
        self,
        db_path: Path | None = None,
        *,
        repository: CharacterMemoryRepository | None = None,
        fallback_index: KeywordMemoryIndex | None = None,
    ) -> None:
        self._repository = repository or CharacterMemoryRepository()
        self._db_path = db_path
        self._fallback_index = fallback_index or KeywordMemoryIndex()
        self._fts_available_by_path: dict[Path, bool] = {}

    def search(
        self,
        entries: list[dict[str, Any]],
        plan: Any,
        *,
        namespace: str = "",
    ) -> list[MemorySearchHit]:
        if not entries:
            return []

        sql_scores: dict[str, float] = {}
        try:
            self._sync_entries(namespace, entries)
            sql_scores = self._query_scores(namespace, entries, plan)
        except Exception as exc:
            logger.warning(f"SQLite memory index unavailable; using keyword index: {exc}")

        hits = self._fallback_index.search(entries, plan, namespace=namespace)
        if not sql_scores:
            return hits

        merged_hits: list[MemorySearchHit] = []
        for hit in hits:
            entry_id = self._entry_id(hit.entry)
            sql_score = sql_scores.get(entry_id, 0.0)
            reasons = hit.reasons
            if sql_score:
                reasons = (*reasons, "sqlite_fts")
            merged_hits.append(
                MemorySearchHit(
                    entry=hit.entry,
                    score=hit.score + sql_score,
                    reasons=reasons,
                )
            )
        merged_hits.sort(
            key=lambda hit: (
                hit.score,
                str(hit.entry.get("updated_at") or ""),
            ),
            reverse=True,
        )
        return merged_hits

    def db_path(self) -> Path:
        if self._db_path is not None:
            return self._db_path
        return self._repository.root() / "character_memory.sqlite3"

    def _connect(self) -> sqlite3.Connection:
        path = self.db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        db_path = self.db_path().resolve()
        if db_path in self._fts_available_by_path:
            return

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memory_entries (
                entry_id TEXT PRIMARY KEY,
                conf_uid TEXT NOT NULL,
                scope_level TEXT NOT NULL,
                scope_id TEXT NOT NULL DEFAULT '',
                memory_type TEXT NOT NULL DEFAULT 'fact',
                status TEXT NOT NULL DEFAULT 'active',
                enabled INTEGER NOT NULL DEFAULT 1,
                subject TEXT NOT NULL DEFAULT '',
                key TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0,
                importance REAL NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                entry_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_memory_entries_conf_status
                ON memory_entries(conf_uid, status, enabled);
            CREATE INDEX IF NOT EXISTS idx_memory_entries_scope_type
                ON memory_entries(conf_uid, scope_level, memory_type);
            """
        )

        self._fts_available_by_path[db_path] = self._ensure_fts_schema(conn)

    def _fts_available(self) -> bool:
        return self._fts_available_by_path.get(self.db_path().resolve(), False)

    def _ensure_fts_schema(self, conn: sqlite3.Connection) -> bool:
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_entries_fts USING fts5(
                    entry_id UNINDEXED,
                    conf_uid UNINDEXED,
                    scope_level,
                    memory_type,
                    subject,
                    key,
                    content,
                    tokenize='unicode61'
                )
                """
            )
        except sqlite3.OperationalError as exc:
            logger.warning(f"SQLite FTS5 is unavailable for character memory: {exc}")
            return False
        return True

    def _sync_entries(self, namespace: str, entries: list[dict[str, Any]]) -> None:
        namespace = self._namespace(namespace, entries)
        if not namespace:
            return

        rows = [self._entry_row(namespace, entry) for entry in entries]
        entry_ids = [row["entry_id"] for row in rows]

        with closing(self._connect()) as conn:
            self._ensure_schema(conn)
            with conn:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO memory_entries (
                        entry_id, conf_uid, scope_level, scope_id, memory_type, status,
                        enabled, subject, key, content, confidence, importance, source,
                        updated_at, entry_json
                    ) VALUES (
                        :entry_id, :conf_uid, :scope_level, :scope_id, :memory_type,
                        :status, :enabled, :subject, :key, :content, :confidence,
                        :importance, :source, :updated_at, :entry_json
                    )
                    """,
                    rows,
                )
                self._delete_stale_rows(conn, namespace, entry_ids)
                if self._fts_available():
                    self._sync_fts_rows(conn, namespace, rows)

    def _delete_stale_rows(
        self,
        conn: sqlite3.Connection,
        namespace: str,
        entry_ids: list[str],
    ) -> None:
        if entry_ids:
            placeholders = ",".join("?" for _ in entry_ids)
            conn.execute(
                f"""
                DELETE FROM memory_entries
                WHERE conf_uid = ? AND entry_id NOT IN ({placeholders})
                """,
                [namespace, *entry_ids],
            )
        else:
            conn.execute("DELETE FROM memory_entries WHERE conf_uid = ?", (namespace,))

    def _sync_fts_rows(
        self,
        conn: sqlite3.Connection,
        namespace: str,
        rows: list[dict[str, Any]],
    ) -> None:
        conn.execute("DELETE FROM memory_entries_fts WHERE conf_uid = ?", (namespace,))
        conn.executemany(
            """
            INSERT INTO memory_entries_fts (
                entry_id, conf_uid, scope_level, memory_type, subject, key, content
            ) VALUES (
                :entry_id, :conf_uid, :scope_level, :memory_type, :subject, :key,
                :content
            )
            """,
            rows,
        )

    def _query_scores(
        self,
        namespace: str,
        entries: list[dict[str, Any]],
        plan: Any,
    ) -> dict[str, float]:
        namespace = self._namespace(namespace, entries)
        if not namespace:
            return {}

        query_text = str(getattr(plan, "query_text", "") or "")
        fts_query = self._build_fts_query(query_text)
        entry_ids = {self._entry_id(entry) for entry in entries}
        scores: dict[str, float] = {}

        with closing(self._connect()) as conn:
            self._ensure_schema(conn)
            if self._fts_available() and fts_query:
                for row in conn.execute(
                    """
                    SELECT entry_id, bm25(memory_entries_fts) AS rank
                    FROM memory_entries_fts
                    WHERE conf_uid = ? AND memory_entries_fts MATCH ?
                    LIMIT 80
                    """,
                    (namespace, fts_query),
                ):
                    entry_id = str(row["entry_id"])
                    if entry_id not in entry_ids:
                        continue
                    rank = float(row["rank"] or 0.0)
                    scores[entry_id] = max(scores.get(entry_id, 0.0), 28.0 - rank)

            like_terms = list(keyword_terms(query_text))[:8]
            for term in like_terms:
                pattern = f"%{term}%"
                for row in conn.execute(
                    """
                    SELECT entry_id
                    FROM memory_entries
                    WHERE conf_uid = ?
                      AND (
                        content LIKE ?
                        OR subject LIKE ?
                        OR key LIKE ?
                        OR memory_type LIKE ?
                      )
                    LIMIT 80
                    """,
                    (namespace, pattern, pattern, pattern, pattern),
                ):
                    entry_id = str(row["entry_id"])
                    if entry_id in entry_ids:
                        scores[entry_id] = scores.get(entry_id, 0.0) + 4.0

        return scores

    def _entry_row(self, namespace: str, entry: dict[str, Any]) -> dict[str, Any]:
        content = clean_text(str(entry.get("content") or ""), max_len=500)
        return {
            "entry_id": self._entry_id(entry),
            "conf_uid": namespace,
            "scope_level": entry_scope_level(entry),
            "scope_id": str(entry.get("scope_id") or ""),
            "memory_type": str(entry.get("memory_type") or "fact"),
            "status": entry_status(entry),
            "enabled": 1 if entry.get("enabled", True) else 0,
            "subject": str(entry.get("subject") or ""),
            "key": str(entry.get("key") or ""),
            "content": content,
            "confidence": float(entry.get("confidence") or 0),
            "importance": float(entry.get("importance") or 0),
            "source": str(entry.get("source") or ""),
            "updated_at": str(entry.get("updated_at") or ""),
            "entry_json": json.dumps(entry, ensure_ascii=False, sort_keys=True),
        }

    def _entry_id(self, entry: dict[str, Any]) -> str:
        entry_id = str(entry.get("id") or "").strip()
        if entry_id:
            return entry_id
        fingerprint = "|".join(
            [
                str(entry.get("scope_id") or ""),
                str(entry.get("memory_type") or ""),
                str(entry.get("subject") or ""),
                str(entry.get("key") or ""),
                str(entry.get("content") or ""),
            ]
        )
        return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()

    def _namespace(self, namespace: str, entries: list[dict[str, Any]]) -> str:
        namespace = (namespace or "").strip()
        if namespace:
            return namespace
        for entry in entries:
            scope_id = str(entry.get("scope_id") or "").strip()
            if scope_id:
                return scope_id
        return ""

    def _build_fts_query(self, query_text: str) -> str:
        terms = list(keyword_terms(query_text))
        if not terms:
            return ""
        quoted_terms = [f'"{term.replace(chr(34), chr(34) + chr(34))}"' for term in terms[:12]]
        return " OR ".join(quoted_terms)
