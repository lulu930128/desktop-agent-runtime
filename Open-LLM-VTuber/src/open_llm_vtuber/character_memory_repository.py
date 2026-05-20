from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


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
        return {
            "version": 1,
            "scope": "character",
            "conf_uid": conf_uid,
            "created_at": now,
            "updated_at": now,
            "entries": [],
        }

    def load(self, conf_uid: str) -> dict[str, Any]:
        path = self.store_path(conf_uid)
        if not path.exists():
            return self.empty_store(conf_uid)

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error(f"Failed to load character memory store {path}: {exc}")
            return self.empty_store(conf_uid)

        if not isinstance(data, dict):
            return self.empty_store(conf_uid)

        data.setdefault("version", 1)
        data.setdefault("scope", "character")
        data.setdefault("conf_uid", conf_uid)
        data.setdefault("created_at", _now_iso())
        data.setdefault("updated_at", data.get("created_at") or _now_iso())
        if not isinstance(data.get("entries"), list):
            data["entries"] = []
        return data

    def save(self, conf_uid: str, data: dict[str, Any]) -> None:
        path = self.store_path(conf_uid)
        path.parent.mkdir(parents=True, exist_ok=True)
        data["updated_at"] = _now_iso()
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp_path, path)
