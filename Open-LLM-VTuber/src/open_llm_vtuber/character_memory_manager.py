from __future__ import annotations

import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypedDict

from loguru import logger

from .character_memory_repository import CharacterMemoryRepository, memory_namespaces, store_lock
from .memory_formation import read_policy, semantic_spans
from .character_memory_retriever import CharacterMemoryRetriever, MemorySearchHit, query_cutoff, query_terms, suppressed_turn_ids
from .character_memory_sql_index import SQLiteMemoryIndex
from .mcpp.privacy import safe_text
from .character_memory_lifecycle import (
    authorize, has_save_authorization, review_digest, entry_status as lifecycle_status,
    is_active_memory as lifecycle_active,
)


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
    "manual": 105,
    "user_statement": 75,
    "explicit": 100,
    "tool_verified": 90,
    "assistant_outcome_confirmed": 82,
    "assistant_outcome": 70,
    "heuristic": 35,
    "unknown": 10,
}

_MEMORY_REPOSITORY = CharacterMemoryRepository()
_MEMORY_INDEX = SQLiteMemoryIndex(repository=_MEMORY_REPOSITORY)
_MEMORY_RETRIEVER = CharacterMemoryRetriever(index=_MEMORY_INDEX)


def _at_or_after(observed: str, previous: str) -> bool:
    try:
        when = datetime.fromisoformat(observed)
        before = datetime.fromisoformat(previous)
        return when.tzinfo is not None and before.tzinfo is not None and when >= before
    except (TypeError, ValueError):
        return False


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def _memory_root() -> Path:
    return _MEMORY_REPOSITORY.root()


def _safe_path_component(value: str) -> str:
    return _MEMORY_REPOSITORY.safe_path_component(value)


def _store_path(conf_uid: str) -> Path:
    return _MEMORY_REPOSITORY.store_path(conf_uid)


def _empty_store(conf_uid: str) -> dict[str, Any]:
    return _MEMORY_REPOSITORY.empty_store(conf_uid)


def _load_store(conf_uid: str) -> dict[str, Any]:
    return _MEMORY_REPOSITORY.load(conf_uid)


def _save_store(conf_uid: str, data: dict[str, Any]) -> None:
    _MEMORY_REPOSITORY.save(conf_uid, data)
    # The index is derived; synchronize deletes and disables, including the last row.
    try:
        _MEMORY_INDEX.refresh(conf_uid)
    except Exception:
        logger.warning("Memory index refresh deferred; retrieval will retry from canonical data.")


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
    return lifecycle_status(entry)  # type: ignore[return-value]


