from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypedDict

from loguru import logger


MemoryType = Literal[
    "preference",
    "instruction",
    "boundary",
    "identity",
    "fact",
]


class CharacterMemoryEntry(TypedDict, total=False):
    id: str
    scope: Literal["character"]
    memory_type: MemoryType
    content: str
    enabled: bool
    confidence: float
    importance: float
    source: str
    source_history_uid: str
    created_at: str
    updated_at: str


SENSITIVE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\b(api[_-]?key|secret|token|password|passwd|pwd)\b",
        r"\bBearer\s+[A-Za-z0-9._\-]+",
        r"\bsk-[A-Za-z0-9_\-]{12,}",
        r"\b[A-Za-z0-9_\-]{24,}\.[A-Za-z0-9_\-]{12,}\.[A-Za-z0-9_\-]{12,}\b",
    ]
]


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _memory_root() -> Path:
    root = os.getenv("KURO_MEMORY_ROOT", "").strip()
    return Path(root) if root else Path("memories")


def _safe_path_component(value: str) -> str:
    safe = os.path.basename((value or "").strip())
    if not safe or safe in {".", ".."}:
        raise ValueError("Invalid memory path component.")
    if any(ch in safe for ch in '<>:"/\\|?*') or any(ord(ch) < 32 for ch in safe):
        raise ValueError(f"Invalid characters in memory path component: {value}")
    return safe


def _store_path(conf_uid: str) -> Path:
    safe_conf_uid = _safe_path_component(conf_uid)
    return _memory_root() / "characters" / safe_conf_uid / "long_term.json"


def _empty_store(conf_uid: str) -> dict[str, Any]:
    now = _now_iso()
    return {
        "version": 1,
        "scope": "character",
        "conf_uid": conf_uid,
        "created_at": now,
        "updated_at": now,
        "entries": [],
    }


def _load_store(conf_uid: str) -> dict[str, Any]:
    path = _store_path(conf_uid)
    if not path.exists():
        return _empty_store(conf_uid)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error(f"Failed to load character memory store {path}: {exc}")
        return _empty_store(conf_uid)

    if not isinstance(data, dict):
        return _empty_store(conf_uid)

    data.setdefault("version", 1)
    data.setdefault("scope", "character")
    data.setdefault("conf_uid", conf_uid)
    data.setdefault("created_at", _now_iso())
    data.setdefault("updated_at", data.get("created_at") or _now_iso())
    if not isinstance(data.get("entries"), list):
        data["entries"] = []
    return data


def _save_store(conf_uid: str, data: dict[str, Any]) -> None:
    path = _store_path(conf_uid)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now_iso()
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def _clean_text(content: str, max_len: int = 260) -> str:
    clean = " ".join((content or "").replace("\r", " ").replace("\n", " ").split())
    clean = clean.strip(" \t\r\n\"'`")
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 1].rstrip("，。,.!?！？、 ") + "…"


def _normalize(content: str) -> str:
    return re.sub(r"[\s，。,.!?！？、:：；;「」『』\"'`]+", "", content or "").lower()


def _contains_sensitive_data(content: str) -> bool:
    return any(pattern.search(content or "") for pattern in SENSITIVE_PATTERNS)


def _classify_memory_type(content: str) -> MemoryType:
    if re.search(r"(叫我|稱呼我|我的名字|我是)", content):
        return "identity"
    if re.search(r"(不要|別再|不要再|不喜歡|討厭)", content):
        return "boundary"
    if re.search(r"(以後|之後|預設|固定|都要|都不要|請你)", content):
        return "instruction"
    if re.search(r"(喜歡|希望|偏好|習慣|想要)", content):
        return "preference"
    return "fact"


def _extract_after_marker(content: str, markers: list[str]) -> str:
    best = ""
    for marker in markers:
        index = content.find(marker)
        if index < 0:
            continue
        candidate = content[index + len(marker) :]
        candidate = candidate.lstrip(" ：:，,。 ")
        if candidate and (not best or len(candidate) < len(best)):
            best = candidate
    return best


