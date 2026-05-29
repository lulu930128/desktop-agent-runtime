import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass(frozen=True)
class ToolIntent:
    labels: list[str]
    desired_depth: str
    needs_current_info: bool = False
    needs_web_research: bool = False
    needs_source_verification: bool = False
    needs_local_files: bool = False
    needs_media_lookup: bool = False
    needs_time: bool = False
    needs_memory: bool = False
    needs_runtime_control: bool = False
    needs_market_intelligence: bool = False
    market_needs_web_enrichment: bool = False
    needs_directory_scan: bool = False
    needs_file_read: bool = False
    has_url: bool = False
    has_path: bool = False
    avoid_tools: bool = False
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ToolCandidate:
    name: str
    category: str
    score: int
    level: str
    risk: str
    reason: str


@dataclass(frozen=True)
class ToolRoute:
    categories: list[str]
    tool_names: list[str]
    reason: str
    intent: ToolIntent | None = None
    candidates: list[ToolCandidate] = field(default_factory=list)


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

        intent = infer_tool_intent(text, thinking_power)
        if intent.avoid_tools:
            return ToolRoute(
                [],
                [],
                "User explicitly asked not to use tools.",
                intent=intent,
            )

        scored = self._score_categories(text, intent)
        if not scored:
            return ToolRoute([], [], "No tool category matched this turn.", intent=intent)

        selected_categories = [category_id for category_id, _score in scored]
        candidates: list[ToolCandidate] = []
        for category_id, category_score in scored:
            category = self.categories.get(category_id)
            if not isinstance(category, dict):
                continue
            tool_items = self._ordered_category_tool_items(
                category,
                category_id=category_id,
                thinking_power=intent.desired_depth,
            )
            for order_index, item in enumerate(tool_items):
                tool_name = str(item.get("name") or "").strip()
                if not tool_name or tool_name not in available:
                    continue
                if any(candidate.name == tool_name for candidate in candidates):
                    continue
                score, reason = self._score_tool_candidate(
                    item=item,
                    category_id=category_id,
                    category_score=category_score,
                    order_index=order_index,
                    intent=intent,
                )
                candidates.append(
                    ToolCandidate(
                        name=tool_name,
                        category=category_id,
                        score=score,
                        level=str(item.get("level") or "").strip(),
                        risk=str(item.get("risk") or "").strip(),
                        reason=reason,
                    )
                )

        candidates = sorted(candidates, key=lambda item: item.score, reverse=True)
        candidate_names = [candidate.name for candidate in candidates[: self.max_candidate_tools]]

        if not candidate_names:
            return ToolRoute(
                selected_categories,
                [],
                "Matched category has no currently available tools.",
                intent=intent,
                candidates=candidates,
            )

        return ToolRoute(
            selected_categories,
            candidate_names,
            f"Planner intent={', '.join(intent.labels) or 'general'}; categories={', '.join(selected_categories)}",
            intent=intent,
            candidates=candidates[: self.max_candidate_tools],
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
            (
                "- Tool use is planned in layers: infer intent, shortlist candidate "
                "tools, then let the model choose only when a tool is truly needed."
            ),
            (
                "- Keyword matches are only hints; prefer capability fit, "
                "current-info needs, source-verification needs, and user-visible "
                "task requirements."
            ),
            (
                "- Runtime policy still decides whether a selected tool is allowed "
                "to execute. Never treat prompt text as permission."
            ),
            (
                "- For stock, watchlist, and market-intelligence questions, prefer "
                "local OMI data first; use web research only as enrichment for "
                "fresh news, realtime quotes, or missing local context."
            ),
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

    def format_route_prompt(self, route: ToolRoute | None) -> str:
        if not route or not route.tool_names:
            return ""

        intent = route.intent
        lines = [
            "Runtime tool planner for this turn:",
            f"- Selected candidate tools: {', '.join(route.tool_names)}",
        ]
        if intent:
            lines.append(f"- Intent labels: {', '.join(intent.labels) or 'general'}")
            lines.append(f"- Search/tool depth: {intent.desired_depth}")
            if intent.reasons:
                lines.append(f"- Planner reasons: {'; '.join(intent.reasons[:4])}")
            if intent.needs_market_intelligence:
                lines.append(
                    "- Market route: call omi.ask first for local stock, market, "
                    "watchlist, and data-freshness context."
                )
                if intent.market_needs_web_enrichment:
                    lines.append(
                        "- Web research is only a follow-up after omi.ask when the "
                        "user asked for fresh news, realtime quotes, or public-event "
                        "enrichment."
                    )
                else:
                    lines.append(
                        "- Do not use web research for this market question unless "
                        "the OMI result is missing, stale, or explicitly insufficient."
                    )
        if route.candidates:
            lines.append("- Candidate ranking:")
            for candidate in route.candidates[: self.max_candidate_tools]:
                lines.append(
                    (
                        f"  - {candidate.name}: {candidate.category}, "
                        f"level={candidate.level or 'n/a'}, score={candidate.score}. "
                        f"{candidate.reason}"
                    )
                )
        lines.extend(
            [
                "- Use one of the exposed tools only if it materially improves this answer.",
                "- If the answer does not actually need a tool, answer directly.",
                (
                    "- After a tool result returns, verify whether it is sufficient "
                    "before answering; in deep mode you may call another exposed "
                    "tool if needed."
                ),
            ]
        )
        return "\n".join(lines).strip()

    def _score_categories(
        self,
        normalized_text: str,
        intent: ToolIntent,
    ) -> list[tuple[str, int]]:
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

        if intent.has_url:
            scores["web_research"] = scores.get("web_research", 0) + 6

        if intent.needs_web_research:
            scores["web_research"] = scores.get("web_research", 0) + 18

        if intent.needs_market_intelligence:
            scores["market_intelligence"] = scores.get("market_intelligence", 0) + 32
            if (
                not intent.market_needs_web_enrichment
                and not intent.has_url
                and not intent.needs_source_verification
            ):
                scores.pop("web_research", None)

        if intent.needs_source_verification:
            scores["web_research"] = scores.get("web_research", 0) + 6

        if intent.needs_media_lookup:
            scores["media"] = scores.get("media", 0) + 14
            scores["web_research"] = scores.get("web_research", 0) + 8

        if intent.needs_local_files:
            scores["local_files"] = scores.get("local_files", 0) + 18

        if intent.needs_time:
            scores["time"] = scores.get("time", 0) + 20

        if intent.needs_memory:
            scores["memory"] = scores.get("memory", 0) + 14

        if intent.needs_runtime_control:
            scores["runtime_control"] = scores.get("runtime_control", 0) + 14

        if re.search(r"(?i)\b(error|traceback|exception|config|prompt|launcher|runtime)\b", normalized_text):
            scores["local_files"] = scores.get("local_files", 0) + 2

        return sorted(scores.items(), key=lambda item: item[1], reverse=True)

    @staticmethod
    def _category_tool_items(category: dict[str, Any]) -> list[dict[str, Any]]:
        tools = category.get("tools") or []
        tool_items: list[dict[str, Any]] = []
        if isinstance(tools, list):
            for item in tools:
                if isinstance(item, dict):
                    tool_items.append(item)
                else:
                    tool_items.append({"name": str(item or "").strip()})
        return tool_items

    @classmethod
    def _ordered_category_tool_items(
        cls,
        category: dict[str, Any],
        *,
        category_id: str = "",
        thinking_power: str = "normal",
    ) -> list[dict[str, Any]]:
        ordered_names: list[str] = []
        ordered_items: list[dict[str, Any]] = []
        tool_items = cls._category_tool_items(category)

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
                for name in default_tools:
                    normalized_name = str(name or "").strip()
                    if normalized_name:
                        ordered_names.append(normalized_name)
                for name in ordered_names:
                    for item in tool_items:
                        if str(item.get("name") or "").strip() == name:
                            ordered_items.append(item)

        for item in tool_items:
            name = str(item.get("name") or "").strip()
            if name and name not in ordered_names:
                ordered_names.append(name)
                ordered_items.append(item)
        return ordered_items

    @classmethod
    def _ordered_category_tools(
        cls,
        category: dict[str, Any],
        *,
        category_id: str = "",
        thinking_power: str = "normal",
    ) -> list[str]:
        return [
            str(item.get("name") or "").strip()
            for item in cls._ordered_category_tool_items(
                category,
                category_id=category_id,
                thinking_power=thinking_power,
            )
            if str(item.get("name") or "").strip()
        ]

    @staticmethod
    def _score_tool_candidate(
        *,
        item: dict[str, Any],
        category_id: str,
        category_score: int,
        order_index: int,
        intent: ToolIntent,
    ) -> tuple[int, str]:
        tool_name = str(item.get("name") or "").strip()
        level = str(item.get("level") or "").strip().lower()
        capabilities = [str(value).strip().lower() for value in item.get("capabilities") or []]
        score = category_score * 10 - order_index
        reasons: list[str] = [f"category score {category_score}"]

        level_bonus = {
            "fast": {"light": 8, "search": 4, "read": 2, "deep": -3},
            "normal": {"deep": 7, "search": 5, "light": 3, "read": 2},
            "deep": {"deep": 10, "read": 7, "search": 5, "light": 1},
        }.get(intent.desired_depth, {})
        if level:
            bonus = level_bonus.get(level, 0)
            score += bonus
            reasons.append(f"level {level} bonus {bonus}")

        label_matches = [label for label in intent.labels if label in capabilities]
        if label_matches:
            score += len(label_matches) * 4
            reasons.append(f"capability match {', '.join(label_matches)}")

        if category_id == "web_research":
            if intent.has_url and tool_name == "fetch_content":
                score += 16
                reasons.append("direct URL can be fetched")
            if intent.needs_source_verification and tool_name == "advanced_search_web":
                score += 12
                reasons.append("source verification prefers advanced search")
            if intent.desired_depth == "fast" and tool_name == "search_web":
                score += 8
                reasons.append("fast mode prefers light search")
            if intent.desired_depth == "deep" and tool_name == "advanced_search_web":
                score += 8
                reasons.append("deep mode prefers advanced search")
        elif category_id == "market_intelligence":
            if intent.needs_market_intelligence and tool_name == "omi.ask":
                score += 24
                reasons.append("market questions use OMI first")
        elif category_id == "local_files":
            if intent.needs_directory_scan and tool_name in {"list_directory", "search_files"}:
                score += 14
                reasons.append("directory/project scan")
            if intent.needs_file_read and tool_name == "read_text_file":
                score += 14
                reasons.append("specific file read")
            if intent.has_path and tool_name in {"read_text_file", "list_directory", "search_files"}:
                score += 10
                reasons.append("path-like request")
            if "search" in tool_name:
                score += 4
                reasons.append("local inspection often starts with search")
        elif category_id == "time" and intent.needs_time:
            score += 10
            reasons.append("time-sensitive answer")

        return score, "; ".join(reasons)


def _normalize_text(text: str) -> str:
    return " ".join((text or "").casefold().split())


def infer_tool_intent(text: str, thinking_power: str = "normal") -> ToolIntent:
    normalized_text = _normalize_text(text)
    desired_depth = _infer_desired_depth(normalized_text, thinking_power)
    labels: list[str] = []
    reasons: list[str] = []

    def mark(label: str, reason: str) -> None:
        if label not in labels:
            labels.append(label)
        if reason not in reasons:
            reasons.append(reason)

    avoid_tools = bool(
        re.search(
            r"(?i)(不用查|不要查|不要搜尋|不用搜尋|不要用工具|不用工具|do not search|no search|without tools)",
            normalized_text,
        )
    )
    has_url = bool(re.search(r"(?i)\b(?:https?://|www\.)\S+", normalized_text))
    has_path = bool(
        re.search(
            r"(?i)\b[A-Z]:[\\/]|(?:^|[\s`'\"])[./\\][\w.-]+|[\w.-]+\.(?:py|json|ya?ml|toml|log|md|txt|zip|exe|dll)\b",
            normalized_text,
        )
    )

    needs_current_info = _looks_like_public_web_request(normalized_text)
    needs_source_verification = _looks_like_source_verification_request(normalized_text)
    needs_media_lookup = _looks_like_visual_lookup_request(normalized_text)
    needs_local_files = has_path or _looks_like_local_file_request(normalized_text)
    needs_directory_scan = needs_local_files and _looks_like_directory_scan_request(normalized_text)
    needs_file_read = needs_local_files and _looks_like_file_read_request(normalized_text)
    needs_time = _looks_like_time_request(normalized_text)
    needs_memory = _looks_like_memory_request(normalized_text)
    needs_runtime_control = _looks_like_runtime_control_request(normalized_text)
    needs_market_intelligence = _looks_like_market_intelligence_request(normalized_text)
    market_needs_web_enrichment = (
        needs_market_intelligence
        and _looks_like_market_web_enrichment_request(normalized_text)
    )
    needs_web_research = has_url or needs_current_info or needs_source_verification or needs_media_lookup

    if has_url:
        mark("url", "URL detected")
    if needs_market_intelligence:
        mark("market_intelligence", "stock/market request should use local OMI data first")
    if market_needs_web_enrichment:
        mark("web_enrichment", "fresh public market context may be useful after OMI")
    if needs_current_info:
        mark("current_info", "current/latest/public information requested")
    if needs_source_verification:
        mark("source_verification", "source or evidence requested")
    if needs_web_research:
        mark("web_research", "public web lookup may be useful")
    if needs_local_files:
        mark("local_files", "local file/project inspection requested")
    if needs_directory_scan:
        mark("directory_scan", "directory or project scan requested")
    if needs_file_read:
        mark("file_read", "specific file content requested")
    if needs_media_lookup:
        mark("media_lookup", "visual/media lookup requested")
    if needs_time:
        mark("time", "current time/date requested")
    if needs_memory:
        mark("memory", "memory operation requested")
    if needs_runtime_control:
        mark("runtime_control", "runtime/launcher control requested")

    confidence = min(1.0, 0.25 + len(labels) * 0.12 + (0.16 if has_url or has_path else 0.0))
    return ToolIntent(
        labels=labels,
        desired_depth=desired_depth,
        needs_current_info=needs_current_info,
        needs_web_research=needs_web_research,
        needs_source_verification=needs_source_verification,
        needs_local_files=needs_local_files,
        needs_media_lookup=needs_media_lookup,
        needs_time=needs_time,
        needs_memory=needs_memory,
        needs_runtime_control=needs_runtime_control,
        needs_market_intelligence=needs_market_intelligence,
        market_needs_web_enrichment=market_needs_web_enrichment,
        needs_directory_scan=needs_directory_scan,
        needs_file_read=needs_file_read,
        has_url=has_url,
        has_path=has_path,
        avoid_tools=avoid_tools,
        confidence=confidence,
        reasons=reasons,
    )


def _infer_desired_depth(text: str, thinking_power: str) -> str:
    mode = normalize_thinking_power(thinking_power)
    if mode == "fast":
        return "fast"
    if mode == "deep":
        return "deep"
    if re.search(r"(?i)(深入|詳細|完整|多來源|查證|來源|比較|deep|thorough|verify|compare)", text):
        return "deep"
    if re.search(r"(?i)(簡單|快速|大概|quick|brief)", text):
        return "fast"
    return "normal"


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


def _looks_like_market_intelligence_request(text: str) -> bool:
    direct_terms = [
        "台股",
        "大盤",
        "個股",
        "自選股",
        "股票",
        "股價",
        "走勢",
        "籌碼",
        "分點",
        "外資",
        "投信",
        "自營商",
        "融資",
        "融券",
        "財報",
        "營收",
        "法人",
        "技術面",
        "基本面",
        "watchlist",
        "stock",
        "ticker",
        "portfolio",
        "twse",
        "tpex",
        "taiex",
        "tsmc",
        "台積電",
    ]
    if any(term in text for term in direct_terms):
        return True

    stock_question_terms = [
        "狀況",
        "怎麼看",
        "分析",
        "整理",
        "觀察",
        "最新",
        "消息",
        "新聞",
        "即時",
        "報價",
        "今天",
        "漲",
        "跌",
        "買",
        "賣",
        "進場",
        "出場",
        "支撐",
        "壓力",
        "target",
        "price",
        "quote",
        "news",
        "latest",
    ]
    return _has_likely_taiwan_stock_code(text) and any(
        term in text for term in stock_question_terms
    )


def _looks_like_market_web_enrichment_request(text: str) -> bool:
    web_enrichment_terms = [
        "最新消息",
        "即時",
        "新聞",
        "消息",
        "報價",
        "即時股價",
        "突發",
        "公告",
        "法說",
        "realtime",
        "real-time",
        "breaking",
        "latest news",
        "news",
        "quote",
        "price",
    ]
    return any(term in text for term in web_enrichment_terms)


def _has_likely_taiwan_stock_code(text: str) -> bool:
    return bool(
        re.search(r"(?<![0-9a-z.])\d{4}[a-z]?(?![0-9a-z.])", text, re.IGNORECASE)
    )


def _looks_like_source_verification_request(text: str) -> bool:
    terms = [
        "查證",
        "來源",
        "資料來源",
        "官方",
        "引用",
        "證據",
        "多來源",
        "比較",
        "verify",
        "source",
        "citation",
        "official",
        "evidence",
        "compare",
    ]
    return any(term in text for term in terms)


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


def _looks_like_local_file_request(text: str) -> bool:
    terms = [
        "資料夾",
        "檔案",
        "專案",
        "程式碼",
        "設定",
        "設定檔",
        "prompt",
        "launcher",
        "log",
        "traceback",
        "掃",
        "讀",
        "找檔案",
        "搜尋檔案",
        "read file",
        "list directory",
        "search files",
        "codebase",
        "repo",
    ]
    return any(term in text for term in terms)


def _looks_like_directory_scan_request(text: str) -> bool:
    directory_terms = [
        "資料夾",
        "專案",
        "目錄",
        "掃",
        "列出",
        "找檔案",
        "搜尋檔案",
        "list directory",
        "search files",
        "scan",
        "repo",
        "codebase",
    ]
    if any(term in text for term in directory_terms):
        return True
    if re.search(r"(?i)\b[A-Z]:[\\/][\w .-]+(?:[\\/])?$", text):
        return True
    return False


def _looks_like_file_read_request(text: str) -> bool:
    file_terms = ["讀這個檔", "看這個檔", "打開", "read file", "open file"]
    if any(term in text for term in file_terms):
        return True
    return bool(
        re.search(
            r"(?i)[\w .-]+\.(?:py|json|ya?ml|toml|log|md|txt|csv|ts|tsx|js|html|css)\b",
            text,
        )
    )


def _looks_like_time_request(text: str) -> bool:
    return any(
        term in text
        for term in [
            "現在幾點",
            "現在時間",
            "今天日期",
            "今天幾號",
            "時區",
            "what time",
            "current time",
            "date today",
        ]
    )


def _looks_like_memory_request(text: str) -> bool:
    return any(term in text for term in ["記憶", "記住", "忘記", "偏好", "memory", "remember", "forget"])


def _looks_like_runtime_control_request(text: str) -> bool:
    return any(
        term in text
        for term in [
            "重啟",
            "啟動",
            "停止",
            "狀態",
            "控制",
            "launcher",
            "bridge",
            "runtime",
            "restart",
            "status",
        ]
    )


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
