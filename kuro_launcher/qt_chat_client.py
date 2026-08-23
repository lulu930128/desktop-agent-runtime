from __future__ import annotations

import json
import threading
import time
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

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._ws_url = ""
        self._ws_app: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._send_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._connected = False
        self._assistant_parts: list[str] = []
        self._assistant_text = ""
        self.client_uid = ""
        self.conf_name = ""
        self.conf_uid = ""
        self.current_history_uid = ""
        self.current_history_title = ""

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
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="kuro-qt-chat-ws", daemon=True)
        self._thread.start()

    def disconnect(self) -> None:
        self._stop_event.set()
        app = self._ws_app
        if app is not None:
            try:
                app.close()
            except Exception:
                pass
        self._ws_app = None
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
        }
        if images:
            payload["images"] = images
        if files:
            payload["files"] = files
        return self._send_json(payload)

    def send_interrupt(self) -> bool:
        return self._send_json({"type": "interrupt-signal", "text": "launcher-interrupt"})

    def request_history_list(self) -> bool:
        return self._send_json({"type": "fetch-history-list"})

    def select_history(self, history_uid: str) -> bool:
        history_uid = (history_uid or "").strip()
        if not history_uid:
            self.error_occurred.emit("請先選擇一段聊天。")
            return False
        return self._send_json({"type": "fetch-and-set-history", "history_uid": history_uid})

    def create_history(self, *, force_new: bool = True) -> bool:
        return self._send_json({"type": "create-new-history", "force_new": bool(force_new)})

    def delete_history(self, history_uid: str) -> bool:
        history_uid = (history_uid or "").strip()
        if not history_uid:
            self.error_occurred.emit("請先選擇要刪除的聊天。")
            return False
        return self._send_json({"type": "delete-history", "history_uid": history_uid})

    def _run_loop(self) -> None:
        attempt = 0
        while not self._stop_event.is_set():
            attempt += 1
            self.state_changed.emit("connecting", False)
            app = websocket.WebSocketApp(
                self._ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            self._ws_app = app
            try:
                app.run_forever(ping_interval=25, ping_timeout=10)
            except Exception as exc:
                self.error_occurred.emit(str(exc))

            if self._stop_event.is_set():
                break
            delay = min(8.0, 1.0 + attempt * 0.75)
            self.log_event.emit(f"chat websocket reconnect in {delay:.1f}s")
            time.sleep(delay)

    def _on_open(self, app: websocket.WebSocketApp) -> None:
        self._connected = True
        self._assistant_parts = []
        self._assistant_text = ""
        self.state_changed.emit("connected", True)
        self.log_event.emit("chat websocket connected")

    def _on_close(self, _app: websocket.WebSocketApp, status_code: int, message: str) -> None:
        was_connected = self._connected
        self._connected = False
        if was_connected:
            self.log_event.emit(f"chat websocket closed: {status_code or '-'} {message or ''}".strip())
        self.state_changed.emit("offline", False)

    def _on_error(self, _app: websocket.WebSocketApp, error: Any) -> None:
        self.error_occurred.emit(str(error))

    def _on_message(self, _app: websocket.WebSocketApp, raw_message: str) -> None:
        try:
            payload = json.loads(str(raw_message or "{}"))
        except Exception as exc:
            self.error_occurred.emit(f"WebSocket JSON parse failed: {exc}")
            return
        if not isinstance(payload, dict):
            return
        self.message_received.emit(payload)
        self._handle_payload(payload)

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
                        "source": "upload",
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
            self.client_uid = str(payload.get("client_uid") or "")
            self.conf_name = str(payload.get("conf_name") or "")
            self.conf_uid = str(payload.get("conf_uid") or "")
            self.client_changed.emit(self.client_uid, self.conf_name, self.conf_uid)
            return

        if message_type == "history-list":
            histories = payload.get("histories") if isinstance(payload.get("histories"), list) else []
            selected = histories[0] if histories else {}
            if isinstance(selected, dict):
                history_uid = str(selected.get("uid") or selected.get("history_uid") or "").strip()
                title = str(selected.get("title") or "").strip()
                if history_uid:
                    self._set_history(history_uid, title)
            self.history_changed.emit(self.current_history_uid, self.current_history_title)
            return

        if message_type == "new-history-created":
            history_uid = str(payload.get("history_uid") or "").strip()
            if history_uid:
                self._set_history(history_uid, "")
            return

        if message_type == "history-data":
            self.history_changed.emit(self.current_history_uid, self.current_history_title)
            return

        if message_type == "history-deleted":
            self.history_changed.emit("", "")
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
            self._send_json({"type": "frontend-playback-complete"}, require_connected=False)
            self.state_changed.emit("idle", True)
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
        self.current_history_uid = history_uid
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
        return " ".join(str(value).replace("\r", " ").replace("\n", " ").split()).strip()