def _is_active_memory(entry: dict[str, Any]) -> bool:
    return lifecycle_active(entry)


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

    if re.search(r"(さっき|前の話|直前|前のターン).*(忘れて|覚えないで)",text):
        return MemoryDeletePlan(action="disable_recent_turn",skip_write=True,reasons=["previous user turn"])
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
    if has_forget and not re.match(
            r"^(?:請|幫我|請幫我|麻煩|please\s+)?(?:忘記|刪掉|刪除|清空|移除|不要再記得|forget\b|delete\b|remove\b|clear\b)",
            text, re.I):
        return MemoryDeletePlan()
    if not has_forget:
        return MemoryDeletePlan()

    if any(term in normalized for term in ["剛剛", "上一輪", "這一輪", "剛才", "lastturn","previousturn","whatijustsaid"]):
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
    return safe_text(content or "") != (content or "") or any(pattern.search(content or "") for pattern in SENSITIVE_PATTERNS)


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
        if source != "explicit":
            candidate["status"] = "pending_confirmation"
            candidate["enabled"] = False
            candidate.setdefault("evidence", {})["verification_status"] = "unverified"
            candidate["confidence"] = min(float(candidate.get("confidence") or 0.62), 0.62)
            candidate["importance"] = min(float(candidate.get("importance") or 0.52), 0.52)
            reasons.append(f"{source} candidate held for confirmation")
        else:
            candidate.setdefault("status", "active")
        candidates.append(candidate)

    if candidates:
        reasons.append(f"{len(candidates)} candidate memories proposed")
    return MemoryWritePlan(candidates=candidates, reasons=reasons)


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
    scope_id: str = "",
    auto_rule: dict | None = None,
) -> bool:
    entries: list[dict[str, Any]] = store["entries"]
    automatic = source == "user_statement" and auto_rule is not None
    if source not in {"manual", "explicit"} and not automatic:
        status = "pending_confirmation"
    if not subject or not key:
        default_subject, default_key = _default_subject_key(
            memory_type=memory_type,
            content=content,
            scope_level=scope_level,
        )
        subject = subject or default_subject
        key = key or default_key

    scope_id = scope_id or str(store.get("conf_uid") or "")
    existing = _find_existing([e for e in entries if _entry_scope_level(e) == scope_level
                               and e.get("scope_id") == scope_id
                               and (subject != "experience" or e.get("key") == key)], content)
    now = _now_iso()
    enabled = status == "active"
    if existing:
        if evidence and evidence.get("turn_id") and (existing.get("evidence") or {}).get("turn_id") == evidence["turn_id"]:
            return False
        # Repeated claims are no authority to edit a prior decision or provenance.
        # Retain the existing record byte-for-byte; its ID remains the reference.
        if _is_active_memory(existing) and existing.get("source") == source:
            return False
        if source not in {"manual", "explicit"} or _source_priority(source) < _source_priority(str(existing.get("source"))):
            return False
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
            if status == "active":
                existing["evidence"] = evidence or {}
                authorize(existing, source, history_uid)
        return changed

    supersedes: list[str] = []
    conflicts_with: list[str] = []
    conflict = _find_conflicting_memory(
        [e for e in entries if e.get("scope_id") == scope_id],
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
            and (not automatic or _at_or_after((evidence or {}).get("observed_at",""), conflict.get("valid_from","")))
        )
        if can_supersede:
            conflict["enabled"] = False
            conflict["status"] = "superseded"
            conflict["valid_to"] = (evidence or {}).get("observed_at") or now
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
            "scope_id": scope_id,
            "valid_from": (evidence or {}).get("observed_at") or now,
            "revision": int(conflict.get("revision",1)) + 1 if conflict and supersedes else 1,
            "last_confirmed_at": now if enabled and source in {"manual","explicit"} else None,
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
    if status == "active" and source in {"manual", "explicit"}:
        authorize(entries[-1], source, history_uid)
    elif status == "active" and automatic:
        authorize(entries[-1], "scoped_auto", evidence["rule_digest"])
        entries[-1]["save_authorization"].update(version=2, source_digest=review_digest(evidence))
    return True


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
    return False


def _suppress(store, entry):
    evidence = entry.get("evidence") or {}
    ref = [evidence.get("character_id"), entry.get("source_history_uid"), evidence.get("turn_id")]
    if all(ref) and ref not in store.setdefault("suppressed_spans", []):
        store["suppressed_spans"].append(ref)


def _in_conversation_scope(entry, namespace, project_id, history_uid):
    level = _entry_scope_level(entry)
    scope = entry.get("scope_id")
    if level == "project":
        # Older role-local stores reused the character ID for an unknown project.
        return bool(project_id and scope == project_id and scope != namespace)
    if level == "thread":
        return bool(history_uid and scope == history_uid)
    return True


