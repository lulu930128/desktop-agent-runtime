from __future__ import annotations

import base64
import json
import struct
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Optional

import websocket
from PySide6.QtCore import QObject, Signal


class QtRuntimeChatClient(QObject):
    """Small WebSocket bridge for the Qt launcher chat tab.

    The Electron pet shell still owns media capture, audio playback, and Live2D
    lip-sync. This client only covers text chat control and runtime status so
    the Qt console does not need to embed the legacy Web UI.
    """

    state_changed = Signal(str, bool)
    message_received = Signal(dict)
    assistant_text_changed = Signal(str)
    history_changed = Signal(str, str)
    client_changed = Signal(str, str, str)
    error_occurred = Signal(str)
    log_event = Signal(str)
    history_operation_changed = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._ws_url = ""
        self._ws_app: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._send_lock = threading.Lock()
        self._scope_lock = threading.RLock()
        self._scope_cancelled = threading.Event()
        self._stop_event = threading.Event()
        self._connected = False
        self._assistant_parts: list[str] = []
        self._assistant_text = ""
        self.client_uid = ""
        self.conf_name = ""
        self.conf_uid = ""
        self.current_history_uid = ""
        self.current_history_title = ""
        self.context_id = ""
        self.active_project_id = ""
        self.history_protocol = ""
        self.effective_model = ""
        self.thinking_power = ""
        self._history_pending: dict | None = None
        self.history_request_id = ""
        self._history_generation = 0
        self._connection_generation = 0

    @property
    def history_ready(self) -> bool:
        return bool(self.connected and self.client_uid and self.conf_uid and self.context_id
                    and self.history_protocol == "kuro.conversation.history.v1")

    @property
    def history_pending(self) -> bool:
        return self._history_pending is not None

    def history_identity(self) -> tuple[str, str, str, str]:
        return self.history_scope_snapshot()[0]

    def history_scope_snapshot(self):
        """Atomically pair identity with a pure Python cancellation token."""
        with self._scope_lock:
            return (self.client_uid, self.conf_uid, self.context_id, self.current_history_uid), self._scope_cancelled

    @contextmanager
    def _changing_scope(self):
        # Transport updates invalidate already-queued work BEFORE any identity
        # field changes, independent of when the GUI consumes its queued signal.
        with self._scope_lock:
            self._scope_cancelled.set()
            try: yield
            finally: self._scope_cancelled = threading.Event()

    def expire_history_request(self) -> None:
        pending = self._history_pending
        if pending and time.monotonic() - pending["started"] > 15:
            self._history_pending = None
            self.history_operation_changed.emit("")
            self.error_occurred.emit("對話操作逾時，結果未確認；請重新讀取紀錄，不會自動重送。")

    def _history_request(self, operation: str, **values) -> bool:
        if not self.history_ready:
            self.error_occurred.emit("對話紀錄尚未就緒；需要支援 history.v1 的 Conversation Runtime。")
            return False
        if self.history_pending:
            return False
        self._history_generation += 1
        payload = {"type": operation, "request_id": uuid.uuid4().hex,
                   "client_uid": self.client_uid, "conf_uid": self.conf_uid,
                   "context_id": self.context_id,
                   "expected_history_uid": self.current_history_uid, **values}
        self._history_pending = {**payload, "started": time.monotonic(),
                                 "generation": self._history_generation}
        # Submission correlation outlives pending: the WS thread can accept a
        # reply before the GUI caller returns from _send_json.
        self.history_request_id = payload["request_id"]
        self.history_operation_changed.emit(operation)
        if self._send_json(payload):
            return True
        self._history_pending = None
        self.history_operation_changed.emit("")
        return False

    def _accept_history_response(self, payload: dict) -> bool:
        pending = self._history_pending
        if not pending or payload.get("request_id") != pending["request_id"]:
            return False
        if any(payload.get(key) != pending[key] for key in ("client_uid", "conf_uid", "context_id")):
            return False
        expected = {"fetch-history-list": "history-list", "fetch-and-set-history": "history-data",
                    "create-new-history": "new-history-created", "delete-history": "history-deleted"}
        if payload.get("type") not in {expected[pending["type"]], "history-error"}:
            return False
        if (pending["type"] in {"fetch-and-set-history", "delete-history"}
                and payload.get("type") != "history-error"
                and payload.get("history_uid") != pending["history_uid"]):
            return False
        self._history_pending = None
        self.history_operation_changed.emit("")
        return True

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def ws_url(self) -> str:
        return self._ws_url

    def connect_to(self, ws_url: str) -> None:
        ws_url = (ws_url or "").strip()
        if not ws_url:
            self.error_occurred.emit("WebSocket URL is empty.")
            return
        if self._thread and self._thread.is_alive() and self._ws_url == ws_url:
            return
        self.disconnect()
        self._ws_url = ws_url
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run_loop,
            args=(self._connection_generation, ws_url, self._stop_event),
            name="kuro-qt-chat-ws", daemon=True)
        self._thread.start()

    def disconnect(self) -> None:
        self._stop_event.set()
        self._connection_generation += 1
        self._history_pending = None
        with self._changing_scope():
            self.context_id = ""
            self.history_protocol = ""
        app = self._ws_app
        self._ws_app = None
        if app is not None:
            try:
                app.close()
            except Exception:
                pass
        if self._connected:
            self._connected = False
            self.state_changed.emit("offline", False)

    def send_text(self, text: str, attachments: list[dict] | None = None) -> bool:
        text = (text or "").strip()
        images, files = self._normalize_attachments(attachments or [])
        if not text and not images and not files:
            self.error_occurred.emit("訊息不可空白。")
            return False
        payload: dict[str, Any] = {
            "type": "text-input",
            "text": text or "請分析我附上的檔案。",
            **self._conversation_identity(),
        }
        if images:
            payload["images"] = images
        if files:
            payload["files"] = files
        return self._send_json(payload)

    def send_interrupt(self) -> bool:
        return self._send_json({"type": "interrupt-signal", "text": "launcher-interrupt",
                                **self._conversation_identity()})

    def _conversation_identity(self) -> dict:
        # Older servers retain their original protocol. The formal view requires
        # history.v1 before enabling input; negotiated turns always carry scope.
        if not self.history_ready:
            return {}
        return dict(zip(("client_uid", "conf_uid", "context_id", "history_uid"), self.history_identity()))

    def send_capture(self, capture: dict, attachments: list[dict]) -> bool:
        """Only Qt can submit a bounded, explicitly requested microphone capture."""
        try:
            if capture.get("format") != "pcm16le" or capture.get("sampleRate") != 16000:
                raise ValueError("unsupported audio format")
            encoded = capture.get("data")
            if not isinstance(encoded, str) or len(encoded) > 2560000:
                raise ValueError("audio capture exceeds 60 seconds")
            pcm = base64.b64decode(encoded, validate=True)
            if not pcm or len(pcm) % 2 or len(pcm) > 1920000:
                raise ValueError("invalid audio capture")
            images, _files = self._normalize_attachments(attachments)
        except (ValueError, TypeError) as exc:
            self.error_occurred.emit(f"錄音無法送出：{exc}")
            return False
        # Keep chunks and the final trigger together with respect to other Qt sends.
        with self._send_lock:
            app = self._ws_app
            if not self._connected or app is None:
                self.error_occurred.emit("聊天 WebSocket 尚未連線，錄音未送出。")
                return False
            try:
                identity = self._conversation_identity()
                for offset in range(0, len(pcm), 8192):
                    samples = [v[0] / 32768.0 for v in struct.iter_unpack("<h", pcm[offset:offset + 8192])]
                    app.send(json.dumps({"type": "mic-audio-data", "audio": samples, **identity}))
                app.send(json.dumps({"type": "mic-audio-end", "images": images, **identity}))
                return True
            except Exception:
                # No replay after an uncertain send; reconnect starts a clean audio buffer.
                app.close()
                self.error_occurred.emit("錄音傳送中斷，請重新連線後再錄音。")
                return False

    def request_history_list(self) -> bool:
        return self._history_request("fetch-history-list")

    def select_history(self, history_uid: str) -> bool:
        history_uid = (history_uid or "").strip()
        if not history_uid:
            self.error_occurred.emit("請先選擇一段聊天。")
            return False
        return self._history_request("fetch-and-set-history", history_uid=history_uid)

    def create_history(self, *, force_new: bool = True) -> bool:
        return self._history_request("create-new-history", force_new=bool(force_new))

    def delete_history(self, history_uid: str, *, confirmed: bool = False) -> bool:
        history_uid = (history_uid or "").strip()
        if not history_uid:
            self.error_occurred.emit("請先選擇要刪除的聊天。")
            return False
        if not confirmed:
            self.error_occurred.emit("刪除對話需要當次確認。")
            return False
        return self._history_request("delete-history", history_uid=history_uid, confirmed=True)

    def _run_loop(self, generation: int, ws_url: str, stop_event: threading.Event) -> None:
        attempt = 0
        while not stop_event.is_set() and generation == self._connection_generation:
            attempt += 1
            self.state_changed.emit("connecting", False)
            app = websocket.WebSocketApp(
                ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            if stop_event.is_set() or generation != self._connection_generation:
                return
            self._ws_app = app
            try:
                app.run_forever(ping_interval=25, ping_timeout=10)
            except Exception as exc:
                if generation == self._connection_generation:
                    self.error_occurred.emit(str(exc))

            if stop_event.is_set() or generation != self._connection_generation:
                break
            delay = min(8.0, 1.0 + attempt * 0.75)
            self.log_event.emit(f"chat websocket reconnect in {delay:.1f}s")
            stop_event.wait(delay)

    def _on_open(self, app: websocket.WebSocketApp) -> None:
        if app is not self._ws_app:
            return
        self._connected = True
        self._assistant_parts = []
        self._assistant_text = ""
        self.state_changed.emit("connected", True)
        self.log_event.emit("chat websocket connected")

    def _on_close(self, _app: websocket.WebSocketApp, status_code: int, message: str) -> None:
        if _app is not self._ws_app:
            return
        was_connected = self._connected
        with self._changing_scope():
            self._connected = False
            self._history_pending = None
            self.context_id = ""
            self.history_protocol = ""
        if was_connected:
            self.log_event.emit(f"chat websocket closed: {status_code or '-'} {message or ''}".strip())
        self.state_changed.emit("offline", False)

    def _on_error(self, _app: websocket.WebSocketApp, error: Any) -> None:
        if _app is not self._ws_app:
            return
        self.error_occurred.emit(str(error))

    def _on_message(self, _app: websocket.WebSocketApp, raw_message: str) -> None:
        if _app is not self._ws_app:
            return  # A replaced connection must never deliver an old profile response.
        try:
            payload = json.loads(str(raw_message or "{}"))
        except Exception as exc:
            self.error_occurred.emit(f"WebSocket JSON parse failed: {exc}")
            return
        if not isinstance(payload, dict):
            return
        if payload.get("type") != "set-model-and-conf" and "conversation_scope" in payload:
            if payload["conversation_scope"] != self._conversation_identity():
                return  # A late tool/text/control event belongs to an older turn context.
        if payload.get("type") in {"history-list", "history-data", "new-history-created", "history-deleted", "history-error"}:
            if not self._accept_history_response(payload):
                return
        self._handle_payload(payload)
        self.message_received.emit(payload)

    def _send_json(self, payload: dict, *, require_connected: bool = True) -> bool:
        if require_connected and not self._connected:
            self.error_occurred.emit("聊天 WebSocket 尚未連線。")
            return False
        app = self._ws_app
        if app is None:
            self.error_occurred.emit("聊天 WebSocket 尚未建立。")
            return False
        try:
            with self._send_lock:
                app.send(json.dumps(payload, ensure_ascii=False))
            return True
        except Exception as exc:
            self.error_occurred.emit(str(exc))
            return False

    def _normalize_attachments(self, attachments: list[dict]) -> tuple[list[dict], list[dict]]:
        images: list[dict] = []
        files: list[dict] = []
        for item in attachments[:6]:
            if not isinstance(item, dict):
                continue
            data = str(item.get("data") or "")
            if not data.startswith("data:"):
                continue
            mime_type = str(item.get("mime_type") or item.get("type") or "application/octet-stream").strip()
            kind = str(item.get("kind") or "").strip().lower()
            if kind == "image" or mime_type.lower().startswith("image/"):
                images.append(
                    {
                        "source": item.get("source") if item.get("source") in {"camera", "screen"} else "upload",
                        "data": data,
                        "mime_type": mime_type,
                    }
                )
                continue
            files.append(
                {
                    "kind": kind or ("audio" if mime_type.lower().startswith("audio/") else "file"),
                    "name": str(item.get("name") or "uploaded-file"),
                    "data": data,
                    "mime_type": mime_type,
                    "size": int(item.get("size") or 0),
                }
            )
        return images, files

    def _handle_payload(self, payload: dict) -> None:
        message_type = str(payload.get("type") or "")

        if message_type == "set-model-and-conf":
            with self._changing_scope():
                self.effective_model = str(payload.get("effective_model") or "")
                self.thinking_power = str(payload.get("thinking_power") or "")
                self._history_pending = None
                self._history_generation += 1
                self.context_id = str(payload.get("context_id") or "")
                self.active_project_id = str(payload.get("active_project_id") or "")
                self.history_protocol = str(payload.get("history_protocol") or "")
                self.current_history_uid = ""
                self.current_history_title = ""
                self._assistant_parts = []
                self._assistant_text = ""
                self.client_uid = str(payload.get("client_uid") or "")
                self.conf_name = str(payload.get("conf_name") or "")
                self.conf_uid = str(payload.get("conf_uid") or "")
            self.client_changed.emit(self.client_uid, self.conf_name, self.conf_uid)
            return

        if message_type == "history-list":
            # Listing histories must not silently switch the primary session.
            if "current_history_uid" in payload:
                history = str(payload["current_history_uid"] or "")
                if history != self.current_history_uid:
                    with self._changing_scope(): self.current_history_uid = history
            return

        if message_type == "history-error":
            code = str(payload.get("error") or "history_operation_failed")
            reason = {
                "history_turn_busy": "對話仍在進行，請停止或等回覆結束後再操作。",
                "history_context_changed": "角色或工作階段已變更，請重新讀取對話紀錄。",
                "history_selection_changed": "目前對話已變更，請重新讀取後再操作。",
                "history_not_found_for_profile": "此角色已無法取得該對話，請重新讀取清單。",
                "history_operation_failed": "對話操作失敗，結果未確認；請重新讀取，不會自動重送。",
            }.get(code, "對話操作遭拒，請重新讀取後再試。")
            self.error_occurred.emit(f"{reason}（{code}）")
            return

        if message_type == "new-history-created":
            history_uid = str(payload.get("history_uid") or "").strip()
            if history_uid:
                self._set_history(history_uid, "")
            return

        if message_type == "history-data":
            history_uid = str(payload.get("history_uid") or self.current_history_uid)
            self._set_history(history_uid, str(payload.get("title") or ""))
            return

        if message_type == "history-deleted":
            if payload.get("success") and payload.get("history_uid") == self.current_history_uid:
                self._set_history("", "")
            return

        if message_type == "full-text":
            self._set_assistant_text(payload.get("text"))
            return

        if message_type == "audio":
            display_text = payload.get("display_text")
            if isinstance(display_text, dict):
                self._append_assistant_text(display_text.get("text"))
            return

        if message_type == "backend-synth-complete":
            # Only the presentation subscriber can acknowledge actual playback.
            return

        if message_type == "control":
            text = str(payload.get("text") or "")
            if text == "conversation-chain-start":
                self._assistant_parts = []
                self._assistant_text = ""
                self.assistant_text_changed.emit("")
                self.state_changed.emit("thinking", True)
            elif text == "conversation-chain-end":
                self.state_changed.emit("idle", True)
            elif text in {"interrupt", "interrupt-signal"}:
                self.state_changed.emit("interrupted", True)
            elif text == "audio-play-start":
                self.state_changed.emit("speaking", True)
            return

        if message_type == "error":
            self.error_occurred.emit(str(payload.get("message") or payload.get("error") or "WebSocket error"))
            return

        if message_type == "force-new-message":
            self.history_changed.emit(self.current_history_uid, self.current_history_title)

    def _set_history(self, history_uid: str, title: str) -> None:
        if self.current_history_uid != history_uid:
            with self._changing_scope(): self.current_history_uid = history_uid
        self.current_history_title = title
        self.history_changed.emit(history_uid, title)

    def _set_assistant_text(self, value: Any) -> None:
        text = self._normalize_text(value)
        if not text or text in {"Connection established", "Thinking..."}:
            return
        if not self._assistant_text or text.startswith(self._assistant_text):
            self._assistant_parts = [text]
            self._assistant_text = text
        elif text not in self._assistant_text:
            self._append_assistant_text(text)
            return
        self.assistant_text_changed.emit(self._assistant_text)

    def _append_assistant_text(self, value: Any) -> None:
        text = self._normalize_text(value)
        if not text:
            return
        if self._assistant_text == text or text in self._assistant_text:
            return
        if self._assistant_text and text.startswith(self._assistant_text):
            self._assistant_parts = [text]
            self._assistant_text = text
        else:
            if self._assistant_parts and self._assistant_parts[-1] == text:
                return
            self._assistant_parts.append(text)
            self._assistant_text = self._merge_text_fragments(self._assistant_parts)
        self.assistant_text_changed.emit(self._assistant_text)

    def _merge_text_fragments(self, parts: list[str]) -> str:
        output = ""
        for part in parts:
            if not part:
                continue
            if not output:
                output = part
                continue
            needs_space = output[-1:].isalnum() and part[:1].isalnum()
            output += (" " if needs_space else "") + part
        return output

    def _normalize_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
