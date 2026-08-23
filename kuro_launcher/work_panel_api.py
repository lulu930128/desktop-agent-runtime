from __future__ import annotations

import ipaddress
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Callable, Optional
from urllib.parse import parse_qs, urlparse

if TYPE_CHECKING:
    from .qt_controller import QtLauncherController


MAX_REQUEST_BYTES = 64 * 1024
MEMORY_STATUSES = {"active", "disabled"}
THINKING_POWERS = {"fast", "normal", "deep"}
MAX_MEMORY_TEXT_LENGTH = 1200


def _require_loopback(host: str) -> None:
    normalized = str(host or "").strip().lower()
    if normalized == "localhost":
        return
    try:
        if ipaddress.ip_address(normalized).is_loopback:
            return
    except ValueError:
        pass
    raise ValueError("Launcher control API must bind to a loopback address.")


def _require_safe_history_uid(value: object) -> str:
    normalized = str(value or "").strip()
    if (
        not normalized
        or len(normalized) > 200
        or normalized in {".", ".."}
        or "/" in normalized
        or "\\" in normalized
        or "\x00" in normalized
    ):
        raise ValueError("Invalid history_uid.")
    return normalized


class WorkPanelControlServer:
    def __init__(
        self,
        controller: QtLauncherController,
        *,
        host: str,
        port: int,
        token: str = "",
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        _require_loopback(host)
        self.controller = controller
        self.host = host
        self.port = int(port)
        self.token = str(token or secrets.token_urlsafe(32))
        self.log = log or (lambda _message: None)
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._action_lock = threading.Lock()
        self.last_error = ""

    @property
    def bound_port(self) -> int:
        if self._httpd is None:
            return self.port
        return int(self._httpd.server_address[1])

    def start(self) -> bool:
        if self._httpd is not None:
            return True
        handler = self._build_handler()
        try:
            httpd = ThreadingHTTPServer((self.host, self.port), handler)
        except OSError as exc:
            self.last_error = str(exc)
            self.log(f"Launcher control API 啟動失敗：{exc}")
            return False
        httpd.daemon_threads = True
        self._httpd = httpd
        self._thread = threading.Thread(
            target=httpd.serve_forever,
            name="kuro-work-panel-control",
            daemon=True,
        )
        self._thread.start()
        self.log(f"Launcher control API 已上線：http://{self.host}:{self.bound_port}")
        return True

    def stop(self) -> None:
        httpd = self._httpd
        self._httpd = None
        if httpd is None:
            return
        httpd.shutdown()
        httpd.server_close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _build_handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "KuroLauncherControl/1.0"

            def log_message(self, _format: str, *_args) -> None:
                return

            def _send(self, status: int, payload: dict) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)

            def _payload(self) -> dict:
                raw_length = self.headers.get("Content-Length", "0")
                try:
                    length = int(raw_length)
                except ValueError as exc:
                    raise ValueError("Invalid Content-Length.") from exc
                if length < 0 or length > MAX_REQUEST_BYTES:
                    raise ValueError("Request body is too large.")
                if length == 0:
                    return {}
                raw = self.rfile.read(length)
                parsed = json.loads(raw.decode("utf-8"))
                if not isinstance(parsed, dict):
                    raise ValueError("JSON body must be an object.")
                return parsed

            def _authorized(self) -> bool:
                header = str(self.headers.get("Authorization") or "")
                prefix = "Bearer "
                if not header.startswith(prefix):
                    return False
                provided = header[len(prefix):].strip()
                return bool(provided) and secrets.compare_digest(provided, owner.token)

            def _dispatch_read(self, path: str, query: dict[str, list[str]]) -> dict:
                if path == "/health":
                    return {"ok": True, "service": "kuro-launcher-control", "version": 1}
                if path == "/v1/profile":
                    return owner.controller.work_panel_profile_state()
                if path == "/v1/history":
                    history_uid = str((query.get("history_uid") or [""])[0]).strip()
                    if history_uid:
                        history_uid = _require_safe_history_uid(history_uid)
                    return owner.controller.work_panel_history_state(history_uid)
                if path == "/v1/memories":
                    return owner.controller.work_panel_memory_state()
                if path == "/v1/tools":
                    return owner.controller.work_panel_tool_policy_state()
                raise LookupError("Unknown launcher control route.")

            def _confirmed(self, payload: dict) -> None:
                if payload.get("confirmed") is not True:
                    raise PermissionError("This action requires explicit confirmation.")

            def _dispatch_write(self, path: str, payload: dict) -> dict:
                if path == "/v1/profile/apply":
                    self._confirmed(payload)
                    thinking_power = str(payload.get("thinking_power") or "normal").strip()
                    if thinking_power not in THINKING_POWERS:
                        raise ValueError("Unsupported thinking_power.")
                    return owner.controller.apply_work_panel_profile(
                        character_id=str(payload.get("character_id") or "").strip(),
                        project_id=str(payload.get("project_id") or "").strip(),
                        model=str(payload.get("model") or "").strip(),
                        thinking_power=thinking_power,
                    )
                if path == "/v1/history/create":
                    result = owner.controller.create_history()
                    return {"ok": True, "result": result, **owner.controller.work_panel_history_state()}
                if path == "/v1/history/select":
                    history_uid = _require_safe_history_uid(payload.get("history_uid"))
                    result = owner.controller.select_history(history_uid)
                    return {"ok": True, "result": result, **owner.controller.work_panel_history_state(history_uid)}
                if path == "/v1/history/delete":
                    self._confirmed(payload)
                    history_uid = _require_safe_history_uid(payload.get("history_uid"))
                    result = owner.controller.delete_history(history_uid)
                    return {"ok": True, "result": result, **owner.controller.work_panel_history_state()}
                if path == "/v1/memory/add":
                    self._confirmed(payload)
                    content = str(payload.get("content") or "").strip()
                    if not content:
                        raise ValueError("Memory content is required.")
                    if len(content) > MAX_MEMORY_TEXT_LENGTH:
                        raise ValueError("Memory content is too long.")
                    changed = owner.controller.add_memory(content)
                    return {"ok": True, "changed": changed, **owner.controller.work_panel_memory_state()}
                if path == "/v1/memory/status":
                    self._confirmed(payload)
                    status = str(payload.get("status") or "").strip()
                    if status not in MEMORY_STATUSES:
                        raise ValueError("Unsupported memory status.")
                    changed = owner.controller.set_memory_status(
                        str(payload.get("entry_id") or "").strip(),
                        status,
                    )
                    return {"ok": True, "changed": changed, **owner.controller.work_panel_memory_state()}
                if path == "/v1/memory/delete":
                    self._confirmed(payload)
                    changed = owner.controller.delete_memory(
                        str(payload.get("entry_id") or "").strip()
                    )
                    return {"ok": True, "changed": changed, **owner.controller.work_panel_memory_state()}
                if path == "/v1/memory/compact":
                    self._confirmed(payload)
                    result = owner.controller.compact_memory()
                    return {"ok": True, "result": result, **owner.controller.work_panel_memory_state()}
                raise LookupError("Unknown launcher control route.")

            def do_GET(self) -> None:
                if not self._authorized():
                    self._send(401, {"ok": False, "error": "Launcher control authorization failed."})
                    return
                parsed = urlparse(self.path)
                try:
                    payload = self._dispatch_read(parsed.path, parse_qs(parsed.query))
                    self._send(200, payload)
                except LookupError as exc:
                    self._send(404, {"ok": False, "error": str(exc)})
                except ValueError as exc:
                    self._send(400, {"ok": False, "error": str(exc)})
                except Exception as exc:
                    owner.log(f"Launcher control read failed: {exc}")
                    self._send(500, {"ok": False, "error": "Launcher control read failed."})

            def do_POST(self) -> None:
                if not self._authorized():
                    self._send(401, {"ok": False, "error": "Launcher control authorization failed."})
                    return
                parsed = urlparse(self.path)
                try:
                    payload = self._payload()
                except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                    self._send(400, {"ok": False, "error": str(exc)})
                    return

                if not owner._action_lock.acquire(blocking=False):
                    self._send(409, {"ok": False, "error": "另一個 Kuro 設定操作仍在執行。"})
                    return
                try:
                    result = self._dispatch_write(parsed.path, payload)
                    self._send(200, result)
                except LookupError as exc:
                    self._send(404, {"ok": False, "error": str(exc)})
                except PermissionError as exc:
                    self._send(409, {"ok": False, "error": str(exc)})
                except ValueError as exc:
                    self._send(400, {"ok": False, "error": str(exc)})
                except RuntimeError as exc:
                    self._send(409, {"ok": False, "error": str(exc)})
                except Exception as exc:
                    owner.log(f"Launcher control action failed: {exc}")
                    self._send(500, {"ok": False, "error": "Launcher control action failed."})
                finally:
                    owner._action_lock.release()

        return Handler
