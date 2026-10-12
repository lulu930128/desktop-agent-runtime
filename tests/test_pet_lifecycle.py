from __future__ import annotations

import threading
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
        "renderer": {"available": True},
        "sourceRoot": str(Path.cwd()),
    }


class PetLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        output = redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def make_controller(self) -> tuple[QtLauncherController, list[str]]:
        messages: list[str] = []
        controller = QtLauncherController.__new__(QtLauncherController)
        controller.cfg = SimpleNamespace(
            pet_control_url="http://127.0.0.1:23567",
            pet_control_host="127.0.0.1",
            pet_control_port=23567,
            root=Path.cwd(),
        )
        controller.log = messages.append
        from kuro_launcher.runtime_lifecycle import RuntimeLifecycle
        controller.lifecycle = RuntimeLifecycle(Path.cwd(), messages.append)
        controller.proc_pet_electron = None
        controller._pet_lifecycle_lock = threading.RLock()
        controller._last_pet_exit_pid = None
        controller._pet_instance_id = ""
        controller._pet_output = None
        controller.presentation_state = Mock(return_value={"presentation": {"confUid": "fixture"}})
        controller.run_pet_command = Mock(return_value={"ok": True})
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


    def test_status_checks_actual_listener_and_source_root(self) -> None:
        controller, _ = self.make_controller()
        for listener, root, valid in ((4321, Path.cwd(), True), (7777, Path.cwd(), False),
                                      (None, Path.cwd(), False), (4321, Path.cwd().parent, False), (4321, "", False)):
            status = {**ready_status(), "sourceRoot": str(root)}
            with self.subTest(listener=listener, root=root), \
                 patch("kuro_launcher.qt_controller.http_get_json", return_value=status), \
                 patch("kuro_launcher.qt_controller.get_listening_pid_windows", return_value=listener), \
                 patch("kuro_launcher.qt_controller.os.name", "nt"):
                if valid:
                    self.assertEqual(controller._read_pet_shell_status()["pid"], 4321)
                else:
                    with self.assertRaises(PetShellIdentityError):
                        controller._read_pet_shell_status()





    def test_missing_pet_spawns_and_concurrent_calls_reuse_one_child(self) -> None:
        controller, _ = self.make_controller()
        child = Mock(pid=4321)
        child.poll.return_value = None

        def read(**_kwargs):
            if controller.proc_pet_electron is None:
                raise OSError("connection refused")
            return ready_status(visible=True)

        def spawn():
            controller.proc_pet_electron = child
            return child

        with patch.object(controller, "_read_pet_shell_status", side_effect=read), \
             patch.object(controller, "_spawn_pet_electron_locked", side_effect=spawn) as start, \
             patch("kuro_launcher.qt_controller.port_is_open", return_value=False), \
             patch("kuro_launcher.qt_controller.http_post_json", return_value={"ok": True}):
            with ThreadPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(lambda _: controller.launch_pet_electron(), range(6)))
        start.assert_called_once()
        self.assertTrue(all(item["ok"] for item in results))




    def test_tracked_instance_mismatch_is_rejected(self) -> None:
        controller, _ = self.make_controller()
        controller.proc_pet_electron = Mock(pid=4321)
        controller.proc_pet_electron.poll.return_value = None
        controller._pet_instance_id = "different-instance"
        with patch("kuro_launcher.qt_controller.http_get_json", return_value=ready_status()), \
             patch("kuro_launcher.qt_controller.get_listening_pid_windows", return_value=4321):
            with self.assertRaises(PetShellIdentityError):
                controller._read_pet_shell_status()

    def test_exited_child_is_reconciled_before_spawn(self) -> None:
        controller, _ = self.make_controller()
        child = Mock(pid=4321)
        child.poll.return_value = 1
        controller.proc_pet_electron = child
        controller._pet_output = Mock()
        output = controller._pet_output
        replacement = Mock(pid=5555)
        with patch.object(controller, "_read_pet_shell_status", side_effect=OSError("refused")), \
             patch("kuro_launcher.qt_controller.port_is_open", return_value=False), \
             patch.object(controller, "_spawn_pet_electron_locked", return_value=replacement) as spawn, \
             patch.object(controller, "_wait_for_pet_shell_ready_locked", return_value=ready_status(pid=5555)):
            self.assertEqual(controller._ensure_pet_shell_ready_locked()["pid"], 5555)
        spawn.assert_called_once()
        output.close.assert_called_once()

    def test_launch_pet_returns_verified_identity_status(self) -> None:
        controller, _messages = self.make_controller()
        controller.presentation_state = Mock(return_value={"presentation": {"confUid": "fixture"}})
        controller.run_pet_command = Mock(return_value={"ok": True})
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