def _apply_memory_delete_plan(
    store: dict[str, Any],
    plan: MemoryDeletePlan,
    *,
    history_uid: str,
    previous_turn_id: str = "",
    character_id: str = "",
    project_id: str = "",
) -> tuple[bool, list[str]]:
    if plan.action == "none":
        return False, []

    entries = [
        entry
        for entry in store.get("entries", [])
        if isinstance(entry, dict) and _in_conversation_scope(entry, store.get("conf_uid"), project_id, history_uid)
        and _entry_status(entry) in {"active","pending_confirmation","superseded","pending_delete"}
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
            if previous_turn_id
            and (entry.get("evidence") or {}).get("turn_id") == previous_turn_id
            and (entry.get("evidence") or {}).get("character_id") == character_id
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
        _suppress(store, entry)
        entry["enabled"] = False
        entry["status"] = final_status
        entry["updated_at"] = now

    note_prefix = "pending-delete" if final_status == "pending_delete" else "disabled"
    return True, [f"{note_prefix}:{len(matches)}"]


def _compact_store(store: dict[str, Any]) -> bool:
    raw_entries = store.get("entries", [])
    if not isinstance(raw_entries, list):
        raise ValueError("Invalid memory entries; compact refused")

    changed = False
    merged_entries: list[dict[str, Any]] = []
    seen_ids: dict[str, dict] = {}
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise ValueError("Invalid memory record; compact refused")
        content = raw_entry.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Invalid memory content; compact refused")

        entry = dict(raw_entry)
        entry.setdefault("id", uuid.uuid4().hex)
        entry.setdefault("scope", "character")
        entry.setdefault("scope_level", _entry_scope_level(entry))
        entry.setdefault("scope_id", str(store.get("conf_uid") or ""))
        entry.setdefault("memory_type", _classify_memory_type(content))
        entry.setdefault("enabled", True)
        entry.setdefault("status", _entry_status(entry))
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

        existing = seen_ids.get(entry["id"])
        if existing == entry:
            changed = True
            continue
        if existing is not None:
            raise ValueError("Conflicting duplicate memory ID; compact refused")
        seen_ids[entry["id"]] = entry
        merged_entries.append(entry)

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


def compact_character_memories(conf_uid: str, *, expected_digests: dict[str, str] | None = None,
                               project_id: str = "") -> tuple[bool, int]:
    if not conf_uid:
        return False, 0
    stores = [(ns,_load_store(ns)) for ns in memory_namespaces(conf_uid,project_id)]
    if expected_digests is not None:
        actual = {entry["id"]:review_digest(entry) for _,store in stores for entry in store["entries"]}
        if actual != expected_digests:
            raise ValueError("Memory changed since review; reload before confirming.")
    removed = 0
    changed = False
    for namespace, store in stores:
        before = len(store["entries"])
        if _compact_store(store):
            _save_store(namespace,store)
            changed = True
            removed += before-len(store["entries"])
    return changed,removed


def add_character_memory(
    conf_uid: str,
    content: str,
    *,
    memory_type: MemoryType | None = None,
    scope_level: MemoryScopeLevel = "character",
    project_id: str = "", history_uid: str = "",
    source: str = "manual",
    confidence: float = 0.95,
    importance: float = 0.75,
    status: MemoryStatus = "active",
    evidence: dict[str, Any] | None = None,
) -> bool:
    """Add or update one long-term memory through the canonical store path."""
    if not conf_uid:
        return False
    content = _clean_text(content, max_len=260)
    if not content or _contains_sensitive_data(content):
        return False

    namespaces = memory_namespaces(conf_uid, project_id)
    namespace = namespaces[1] if scope_level == "global_user" else namespaces[-1] if scope_level == "project" and project_id else conf_uid
    store = _load_store(namespace)
    changed = _upsert_memory(
        store,
        content=content,
        memory_type=memory_type or _classify_memory_type(content),
        source=source,
        history_uid=history_uid, scope_id={"global_user":"local-user","project":project_id,"thread":history_uid}.get(scope_level,conf_uid),
        confidence=confidence,
        importance=importance,
        scope_level=scope_level,
        evidence=evidence or {"source": "launcher"},
        status=status,
    )
    if not changed:
        return False

    _save_store(namespace, store)
    return True


def _record_store(character, project, identity):
    for namespace in memory_namespaces(character, project):
        store = _load_store(namespace)
        if any(entry.get("id") == identity for entry in store["entries"]):
            return namespace, store
    return character, _load_store(character)


def revise_character_memory(character, project, identity, content, *, expected_digest):
    """User-reviewed replacement with one canonical atomic publication."""
    if not isinstance(content,str) or not content.strip() or len(content.strip())>260 or _contains_sensitive_data(content):
        raise ValueError("Invalid memory revision")
    namespace,store=_record_store(character,project,identity)
    old=next((e for e in store["entries"] if e.get("id")==identity),None)
    if old is None or review_digest(old)!=expected_digest or not _is_active_memory(old):
        raise ValueError("Reviewed memory revision is no longer current")
    content=content.strip()
    if old["content"]==content:
        return False
    now=_now_iso()
    current=dict(old,id=uuid.uuid4().hex,content=content,source="manual",revision=old.get("revision",1)+1,
                 status="active",enabled=True,created_at=now,updated_at=now,valid_from=now,valid_to=None,
                 last_confirmed_at=now,supersedes=[identity],conflicts_with=[],source_history_uid="",
                 evidence={"source":"launcher","revises":identity,"reviewed_digest":expected_digest})
    authorize(current,"user_confirmation",expected_digest)
    old.update(enabled=False,status="superseded",valid_to=now,updated_at=now)
    store["entries"].append(current)
    _save_store(namespace,store)
    return True


def update_character_memory_status(
    conf_uid: str,
    entry_id: str,
    status: MemoryStatus,
    *,
    expected_digest: str | None = None, project_id: str = "",
) -> bool:
    """Update lifecycle status for a memory entry.

    Only active entries are enabled for prompt retrieval; all other lifecycle states
    stay visible in the store but are excluded from prompts.
    """
    if not conf_uid or not entry_id:
        return False
    if status not in {
        "active",
        "superseded",
        "disabled",
        "pending_confirmation",
        "pending_delete",
    }:
        return False

    conf_uid, store = _record_store(conf_uid, project_id, entry_id)
    entries = store.get("entries")
    if not isinstance(entries, list):
        return False

    now = _now_iso()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("id") or "") != entry_id:
            continue
        if expected_digest is not None and expected_digest != review_digest(entry):
            raise ValueError("Memory changed since review; reload before confirming.")
        enabled = status == "active"
        changed = (
            entry.get("status") != status
            or bool(entry.get("enabled", True)) != enabled
            or (status == "active" and not lifecycle_active(entry))
        )
        entry["status"] = status
        if not enabled:
            _suppress(store, entry)
        entry["enabled"] = enabled
        entry["updated_at"] = now
        if status == "active":
            authorize(entry, "user_confirmation", entry_id)
        if changed:
            _save_store(conf_uid, store)
        return changed
    return False


