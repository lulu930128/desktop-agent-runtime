from __future__ import annotations

import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import launcher_qt  # noqa: F401 - bootstraps the vendored runtime source path.
from kuro_launcher.qt_controller import (
    PET_CONTROL_PROTOCOL_VERSION,
    PET_CONTROL_SERVICE,
    PetShellIdentityError,
    QtLauncherController,
)


def ready_status(*, visible: bool = False, pid: int = 4321) -> dict:
    return {
        "ok": True,
        "service": PET_CONTROL_SERVICE,
        "protocolVersion": PET_CONTROL_PROTOCOL_VERSION,
        "pid": pid,
        "instanceId": f"instance-{pid}",
        "renderer": {"briefingVisible": visible},
    }


class PetLifecycleTests(unittest.TestCase):
    def make_controller(self) -> tuple[QtLauncherController, list[str]]:
        messages: list[str] = []
        controller = QtLauncherController.__new__(QtLauncherController)
        controller.cfg = SimpleNamespace(
            pet_control_url="http://127.0.0.1:23567",
            pet_control_host="127.0.0.1",
            pet_control_port=23567,
        )
        controller.log = messages.append
        controller.proc_pet_electron = None
        controller._pet_lifecycle_lock = threading.RLock()
        controller._last_pet_exit_pid = None
        return controller, messages

    def test_status_identity_requires_service_protocol_pid_and_instance(self) -> None:
        status = ready_status()

        self.assertIs(QtLauncherController._validate_pet_shell_status(status), status)

        for missing_key in ("service", "protocolVersion", "pid", "instanceId"):
            malformed = dict(status)
            malformed.pop(missing_key)
            with self.subTest(missing_key=missing_key):
                with self.assertRaises(PetShellIdentityError):
                    QtLauncherController._validate_pet_shell_status(malformed)

    def test_unknown_listener_fails_closed_without_spawning(self) -> None:
        controller, _messages = self.make_controller()
        with (
            patch.object(controller, "_read_pet_shell_status", side_effect=OSError("not-json")),
            patch("kuro_launcher.qt_controller.port_is_open", return_value=True),
            patch.object(controller, "_spawn_pet_electron_locked") as spawn,
        ):
            with self.assertRaisesRegex(RuntimeError, "Pet control port"):
                controller._ensure_pet_shell_ready_locked(timeout_s=0.5)

        spawn.assert_not_called()

    def test_ensure_work_panel_reveals_and_verifies_visibility(self) -> None:
        controller, messages = self.make_controller()
        with (
            patch.object(
                controller,
                "_ensure_pet_shell_ready_locked",
                return_value=ready_status(visible=False),
            ),
            patch.object(
                controller,
                "_read_pet_shell_status",
                return_value=ready_status(visible=True),
            ),
            patch("kuro_launcher.qt_controller.http_post_json", return_value={"ok": True}) as post,
        ):
            result = controller.ensure_work_panel(timeout_s=0.5)

        self.assertTrue(result["ok"])
        self.assertEqual(result["pid"], 4321)
        post.assert_called_once_with(
            "http://127.0.0.1:23567/command",
            {"action": "set-briefing-visible", "enabled": True},
            timeout=5.0,
        )
        self.assertTrue(any("ensure-work-panel ready" in message for message in messages))

    def test_launch_pet_returns_verified_identity_status(self) -> None:
        controller, _messages = self.make_controller()
        expected = ready_status(visible=True)
        with patch.object(
            controller,
            "_ensure_pet_shell_ready_locked",
            return_value=expected,
        ):
            result = controller.launch_pet_electron()

        self.assertIs(result, expected)

    def test_stop_profile_can_preserve_pet_shell(self) -> None:
        controller, _messages = self.make_controller()
        controller.proc_llm = None
        controller.proc_tts = None
        controller.proc_bridge = None
        controller.cfg.llm_port = 23456
        controller.cfg.tts_port = 9981
        controller.cfg.bridge_host = "127.0.0.1"
        controller.cfg.bridge_port = 1188
        with (
            patch.object(controller, "stop_pet_electron") as stop_pet,
            patch("kuro_launcher.qt_controller.get_listening_pid_windows", return_value=None),
        ):
            controller.stop_profile(silent=True, stop_bridge=False, stop_pet=False)

        stop_pet.assert_not_called()

    def test_stop_refuses_to_kill_unverified_listener(self) -> None:
        controller, messages = self.make_controller()
        with (
            patch.object(controller, "_read_pet_shell_status", side_effect=OSError("not-kuro")),
            patch("kuro_launcher.qt_controller.port_is_open", return_value=True),
            patch("kuro_launcher.qt_controller.taskkill_tree") as taskkill,
        ):
            controller.stop_pet_electron()

        taskkill.assert_not_called()
        self.assertTrue(any("拒絕終止未知程序" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
