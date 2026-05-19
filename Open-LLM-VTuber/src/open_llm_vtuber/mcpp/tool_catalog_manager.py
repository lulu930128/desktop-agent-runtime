import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass(frozen=True)
class ToolRoute:
    categories: list[str]
    tool_names: list[str]
    reason: str


class ToolCatalog:
    def __init__(self, catalog: dict[str, Any] | None = None) -> None:
        self.catalog = catalog if isinstance(catalog, dict) else {}
        categories = self.catalog.get("categories")
        self.categories = categories if isinstance(categories, dict) else {}
        routing = self.catalog.get("routing")
        self.routing = routing if isinstance(routing, dict) else {}

    @classmethod
    def load_default(cls) -> "ToolCatalog":
        path = _default_catalog_path()
        if path and path.exists():
            try:
                return cls(json.loads(path.read_text(encoding="utf-8")))
            except Exception as exc:
                logger.warning(f"Failed to load tool catalog from {path}: {exc}")
        return cls({"version": 1, "routing": {"max_candidate_tools": 6}, "categories": {}})

    @property
    def enabled(self) -> bool:
        return bool(self.categories)

    @property
    def max_candidate_tools(self) -> int:
        raw_value = self.routing.get("max_candidate_tools", 6)
        try:
            return max(1, min(int(raw_value), 20))
        except Exception:
            return 6

    def route(
        self,
        request_text: str,
        available_tool_names: list[str],
        thinking_power: str = "normal",
    ) -> ToolRoute:
        available = {name for name in available_tool_names if name}
        if not self.enabled or not available:
            return ToolRoute([], [], "Tool catalog is empty or no tools are available.")

        text = _normalize_text(request_text)
        if not text:
            return ToolRoute([], [], "No user request text available for tool routing.")

        scored = self._score_categories(text)
        if not scored:
            return ToolRoute([], [], "No tool category matched this turn.")

        selected_categories = [category_id for category_id, _score in scored]
        candidate_names: list[str] = []
        for category_id in selected_categories:
            category = self.categories.get(category_id)
            if not isinstance(category, dict):
                continue
            for tool_name in self._ordered_category_tools(
                category,
                category_id=category_id,
                thinking_power=thinking_power,
            ):
                if tool_name in available and tool_name not in candidate_names:
                    candidate_names.append(tool_name)
                if len(candidate_names) >= self.max_candidate_tools:
                    break
            if len(candidate_names) >= self.max_candidate_tools:
                break

        if not candidate_names:
            return ToolRoute(
                selected_categories,
                [],
                "Matched category has no currently available tools.",
            )

        return ToolRoute(
            selected_categories,
            candidate_names,
            f"Matched categories: {', '.join(selected_categories)}",
        )

    def format_prompt_summary(
        self,
        available_tool_names: list[str] | None = None,
        thinking_power: str = "normal",
    ) -> str:
        available = set(available_tool_names or [])
        normalized_power = normalize_thinking_power(thinking_power)
        lines = [
            "Tool catalog routing summary:",
            "- First select a capability category, then choose a tool inside that category.",
            "- Runtime policy still decides whether a selected tool is allowed to execute.",
            f"- Current thinking power: {normalized_power}. This controls web-search depth.",
            "",
            "Categories:",
        ]
        for category_id, category in self.categories.items():
            if not isinstance(category, dict):
                continue
            title = str(category.get("title") or category_id)
            description = str(category.get("description") or "").strip()
            tools = [
                name
                for name in self._ordered_category_tools(
                    category,
                    category_id=category_id,
                    thinking_power=normalized_power,
                )
                if not available or name in available
            ]
            tool_text = ", ".join(tools) if tools else "(no active tools yet)"
            lines.append(f"- {category_id} / {title}: {description}")
            lines.append(f"  Tools: {tool_text}")
        return "\n".join(lines).strip()

    def _score_categories(self, normalized_text: str) -> list[tuple[str, int]]:
        scores: dict[str, int] = {}
        for category_id, category in self.categories.items():
            if not isinstance(category, dict):
                continue
            score = 0
            keywords = category.get("intent_keywords") or []
            if isinstance(keywords, list):
                for keyword in keywords:
                    kw = _normalize_text(str(keyword))
                    if kw and kw in normalized_text:
                        score += 3 if len(kw) >= 4 else 1
            if score > 0:
                scores[category_id] = score

        if re.search(r"(?i)\b(?:https?://|www\.)\S+", normalized_text):
            scores["web_research"] = scores.get("web_research", 0) + 6

        if _looks_like_public_web_request(normalized_text):
            scores["web_research"] = scores.get("web_research", 0) + 5

        if _looks_like_visual_lookup_request(normalized_text):
            scores["web_research"] = scores.get("web_research", 0) + 4

        if re.search(r"(?i)\b[A-Z]:[\\/]|(?:^|[\s`'\"])[./\\][\w.-]+|\.py\b|\.json\b|\.ya?ml\b|\.log\b", normalized_text):
            scores["local_files"] = scores.get("local_files", 0) + 5

        if re.search(r"(?i)\b(error|traceback|exception|config|prompt|launcher|runtime)\b", normalized_text):
            scores["local_files"] = scores.get("local_files", 0) + 2

        return sorted(scores.items(), key=lambda item: item[1], reverse=True)

    @staticmethod
    def _ordered_category_tools(
        category: dict[str, Any],
        *,
        category_id: str = "",
        thinking_power: str = "normal",
    ) -> list[str]:
        ordered: list[str] = []
        tools = category.get("tools") or []
        tool_items: list[dict[str, Any]] = []
        if isinstance(tools, list):
            for item in tools:
                if isinstance(item, dict):
                    tool_items.append(item)
                else:
                    tool_items.append({"name": str(item or "").strip()})

        if category_id == "web_research":
            level_order = {
                "fast": {"light": 0, "read": 1, "deep": 2, "search": 2},
                "normal": {"deep": 0, "light": 1, "read": 2, "search": 1},
                "deep": {"deep": 0, "read": 1, "light": 2, "search": 2},
            }.get(normalize_thinking_power(thinking_power), {})
            tool_items = sorted(
                tool_items,
                key=lambda item: level_order.get(str(item.get("level") or ""), 9),
            )
        else:
            default_tools = category.get("default_tools") or []
            if isinstance(default_tools, list):
                ordered.extend(str(name) for name in default_tools if str(name).strip())

        for item in tool_items:
            name = str(item.get("name") or "").strip()
            if name and name not in ordered:
                ordered.append(name)
        return ordered


