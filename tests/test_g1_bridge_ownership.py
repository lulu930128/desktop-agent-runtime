"""No real process/port actions: Bridge lifecycle owns only its ManagedProc."""
from contextlib import ExitStack
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import launcher_qt
from kuro_launcher.qt_controller import QtLauncherController
from kuro_launcher.procs import ManagedProc


class BridgeOwnershipTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.c = QtLauncherController.__new__(QtLauncherController)
        self.c.cfg = SimpleNamespace(bridge_host='127.0.0.1', bridge_port=1188, tts_mode='central')
        self.c.proc_bridge = self.c.proc_llm = self.c.proc_tts = None
        self.c.lifecycle = SimpleNamespace(lock=threading.RLock(), desired_running=True, record=Mock())
        self.c.stop_pet_electron = Mock()
        self.c.mail_poller_runtime = Mock()
        self.c.core_runtime = Mock()
        self.c.log = Mock()
        self.c._ensure_bridge_on_start = Mock()
        self.port = stack.enter_context(patch('kuro_launcher.qt_controller.port_is_open', return_value=True))
        self.lookup = stack.enter_context(patch('kuro_launcher.qt_controller.get_listening_pid_windows', return_value=424242))
        self.kill = stack.enter_context(patch('kuro_launcher.qt_controller.taskkill_tree'))
        stack.enter_context(patch('kuro_launcher.qt_controller.time.sleep'))

    def owned(self, *, exited=False):
        proc = Mock(spec=ManagedProc)
        proc.popen = Mock()
        proc.popen.poll.return_value = 0 if exited else None
        proc.popen.wait.return_value = 0
        self.c.proc_bridge = proc
        return proc

    def test_foreign_listener_survives_close_and_stop_profile(self):
        self.c.close()
        self.c.stop_profile()
        self.kill.assert_not_called()
        self.lookup.assert_not_called()
        self.c._ensure_bridge_on_start.assert_not_called()
        self.c.core_runtime.stop.assert_called_once()
        self.c.mail_poller_runtime.stop.assert_called_once()

    def test_foreign_listener_rejects_toggle_and_restart_without_spawn(self):
        for name in ('toggle_bridge', 'restart_bridge'):
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, 'owned|unverified'):
                getattr(self.c, name)()
        self.kill.assert_not_called()
        self.lookup.assert_not_called()
        self.c._ensure_bridge_on_start.assert_not_called()

    def test_close_stops_owned_handle_once_and_does_not_target_replacement_listener(self):
        proc = self.owned()
        self.c.close()
        self.c.close()
        proc.stop.assert_called_once()
        proc.popen.wait.assert_called_once()
        self.assertIsNone(self.c.proc_bridge)
        self.kill.assert_not_called()
        self.lookup.assert_not_called()

    def test_failed_owned_stop_retains_handle_and_restart_does_not_spawn(self):
        proc = self.owned()
        proc.stop.side_effect = OSError('synthetic stop failure')
        with self.assertRaises(OSError):
            self.c.restart_bridge()
        self.assertIs(self.c.proc_bridge, proc)
        self.c._ensure_bridge_on_start.assert_not_called()
        self.kill.assert_not_called()

    def test_stale_owned_handle_cannot_stop_foreign_listener(self):
        proc = self.owned(exited=True)
        with self.assertRaises(RuntimeError):
            self.c.restart_bridge()
        proc.stop.assert_not_called()
        self.kill.assert_not_called()
        self.c._ensure_bridge_on_start.assert_not_called()

    def test_owned_restart_waits_and_starts_only_after_port_release(self):
        proc = self.owned()
        self.port.return_value = False
        self.c.restart_bridge()
        proc.stop.assert_called_once()
        proc.popen.wait.assert_called_once()
        self.c._ensure_bridge_on_start.assert_called_once()
        self.kill.assert_not_called()

    def test_replacement_listener_after_owned_stop_blocks_restart(self):
        proc = self.owned()
        with self.assertRaises(RuntimeError):
            self.c.restart_bridge()
        proc.stop.assert_called_once()
        self.c._ensure_bridge_on_start.assert_not_called()
        self.kill.assert_not_called()

    def test_idle_toggle_starts_and_live_owned_toggle_stops(self):
        self.port.return_value = False
        self.c.toggle_bridge()
        self.c._ensure_bridge_on_start.assert_called_once()
        proc = self.owned()
        self.port.return_value = True
        self.c.toggle_bridge()
        proc.stop.assert_called_once()
        self.kill.assert_not_called()


if __name__ == '__main__':
    unittest.main()