def _extract_memory_candidates(user_text: str) -> list[dict[str, Any]]:
    text = _clean_text(user_text, max_len=600)
    if not text:
        return []

    candidates: list[dict[str, Any]] = []

    remember_target = _extract_after_marker(
        text,
        ["幫我記住", "請記住", "記住", "記起來"],
    )
    if remember_target:
        for clause in re.split(r"[，。,；;、]", remember_target):
            clause = _clean_text(clause)
            if not clause or re.search(r"(叫我|稱呼我)", clause):
                continue
            content = (
                clause
                if re.search(r"(以後|之後|預設|我希望|我喜歡|我不喜歡|我習慣|不要)", clause)
                else f"使用者要求記住：{clause}"
            )
            candidates.append(
                {
                    "content": content,
                    "source": "explicit",
                    "importance": 0.85,
                }
            )

    nickname_match = re.search(r"(?:以後|之後)?(?:請)?(?:叫我|稱呼我)[「『\"]?([^，。,.!?！？\n」』\"]{1,32})", text)
    has_nickname_candidate = bool(nickname_match)
    if nickname_match:
        nickname = _clean_text(nickname_match.group(1), max_len=40)
        if nickname:
            candidates.append(
                {
                    "content": f"使用者希望被稱呼為「{nickname}」。",
                    "source": "explicit",
                    "importance": 0.95,
                    "memory_type": "identity",
                }
            )

    stable_patterns = [
        r"(以後[^。！？!?]{2,160})",
        r"(之後[^。！？!?]{2,160})",
        r"(預設[^。！？!?]{2,160})",
        r"(我希望[^。！？!?]{2,160})",
        r"(我喜歡[^。！？!?]{2,160})",
        r"(我不喜歡[^。！？!?]{2,160})",
        r"(我習慣[^。！？!?]{2,160})",
        r"(不要再[^。！？!?]{2,160})",
        r"(不要每次[^。！？!?]{2,160})",
        r"(別再[^。！？!?]{2,160})",
    ]
    for pattern in stable_patterns:
        for match in re.finditer(pattern, text):
            phrase = _clean_text(match.group(1))
            if has_nickname_candidate and re.search(r"(叫我|稱呼我)", phrase):
                continue
            if phrase:
                candidates.append(
                    {
                        "content": phrase,
                        "source": "heuristic",
                        "importance": 0.68,
                    }
                )

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        content = _clean_text(str(candidate.get("content") or ""))
        key = _normalize(content)
        if not content or key in seen:
            continue
        seen.add(key)
        candidate["content"] = content
        candidate.setdefault("memory_type", _classify_memory_type(content))
        candidate.setdefault("confidence", 0.88 if candidate.get("source") == "explicit" else 0.72)
        deduped.append(candidate)
    return deduped


def _extract_forget_target(user_text: str) -> str:
    text = _clean_text(user_text, max_len=500)
    if not re.search(r"(忘記|忘掉|刪掉|刪除|移除)", text):
        return ""
    if "記憶" not in text and "記住" not in text:
        return ""
    if re.search(r"(全部|所有|所有的|全部的).{0,8}記憶", text):
        return "__all__"
    target = _extract_after_marker(
        text,
        ["忘記", "忘掉", "刪掉", "刪除", "移除"],
    )
    target = re.sub(r"(這個|這段|記憶|長期記憶|關於)", "", target)
    return _clean_text(target, max_len=120).strip(" 的。.!！?？")


def _find_existing(entries: list[dict[str, Any]], content: str) -> dict[str, Any] | None:
    target = _normalize(content)
    if not target:
        return None

    for entry in entries:
        existing = _normalize(str(entry.get("content") or ""))
        if not existing:
            continue
        if existing == target:
            return entry
        if len(target) > 16 and (target in existing or existing in target):
            return entry

    if content.startswith("使用者希望被稱呼為"):
        for entry in entries:
            if str(entry.get("content") or "").startswith("使用者希望被稱呼為"):
                return entry

    return None


def _upsert_memory(
    store: dict[str, Any],
    *,
    content: str,
    memory_type: MemoryType,
    source: str,
    history_uid: str,
    confidence: float,
    importance: float,
) -> bool:
    entries: list[dict[str, Any]] = store["entries"]
    existing = _find_existing(entries, content)
    now = _now_iso()
    if existing:
        changed = False
        for key, value in {
            "content": content,
            "memory_type": memory_type,
            "enabled": True,
            "confidence": max(float(existing.get("confidence") or 0), confidence),
            "importance": max(float(existing.get("importance") or 0), importance),
            "source_history_uid": history_uid,
            "source": source,
        }.items():
            if existing.get(key) != value:
                existing[key] = value
                changed = True
        if changed:
            existing["updated_at"] = now
        return changed

    entries.append(
        {
            "id": uuid.uuid4().hex,
            "scope": "character",
            "memory_type": memory_type,
            "content": content,
            "enabled": True,
            "confidence": confidence,
            "importance": importance,
            "source": source,
            "source_history_uid": history_uid,
            "created_at": now,
            "updated_at": now,
        }
    )
    return True


