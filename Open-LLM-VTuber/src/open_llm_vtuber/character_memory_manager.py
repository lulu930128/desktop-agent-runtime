from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
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
    "project_decision",
    "project_state",
    "thread_summary",
]

MemoryScopeLevel = Literal[
    "global_user",
    "character",
    "project",
    "thread",
    "runtime",
]

MemoryStatus = Literal[
    "active",
    "superseded",
    "disabled",
    "pending_confirmation",
    "pending_delete",
]

MemoryDeleteAction = Literal[
    "none",
    "disable_all",
    "disable_scope",
    "disable_recent_turn",
    "disable_matching",
    "pending_matching",
]


@dataclass(frozen=True)
class MemoryReadPlan:
    query_text: str = ""
    scope_priority: list[MemoryScopeLevel] = field(
        default_factory=lambda: ["project", "character", "thread", "global_user"]
    )
    memory_types: list[MemoryType] = field(default_factory=list)
    max_entries: int = 12
    token_budget: int = 900
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MemoryWritePlan:
    candidates: list[dict[str, Any]] = field(default_factory=list)
    skip_write: bool = False
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MemoryDeletePlan:
    action: MemoryDeleteAction = "none"
    target_text: str = ""
    scope_level: MemoryScopeLevel | None = None
    skip_write: bool = False
    max_direct_matches: int = 8
    reasons: list[str] = field(default_factory=list)


class CharacterMemoryEntry(TypedDict, total=False):
    id: str
    scope: Literal["character"]
    scope_level: MemoryScopeLevel
    scope_id: str
    memory_type: MemoryType
    subject: str
    key: str
    content: str
    enabled: bool
    status: MemoryStatus
    confidence: float
    importance: float
    source: str
    source_history_uid: str
    evidence: dict[str, Any]
    supersedes: list[str]
    conflicts_with: list[str]
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

SOURCE_PRIORITY = {
    "explicit": 100,
    "tool_verified": 90,
    "assistant_outcome_confirmed": 82,
    "assistant_outcome": 70,
    "heuristic": 35,
    "unknown": 10,
}


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


