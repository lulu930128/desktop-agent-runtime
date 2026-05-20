from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol


VALID_SCOPE_LEVELS = {
    "global_user",
    "character",
    "project",
    "thread",
    "runtime",
}

VALID_STATUSES = {
    "active",
    "superseded",
    "disabled",
    "pending_confirmation",
    "pending_delete",
}


@dataclass(frozen=True)
class MemorySearchHit:
    entry: dict[str, Any]
    score: float
    reasons: tuple[str, ...] = ()


class MemoryIndex(Protocol):
    def search(
        self,
        entries: list[dict[str, Any]],
        plan: Any,
        *,
        namespace: str = "",
    ) -> list[MemorySearchHit]:
        ...


def normalize_text(content: str) -> str:
    return re.sub(r"[\s,.;:!?\"'`]+", "", content or "").lower()


def clean_text(content: str, max_len: int = 260) -> str:
    clean = " ".join((content or "").replace("\r", " ").replace("\n", " ").split())
    clean = clean.strip(" \t\r\n\"'`")
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 1].rstrip(".,!?") + "..."


def estimate_tokens(content: str) -> int:
    text = content or ""
    if not text:
        return 0
    return max(1, len(text) // 3)


def keyword_terms(content: str) -> set[str]:
    text = (content or "").lower()
    terms = set(re.findall(r"[a-z0-9_./:\\-]{2,}", text))
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        terms.add(chunk)
        if len(chunk) > 2:
            terms.update(chunk[index : index + 2] for index in range(len(chunk) - 1))
    return {term for term in terms if len(term) >= 2}


def entry_scope_level(entry: dict[str, Any]) -> str:
    scope_level = str(entry.get("scope_level") or "").strip()
    if scope_level in VALID_SCOPE_LEVELS:
        return scope_level
    if str(entry.get("scope") or "") == "character":
        return "character"
    return "character"


def entry_status(entry: dict[str, Any]) -> str:
    status = str(entry.get("status") or "").strip()
    if status in VALID_STATUSES:
        return status
    return "active" if entry.get("enabled", True) else "disabled"


def is_active_memory(entry: dict[str, Any]) -> bool:
    return entry.get("enabled", True) and entry_status(entry) == "active"


def format_scope_label(entry: dict[str, Any]) -> str:
    scope_level = entry_scope_level(entry)
    scope_id = str(entry.get("scope_id") or "").strip()
    return f"{scope_level}:{scope_id}" if scope_id else scope_level


class KeywordMemoryIndex:
    """Current production index: deterministic BM25-like keyword scoring.

    It keeps retrieval dependency-free today, while matching the shape of a
    future SQLite FTS or vector-backed index.
    """

    def search(
        self,
        entries: list[dict[str, Any]],
        plan: Any,
        *,
        namespace: str = "",
    ) -> list[MemorySearchHit]:
        hits = [
            MemorySearchHit(
                entry=entry,
                score=self._score(entry, plan),
                reasons=("keyword",),
            )
            for entry in entries
        ]
        hits.sort(
            key=lambda hit: (
                hit.score,
                str(hit.entry.get("updated_at") or ""),
            ),
            reverse=True,
        )
        return hits

    def _scope_priority_score(self, scope_level: str, priority: list[str]) -> int:
        try:
            return max(0, 20 - priority.index(scope_level) * 4)
        except ValueError:
            return 0

    def _score(self, entry: dict[str, Any], plan: Any) -> float:
        content = str(entry.get("content") or "")
        memory_type = str(entry.get("memory_type") or "fact")
        memory_types = list(getattr(plan, "memory_types", []) or [])
        scope_priority = list(getattr(plan, "scope_priority", []) or [])
        query_text = str(getattr(plan, "query_text", "") or "")

        score = float(entry.get("importance") or 0.0) * 45
        score += float(entry.get("confidence") or 0.0) * 15
        score += self._scope_priority_score(entry_scope_level(entry), scope_priority)

        if memory_type in memory_types:
            score += max(4, 18 - memory_types.index(memory_type) * 2)

        query_terms = keyword_terms(query_text)
        entry_terms = keyword_terms(
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

        normalized_query = normalize_text(query_text)
        normalized_content = normalize_text(content)
        if normalized_query and normalized_content:
            if normalized_query in normalized_content or normalized_content in normalized_query:
                score += 16

        if entry.get("updated_at"):
            score += 2
        return score


class CharacterMemoryRetriever:
    def __init__(self, index: MemoryIndex | None = None) -> None:
        self._index = index or KeywordMemoryIndex()

    def retrieve(
        self,
        entries: list[dict[str, Any]],
        *,
        enabled_only: bool = True,
        read_plan: Any | None = None,
        namespace: str = "",
        max_entries: int | None = None,
        token_budget: int | None = None,
    ) -> list[dict[str, Any]]:
        candidates = [
            entry
            for entry in entries
            if isinstance(entry, dict) and (not enabled_only or is_active_memory(entry))
        ]

        if read_plan:
            hits = self._index.search(candidates, read_plan, namespace=namespace)
            ordered_entries = [hit.entry for hit in hits]
            max_count = max_entries or int(getattr(read_plan, "max_entries", 12) or 12)
            budget = (
                token_budget
                if token_budget is not None
                else int(getattr(read_plan, "token_budget", 900) or 900)
            )
        else:
            ordered_entries = sorted(
                candidates,
                key=lambda entry: (
                    float(entry.get("importance") or 0),
                    str(entry.get("updated_at") or ""),
                ),
                reverse=True,
            )
            max_count = max_entries or len(ordered_entries)
            budget = token_budget

        return self._pack_entries(
            ordered_entries,
            max_entries=max(0, max_count),
            token_budget=budget,
        )

    def _pack_entries(
        self,
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
            content = clean_text(str(entry.get("content") or ""), max_len=220)
            if not content:
                continue
            entry_tokens = estimate_tokens(content) + 8
            if token_budget is not None and selected and used_tokens + entry_tokens > token_budget:
                continue
            selected.append(entry)
            used_tokens += entry_tokens
            if token_budget is not None and used_tokens >= token_budget:
                break
        return selected