def delete_character_memory(conf_uid: str, entry_id: str, *, expected_digest: str | None = None, project_id: str = "") -> bool:
    """Permanently remove one memory entry from the canonical store."""
    if not conf_uid or not entry_id:
        return False

    conf_uid, store = _record_store(conf_uid, project_id, entry_id)
    entries = store.get("entries")
    if not isinstance(entries, list):
        return False

    if expected_digest is not None:
        target = next((entry for entry in entries if isinstance(entry, dict)
                       and str(entry.get("id") or "") == entry_id), None)
        if target is None or review_digest(target) != expected_digest:
            raise ValueError("Memory changed since review; reload before confirming.")

    next_entries = [
        entry
        for entry in entries
        if not (
            isinstance(entry, dict)
            and str(entry.get("id") or "") == entry_id
        )
    ]
    if len(next_entries) == len(entries):
        return False

    for entry in entries:
        if entry.get("id") == entry_id:
            _suppress(store, entry)
    store["entries"] = next_entries
    _save_store(conf_uid, store)
    return True


def process_character_memory_turn(
    *,
    conf_uid: str,
    history_uid: str,
    user_text: str,
    assistant_text: str = "",
    turn_id: str = "", previous_turn_id: str = "",
    observed_at: str = "", project_id: str = "",
    backfill: bool = False, policy_digest: str | None = None,
) -> tuple[bool, list[str]]:
    """Conservatively extract long-term character memories from a completed turn."""
    if not conf_uid:
        return False, []

    if not user_text.strip():
        return False, []
    if _contains_sensitive_data(user_text) or _contains_sensitive_data(assistant_text):
        return False, ["skipped-sensitive"]
    original_text = user_text.strip()
    user_text = _clean_text(user_text, max_len=1200)
    assistant_text = _clean_text(assistant_text, max_len=1600)

    notes = []
    observed_at = observed_at or _now_iso()
    namespaces = memory_namespaces(conf_uid, project_id)
    delete_plan = infer_memory_delete_plan(user_text)
    if delete_plan.skip_write:
        if backfill:
            return False, ["excluded:historical-command"]
        changed = False
        for namespace in namespaces:
            store = _load_store(namespace)
            modified, actions = _apply_memory_delete_plan(store, delete_plan, history_uid=history_uid,
                                                         character_id=conf_uid, previous_turn_id=previous_turn_id, project_id=project_id)
            if namespace == conf_uid:
                for identity in (turn_id, previous_turn_id if delete_plan.action == "disable_recent_turn" else ""):
                    if identity:
                        ref = [conf_uid, history_uid, identity]
                        if ref not in store.setdefault("suppressed_spans", []):
                            store["suppressed_spans"].append(ref)
                            modified = True
            if modified:
                _save_store(namespace, store)
                changed = True
            notes.extend(actions)
        return changed, notes + ["write-skipped"]

    write_plan = build_memory_write_plan(
        user_text=user_text,
        assistant_text=assistant_text,
        skip_write=delete_plan.skip_write,
    )
    if write_plan.skip_write:
        notes.append("write-skipped")

    rule = read_policy(_MEMORY_REPOSITORY, conf_uid, project_id)
    if policy_digest is not None and (review_digest(rule) if rule else "") != policy_digest:
        if backfill:
            raise ValueError("formation_policy_changed")
        rule = None
    semantic = semantic_spans(original_text, rule, history=history_uid, turn=turn_id, observed=observed_at)
    def persist(rule):
        candidates = list(write_plan.candidates)
        if turn_id and turn_id in suppressed_turn_ids(suppressed_sources(conf_uid, project_id)):
            return False, ["excluded:suppressed"]
        if semantic and not any(c.get("source") == "explicit" for c in candidates):
            candidates = [c for c in candidates if c["source"] != "heuristic"] + semantic
        if backfill:
            candidates = [c for c in candidates if any(c is formed for formed in semantic)]
        changed = False
        for candidate in candidates:
            content = str(candidate.get("content") or "")
            if _contains_sensitive_data(content):
                continue
            level = candidate.get("scope_level", "character")
            if candidate.get("source") == "explicit" and candidate.get("memory_type") in {"identity","preference"}:
                level = "global_user"
            namespace = namespaces[1] if level == "global_user" else namespaces[-1] if level == "project" and project_id else conf_uid
            scope_id = {"global_user":"local-user","project":project_id,"thread":history_uid}.get(level,conf_uid)
            store = _load_store(namespace)
            if turn_id and [conf_uid,history_uid,turn_id] in store.get("suppressed_spans", []):
                continue
            evidence = dict(candidate.get("evidence") or {}, character_id=conf_uid, turn_id=turn_id,
                            observed_at=observed_at, project_id=project_id)
            if _upsert_memory(
                store,
                content=content,
                memory_type=candidate.get("memory_type", "fact"),
                source=str(candidate.get("source") or "heuristic"),
                history_uid=history_uid,
                confidence=float(candidate.get("confidence") or 0.72),
                importance=float(candidate.get("importance") or 0.68),
                scope_level=level, scope_id=scope_id, auto_rule=rule if any(candidate is formed for formed in semantic) else None,
                subject=str(candidate.get("subject") or ""),
                key=str(candidate.get("key") or ""),
                evidence=evidence,
                status=candidate.get("status", "active"),
            ):
                _save_store(namespace, store)
                changed = True
                note_action = (
                    "pending"
                    if candidate.get("status") == "pending_confirmation"
                    else "upsert"
                )
                notes.append(f"{note_action}:{candidate.get('source') or 'heuristic'}")

        return changed, notes

    if rule and semantic:
        # Revocation and authorization share the policy file lock. Classification
        # can run outside it; only the exact reviewed grant may authorize a write.
        policy_path = _MEMORY_REPOSITORY.root() / "formation-policy.json"
        with store_lock(policy_path,wait=True):
            current = read_policy(_MEMORY_REPOSITORY,conf_uid,project_id)
            if current != rule:
                if backfill:
                    raise ValueError("formation_policy_changed")
                for candidate in semantic:
                    candidate.update(scope_level="character",status="pending_confirmation")
                rule = None
            return persist(rule)
    return persist(rule)


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
        return "project", normalized
    if memory_type == "identity":
        if any(term in normalized for term in ["稱呼", "叫我", "名字"]):
            return "user_identity", "preferred_name"
        return "user_identity", normalized[:48]
    if memory_type == "preference":
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


