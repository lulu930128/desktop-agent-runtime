import json
import os
import uuid
from .mcpp.privacy import project, safe_text
from datetime import datetime
from typing import Any, Literal

from loguru import logger

from .chat_history_manager import _get_safe_history_path


HistoryEventType = Literal[
    "tool_call",
    "omi_evidence",
    "memory_update",
    "memory_skipped",
]


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _compact_text(value: Any, max_len: int = 360) -> str:
    value = project(value)
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False)
        except Exception:
            value = str(value)
    compact = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 1].rstrip(" ，、。,.!?！？；;:：") + "…"


def _event_path(conf_uid: str, history_uid: str) -> str:
    history_path = _get_safe_history_path(conf_uid, history_uid)
    root, _ = os.path.splitext(history_path)
    return f"{root}.events.jsonl"


def store_history_event(
    *,
    conf_uid: str,
    history_uid: str,
    event_type: HistoryEventType,
    status: str = "ok",
    title: str = "",
    summary: str = "",
    detail: Any = None,
    compact_detail: bool = True,
    detail_max_len: int = 1200,
) -> bool:
    if not conf_uid or not history_uid:
        return False

    event = {
        "id": uuid.uuid4().hex,
        "type": event_type,
        "status": _compact_text(status, max_len=40) or "ok",
        "title": _compact_text(title, max_len=80),
        "summary": _compact_text(summary, max_len=360),
        "timestamp": _now_iso(),
    }
    if detail is not None:
        if compact_detail:
            event["detail"] = _compact_text(detail, max_len=max(120, detail_max_len))
        else:
            event["detail"] = project(detail)

    try:
        path = _event_path(conf_uid, history_uid)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
            f.write("\n")
        return True
    except Exception as e:
        logger.warning(f"Failed to store history event: {e}")
        return False


def read_history_events(
    conf_uid: str,
    history_uid: str,
    *,
    event_types: set[str] | None = None,
    limit: int = 80,
) -> list[dict[str, Any]]:
    if not conf_uid or not history_uid:
        return []

    try:
        path = _event_path(conf_uid, history_uid)
    except Exception:
        return []

    if not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except Exception as e:
        logger.warning(f"Failed to read history events: {e}")
        return []

    events: list[dict[str, Any]] = []
    for line in lines[-max(1, limit) :]:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "")
        if event_types and event_type not in event_types:
            continue
        events.append(event)
    return events
