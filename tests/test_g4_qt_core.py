"""G4 synthetic Qt/Core wiring checks; no private state or running services."""
import ast
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Open-LLM-VTuber" / "src"))
sys.path.insert(0, str(ROOT / "Open-LLM-VTuber"))

from kuro_launcher.qt_controller import QtLauncherController


def today(complete=True):
    return dict(contract="kuro.core.today.v1", complete=complete, items=[],
                sections=[], sourceStates=[], limitations=[])


class CoreWrapperTests(unittest.TestCase):
    def setUp(self):
        self.controller = QtLauncherController.__new__(QtLauncherController)
        self.controller.core_runtime = Mock()
        self.controller.core_runtime.request.return_value = {"ok": True}

    def test_today_uses_only_today_route_and_checks_contract(self):
        request = self.controller.core_runtime.request
        request.return_value = today()
        self.assertEqual(self.controller.read_today(), today())
        request.assert_called_once_with("/v1/today", None)
        request.return_value = {"contract": "legacy"}
        with self.assertRaisesRegex(RuntimeError, "contract"):
            self.controller.read_today()

    def test_schedule_queries_are_encoded_without_losing_values(self):
        self.controller.read_schedule_view(start="2026-10-09", end="2026-10-16",
                                           timezone="Asia/Taipei", limit=25, offset=50)
        route, payload = self.controller.core_runtime.request.call_args.args
        self.assertIsNone(payload)
        self.assertEqual(urlsplit(route).path, "/v1/schedule/view")
        self.assertEqual(parse_qs(urlsplit(route).query), {
            "start": ["2026-10-09"], "end": ["2026-10-16"],
            "timezone": ["Asia/Taipei"], "limit": ["25"], "offset": ["50"],
        })
        self.controller.read_schedule_item("a/b?x=1&name=行程")
        route, payload = self.controller.core_runtime.request.call_args.args
        self.assertEqual(parse_qs(urlsplit(route).query), {"id": ["a/b?x=1&name=行程"]})

    def test_all_schedule_wrappers_delegate_to_core_request(self):
        item = {"title": "fixture", "timezone": "Asia/Taipei"}
        command = dict(action="complete", id="schedule-1", scope="this",
                       occurrenceDate="2026-10-09", expectedRevision=7,
                       confirmed=True, idempotencyKey="synthetic-key")
        notification = dict(action="snooze", id="notification-1", confirmed=True,
                            until="2026-10-09T15:30:00+08:00")
        cases = [
            (self.controller.read_core_status, (), "/status", None),
            (self.controller.prepare_schedule, (item,), "/v1/schedule/prepare", {"item": item}),
            (self.controller.mutate_schedule, (command,), "/v1/schedule/mutate", command),
            (self.controller.read_schedule_notifications, (), "/v1/schedule/notifications", None),
            (self.controller.schedule_notification_action, (notification,), "/v1/schedule/notification-action", notification),
            (self.controller.materialize_schedule, ("2026-10-16",), "/v1/schedule/materialize", {"through": "2026-10-16"}),
        ]
        for method, args, route, payload in cases:
            with self.subTest(route=route):
                self.assertEqual(method(*args), {"ok": True})
                self.controller.core_runtime.request.assert_called_with(route, payload)
        self.controller.core_runtime.start.assert_not_called()

    def test_unavailable_conflict_and_invalid_response_fail_explicitly(self):
        request = self.controller.core_runtime.request
        request.side_effect = ConnectionError("Core unavailable")
        with self.assertRaisesRegex(ConnectionError, "Core unavailable"):
            self.controller.read_today()
        request.side_effect = HTTPError("synthetic", 409, "conflict", {}, io.BytesIO(b"{}"))
        with self.assertRaisesRegex(RuntimeError, "Core conflict"):
            self.controller.mutate_schedule({})
        request.side_effect = None
        for result in (None, [], {"ok": False}):
            request.return_value = result
            with self.assertRaisesRegex(RuntimeError, "Core"):
                self.controller.read_core_status()




class CanonicalPathTests(unittest.TestCase):
    def test_only_legacy_builders_can_request_pet_briefing(self):
        tree = ast.parse((ROOT / "kuro_launcher/qt_app.py").read_text(encoding="utf-8-sig"))
        legacy = {"_build_briefing_page", "_build_briefing_settings_page", "refresh_briefing"}
        forbidden = {"read_briefing_summary", "refresh_briefing", "refresh_daily_briefing",
                     "_build_briefing_page", "_build_briefing_settings_page"}
        window = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                      and node.name == "KuroQtLauncherWindow")
        for method in window.body:
            if not isinstance(method, ast.FunctionDef) or method.name in legacy:
                continue
            for node in ast.walk(method):
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, forbidden, f"canonical caller: {method.name}")


if __name__ == "__main__":
    unittest.main()
