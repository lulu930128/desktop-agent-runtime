import os
from pathlib import Path

from open_llm_vtuber.character_memory_manager import format_character_memories_for_preview

from .records import MemoryRecord


MEMORY_STATUS_LABELS = {
    "active": "啟用",
    "pending_confirmation": "待確認",
    "superseded": "已取代",
    "disabled": "停用",
    "pending_delete": "待刪除",
}


def ensure_character_memory_root(open_llm_dir: Path) -> None:
    os.environ["KURO_MEMORY_ROOT"] = str((open_llm_dir / "memories").resolve())


def memory_status_from_entry(entry: dict) -> str:
    status = str(entry.get("status") or "").strip()
    if status in MEMORY_STATUS_LABELS:
        return status
    return "active" if entry.get("enabled", True) else "disabled"


def memory_record_is_active(record: MemoryRecord) -> bool:
    return record.enabled and record.status == "active"


def classify_memory_text(content: str) -> str:
    content = content or ""
    if any(token in content for token in ("叫我", "稱呼我", "我的名字", "我是")):
        return "identity"
    if any(token in content for token in ("不要", "別再", "不喜歡", "討厭")):
        return "boundary"
    if any(token in content for token in ("以後", "之後", "預設", "固定", "都要", "都不要")):
        return "instruction"
    if any(token in content for token in ("喜歡", "希望", "偏好", "習慣", "想要")):
        return "preference"
    return "fact"


def format_character_memory_preview(open_llm_dir: Path, conf_uid: str) -> str:
    conf_uid = (conf_uid or "").strip()
    if not conf_uid:
        return ""
    ensure_character_memory_root(open_llm_dir)
    try:
        return format_character_memories_for_preview(conf_uid)
    except Exception as exc:
        return f"角色長期記憶讀取失敗：{exc}"
