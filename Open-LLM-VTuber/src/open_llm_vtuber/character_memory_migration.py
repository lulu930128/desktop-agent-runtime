"""Explicit, digest-checked legacy migration. Nothing runs at import/startup."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .character_memory_lifecycle import entry_status, has_save_authorization
from .character_memory_repository import store_lock


def inventory(store: dict[str, Any]) -> list[dict[str, str]]:
    if not isinstance(store, dict) or not isinstance(store.get("entries"), list):
        raise ValueError("Invalid memory store; migration refused.")
    rows = []
    seen = set()
    for entry in store["entries"]:
        if not isinstance(entry, dict) or not entry.get("id") or entry["id"] in seen:
            raise ValueError("Invalid or duplicate memory identity; migration refused.")
        seen.add(entry["id"])
        classification = (
            "authorized" if has_save_authorization(entry) else
            "assistant_claim" if entry.get("source") == "assistant_outcome" else
            "insufficient_evidence"
        )
        rows.append({"id": entry["id"], "classification": classification,
                     "effective_status": entry_status(entry)})
    return rows


def dry_run(store: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    rows = inventory(store)
    result = deepcopy(store)
    changes = []
    for entry, row in zip(result["entries"], rows):
        status = row["effective_status"]
        enabled = status == "active"
        if entry.get("status") != status or entry.get("enabled") is not enabled:
            changes.append(row)
            entry["status"] = status
            entry["enabled"] = enabled
    result["trust_migration_version"] = 1
    return result, changes


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_migration(path: Path, *, expected_digest: str, backup: Path) -> dict[str, Any]:
    """Caller must authorize exact path/backup; operates on one store, never scans."""
    path, backup = path.resolve(strict=True), backup.resolve()
    if path == backup or backup.exists():
        raise ValueError("Backup must be a new distinct file.")
    original = path.read_bytes()
    if hashlib.sha256(original).hexdigest() != expected_digest:
        raise ValueError("Store changed since inventory.")
    updated, changes = dry_run(json.loads(original))
    backup.parent.mkdir(parents=True, exist_ok=True)
    with backup.open("xb") as out:
        out.write(original)
        out.flush()
        os.fsync(out.fileno())
    if file_digest(backup) != expected_digest:
        raise OSError("Backup verification failed.")
    _replace_checked(path, json.dumps(updated, ensure_ascii=False, indent=2).encode(), expected_digest)
    return {"changes": len(changes), "before_digest": expected_digest,
            "after_digest": file_digest(path), "index_rebuild_required": True}


def restore(path: Path, *, backup: Path, expected_current_digest: str, expected_backup_digest: str) -> None:
    original = backup.read_bytes()
    if hashlib.sha256(original).hexdigest() != expected_backup_digest:
        raise ValueError("Backup changed since migration; restore refused.")
    inventory(json.loads(original))
    _replace_checked(path, original, expected_current_digest)


def _replace_checked(path: Path, payload: bytes, expected_digest: str) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".memory-migration-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        with store_lock(path):
            if file_digest(path) != expected_digest:
                raise ValueError("Store changed during migration; backup retained.")
            os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
