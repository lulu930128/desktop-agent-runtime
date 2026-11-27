from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from itertools import chain
from .memory_episode import episode_messages
from .memory_semantics import local_encoder, vector_schema, put_vector, remove_vector, vector_hits

from loguru import logger

from .character_memory_repository import CharacterMemoryRepository
from .character_memory_retriever import clean_text, estimate_tokens, keyword_terms, query_terms, query_cutoff, suppressed_turn_ids
from .chat_history_manager import _get_safe_history_path
from .character_memory_repository import store_lock


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
    turn_id: str = ""
    source_span: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "conf_uid": self.conf_uid,
            "history_uid": self.history_uid,
            "message_index": self.message_index,
            "role": self.role,
            "timestamp": self.timestamp,
            "title": self.title,
            "content": self.content,
            "score": self.score, "turn_id": self.turn_id, "source_span": list(self.source_span),
        }


class ConversationHistoryIndex:
    """SQLite FTS sidecar for cross-conversation raw history lookup."""

    def __init__(
        self,
        db_path: Path | None = None,
        *,
        repository: CharacterMemoryRepository | None = None,
    ) -> None:
        self.retrieval_mode = "hybrid"
        self._repository = repository or CharacterMemoryRepository()
        self._db_path = db_path
        self._ready: dict[tuple[Path, Path, str], str] = {}
        self._schema_file_ids = {}
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
        project_id: str = "", current_turn_id: str = "",
        max_snippets: int = 5,
        token_budget: int = 700,
    ) -> list[ConversationSearchHit]:
        conf_uid = (conf_uid or "").strip()
        query_text = clean_text(query_text, max_len=600)
        if not conf_uid or not query_text:
            return []

        directory = self._directory(conf_uid)
        key = (self.db_path().resolve(), directory, conf_uid)
        if not self.db_path().is_file() or self._schema_file_ids.get(key[0]) != key[0].stat().st_ino:
            self._fts_available_by_path.pop(self.db_path().resolve(), None)
            self._ready.pop(key,None)
        encoder = local_encoder()
        if self._ready.get(key) != (encoder.revision if encoder else "lexical"):
            self.sync(conf_uid)
        else:
            pending = directory / ".index-pending"
            for marker in pending.glob("*.json"):
                self._refresh_or_quarantine(conf_uid, directory / marker.name, marker)
        from .character_memory_manager import suppressed_sources
        blocked = suppressed_sources(conf_uid, project_id)
        scores = self._query_scores(conf_uid, query_text, exclude_history_uid if not include_current_history else "", project_id, current_turn_id, blocked)
        if not scores:
            return []

        rows = self._load_hit_rows(conf_uid,scores,exclude_history_uid=exclude_history_uid,
                                   include_current_history=include_current_history)
        # Resolve a reference explicitly present in the best eligible source. A second
        # lookup uses the same scope, time and suppression predicates as the first.
        if rows and re.search(r"how much|which|where|cost|price|金額|多少|どれ|いくら", query_text,re.I):
            anchor = max(rows,key=lambda row:scores[row["message_id"]])
            references = [code for code in re.findall(r"\b(?=[A-Z0-9-]*[A-Z])(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{2,}\b",anchor["content"])
                          if code.casefold() not in query_text.casefold()]
            if references:
                cutoff = query_cutoff(query_text)
                lookup = " ".join(dict.fromkeys(references)) + (" as of " + cutoff if cutoff else "")
                linked = self._query_scores(conf_uid,lookup,exclude_history_uid if not include_current_history else "",
                                            project_id,current_turn_id,blocked)
                joined = self._load_hit_rows(conf_uid,linked,exclude_history_uid=exclude_history_uid,
                                             include_current_history=include_current_history)
                known = set(scores)
                for row in joined:
                    identity = row["message_id"]
                    if (row["history_uid"] != anchor["history_uid"] and
                            any(code in row["content"] for code in references)):
                        scores[identity] = max(scores.get(identity,0), scores[anchor["message_id"]]*0.99)
                        if identity not in known:
                            rows.append(row)
        hits = [
            ConversationSearchHit(
                conf_uid=str(row["conf_uid"]),
                history_uid=str(row["history_uid"]),
                message_index=int(row["message_index"]),
                role=str(row["role"] or ""),
                turn_id=str(row["turn_id"] or ""),
                source_span=tuple(json.loads(row["span"] or "[]")),
                timestamp=str(row["timestamp"] or ""),
                title="" if blocked or project_id else str(row["title"] or ""),
                content=str(row["content"] or ""),
                score=float(scores.get(str(row["message_id"]), 0.0)),
            )
            for row in rows
        ]
        # A bare assistant reply can refer to another subject ("previous code").
        # When its complete, eligible source pair was retrieved, carry that grounding.
        from dataclasses import replace
        pairs = {(hit.history_uid,hit.turn_id):hit for hit in hits if hit.role=="episode" and hit.turn_id}
        def grounded(hit):
            pair=pairs.get((hit.history_uid,hit.turn_id))
            if pair and hit.role in {"ai","assistant"}:
                return replace(pair,score=max(hit.score,pair.score))
            return hit
        hits = [grounded(hit) for hit in hits]
        hits.sort(key=lambda hit: (hit.score, hit.timestamp), reverse=True)
        return self._pack_hits(
            hits,
            max_snippets=max(0, int(max_snippets or 0)),
            token_budget=max(120, int(token_budget or 700)),
            query_text=query_text,
        )

    def _directory(self, conf_uid):
        return Path(_get_safe_history_path(conf_uid, "probe")).resolve().parent

    def sync(self, conf_uid: str) -> None:
        """Cold reconcile and explicit repair. Each source commits independently."""
        directory = self._directory(conf_uid)
        paths = set(directory.glob("*.json"))
        with closing(self._connect()) as conn:
            self._ensure_schema(conn)
            known = conn.execute("SELECT history_uid FROM history_sources WHERE conf_uid=?", (conf_uid,))
            paths.update(directory / (row[0] + ".json") for row in known)
        for path in sorted(paths):
            self._refresh_or_quarantine(conf_uid, path, directory / ".index-pending" / path.name)
        encoder = local_encoder()
        self._ready[(self.db_path().resolve(), directory, conf_uid)] = encoder.revision if encoder else "lexical"

    def _refresh_or_quarantine(self, conf_uid, path, marker):
        try:
            self._refresh(conf_uid,path,marker)
        except (OSError,ValueError,TypeError) as exc:
            logger.warning("History source excluded pending repair ({})",type(exc).__name__)
            with closing(self._connect()) as conn, conn:
                conn.execute("INSERT OR REPLACE INTO history_failures VALUES(?,?,?)",
                             (conf_uid,path.stem,type(exc).__name__))

    def _refresh(self, conf_uid, path, marker):
        # Commit the watermark with the rows; a crash before clearing intent is replayable.
        if not path.parent.exists():
            with closing(self._connect()) as conn, conn:
                self._replace_source(conn, conf_uid, path.stem, [], "", "")
            return
        with store_lock(path), closing(self._connect()) as conn, conn:
            self._ensure_schema(conn)
            history_uid = path.stem
            row = conn.execute("SELECT revision FROM history_sources WHERE conf_uid=? AND history_uid=?",
                               (conf_uid, history_uid)).fetchone()
            if path.exists():
                info = path.stat()
                encoder = local_encoder()
                revision = f"episode-v2:{info.st_ino}:{info.st_mtime_ns}:{info.st_size}:{encoder.revision if encoder else 0}"
                if row and revision == row[0] and not marker.exists() and not conn.execute(
                        "SELECT 1 FROM history_failures WHERE conf_uid=? AND history_uid=?", (conf_uid,history_uid)).fetchone():
                    return
                messages = json.loads(path.read_bytes())
                if not isinstance(messages, list) or not all(isinstance(m, dict) for m in messages):
                    raise ValueError("Invalid History source; repair required")
                metadata = next((m for m in messages if m.get("role") == "metadata"), {})
                messages = [m for m in messages if m.get("role") != "metadata"]
                title = str(metadata.get("title") or "")
            else:
                revision, messages, title = "", [], ""
            self._replace_source(conn, conf_uid, history_uid, messages, title, revision,
                                 legacy=bool(revision and metadata.get("companion_legacy_episodes") is True))
            conn.execute("DELETE FROM history_failures WHERE conf_uid=? AND history_uid=?", (conf_uid,history_uid))
            conn.commit()
            marker.unlink(missing_ok=True)

    def record_append(self, conf_uid, history_uid, previous_stat, path, messages, title, previous_title):
        """Fast path called inside the History owner's lock after atomic publication."""
        if not previous_stat or not self.db_path().exists() or title != previous_title:
            return
        encoder = local_encoder()
        version = encoder.revision if encoder else 0
        def stamp(stat):
            return f"episode-v2:{stat.st_ino}:{stat.st_mtime_ns}:{stat.st_size}:{version}"
        with closing(self._connect()) as conn, conn:
            self._ensure_schema(conn)
            known = conn.execute("SELECT revision FROM history_sources WHERE conf_uid=? AND history_uid=?",
                                 (conf_uid,history_uid)).fetchone()
            if not known or known[0] != stamp(previous_stat):
                return
            last = len(messages)-1
            rows = [(last,messages[-1])]
            if last and messages[-1].get("completion") == "complete":
                base = max(0,last-3)
                for offset, episode in episode_messages(messages[base:]):
                    if offset == last-base:
                        episode["source_span"] = [base+i for i in episode["source_span"]]
                        rows.append((last,episode))
            self._replace_source(conn,conf_uid,history_uid,[],title,stamp(path.stat()),append=rows)
            conn.commit()
            (path.parent / ".index-pending" / path.name).unlink(missing_ok=True)

    def _replace_source(self, conn, conf_uid, history_uid, messages, title, revision, *, legacy=False, append=None):
        previous = {} if append else {row["message_id"]: row for row in conn.execute(
            "SELECT rowid, message_id, title, message_json FROM conversation_messages WHERE conf_uid=? AND history_uid=?",
            (conf_uid, history_uid))}
        encoder = local_encoder()
        to_encode=[]
        def flush_vectors():
            if to_encode:
                vectors = encoder.encode([content for _,content in to_encode])
                for (identity,_),vector in zip(to_encode,vectors):
                    put_vector(conn,conf_uid,identity,encoder,vector)
                to_encode.clear()
        for index, message in (append or chain(enumerate(messages), episode_messages(messages, legacy=legacy))):
            content = message.get("content")
            role = message.get("role")
            if not isinstance(content, str) or not content.strip() or role not in {"human","ai","user","assistant","episode"}:
                continue
            if message.get("completion") == "interrupted":
                continue
            identity = self._message_id(conf_uid, history_uid, index, message)
            old = previous.pop(identity, None)
            payload = json.dumps(message, ensure_ascii=False, sort_keys=True)
            if old and old["title"] == title and old["message_json"] == payload:
                if role != "episode" or not encoder or conn.execute(
                    "SELECT 1 FROM semantic_vectors WHERE owner=? AND id=? AND revision=?",
                    (conf_uid,identity,encoder.revision)).fetchone():
                    continue
            if old:
                self._remove(conn, conf_uid, identity, old["rowid"])
            timestamp = str(message.get("timestamp") or "")
            rowid = conn.execute(
                "INSERT INTO conversation_messages(message_id, conf_uid, history_uid, message_index, role,"
                "timestamp,title,content,updated_at,message_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (identity, conf_uid, history_uid, index, role, timestamp, title, content, timestamp, payload)
            ).lastrowid
            if role == "episode" and encoder:
                to_encode.append((identity,content))
                if len(to_encode)==8:  # measured CPU batch size; all rows are processed
                    flush_vectors()
            if self._fts_available():
                terms = " ".join(sorted(keyword_terms(content)))
                conn.execute("INSERT INTO conversation_messages_fts(rowid,message_id,conf_uid,history_uid,role,title,content)"
                             " VALUES(?,?,?,?,?,?,?)", (rowid, identity, conf_uid, history_uid, role, "", terms))
        flush_vectors()
        for identity,row in previous.items():
            self._remove(conn, conf_uid, identity, row["rowid"])
        if revision:
            conn.execute("INSERT OR REPLACE INTO history_sources VALUES(?,?,?)", (conf_uid,history_uid,revision))
        else:
            conn.execute("DELETE FROM history_sources WHERE conf_uid=? AND history_uid=?", (conf_uid,history_uid))

    def _remove(self, conn, owner, identity, rowid):
        remove_vector(conn, owner, identity)
        if self._fts_available():
            conn.execute("DELETE FROM conversation_messages_fts WHERE rowid=?", (rowid,))
        conn.execute("DELETE FROM conversation_messages WHERE rowid=?", (rowid,))

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
        inode = db_path.stat().st_ino
        if db_path in self._fts_available_by_path and self._schema_file_ids.get(db_path)==inode:
            return

        with conn:
            conn.execute("BEGIN IMMEDIATE")
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='history_sources'").fetchone():
                conn.execute("DROP TABLE IF EXISTS conversation_messages_fts")
                conn.execute("DROP TABLE IF EXISTS conversation_messages")
                conn.execute("CREATE TABLE history_sources(conf_uid TEXT,history_uid TEXT,revision TEXT,"
                             "PRIMARY KEY(conf_uid,history_uid))")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS history_failures(conf_uid TEXT,history_uid TEXT,reason TEXT,PRIMARY KEY(conf_uid,history_uid));
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_history_turn ON conversation_messages(conf_uid,json_extract(message_json,'$.turn_id'))")
        vector_schema(conn)
        self._schema_file_ids[db_path] = inode
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

    def _query_scores(self, conf_uid: str, query_text: str, excluded: str, project: str, current_turn: str, blocked: set) -> dict[str, float]:
        fts_query = self._build_fts_query(query_text)
        scores: dict[str, float] = {}

        with closing(self._connect()) as conn:
            self._ensure_schema(conn)
            # Source span/scope predicates precede ranking and LIMIT.
            blocked_turns = suppressed_turn_ids(blocked)
            def eligible_turn(turn, linked):
                if turn in blocked_turns or current_turn and turn==current_turn:
                    return 0
                linked_turns = json.loads(linked) if linked else ()
                return int(current_turn not in linked_turns and blocked_turns.isdisjoint(linked_turns))
            conn.create_function("can_recall", 2, eligible_turn)
            eligible = """m.conf_uid=? AND m.history_uid!=?
              AND NOT EXISTS(SELECT 1 FROM history_failures f WHERE f.conf_uid=m.conf_uid AND f.history_uid=m.history_uid)
              AND COALESCE(json_extract(m.message_json,'$.project_id'),'') IN ('',?)
              """
            if blocked_turns or current_turn:
                eligible += " AND can_recall(json_extract(m.message_json,'$.turn_id'),json_extract(m.message_json,'$.source_turns'))"
            params = (conf_uid,excluded,project)
            cutoff = query_cutoff(query_text)
            if cutoff:
                eligible += " AND date(substr(m.timestamp,1,10)) <= ?"
                params += (cutoff,)
            if self._fts_available():
                if fts_query and self.retrieval_mode != "vector":
                    for row in conn.execute(f"""
                        SELECT m.message_id,bm25(conversation_messages_fts) AS rank
                        FROM conversation_messages_fts JOIN conversation_messages m
                          ON m.rowid=conversation_messages_fts.rowid
                        WHERE {eligible} AND conversation_messages_fts MATCH ?
                        ORDER BY rank,m.message_id LIMIT 120""", (*params,fts_query)):
                        scores[row["message_id"]] = 1.0 - row["rank"]
                encoder = local_encoder()
                if encoder and self.retrieval_mode != "fts":
                    predicate = f"AND EXISTS (SELECT 1 FROM conversation_messages m WHERE m.message_id=s.id AND {eligible})"
                    for identity,score in vector_hits(conn,conf_uid,encoder,query_text,0.48,120,
                                                      eligible_sql=predicate,eligible_args=params).items():
                        scores[identity] = scores.get(identity,0) + score
                return scores
            for term in sorted(query_terms(query_text))[:10]:
                pattern = f"%{term}%"
                for row in conn.execute(
                    f"""
                    SELECT message_id
                    FROM conversation_messages m
                    WHERE {eligible} AND content LIKE ?
                    LIMIT 120
                    """,
                    (*params, pattern),
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
                           timestamp, title, content, json_extract(message_json,'$.turn_id') AS turn_id,
                           json_extract(message_json,'$.source_span') AS span
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
        query_text: str = "",
    ) -> list[ConversationSearchHit]:
        selected: list[ConversationSearchHit] = []
        used_tokens = 0
        seen_turns = set()
        for hit in hits:
            if hit.turn_id and (hit.history_uid,hit.turn_id) in seen_turns:
                continue
            if len(selected) >= max_snippets:
                break
            content = hit.content
            if len(content) > 360:
                # Anchor long source excerpts at the most informative matching term.
                position = next((position for term in sorted(keyword_terms(query_text),key=lambda term:(-len(term),term))
                                 if (position := content.lower().find(term)) >= 0),0)
                start = max(0,position-80)
                content = ("… " if start else "") + content[start:]
            content = clean_text(content, max_len=360)
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
                    score=hit.score, turn_id=hit.turn_id, source_span=hit.source_span,
                )
            )
            seen_turns.add((hit.history_uid,hit.turn_id))
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
        terms = sorted(query_terms(query_text), key=lambda term: (-len(term), term))
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
    project_id: str = "", current_turn_id: str = "",
    max_snippets: int = 4,
    token_budget: int = 520,
) -> str:
    hits = _CONVERSATION_HISTORY_INDEX.search(
        conf_uid,
        query_text,
        exclude_history_uid=current_history_uid,
        include_current_history=True, project_id=project_id, current_turn_id=current_turn_id,
        max_snippets=max_snippets,
        token_budget=token_budget,
    )
    if not hits:
        return ""

    lines = [
        "Past conversation snippets relevant to this turn:",
        "- These are raw snippets from chat histories, not confirmed long-term facts.",
        "- Use them as source-grounded context; prefer long-term memory for stable preferences.",
    ]
    for hit in hits:
        source = f"history={hit.history_uid} message={hit.message_index}"
        if hit.source_span:
            source += f" span={hit.source_span[0]}..{hit.source_span[-1]}"
        if hit.timestamp:
            source += f" time={hit.timestamp}"
        if hit.title:
            source += f" title={hit.title}"
        lines.append(
            f"- [{source}] {hit.role}: {hit.content}"
        )
    return "\n".join(lines).strip()
