"""SYNTHETIC read-only port; deliberately has no production owner dependencies."""
from __future__ import annotations

import copy
import json
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent / "frontend"
READS = frozenset({"getState", "getChatState", "getData", "getProfile", "getHistories",
                  "getMemories", "getTools", "schedule.status", "schedule.view",
                  "schedule.notifications"})


class PreviewProtocol:
    def __init__(self):
        self.fixture = json.loads((FRONTEND / "src/synthetic.json").read_text(encoding="utf-8"))
        self.last_id = 0

    def request(self, raw: str) -> str:
        reply = {"id": None, "context": self.fixture["context"],
                 "revision": self.fixture["revision"],
                 "result": {"ok": False, "error": "invalid_request"}}
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > 8192:
            return json.dumps(reply)
        try:
            value = json.loads(raw)
            if not isinstance(value, dict) or set(value) != {"id", "context", "revision", "command", "payload"}:
                return json.dumps(reply)
            request_id = value["id"]
            if type(request_id) is not int or not self.last_id < request_id <= 2**31 - 1:
                return json.dumps(reply)
            reply["id"] = request_id
            self.last_id = request_id
            if value["context"] != self.fixture["context"] or type(value["revision"]) is not int or value["revision"] != self.fixture["revision"]:
                reply["result"]["error"] = "stale_context"
                return json.dumps(reply)
            command, payload = value["command"], value["payload"]
            if not isinstance(command, str) or command not in READS:
                reply["result"]["error"] = "SYNTHETIC preview: unavailable; no operation performed"
                return json.dumps(reply)
            allowed_keys = ({"historyUid"} if command == "getHistories" else
                            {"start", "end", "timezone", "limit", "offset"} if command == "schedule.view" else set())
            if not isinstance(payload, dict) or set(payload) - allowed_keys:
                return json.dumps(reply)
            if command == "getHistories" and payload.get("historyUid", "synthetic-history") != "synthetic-history":
                reply["result"]["error"] = "stale_context"
                return json.dumps(reply)
            if command == "schedule.view":
                for key, val in payload.items():
                    if key in {"limit", "offset"}:
                        if type(val) is not int or not 0 <= val <= 100:
                            return json.dumps(reply)
                    elif not isinstance(val, str) or len(val) > 64:
                        return json.dumps(reply)
            reply["result"] = copy.deepcopy(self.fixture[command])
        except (ValueError, TypeError):
            pass
        return json.dumps(reply, ensure_ascii=False)