def _normalize_text(text: str) -> str:
    return " ".join((text or "").casefold().split())


def _looks_like_public_web_request(text: str) -> bool:
    """Catch natural Chinese/English requests that imply public web lookup."""
    public_lookup_terms = [
        "查",
        "搜尋",
        "搜索",
        "搜",
        "最新",
        "最近",
        "即時",
        "目前",
        "現況",
        "近況",
        "新聞",
        "價格",
        "匯率",
        "股價",
        "天氣",
        "地震",
        "颱風",
        "官方",
        "文件",
        "資料來源",
    ]
    if any(term in text for term in public_lookup_terms):
        return True

    return bool(
        re.search(
            r"(?i)\b(search|lookup|latest|recent|current|news|price|weather|earthquake|official|docs?)\b",
            text,
        )
    )


def _looks_like_visual_lookup_request(text: str) -> bool:
    visual_markers = [
        "visual input instructions",
        "attached visual context",
        "attached image",
        "image data",
        "screenshot",
        "圖片",
        "照片",
        "截圖",
    ]
    if not any(marker in text for marker in visual_markers):
        return False

    lookup_terms = [
        "查",
        "搜",
        "找",
        "哪裡",
        "在哪",
        "來源",
        "這是什麼",
        "是什麼",
        "角色",
        "人物",
        "動漫",
        "動畫",
        "漫畫",
        "虛擬主播",
        "遊戲角色",
        "吉祥物",
        "立繪",
        "二次元",
        "品牌",
        "型號",
        "產品",
        "地點",
        "辨識",
        "官方",
        "價格",
        "identify",
        "what is",
        "where is",
        "source",
        "search",
        "lookup",
        "brand",
        "model",
        "product",
        "location",
        "character",
        "anime",
        "manga",
        "vtuber",
        "virtual youtuber",
        "game character",
    ]
    return any(term in text for term in lookup_terms)


def normalize_thinking_power(value: str) -> str:
    normalized = (value or "normal").strip().lower()
    aliases = {
        "quick": "fast",
        "light": "fast",
        "fast": "fast",
        "normal": "normal",
        "medium": "normal",
        "default": "normal",
        "deep": "deep",
        "depth": "deep",
        "high": "deep",
    }
    return aliases.get(normalized, "normal")


def _default_catalog_path() -> Path | None:
    env_path = os.getenv("KURO_TOOL_CATALOG_PATH", "").strip()
    if env_path:
        return Path(env_path)

    candidates = [
        Path.cwd() / "tool_catalog.json",
        Path(__file__).resolve().parents[3] / "tool_catalog.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]
