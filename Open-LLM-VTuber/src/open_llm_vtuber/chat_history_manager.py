import os
import re
import json
from .mcpp.privacy import safe_text
from functools import wraps
from pathlib import Path
import tempfile
from .character_memory_repository import store_lock
import uuid
from datetime import datetime
from typing import Literal, List, TypedDict, Optional
from loguru import logger


class HistoryMessage(TypedDict):
    role: Literal["human", "ai"]
    timestamp: str
    content: str
    # Optional display information for the message
    name: Optional[str]
    avatar: Optional[str]


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def _compact_text(content: str, max_len: int = 80) -> str:
    if not isinstance(content, str):
        return ""
    compact = " ".join(content.replace("\r", " ").replace("\n", " ").split())
    compact = compact.strip(" \t\r\n\"'`")
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 1].rstrip(" ，、。,.!?！？；;:：") + "…"


def _derive_history_title(content: str) -> str:
    return _compact_text(content, max_len=28)


def _build_metadata(now_str: Optional[str] = None) -> dict:
    timestamp = now_str or _now_iso()
    return {
        "role": "metadata",
        "timestamp": timestamp,
        "created_at": timestamp,
        "updated_at": timestamp,
        "last_opened_at": timestamp,
        "last_message_at": "",
        "title": "",
        "summary_short": "",
        "last_preview": "",
        "auto_title": True,
        "message_count": 0,
    }


def _ensure_metadata_entry(history_data: list) -> dict:
    timestamp = _now_iso()
    if history_data and history_data[0].get("role") == "metadata":
        metadata = history_data[0]
    else:
        metadata = _build_metadata(timestamp)
        history_data.insert(0, metadata)

    metadata.setdefault("timestamp", timestamp)
    metadata.setdefault("created_at", metadata.get("timestamp", timestamp))
    metadata.setdefault("updated_at", metadata.get("created_at", timestamp))
    metadata.setdefault("last_opened_at", metadata.get("created_at", timestamp))
    metadata.setdefault("last_message_at", "")
    metadata.setdefault("title", "")
    metadata.setdefault("summary_short", "")
    metadata.setdefault("last_preview", "")
    metadata.setdefault("auto_title", True)
    metadata.setdefault("message_count", 0)
    return metadata


def _is_safe_filename(filename: str) -> bool:
    """Validate filename for safety and allowed characters"""
    if not filename or len(filename) > 255:
        return False

    # Allow alphanumeric, hyphen, underscore, and common unicode characters
    # Block any filesystem special characters, control characters, and path separators
    pattern = re.compile(r"^[\w\-_\u0020-\u007E\u00A0-\uFFFF]+$")
    return bool(pattern.match(filename))


def _sanitize_path_component(component: str) -> str:
    """Sanitize and validate a path component"""
    # Remove any path components, get just the basename
    sanitized = os.path.basename(component.strip())

    if sanitized != component.strip() or sanitized in {".",".."} or not _is_safe_filename(sanitized):
        raise ValueError(f"Invalid characters in path component: {component}")

    return sanitized


def _ensure_conf_dir(conf_uid: str) -> str:
    """Ensure the directory for a specific conf exists and return its path"""
    if not conf_uid:
        raise ValueError("conf_uid cannot be empty")

    safe_conf_uid = _sanitize_path_component(conf_uid)
    base_dir = os.path.join("chat_history", safe_conf_uid)
    os.makedirs(base_dir, exist_ok=True)
    return base_dir


def _get_safe_history_path(conf_uid: str, history_uid: str) -> str:
    """Get sanitized path for history file"""
    safe_conf_uid = _sanitize_path_component(conf_uid)
    safe_history_uid = _sanitize_path_component(history_uid)
    base_dir = os.path.join("chat_history", safe_conf_uid)
    full_path = os.path.normpath(os.path.join(base_dir, f"{safe_history_uid}.json"))
    if not full_path.startswith(base_dir):
        raise ValueError("Invalid path: Path traversal detected")
    return full_path


