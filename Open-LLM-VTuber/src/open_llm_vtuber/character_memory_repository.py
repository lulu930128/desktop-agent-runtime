from __future__ import annotations

import json
import os
import hashlib
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class MemorySnapshot(dict):
    """Read revision kept outside serialized user data."""
    disk_digest: str | None = None


@contextmanager
def store_lock(path: Path):
    """Process-safe, non-blocking lock; the OS releases it after a crash."""
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if not handle.tell():
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise ValueError("Memory store is busy; reload before retrying.") from None
        else:
            import fcntl
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ValueError("Memory store is busy; reload before retrying.") from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


class CharacterMemoryRepository:
    """Filesystem-backed store for character long-term memories.

    The repository owns path safety, default store shape, and atomic JSON writes.
    Higher layers should treat the returned dict as the canonical persistence
    format until a database-backed repository replaces this implementation.
    """

    def __init__(self, root_env_var: str = "KURO_MEMORY_ROOT") -> None:
        self._root_env_var = root_env_var

    def root(self) -> Path:
        root = os.getenv(self._root_env_var, "").strip()
        return Path(root) if root else Path("memories")

    def safe_path_component(self, value: str) -> str:
        safe = os.path.basename((value or "").strip())
        if not safe or safe in {".", ".."}:
            raise ValueError("Invalid memory path component.")
        if any(ch in safe for ch in '<>:"/\\|?*') or any(ord(ch) < 32 for ch in safe):
            raise ValueError(f"Invalid characters in memory path component: {value}")
        return safe

    def store_path(self, conf_uid: str) -> Path:
        safe_conf_uid = self.safe_path_component(conf_uid)
        return self.root() / "characters" / safe_conf_uid / "long_term.json"

    def empty_store(self, conf_uid: str) -> dict[str, Any]:
        now = _now_iso()
        return MemorySnapshot({
            "version": 1,
            "scope": "character",
            "conf_uid": conf_uid,
            "created_at": now,
            "updated_at": now,
            "entries": [],
        })

    def load(self, conf_uid: str) -> dict[str, Any]:
        path = self.store_path(conf_uid)
        if not path.exists():
            return self.empty_store(conf_uid)

        try:
            raw = path.read_bytes()
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            logger.error("Failed to load character memory store; raw error omitted.")
            raise ValueError("Memory store could not be read; refusing an empty replacement.") from None

        if not isinstance(data, dict):
            raise ValueError("Invalid memory store; refusing an empty replacement.")

        data.setdefault("version", 1)
        data.setdefault("scope", "character")
        data.setdefault("conf_uid", conf_uid)
        data.setdefault("created_at", _now_iso())
        data.setdefault("updated_at", data.get("created_at") or _now_iso())
        if not isinstance(data.get("entries"), list):
            raise ValueError("Invalid memory entries; refusing an empty replacement.")
        snapshot = MemorySnapshot(data)
        snapshot.disk_digest = hashlib.sha256(raw).hexdigest()
        return snapshot

    def save(self, conf_uid: str, data: dict[str, Any]) -> None:
        path = self.store_path(conf_uid)
        path.parent.mkdir(parents=True, exist_ok=True)
        with store_lock(path):
            current = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
            if current != getattr(data, "disk_digest", None):
                raise ValueError("Memory changed since read; reload before saving.")
            data["updated_at"] = _now_iso()
            payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            fd, temporary = tempfile.mkstemp(prefix=".memory-", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as out:
                    out.write(payload)
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(temporary, path)
                if isinstance(data, MemorySnapshot):
                    data.disk_digest = hashlib.sha256(payload).hexdigest()
            finally:
                Path(temporary).unlink(missing_ok=True)
