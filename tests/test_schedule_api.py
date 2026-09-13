import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from kuro_core.schedule_api import ScheduleServer


class ScheduleApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.token = "s"*40
        self.server = ScheduleServer(Path(self.temp.name)/"db.sqlite3", port=0, token=self.token, instance_id="test")
        self.server.start()
        self.addCleanup(self.server.stop)

    def request(self, path, payload=None, **headers):
        req = urllib.request.Request(f"http://127.0.0.1:{self.server.port}{path}",
                                     data=json.dumps(payload).encode() if payload is not None else None,
                                     headers={"Authorization": f"Bearer {self.token}","Content-Type":"application/json", **headers})
        try:
            result = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=3)
        except urllib.error.HTTPError as exc:
            result = exc
        with result:
            return result.code, json.load(result)

    def test_identity_auth_origin_and_unknown_route(self):
        code, status = self.request("/status")
        self.assertEqual(code, 200)
        self.assertEqual(status["instanceId"], "test")
        self.assertEqual(status["schema"], 3)
        self.assertEqual(self.request("/status", Authorization="Bearer wrong")[0],401)
        self.assertEqual(self.request("/status", Origin="https://example.invalid")[0],401)
        self.assertEqual(self.request("/v1/unknown")[0],404)

    def test_mutation_errors_and_read_no_write(self):
        self.assertEqual(self.request("/v1/schedule/mutate",[])[0],400)
        self.assertEqual(self.request("/v1/schedule/mutate",{"action":"create"})[0],403)
        command = {"action":"create","confirmed":True,"idempotencyKey":"one","item":{
            "title":"Test","kind":"event","timezone":"Asia/Taipei","allDay":True,"start":"2026-09-12","end":"2026-09-14"}}
        code, created = self.request("/v1/schedule/mutate", command)
        self.assertEqual(code,200)
        code, replay = self.request("/v1/schedule/mutate",command)
        self.assertEqual(created,replay)
        conflict = {"action":"cancel","id":created["id"],"expectedRevision":99,"confirmed":True,"idempotencyKey":"two"}
        self.assertEqual(self.request("/v1/schedule/mutate",conflict)[0],409)
        self.assertEqual(self.request("/v1/schedule/materialize",{"through":"2026-09-16"})[0],200)
        with patch.object(self.server.store,"advance",side_effect=AssertionError("GET wrote")):
            code, view = self.request("/v1/schedule/view?start=2026-09-12&end=2026-09-13&timezone=Asia%2FTaipei")
        self.assertEqual(code,200)
        self.assertEqual(len(view["items"]),1)
        self.assertEqual(self.request("/v1/schedule/view?start=bad&end=bad&timezone=UTC")[0],400)

    def test_bind_collision_does_not_touch_another_database(self):
        other = Path(self.temp.name)/"other.sqlite3"
        with self.assertRaises(OSError):
            ScheduleServer(other, port=self.server.port, token=self.token, instance_id="second")
        self.assertFalse(other.exists())

    def test_saved_mutation_survives_projection_failure(self):
        command = {"action":"create","confirmed":True,"idempotencyKey":"projection-retry","item":{
            "title":"Saved once","kind":"deadline","timezone":"UTC","allDay":True,"due":"2026-09-12"}}
        with patch.object(self.server.store,"advance",side_effect=RuntimeError("projection unavailable")):
            with self.assertLogs("kuro_core.schedule_api",level="ERROR"):
                code, saved = self.request("/v1/schedule/mutate",command)
        self.assertEqual(code,200)
        self.assertEqual(saved["projection"],"pending")
        self.assertEqual(self.request("/v1/schedule/item?id="+saved["id"])[1]["item"]["title"],"Saved once")
        self.assertEqual(self.request("/v1/schedule/mutate",command)[1]["id"],saved["id"])

    def test_same_database_cannot_run_on_second_port(self):
        with self.assertRaises(OSError):
            ScheduleServer(self.server.store.path, port=0, token=self.token, instance_id="second")

    def test_restart_recovers_saved_state(self):
        self.request("/v1/schedule/mutate",{"action":"create","confirmed":True,"idempotencyKey":"persist","item":{
            "title":"Retained","kind":"deadline","timezone":"UTC","allDay":True,"due":"2026-09-12"}})
        path = self.server.store.path
        self.server.stop()
        self.server = ScheduleServer(path,port=0,token=self.token,instance_id="restarted")
        self.server.start()
        self.addCleanup(self.server.stop)
        self.request("/v1/schedule/materialize",{"through":"2026-09-16"})
        code, view = self.request("/v1/schedule/view?start=2026-09-12&end=2026-09-13&timezone=UTC")
        self.assertEqual(code,200)
        self.assertEqual(view["items"][0]["item"]["title"],"Retained")


if __name__ == "__main__":
    unittest.main()