def formation_policy_digest(character_id, project_id):
    rule = read_policy(_MEMORY_REPOSITORY, character_id, project_id)
    return review_digest(rule) if rule else ""


def finish_pending_turns(character, history, current_turn, live_input):
    """Resume persisted live turns under their original grant. Use L0 on recovery."""
    import json
    from .chat_history_manager import _get_safe_history_path, get_history, read_memory_source
    pending = Path(_get_safe_history_path(character,history)).parent / ".formation-pending"
    changed, notes = False, []
    history_cache = {}
    markers = []
    for marker in pending.glob("*.json"):
        try:
            markers.append((marker.stat().st_mtime_ns,marker))
        except FileNotFoundError:
            continue  # A concurrent worker finished it.
    for _,marker in sorted(markers):
        try:
            with store_lock(pending / "worker"):
                if not marker.is_file():
                    continue
                job = json.loads(marker.read_bytes())
                turn, uid = job["turn"], job["history"]
                if turn == current_turn and uid == history:
                    data = live_input
                else:
                    source = Path(_get_safe_history_path(character,uid))
                    if not source.is_file():
                        relocated = read_memory_source(Path.cwd(),character,uid,turn)
                        if relocated is None:
                            notes.append("formation-source-unavailable")
                            continue
                        uid = relocated["history"]
                        source = Path(_get_safe_history_path(character,uid))
                    stat=source.stat()
                    revision=(stat.st_ino,stat.st_size,stat.st_mtime_ns)
                    if history_cache.get(uid,(None,))[0] != revision:
                        rows=get_history(character,uid,strict=True)
                        turns={}
                        previous=""
                        for i,user in enumerate(rows):
                            if user.get("role")!="human":
                                continue
                            identity=user.get("turn_id","")
                            reply=rows[i+1] if i+1<len(rows) else {}
                            if identity and reply.get("turn_id")==identity and reply.get("completion")=="complete":
                                turns[identity]=dict(user_text=user["content"],assistant_text=reply["content"],
                                    previous_turn_id=previous,project_id=user.get("project_id",""),observed_at=user["timestamp"])
                            previous=identity
                        history_cache[uid]=(revision,turns)
                    data=history_cache[uid][1].get(turn)
                    if data is None:
                        notes.append("formation-incomplete")
                        continue
                modified, actions = process_character_memory_turn(conf_uid=character,history_uid=uid,turn_id=turn,
                                                                 policy_digest=job["policy_digest"],**data)
                changed |= modified
                notes.extend(actions)
                marker.unlink()
        except (OSError,ValueError,KeyError,TypeError,sqlite3.Error) as exc:
            logger.warning("Memory formation pending ({})", type(exc).__name__)
            notes.append("formation-deferred")
    return changed,notes


