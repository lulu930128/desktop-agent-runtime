import socket
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace
from unittest.mock import Mock, patch

from kuro_launcher.core_runtime import CoreRuntime
from kuro_launcher.config import load_config

ROOT = Path(__file__).resolve().parents[1]


class CoreRuntimeTests(unittest.TestCase):
    def test_config_is_scoped_and_disabled_rollback_does_not_start(self):
        cfg = load_config(ROOT/"kuro_launcher.settings.yaml")
        self.assertEqual(cfg.core_db_path, ROOT/"local_state/core/work.sqlite3")
        self.assertEqual(cfg.core_timezone,"Asia/Taipei")
        runtime = CoreRuntime(replace(cfg,core_enabled=False), lambda _: None)
        self.assertFalse(runtime.start())
        self.assertEqual(runtime.child_environment(), {})

    def test_actual_isolated_child_identity_and_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1",0))
                port = sock.getsockname()[1]
            cfg = SimpleNamespace(core_enabled=True, core_port=port, core_db_path=Path(tmp)/"work.sqlite3",
                                  root=ROOT, env_llm=ROOT/"envs/kuro-llm310", logs_dir=Path(tmp)/"logs")
            runtime = CoreRuntime(cfg, lambda _: None)
            try:
                self.assertTrue(runtime.start())
                proc = runtime.proc.popen
                status = runtime.ready()
                self.assertEqual(status["pid"],proc.pid)
                self.assertNotIn(runtime.token, " ".join(proc.args))
                self.assertEqual(runtime.child_environment()["KURO_CORE_INSTANCE"],status["instanceId"])
                self.assertTrue(runtime.start())
                self.assertIs(runtime.proc.popen,proc)
                runtime.request("/v1/schedule/mutate",{"action":"create","confirmed":True,"idempotencyKey":"one","item":{
                    "title":"Synthetic","kind":"deadline","allDay":True,"due":"2026-09-12","timezone":"UTC"}})
                runtime.stop()
                self.assertIsNotNone(proc.poll())
                self.assertTrue(runtime.start())
                self.assertNotEqual(runtime.proc.popen.pid,proc.pid)
                runtime.request("/v1/schedule/materialize",{"through":"2026-09-16"})
                result = runtime.request("/v1/schedule/view?start=2026-09-12&end=2026-09-13&timezone=UTC")
                self.assertEqual(result["items"][0]["item"]["title"],"Synthetic")
            finally:
                runtime.stop()

    def test_refuses_unknown_listener_without_spawning(self):
        cfg = SimpleNamespace(core_enabled=True,core_port=1)
        runtime = CoreRuntime(cfg, lambda _: None)
        with patch("kuro_launcher.core_runtime.port_is_open",return_value=True), patch("kuro_launcher.core_runtime.subprocess.Popen") as spawn:
            with self.assertRaises(RuntimeError):
                runtime.start()
            spawn.assert_not_called()

    def test_launcher_close_stops_core_even_if_profile_shutdown_fails(self):
        import launcher_qt  # Configure the existing vendored runtime import path.
        from kuro_launcher.qt_controller import QtLauncherController
        controller = QtLauncherController.__new__(QtLauncherController)
        controller.stop_profile = Mock(side_effect=RuntimeError("profile failure"))
        controller.core_runtime = Mock()
        with self.assertRaises(RuntimeError):
            controller.close()
        controller.core_runtime.stop.assert_called_once_with()
