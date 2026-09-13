import tempfile
import unittest
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from kuro_core.storage import KuroCoreStore
from kuro_core.schedule_store import ScheduleStore
from kuro_core.schedule_contract import ScheduleConflict, prepare_item
from kuro_core.schedule_notifications import ScheduleNotifications


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"core.sqlite3";KuroCoreStore(self.path).initialize()
        self.store=ScheduleStore(self.path);self.notifications=ScheduleNotifications(self.store,"Asia/Taipei")
        self.item={"title":"提醒測試","kind":"study","timezone":"Asia/Taipei","start":"2026-09-12T09:00:00+08:00","end":"2026-09-12T10:00:00+08:00","notification":{"enabled":True,"minutesBefore":10,"channel":"desktop"}}
        self.record=self.store.mutate({"action":"create","confirmed":True,"idempotencyKey":"new","item":self.item})
        self.store.advance("2026-09-18")
        self.now="2026-09-12T08:50:00+08:00"

    def action(self,action,now=None,**kwargs):
        return self.notifications.action(dict(action=action,**kwargs),now=now or self.now)

    def tick(self,now=None):self.notifications.tick(now=now or self.now)

    def claim(self):
        self.tick();return self.action("claim")["delivery"]

    def test_disabled_never_produces_reminder(self):
        self.item["notification"]["enabled"]=False
        self.store.mutate({"action":"update","id":self.record["id"],"expectedRevision":1,"confirmed":True,"idempotencyKey":"disabled","item":self.item})
        self.tick();self.assertEqual(self.notifications.read()["items"],[])

    def test_due_delivery_ack_and_no_replay(self):
        self.tick("2026-09-12T08:49:59+08:00");self.assertIsNone(self.action("claim")["delivery"])
        delivery=self.claim();self.assertIsNotNone(delivery)
        self.assertIsNone(self.action("claim")["delivery"])
        self.assertEqual(self.action("authorize",**delivery)["state"],"dispatching")
        self.assertEqual(self.action("ack",**delivery,result="delivered")["state"],"delivered")
        self.tick();self.assertIsNone(self.action("claim")["delivery"])

    def test_claim_lease_recovers_but_dispatch_unknown_does_not_retry(self):
        first=self.claim();self.tick("2026-09-12T08:50:21+08:00")
        second=self.action("claim",now="2026-09-12T08:50:21+08:00")["delivery"]
        self.assertNotEqual(first["leaseToken"],second["leaseToken"])
        with self.assertRaises(ScheduleConflict):self.action("authorize",**first)
        self.action("authorize",now="2026-09-12T08:50:22+08:00",**second)
        self.tick("2026-09-12T08:50:45+08:00")
        self.assertEqual(self.notifications.read()["items"][0]["state"],"unknown")
        self.assertIsNone(self.action("claim",now="2026-09-12T08:50:45+08:00")["delivery"])

    def test_quiet_and_missed_window(self):
        self.action("preferences",confirmed=True,preferences={"timezone":"Asia/Taipei","quietEnabled":True,"quietStart":"08:00","quietEnd":"09:00"})
        self.tick();self.assertEqual(self.notifications.read()["items"][0]["state"],"suppressed")
        self.assertIsNone(self.action("claim")["delivery"])
        self.tick("2026-09-12T09:31:00+08:00");self.assertEqual(self.notifications.read()["items"][0]["state"],"missed")

    def test_quiet_ending_releases_recent_candidate(self):
        self.action("preferences",confirmed=True,preferences={"timezone":"Asia/Taipei","quietEnabled":True,"quietStart":"08:00","quietEnd":"08:55"})
        self.tick();self.tick("2026-09-12T08:55:00+08:00")
        self.assertEqual(self.notifications.read()["items"][0]["state"],"ready")

    def test_snooze_dismiss_and_restart(self):
        delivery=self.claim();self.action("authorize",**delivery);self.action("ack",**delivery,result="delivered")
        self.action("snooze",id=delivery["id"],confirmed=True,until="2026-09-12T09:10:00+08:00")
        self.notifications=ScheduleNotifications(ScheduleStore(self.path),"Asia/Taipei")
        self.tick("2026-09-12T09:00:00+08:00");self.assertEqual(self.notifications.read()["items"][0]["state"],"snoozed")
        self.tick("2026-09-12T09:10:00+08:00");self.assertEqual(self.notifications.read()["items"][0]["state"],"ready")
        self.action("dismiss",now="2026-09-12T09:10:00+08:00",id=delivery["id"],confirmed=True)
        self.tick("2026-09-12T09:11:00+08:00");self.assertEqual(self.notifications.read()["items"],[])

    def test_cancel_after_claim_prevents_dispatch(self):
        delivery=self.claim()
        self.store.mutate({"action":"cancel","id":self.record["id"],"expectedRevision":1,"confirmed":True,"idempotencyKey":"cancel"})
        with self.assertRaises(ScheduleConflict):self.action("authorize",**delivery)

    def test_multiple_consumers_only_one_claim(self):
        self.tick()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.action("claim")["delivery"],range(8)))
        self.assertEqual(sum(r is not None for r in results),1)

    def test_invalid_preferences_and_snooze(self):
        with self.assertRaises(PermissionError):self.action("preferences",confirmed=False,preferences={})
        with self.assertRaises(ValueError):self.action("preferences",confirmed=True,preferences={"timezone":"UTC","quietEnabled":True,"quietStart":"08:00","quietEnd":"08:00"})
        delivery=self.claim();self.action("authorize",**delivery);self.action("ack",**delivery,result="failed")
        with self.assertRaises(ValueError):self.action("snooze",id=delivery["id"],confirmed=True,until="2026-09-01T00:00:00Z")

    def test_backend_prepares_wall_time_and_rejects_dst_gap(self):
        item=dict(self.item,start="2026-09-12T09:00",end="2026-09-12T10:00")
        self.assertTrue(prepare_item(item)["start"].endswith("+08:00"))
        with self.assertRaises(ValueError):prepare_item(dict(item,timezone="America/New_York",start="2026-03-08T02:30",end="2026-03-08T04:00"))