def suppressed_sources(character_id, project_id="", history_uid=""):
    if not character_id:
        return set()
    namespaces = memory_namespaces(character_id, project_id)
    try:
        return _MEMORY_INDEX.suppressed(namespaces, character_id, history_uid)
    except (sqlite3.Error, OSError, ValueError):
        return {(history,turn) for namespace in namespaces
                for character,history,turn in _load_store(namespace).get("suppressed_spans", [])
                if character == character_id and (not history_uid or history == history_uid)}


def list_character_memories(
    conf_uid: str,
    *,
    enabled_only: bool = True,
    query_text: str = "",
    read_plan: MemoryReadPlan | None = None,
    project_id: str = "", history_uid: str = "", historical: bool = False,
    max_entries: int | None = None,
    token_budget: int | None = None,
) -> list[dict[str, Any]]:
    if not conf_uid:
        return []
    namespaces = memory_namespaces(conf_uid, project_id)
    plan = read_plan
    if plan is None and query_text:
        plan = infer_memory_read_plan(query_text, max_entries=max_entries or 12)

    if plan and enabled_only:
        cutoff = query_cutoff(plan.query_text)
        hits = []
        for namespace in namespaces:
            try:
                hits.extend(_MEMORY_INDEX.lookup(namespace, plan, project_id=project_id,
                                                 history_uid=history_uid, historical=historical or bool(cutoff), cutoff=cutoff))
            except (ValueError, OSError, RuntimeError, sqlite3.Error):
                logger.warning("Memory projection unavailable; using scoped canonical text")
                entries = _load_store(namespace)["entries"]
                terms = query_terms(plan.query_text)
                for entry in entries:
                    if cutoff and (not (entry.get("valid_from") or entry.get("created_at")) or
                            (entry.get("valid_from") or entry["created_at"])[:10] > cutoff or
                            (entry.get("valid_to") and entry["valid_to"][:10] <= cutoff)):
                        continue
                    if not historical and not cutoff:
                        now = _now_iso()
                        if ((entry.get("valid_from") and not _at_or_after(now,entry["valid_from"])) or
                                (entry.get("valid_to") and _at_or_after(now,entry["valid_to"]))):
                            continue
                    authorized_history = (historical or bool(cutoff)) and _entry_status(entry)=="superseded" and has_save_authorization(entry)
                    if (not (_is_active_memory(entry) or authorized_history) or not terms.intersection(_keyword_terms(entry["content"]))
                            or not _in_conversation_scope(entry, namespace, project_id, history_uid)):
                        continue
                    hits.append(MemorySearchHit(entry, 1, ("canonical",)))
        hits.sort(key=lambda h: (-h.score, h.entry["id"]))
        return _MEMORY_RETRIEVER._pack_entries([h.entry for h in hits], max_entries=max_entries or plan.max_entries,
                                               token_budget=token_budget or plan.token_budget)
    entries = [
        entry for namespace in namespaces for entry in _load_store(namespace)["entries"]
        if not enabled_only or _in_conversation_scope(entry, namespace, project_id, history_uid)
    ]
    entries = _MEMORY_RETRIEVER.retrieve(
        entries,
        enabled_only=enabled_only,
        read_plan=plan,
        namespace=conf_uid,
        max_entries=max_entries,
        token_budget=token_budget,
    )
    return entries


