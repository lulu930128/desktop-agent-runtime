"""Core projections in the actual Work Companion; no provider or live Core IO."""
import copy
from unittest.mock import patch
import unittest

from work_companion_fixture import APP, ROOT, ProductionWindowFixture
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox


def projection():
    return {"contract": "kuro.core.today.v1", "complete": False, "asOf": "2026-10-10T09:00:00+08:00",
        "timezone": "Asia/Taipei", "limitations": ["source_partial"], "counts": {},
        "items": [{"workId": "work-1", "title": "SYNTHETIC 待辦", "source": "fixture-source", "level": "focus",
                   "summary": "確認測試資料", "reasonCodes": ["due_today"], "actionKind": "review",
                   "evidenceRef": "evidence-1", "stale": False, "partial": True}],
        "sections": [{"kind": "focus", "itemIds": ["work-1"]}],
        "sourceStates": [{"integrationId": "fixture-source", "availability": "partial", "freshness": "current",
                          "connection": "connected", "observedAt": "2026-10-10T08:30:00+08:00", "limitationCount": 1}]}


class CoreViewTests(unittest.TestCase):
    def setUp(self):
        self.fx = ProductionWindowFixture()
        self.addCleanup(self.fx.close)
        self.w = self.fx.window

    def test_today_refresh_retains_selected_work_and_detail(self):
        page = self.w.today_page
        data = projection()
        page.apply(data)
        page.select_work("work-1")
        detail = page.detail.toPlainText()
        for _ in range(5):
            page.apply(copy.deepcopy(data))
        self.assertEqual(page.items.currentItem().data(Qt.ItemDataRole.UserRole)["workId"], "work-1")
        self.assertEqual(page.detail.toPlainText(), detail)
        self.assertIn("source_partial", detail)
        self.assertIn("evidence-1", detail)
        data["items"][0]["summary"] = "Core 已更新"
        page.apply(data)
        self.assertIn("Core 已更新", page.detail.toPlainText())
        self.assertIn("partial", page.sources.toPlainText())

    def test_today_context_is_visible_draft_only_and_retains_limitations(self):
        page = self.w.today_page
        page.apply(projection())
        page.select_work("work-1")
        with patch.object(self.w.chat_client, "send_text") as send:
            page.use_context()
        send.assert_not_called()
        self.assertEqual(self.w.work_companion.page, "chat")
        self.assertIn("source_partial", self.w.chat_input.toPlainText())
        self.assertIn("Core Today", self.w.chat_input.toPlainText())
        self.assertTrue(self.w.chat_context.isVisible())
        self.assertIn("SYNTHETIC", self.w.chat_context_label.text())
        self.w.clear_chat_context.click()
        self.assertFalse(self.w.chat_context.isVisible())
        self.assertIn("Core Today", self.w.chat_input.toPlainText())

    def test_today_failure_keeps_visible_stale_detail_and_prevents_reenable(self):
        page = self.w.today_page
        page.apply(projection())
        page.select_work("work-1")
        page.clear_failed("fixture offline")
        page.show_detail(page.items.currentItem())
        self.assertFalse(page.context_button.isEnabled())
        self.assertIn("上次投影", page.status.text())
        self.assertIn("evidence-1", page.detail.toPlainText())
        page.apply(projection())
        self.assertTrue(page.context_button.isEnabled())

    def schedule(self):
        page = self.w.schedule_page
        record = {"scheduleId": "schedule-1", "occurrenceDate": "2026-10-10", "revision": 7,
            "state": "pending", "timeState": "scheduled", "recurring": False,
            "item": {"title": "SYNTHETIC 行程", "kind": "task", "due": "2026-10-10T10:00", "timezone": "Asia/Taipei"}}
        result = ({"timezone": "Asia/Taipei"}, {"start": "2026-10-10", "end": "2026-10-17"},
                  {"contract": "kuro.core.schedule.v1", "items": [record], "coverage": "complete"}, {"items": []})
        page.apply(result)
        page.items.setCurrentRow(0)
        return page, result

    def test_schedule_refresh_preserves_occurrence_and_revision_fenced_command(self):
        page, result = self.schedule()
        page.apply(copy.deepcopy(result))
        self.assertEqual(page.selected()["scheduleId"], "schedule-1")
        with patch.object(page, "run") as run, patch("kuro_launcher.qt_core_pages.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            page.mutate("complete")
            run.call_args.args[0]()
        command = self.fx.controller.mutate_schedule.call_args.args[0]
        self.assertEqual(command["expectedRevision"], 7)
        self.assertEqual(command["occurrenceDate"], "2026-10-10")
        self.assertTrue(command["confirmed"])
        self.assertTrue(command["idempotencyKey"])

    def test_schedule_cancellation_and_materialization_need_confirmation(self):
        page, _ = self.schedule()
        with patch.object(page, "run") as run, patch("kuro_launcher.qt_core_pages.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
            page.mutate("cancel")
            page.advance()
            run.assert_not_called()

    def test_today_offscreen_screenshot(self):
        self.w.today_page.apply(projection())
        self.w.today_page.select_work("work-1")
        self.w.work_companion.set_page("today")
        self.w.work_companion.privacy_status.setText("SYNTHETIC FIXTURE · Core projection／無 provider")
        APP.processEvents()
        self.assertTrue(self.w.work_companion.grab().save(str(
            ROOT / "devtools/git-work-companion-parity-20261010/R3-Today-offscreen.png"), "PNG"))


if __name__ == "__main__":
    unittest.main()
