from __future__ import annotations

import asyncio
import re
from datetime import datetime
from html import unescape
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)
SEARCH_ENDPOINT = "https://html.duckduckgo.com/html/"
DEFAULT_TIMEZONE = "Asia/Taipei"
LOCAL_INTENT_TOKENS = [
    "附近",
    "地址",
    "在哪",
    "哪裡",
    "哪间",
    "哪家",
    "哪間",
    "營業",
    "营业",
    "現在",
    "宵夜",
    "晚餐",
    "午餐",
    "餐廳",
    "餐厅",
    "牛排",
    "咖啡",
    "美食",
    "景點",
    "景点",
    "停車",
    "停车",
]
FRESHNESS_TOKENS = [
    "最新",
    "即時",
    "即时报",
    "即時",
    "現在",
    "今天",
    "今日",
    "最近",
    "剛剛",
    "news",
    "latest",
    "today",
    "current",
    "recent",
]
LOCAL_DETAIL_HINTS = ["營業", "营业", "hours", "open", "closing", "地址", "location"]

mcp = FastMCP("kuro-web")


def _normalize_whitespace(text: str) -> str:
    return " ".join((text or "").split())


def _decode_duckduckgo_href(href: str) -> str:
    if not href:
        return ""
    href = href.strip()
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    if href.startswith("//"):
        return f"https:{href}"
    if href.startswith("/"):
        return urljoin(SEARCH_ENDPOINT, href)
    return href


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _is_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff\u3040-\u30ff]", text or ""))


def _contains_any(text: str, tokens: list[str]) -> bool:
    lowered = (text or "").lower()
    return any(token.lower() in lowered for token in tokens)


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = _normalize_whitespace(value)
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        output.append(normalized)
    return output


async def _get_text(
    url: str,
    *,
    timeout: float = 20.0,
    params: dict[str, Any] | None = None,
) -> str:
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(timeout),
        headers=headers,
    ) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.text


def _extract_readable_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    for bad in soup(["script", "style", "noscript", "svg", "header", "footer"]):
        bad.decompose()

    title = _normalize_whitespace(soup.title.get_text(" ", strip=True) if soup.title else "")

    candidates = [
        soup.select_one("main"),
        soup.select_one("article"),
        soup.select_one("[role='main']"),
        soup.select_one(".article"),
        soup.select_one(".post"),
        soup.select_one(".entry-content"),
        soup.select_one("#content"),
    ]
    text_source = next((node for node in candidates if node), soup)
    text = _normalize_whitespace(text_source.get_text("\n", strip=True))
    return title, text


async def _search_once(query: str, max_results: int) -> list[dict[str, str]]:
    html = await _get_text(SEARCH_ENDPOINT, params={"q": query})
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, str]] = []

    for block in soup.select(".result"):
        title_el = block.select_one(".result__title")
        link_el = block.select_one(".result__title a, .result__url")
        snippet_el = block.select_one(".result__snippet")

        title = _normalize_whitespace(
            title_el.get_text(" ", strip=True) if title_el else ""
        )
        href = _decode_duckduckgo_href(link_el.get("href", "") if link_el else "")
        snippet = _normalize_whitespace(
            unescape(snippet_el.get_text(" ", strip=True) if snippet_el else "")
        )

        if not title and not href:
            continue

        results.append(
            {
                "title": title or href,
                "url": href,
                "snippet": snippet,
            }
        )
        if len(results) >= max_results:
            break

    return results


def _build_query_variants(question: str, *, timezone: str) -> list[str]:
    question = _normalize_whitespace(question)
    if not question:
        return []

    variants: list[str] = [question]
    now = datetime.now(ZoneInfo(timezone))
    year = str(now.year)
    month_day = now.strftime("%m/%d")
    local_intent = _contains_any(question, LOCAL_INTENT_TOKENS)
    freshness = _contains_any(question, FRESHNESS_TOKENS)
    cjk = _is_cjk(question)

    if local_intent:
        if cjk:
            variants.extend(
                [
                    f"{question} 營業時間",
                    f"{question} 地址",
                    f"{question} 評價",
                ]
            )
            if "現在" in question or "今晚" in question or "宵夜" in question:
                variants.append(f"{question} 現在 營業")
        else:
            variants.extend(
                [
                    f"{question} opening hours",
                    f"{question} address",
                    f"{question} reviews",
                ]
            )

    if freshness:
        if cjk:
            variants.extend(
                [
                    f"{question} 最新",
                    f"{question} 今天",
                    f"{question} {year}",
                    f"{question} {month_day}",
                ]
            )
        else:
            variants.extend(
                [
                    f"{question} latest",
                    f"{question} today",
                    f"{question} {year}",
                    f"{question} {month_day}",
                ]
            )

    if not local_intent and not freshness:
        if cjk:
            variants.append(f"{question} 資訊")
        else:
            variants.append(f"{question} information")

    return _dedupe_keep_order(variants)[:5]