def format_character_memories_for_prompt(
    conf_uid: str,
    *,
    max_entries: int = 24,
    query_text: str = "",
    project_id: str = "", history_uid: str = "",
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
        enabled_only=True, history_uid=history_uid, project_id=project_id,
        historical=bool(re.search(r"以前|當時|過去|之前|截至|as of|時点|formerly|used to|previously|以前は", query_text, re.I)),
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
            validity = entry.get("status") or "unknown"
            observed = (entry.get("evidence") or {}).get("observed_at") or entry.get("created_at","")
            evidence = entry.get("evidence") or {}
            provenance = " ".join(f"{key}={value}" for key,value in (
                ("observed",observed),("event_date",evidence.get("event_date")),("valid_to",entry.get("valid_to")),
                ("revision",entry.get("revision",1)),("source",entry.get("source")),
                ("history",entry.get("source_history_uid")),("turn",evidence.get("turn_id"))) if value)
            lines.append(f"- [{scope_label} {validity} {provenance} id={entry.get('id')}] ({memory_type}) {content}")
    return "\n".join(lines).strip()


def format_character_memories_for_preview(conf_uid: str, *, max_entries: int | None = None) -> str:
    entries = list_character_memories(conf_uid, enabled_only=False)[:max_entries]
    if not entries:
        return "目前沒有角色長期記憶。"

    lines: list[str] = []
    for entry in entries:
        status = _entry_status(entry)
        marker = "ACTIVE" if _is_active_memory(entry) else status.upper()
        memory_type = str(entry.get("memory_type") or "fact")
        content = _clean_text(str(entry.get("content") or ""), max_len=260)
        updated_at = str(entry.get("updated_at") or "")
        lines.append(f"[{marker}] ({memory_type}) {content}")
        if updated_at:
            lines.append(f"  updated: {updated_at}")
    return "\n".join(lines).strip()
