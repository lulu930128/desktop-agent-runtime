"""Shared memory lifecycle and content-bound approval rules (no I/O)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

VALID_STATUSES = {"active", "pending_confirmation", "disabled", "superseded", "pending_delete"}
AUTHORIZED_SOURCES = {"manual", "explicit", "assistant_outcome_confirmed"}


def content_digest(entry: dict[str, Any]) -> str:
    payload = {key: entry.get(key, "") for key in (
        "content", "scope_level", "scope_id", "memory_type", "subject", "key"
    )}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def has_save_authorization(entry: dict[str, Any]) -> bool:
    approval = entry.get("save_authorization")
    if isinstance(approval, dict):
        try:
            authorized_at = datetime.fromisoformat(approval.get("authorized_at", ""))
        except (TypeError, ValueError):
            return False
        method = approval.get("method")
        return (approval.get("version") == 1 and isinstance(method, str)
                and method in {"manual", "explicit", "user_confirmation"}
                and approval.get("content_digest") == content_digest(entry)
                and authorized_at.tzinfo is not None)
    if "save_authorization" in entry:
        return False
    # Preserve identifiable pre-M0 manual/explicit records; never infer tool success.
    return isinstance(entry.get("source"), str) and entry["source"] in AUTHORIZED_SOURCES


def review_digest(entry: dict[str, Any]) -> str:
    """Bind a UI approval to the whole reviewed revision, including lifecycle."""
    return hashlib.sha256(json.dumps(entry, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def authorize(entry: dict[str, Any], method: str, reference: str = "") -> None:
    entry["save_authorization"] = {
        "version": 1, "method": method, "reference": reference,
        "content_digest": content_digest(entry),
        "authorized_at": datetime.now(timezone.utc).isoformat(),
    }


def entry_status(entry: dict[str, Any]) -> str:
    status = entry.get("status")
    if status is None and "status" not in entry:
        status = "active" if has_save_authorization(entry) else "pending_confirmation"
    if not isinstance(status, str) or status not in VALID_STATUSES:
        return "pending_confirmation"
    if entry.get("enabled", True) is not True:
        return "disabled" if status == "active" else status
    if status == "active" and not has_save_authorization(entry):
        return "pending_confirmation"
    return status


def is_active_memory(entry: dict[str, Any]) -> bool:
    return entry.get("enabled", True) is True and entry_status(entry) == "active"
