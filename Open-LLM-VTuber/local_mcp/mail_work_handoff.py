"""Allowlisted actionable metadata from a successful existing Mail fetch only."""
import json
import os
from pathlib import Path
import tempfile

from mail_status_handoff import (_atomic_replace, _commit_lock, _timestamp, MailStatusWriteError)

MAX_BYTES = 2 * 1024 * 1024
MAX_ITEMS = 500
TEXT_FIELDS = {"id": 120, "threadId": 120, "subject": 240, "from": 240,
               "senderEmail": 240, "date": 80}
BOOL_FIELDS = ("unread", "requiredEvent", "muted", "attention", "gmailImportant")
PRIORITIES = {"low", "normal", "medium", "high", "critical", "urgent", "muted"}


class MailWorkWriteError(Exception):
    """Sanitized local handoff error; never return payload/path/provider errors."""


def _text(value, maximum):
    if not isinstance(value, str):
        raise ValueError("Invalid work text")
    return value.strip()[:maximum]


def build_work_handoff(snapshot, *, attempt_at):
    messages = snapshot["mail"]["messages"]
    if not isinstance(messages, list) or len(messages) > MAX_ITEMS:
        raise ValueError("Invalid work count")
    stamp = _timestamp(snapshot["updatedAt"])
    attempt = _timestamp(attempt_at)
    items = []
    seen = set()
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("Invalid work item")
        item = {key: _text(message.get(key, ""), maximum) for key, maximum in TEXT_FIELDS.items()}
        raw_id = message.get("id", "")
        if (not item["id"] or len(raw_id.strip()) > 120 or item["id"] in seen
                or any(ord(c) < 32 or ord(c) == 127 for c in item["id"])):
            raise ValueError("Invalid or duplicate work identity")
        if len(message.get("threadId", "").strip()) > 120:
            raise ValueError("Invalid thread identity")
        seen.add(item["id"])
        for key in BOOL_FIELDS:
            value = message.get(key, False)
            if type(value) is not bool:
                raise ValueError("Invalid work boolean")
            item[key] = value
        priority = message.get("priorityLevel", "normal")
        if not isinstance(priority, str) or priority not in PRIORITIES:
            raise ValueError("Invalid work priority")
        item["priorityLevel"] = priority
        event = message.get("event")
        if event is not None and not isinstance(event, dict):
            raise ValueError("Invalid work event")
        item["event"] = {key: _text((event or {}).get(key, ""), maximum)
                         for key, maximum in (("id", 120), ("name", 120), ("category", 80))}
        items.append(item)
    return {"schemaVersion": 1, "source": "gmail_briefing", "contract": "kuro.mail.work.v1",
            "updatedAt": stamp.isoformat(), "attemptAt": attempt.isoformat(), "items": items}


def write_work(file_path, *, private_root, attempt_at, snapshot=None):
    # Failed provider attempts must leave the last-good file byte-for-byte intact.
    if snapshot is None:
        return "preserved"
    temp_path = None
    try:
        path = Path(file_path)
        root = Path(private_root).resolve()
        if not path.is_absolute():
            raise ValueError("Work path must be absolute")
        path = path.resolve()
        path.relative_to(root)
        if path == root:
            raise ValueError("Work path must be a private file")
        payload = build_work_handoff(snapshot, attempt_at=attempt_at)
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(raw) > MAX_BYTES:
            raise ValueError("Work too large")
        path.parent.mkdir(parents=True, exist_ok=True)
        with _commit_lock(path.with_name(path.name + ".lock")):
            try:
                with path.open("rb") as handle:
                    previous_raw = handle.read(MAX_BYTES + 1)
                if len(previous_raw) <= MAX_BYTES:
                    previous = json.loads(previous_raw.decode("utf-8"))
                    if (isinstance(previous, dict) and previous.get("contract") == "kuro.mail.work.v1"
                            and _timestamp(previous["attemptAt"]) >= _timestamp(attempt_at)):
                        return "superseded"
            except (FileNotFoundError, ValueError, KeyError, TypeError, RecursionError):
                pass  # Fresh provider success may repair a malformed old handoff.
            fd, name = tempfile.mkstemp(prefix=".mail-work-", suffix=".tmp", dir=path.parent)
            temp_path = Path(name)
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            _atomic_replace(temp_path, path)
            temp_path = None
        return "written"
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError, MailStatusWriteError):
        raise MailWorkWriteError("mail_work_write_failed") from None
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                raise MailWorkWriteError("mail_work_temp_cleanup_failed") from None