def _write_history(filepath, data):
    path = Path(filepath)
    fd, name = tempfile.mkstemp(prefix=".history-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _indexed_change(operation):
    """Publish intent before changing the source. Reconciliation shares this lock."""
    @wraps(operation)
    def changed(conf_uid, history_uid, *args, **kwargs):
        if not conf_uid or not history_uid:
            return operation(conf_uid, history_uid, *args, **kwargs)
        path = Path(_get_safe_history_path(conf_uid, history_uid))
        path.parent.mkdir(parents=True, exist_ok=True)
        with store_lock(path,wait=True):
            pending = path.parent / ".index-pending"
            pending.mkdir(exist_ok=True)
            (pending / path.name).touch()
            return operation(conf_uid, history_uid, *args, **kwargs)
    return changed


def create_new_history(conf_uid: str) -> str:
    """Create a new history file with a unique ID and return the history_uid"""
    if not conf_uid:
        logger.warning("No conf_uid provided")
        return ""

    # Use uuid.uuid4().hex to generate a UUID without hyphens
    # New format: UUID_YYYY-MM-DD_HH-MM-SS
    history_uid = f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_{uuid.uuid4().hex}"
    conf_dir = _ensure_conf_dir(conf_uid)  # conf_uid is sanitized here

    now_str = _now_iso()

    # Create history file with empty metadata
    try:
        filepath = os.path.join(conf_dir, f"{history_uid}.json")
        initial_data = [_build_metadata(now_str)]
        _write_history(filepath, initial_data)
    except Exception as e:
        logger.error('Failed to create new history file; payload details omitted.')
        return ""

    logger.debug(f"Created new history file with empty metadata: {filepath}")
    return history_uid


@_indexed_change
def store_message(
    conf_uid: str,
    history_uid: str,
    role: Literal["human", "ai"],
    content: str,
    name: str | None = None,
    avatar: str | None = None,
    *,
    turn_id: str = "",
    completion: str = "",
    project_id: str = "",
    formation_rule: str | None = None,
):
    """Store a message in a specific history file

    Args:
        conf_uid: Configuration unique identifier
        history_uid: History unique identifier
        role: Message role ("human" or "ai")
        content: Message content
        name: Optional display name (default None)
        avatar: Optional avatar URL (default None)
    """
    if not conf_uid or not history_uid:
        if not conf_uid:
            logger.warning("Missing conf_uid")
        if not history_uid:
            logger.warning("Missing history_uid")
        return

    filepath = _get_safe_history_path(conf_uid, history_uid)
    logger.debug(f"Storing {role} message to {filepath}")

    history_data = []
    previous_stat = Path(filepath).stat() if os.path.exists(filepath) else None
    if previous_stat:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                history_data = json.load(f)
        except Exception:
            logger.error(f"Failed to load history file: {filepath}")
            raise ValueError("Unreadable history; preserving original file") from None

    content = safe_text(content)
    if not isinstance(history_data,list) or not all(isinstance(row,dict) for row in history_data):
        raise ValueError("Invalid History source; preserving original")
    if turn_id:
        for index in range(len(history_data)-1,-1,-1):
            prior = history_data[index]
            if prior.get("turn_id")!=turn_id or prior.get("role")!=role:
                continue
            if (prior.get("content"),prior.get("completion",""),prior.get("project_id",""))!=(content,completion,project_id):
                raise ValueError("Conflicting History turn identity")
            previous = next((r.get("turn_id","") for r in reversed(history_data[:index]) if r.get("role")=="human"),"")
            return {"previous_turn_id":previous,"observed_at":prior.get("timestamp","")}
    metadata = _ensure_metadata_entry(history_data)
    previous_title = metadata.get("title", "")

    now_str = _now_iso()
    new_item = {
        "role": role,
        "timestamp": now_str,
        "content": content,
    }

    if turn_id:
        new_item.update(turn_id=turn_id, completion=completion, project_id=project_id)

    # Add optional display information if provided
    if name is not None:
        new_item["name"] = name
    if avatar is not None:
        new_item["avatar"] = avatar

    history_data.append(new_item)

    actual_messages = [msg for msg in history_data if msg.get("role") != "metadata"]
    metadata["updated_at"] = now_str
    metadata["last_message_at"] = now_str
    metadata["message_count"] = len(actual_messages)
    metadata["last_preview"] = _compact_text(content, max_len=88)

    first_human = next(
        (
            msg
            for msg in actual_messages
            if msg.get("role") == "human" and isinstance(msg.get("content"), str)
        ),
        None,
    )
    if first_human:
        if not metadata.get("title"):
            title = _derive_history_title(first_human.get("content", ""))
            if title:
                metadata["title"] = title
                metadata["auto_title"] = True
        if not metadata.get("summary_short"):
            metadata["summary_short"] = _compact_text(
                first_human.get("content", ""), max_len=72
            )

    if role == "ai" and completion == "complete" and formation_rule is not None:
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", turn_id):
            raise ValueError("Invalid formation turn identity")
        pending = Path(filepath).parent / ".formation-pending"
        pending.mkdir(exist_ok=True)
        _write_history(pending / (turn_id + ".json"),
                       {"history":history_uid, "turn":turn_id, "project_id":project_id, "policy_digest":formation_rule})
    _write_history(filepath, history_data)
    try:
        from .conversation_history_index import _CONVERSATION_HISTORY_INDEX
        _CONVERSATION_HISTORY_INDEX.record_append(conf_uid,history_uid,previous_stat,Path(filepath),
                                                   actual_messages,metadata.get("title",""),previous_title)
    except Exception as exc:
        logger.warning("History index append pending ({})", type(exc).__name__)
    logger.debug(f"Successfully stored {role} message")
    previous = next((m.get("turn_id", "") for m in reversed(actual_messages[:-1])
                     if m.get("role") == "human"), "")
    return {"previous_turn_id": previous, "observed_at": now_str}


def read_memory_source(root: Path, actor: str, history: str, turn: str):
    """Explicit management read of one referenced user statement, including renamed histories."""
    import sqlite3
    from contextlib import closing
    root=Path(root).resolve()
    if not (actor and history and turn):
        return None
    candidates=[history]
    db = root/"memories/conversation_history.sqlite3"
    if db.is_file():
        try:
            with closing(sqlite3.connect(db.as_uri()+"?mode=ro",uri=True)) as conn:
                candidates.extend(row[0] for row in conn.execute(
                    "SELECT DISTINCT history_uid FROM conversation_messages WHERE conf_uid=? AND json_extract(message_json,'$.turn_id')=?",
                    (actor,turn)))
        except sqlite3.Error:
            pass  # The canonical original path is still independently readable.
    for uid in dict.fromkeys(candidates):
        path = root / _get_safe_history_path(actor,uid)
        if path.is_file():
            rows=json.loads(path.read_bytes())
            for row in rows:
                if row.get("role") in {"human","user"} and row.get("turn_id")==turn:
                    return {"history":uid,"observed_at":row.get("timestamp",""),"project_id":row.get("project_id",""),"text":row.get("content","")}
    return None


def get_metadata(conf_uid: str, history_uid: str) -> dict:
    """Get metadata from history file"""
    if not conf_uid or not history_uid:
        return {}

    filepath = _get_safe_history_path(conf_uid, history_uid)
    if not os.path.exists(filepath):
        return {}

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            history_data = json.load(f)

        if history_data and history_data[0]["role"] == "metadata":
            return history_data[0]
    except Exception as e:
        logger.error('Failed to get metadata; payload details omitted.')
    return {}


@_indexed_change
def update_metadate(conf_uid: str, history_uid: str, metadata: dict) -> bool:
    """Set metadata in history file

    Updates existing metadata with new fields, preserving existing ones.
    If no metadata exists, creates new metadata entry.
    """
    if not conf_uid or not history_uid:
        return False

    filepath = _get_safe_history_path(conf_uid, history_uid)
    if not os.path.exists(filepath):
        return False

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            history_data = json.load(f)

        if history_data and history_data[0]["role"] == "metadata":
            # Update existing metadata while preserving other fields
            history_data[0].update(metadata)
        else:
            # Create new metadata with timestamp if none exists
            new_metadata = {
                "role": "metadata",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            }
            new_metadata.update(metadata)  # Add new fields
            history_data.insert(0, new_metadata)

        _write_history(filepath, history_data)

        logger.debug(f"Updated metadata for history {history_uid}")
        return True
    except Exception as e:
        logger.error('Failed to set metadata; payload details omitted.')
    return False


def touch_history_opened(conf_uid: str, history_uid: str) -> bool:
    return update_metadate(
        conf_uid,
        history_uid,
        {
            "last_opened_at": _now_iso(),
        },
    )


def get_history(conf_uid: str, history_uid: str, *, strict: bool = False) -> List[HistoryMessage]:
    """Read chat history for the given conf_uid and history_uid"""
    if not conf_uid or not history_uid:
        if not conf_uid:
            logger.warning("Missing conf_uid")
        if not history_uid:
            logger.warning("Missing history_uid")
        return []

    filepath = _get_safe_history_path(conf_uid, history_uid)

    if not os.path.exists(filepath):
        if strict:
            raise FileNotFoundError("History is unavailable")
        logger.warning(f"History file not found: {filepath}")
        return []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            history_data = json.load(f)
            # Filter out metadata
            return [msg for msg in history_data if msg["role"] != "metadata"]
    except Exception:
        if strict:
            raise
        return []


def get_history_timeline(conf_uid: str, history_uid: str, *, limit: int = 120, strict: bool = False) -> list[dict]:
    """Canonical transcript projection including runtime-owned tool/memory events."""
    from .chat_event_manager import read_history_events

    rows = [dict(message) for message in get_history(conf_uid, history_uid, strict=strict)
            if message.get("role") not in {"metadata", "system"}]
    for event in read_history_events(conf_uid, history_uid, limit=limit, strict=strict):
        title = str(event.get("title") or event.get("type") or "事件")
        state = str(event.get("status") or "")
        summary = str(event.get("summary") or "")
        rows.append({"role": "event", "timestamp": event.get("timestamp", ""),
                     "content": f"{title} · {state}\n{summary}".strip(), "event": event})

    def order(row):
        try:
            timestamp = datetime.fromisoformat(str(row.get("timestamp") or "").replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError, OverflowError, OSError):
            timestamp = 0.0
        priority = 0 if row.get("role") in {"human", "user"} else 1 if row.get("role") == "event" else 2
        return timestamp, priority

    return sorted(rows, key=order)[-max(1, min(limit, 500)):]


def delete_history_path(path: Path) -> int:
    """Remove the paired transcript and events and invalidate derived recall under the same lock."""
    if not path.parent.is_dir():
        return 0
    with store_lock(path,wait=True):
        pending = path.parent / ".index-pending"
        pending.mkdir(exist_ok=True)
        (pending / path.name).touch()
        count = 0
        for source in (path.with_suffix(".events.jsonl"),path):
            if source.exists():
                source.unlink()
                count += 1
        return count


def delete_history(conf_uid: str, history_uid: str) -> bool:
    if not conf_uid or not history_uid:
        return False
    try:
        return bool(delete_history_path(Path(_get_safe_history_path(conf_uid,history_uid))))
    except (OSError,ValueError):
        logger.error("Failed to delete history; details omitted.")
        return False


def get_history_list(conf_uid: str, *, strict: bool = False) -> List[dict]:
    """Get list of histories with their latest messages"""
    if not conf_uid:
        return []

    histories = []
    conf_dir = _ensure_conf_dir(conf_uid)
    try:
        for filename in os.listdir(conf_dir):
            if not filename.endswith(".json"):
                continue

            history_uid = filename[:-5]
            filepath = os.path.join(conf_dir, filename)

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    messages = json.load(f)
                    metadata = _ensure_metadata_entry(messages)

                    # Filter out metadata for checking if history is empty
                    actual_messages = [
                        msg for msg in messages if msg["role"] != "metadata"
                    ]

                    latest_message = actual_messages[-1] if actual_messages else None
                    first_human = next(
                        (
                            msg
                            for msg in actual_messages
                            if msg.get("role") == "human"
                            and isinstance(msg.get("content"), str)
                        ),
                        None,
                    )
                    title = str(metadata.get("title") or "").strip()
                    if not title:
                        title_seed = ""
                        if first_human:
                            title_seed = first_human.get("content", "")
                        elif latest_message:
                            title_seed = latest_message.get("content", "")
                        title = _derive_history_title(title_seed) or "新對話"

                    summary_short = str(metadata.get("summary_short") or "").strip()
                    if not summary_short:
                        summary_seed = ""
                        if first_human:
                            summary_seed = first_human.get("content", "")
                        elif latest_message:
                            summary_seed = latest_message.get("content", "")
                        summary_short = _compact_text(summary_seed, max_len=72)

                    last_preview = str(metadata.get("last_preview") or "").strip()
                    if not last_preview and latest_message:
                        last_preview = _compact_text(
                            latest_message.get("content", ""), max_len=88
                        )

                    sort_ts = (
                        str(metadata.get("updated_at") or "").strip()
                        or (
                            latest_message["timestamp"]
                            if latest_message and latest_message.get("timestamp")
                            else ""
                        )
                        or str(metadata.get("timestamp") or "").strip()
                    )
                    history_info = {
                        "uid": history_uid,
                        "title": title,
                        "summary_short": summary_short,
                        "last_preview": last_preview,
                        "latest_message": latest_message,
                        "timestamp": sort_ts or None,
                        "created_at": metadata.get("created_at"),
                        "updated_at": metadata.get("updated_at"),
                        "last_opened_at": metadata.get("last_opened_at"),
                        "is_empty": len(actual_messages) == 0,
                    }
                    histories.append(history_info)
            except Exception as e:
                logger.error('Error reading history file; payload details omitted.')
                if strict:
                    raise
                continue

        histories.sort(
            key=lambda x: x["timestamp"] if x["timestamp"] else "", reverse=True
        )
        return histories

    except Exception as e:
        logger.error('Error listing histories; payload details omitted.')
        if strict:
            raise
        return []


@_indexed_change
def modify_latest_message(
    conf_uid: str,
    history_uid: str,
    role: Literal["human", "ai", "system"],
    new_content: str,
) -> bool:
    """Modify the latest message in a specific history file if it matches the given role"""
    if not conf_uid or not history_uid:
        logger.warning("Missing conf_uid or history_uid")
        return False

    filepath = _get_safe_history_path(conf_uid, history_uid)
    if not os.path.exists(filepath):
        logger.warning(f"History file not found: {filepath}")
        return False

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            history_data = json.load(f)

        if not history_data:
            logger.warning("History is empty")
            return False

        latest_message = history_data[-1]
        if latest_message["role"] != role:
            logger.warning(
                f"Latest message role ({latest_message['role']}) doesn't match requested role ({role})"
            )
            return False

        latest_message["content"] = safe_text(new_content)
        _write_history(filepath, history_data)

        logger.debug(f"Successfully modified latest {role} message")
        return True

    except Exception as e:
        logger.error('Failed to modify latest message; payload details omitted.')
        return False


def rename_history_file(
    conf_uid: str, old_history_uid: str, new_history_uid: str
) -> bool:
    """Rename a history file with a new history_uid"""
    if not conf_uid or not old_history_uid or not new_history_uid:
        logger.warning("Missing required parameters for rename")
        return False

    old_filepath = _get_safe_history_path(conf_uid, old_history_uid)
    new_filepath = _get_safe_history_path(conf_uid, new_history_uid)

    try:
        if os.path.exists(old_filepath):
            from contextlib import ExitStack
            with ExitStack() as locks:
                for path in sorted({Path(old_filepath), Path(new_filepath)}):
                    locks.enter_context(store_lock(path,wait=True))
                    pending = path.parent / ".index-pending"
                    pending.mkdir(exist_ok=True)
                    (pending / path.name).touch()
                os.rename(old_filepath, new_filepath)
            logger.info(
                f"Renamed history file from {old_history_uid} to {new_history_uid}"
            )
            return True
    except Exception as e:
        logger.error('Failed to rename history file; payload details omitted.')
    return False


def get_latest_history_uid(conf_uid: str) -> str:
    histories = get_history_list(conf_uid)
    if not histories:
        return ""
    return str(histories[0].get("uid") or "")
