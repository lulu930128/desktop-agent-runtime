"""Transactional local work state in the Core database, separate from observations."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager, closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .schedule_contract import (ScheduleConflict, anchor_date, aware, bounds, day, integer,
                                matches, occurrence, text, validate_item, zone)

UTC = timezone.utc


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def verify_schema(conn):
    # A version number alone is not readiness (e.g. incomplete/manual restores).
    for table, columns in {
        "schedule_items": "id,revision,payload,cancelled,cutoff,cursor,ordinal,lineage",
        "schedule_occurrences": "item_id,original_date,payload,state,exception,cancelled,reason,start_utc,end_utc",
        "schedule_revisions": "sequence,item_id,revision,command,created_at",
        "schedule_mutations": "key,digest,response",
        "schedule_notification_deliveries": "id,item_id,original_date,rule_revision,channel,state,due_at",
    }.items():
        conn.execute(f"SELECT {columns} FROM {table} LIMIT 0")


def migrate_schedule(path):
    """Back up v1 using SQLite's snapshot API; migrate DDL in one transaction."""
    with closing(sqlite3.connect(path, timeout=10)) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version in {2, 3}:
            verify_schema(conn)
            return
        if version != 1:
            raise RuntimeError("Schedule migration requires Core schema 1")
        backup = Path(str(path) + f".pre-v2-{uuid.uuid4().hex}.bak")
        with closing(sqlite3.connect(backup)) as target:
            conn.backup(target)
        conn.execute("BEGIN IMMEDIATE")
        try:
            if conn.execute("PRAGMA user_version").fetchone()[0] == 2:
                conn.rollback()
                return
            statements = [
                "CREATE TABLE schedule_items (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL, cancelled INTEGER NOT NULL DEFAULT 0, cutoff TEXT, cursor TEXT NOT NULL, ordinal INTEGER NOT NULL DEFAULT 0, lineage TEXT)",
                "CREATE TABLE schedule_revisions (sequence INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL REFERENCES schedule_items(id), revision INTEGER NOT NULL, command TEXT NOT NULL, created_at TEXT NOT NULL)",
                "CREATE TABLE schedule_mutations (key TEXT PRIMARY KEY, digest TEXT NOT NULL, response TEXT NOT NULL)",
                "CREATE TABLE schedule_occurrences (item_id TEXT NOT NULL REFERENCES schedule_items(id), original_date TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', exception INTEGER NOT NULL DEFAULT 0, cancelled INTEGER NOT NULL DEFAULT 0, reason TEXT, start_utc TEXT, end_utc TEXT, PRIMARY KEY(item_id, original_date))",
                "CREATE INDEX schedule_occurrences_time ON schedule_occurrences(end_utc, start_utc)",
                "CREATE TABLE schedule_notification_deliveries (id TEXT PRIMARY KEY, item_id TEXT NOT NULL REFERENCES schedule_items(id), original_date TEXT NOT NULL, rule_revision INTEGER NOT NULL, channel TEXT NOT NULL, state TEXT NOT NULL, due_at TEXT, UNIQUE(item_id, original_date, rule_revision, channel))",
            ]
            for statement in statements:
                conn.execute(statement)
            conn.execute("PRAGMA user_version=2")
            verify_schema(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise


class ScheduleStore:
    def __init__(self, path):
        self.path = Path(path).resolve()

    @contextmanager
    def connect(self, *, write=False):
        # Existing database only. Reads neither create directories nor change PRAGMAs.
        uri = self.path.as_uri() + ("?mode=rw" if write else "?mode=ro")
        conn = sqlite3.connect(uri, uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            if conn.execute("PRAGMA user_version").fetchone()[0] != 3:
                raise RuntimeError("Unsupported schedule schema")
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if write:
                conn.commit()
        except Exception:
            if write:
                conn.rollback()
            raise
        finally:
            conn.close()

    def _record(self, conn, item_id):
        row = conn.execute("SELECT * FROM schedule_items WHERE id=?", (item_id,)).fetchone()
        if row is None:
            raise LookupError("Schedule not found")
        return row

    def get(self, item_id):
        with self.connect() as conn:
            return self._public(self._record(conn, item_id))

    @staticmethod
    def _public(row):
        return {"id": row["id"], "revision": row["revision"], "item": json.loads(row["payload"]),
                "cancelled": bool(row["cancelled"]), "cutoff": row["cutoff"], "lineage": row["lineage"]}

    def mutate(self, command):
        if not isinstance(command, dict) or set(command) - {"action", "idempotencyKey", "id", "expectedRevision", "item", "scope", "occurrenceDate", "confirmed"}:
            raise ValueError("Invalid mutation fields")
        if command.get("confirmed") is not True:
            raise PermissionError("Explicit local operation confirmation required")
        key = text(command.get("idempotencyKey"), "idempotencyKey", 160)
        action = command.get("action")
        if action not in {"create", "update", "cancel", "complete", "skip", "reopen"}:
            raise ValueError("Unknown schedule action")
        if action not in {"create", "update"} and "item" in command:
            raise ValueError("This action does not accept an item payload")
        if action != "create" and command.get("scope", "all") == "all" and "occurrenceDate" in command:
            raise ValueError("All scope does not accept occurrenceDate")
        digest = hashlib.sha256(encoded(command).encode()).hexdigest()
        with self.connect(write=True) as conn:
            replay = conn.execute("SELECT * FROM schedule_mutations WHERE key=?", (key,)).fetchone()
            if replay:
                if replay["digest"] != digest:
                    raise ScheduleConflict("Idempotency key reused with different payload")
                return json.loads(replay["response"])
            if action == "create":
                if set(command) - {"action", "idempotencyKey", "item", "confirmed"}:
                    raise ValueError("Unexpected create fields")
                item = validate_item(command.get("item"))
                item_id = uuid.uuid4().hex
                conn.execute("INSERT INTO schedule_items(id,revision,payload,cursor) VALUES(?,1,?,?)",
                             (item_id, encoded(item), anchor_date(item).isoformat()))
                revision = 1
            else:
                item_id = text(command.get("id"), "id", 100)
                row = self._record(conn, item_id)
                revision = integer(command.get("expectedRevision"), "expectedRevision", 1, 2147483647)
                if revision != row["revision"]:
                    raise ScheduleConflict("Schedule revision changed; reload before editing")
                if row["cancelled"]:
                    raise ScheduleConflict("Schedule is cancelled")
                item = json.loads(row["payload"])
                scope = command.get("scope", "all")
                if scope not in {"all", "this", "future"}:
                    raise ValueError("Unknown edit scope")
                original = None
                if scope != "all" or action in {"complete", "skip", "reopen"}:
                    original = day(command.get("occurrenceDate")).isoformat()
                    found = conn.execute("SELECT * FROM schedule_occurrences WHERE item_id=? AND original_date=?", (item_id, original)).fetchone()
                    if not found or found["reason"] or found["cancelled"]:
                        raise ScheduleConflict("Occurrence must be materialized and active")
                revision += 1
                if action in {"complete", "skip", "reopen"}:
                    if scope != "this":
                        raise ValueError("Completion applies to one occurrence")
                    if not json.loads(found["payload"])["trackCompletion"]:
                        raise ValueError("Completion tracking is disabled")
                    state = {"complete": "completed", "skip": "skipped", "reopen": "pending"}[action]
                    conn.execute("UPDATE schedule_occurrences SET state=? WHERE item_id=? AND original_date=?", (state, item_id, original))
                elif scope == "this":
                    if action == "cancel":
                        conn.execute("UPDATE schedule_occurrences SET cancelled=1,exception=1 WHERE item_id=? AND original_date=?", (item_id, original))
                    else:
                        replacement = validate_item(command.get("item"))
                        if replacement["recurrence"]:
                            raise ValueError("Single occurrence cannot recur")
                        if found["state"] != "pending":
                            raise ScheduleConflict("Cannot rewrite completed history")
                        self._put_occurrence(conn, item_id, original, replacement, exception=1)
                elif scope == "future":
                    if not item["recurrence"]:
                        raise ValueError("Future scope requires a recurring series")
                    if conn.execute("SELECT 1 FROM schedule_occurrences WHERE item_id=? AND original_date>=? AND (exception=1 OR state!='pending') LIMIT 1", (item_id, original)).fetchone():
                        raise ScheduleConflict("Future exceptions or completed history require resolution")
                    conn.execute("UPDATE schedule_items SET cutoff=? WHERE id=?", (original, item_id))
                    conn.execute("UPDATE schedule_occurrences SET cancelled=1 WHERE item_id=? AND original_date>=?", (item_id, original))
                    if action == "update":
                        replacement = validate_item(command.get("item"))
                        child_id = uuid.uuid4().hex
                        conn.execute("INSERT INTO schedule_items(id,revision,payload,cursor,lineage) VALUES(?,1,?,?,?)", (child_id, encoded(replacement), anchor_date(replacement).isoformat(), item_id))
                        conn.execute("INSERT INTO schedule_revisions(item_id,revision,command,created_at) VALUES(?,1,?,?)", (child_id, encoded(command), datetime.now(UTC).isoformat()))
                elif action == "cancel":
                    conn.execute("UPDATE schedule_items SET cancelled=1 WHERE id=?", (item_id,))
                    conn.execute("UPDATE schedule_occurrences SET cancelled=1 WHERE item_id=? AND state='pending'", (item_id,))
                else:
                    replacement = validate_item(command.get("item"))
                    timing = {"start", "end", "due", "allDay", "timezone", "recurrence", "kind"}
                    changed = any(item.get(k) != replacement.get(k) for k in timing)
                    if changed and conn.execute("SELECT 1 FROM schedule_occurrences WHERE item_id=? AND (exception=1 OR state!='pending') LIMIT 1", (item_id,)).fetchone():
                        raise ScheduleConflict("Timing change cannot remap exceptions or completed history")
                    if row["cutoff"] and changed:
                        raise ScheduleConflict("Edit the split successor instead of rewriting a historical series")
                    if changed:
                        conn.execute("DELETE FROM schedule_occurrences WHERE item_id=?", (item_id,))
                        conn.execute("UPDATE schedule_items SET cursor=?,ordinal=0 WHERE id=?", (anchor_date(replacement).isoformat(), item_id))
                    else:
                        for current in conn.execute("SELECT * FROM schedule_occurrences WHERE item_id=? AND exception=0 AND state='pending'", (item_id,)).fetchall():
                            if not current["reason"]:
                                self._put_occurrence(conn, item_id, current["original_date"], occurrence(replacement, day(current["original_date"])))
                    conn.execute("UPDATE schedule_items SET payload=? WHERE id=?", (encoded(replacement), item_id))
                conn.execute("UPDATE schedule_items SET revision=? WHERE id=?", (revision, item_id))
                # Delivery creation/dispatch is M5. Already-pending records must not survive edits.
                delivery_sql = "UPDATE schedule_notification_deliveries SET state='cancelled' WHERE item_id=? AND state IN ('pending','ready','suppressed','snoozed','claimed','dispatching')"
                delivery_args = [item_id]
                if scope == "this":
                    delivery_sql += " AND original_date=?"
                    delivery_args.append(original)
                elif scope == "future":
                    delivery_sql += " AND original_date>=?"
                    delivery_args.append(original)
                conn.execute(delivery_sql, delivery_args)
            conn.execute("INSERT INTO schedule_revisions(item_id,revision,command,created_at) VALUES(?,?,?,?)", (item_id, revision, encoded(command), datetime.now(UTC).isoformat()))
            response = self._public(self._record(conn, item_id))
            if action == "update" and command.get("scope") == "future":
                response["successor"] = self._public(self._record(conn, child_id))
            conn.execute("INSERT INTO schedule_mutations VALUES(?,?,?)", (key, digest, encoded(response)))
            return response

    @staticmethod
    def _put_occurrence(conn, item_id, original, payload, *, exception=0, reason=None):
        start, end = bounds(payload) if not reason else (None, None)
        conn.execute("""INSERT INTO schedule_occurrences(item_id,original_date,payload,exception,reason,start_utc,end_utc)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(item_id,original_date) DO UPDATE SET
            payload=excluded.payload,exception=excluded.exception,reason=excluded.reason,
            start_utc=excluded.start_utc,end_utc=excluded.end_utc""",
                     (item_id, original, encoded(payload), exception, reason, start.isoformat() if start else None, end.isoformat() if end else None))

    def advance(self, through: str, *, budget: int = 3660) -> dict:
        """Explicit bounded materialization command. Cursor records evaluated calendar days."""
        horizon = day(through)
        integer(budget, "budget", 1, 10000)
        used = 0
        with self.connect(write=True) as conn:
            rows = conn.execute("SELECT * FROM schedule_items WHERE cancelled=0 ORDER BY cursor,id").fetchall()
            for row in rows:
                item = json.loads(row["payload"])
                cursor, ordinal = day(row["cursor"]), row["ordinal"]
                rule = item["recurrence"]
                while cursor <= horizon and used < budget:
                    if row["cutoff"] and cursor >= day(row["cutoff"]):
                        cursor = horizon + timedelta(days=1)
                        break
                    if (not rule and cursor > anchor_date(item)) or (rule and ((rule.get("count") and ordinal >= rule["count"]) or (rule.get("until") and cursor > day(rule["until"])))):
                        cursor = horizon + timedelta(days=1)
                        break
                    used += 1
                    if matches(item, cursor):
                        ordinal += 1
                        try:
                            payload = occurrence(item, cursor)
                            self._put_occurrence(conn, row["id"], cursor.isoformat(), payload)
                        except ValueError as exc:
                            if "DST gap" not in str(exc):
                                raise
                            self._put_occurrence(conn, row["id"], cursor.isoformat(), item, reason="dst_gap")
                    cursor += timedelta(days=1)
                conn.execute("UPDATE schedule_items SET cursor=?,ordinal=? WHERE id=?", (cursor.isoformat(), ordinal, row["id"]))
            incomplete = conn.execute("SELECT COUNT(*) FROM schedule_items WHERE cancelled=0 AND cursor<=?", (horizon.isoformat(),)).fetchone()[0]
        return {"through": through, "evaluatedDays": used, "complete": incomplete == 0}

    def view(self, start_date: str, end_date: str, timezone_name: str, *, as_of: str | None = None, limit: int = 200, offset: int = 0) -> dict:
        start_day, end_day, tz = day(start_date), day(end_date), zone(timezone_name)
        if not 0 < (end_day-start_day).days <= 366:
            raise ValueError("Range must be 1 to 366 days, exclusive end")
        integer(limit, "limit", 1, 500)
        integer(offset, "offset", 0, 10000000)
        now = aware(as_of) if as_of else datetime.now(UTC)
        from datetime import time
        start = datetime.combine(start_day, time.min, tz).astimezone(UTC)
        end = datetime.combine(end_day, time.min, tz).astimezone(UTC)
        with self.connect() as conn:
            # A single snapshot binds coverage to the selected rows under concurrent mutation.
            conn.execute("BEGIN")
            coverage = conn.execute("SELECT COUNT(*) FROM schedule_items WHERE cancelled=0 AND cursor<=?", ((end_day+timedelta(days=1)).isoformat(),)).fetchone()[0] == 0
            rows = conn.execute("""SELECT o.*, i.revision FROM schedule_occurrences o
                JOIN schedule_items i ON i.id=o.item_id WHERE o.cancelled=0 AND o.reason IS NULL
                AND o.start_utc < ? AND (o.end_utc > ? OR (o.end_utc=o.start_utc AND o.start_utc>=?)
                OR (o.state='pending' AND json_extract(o.payload,'$.trackCompletion')=1 AND o.end_utc<=?))
                ORDER BY o.start_utc,o.item_id,o.original_date LIMIT ? OFFSET ?""",
                (end.isoformat(), start.isoformat(), start.isoformat(), min(now.astimezone(UTC), end).isoformat(), limit+1, offset)).fetchall()
            items = []
            for row in rows[:limit]:
                payload = json.loads(row["payload"])
                _, finish = bounds(payload)
                overdue = row["state"] == "pending" and payload["trackCompletion"] and finish <= now.astimezone(UTC)
                items.append({"id": f"{row['item_id']}:{row['original_date']}", "scheduleId": row["item_id"],
                              "occurrenceDate": row["original_date"], "revision": row["revision"],
                              "item": payload, "state": row["state"], "overdue": overdue,
                              "recurring": bool(json.loads(self._record(conn, row["item_id"])["payload"])["recurrence"]),
                              "timeState": "ended" if finish <= now.astimezone(UTC) else "upcoming" if aware(row["start_utc"]) > now.astimezone(UTC) else "ongoing"})
            skipped = conn.execute("SELECT COUNT(*) FROM schedule_occurrences WHERE cancelled=0 AND reason IS NOT NULL AND original_date>=? AND original_date<?", (start_date, end_date)).fetchone()[0]
        return {"contract": "kuro.core.schedule.v1", "startDate": start_date, "endDateExclusive": end_date,
                "timezone": timezone_name, "asOf": now.isoformat(), "items": items,
                "coverage": "complete" if coverage else "incomplete", "hasMore": len(rows)>limit,
                "nextOffset": offset+limit if len(rows)>limit else None,
                "limitations": (["materialization_pending"] if not coverage else []) + (["dst_occurrences_skipped"] if skipped else []),
                "skippedCount": skipped, "source": "local", "externalSync": "not_configured"}
