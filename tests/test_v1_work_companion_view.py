"""Former preview checks now exercise the only production view with isolated owners."""
import ast
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from work_companion_fixture import APP, ROOT, ProductionWindowFixture
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QFrame
from kuro_launcher.qt_work_companion_view import HistoryDrawer, WorkCompanionView


class ProductionLayoutTests(unittest.TestCase):
    def setUp(self):
        self.fx = ProductionWindowFixture()
        self.addCleanup(self.fx.close)
        self.w = self.fx.window
        self.view = self.w.work_companion
        self.fx.patches.enter_context(patch.object(self.w.core_health_page, "refresh"))
        self.fx.controller.read_companion_diagnostics.return_value = {}
        self.fx.controller.read_tool_policy_summary.return_value = dict(default_mode="blocked", tools=[])

    def settle(self):
        APP.processEvents()
        QTest.qWait(10)
        APP.processEvents()

    def test_single_surface_and_drawer_at_supported_sizes(self):
        self.assertEqual(APP.platformName(), "offscreen")
        self.assertAlmostEqual(self.view.devicePixelRatioF(), float(os.environ.get("QT_SCALE_FACTOR", "1")))
        self.assertEqual(len(self.w.findChildren(WorkCompanionView)), 1)
        self.assertEqual(len(self.w.findChildren(HistoryDrawer)), 1)
        self.assertFalse(hasattr(self.w, "settings_dialog"))
        for width in (1120, 1280, 1440):
            self.w.resize(width, 800)
            for key in self.view.pages:
                self.w._set_page(key)
                self.settle()
                self.assertLessEqual(self.w.width(), width)
                self.assertTrue(self.view.rect().contains(self.view.stage.geometry()))
                self.assertEqual(self.view.rail.width(), 180 if key == "chat" else 73)
                self.assertEqual(self.view.stack.currentWidget(), self.view.pages[key])
        self.w._set_page("chat")
        before = self.w.history_transcript.geometry()
        self.view.show_history(True)
        self.settle()
        self.assertEqual(self.w.history_transcript.geometry(), before)
        self.assertTrue(self.view.stage.rect().contains(self.view.history_drawer.geometry()))
        self.assertTrue(self.view.history_drawer.search.hasFocus())
        QTest.keyClick(self.view.history_drawer.search, Qt.Key.Key_Escape)
        self.settle()
        self.assertFalse(self.view.history_drawer.isVisible())

    def test_enter_shift_enter_and_ime_on_real_composer(self):
        self.fx.tasks.reset_mock()
        edit = self.w.chat_input
        spy = QSignalSpy(edit.submit_requested)
        edit.setPlainText("範例")
        QTest.keyClick(edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        self.assertIn("\n", edit.toPlainText())
        self.assertEqual(spy.count(), 0)
        APP.sendEvent(edit, QInputMethodEvent("注音", []))
        QTest.keyClick(edit, Qt.Key.Key_Return)
        self.assertEqual(spy.count(), 0)
        APP.sendEvent(edit, QInputMethodEvent("", []))
        QTest.keyClick(edit, Qt.Key.Key_Return)
        self.assertEqual(spy.count(), 1)
        self.assertFalse(self.w.chat_send_button.isEnabled())
        self.fx.tasks.assert_not_called()

    def test_message_html_is_literal_and_long_text_stays_in_transcript(self):
        payload = "<img src='file:///private'>\n  code\n" + "字" * 2400 + "X" * 1200
        self.w.chat_live_blocks = [("User", "SYNTHETIC", payload), ("Kuro", "SYNTHETIC", "回覆")]
        self.w._render_chat_transcript_with_live()
        self.settle()
        self.assertIn("<img src='file:///private'>", self.w.history_transcript.toPlainText())
        self.assertEqual(self.w.history_transcript.horizontalScrollBar().maximum(), 0)
        self.assertGreater(self.w.history_transcript.verticalScrollBar().maximum(), 0)
        self.w.chat_live_blocks = [("User", "10:00 · SYNTHETIC", "請整理今天的工作；先確認來源是否完整。"),
            ("Event", "10:00 · SYNTHETIC", "Core Today · partial · 來源尚有缺漏"),
            ("Kuro", "10:01 · SYNTHETIC", "目前投影只有一筆待辦。\n來源不完整，因此不能推論其他工作已完成。")]
        self.w.work_companion.privacy_status.setText("SYNTHETIC FIXTURE · 無私人資料／裝置／provider")
        self.w._render_chat_transcript_with_live()
        self.settle()
        self.assertTrue(self.view.grab().save(str(ROOT /
            "devtools/git-work-companion-parity-20261010/R4-Chat-offscreen.png"), "PNG"))

    def test_git_attachment_limits_and_growth_are_enforced_before_encoding(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for suffix, limit in ((".png", 8), (".wav", 12), (".zip", 24), (".bin", 16), (".txt", 4), (".py", 4)):
                path = root / ("fixture" + suffix)
                path.write_bytes(b"fixture")
                with self.subTest(suffix=suffix):
                    with self.assertRaisesRegex(ValueError, str(limit)):
                        self.w._build_chat_attachment(path, limit * 1024 * 1024 + 1)
                    result = self.w._build_chat_attachment(path, 7)
                    self.assertEqual(result["size"], 7)
            growing = root / "growing.txt"
            growing.write_bytes(b"x" * (4 * 1024 * 1024 + 1))
            with self.assertRaises(ValueError):
                self.w._build_chat_attachment(growing, 1)

    def test_offline_pet_controls_have_reason_and_do_not_dispatch(self):
        groups = [p for p in self.w.findChildren(QFrame) if p.property("petControlGroup")]
        self.assertEqual(len(groups), 2)
        for group in groups:
            self.assertFalse(group.isEnabled())
            self.assertTrue(group.toolTip())


class SourceCutoverTests(unittest.TestCase):
    def test_formal_host_has_one_view_and_no_preview_import(self):
        source = (ROOT / "kuro_launcher/qt_app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertEqual(sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                             and n.func.id == "WorkCompanionView" for n in ast.walk(tree)), 1)
        for relative in ("launcher_qt.py", "kuro_launcher/qt_app.py", "kuro_launcher/qt_work_companion_view.py"):
            self.assertNotIn("SyntheticPreviewModel", (ROOT / relative).read_text(encoding="utf-8"))
        self.assertFalse((ROOT / "devtools/work_companion_synthetic.py").exists())
        self.assertFalse((ROOT / "devtools/preview_work_companion_v1.py").exists())

    def test_g7_retired_paths_remain_absent(self):
        manifest = json.loads((ROOT / "docs/agent-runs/qt-ui-convergence-20261007/G7DeletionManifest.json").read_text(encoding="utf-8-sig"))
        paths = [item["path"] for item in manifest["files"]]
        self.assertEqual(len(paths), 35)
        for relative in paths:
            self.assertFalse((ROOT / relative).exists(), relative)


if __name__ == "__main__":
    unittest.main()
