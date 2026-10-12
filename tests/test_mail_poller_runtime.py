from dataclasses import replace
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import yaml
from kuro_launcher.config import load_config
from kuro_launcher.core_runtime import CoreRuntime
from kuro_launcher.mail_poller_runtime import MailPollerRuntime
from g2_fixtures import ROOT, load_producer, status_writer


class MailPollerRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = SimpleNamespace(core_enabled=True, core_mail_enabled=True,
            core_mail_status_path=self.root / "status.json", core_mail_work_path=self.root / "work.json",
            root=self.root, open_llm_dir=self.root / "producer", env_llm=ROOT / "envs/kuro-llm310",
            pet_control_host="127.0.0.1", pet_control_port=12345, core_port=12346)

    def test_single_exact_child_environment_and_stop(self):
        child = Mock(pid=99)
        child.poll.return_value = None
        with patch("kuro_launcher.mail_poller_runtime.subprocess.Popen", return_value=child) as spawn, \
             patch.dict(os.environ, {"KURO_MAIL_STATUS_FILE": "inherited-status",
                 "KURO_MAIL_WORK_FILE": "inherited-work", "KURO_MAIL_POLLER_OWNER": "electron"}):
            runtime = MailPollerRuntime(self.cfg, Mock())
            self.assertTrue(runtime.start())
            self.assertTrue(runtime.start())
            spawn.assert_called_once()
            env = spawn.call_args.kwargs["env"]
            self.assertEqual(env["KURO_MAIL_POLLER_OWNER"], "launcher")
            self.assertEqual(env["KURO_MAIL_WORK_FILE"], str(self.cfg.core_mail_work_path))
            self.assertEqual(env["KURO_MAIL_STATUS_FILE"], str(self.cfg.core_mail_status_path))
            self.assertEqual(spawn.call_args.args[0][-1], str(self.cfg.open_llm_dir / "local_mcp/mail_poller.py"))
            self.assertNotIn("--once", spawn.call_args.args[0])
            runtime.stop()
            runtime.stop()
            child.terminate.assert_called_once()
            child.wait.assert_called_once_with(timeout=4)
            self.assertIsNone(runtime.proc)

    def test_disabled_never_spawns_or_injects_handoffs_but_blocks_electron_owner(self):
        for field in ("core_enabled", "core_mail_enabled"):
            cfg = SimpleNamespace(**{**vars(self.cfg), field: False})
            runtime = MailPollerRuntime(cfg, Mock())
            with patch("kuro_launcher.mail_poller_runtime.subprocess.Popen") as spawn:
                self.assertFalse(runtime.start())
                spawn.assert_not_called()
            self.assertEqual(runtime.child_environment(), {"KURO_MAIL_POLLER_OWNER": "launcher"})

    def test_stop_timeout_escalates_only_exact_child(self):
        runtime = MailPollerRuntime(self.cfg, Mock())
        runtime.proc = Mock()
        child = runtime.proc
        child.poll.return_value = None
        child.wait.side_effect = [subprocess.TimeoutExpired("synthetic", 4), 0]
        runtime.stop()
        child.terminate.assert_called_once()
        child.kill.assert_called_once()
        self.assertEqual(child.wait.call_count, 2)

    def test_actual_synthetic_child_lifecycle_does_not_run_provider(self):
        script = self.cfg.open_llm_dir / "local_mcp/mail_poller.py"
        script.parent.mkdir(parents=True)
        script.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
        runtime = MailPollerRuntime(self.cfg, Mock())
        try:
            self.assertTrue(runtime.start())
            child = runtime.proc
            self.assertIsNone(child.poll())
            self.assertTrue(runtime.start())
            self.assertIs(runtime.proc, child)
        finally:
            runtime.stop()
        self.assertIsNotNone(child.poll())
        self.assertFalse(self.cfg.core_mail_status_path.exists())
        self.assertFalse(self.cfg.core_mail_work_path.exists())

    def test_configuration_canonical_work_path_bounds_and_missing_handoff(self):
        source = yaml.safe_load((ROOT / "kuro_launcher.settings.yaml").read_text(encoding="utf-8"))
        mail = source["core"]["integrations"]["mail"]
        mail.update(enabled=True, status_path=str(self.root / "status.json"), work_path=str(self.root / "work.json"))
        path = self.root / "settings.yaml"
        path.write_text(yaml.safe_dump(source), encoding="utf-8")
        cfg = load_config(path)
        self.assertEqual(cfg.core_mail_work_path, self.root / "work.json")
        self.assertEqual(CoreRuntime(cfg, Mock()).child_environment()["KURO_MAIL_WORK_FILE"], str(cfg.core_mail_work_path))
        for value in (None, "", "${UNRESOLVED}/work.json", 12, str(cfg.core_mail_status_path)):
            mail["work_path"] = value
            path.write_text(yaml.safe_dump(source), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(path)
        mail["work_path"] = str(cfg.core_mail_work_path)
        for value in (True, 0, 2097153, "100"):
            mail["work_max_bytes"] = value
            path.write_text(yaml.safe_dump(source), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(path)
        self.assertFalse(cfg.core_mail_work_path.exists())

    def test_launcher_close_stops_mail_and_core_when_profile_raises(self):
        import launcher_qt
        from kuro_launcher.qt_controller import QtLauncherController
        controller = QtLauncherController.__new__(QtLauncherController)
        controller.stop_profile = Mock(side_effect=RuntimeError("synthetic"))
        controller.mail_poller_runtime = Mock()
        controller.core_runtime = Mock()
        with self.assertRaises(RuntimeError):
            controller.close()
        controller.mail_poller_runtime.stop.assert_called_once()
        controller.core_runtime.stop.assert_called_once()


class PollerPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"KURO_GMAIL_PRIVATE_DIR": self.tmp.name, "KURO_MAIL_BRIEFING_AUTO": "1"})
        env.start()
        self.addCleanup(env.stop)
        load_producer("mail_tools_server")
        self.poller = load_producer("mail_poller")

    def test_live_preferences_disable_reenable_and_interval_from_same_owner(self):
        prefs = [{"autoRefresh": True, "intervalSeconds": 300},
                 {"autoRefresh": True, "intervalSeconds": 600},
                 {"autoRefresh": False, "intervalSeconds": 300},
                 {"autoRefresh": True, "intervalSeconds": 300}]
        with patch.object(self.poller.mail_tools_server, "_load_mail_preferences", side_effect=prefs) as read, \
             patch.object(self.poller, "_run_once", return_value={}) as run, \
             patch.object(self.poller, "_print_json"), \
             patch.object(self.poller.time, "monotonic", side_effect=[0, 0, 301, 302, 303, 303]), \
             patch.object(self.poller.time, "sleep", side_effect=[None, None, None, KeyboardInterrupt]):
            with self.assertRaises(KeyboardInterrupt):
                self.poller.run_loop(SimpleNamespace())
        self.assertEqual(read.call_count, 4)
        self.assertEqual(run.call_count, 2)

    def test_single_poller_lock_refuses_other_owner_before_fetch(self):
        lock = Path(self.tmp.name) / "mail_poller.lock"
        with status_writer._commit_lock(lock), \
             patch.object(sys, "argv", ["poller"]), \
             patch.object(self.poller, "run_loop") as loop, \
             patch.object(self.poller, "_print_json"):
            self.assertEqual(self.poller.main(), 2)
            loop.assert_not_called()

    def test_manual_once_keeps_existing_provider_path(self):
        with patch.object(sys, "argv", ["poller", "--once"]), \
             patch.object(self.poller, "_run_once", return_value={}) as run, \
             patch.object(self.poller, "_print_json"), \
             patch.object(self.poller, "run_loop") as loop:
            self.assertEqual(self.poller.main(), 0)
            run.assert_called_once()
            loop.assert_not_called()
