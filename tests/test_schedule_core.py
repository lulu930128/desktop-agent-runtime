from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from kuro_core.storage import KuroCoreStore
from kuro_core.schedule_store import ScheduleStore, migrate_schedule
from kuro_core.schedule_contract import ScheduleConflict, validate_item


def event(**changes):
    value = {"title": "Study", "kind": "study", "timezone": "Asia/Taipei",
             "start": "2026-09-12T09:00:00+08:00", "end": "2026-09-12T10:00:00+08:00"}
    value.update(changes)
    return value


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/"core.sqlite3"
        KuroCoreStore(self.path).initialize()
        self.store = ScheduleStore(self.path)

    def command(self, action, **kwargs):
        return dict(action=action, confirmed=True, idempotencyKey=uuid.uuid4().hex, **kwargs)

    def create(self, **changes):
        return self.store.mutate(self.command("create", item=event(**changes)))

    def edit(self, record, action="update", **kwargs):
        return self.store.mutate(self.command(action, id=record["id"], expectedRevision=record["revision"], **kwargs))

    def view(self, start="2026-09-12", end="2026-09-13", **kwargs):
        return self.store.view(start, end, "Asia/Taipei", as_of="2026-09-12T12:00:00+08:00", **kwargs)

    def test_migration_preserves_v1_and_backup(self):
        legacy = Path(self.temp.name)/"legacy.sqlite3"
        with sqlite3.connect(legacy) as conn:
            conn.execute("CREATE TABLE observations (id TEXT)")
            conn.execute("INSERT INTO observations VALUES ('old')")
            conn.execute("PRAGMA user_version=1")
        migrate_schedule(legacy)
        with sqlite3.connect(legacy) as conn:
            self.assertEqual(conn.execute("SELECT id FROM observations").fetchone()[0], "old")
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
        backups = list(Path(self.temp.name).glob("legacy.sqlite3.pre-v2-*.bak"))
        self.assertEqual(len(backups), 1)
        with sqlite3.connect(backups[0]) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT id FROM observations").fetchone()[0], "old")

    def test_migration_failure_rolls_back_and_future_schema_fails(self):
        legacy = Path(self.temp.name)/"bad.sqlite3"
        with sqlite3.connect(legacy) as conn:
            conn.execute("CREATE TABLE schedule_items (id TEXT)")
            conn.execute("PRAGMA user_version=1")
        with self.assertRaises(sqlite3.OperationalError):
            migrate_schedule(legacy)
        with sqlite3.connect(legacy) as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertFalse(conn.execute("SELECT name FROM sqlite_master WHERE name='schedule_revisions'").fetchone())
            conn.execute("PRAGMA user_version=99")
        with self.assertRaises(RuntimeError):
            KuroCoreStore(legacy).initialize()

    def test_schema_number_without_required_tables_is_not_ready(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("DROP TABLE schedule_notification_deliveries")
        with self.assertRaises(sqlite3.OperationalError):
            KuroCoreStore(self.path).initialize()

    def test_idempotency_and_parallel_conflict(self):
        command = self.command("create", item=event())
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(lambda _: self.store.mutate(command), range(10)))
        self.assertEqual(len({r["id"] for r in results}), 1)
        changed = copy.deepcopy(command)
        changed["item"]["title"] = "Different"
        with self.assertRaises(ScheduleConflict):
            self.store.mutate(changed)
        original = results[0]
        def update(n):
            try:
                return self.edit(original, item=event(title=str(n)))["revision"]
            except ScheduleConflict:
                return "conflict"
        with ThreadPoolExecutor(max_workers=4) as pool:
            updated = list(pool.map(update, range(4)))
        self.assertEqual(updated.count(2), 1)
        self.assertEqual(updated.count("conflict"), 3)

    def test_validation_and_confirmation(self):
        for item in [event(start="2026-09-12T09:00:00"), event(end="2026-09-12T08:00:00+08:00"),
                     event(timezone="bad"), event(start="2026-09-12T09:00:00+09:00"), event(title=""),
                     event(recurrence={"frequency":"weekly","weekdays":[True]}), event(unknown=True),
                     event(notification={"enabled":1})]:
            with self.subTest(item=item), self.assertRaises(ValueError):
                self.store.mutate(self.command("create", item=item))
        command = self.command("create", item=event())
        command["confirmed"] = False
        with self.assertRaises(PermissionError):
            self.store.mutate(command)

    def test_read_does_not_materialize_or_change_db(self):
        self.create()
        with sqlite3.connect(self.path) as conn:
            before = list(conn.iterdump())
        result = self.view()
        self.assertEqual(result["coverage"], "incomplete")
        self.assertEqual(result["items"], [])
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(before, list(conn.iterdump()))
        self.store.advance("2026-09-15")
        self.assertEqual(self.view()["coverage"], "complete")

    def test_cross_day_midnight_and_all_day(self):
        self.create(start="2026-09-11T09:00:00+08:00", end="2026-09-14T10:00:00+08:00")
        self.create(kind="event", start="2026-09-11T09:00:00+08:00", end="2026-09-12T00:00:00+08:00")
        self.create(allDay=True, start="2026-09-11", end="2026-09-14")
        self.store.advance("2026-09-15")
        result = self.view()["items"]
        self.assertEqual(len(result), 2)
        self.assertTrue(all(x["timeState"] == "ongoing" for x in result))
        self.assertEqual(next(x for x in result if x["item"]["allDay"])["item"]["start"], "2026-09-11")

    def test_old_uncompleted_and_bounded_catchup(self):
        self.create(start="2010-01-01T09:00:00+08:00", end="2010-01-01T10:00:00+08:00",
                    recurrence={"frequency":"monthly", "count":2})
        result = self.store.advance("2026-09-15", budget=10)
        self.assertFalse(result["complete"])
        self.assertEqual(result["evaluatedDays"], 10)
        self.store.advance("2026-09-15")
        result = self.view()["items"]
        self.assertEqual(len(result), 2)
        self.assertTrue(all(x["overdue"] for x in result))

    def test_deadline_date_does_not_expire_at_midnight(self):
        item = {"title":"Deadline", "kind":"deadline", "allDay":True,"due":"2026-09-12","timezone":"Asia/Taipei"}
        self.store.mutate(self.command("create", item=item))
        self.store.advance("2026-09-15")
        self.assertFalse(self.view()["items"][0]["overdue"])
        later = self.store.view("2026-09-13", "2026-09-14", "Asia/Taipei", as_of="2026-09-13T00:00:00+08:00")
        self.assertTrue(later["items"][0]["overdue"])

    def test_single_exception_identity_and_completion(self):
        record = self.create(recurrence={"frequency":"daily", "count":3})
        self.store.advance("2026-09-17")
        updated = self.edit(record, scope="this", occurrenceDate="2026-09-12", item=event(start="2026-09-13T13:00:00+08:00",end="2026-09-13T14:00:00+08:00"))
        rows = self.view("2026-09-13", "2026-09-14")["items"]
        moved = next(x for x in rows if x["occurrenceDate"] == "2026-09-12")
        self.assertEqual(moved["scheduleId"], record["id"])
        self.assertEqual(len(rows), 2)
        completed = self.edit(updated, "complete", scope="this", occurrenceDate="2026-09-12")
        self.assertEqual(self.store.get(record["id"])["revision"], completed["revision"])
        with self.assertRaises(ScheduleConflict):
            self.edit(completed, item=event(start="2026-09-12T11:00:00+08:00",end="2026-09-12T12:00:00+08:00"))

    def test_future_split_no_duplicate_and_cancel(self):
        record = self.create(recurrence={"frequency":"daily", "count":5})
        self.store.advance("2026-09-20")
        changed = self.edit(record, scope="future", occurrenceDate="2026-09-14", item=event(start="2026-09-14T11:00:00+08:00", end="2026-09-14T12:00:00+08:00", recurrence={"frequency":"daily","count":3}))
        self.store.advance("2026-09-20")
        rows = self.view("2026-09-12", "2026-09-18")["items"]
        self.assertEqual(len(rows), 5)
        self.assertEqual(len({x["id"] for x in rows}), 5)
        self.edit(changed["successor"], "cancel")
        self.assertEqual(len(self.view("2026-09-12", "2026-09-18")["items"]), 2)

    def test_weekly_monthly_rules(self):
        self.create(start="2026-01-31T09:00:00+08:00",end="2026-01-31T10:00:00+08:00", recurrence={"frequency":"monthly", "count":2})
        self.store.advance("2026-09-15")
        self.assertEqual([x["occurrenceDate"] for x in self.view()["items"]], ["2026-01-31", "2026-03-31"])
        weekly = self.create(kind="event",recurrence={"frequency":"weekly","interval":2,"weekdays":[0,2]})
        self.store.advance("2026-10-02")
        rows = [x for x in self.view("2026-09-12","2026-10-01")["items"] if x["scheduleId"] == weekly["id"]]
        self.assertEqual([x["occurrenceDate"] for x in rows], ["2026-09-21","2026-09-23"])

    def test_dst_gap_and_fold(self):
        record = self.create(timezone="America/New_York",start="2026-03-07T02:30:00-05:00",end="2026-03-07T03:30:00-05:00", recurrence={"frequency":"daily","count":3})
        self.store.advance("2026-03-12")
        with self.store.connect() as conn:
            rows = conn.execute("SELECT original_date,reason FROM schedule_occurrences WHERE item_id=? ORDER BY original_date",(record["id"],)).fetchall()
        self.assertEqual(rows[1]["reason"], "dst_gap")
        with self.assertRaises(ValueError):
            validate_item(event(timezone="America/New_York",start="2026-03-08T02:30:00-05:00",end="2026-03-08T03:30:00-04:00"))

    def test_restart_pagination_and_rollback(self):
        record = self.create(recurrence={"frequency":"daily", "count":4})
        self.store.advance("2026-09-20")
        with patch.object(self.store, "_public", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                self.edit(record, "cancel")
        self.assertFalse(ScheduleStore(self.path).get(record["id"])["cancelled"])
        page = self.view("2026-09-12","2026-09-18",limit=2)
        second = self.view("2026-09-12","2026-09-18",limit=2,offset=page["nextOffset"])
        self.assertEqual(len({x["id"] for x in page["items"]+second["items"]}), 4)

    def test_completion_invalidates_only_its_own_pending_notification(self):
        record = self.create(recurrence={"frequency":"daily","count":2})
        self.store.advance("2026-09-17")
        with self.store.connect(write=True) as conn:
            for original in ("2026-09-12","2026-09-13"):
                conn.execute("INSERT INTO schedule_notification_deliveries(id,item_id,original_date,rule_revision,channel,state) VALUES(?,?,?,1,'panel','pending')", (original,record["id"],original))
        self.edit(record,"complete",scope="this",occurrenceDate="2026-09-12")
        with self.store.connect() as conn:
            rows = conn.execute("SELECT state FROM schedule_notification_deliveries ORDER BY original_date").fetchall()
        self.assertEqual([r["state"] for r in rows],["cancelled","pending"])

    def test_until_and_cancelled_exception_remain_stable_on_catchup(self):
        record = self.create(recurrence={"frequency":"daily","until":"2026-09-14"})
        self.store.advance("2026-09-17")
        self.edit(record,"cancel",scope="this",occurrenceDate="2026-09-13")
        self.store.advance("2026-09-20")
        self.assertEqual([r["occurrenceDate"] for r in self.view("2026-09-12","2026-09-18")["items"]],["2026-09-12","2026-09-14"])

    def test_view_timezone_differs_from_series_timezone(self):
        self.create(kind="event",start="2026-09-13T00:30:00+08:00",end="2026-09-13T01:30:00+08:00")
        self.store.advance("2026-09-17")
        self.assertEqual(self.view()["items"],[])
        utc_view = self.store.view("2026-09-12","2026-09-13","UTC",as_of="2026-09-12T12:00:00Z")
        self.assertEqual(len(utc_view["items"]),1)

    def test_actual_v1_backup_can_restore_observation_store(self):
        # A fresh initialization produces a complete v1 schema backup before v2.
        backup = next(Path(self.temp.name).glob("core.sqlite3.pre-v2-*.bak"))
        restored = Path(self.temp.name)/"restored.sqlite3"
        with sqlite3.connect(backup) as src, sqlite3.connect(restored) as dst:
            src.backup(dst)
        core = KuroCoreStore(restored)
        core.initialize()
        self.assertEqual(core.schema_version(),3)
        self.assertEqual(core.list_observations(),[])

    def test_dst_fold_uses_earlier_instant_for_generated_occurrences(self):
        self.create(kind="event",timezone="America/New_York",start="2026-10-31T01:30:00-04:00",end="2026-10-31T02:30:00-04:00",recurrence={"frequency":"daily","count":2})
        self.store.advance("2026-11-05")
        result = self.store.view("2026-11-01","2026-11-02","America/New_York",as_of="2026-11-01T00:00:00-04:00")
        self.assertTrue(result["items"][0]["item"]["start"].endswith("-04:00"))
        self.assertTrue(result["items"][0]["item"]["end"].endswith("-05:00"))


if __name__ == "__main__":
    unittest.main()
