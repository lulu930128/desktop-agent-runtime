import socket
import os
import tempfile
import unittest
from urllib.error import HTTPError

import yaml
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace
from unittest.mock import Mock, patch

from kuro_launcher.core_runtime import CoreRuntime
from kuro_launcher.config import load_config

ROOT = Path(__file__).resolve().parents[1]


class CoreRuntimeTests(unittest.TestCase):
    def test_electron_spawn_receives_no_business_handoff_environment(self):
        import launcher_qt  # Configure vendored imports without starting the stack.
        from kuro_launcher.qt_controller import QtLauncherController

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for core_enabled, mail_enabled in ((False, True), (True, False), (True, True)):
                with self.subTest(core_enabled=core_enabled, mail_enabled=mail_enabled):
                    cfg = SimpleNamespace(
                        core_enabled=core_enabled, core_port=1,
                        core_mail_enabled=mail_enabled, core_mail_status_path=root / "configured.json",
                        core_mail_work_path=root / "configured-work.json",
                        llm_url="http://127.0.0.1:1", llm_host="127.0.0.1", llm_port=1,
                        pet_control_host="127.0.0.1", pet_control_port=2,
                        logs_dir=root / "logs", pet_electron_dir=root,
                    )
                    controller = QtLauncherController.__new__(QtLauncherController)
                    controller.cfg = cfg
                    controller.log = Mock()
                    controller.presentation_state = Mock(return_value={"presentation": {}})
                    controller._pet_electron_runtime = Mock(return_value=(root / "fake.exe", ""))
                    controller.core_runtime = CoreRuntime(cfg, controller.log)
                    # Exercise real env assembly; neither Core nor Electron may start.
                    with patch.object(controller.core_runtime, "start", return_value=core_enabled), \
                            patch.dict(os.environ, {"KURO_MAIL_STATUS_FILE": str(root / "inherited.json"),
                                "KURO_MAIL_WORK_FILE": str(root / "inherited-work.json"),
                                "KURO_MAIL_POLLER_OWNER": "electron"}), \
                            patch("kuro_launcher.qt_controller.subprocess.Popen") as spawn:
                        try:
                            controller._spawn_pet_electron_locked()
                            child_env = spawn.call_args.kwargs["env"]
                            for key in ("KURO_MAIL_POLLER_OWNER", "KURO_MAIL_STATUS_FILE", "KURO_MAIL_WORK_FILE", "KURO_CORE_TOKEN"):
                                self.assertNotIn(key, child_env)
                        finally:
                            controller._pet_output.close()
            self.assertFalse((root / "configured.json").exists())
            self.assertFalse((root / "inherited.json").exists())

    def test_config_is_scoped_and_disabled_rollback_does_not_start(self):
        cfg = load_config(ROOT/"kuro_launcher.settings.yaml")
        self.assertEqual(cfg.core_db_path, ROOT/"local_state/core/work.sqlite3")
        self.assertEqual(cfg.core_timezone,"Asia/Taipei")
        self.assertFalse(cfg.core_study_enabled)
        self.assertEqual(cfg.core_study_snapshot_path, ROOT/"Open-LLM-VTuber/private/study/study_snapshot.json")
        self.assertEqual(cfg.core_study_ttl_seconds, 3600)
        self.assertEqual(cfg.core_study_max_bytes, 2097152)
        self.assertFalse(cfg.core_mail_enabled)
        self.assertEqual(cfg.core_mail_status_path, ROOT/"Open-LLM-VTuber/private/gmail/mail_status.json")
        self.assertEqual(cfg.core_mail_ttl_seconds, 1800)
        self.assertEqual(cfg.core_mail_max_bytes, 65536)
        self.assertNotIn("KURO_MAIL_STATUS_FILE", CoreRuntime(cfg, lambda _: None).child_environment())
        runtime = CoreRuntime(replace(cfg,core_enabled=False), lambda _: None)
        self.assertFalse(runtime.start())
        self.assertEqual(runtime.child_environment(), {})

    def test_actual_isolated_child_identity_and_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1",0))
                port = sock.getsockname()[1]
            study_path = Path(tmp)/"missing-study.json"
            mail_path = Path(tmp)/"missing-mail.json"
            cfg = SimpleNamespace(core_enabled=True, core_port=port, core_db_path=Path(tmp)/"work.sqlite3",
                                  root=ROOT, env_llm=ROOT/"envs/kuro-llm310", logs_dir=Path(tmp)/"logs",
                                  core_study_enabled=True, core_study_snapshot_path=study_path,
                                  core_study_ttl_seconds=123, core_study_max_bytes=2048,
                                  core_mail_enabled=True, core_mail_status_path=mail_path,
                                  core_mail_work_path=Path(tmp)/"missing-mail-work.json",
                                  core_mail_ttl_seconds=234, core_mail_max_bytes=4096)
            runtime = CoreRuntime(cfg, lambda _: None)
            try:
                self.assertTrue(runtime.start())
                proc = runtime.proc.popen
                status = runtime.ready()
                self.assertEqual(status["pid"],proc.pid)
                self.assertEqual(status["contract"],"kuro.core.api.v1")
                self.assertEqual(status["capabilities"]["schedule"]["contract"],"kuro.core.schedule.v1")
                self.assertEqual(status["capabilities"]["schedule"]["schema"],3)
                study = runtime.request("/v1/integrations/study")
                self.assertEqual(study["contract"],"kuro.core.integration.study.v1")
                self.assertEqual(study["item"]["availability"],"missing")
                self.assertFalse(study_path.exists())
                self.assertEqual(status["capabilities"]["integrations"]["configured"], ["mail", "study"])
                mail = runtime.request("/v1/integrations/mail")
                self.assertEqual(mail["contract"], "kuro.core.integration.mail.v1")
                self.assertEqual(mail["item"]["availability"], "missing")
                self.assertFalse(mail_path.exists())
                self.assertIn("--mail-enabled", proc.args)
                for flag, expected in (("--mail-status", str(mail_path.resolve())),
                                       ("--mail-work", str(cfg.core_mail_work_path.resolve())),
                                       ("--mail-work-max-bytes", "2097152"),
                                       ("--mail-ttl-seconds", "234"), ("--mail-max-bytes", "4096")):
                    self.assertEqual(proc.args[proc.args.index(flag) + 1], expected)
                self.assertEqual(runtime.child_environment()["KURO_MAIL_STATUS_FILE"],
                                 proc.args[proc.args.index("--mail-status") + 1])
                self.assertEqual(runtime.child_environment()["KURO_MAIL_WORK_FILE"],
                                 proc.args[proc.args.index("--mail-work") + 1])
                self.assertNotIn(str(mail_path), str(status) + str(mail))
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

    def test_mail_disabled_has_no_cli_env_or_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            cfg = SimpleNamespace(core_enabled=True, core_port=port, core_db_path=Path(tmp)/"work.sqlite3",
                                  root=ROOT, env_llm=ROOT/"envs/kuro-llm310", logs_dir=Path(tmp)/"logs",
                                  core_mail_enabled=False, core_mail_status_path=Path(tmp)/"missing-mail.json")
            runtime = CoreRuntime(cfg, lambda _: None)
            try:
                self.assertTrue(runtime.start())
                self.assertFalse(any(arg.startswith("--mail-") for arg in runtime.proc.popen.args))
                self.assertNotIn("KURO_MAIL_STATUS_FILE", runtime.child_environment())
                self.assertEqual(runtime.ready()["capabilities"]["integrations"]["configured"], [])
                with self.assertRaises(HTTPError) as caught:
                    runtime.request("/v1/integrations/mail")
                self.assertEqual(caught.exception.code, 404)
                caught.exception.close()
            finally:
                runtime.stop()

    def test_mail_config_requires_path_but_not_existing_handoff(self):
        source = yaml.safe_load((ROOT/"kuro_launcher.settings.yaml").read_text(encoding="utf-8"))
        mail = source["core"]["integrations"]["mail"]
        mail["enabled"] = True
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp)/"settings.yaml"
            for missing in (None, "", " "):
                mail["status_path"] = missing
                config_path.write_text(yaml.safe_dump(source, allow_unicode=True), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "explicit status_path"):
                    load_config(config_path)
            missing = Path(tmp)/"does-not-exist.json"
            mail["status_path"] = str(missing)
            config_path.write_text(yaml.safe_dump(source, allow_unicode=True), encoding="utf-8")
            cfg = load_config(config_path)
            self.assertTrue(cfg.core_mail_enabled)
            self.assertEqual(cfg.core_mail_status_path, missing.resolve())
            self.assertFalse(missing.exists())
            for key, maximum in (("ttl_seconds", 2592000), ("max_bytes", 65536)):
                previous = mail[key]
                for value in (True, "1", 0, -1, 1.5, maximum + 1):
                    with self.subTest(key=key, value=value):
                        mail[key] = value
                        config_path.write_text(yaml.safe_dump(source, allow_unicode=True), encoding="utf-8")
                        with self.assertRaisesRegex(ValueError, key):
                            load_config(config_path)
                mail[key] = previous

    def test_mail_runtime_rejects_invalid_config_before_spawn(self):
        with tempfile.TemporaryDirectory() as tmp:
            defaults = dict(core_enabled=True, core_port=1, core_db_path=Path(tmp)/"work.sqlite3",
                            root=ROOT, env_llm=ROOT/"envs/kuro-llm310", logs_dir=Path(tmp)/"logs",
                            core_mail_enabled=True, core_mail_status_path=Path(tmp)/"missing-mail.json",
                            core_mail_work_path=Path(tmp)/"missing-mail-work.json",
                            core_mail_ttl_seconds=1800, core_mail_max_bytes=65536)
            for key, values in (("core_mail_status_path", (None, "", " ", "relative.json")),
                                ("core_mail_ttl_seconds", (True, "1", 0, -1, 1.5, 2592001)),
                                ("core_mail_max_bytes", (True, "1", 0, -1, 1.5, 65537))):
                for value in values:
                    runtime = CoreRuntime(SimpleNamespace(**{**defaults, key: value}), lambda _: None)
                    with self.subTest(key=key, value=value), \
                            patch("kuro_launcher.core_runtime.port_is_open", return_value=False), \
                            patch("kuro_launcher.core_runtime.subprocess.Popen") as spawn:
                        with self.assertRaises(ValueError):
                            runtime.start()
                        spawn.assert_not_called()
            self.assertFalse(defaults["logs_dir"].exists())
            self.assertFalse(defaults["core_db_path"].exists())

    def test_study_config_requires_path_but_not_existing_handoff(self):
        source = yaml.safe_load((ROOT/"kuro_launcher.settings.yaml").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp)/"settings.yaml"
            source["core"]["integrations"]["study"]["enabled"] = True
            source["core"]["integrations"]["study"]["snapshot_path"] = ""
            config_path.write_text(yaml.safe_dump(source, allow_unicode=True), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "explicit snapshot_path"):
                load_config(config_path)

            missing = Path(tmp)/"does-not-exist.json"
            source["core"]["integrations"]["study"]["snapshot_path"] = str(missing)
            config_path.write_text(yaml.safe_dump(source, allow_unicode=True), encoding="utf-8")
            cfg = load_config(config_path)
            self.assertTrue(cfg.core_study_enabled)
            self.assertEqual(cfg.core_study_snapshot_path, missing.resolve())
            self.assertFalse(missing.exists())

            source["core"]["integrations"]["study"]["ttl_seconds"] = True
            config_path.write_text(yaml.safe_dump(source, allow_unicode=True), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ttl_seconds"):
                load_config(config_path)

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