def _score_result(
    result: dict[str, str],
    *,
    question: str,
    local_intent: bool,
    freshness: bool,
) -> int:
    haystack = f"{result.get('title', '')} {result.get('snippet', '')}".lower()
    score = 0
    for token in _normalize_whitespace(question).lower().split():
        if token and token in haystack:
            score += 2

    domain = _domain(result.get("url", ""))
    if domain:
        score += 1
    if any(domain.endswith(suffix) for suffix in [".gov.tw", ".gov", ".edu", ".org"]):
        score += 2
    if "wikipedia.org" in domain:
        score += 1

    if local_intent and _contains_any(haystack, LOCAL_DETAIL_HINTS):
        score += 4
    if freshness and _contains_any(
        haystack,
        [str(datetime.now().year), "latest", "today", "breaking", "最新", "今日"],
    ):
        score += 3
    return score


def _merge_results(
    results_by_query: list[tuple[str, list[dict[str, str]]]],
    *,
    question: str,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    local_intent = _contains_any(question, LOCAL_INTENT_TOKENS)
    freshness = _contains_any(question, FRESHNESS_TOKENS)

    for query, results in results_by_query:
        for item in results:
            url = item.get("url", "").strip()
            title = item.get("title", "").strip()
            key = url or title.lower()
            if not key:
                continue

            entry = merged.setdefault(
                key,
                {
                    "title": title,
                    "url": url,
                    "snippet": item.get("snippet", "").strip(),
                    "matched_queries": [],
                    "score": 0,
                },
            )
            entry["matched_queries"].append(query)
            if len(item.get("snippet", "")) > len(entry.get("snippet", "")):
                entry["snippet"] = item.get("snippet", "").strip()
            entry["score"] = max(
                int(entry.get("score", 0)),
                _score_result(
                    item,
                    question=question,
                    local_intent=local_intent,
                    freshness=freshness,
                ),
            )

    ranked = sorted(
        merged.values(),
        key=lambda item: (
            int(item.get("score", 0)),
            len(item.get("matched_queries", [])),
            len(item.get("snippet", "")),
        ),
        reverse=True,
    )
    return ranked


async def _fetch_brief(url: str, max_chars: int = 900) -> str:
    try:
        html = await _get_text(url, timeout=15.0)
    except Exception as exc:
        return f"Fetch failed: {exc}"

    title, text = _extract_readable_text(html)
    if not text:
        return "No readable text content found."
    trimmed = text[:max_chars]
    if len(text) > max_chars:
        trimmed += " ..."
    if title:
        return f"Title: {title}\nContent: {trimmed}"
    return f"Content: {trimmed}"


@mcp.tool(
    name="search_web",
    description="Quick public web search. Good for a fast first pass when you only need titles, snippets, and URLs.",
)
async def search_web(query: str, max_results: int = 5) -> str:
    query = _normalize_whitespace(query)
    if not query:
        return "Search error: query is empty."

    max_results = max(1, min(int(max_results or 5), 10))
    try:
        results = await _search_once(query, max_results)
    except Exception as exc:
        return f"Search error: {exc}"

    if not results:
        return "Search returned no usable results."

    lines = [f"Search results for: {query}"]
    for idx, item in enumerate(results, start=1):
        lines.append(f"{idx}. {item['title']}")
        if item["url"]:
            lines.append(f"URL: {item['url']}")
        if item["snippet"]:
            lines.append(f"Snippet: {item['snippet']}")
        lines.append("")
    return "\n".join(lines).strip()


@mcp.tool(
    name="smart_search_web",
    description=(
        "Smarter multi-step web search for time-sensitive or practical questions. "
        "It rewrites the query, searches several variants, deduplicates results, "
        "and can fetch top pages for better evidence."
    ),
)
async def smart_search_web(
    question: str,
    max_results: int = 5,
    fetch_top_pages: int = 2,
    timezone: str = DEFAULT_TIMEZONE,
) -> str:
    question = _normalize_whitespace(question)
    if not question:
        return "Smart search error: question is empty."

    max_results = max(1, min(int(max_results or 5), 8))
    fetch_top_pages = max(0, min(int(fetch_top_pages or 0), 3))
    variants = _build_query_variants(question, timezone=timezone)
    if not variants:
        return "Smart search error: failed to build query variants."

    search_tasks = [_search_once(query, max_results) for query in variants]
    gathered = await asyncio.gather(*search_tasks, return_exceptions=True)

    results_by_query: list[tuple[str, list[dict[str, str]]]] = []
    errors: list[str] = []
    for query, result in zip(variants, gathered):
        if isinstance(result, Exception):
            errors.append(f"{query}: {result}")
            continue
        results_by_query.append((query, result))

    merged = _merge_results(results_by_query, question=question)[:max_results]
    if not merged:
        error_text = f" Smart-search query errors: {' | '.join(errors)}" if errors else ""
        return f"Smart search returned no usable results.{error_text}"

    top_pages = [item for item in merged if item.get("url")] [:fetch_top_pages]
    fetch_notes: list[tuple[str, str]] = []
    if top_pages:
        fetched = await asyncio.gather(
            *[_fetch_brief(item["url"]) for item in top_pages],
            return_exceptions=True,
        )
        for item, payload in zip(top_pages, fetched):
            if isinstance(payload, Exception):
                fetch_notes.append((item["url"], f"Fetch failed: {payload}"))
            else:
                fetch_notes.append((item["url"], payload))

    lines = [f"Smart search for: {question}", f"Search plan: {' | '.join(variants)}", ""]

    if errors:
        lines.append("Search warnings:")
        for err in errors[:3]:
            lines.append(f"- {err}")
        lines.append("")

    lines.append("Ranked results:")
    for idx, item in enumerate(merged, start=1):
        lines.append(f"{idx}. {item['title']}")
        if item.get("url"):
            lines.append(f"URL: {item['url']}")
        if item.get("snippet"):
            lines.append(f"Snippet: {item['snippet']}")
        if item.get("matched_queries"):
            lines.append(
                f"Matched queries: {', '.join(item['matched_queries'][:3])}"
            )
        lines.append("")

    if fetch_notes:
        lines.append("Fetched page notes:")
        for url, note in fetch_notes:
            lines.append(f"URL: {url}")
            lines.append(note)
            lines.append("")

    return "\n".join(lines).strip()


@mcp.tool(
    name="fetch_content",
    description="Fetch a public web page and return cleaned main text content for reading or verification.",
)
async def fetch_content(url: str, max_chars: int = 4000) -> str:
    url = (url or "").strip()
    if not url:
        return "Fetch error: url is empty."

    max_chars = max(500, min(int(max_chars or 4000), 12000))
    try:
        html = await _get_text(url)
    except Exception as exc:
        return f"Fetch error: {exc}"

    title, text = _extract_readable_text(html)
    if not text:
        return f"Fetched: {url}\nNo readable text content found."

    trimmed = text[:max_chars]
    if len(text) > max_chars:
        trimmed += " ..."

    parts = [f"Fetched: {url}"]
    if title:
        parts.append(f"Title: {title}")
    parts.append(f"Content: {trimmed}")
    return "\n".join(parts)


@mcp.tool(
    name="get_current_time",
    description="Get the current local time in a requested IANA timezone.",
)
def get_current_time(timezone: str = DEFAULT_TIMEZONE) -> str:
    try:
        now = datetime.now(ZoneInfo((timezone or DEFAULT_TIMEZONE).strip()))
    except Exception:
        now = datetime.now(ZoneInfo(DEFAULT_TIMEZONE))
        timezone = DEFAULT_TIMEZONE
    return (
        f"Current time in {timezone}: "
        f"{now.strftime('%Y-%m-%d %H:%M:%S %Z')} "
        f"(ISO: {now.isoformat()})"
    )


if __name__ == "__main__":
    mcp.run()
