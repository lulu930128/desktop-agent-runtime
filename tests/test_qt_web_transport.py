"""Actual Qt client over disposable loopback WS + Core HTTP; no private IO."""
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from PySide6.QtCore import QObject, Signal, Slot, Qt
from PySide6.QtWidgets import QApplication
from kuro_launcher.qt_chat_client import QtRuntimeChatClient
from kuro_launcher.qt_web_adapter import QtOwnerAdapter
from kuro_launcher.qt_web_protocol import RequestBroker, CONTRACT
from kuro_launcher.qt_controller import QtLauncherController
from kuro_launcher.core_runtime import CoreRuntime
from kuro_core.api_server import CoreApiServer
from web_candidate_fixtures import controller_fixture, core_today


class Inbox(QObject):
    def __init__(self, adapter): super().__init__(); self.adapter = adapter
    @Slot(dict)
    def receive(self, value): self.adapter.receive(value)
    @Slot(str, bool)
    def state(self, value, connected): self.adapter.on_state(value, connected)


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def until(self, predicate):
        deadline = time.monotonic()+5
        while time.monotonic()<deadline:
            self.app.processEvents()
            if predicate(): return
            time.sleep(.005)
        self.fail("SYNTHETIC transport timeout")

    def test_real_qt_primary_ws_history_stream_interrupt_and_stale(self):
        from web_candidate_fixtures import SyntheticConversation
        server = SyntheticConversation()
        server.start()
        ports, received, roles = [server.port], server.received, server.roles
        client=QtRuntimeChatClient()
        adapter=QtOwnerAdapter(controller_fixture(),client,lambda w,d:d(w()),window_action=Mock())
        inbox=Inbox(adapter)
        client.message_received.connect(inbox.receive,Qt.ConnectionType.QueuedConnection)
        client.state_changed.connect(inbox.state,Qt.ConnectionType.QueuedConnection)
        replies=[]; confirm=Mock(return_value=True)
        broker=RequestBroker(adapter,confirm,replies.append)
        seq=0
        def call(method,payload=None):
            nonlocal seq
            seq+=1; before=len(replies)
            broker.submit(json.dumps(dict(contract=CONTRACT,id=f"t{seq}",expected=adapter.identity(),method=method,payload=payload or {})))
            self.until(lambda:len(replies)>before)
            return replies[-1]["result"]
        try:
            client.connect_to(f"ws://127.0.0.1:{ports[0]}/client-ws?client_role=qt-primary")
            self.until(lambda:client.history_ready)
            result=call("getHistories")
            self.assertTrue(result["ok"],result)
            self.assertEqual(result["messages"][0]["role"],"event")
            self.assertEqual(result["histories"][0]["uid"],"h1")
            self.assertTrue(call("sendText",{"text":"SYNTHETIC question","attachments":[]})["ok"])
            self.until(lambda:len(adapter.timeline)==1 and adapter.state=="idle")
            self.assertEqual(adapter.latest_assistant,"SYNTHETIC reply")
            self.assertTrue(call("control",{"action":"interrupt","payload":{}})["ok"])
            self.assertTrue(call("createHistory")["ok"])
            self.assertTrue(call("selectHistory",{"historyUid":"h1"})["ok"])
            self.assertTrue(call("deleteHistory",{"historyUid":"h1"})["ok"])
            confirm.assert_called_once()
            self.assertEqual(len(roles),1);self.assertIn("qt-primary",roles[0])
            self.assertNotIn("pet-presentation",roles[0])
            self.assertTrue(all("context_id" in row for row in received))
        finally:
            broker.close();client.disconnect()
            if client._thread:client._thread.join(3)
            server.close()
            self.assertFalse(server.thread.is_alive())

    def test_real_disposable_core_http_no_materialize_write(self):
        api=CoreApiServer(port=0,token="synthetic-web-candidate-token-000000")
        actions=[]
        api.register("GET","/v1/today",lambda query:core_today())
        api.register("GET","/status",lambda query:{"contract":"kuro.core.api.v1","capabilities":{"schedule":{"contract":"kuro.core.schedule.v1","today":"2026-10-10","timezone":"UTC"}}})
        api.register("GET","/v1/schedule/view",lambda query:{"items":[],"coverage":"incomplete","limitations":["materialization_pending"]})
        api.register("GET","/v1/schedule/notifications",lambda query:{"items":[]})
        api.register("POST","/v1/schedule/materialize",lambda p:actions.append(p) or {})
        api.register("POST","/v1/schedule/mutate",lambda p:actions.append(p) or {"revision":2})
        api.start()
        c=QtLauncherController.__new__(QtLauncherController)
        c.core_runtime=CoreRuntime(SimpleNamespace(core_enabled=True,core_port=api.port),lambda _:None)
        c.core_runtime.token="synthetic-web-candidate-token-000000"
        from web_candidate_fixtures import ChatFixture
        adapter=QtOwnerAdapter(c,ChatFixture(),lambda w,d:d(w()),window_action=Mock())
        replies=[];broker=RequestBroker(adapter,lambda *_:False,replies.append)
        def call(method,payload):
            broker.submit(json.dumps(dict(contract=CONTRACT,id=f"h{len(replies)}",expected=adapter.identity(),method=method,payload=payload)))
            return replies[-1]["result"]
        try:
            self.assertEqual(call("getData",{})["canonical"],{"ok":True,**core_today()})
            for action,payload in (("status",{}),("materialize",{"through":"2026-10-12"}),
                ("view",{"start":"2026-10-10","end":"2026-10-11","timezone":"UTC"}),("notifications",{})):
                result=call("schedule",{"action":action,"payload":payload})
                self.assertEqual(result["ok"],action!="materialize")
            result=call("schedule",{"action":"mutate","payload":{"action":"create","item":{},"idempotencyKey":"synthetic","confirmed":True}})
            self.assertTrue(result["cancelled"]);self.assertEqual(actions,[])
        finally:api.stop()


if __name__=="__main__":unittest.main()
