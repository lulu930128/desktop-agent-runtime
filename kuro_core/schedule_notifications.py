"""Core-owned reminders: persist decisions; transport cannot choose eligibility."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from .schedule_contract import ScheduleConflict, aware, bounds, day, integer, localize, text, zone
from .schedule_store import encoded

UTC = timezone.utc


def migrate_notifications(path):
    with closing(sqlite3.connect(path, timeout=10)) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version == 3:
            conn.execute("SELECT lease_token,lease_until,snooze_until,title,updated_at FROM schedule_notification_deliveries LIMIT 0")
            conn.execute("SELECT payload FROM schedule_preferences LIMIT 0")
            conn.execute("SELECT payload FROM schedule_notification_audit LIMIT 0")
            return
        if version != 2:
            raise RuntimeError("Notification migration requires Core schema 2")
        with closing(sqlite3.connect(str(path)+f".pre-v3-{uuid.uuid4().hex}.bak")) as backup:
            conn.backup(backup)
        conn.execute("BEGIN IMMEDIATE")
        try:
            if conn.execute("PRAGMA user_version").fetchone()[0] == 3:
                conn.rollback()
                return
            for column in ("lease_token TEXT", "lease_until TEXT", "snooze_until TEXT", "title TEXT", "updated_at TEXT"):
                conn.execute("ALTER TABLE schedule_notification_deliveries ADD COLUMN " + column)
            conn.execute("CREATE TABLE schedule_preferences (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
            conn.execute("CREATE TABLE schedule_notification_audit (sequence INTEGER PRIMARY KEY, delivery_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)")
            conn.execute("CREATE INDEX schedule_delivery_due ON schedule_notification_deliveries(state,due_at)")
            conn.execute("PRAGMA user_version=3")
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def clock_value(value):
    if not isinstance(value, str):
        raise ValueError("Clock must be HH:MM")
    parsed = time.fromisoformat(value)
    if parsed.tzinfo or parsed.isoformat(timespec="minutes") != value:
        raise ValueError("Clock must be HH:MM")
    return parsed


class ScheduleNotifications:
    def __init__(self, store, default_timezone="UTC"):
        zone(default_timezone)
        self.store = store
        self.default_timezone = default_timezone

    def _preferences(self, conn):
        row = conn.execute("SELECT payload FROM schedule_preferences WHERE id=1").fetchone()
        return json.loads(row[0]) if row else {"timezone": self.default_timezone, "quietEnabled": True, "quietStart": "22:00", "quietEnd": "08:00"}

    @staticmethod
    def _quiet(now, prefs):
        local = now.astimezone(zone(prefs["timezone"])).time().replace(tzinfo=None)
        start, end = clock_value(prefs["quietStart"]), clock_value(prefs["quietEnd"])
        return prefs["quietEnabled"] and (start <= local < end if start < end else local >= start or local < end)

    @staticmethod
    def _key(item):
        value = {k:item.get(k) for k in ("start","end","due","timezone","allDay","notification")}
        return int(hashlib.sha256(encoded(value).encode()).hexdigest()[:15],16)

    @staticmethod
    def _due(item):
        prefs = item["notification"]
        key = "due" if item["kind"] == "deadline" else "start"
        start = localize(datetime.combine(day(item[key]), clock_value(prefs["allDayTime"])), zone(item["timezone"])) if item["allDay"] else aware(item[key])
        return start.astimezone(UTC)-timedelta(minutes=prefs["minutesBefore"])

    @staticmethod
    def _audit(conn, delivery_id, action, now):
        conn.execute("INSERT INTO schedule_notification_audit(delivery_id,created_at,payload) VALUES(?,?,?)", (delivery_id,now.isoformat(),encoded({"action":action})))

    def _active(self, conn, delivery, now=None):
        row = conn.execute("""SELECT o.*,i.cancelled AS series_cancelled FROM schedule_occurrences o
            JOIN schedule_items i ON i.id=o.item_id WHERE o.item_id=? AND o.original_date=?""", (delivery["item_id"],delivery["original_date"])).fetchone()
        if not row or row["cancelled"] or row["series_cancelled"] or row["reason"] or row["state"] != "pending":
            return False
        item = json.loads(row["payload"])
        if now is not None and not item["trackCompletion"] and bounds(item)[1] <= now:
            return False
        return item["notification"]["enabled"] and self._key(item) == delivery["rule_revision"]

    def tick(self, *, now=None):
        now = aware(now).astimezone(UTC) if now else datetime.now(UTC)
        with self.store.connect(write=True) as conn:
            prefs = self._preferences(conn)
            # Materialized instances only; never fabricate an unexpanded occurrence.
            rows = conn.execute("""SELECT o.* FROM schedule_occurrences o JOIN schedule_items i ON i.id=o.item_id
                WHERE i.cancelled=0 AND o.cancelled=0 AND o.reason IS NULL AND o.state='pending'
                AND json_extract(o.payload,'$.notification.enabled')=1""").fetchall()
            for row in rows:
                item = json.loads(row["payload"])
                due_error = False
                try:
                    due = self._due(item)
                except ValueError:
                    due = bounds(item)[0]
                    due_error = True
                key = self._key(item)
                delivery_id = hashlib.sha256(f"{row['item_id']}:{row['original_date']}:{key}".encode()).hexdigest()
                conn.execute("""INSERT INTO schedule_notification_deliveries(id,item_id,original_date,rule_revision,channel,state,due_at,title,updated_at)
                    VALUES(?,?,?,?,?,'pending',?,?,?) ON CONFLICT(item_id,original_date,rule_revision,channel)
                    DO UPDATE SET title=excluded.title,state=CASE WHEN state='cancelled' THEN 'pending' ELSE state END""",
                    (delivery_id,row["item_id"],row["original_date"],key,item["notification"]["channel"],due.isoformat(),item["title"],now.isoformat()))
                if due_error:
                    previous = conn.execute("SELECT state FROM schedule_notification_deliveries WHERE id=?",(delivery_id,)).fetchone()[0]
                    if previous != "failed":
                        conn.execute("UPDATE schedule_notification_deliveries SET state='failed' WHERE id=?",(delivery_id,))
                        self._audit(conn,delivery_id,"reminder_time_dst_gap",now)
            for row in conn.execute("SELECT * FROM schedule_notification_deliveries WHERE state IN ('pending','ready','suppressed','snoozed','claimed','dispatching')").fetchall():
                target = row["state"]
                if not self._active(conn,row,now):
                    target = "cancelled"
                elif target in {"claimed","dispatching"}:
                    if row["lease_until"] and aware(row["lease_until"]) <= now:
                        target = "unknown" if target == "dispatching" else "ready"
                elif row["due_at"] and aware(row["due_at"]) <= now:
                    target = "missed" if now-aware(row["due_at"]) > timedelta(minutes=30) else "suppressed" if self._quiet(now,prefs) else "ready"
                else:
                    target = "snoozed" if row["snooze_until"] else "pending"
                if target != row["state"]:
                    conn.execute("UPDATE schedule_notification_deliveries SET state=?,updated_at=? WHERE id=?", (target,now.isoformat(),row["id"]))
                    self._audit(conn,row["id"],target,now)
        return {"evaluatedAt":now.isoformat()}

    def read(self):
        with self.store.connect() as conn:
            rows = conn.execute("SELECT * FROM schedule_notification_deliveries WHERE state NOT IN ('cancelled','dismissed','pending') ORDER BY due_at DESC,id LIMIT 101").fetchall()
            return {"preferences":self._preferences(conn),"hasMore":len(rows)>100,"items":[
                {"id":r["id"],"scheduleId":r["item_id"],"occurrenceDate":r["original_date"],"title":r["title"],"state":r["state"],"dueAt":r["due_at"],"channel":r["channel"]} for r in rows[:100]]}

    def action(self, payload, *, now=None):
        now = aware(now).astimezone(UTC) if now else datetime.now(UTC)
        if not isinstance(payload,dict):
            raise ValueError("Notification action must be an object")
        action = payload.get("action")
        allowed = {"claim":{"action"},"authorize":{"action","id","leaseToken"},"ack":{"action","id","leaseToken","result"},
                   "dismiss":{"action","id","confirmed"},"snooze":{"action","id","confirmed","until"},"preferences":{"action","confirmed","preferences"}}
        if action not in allowed or set(payload) != allowed[action]:
            raise ValueError("Invalid notification action fields")
        if action in {"dismiss","snooze","preferences"} and payload.get("confirmed") is not True:
            raise PermissionError("Confirmation required")
        with self.store.connect(write=True) as conn:
            if action == "preferences":
                p = payload["preferences"]
                if not isinstance(p,dict) or set(p) != {"timezone","quietEnabled","quietStart","quietEnd"} or type(p["quietEnabled"]) is not bool:
                    raise ValueError("Invalid preferences")
                zone(p["timezone"])
                clock_value(p["quietStart"]); clock_value(p["quietEnd"])
                if p["quietStart"] == p["quietEnd"]:
                    raise ValueError("Quiet start and end must differ")
                conn.execute("INSERT INTO schedule_preferences VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (encoded(p),))
                self._audit(conn,"preferences","updated",now)
                return {"preferences":p}
            if action == "claim":
                if self._quiet(now,self._preferences(conn)):
                    return {"delivery":None}
                for row in conn.execute("SELECT * FROM schedule_notification_deliveries WHERE state='ready' AND channel='desktop' ORDER BY due_at,id LIMIT 100").fetchall():
                    if not self._active(conn,row,now) or not row["due_at"] or not timedelta(0) <= now-aware(row["due_at"]) <= timedelta(minutes=30):
                        continue
                    token = uuid.uuid4().hex
                    conn.execute("UPDATE schedule_notification_deliveries SET state='claimed',lease_token=?,lease_until=?,updated_at=? WHERE id=?",(token,(now+timedelta(seconds=20)).isoformat(),now.isoformat(),row["id"]))
                    self._audit(conn,row["id"],"claimed",now)
                    return {"delivery":{"id":row["id"],"leaseToken":token}}
                return {"delivery":None}
            row = conn.execute("SELECT * FROM schedule_notification_deliveries WHERE id=?", (text(payload.get("id"),"id",100),)).fetchone()
            if not row:
                raise LookupError("Notification not found")
            if action in {"authorize","ack"}:
                if payload["leaseToken"] != row["lease_token"] or not row["lease_until"] or aware(row["lease_until"]) <= now:
                    raise ScheduleConflict("Delivery lease expired")
                required = "claimed" if action == "authorize" else "dispatching"
                if row["state"] != required:
                    if action == "ack" and row["state"] == payload.get("result"):
                        return {"state":row["state"]}
                    raise ScheduleConflict("Delivery state changed")
                if action == "authorize":
                    if not self._active(conn,row,now) or self._quiet(now,self._preferences(conn)) or now-aware(row["due_at"]) > timedelta(minutes=30):
                        raise ScheduleConflict("Reminder no longer eligible")
                    target = "dispatching"
                else:
                    target = payload["result"]
                    if target not in {"delivered","failed","unknown"}:
                        raise ValueError("Invalid delivery result")
            elif action == "dismiss":
                target = "dismissed"
            else:
                if not self._active(conn,row,now) or row["state"] in {"dispatching","claimed","cancelled"}:
                    raise ScheduleConflict("Reminder cannot be snoozed")
                until = aware(payload["until"]).astimezone(UTC)
                if not now < until <= now+timedelta(days=7):
                    raise ValueError("Snooze must be in the next seven days")
                conn.execute("UPDATE schedule_notification_deliveries SET due_at=?,snooze_until=? WHERE id=?", (until.isoformat(),until.isoformat(),row["id"]))
                target = "snoozed"
            conn.execute("UPDATE schedule_notification_deliveries SET state=?,updated_at=? WHERE id=?", (target,now.isoformat(),row["id"]))
            self._audit(conn,row["id"],target,now)
            return {"state":target, **({"title":row["title"],"dueAt":row["due_at"]} if action=="authorize" else {})}
