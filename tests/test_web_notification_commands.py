"""Core notification command transaction tests in a disposable schema-v3 DB."""
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import threading
import unittest
from kuro_core.storage import KuroCoreStore
from kuro_core.schedule_store import ScheduleStore
from kuro_core.schedule_notifications import ScheduleNotifications, CONSUMER_COMMAND_CONTRACT
from kuro_core.schedule_contract import ScheduleConflict

ROOT=Path(__file__).resolve().parents[1]


class NotificationCommands(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(prefix=".validation-web-notice-",dir=ROOT)
        self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/"synthetic.sqlite3"
        KuroCoreStore(self.path).initialize()
        self.store=ScheduleStore(self.path)
        self.notices=ScheduleNotifications(self.store,"UTC")
        self.now=datetime(2026,10,10,12,0,tzinfo=timezone.utc)
        self.preferences={"timezone":"UTC","quietEnabled":False,"quietStart":"22:00","quietEnd":"08:00"}
        self.notices.action({"action":"preferences","confirmed":True,"preferences":self.preferences},now=self.now.isoformat())
        self.store.mutate({"action":"create","confirmed":True,"idempotencyKey":"synthetic-create","item":{
            "title":"SYNTHETIC","kind":"study","timezone":"UTC","start":"2026-10-10T12:00:00+00:00","end":"2026-10-10T13:00:00+00:00",
            "notification":{"enabled":True,"minutesBefore":0,"channel":"desktop"}}})
        self.store.advance("2026-10-11");self.notices.tick(now=self.now.isoformat())

    def payload(self,action="dismiss",key="key"):
        snapshot=self.notices.read()
        if action=="preferences": command={"action":action,"confirmed":True,"preferences":{**self.preferences,"quietEnabled":True}};revision=snapshot["preferencesRevision"]
        else:
            row=snapshot["items"][0]
            command={"action":action,"confirmed":True,"id":row["id"]}
            if action=="snooze":command["until"]=(self.now+timedelta(minutes=10)).isoformat()
            revision=row["revision"]
        return {"command":command,"expectedRevision":revision,"idempotencyKey":key}

    def count(self,table):
        with self.store.connect() as conn:return conn.execute("SELECT COUNT(*) FROM "+table).fetchone()[0]

    def test_read_is_read_only_and_exposes_revision_not_lease(self):
        before=self.path.read_bytes();snapshot=self.notices.read()
        self.assertEqual(before,self.path.read_bytes())
        self.assertEqual(snapshot["consumerWriteContract"],CONSUMER_COMMAND_CONTRACT)
        self.assertEqual(len(snapshot["preferencesRevision"]),64)
        self.assertEqual(len(snapshot["items"][0]["revision"]),64)
        self.assertNotIn("leaseToken",snapshot["items"][0])

    def test_dismiss_exact_replay_no_second_audit(self):
        p=self.payload();first=self.notices.command(p,now=self.now.isoformat());count=self.count("schedule_notification_audit")
        self.assertEqual(self.notices.command(p,now=(self.now+timedelta(seconds=1)).isoformat()),first)
        self.assertEqual(self.count("schedule_notification_audit"),count)
        self.assertEqual(first["state"],"dismissed")

    def test_snooze_idempotent_and_different_payload_same_key_conflicts(self):
        p=self.payload("snooze");first=self.notices.command(p,now=self.now.isoformat())
        self.assertEqual(first["state"],"snoozed")
        self.assertEqual(self.notices.command(p,now=self.now.isoformat()),first)
        p["command"]["until"]=(self.now+timedelta(minutes=20)).isoformat()
        with self.assertRaises(ScheduleConflict):self.notices.command(p,now=self.now.isoformat())

    def test_preferences_revision_prevents_lost_update(self):
        first=self.payload("preferences","a");second=self.payload("preferences","b")
        self.notices.command(first,now=self.now.isoformat())
        with self.assertRaises(ScheduleConflict):self.notices.command(second,now=self.now.isoformat())
        self.assertTrue(self.notices.read()["preferences"]["quietEnabled"])

    def test_tray_claim_changes_revision_and_consumer_cannot_authorize(self):
        p=self.payload()
        delivery=self.notices.action({"action":"claim"},now=self.now.isoformat())["delivery"]
        self.assertIsNotNone(delivery)
        with self.assertRaises(ScheduleConflict):self.notices.command(p,now=self.now.isoformat())
        p["command"]={"action":"claim"}
        with self.assertRaises(PermissionError):self.notices.command(p,now=self.now.isoformat())

    def test_no_confirmation_no_receipt_or_write(self):
        p=self.payload();p["command"]["confirmed"]=False
        before=self.path.read_bytes()
        with self.assertRaises(PermissionError):self.notices.command(p,now=self.now.isoformat())
        self.assertEqual(before,self.path.read_bytes())

    def test_invalid_action_rolls_back_receipt_and_audit(self):
        p=self.payload("snooze");p["command"]["until"]=(self.now-timedelta(minutes=1)).isoformat()
        counts=(self.count("schedule_mutations"),self.count("schedule_notification_audit"))
        with self.assertRaises(ValueError):self.notices.command(p,now=self.now.isoformat())
        self.assertEqual(counts,(self.count("schedule_mutations"),self.count("schedule_notification_audit")))

    def test_concurrent_same_command_applies_once(self):
        p=self.payload();outcomes=[];before=self.count("schedule_notification_audit")
        def run():
            try:outcomes.append(self.notices.command(copy.deepcopy(p),now=self.now.isoformat()))
            except Exception as exc:outcomes.append(exc)
        threads=[threading.Thread(target=run) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join(4)
        self.assertEqual(outcomes,[{"state":"dismissed"}]*2)
        self.assertEqual(self.count("schedule_notification_audit"),before+1)

    def test_actual_controller_http_command_replay_and_conflict(self):
        from types import SimpleNamespace
        from kuro_core.api_server import CoreApiServer
        from kuro_core.schedule_api import ScheduleCapability
        from kuro_launcher.core_runtime import CoreRuntime
        from kuro_launcher.qt_controller import QtLauncherController
        api = CoreApiServer(port=0, token="synthetic-notification-command-token-0000")
        # Attach the disposable store without starting the scheduler worker.
        capability = ScheduleCapability.__new__(ScheduleCapability)
        capability.store, capability.notifications = self.store, self.notices
        capability.timezone = "UTC"
        capability.register_routes(api); api.start()
        self.addCleanup(api.stop)
        controller = QtLauncherController.__new__(QtLauncherController)
        controller.core_runtime = CoreRuntime(SimpleNamespace(core_enabled=True, core_port=api.port), lambda _: None)
        controller.core_runtime.token = "synthetic-notification-command-token-0000"
        p = self.payload()
        self.assertEqual(controller.schedule_notification_command(p)["state"], "dismissed")
        count = self.count("schedule_notification_audit")
        self.assertEqual(controller.schedule_notification_command(p)["state"], "dismissed")
        self.assertEqual(count, self.count("schedule_notification_audit"))
        p["idempotencyKey"] = "stale-revision"
        with self.assertRaisesRegex(RuntimeError, "409"):
            controller.schedule_notification_command(p)


if __name__=="__main__":unittest.main()