def _disable_memories(store: dict[str, Any], target: str) -> int:
    entries: list[dict[str, Any]] = store["entries"]
    now = _now_iso()
    count = 0
    if target == "__all__":
        for entry in entries:
            if entry.get("enabled", True):
                entry["enabled"] = False
                entry["updated_at"] = now
                count += 1
        return count

    normalized_target = _normalize(target)
    if not normalized_target:
        return 0
    for entry in entries:
        content = str(entry.get("content") or "")
        if normalized_target in _normalize(content) and entry.get("enabled", True):
            entry["enabled"] = False
            entry["updated_at"] = now
            count += 1
    return count


def process_character_memory_turn(
    *,
    conf_uid: str,
    history_uid: str,
    user_text: str,
    assistant_text: str = "",
) -> tuple[bool, list[str]]:
    """Conservatively extract long-term character memories from a completed turn."""
    if not conf_uid:
        return False, []

    user_text = _clean_text(user_text, max_len=1200)
    if not user_text:
        return False, []

    if _contains_sensitive_data(user_text):
        logger.info("Skipped character memory write because the user text looks sensitive.")
        return False, ["skipped-sensitive"]

    store = _load_store(conf_uid)
    notes: list[str] = []
    changed = False

    forget_target = _extract_forget_target(user_text)
    if forget_target:
        disabled = _disable_memories(store, forget_target)
        if disabled:
            changed = True
            notes.append(f"disabled:{disabled}")

    for candidate in _extract_memory_candidates(user_text):
        content = str(candidate.get("content") or "")
        if _contains_sensitive_data(content):
            continue
        if _upsert_memory(
            store,
            content=content,
            memory_type=candidate.get("memory_type", "fact"),
            source=str(candidate.get("source") or "heuristic"),
            history_uid=history_uid,
            confidence=float(candidate.get("confidence") or 0.72),
            importance=float(candidate.get("importance") or 0.68),
        ):
            changed = True
            notes.append("upsert")

    if not changed:
        return False, notes

    # Keep the first version compact so prompt injection stays predictable.
    entries = store["entries"]
    enabled_entries = [entry for entry in entries if entry.get("enabled", True)]
    if len(enabled_entries) > 80:
        enabled_entries.sort(
            key=lambda entry: (
                float(entry.get("importance") or 0),
                str(entry.get("updated_at") or ""),
            ),
            reverse=True,
        )
        keep_ids = {entry.get("id") for entry in enabled_entries[:80]}
        for entry in entries:
            if entry.get("enabled", True) and entry.get("id") not in keep_ids:
                entry["enabled"] = False
                entry["updated_at"] = _now_iso()

    _save_store(conf_uid, store)
    return True, notes


def list_character_memories(conf_uid: str, *, enabled_only: bool = True) -> list[dict[str, Any]]:
    if not conf_uid:
        return []
    store = _load_store(conf_uid)
    entries = [
        entry
        for entry in store.get("entries", [])
        if isinstance(entry, dict) and (not enabled_only or entry.get("enabled", True))
    ]
    entries.sort(
        key=lambda entry: (
            float(entry.get("importance") or 0),
            str(entry.get("updated_at") or ""),
        ),
        reverse=True,
    )
    return entries


def format_character_memories_for_prompt(conf_uid: str, *, max_entries: int = 24) -> str:
    entries = list_character_memories(conf_uid, enabled_only=True)[:max_entries]
    if not entries:
        return ""

    lines = [
        "以下是此角色與使用者之間的長期記憶。這些內容只作為背景脈絡；只有在相關時使用，不要逐字背誦，也不要主動提到記憶系統。",
    ]
    for entry in entries:
        memory_type = str(entry.get("memory_type") or "fact")
        content = _clean_text(str(entry.get("content") or ""), max_len=220)
        if content:
            lines.append(f"- ({memory_type}) {content}")
    return "\n".join(lines).strip()


def format_character_memories_for_preview(conf_uid: str, *, max_entries: int = 80) -> str:
    entries = list_character_memories(conf_uid, enabled_only=False)[:max_entries]
    if not entries:
        return "目前沒有角色長期記憶。"

    lines: list[str] = []
    for entry in entries:
        marker = "ON" if entry.get("enabled", True) else "OFF"
        memory_type = str(entry.get("memory_type") or "fact")
        content = _clean_text(str(entry.get("content") or ""), max_len=260)
        updated_at = str(entry.get("updated_at") or "")
        lines.append(f"[{marker}] ({memory_type}) {content}")
        if updated_at:
            lines.append(f"  updated: {updated_at}")
    return "\n".join(lines).strip()
