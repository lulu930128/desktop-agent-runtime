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
from kuro_launcher.work_panel_activation import WorkPanelActivationError, window_failure_code


def ready_status(*, visible: bool = False, pid: int = 4321) -> dict:
    return {
        "ok": True,
        "service": PET_CONTROL_SERVICE,
        "protocolVersion": PET_CONTROL_PROTOCOL_VERSION,
        "pid": pid,
        "instanceId": f"instance-{pid}",
        "renderer": {"briefingVisible": visible},
        "sourceRoot": str(Path.cwd()),
        "workPanel": {"contractVersion": 1, "exists": True, "visible": visible,
                      "minimized": False, "focused": False, "loading": False,
                      "rendererReady": True, "responsive": True, "displayMatch": True},
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
            {"action": "set-briefing-visible", "enabled": True,
             "expectedInstanceId": "instance-4321", "requestId": result["request_id"]},
            timeout=3.0,
        )
        self.assertTrue(any("activation-recovery-succeeded" in message for message in messages))

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

    def test_window_contract_rejects_incomplete_or_unusable_state(self) -> None:
        good = ready_status(visible=True)["workPanel"]
        self.assertEqual(window_failure_code(good), "")  # focus=False is allowed
        for field, value, code in (("contractVersion", 0, "WP_WINDOW_CONTRACT_UNSUPPORTED"),
                                   ("exists", False, "WP_WINDOW_NOT_CREATED"),
                                   ("rendererReady", False, "WP_RENDERER_NOT_READY"),
                                   ("responsive", False, "WP_RENDERER_NOT_READY"),
                                   ("loading", True, "WP_RENDERER_NOT_READY"),
                                   ("visible", False, "WP_WINDOW_NOT_VISIBLE"),
                                   ("minimized", True, "WP_WINDOW_NOT_VISIBLE"),
                                   ("displayMatch", False, "WP_WINDOW_OFFSCREEN")):
            with self.subTest(field=field):
                self.assertEqual(window_failure_code({**good, field: value}), code)

    def test_instance_change_during_verification_is_terminal(self) -> None:
        controller, _ = self.make_controller()
        with patch.object(controller, "_ensure_pet_shell_ready_locked", return_value=ready_status()), \
             patch.object(controller, "_read_pet_shell_status", return_value=ready_status(visible=True, pid=5555)), \
             patch("kuro_launcher.qt_controller.http_post_json", return_value={"ok": True}), \
             patch.object(controller, "_recover_work_panel_pet_locked") as recover:
            with self.assertRaises(WorkPanelActivationError) as raised:
                controller.ensure_work_panel(request_id="request-test", source="second-launch")
        self.assertEqual(raised.exception.result["failure_code"], "WP_PET_IDENTITY_MISMATCH")
        recover.assert_not_called()

    def test_recovery_is_bounded_and_final_failure_is_persisted(self) -> None:
        controller, _ = self.make_controller()
        output = io.StringIO()
        with patch.object(controller, "_ensure_pet_shell_ready_locked", return_value=ready_status()), \
             patch.object(controller, "_reveal_work_panel_locked", side_effect=RuntimeError("reveal timeout")) as reveal, \
             patch.object(controller, "_recover_work_panel_pet_locked") as recover, redirect_stdout(output):
            with self.assertRaises(WorkPanelActivationError) as raised:
                controller.ensure_work_panel(request_id="request-test", source="second-launch")
        self.assertEqual(reveal.call_count, 2)
        recover.assert_called_once()
        self.assertEqual(raised.exception.result["recovery_attempt"], 1)
        events = [json.loads(line.removeprefix("[work-panel] ")) for line in output.getvalue().splitlines()]
        self.assertEqual(events[-1]["event"], "activation-recovery-failed")
        self.assertEqual(events[-1]["source"], "second-launch")
        self.assertEqual(events[-1]["request_id"], "request-test")
        self.assertEqual(events[-1]["error"], "reveal timeout")
        self.assertNotIn("activation-recovery-succeeded", output.getvalue())

    def test_second_reveal_can_recover(self) -> None:
        controller, _ = self.make_controller()
        with patch.object(controller, "_ensure_pet_shell_ready_locked", return_value=ready_status()), \
             patch.object(controller, "_reveal_work_panel_locked", side_effect=[RuntimeError("timeout"), None]), \
             patch.object(controller, "_recover_work_panel_pet_locked") as recover:
            result = controller.ensure_work_panel()
        recover.assert_called_once()
        self.assertEqual(result["final_status"], "recovered")
        self.assertTrue(result["ok"])

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
                results = list(pool.map(lambda _: controller.ensure_work_panel(), range(6)))
        start.assert_called_once()
        self.assertTrue(all(item["ok"] for item in results))

    def test_recovery_terminates_only_tracked_handle(self) -> None:
        controller, _ = self.make_controller()
        child = Mock(pid=4321)
        child.poll.return_value = None
        child.wait.side_effect = lambda **_: setattr(child.poll, "return_value", 0)
        controller.proc_pet_electron = child
        with patch.object(controller, "_read_pet_shell_status", return_value=ready_status()), \
             patch("kuro_launcher.qt_controller.get_listening_pid_windows", return_value=4321), \
             patch("kuro_launcher.qt_controller.port_is_open", side_effect=[True, False]), \
             patch("kuro_launcher.qt_controller.taskkill_tree") as kill_tree:
            controller._recover_work_panel_pet_locked()
        child.terminate.assert_called_once()
        kill_tree.assert_not_called()
        self.assertIsNone(controller.proc_pet_electron)

    def test_recovery_refuses_untracked_or_replaced_listener(self) -> None:
        for tracked in (False, True):
            controller, _ = self.make_controller()
            child = Mock(pid=4321)
            child.poll.return_value = None
            controller.proc_pet_electron = child if tracked else None
            with patch.object(controller, "_read_pet_shell_status", side_effect=OSError("timeout")), \
                 patch("kuro_launcher.qt_controller.get_listening_pid_windows", return_value=7777), \
                 patch("kuro_launcher.qt_controller.port_is_open", return_value=True):
                with self.assertRaises(PetShellIdentityError):
                    controller._recover_work_panel_pet_locked()
            child.terminate.assert_not_called()

    def test_late_reveal_success_does_not_terminate_child(self) -> None:
        controller, _ = self.make_controller()
        child = Mock(pid=4321)
        child.poll.return_value = None
        controller.proc_pet_electron = child
        with patch.object(controller, "_read_pet_shell_status", return_value=ready_status(visible=True)):
            controller._recover_work_panel_pet_locked()
        child.terminate.assert_not_called()

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
