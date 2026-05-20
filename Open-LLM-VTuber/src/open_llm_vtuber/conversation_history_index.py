from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from .character_memory_repository import CharacterMemoryRepository
from .character_memory_retriever import clean_text, estimate_tokens, keyword_terms
from .chat_history_manager import get_history, get_history_list


@dataclass(frozen=True)
class ConversationSearchHit:
    conf_uid: str
    history_uid: str
    message_index: int
    role: str
    timestamp: str
    title: str
    content: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "conf_uid": self.conf_uid,
            "history_uid": self.history_uid,
            "message_index": self.message_index,
            "role": self.role,
            "timestamp": self.timestamp,
            "title": self.title,
            "content": self.content,
            "score": self.score,
        }


class ConversationHistoryIndex:
    """SQLite FTS sidecar for cross-conversation raw history lookup."""

    def __init__(
        self,
        db_path: Path | None = None,
        *,
        repository: CharacterMemoryRepository | None = None,
    ) -> None:
        self._repository = repository or CharacterMemoryRepository()
        self._db_path = db_path
        self._fts_available_by_path: dict[Path, bool] = {}

    def db_path(self) -> Path:
        if self._db_path is not None:
            return self._db_path
        return self._repository.root() / "conversation_history.sqlite3"

    def search(
        self,
        conf_uid: str,
        query_text: str,
        *,
        exclude_history_uid: str = "",
        include_current_history: bool = False,
        max_snippets: int = 5,
        token_budget: int = 700,
    ) -> list[ConversationSearchHit]:
        conf_uid = (conf_uid or "").strip()
        query_text = clean_text(query_text, max_len=600)
        if not conf_uid or not query_text:
            return []

        self.sync(conf_uid)
        scores = self._query_scores(conf_uid, query_text)
        if not scores:
            return []

        rows = self._load_hit_rows(
            conf_uid,
            scores,
            exclude_history_uid=exclude_history_uid,
            include_current_history=include_current_history,
        )
        hits = [
            ConversationSearchHit(
                conf_uid=str(row["conf_uid"]),
                history_uid=str(row["history_uid"]),
                message_index=int(row["message_index"]),
                role=str(row["role"] or ""),
                timestamp=str(row["timestamp"] or ""),
                title=str(row["title"] or ""),
                content=str(row["content"] or ""),
                score=float(scores.get(str(row["message_id"]), 0.0)),
            )
            for row in rows
        ]
        hits.sort(key=lambda hit: (hit.score, hit.timestamp), reverse=True)
        return self._pack_hits(
            hits,
            max_snippets=max(0, int(max_snippets or 0)),
            token_budget=max(120, int(token_budget or 700)),
        )

    def sync(self, conf_uid: str) -> None:
        conf_uid = (conf_uid or "").strip()
        if not conf_uid:
            return

        rows: list[dict[str, Any]] = []
        for history in get_history_list(conf_uid):
            history_uid = str(history.get("uid") or "").strip()
            if not history_uid:
                continue
            title = clean_text(
                str(history.get("title") or history.get("summary_short") or ""),
                max_len=120,
            )
            updated_at = str(history.get("updated_at") or history.get("timestamp") or "")
            messages = get_history(conf_uid, history_uid)
            for index, message in enumerate(messages):
                if not isinstance(message, dict):
                    continue
                role = str(message.get("role") or "").strip()
                content = clean_text(str(message.get("content") or ""), max_len=1200)
                if not content:
                    continue
                rows.append(
                    {
                        "message_id": self._message_id(conf_uid, history_uid, index, message),
                        "conf_uid": conf_uid,
                        "history_uid": history_uid,
                        "message_index": index,
                        "role": role,
                        "timestamp": str(message.get("timestamp") or ""),
                        "title": title,
                        "content": content,
                        "updated_at": updated_at,
                        "message_json": json.dumps(
                            message,
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    }
                )

        message_ids = [row["message_id"] for row in rows]
        with closing(self._connect()) as conn:
            self._ensure_schema(conn)
            with conn:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO conversation_messages (
                        message_id, conf_uid, history_uid, message_index, role,
                        timestamp, title, content, updated_at, message_json
                    ) VALUES (
                        :message_id, :conf_uid, :history_uid, :message_index, :role,
                        :timestamp, :title, :content, :updated_at, :message_json
                    )
                    """,
                    rows,
                )
                self._delete_stale_rows(conn, conf_uid, message_ids)
                if self._fts_available():
                    self._sync_fts_rows(conn, conf_uid, rows)

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
            CREATE TABLE IF NOT EXISTS conversation_messages (
                message_id TEXT PRIMARY KEY,
                conf_uid TEXT NOT NULL,
                history_uid TEXT NOT NULL,
                message_index INTEGER NOT NULL DEFAULT 0,
                role TEXT NOT NULL DEFAULT '',
                timestamp TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT '',
                message_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_conversation_messages_conf_history
                ON conversation_messages(conf_uid, history_uid);
            CREATE INDEX IF NOT EXISTS idx_conversation_messages_timestamp
                ON conversation_messages(conf_uid, timestamp);
            """
        )
        self._fts_available_by_path[db_path] = self._ensure_fts_schema(conn)

    def _ensure_fts_schema(self, conn: sqlite3.Connection) -> bool:
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS conversation_messages_fts USING fts5(
                    message_id UNINDEXED,
                    conf_uid UNINDEXED,
                    history_uid UNINDEXED,
                    role,
                    title,
                    content,
                    tokenize='unicode61'
                )
                """
            )
        except sqlite3.OperationalError as exc:
            logger.warning(f"SQLite FTS5 is unavailable for conversation history: {exc}")
            return False
        return True

    def _fts_available(self) -> bool:
        return self._fts_available_by_path.get(self.db_path().resolve(), False)

    def _delete_stale_rows(
        self,
        conn: sqlite3.Connection,
        conf_uid: str,
        message_ids: list[str],
    ) -> None:
        if message_ids:
            placeholders = ",".join("?" for _ in message_ids)
            conn.execute(
                f"""
                DELETE FROM conversation_messages
                WHERE conf_uid = ? AND message_id NOT IN ({placeholders})
                """,
                [conf_uid, *message_ids],
            )
        else:
            conn.execute("DELETE FROM conversation_messages WHERE conf_uid = ?", (conf_uid,))

    def _sync_fts_rows(
        self,
        conn: sqlite3.Connection,
        conf_uid: str,
        rows: list[dict[str, Any]],
    ) -> None:
        conn.execute("DELETE FROM conversation_messages_fts WHERE conf_uid = ?", (conf_uid,))
        conn.executemany(
            """
            INSERT INTO conversation_messages_fts (
                message_id, conf_uid, history_uid, role, title, content
            ) VALUES (
                :message_id, :conf_uid, :history_uid, :role, :title, :content
            )
            """,
            rows,
        )

    def _query_scores(self, conf_uid: str, query_text: str) -> dict[str, float]:
        fts_query = self._build_fts_query(query_text)
        scores: dict[str, float] = {}

        with closing(self._connect()) as conn:
            self._ensure_schema(conn)
            if self._fts_available() and fts_query:
                try:
                    for row in conn.execute(
                        """
                        SELECT message_id, bm25(conversation_messages_fts) AS rank
                        FROM conversation_messages_fts
                        WHERE conf_uid = ? AND conversation_messages_fts MATCH ?
                        LIMIT 120
                        """,
                        (conf_uid, fts_query),
                    ):
                        message_id = str(row["message_id"])
                        rank = float(row["rank"] or 0.0)
                        scores[message_id] = max(scores.get(message_id, 0.0), 30.0 - rank)
                except sqlite3.OperationalError as exc:
                    logger.warning(f"Conversation history FTS query failed: {exc}")

            for term in list(keyword_terms(query_text))[:10]:
                pattern = f"%{term}%"
                for row in conn.execute(
                    """
                    SELECT message_id
                    FROM conversation_messages
                    WHERE conf_uid = ?
                      AND (content LIKE ? OR title LIKE ? OR role LIKE ?)
                    LIMIT 120
                    """,
                    (conf_uid, pattern, pattern, pattern),
                ):
                    message_id = str(row["message_id"])
                    scores[message_id] = scores.get(message_id, 0.0) + 4.0

        return scores

    def _load_hit_rows(
        self,
        conf_uid: str,
        scores: dict[str, float],
        *,
        exclude_history_uid: str,
        include_current_history: bool,
    ) -> list[sqlite3.Row]:
        if not scores:
            return []

        message_ids = list(scores.keys())
        placeholders = ",".join("?" for _ in message_ids)
        params: list[Any] = [conf_uid, *message_ids]
        exclude_clause = ""
        if exclude_history_uid and not include_current_history:
            exclude_clause = " AND history_uid != ?"
            params.append(exclude_history_uid)

        with closing(self._connect()) as conn:
            self._ensure_schema(conn)
            return list(
                conn.execute(
                    f"""
                    SELECT message_id, conf_uid, history_uid, message_index, role,
                           timestamp, title, content
                    FROM conversation_messages
                    WHERE conf_uid = ?
                      AND message_id IN ({placeholders})
                      {exclude_clause}
                    """,
                    params,
                )
            )

    def _pack_hits(
        self,
        hits: list[ConversationSearchHit],
        *,
        max_snippets: int,
        token_budget: int,
    ) -> list[ConversationSearchHit]:
        selected: list[ConversationSearchHit] = []
        used_tokens = 0
        for hit in hits:
            if len(selected) >= max_snippets:
                break
            content = clean_text(hit.content, max_len=360)
            if not content:
                continue
            estimated = estimate_tokens(content) + 16
            if selected and used_tokens + estimated > token_budget:
                continue
            selected.append(
                ConversationSearchHit(
                    conf_uid=hit.conf_uid,
                    history_uid=hit.history_uid,
                    message_index=hit.message_index,
                    role=hit.role,
                    timestamp=hit.timestamp,
                    title=hit.title,
                    content=content,
                    score=hit.score,
                )
            )
            used_tokens += estimated
            if used_tokens >= token_budget:
                break
        return selected

    def _message_id(
        self,
        conf_uid: str,
        history_uid: str,
        index: int,
        message: dict[str, Any],
    ) -> str:
        raw = "|".join(
            [
                conf_uid,
                history_uid,
                str(index),
                str(message.get("timestamp") or ""),
                str(message.get("role") or ""),
                str(message.get("content") or ""),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _build_fts_query(self, query_text: str) -> str:
        terms = list(keyword_terms(query_text))
        if not terms:
            return ""
        quoted_terms = [f'"{term.replace(chr(34), chr(34) + chr(34))}"' for term in terms[:12]]
        return " OR ".join(quoted_terms)


_CONVERSATION_HISTORY_INDEX = ConversationHistoryIndex()


def search_past_conversations(
    conf_uid: str,
    query_text: str,
    *,
    exclude_history_uid: str = "",
    include_current_history: bool = False,
    max_snippets: int = 5,
    token_budget: int = 700,
) -> list[dict[str, Any]]:
    hits = _CONVERSATION_HISTORY_INDEX.search(
        conf_uid,
        query_text,
        exclude_history_uid=exclude_history_uid,
        include_current_history=include_current_history,
        max_snippets=max_snippets,
        token_budget=token_budget,
    )
    return [hit.to_dict() for hit in hits]


def format_past_conversations_for_prompt(
    conf_uid: str,
    query_text: str,
    *,
    current_history_uid: str = "",
    max_snippets: int = 4,
    token_budget: int = 520,
) -> str:
    hits = _CONVERSATION_HISTORY_INDEX.search(
        conf_uid,
        query_text,
        exclude_history_uid=current_history_uid,
        include_current_history=False,
        max_snippets=max_snippets,
        token_budget=token_budget,
    )
    if not hits:
        return ""

    lines = [
        "Past conversation snippets relevant to this turn:",
        "- These are raw snippets from other chat histories, not confirmed long-term facts.",
        "- Use them as source-grounded context; prefer long-term memory for stable preferences.",
    ]
    for hit in hits:
        source = f"history={hit.history_uid}"
        if hit.timestamp:
            source += f" time={hit.timestamp}"
        if hit.title:
            source += f" title={hit.title}"
        lines.append(
            f"- [{source}] {hit.role}: {clean_text(hit.content, max_len=260)}"
        )
    return "\n".join(lines).strip()
