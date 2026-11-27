from __future__ import annotations

import hashlib
from .character_memory_repository import store_lock
from .memory_semantics import (
    local_encoder,
    vector_schema,
    remove_vector,
    put_vector,
    vector_hits,
)
import json
import sqlite3
from contextlib import closing
from functools import lru_cache
from typing import Any


from .character_memory_repository import CharacterMemoryRepository
from .character_memory_lifecycle import is_active_memory, has_save_authorization
from .character_memory_retriever import (
    KeywordMemoryIndex,
    MemorySearchHit,
    clean_text,
    entry_scope_level,
    entry_status,
    keyword_terms,
    query_terms,
)


class SQLiteMemoryIndex:
    """A revision-checked projection of the canonical Repository, shared by Qt and Chat."""

    def __init__(self, db_path=None, *, repository=None, fallback_index=None):
        self._repository = repository or CharacterMemoryRepository()
        self._db_path = db_path
        self._fallback_index = fallback_index or KeywordMemoryIndex()
        self._initialized = {}

    def db_path(self):
        return self._db_path or self._repository.root() / "character_memory.sqlite3"

    def _connect(self):
        path = self.db_path().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            stamp = path.stat().st_ino
            if self._initialized.get(path) != stamp:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("BEGIN IMMEDIATE")
                if not conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='memory_revisions'"
                ).fetchone():
                    conn.execute("DROP TABLE IF EXISTS memory_entries_fts")
                    conn.execute("DROP TABLE IF EXISTS memory_entries")
                    conn.execute(
                        "CREATE TABLE memory_revisions(conf_uid TEXT PRIMARY KEY,rev TEXT)"
                    )
                conn.commit()
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS memory_spans(
                      owner TEXT, character TEXT, history TEXT, turn TEXT,
                      PRIMARY KEY(owner,character,history,turn));
                    CREATE TABLE IF NOT EXISTS memory_entries(
                      conf_uid TEXT,entry_id TEXT,scope_level TEXT,scope_id TEXT,memory_type TEXT,
                      status TEXT,enabled INTEGER,subject TEXT,key TEXT,content TEXT,confidence REAL,
                      importance REAL,source TEXT,updated_at TEXT,entry_json TEXT, PRIMARY KEY(conf_uid,entry_id));
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_entries_fts USING fts5(terms);
                """)
                vector_schema(conn)
                self._initialized[path] = stamp
            return conn
        except Exception:
            conn.close()
            raise

    def _revision(self, path, encoder):
        try:
            stat = path.stat()
            return f"facts-v2:{stat.st_ino}:{stat.st_mtime_ns}:{stat.st_size}:{encoder.revision if encoder else ''}"
        except FileNotFoundError:
            return ""

    def refresh(self, namespace):
        path = self._repository.store_path(namespace)
        encoder = local_encoder()
        with closing(self._connect()) as conn:
            rev = self._revision(path, encoder)
            known = conn.execute(
                "SELECT rev FROM memory_revisions WHERE conf_uid=?", (namespace,)
            ).fetchone()
            if (known[0] if known else "") == rev:
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            with store_lock(path), conn:
                rev = self._revision(path, encoder)
                store = self._repository.load(namespace)
                entries = store["entries"]
                conn.execute("DELETE FROM memory_spans WHERE owner=?", (namespace,))
                conn.executemany(
                    "INSERT OR IGNORE INTO memory_spans VALUES(?,?,?,?)",
                    ((namespace, *ref) for ref in store.get("suppressed_spans", [])),
                )
                self._sync(conn, namespace, entries, encoder)
                conn.execute(
                    "INSERT OR REPLACE INTO memory_revisions VALUES(?,?)",
                    (namespace, rev),
                )

    def sync(self, namespace, entries):
        with closing(self._connect()) as conn, conn:
            self._sync(conn, namespace, entries, local_encoder())
            conn.execute("DELETE FROM memory_revisions WHERE conf_uid=?", (namespace,))

    def _sync(self, conn, namespace, entries, encoder):
        existing = {
            r["entry_id"]: r
            for r in conn.execute(
                "SELECT rowid,entry_id,entry_json FROM memory_entries WHERE conf_uid=?",
                (namespace,),
            )
        }
        vectors = dict(
            conn.execute(
                "SELECT id,revision FROM semantic_vectors WHERE owner=?", (namespace,)
            )
        )
        for entry in entries:
            row = self._entry_row(namespace, entry)
            key = row["entry_id"]
            old = existing.pop(key, None)
            vector_eligible = row["enabled"] or (
                row["status"] == "superseded" and has_save_authorization(entry)
            )
            if old and old["entry_json"] == row["entry_json"]:
                if (
                    not encoder
                    or not vector_eligible
                    or vectors.get(key) == encoder.revision
                ):
                    continue
            if old:
                self._remove(conn, namespace, old)
            fields = ",".join(row)
            values = ",".join(":" + name for name in row)
            rowid = conn.execute(
                f"INSERT INTO memory_entries({fields}) VALUES({values})", row
            ).lastrowid
            terms = sorted(
                keyword_terms(" ".join([row["content"], row["subject"], row["key"]]))
            )
            conn.execute(
                "INSERT INTO memory_entries_fts(rowid,terms) VALUES(?,?)",
                (rowid, " ".join(terms)),
            )
            if encoder and vector_eligible:
                put_vector(
                    conn, namespace, key, encoder, encoder.encode([row["content"]])[0]
                )
        for old in existing.values():
            self._remove(conn, namespace, old)

    def _remove(self, conn, namespace, old):
        conn.execute("DELETE FROM memory_entries_fts WHERE rowid=?", (old["rowid"],))
        conn.execute("DELETE FROM memory_entries WHERE rowid=?", (old["rowid"],))
        remove_vector(conn, namespace, old["entry_id"])

    def suppressed(self, namespaces, character, history=""):
        stamps = tuple(
            self._revision(self._repository.store_path(ns), None) for ns in namespaces
        )
        return self._read_suppressed(
            self.db_path().resolve(), tuple(namespaces), character, history, stamps
        )

    @lru_cache(maxsize=32)
    def _read_suppressed(self, database, namespaces, character, history, stamps):
        result = set()
        for namespace in namespaces:
            if self._repository.store_path(namespace).is_file():
                self.refresh(namespace)
                with closing(self._connect()) as conn:
                    rows = conn.execute(
                        "SELECT history,turn FROM memory_spans WHERE owner=? AND character=?"
                        " AND (?='' OR history=?)",
                        (namespace, character, history, history),
                    )
                    result.update((r[0], r[1]) for r in rows)
        return frozenset(result)

    def lookup(
        self,
        namespace,
        plan,
        *,
        history_uid="",
        historical=False,
        project_id="",
        cutoff="",
    ):
        if not self._repository.store_path(namespace).is_file():
            return []
        self.refresh(namespace)
        terms = sorted(
            query_terms(plan.query_text), key=lambda term: (-len(term), term)
        )
        encoder = local_encoder()
        if not terms and not encoder:
            return []
        expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        where = """conf_uid=? AND (enabled=1 OR (? AND status='superseded'))
          AND (scope_level!='thread' OR (scope_id=? AND ?!=''))
          AND (scope_level!='project' OR (scope_id=? AND ?!='' AND scope_id!=conf_uid))"""
        args = (namespace, historical, history_uid, history_uid, project_id, project_id)
        if cutoff:
            where += """ AND substr(coalesce(json_extract(entry_json,'$.valid_from'),
                             json_extract(entry_json,'$.created_at')),1,10) <= ?
                         AND coalesce(nullif(substr(json_extract(entry_json,'$.valid_to'),1,10),''),'9999-12-31') > ?"""
            args += (cutoff, cutoff)
        elif not historical:
            where += """ AND (nullif(json_extract(entry_json,'$.valid_from'),'') IS NULL
                              OR julianday(json_extract(entry_json,'$.valid_from')) <= julianday('now'))
                         AND (nullif(json_extract(entry_json,'$.valid_to'),'') IS NULL
                              OR julianday(json_extract(entry_json,'$.valid_to')) > julianday('now'))"""
        limit = max(plan.max_entries * 8, 1)
        with closing(self._connect()) as conn:
            hits = {}
            if terms:
                rows = conn.execute(
                    f"""SELECT entry_json,bm25(memory_entries_fts) rank FROM memory_entries m
                    JOIN memory_entries_fts ON memory_entries_fts.rowid=m.rowid
                    WHERE {where} AND memory_entries_fts MATCH ? ORDER BY rank,entry_id LIMIT ?""",
                    (*args, expression, limit),
                )
                for row in rows:
                    entry = json.loads(row["entry_json"])
                    if not has_save_authorization(entry):
                        continue
                    hits[entry["id"]] = MemorySearchHit(
                        entry, 1.0 - row["rank"], ("fts",)
                    )
            if encoder:
                predicate = f"AND EXISTS (SELECT 1 FROM memory_entries WHERE entry_id=s.id AND {where})"
                for identity, score in vector_hits(
                    conn,
                    namespace,
                    encoder,
                    plan.query_text,
                    0.48,
                    limit,
                    eligible_sql=predicate,
                    eligible_args=args,
                ).items():
                    row = conn.execute(
                        f"SELECT entry_json FROM memory_entries WHERE {where} AND entry_id=?",
                        (*args, identity),
                    ).fetchone()
                    if row and has_save_authorization(json.loads(row[0])):
                        previous = hits.get(identity)
                        hits[identity] = MemorySearchHit(
                            json.loads(row[0]),
                            score + (previous.score if previous else 0),
                            ("fts", "vector") if previous else ("vector",),
                        )
            return sorted(hits.values(), key=lambda h: (-h.score, h.entry["id"]))

    def search(self, entries, plan, *, namespace=""):
        eligible = {self._entry_id(entry) for entry in entries}
        return [
            hit
            for hit in self.lookup(namespace, plan)
            if self._entry_id(hit.entry) in eligible
        ]

    def _entry_row(self, namespace: str, entry: dict[str, Any]) -> dict[str, Any]:
        content = clean_text(str(entry.get("content") or ""), max_len=500)
        return {
            "entry_id": self._entry_id(entry),
            "conf_uid": namespace,
            "scope_level": entry_scope_level(entry),
            "scope_id": str(entry.get("scope_id") or ""),
            "memory_type": str(entry.get("memory_type") or "fact"),
            "status": entry_status(entry),
            "enabled": 1 if is_active_memory(entry) else 0,
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
