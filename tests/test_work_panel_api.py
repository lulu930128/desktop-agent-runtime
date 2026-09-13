from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from kuro_launcher.work_panel_api import WorkPanelControlServer, _require_loopback


class FakeController:
    def __init__(self) -> None:
        self.profile_payloads: list[dict[str, str]] = []

    def work_panel_profile_state(self) -> dict:
        return {
            "ok": True,
            "characters": [{"id": "kuro", "name": "Kuro"}],
            "projects": [{"id": "desktop", "name": "Desktop"}],
            "models": ["gpt-test"],
            "thinking_options": ["fast", "normal", "deep"],
            "selected": {
                "character_id": "kuro",
                "project_id": "desktop",
                "model": "gpt-test",
                "thinking_power": "normal",
            },
        }

    def apply_work_panel_profile(self, **payload: str) -> dict:
        self.profile_payloads.append(payload)
        return {"ok": True, "applied": payload}

    def work_panel_history_state(self, history_uid: str = "") -> dict:
        return {"ok": True, "current_history_uid": history_uid, "histories": [], "messages": []}

    def create_history(self) -> dict:
        return {"history_uid": "new-history"}

    def select_history(self, history_uid: str) -> dict:
        return {"history_uid": history_uid}

    def delete_history(self, history_uid: str) -> dict:
        return {"deleted": history_uid}

    def work_panel_memory_state(self) -> dict:
        return {"ok": True, "memories": []}

    def add_memory(self, _content: str) -> bool:
        return True

    def set_memory_status(self, _entry_id: str, _status: str, *, expected_digest=None) -> bool:
        return True

    def delete_memory(self, _entry_id: str) -> bool:
        return True

    def compact_memory(self) -> dict:
        return {"compacted": 0}

    def work_panel_tool_policy_state(self) -> dict:
        return {"ok": True, "default_mode": "blocked", "tools": []}


class WorkPanelControlServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = FakeController()
        self.server = WorkPanelControlServer(
            self.controller,
            host="127.0.0.1",
            port=0,
        )
        self.assertTrue(self.server.start())
        self.base_url = f"http://127.0.0.1:{self.server.bound_port}"

    def tearDown(self) -> None:
        self.server.stop()

    def request(
        self,
        path: str,
        payload: dict | None = None,
        *,
        authorized: bool = True,
    ) -> tuple[int, dict]:
        data = None
        headers: dict[str, str] = (
            {"Authorization": f"Bearer {self.server.token}"} if authorized else {}
        )
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(f"{self.base_url}{path}", data=data, headers=headers)
        with urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_read_routes_return_local_state(self) -> None:
        status, health = self.request("/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["service"], "kuro-launcher-control")

        status, profile = self.request("/v1/profile")
        self.assertEqual(status, 200)
        self.assertEqual(profile["selected"]["character_id"], "kuro")

    def test_runtime_retry_stop_and_restart_are_authenticated_and_confirmed(self) -> None:
        self.controller.lifecycle = SimpleNamespace(phase='ready', snapshot=lambda: {'phase': 'ready'})
        self.controller.retry_runtime = Mock(return_value={'ok': True})
        self.controller.stop_profile = Mock()
        self.controller.request_restart = Mock()
        for action in ('retry', 'stop', 'restart-launcher'):
            with self.assertRaises(HTTPError) as denied:
                self.request('/v1/runtime/' + action, {'confirmed': True}, authorized=False)
            self.assertEqual(denied.exception.code, 401)
            with self.assertRaises(HTTPError) as denied:
                self.request('/v1/runtime/' + action, {})
            self.assertEqual(denied.exception.code, 409)
            _, result = self.request('/v1/runtime/' + action, {'confirmed': True})
            self.assertTrue(result['ok'])
        self.controller.retry_runtime.assert_called_once()
        self.controller.stop_profile.assert_called_once_with(stop_bridge=False, stop_pet=False)
        self.controller.request_restart.assert_called_once()

    def test_read_routes_reject_missing_session_token(self) -> None:
        with self.assertRaises(HTTPError) as raised:
            self.request("/v1/profile", authorized=False)
        self.assertEqual(raised.exception.code, 401)

    def test_profile_write_requires_explicit_confirmation(self) -> None:
        with self.assertRaises(HTTPError) as raised:
            self.request(
                "/v1/profile/apply",
                {"character_id": "kuro", "project_id": "desktop", "model": "gpt-test"},
            )
        self.assertEqual(raised.exception.code, 409)
        self.assertEqual(self.controller.profile_payloads, [])

        status, result = self.request(
            "/v1/profile/apply",
            {
                "confirmed": True,
                "character_id": "kuro",
                "project_id": "desktop",
                "model": "gpt-test",
                "thinking_power": "deep",
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        self.assertEqual(self.controller.profile_payloads[0]["thinking_power"], "deep")

    def test_memory_status_rejects_unknown_value(self) -> None:
        with self.assertRaises(HTTPError) as raised:
            self.request(
                "/v1/memory/status",
                {"confirmed": True, "entry_id": "memory-1", "status": "approved"},
            )
        self.assertEqual(raised.exception.code, 400)

    def test_memory_approval_requires_reviewed_content_digest(self) -> None:
        with self.assertRaises(HTTPError) as raised:
            self.request('/v1/memory/status', {'confirmed':True,'entry_id':'memory-1','status':'active'})
        self.assertEqual(raised.exception.code,400)
        status,_=self.request('/v1/memory/status', {'confirmed':True,'entry_id':'memory-1','status':'active','content_digest':'a'*64})
        self.assertEqual(status,200)

    def test_history_routes_reject_path_like_identifiers(self) -> None:
        with self.assertRaises(HTTPError) as raised:
            self.request("/v1/history/select", {"history_uid": "../private"})
        self.assertEqual(raised.exception.code, 400)

    def test_only_loopback_bind_addresses_are_allowed(self) -> None:
        _require_loopback("localhost")
        _require_loopback("::1")
        with self.assertRaises(ValueError):
            _require_loopback("0.0.0.0")


if __name__ == "__main__":
    unittest.main()
