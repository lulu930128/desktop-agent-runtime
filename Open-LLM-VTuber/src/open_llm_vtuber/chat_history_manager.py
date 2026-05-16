import os
import re
import json
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
    return datetime.now().isoformat(timespec="seconds")


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

    if not _is_safe_filename(sanitized):
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
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(initial_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to create new history file: {e}")
        return ""

    logger.debug(f"Created new history file with empty metadata: {filepath}")
    return history_uid


def store_message(
    conf_uid: str,
    history_uid: str,
    role: Literal["human", "ai"],
    content: str,
    name: str | None = None,
    avatar: str | None = None,
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
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                history_data = json.load(f)
        except Exception:
            logger.error(f"Failed to load history file: {filepath}")
            pass

    metadata = _ensure_metadata_entry(history_data)

    now_str = _now_iso()
    new_item = {
        "role": role,
        "timestamp": now_str,
        "content": content,
    }

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

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(history_data, f, ensure_ascii=False, indent=2)
    logger.debug(f"Successfully stored {role} message")


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
        logger.error(f"Failed to get metadata: {e}")
    return {}


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

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)

        logger.debug(f"Updated metadata for history {history_uid}")
        return True
    except Exception as e:
        logger.error(f"Failed to set metadata: {e}")
    return False


def touch_history_opened(conf_uid: str, history_uid: str) -> bool:
    return update_metadate(
        conf_uid,
        history_uid,
        {
            "last_opened_at": _now_iso(),
        },
    )


def get_history(conf_uid: str, history_uid: str) -> List[HistoryMessage]:
    """Read chat history for the given conf_uid and history_uid"""
    if not conf_uid or not history_uid:
        if not conf_uid:
            logger.warning("Missing conf_uid")
        if not history_uid:
            logger.warning("Missing history_uid")
        return []

    filepath = _get_safe_history_path(conf_uid, history_uid)

    if not os.path.exists(filepath):
        logger.warning(f"History file not found: {filepath}")
        return []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            history_data = json.load(f)
            # Filter out metadata
            return [msg for msg in history_data if msg["role"] != "metadata"]
    except Exception:
        return []


def delete_history(conf_uid: str, history_uid: str) -> bool:
    """Delete a specific history file"""
    if not conf_uid or not history_uid:
        logger.warning("Missing conf_uid or history_uid")
        return False

    filepath = _get_safe_history_path(conf_uid, history_uid)
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.debug(f"Successfully deleted history file: {filepath}")
            return True
    except Exception as e:
        logger.error(f"Failed to delete history file: {e}")
    return False


def get_history_list(conf_uid: str) -> List[dict]:
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
                logger.error(f"Error reading history file {filename}: {e}")
                continue

        histories.sort(
            key=lambda x: x["timestamp"] if x["timestamp"] else "", reverse=True
        )
        return histories

    except Exception as e:
        logger.error(f"Error listing histories: {e}")
        return []


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

        latest_message["content"] = new_content
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)

        logger.debug(f"Successfully modified latest {role} message")
        return True

    except Exception as e:
        logger.error(f"Failed to modify latest message: {e}")
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
            os.rename(old_filepath, new_filepath)
            logger.info(
                f"Renamed history file from {old_history_uid} to {new_history_uid}"
            )
            return True
    except Exception as e:
        logger.error(f"Failed to rename history file: {e}")
    return False


def get_latest_history_uid(conf_uid: str) -> str:
    histories = get_history_list(conf_uid)
    if not histories:
        return ""
    return str(histories[0].get("uid") or "")