def _estimate_tokens(content: str) -> int:
    text = content or ""
    if not text:
        return 0
    # Cheap mixed CJK/Latin estimate. Good enough for budget packing.
    return max(1, len(text) // 3)


def _keyword_terms(content: str) -> set[str]:
    text = (content or "").lower()
    terms = set(re.findall(r"[a-z0-9_./:\\-]{2,}", text))
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        terms.add(chunk)
        if len(chunk) > 2:
            terms.update(chunk[index : index + 2] for index in range(len(chunk) - 1))
    return {term for term in terms if len(term) >= 2}


def _entry_scope_level(entry: dict[str, Any]) -> MemoryScopeLevel:
    scope_level = str(entry.get("scope_level") or "").strip()
    if scope_level in {"global_user", "character", "project", "thread", "runtime"}:
        return scope_level  # type: ignore[return-value]
    if str(entry.get("scope") or "") == "character":
        return "character"
    return "character"


def _entry_status(entry: dict[str, Any]) -> MemoryStatus:
    status = str(entry.get("status") or "").strip()
    if status in {
        "active",
        "superseded",
        "disabled",
        "pending_confirmation",
        "pending_delete",
    }:
        return status  # type: ignore[return-value]
    return "active" if entry.get("enabled", True) else "disabled"


def _is_active_memory(entry: dict[str, Any]) -> bool:
    return entry.get("enabled", True) and _entry_status(entry) == "active"


def _source_priority(source: str) -> int:
    return SOURCE_PRIORITY.get(str(source or "unknown"), SOURCE_PRIORITY["unknown"])


def _infer_scope_priority(query_text: str) -> list[MemoryScopeLevel]:
    text = _normalize(query_text)
    project_terms = [
        "專案",
        "launcher",
        "工具",
        "搜尋",
        "prompt",
        "tts",
        "live2d",
        "記憶",
        "程式",
        "架構",
        "施工",
        "push",
        "commit",
    ]
    user_terms = ["偏好", "喜歡", "語氣", "叫我", "名字", "稱呼", "習慣"]

    if any(term in text for term in project_terms):
        return ["project", "thread", "character", "global_user"]
    if any(term in text for term in user_terms):
        return ["global_user", "character", "thread", "project"]
    return ["character", "project", "thread", "global_user"]


def _infer_memory_types(query_text: str) -> list[MemoryType]:
    text = _normalize(query_text)
    memory_types: list[MemoryType] = []

    def add(memory_type: MemoryType) -> None:
        if memory_type not in memory_types:
            memory_types.append(memory_type)

    if any(term in text for term in ["限制", "不要", "不能", "規則", "邊界"]):
        add("boundary")
    if any(term in text for term in ["偏好", "喜歡", "語氣", "風格", "習慣"]):
        add("preference")
    if any(term in text for term in ["叫我", "名字", "稱呼", "我是"]):
        add("identity")
    if any(term in text for term in ["專案", "架構", "施工", "完成", "push", "commit"]):
        add("project_decision")
        add("project_state")
    if any(term in text for term in ["怎麼做", "設計", "流程", "策略"]):
        add("instruction")
        add("project_decision")

    for fallback in ("instruction", "preference", "fact"):
        add(fallback)  # type: ignore[arg-type]
    return memory_types


def infer_memory_read_plan(
    query_text: str,
    *,
    max_entries: int = 12,
    token_budget: int = 900,
) -> MemoryReadPlan:
    text = _clean_text(query_text, max_len=900)
    scope_priority = _infer_scope_priority(text)
    memory_types = _infer_memory_types(text)
    reasons = ["query-aware long-term memory selection"]
    if text:
        reasons.append("current user turn is available")
    return MemoryReadPlan(
        query_text=text,
        scope_priority=scope_priority,
        memory_types=memory_types,
        max_entries=max(1, max_entries),
        token_budget=max(120, token_budget),
        reasons=reasons,
    )


def infer_memory_delete_plan(user_text: str) -> MemoryDeletePlan:
    text = _clean_text(user_text, max_len=700)
    normalized = _normalize(text)
    if not normalized:
        return MemoryDeletePlan()

    skip_write = any(
        term in normalized
        for term in [
            "不要記住這個",
            "這個不要記",
            "不用記這個",
            "不要寫入記憶",
            "不要存這個",
            "dontrememberthis",
            "donotrememberthis",
        ]
    )
    has_forget = any(
        term in normalized
        for term in [
            "忘記",
            "刪掉",
            "刪除",
            "清空",
            "移除",
            "不要再記得",
            "forget",
            "delete",
            "remove",
            "clear",
        ]
    )
    if skip_write and not has_forget:
        return MemoryDeletePlan(
            action="none",
            skip_write=True,
            reasons=["user asked not to write this turn"],
        )
    if not has_forget:
        return MemoryDeletePlan()

    if any(term in normalized for term in ["剛剛", "上一輪", "這一輪", "剛才", "lastturn"]):
        return MemoryDeletePlan(
            action="disable_recent_turn",
            skip_write=True,
            reasons=["delete memories written from the current or recent turn"],
        )

    if any(term in normalized for term in ["所有記憶", "全部記憶", "allmemory", "allmemories"]):
        return MemoryDeletePlan(
            action="disable_all",
            skip_write=True,
            reasons=["user asked to disable all memories in this store"],
        )

    if any(term in normalized for term in ["專案記憶", "projectmemory", "projectmemories"]):
        return MemoryDeletePlan(
            action="disable_scope",
            scope_level="project",
            skip_write=True,
            reasons=["user asked to disable project-scope memories"],
        )

    if any(term in normalized for term in ["角色記憶", "kuro記憶", "charactermemory"]):
        return MemoryDeletePlan(
            action="disable_scope",
            scope_level="character",
            skip_write=True,
            reasons=["user asked to disable character-scope memories"],
        )

    target = _extract_after_marker(
        text,
        [
            "忘記關於",
            "刪掉關於",
            "刪除關於",
            "移除關於",
            "忘記",
            "刪掉",
            "刪除",
            "移除",
            "forget",
            "delete",
            "remove",
        ],
    )
    target = re.sub(
        r"(的記憶|這段記憶|相關記憶|memory|memories|please|幫我|請)",
        "",
        target,
        flags=re.IGNORECASE,
    )
    target = _clean_text(target, max_len=120).strip(" ：:，。,.!?！？")
    if target:
        return MemoryDeletePlan(
            action="disable_matching",
            target_text=target,
            skip_write=True,
            reasons=["user asked to disable matching memories"],
        )

    return MemoryDeletePlan(
        action="pending_matching",
        skip_write=True,
        reasons=["delete request was ambiguous"],
    )


def _contains_sensitive_data(content: str) -> bool:
    return any(pattern.search(content or "") for pattern in SENSITIVE_PATTERNS)


def _looks_like_project_memory_turn(text: str) -> bool:
    normalized = _normalize(text)
    return any(
        term in normalized
        for term in [
            "專案",
            "架構",
            "施工",
            "工具",
            "搜尋",
            "記憶",
            "launcher",
            "prompt",
            "tts",
            "live2d",
            "push",
            "commit",
            "測試",
            "驗證",
        ]
    )


def _looks_like_completion_text(text: str) -> bool:
    normalized = _normalize(text)
    if any(term in normalized for term in ["失敗", "無法", "不能完成", "error"]):
        return False
    return any(
        term in normalized
        for term in [
            "已",
            "完成",
            "改好",
            "加上",
            "新增",
            "實作",
            "驗證",
            "測試",
            "通過",
            "push",
            "commit",
            "pushed",
        ]
    )


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


def _extract_assistant_outcome_candidates(
    user_text: str,
    assistant_text: str,
) -> list[dict[str, Any]]:
    user_text = _clean_text(user_text, max_len=800)
    assistant_text = _clean_text(assistant_text, max_len=1400)
    if not user_text or not assistant_text:
        return []
    if not _looks_like_project_memory_turn(user_text):
        return []
    if not _looks_like_completion_text(assistant_text):
        return []

    sentences = [
        _clean_text(sentence, max_len=220)
        for sentence in re.split(r"[。！？!?\n]+", assistant_text)
    ]
    candidates: list[dict[str, Any]] = []
    for sentence in sentences:
        if len(sentence) < 8 or not _looks_like_completion_text(sentence):
            continue
        content = _clean_text(f"本專案進度：{sentence}", max_len=260)
        candidates.append(
            {
                "content": content,
                "source": "assistant_outcome",
                "importance": 0.74,
                "confidence": 0.78,
                "memory_type": "project_state",
                "scope_level": "project",
                "subject": "project_progress",
                "key": _normalize(sentence)[:48],
                "evidence": {
                    "user_excerpt": _clean_text(user_text, max_len=160),
                    "assistant_excerpt": sentence,
                },
            }
        )
        if len(candidates) >= 2:
            break
    return candidates


def _dedupe_memory_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        content = _clean_text(str(candidate.get("content") or ""))
        key = _normalize(content)
        if not content or key in seen:
            continue
        seen.add(key)
        candidate["content"] = content
        deduped.append(candidate)
    return deduped


def build_memory_write_plan(
    *,
    user_text: str,
    assistant_text: str = "",
    skip_write: bool = False,
) -> MemoryWritePlan:
    if skip_write:
        return MemoryWritePlan(
            skip_write=True,
            reasons=["write skipped by delete/forget request"],
        )

    raw_candidates = _dedupe_memory_candidates(
        [
            *_extract_memory_candidates(user_text),
            *_extract_assistant_outcome_candidates(user_text, assistant_text),
        ]
    )
    candidates: list[dict[str, Any]] = []
    reasons: list[str] = []

    for candidate in raw_candidates:
        source = str(candidate.get("source") or "heuristic")
        if source == "heuristic":
            candidate["status"] = "pending_confirmation"
            candidate["confidence"] = min(float(candidate.get("confidence") or 0.62), 0.62)
            candidate["importance"] = min(float(candidate.get("importance") or 0.52), 0.52)
            reasons.append("heuristic candidate held for confirmation")
        else:
            candidate.setdefault("status", "active")
        candidates.append(candidate)

    if candidates:
        reasons.append(f"{len(candidates)} candidate memories proposed")
    return MemoryWritePlan(candidates=candidates, reasons=reasons)


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
    scope_level: MemoryScopeLevel = "character",
    subject: str = "",
    key: str = "",
    evidence: dict[str, Any] | None = None,
    status: MemoryStatus = "active",
) -> bool:
    entries: list[dict[str, Any]] = store["entries"]
    if not subject or not key:
        default_subject, default_key = _default_subject_key(
            memory_type=memory_type,
            content=content,
            scope_level=scope_level,
        )
        subject = subject or default_subject
        key = key or default_key

    existing = _find_existing(entries, content)
    now = _now_iso()
    enabled = status == "active"
    if existing:
        changed = False
        existing_source = str(existing.get("source") or "unknown")
        should_reactivate = enabled and _source_priority(source) >= _source_priority(existing_source)
        for field_name, value in {
            "content": content,
            "memory_type": memory_type,
            "enabled": should_reactivate or existing.get("enabled", True),
            "status": status if should_reactivate else _entry_status(existing),
            "scope_level": existing.get("scope_level") or scope_level,
            "scope_id": existing.get("scope_id") or str(store.get("conf_uid") or ""),
            "subject": existing.get("subject") or subject,
            "key": existing.get("key") or key,
            "confidence": max(float(existing.get("confidence") or 0), confidence),
            "importance": max(float(existing.get("importance") or 0), importance),
            "source_history_uid": history_uid,
            "source": source,
            "evidence": existing.get("evidence") or evidence or {},
        }.items():
            if existing.get(field_name) != value:
                existing[field_name] = value
                changed = True
        if changed:
            existing["updated_at"] = now
        return changed

    supersedes: list[str] = []
    conflicts_with: list[str] = []
    conflict = _find_conflicting_memory(
        entries,
        content=content,
        scope_level=scope_level,
        subject=subject,
        key=key,
    )
    if conflict:
        conflict_id = str(conflict.get("id") or "")
        existing_source = str(conflict.get("source") or "unknown")
        can_supersede = (
            status == "active"
            and _source_priority(source) >= _source_priority(existing_source)
        )
        if can_supersede:
            conflict["enabled"] = False
            conflict["status"] = "superseded"
            conflict["updated_at"] = now
            supersedes.append(conflict_id)
        else:
            status = "pending_confirmation"
            enabled = False
            conflicts_with.append(conflict_id)

    entries.append(
        {
            "id": uuid.uuid4().hex,
            "scope": "character",
            "scope_level": scope_level,
            "scope_id": str(store.get("conf_uid") or ""),
            "memory_type": memory_type,
            "subject": subject,
            "key": key,
            "content": content,
            "enabled": enabled,
            "status": status,
            "confidence": confidence,
            "importance": importance,
            "source": source,
            "source_history_uid": history_uid,
            "evidence": evidence or {},
            "supersedes": [item for item in supersedes if item],
            "conflicts_with": [item for item in conflicts_with if item],
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
                entry["status"] = "disabled"
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
            entry["status"] = "disabled"
            entry["updated_at"] = now
            count += 1
    return count


def _memory_matches_target(entry: dict[str, Any], target_text: str) -> bool:
    normalized_target = _normalize(target_text)
    if not normalized_target:
        return False
    haystack = _normalize(
        " ".join(
            [
                str(entry.get("content") or ""),
                str(entry.get("subject") or ""),
                str(entry.get("key") or ""),
                str(entry.get("memory_type") or ""),
                _format_scope_label(entry),
            ]
        )
    )
    if normalized_target in haystack:
        return True
    target_terms = _keyword_terms(target_text)
    entry_terms = _keyword_terms(haystack)
    return bool(target_terms and target_terms & entry_terms)


def _apply_memory_delete_plan(
    store: dict[str, Any],
    plan: MemoryDeletePlan,
    *,
    history_uid: str,
) -> tuple[bool, list[str]]:
    if plan.action == "none":
        return False, []

    entries = [
        entry
        for entry in store.get("entries", [])
        if isinstance(entry, dict) and _is_active_memory(entry)
    ]
    if not entries:
        return False, []

    if plan.action == "disable_all":
        matches = entries
        final_status: MemoryStatus = "disabled"
    elif plan.action == "disable_scope" and plan.scope_level:
        matches = [entry for entry in entries if _entry_scope_level(entry) == plan.scope_level]
        final_status = "disabled"
    elif plan.action == "disable_recent_turn":
        matches = [
            entry
            for entry in entries
            if str(entry.get("source_history_uid") or "") == str(history_uid or "")
        ]
        final_status = "disabled"
    elif plan.action == "disable_matching":
        matches = [
            entry for entry in entries if _memory_matches_target(entry, plan.target_text)
        ]
        final_status = (
            "pending_delete"
            if len(matches) > plan.max_direct_matches
            else "disabled"
        )
    elif plan.action == "pending_matching":
        return False, ["delete-pending:ambiguous"]
    else:
        return False, []

    if not matches:
        return False, ["delete-miss"]

    now = _now_iso()
    for entry in matches:
        entry["enabled"] = False
        entry["status"] = final_status
        entry["updated_at"] = now

    note_prefix = "pending-delete" if final_status == "pending_delete" else "disabled"
    return True, [f"{note_prefix}:{len(matches)}"]


def _merge_entry(existing: dict[str, Any], incoming: dict[str, Any]) -> bool:
    changed = False
    existing_enabled = bool(existing.get("enabled", True))
    incoming_enabled = bool(incoming.get("enabled", True))
    existing_importance = float(existing.get("importance") or 0)
    incoming_importance = float(incoming.get("importance") or 0)
    existing_updated = str(existing.get("updated_at") or "")
    incoming_updated = str(incoming.get("updated_at") or "")

    prefer_incoming_content = (
        incoming_enabled and not existing_enabled
        or incoming_importance > existing_importance
        or (
            incoming_importance == existing_importance
            and incoming_updated > existing_updated
            and len(str(incoming.get("content") or ""))
            >= len(str(existing.get("content") or ""))
        )
    )

    if prefer_incoming_content:
        for key in ("content", "memory_type", "source", "source_history_uid"):
            value = incoming.get(key)
            if value and existing.get(key) != value:
                existing[key] = value
                changed = True

    merged_values = {
        "enabled": existing_enabled or incoming_enabled,
        "confidence": max(
            float(existing.get("confidence") or 0),
            float(incoming.get("confidence") or 0),
        ),
        "importance": max(existing_importance, incoming_importance),
        "updated_at": max(existing_updated, incoming_updated) or _now_iso(),
    }
    for key, value in merged_values.items():
        if existing.get(key) != value:
            existing[key] = value
            changed = True
    return changed


def _compact_store(store: dict[str, Any]) -> bool:
    raw_entries = store.get("entries", [])
    if not isinstance(raw_entries, list):
        store["entries"] = []
        return True

    changed = False
    merged_entries: list[dict[str, Any]] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            changed = True
            continue
        content = _clean_text(str(raw_entry.get("content") or ""), max_len=260)
        if not content:
            changed = True
            continue

        entry = dict(raw_entry)
        if entry.get("content") != content:
            entry["content"] = content
            changed = True
        entry.setdefault("id", uuid.uuid4().hex)
        entry.setdefault("scope", "character")
        entry.setdefault("scope_level", _entry_scope_level(entry))
        entry.setdefault("scope_id", str(store.get("conf_uid") or ""))
        entry.setdefault("memory_type", _classify_memory_type(content))
        entry.setdefault("enabled", True)
        entry.setdefault("status", "active" if entry.get("enabled", True) else "disabled")
        if not entry.get("subject") or not entry.get("key"):
            subject, key = _default_subject_key(
                memory_type=entry.get("memory_type", "fact"),
                content=content,
                scope_level=_entry_scope_level(entry),
            )
            if not entry.get("subject"):
                entry["subject"] = subject
            if not entry.get("key"):
                entry["key"] = key
        entry.setdefault("confidence", 0.7)
        entry.setdefault("importance", 0.6)
        entry.setdefault("source", "unknown")
        entry.setdefault("source_history_uid", "")
        entry.setdefault("evidence", {})
        entry.setdefault("supersedes", [])
        entry.setdefault("conflicts_with", [])
        entry.setdefault("created_at", _now_iso())
        entry.setdefault("updated_at", entry.get("created_at") or _now_iso())

        existing = _find_existing(merged_entries, content)
        if existing:
            if _merge_entry(existing, entry):
                changed = True
            changed = True
            continue
        merged_entries.append(entry)

    enabled_entries = [entry for entry in merged_entries if _is_active_memory(entry)]
    if len(enabled_entries) > 80:
        enabled_entries.sort(
            key=lambda entry: (
                float(entry.get("importance") or 0),
                str(entry.get("updated_at") or ""),
            ),
            reverse=True,
        )
        keep_ids = {entry.get("id") for entry in enabled_entries[:80]}
        for entry in merged_entries:
            if _is_active_memory(entry) and entry.get("id") not in keep_ids:
                entry["enabled"] = False
                entry["status"] = "disabled"
                entry["updated_at"] = _now_iso()
                changed = True

    merged_entries.sort(
        key=lambda entry: (
            _is_active_memory(entry),
            float(entry.get("importance") or 0),
            str(entry.get("updated_at") or ""),
        ),
        reverse=True,
    )

    if merged_entries != raw_entries:
        store["entries"] = merged_entries
        changed = True
    return changed


def compact_character_memories(conf_uid: str) -> tuple[bool, int]:
    if not conf_uid:
        return False, 0
    store = _load_store(conf_uid)
    before_count = len(store.get("entries", [])) if isinstance(store.get("entries"), list) else 0
    changed = _compact_store(store)
    after_count = len(store.get("entries", [])) if isinstance(store.get("entries"), list) else 0
    if changed:
        _save_store(conf_uid, store)
    return changed, max(0, before_count - after_count)


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

    assistant_text = _clean_text(assistant_text, max_len=1600)

    if _contains_sensitive_data(user_text) or _contains_sensitive_data(assistant_text):
        logger.info("Skipped character memory write because the turn looks sensitive.")
        return False, ["skipped-sensitive"]

    store = _load_store(conf_uid)
    notes: list[str] = []
    changed = False

    delete_plan = infer_memory_delete_plan(user_text)
    delete_changed, delete_notes = _apply_memory_delete_plan(
        store,
        delete_plan,
        history_uid=history_uid,
    )
    if delete_changed:
        changed = True
    notes.extend(delete_notes)

    write_plan = build_memory_write_plan(
        user_text=user_text,
        assistant_text=assistant_text,
        skip_write=delete_plan.skip_write,
    )
    if write_plan.skip_write:
        notes.append("write-skipped")

    for candidate in write_plan.candidates:
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
            scope_level=candidate.get("scope_level", "character"),
            subject=str(candidate.get("subject") or ""),
            key=str(candidate.get("key") or ""),
            evidence=candidate.get("evidence") or {},
            status=candidate.get("status", "active"),
        ):
            changed = True
            note_action = (
                "pending"
                if candidate.get("status") == "pending_confirmation"
                else "upsert"
            )
            notes.append(f"{note_action}:{candidate.get('source') or 'heuristic'}")

    if not changed:
        return False, notes

    _compact_store(store)
    _save_store(conf_uid, store)
    return True, notes


def _scope_priority_score(
    scope_level: MemoryScopeLevel,
    priority: list[MemoryScopeLevel],
) -> int:
    try:
        return max(0, 20 - priority.index(scope_level) * 4)
    except ValueError:
        return 0


def _score_memory_for_plan(entry: dict[str, Any], plan: MemoryReadPlan) -> float:
    content = str(entry.get("content") or "")
    memory_type = str(entry.get("memory_type") or "fact")
    score = float(entry.get("importance") or 0.0) * 45
    score += float(entry.get("confidence") or 0.0) * 15
    score += _scope_priority_score(_entry_scope_level(entry), plan.scope_priority)

    if memory_type in plan.memory_types:
        score += max(4, 18 - plan.memory_types.index(memory_type) * 2)

    query_terms = _keyword_terms(plan.query_text)
    entry_terms = _keyword_terms(
        " ".join(
            [
                content,
                str(entry.get("subject") or ""),
                str(entry.get("key") or ""),
                memory_type,
            ]
        )
    )
    overlap = query_terms & entry_terms
    if overlap:
        score += min(len(overlap), 10) * 7

    normalized_query = _normalize(plan.query_text)
    normalized_content = _normalize(content)
    if normalized_query and normalized_content:
        if normalized_query in normalized_content or normalized_content in normalized_query:
            score += 16

    updated_at = str(entry.get("updated_at") or "")
    if updated_at:
        score += 2
    return score


def _pack_memory_entries(
    entries: list[dict[str, Any]],
    *,
    max_entries: int,
    token_budget: int | None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used_tokens = 0
    for entry in entries:
        if len(selected) >= max_entries:
            break
        content = _clean_text(str(entry.get("content") or ""), max_len=220)
        if not content:
            continue
        entry_tokens = _estimate_tokens(content) + 8
        if token_budget is not None and selected and used_tokens + entry_tokens > token_budget:
            continue
        selected.append(entry)
        used_tokens += entry_tokens
        if token_budget is not None and used_tokens >= token_budget:
            break
    return selected


def _format_scope_label(entry: dict[str, Any]) -> str:
    scope_level = _entry_scope_level(entry)
    scope_id = str(entry.get("scope_id") or "").strip()
    return f"{scope_level}:{scope_id}" if scope_id else scope_level


def _default_subject_key(
    *,
    memory_type: MemoryType,
    content: str,
    scope_level: MemoryScopeLevel,
) -> tuple[str, str]:
    normalized = _normalize(content)
    if scope_level == "project":
        if any(term in normalized for term in ["工具", "tool", "搜尋", "search"]):
            return "tooling", "tool_planner"
        if any(term in normalized for term in ["launcher", "控制版面"]):
            return "launcher", "state"
        if any(term in normalized for term in ["記憶", "memory"]):
            return "memory_system", "state"
        return "project_progress", normalized[:48]

    if memory_type == "identity":
        if any(term in normalized for term in ["稱呼", "叫我", "名字"]):
            return "user_identity", "preferred_name"
        return "user_identity", normalized[:48]
    if memory_type == "preference":
        if any(term in normalized for term in ["語氣", "回覆", "中文", "日文"]):
            return "user_preference", "reply_style"
        return "user_preference", normalized[:48]
    if memory_type == "boundary":
        return "user_boundary", normalized[:48]
    if memory_type == "instruction":
        return "user_instruction", normalized[:48]
    return "user_fact", normalized[:48]


def _find_conflicting_memory(
    entries: list[dict[str, Any]],
    *,
    content: str,
    scope_level: MemoryScopeLevel,
    subject: str,
    key: str,
) -> dict[str, Any] | None:
    if not subject or not key:
        return None

    target = _normalize(content)
    for entry in entries:
        if not _is_active_memory(entry):
            continue
        if _entry_scope_level(entry) != scope_level:
            continue
        if str(entry.get("subject") or "") != subject:
            continue
        if str(entry.get("key") or "") != key:
            continue
        existing = _normalize(str(entry.get("content") or ""))
        if existing and existing != target:
            return entry
    return None


def list_character_memories(
    conf_uid: str,
    *,
    enabled_only: bool = True,
    query_text: str = "",
    read_plan: MemoryReadPlan | None = None,
    max_entries: int | None = None,
    token_budget: int | None = None,
) -> list[dict[str, Any]]:
    if not conf_uid:
        return []
    store = _load_store(conf_uid)
    entries = [
        entry
        for entry in store.get("entries", [])
        if isinstance(entry, dict) and (not enabled_only or _is_active_memory(entry))
    ]

    plan = read_plan
    if plan is None and query_text:
        plan = infer_memory_read_plan(query_text, max_entries=max_entries or 12)

    if plan:
        entries.sort(
            key=lambda entry: (
                _score_memory_for_plan(entry, plan),
                str(entry.get("updated_at") or ""),
            ),
            reverse=True,
        )
        max_count = max_entries or plan.max_entries
        budget = token_budget if token_budget is not None else plan.token_budget
    else:
        entries.sort(
            key=lambda entry: (
                float(entry.get("importance") or 0),
                str(entry.get("updated_at") or ""),
            ),
            reverse=True,
        )
        max_count = max_entries or len(entries)
        budget = token_budget

    entries = _pack_memory_entries(
        entries,
        max_entries=max(0, max_count),
        token_budget=budget,
    )
    return entries


def format_character_memories_for_prompt(
    conf_uid: str,
    *,
    max_entries: int = 24,
    query_text: str = "",
    token_budget: int | None = None,
    read_plan: MemoryReadPlan | None = None,
) -> str:
    if max_entries <= 0:
        return ""

    plan = read_plan
    if plan is None and query_text:
        plan = infer_memory_read_plan(
            query_text,
            max_entries=max_entries,
            token_budget=token_budget or 900,
        )

    entries = list_character_memories(
        conf_uid,
        enabled_only=True,
        query_text=query_text,
        read_plan=plan,
        max_entries=max_entries,
        token_budget=token_budget,
    )
    if not entries:
        return ""

    heading = (
        "以下是與本輪使用者問題最相關的長期記憶。只在有幫助時使用，不要逐字背誦，也不要主動提到記憶系統。"
        if query_text or plan
        else "以下是此角色與使用者之間的長期記憶。這些內容只作為背景脈絡；只有在相關時使用，不要逐字背誦，也不要主動提到記憶系統。"
    )
    lines = [
        heading,
    ]
    if plan:
        lines.append(
            f"Memory read plan: scopes={', '.join(plan.scope_priority)}; "
            f"types={', '.join(plan.memory_types[:5])}; budget={plan.token_budget}"
        )
    for entry in entries:
        memory_type = str(entry.get("memory_type") or "fact")
        content = _clean_text(str(entry.get("content") or ""), max_len=220)
        if content:
            scope_label = _format_scope_label(entry)
            lines.append(f"- [{scope_label}] ({memory_type}) {content}")
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
