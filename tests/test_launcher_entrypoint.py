from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import launcher_qt


class LauncherEntrypointTests(unittest.TestCase):
    def test_desktop_vbs_targets_built_work_panel_with_repo_python(self) -> None:
        script = (Path(__file__).resolve().parents[1] / "桌寵啟動器.vbs").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn('pet-electron\\renderer-dist\\work-panel.html', script)
        self.assertIn('launcherArgs = """" & launcherScript & """ --work-panel"', script)
        self.assertIn('WScript.Arguments.Named.Exists("check")', script)
        self.assertIn('Call MsgBox(', script)
        self.assertNotIn('cmd = "pyw ', script)

    def test_consume_work_panel_arg_removes_only_launcher_flag(self) -> None:
        work_panel_mode, qt_argv = launcher_qt._consume_work_panel_arg(
            ["launcher_qt.py", "--style", "Fusion", "--work-panel"]
        )

        self.assertTrue(work_panel_mode)
        self.assertEqual(qt_argv, ["launcher_qt.py", "--style", "Fusion"])

    def test_existing_work_panel_uses_pet_control_when_available(self) -> None:
        cfg = object()
        with (
            patch.object(launcher_qt, "_reveal_existing_work_panel", return_value=True) as reveal,
            patch.object(launcher_qt, "_signal_existing_launcher_console") as signal,
        ):
            activated = launcher_qt._activate_existing_launcher(cfg, work_panel_mode=True)

        self.assertTrue(activated)
        reveal.assert_called_once_with(cfg)
        signal.assert_not_called()

    def test_existing_work_panel_does_not_fall_back_to_launcher_console(self) -> None:
        cfg = object()
        with (
            patch.object(launcher_qt, "_reveal_existing_work_panel", return_value=False) as reveal,
            patch.object(
                launcher_qt,
                "_signal_existing_launcher_console",
                return_value=True,
            ) as signal,
        ):
            activated = launcher_qt._activate_existing_launcher(cfg, work_panel_mode=True)

        self.assertFalse(activated)
        reveal.assert_called_once_with(cfg)
        signal.assert_not_called()

    def test_existing_console_launch_signals_launcher_directly(self) -> None:
        cfg = object()
        with (
            patch.object(launcher_qt, "_reveal_existing_work_panel") as reveal,
            patch.object(
                launcher_qt,
                "_signal_existing_launcher_console",
                return_value=True,
            ) as signal,
        ):
            activated = launcher_qt._activate_existing_launcher(cfg, work_panel_mode=False)

        self.assertTrue(activated)
        reveal.assert_not_called()
        signal.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
