from __future__ import annotations

import asyncio
import ipaddress
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import unescape
from typing import Any
from urllib.parse import parse_qs, parse_qsl, unquote, urlencode, urljoin, urlparse, urlunparse
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
OFFICIAL_INTENT_TOKENS = [
    "官方",
    "官網",
    "官方文件",
    "原廠",
    "公告",
    "規格",
    "法規",
    "documentation",
    "official",
    "docs",
    "api",
    "release notes",
]
DOCUMENTATION_INTENT_TOKENS = [
    "文件",
    "教學",
    "指南",
    "規格",
    "API",
    "SDK",
    "documentation",
    "docs",
    "guide",
    "reference",
    "spec",
]
COMPARISON_INTENT_TOKENS = [
    "比較",
    "差異",
    "差別",
    "推薦",
    "評測",
    "優缺點",
    "compare",
    "comparison",
    "versus",
    " vs ",
    "review",
    "benchmark",
]
LOW_TRUST_DOMAIN_MARKERS = [
    "reddit.com",
    "quora.com",
    "facebook.com",
    "x.com",
    "twitter.com",
    "tiktok.com",
    "instagram.com",
]
SEARCH_DEPTH_PROFILES = {
    "fast": {
        "query_limit": 3,
        "results_per_query": 4,
        "max_results": 4,
        "fetch_top_pages": 0,
        "evidence_chars": 900,
    },
    "normal": {
        "query_limit": 5,
        "results_per_query": 6,
        "max_results": 6,
        "fetch_top_pages": 2,
        "evidence_chars": 1400,
    },
    "deep": {
        "query_limit": 8,
        "results_per_query": 8,
        "max_results": 10,
        "fetch_top_pages": 4,
        "evidence_chars": 2200,
    },
}

mcp = FastMCP("kuro-web")


@dataclass(frozen=True)
class SearchIntent:
    local: bool
    freshness: bool
    official: bool
    documentation: bool
    comparison: bool
    cjk: bool


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


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))


def _normalize_depth(depth: str) -> str:
    normalized = (depth or "normal").strip().lower()
    aliases = {
        "quick": "fast",
        "light": "fast",
        "fast": "fast",
        "normal": "normal",
        "medium": "normal",
        "default": "normal",
        "deep": "deep",
        "advanced": "deep",
        "high": "deep",
    }
    return aliases.get(normalized, "normal")


def _safe_zoneinfo(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo((timezone or DEFAULT_TIMEZONE).strip())
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def _split_domain_list(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = [str(item) for item in value]
    else:
        raw_items = re.split(r"[,;\s]+", str(value or ""))

    domains: list[str] = []
    for item in raw_items:
        item = item.strip().lower()
        if not item:
            continue
        if item.startswith("http://") or item.startswith("https://"):
            item = urlparse(item).netloc.lower()
        item = item.lstrip(".").removeprefix("www.")
        item = item.strip("/")
        if item and item not in domains:
            domains.append(item)
    return domains[:8]


def _strip_www(hostname: str) -> str:
    return (hostname or "").lower().removeprefix("www.")


def _domain_matches(domain: str, candidates: list[str]) -> bool:
    normalized = _strip_www(domain)
    return any(normalized == item or normalized.endswith(f".{item}") for item in candidates)


def _canonical_url(url: str) -> str:
    parsed = urlparse(url or "")
    if not parsed.scheme or not parsed.netloc:
        return (url or "").strip()

    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower()
        not in {
            "fbclid",
            "gclid",
            "mc_cid",
            "mc_eid",
            "ref",
            "source",
        }
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (
            parsed.scheme.lower(),
            _strip_www(parsed.netloc),
            path,
            "",
            urlencode(filtered_query, doseq=True),
            "",
        )
    )


def _url_block_reason(url: str) -> str:
    parsed = urlparse(url or "")
    if parsed.scheme.lower() not in {"http", "https"}:
        return "Only public HTTP/HTTPS pages can be fetched."

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return "URL has no hostname."
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return f"URL host '{host}' is blocked."
    if host.endswith(".local") or host.endswith(".internal"):
        return f"URL host '{host}' looks private/internal."

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return ""
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        return f"URL host '{host}' is private/internal."
    return ""


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
    blocked = _url_block_reason(url)
    if blocked:
        raise ValueError(f"Blocked URL: {blocked}")

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


def _meta_content(soup: BeautifulSoup, *selectors: str) -> str:
    for selector in selectors:
        node = soup.select_one(selector)
        if not node:
            continue
        value = node.get("content") or node.get("datetime") or node.get_text(" ", strip=True)
        value = _normalize_whitespace(str(value or ""))
        if value:
            return value
    return ""


def _extract_page_snapshot(url: str, html: str, max_chars: int) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = _normalize_whitespace(soup.title.get_text(" ", strip=True) if soup.title else "")
    description = _meta_content(
        soup,
        "meta[name='description']",
        "meta[property='og:description']",
        "meta[name='twitter:description']",
    )
    published_at = _meta_content(
        soup,
        "meta[property='article:published_time']",
        "meta[property='og:updated_time']",
        "meta[name='date']",
        "meta[name='pubdate']",
        "time[datetime]",
    )

    for bad in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        bad.decompose()

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
    trimmed = text[:max_chars]
    if len(text) > max_chars:
        trimmed += " ..."

    return {
        "url": url,
        "domain": _domain(url),
        "title": title,
        "description": description,
        "published_at": published_at,
        "content": trimmed,
    }


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


def _classify_search_intent(question: str) -> SearchIntent:
    return SearchIntent(
        local=_contains_any(question, LOCAL_INTENT_TOKENS),
        freshness=_contains_any(question, FRESHNESS_TOKENS),
        official=_contains_any(question, OFFICIAL_INTENT_TOKENS),
        documentation=_contains_any(question, DOCUMENTATION_INTENT_TOKENS),
        comparison=_contains_any(question, COMPARISON_INTENT_TOKENS),
        cjk=_is_cjk(question),
    )


def _build_advanced_query_plan(
    question: str,
    *,
    timezone: str,
    depth: str = "normal",
    preferred_domains: list[str] | None = None,
    require_official: bool = False,
    recency_days: int = 0,
) -> tuple[list[str], SearchIntent]:
    question = _normalize_whitespace(question)
    if not question:
        return [], _classify_search_intent("")

    depth = _normalize_depth(depth)
    profile = SEARCH_DEPTH_PROFILES[depth]
    preferred_domains = preferred_domains or []
    variants: list[str] = [question]
    now = datetime.now(_safe_zoneinfo(timezone))
    year = str(now.year)
    month_day = now.strftime("%m/%d")
    intent = _classify_search_intent(question)

    for domain in preferred_domains[:3]:
        variants.append(f"{question} site:{domain}")

    if require_official or intent.official:
        if intent.cjk:
            variants.extend(
                [
                    f"{question} 官方",
                    f"{question} 官方文件",
                    f"{question} 公告",
                ]
            )
        variants.extend(
            [
                f"{question} official",
                f"{question} documentation",
                f"{question} release notes",
            ]
        )

    if intent.documentation:
        variants.extend(
            [
                f"{question} docs",
                f"{question} reference",
                f"{question} API",
            ]
        )

    if intent.local:
        if intent.cjk:
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

    if intent.freshness or recency_days > 0:
        if intent.cjk:
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

    if intent.comparison:
        if intent.cjk:
            variants.extend([f"{question} 比較", f"{question} 評測"])
        variants.extend([f"{question} comparison", f"{question} review"])

    if not any([intent.local, intent.freshness, intent.official, intent.documentation]):
        if intent.cjk:
            variants.append(f"{question} 資訊")
        else:
            variants.append(f"{question} information")

    if recency_days > 0:
        since = now - timedelta(days=recency_days)
        variants.append(f"{question} after:{since.strftime('%Y-%m-%d')}")

    return _dedupe_keep_order(variants)[: int(profile["query_limit"])], intent


def _build_query_variants(question: str, *, timezone: str) -> list[str]:
    variants, _intent = _build_advanced_query_plan(
        question,
        timezone=timezone,
        depth="normal",
    )
    return variants


def _score_result(
    result: dict[str, str],
    *,
    question: str,
    local_intent: bool,
    freshness: bool,
    intent: SearchIntent | None = None,
    preferred_domains: list[str] | None = None,
    require_official: bool = False,
) -> int:
    haystack = f"{result.get('title', '')} {result.get('snippet', '')}".lower()
    score = 0
    preferred_domains = preferred_domains or []
    terms = _question_terms(question)
    for token in terms:
        if token and token in haystack:
            score += 2

    domain = _domain(result.get("url", ""))
    if domain:
        score += 1
    score += _source_quality_score(domain, result.get("title", ""), result.get("snippet", ""))
    if preferred_domains and _domain_matches(domain, preferred_domains):
        score += 10
    if "wikipedia.org" in domain:
        score += 1

    if local_intent and _contains_any(haystack, LOCAL_DETAIL_HINTS):
        score += 4
    if freshness and _contains_any(
        haystack,
        [str(datetime.now().year), "latest", "today", "breaking", "最新", "今日"],
    ):
        score += 3
    if intent and intent.documentation and _contains_any(
        f"{domain} {haystack}",
        ["docs", "documentation", "developer", "reference", "api", "文件"],
    ):
        score += 5
    if (require_official or (intent.official if intent else False)) and _looks_official(
        domain,
        result.get("title", ""),
        result.get("snippet", ""),
    ):
        score += 7
    return score


def _question_terms(question: str) -> list[str]:
    raw_terms = re.findall(r"[A-Za-z0-9_+.#-]{2,}|[\u4e00-\u9fff]{2,}", question or "")
    stop_terms = {
        "請問",
        "幫我",
        "查詢",
        "搜尋",
        "一下",
        "最新",
        "現在",
        "今天",
        "what",
        "when",
        "where",
        "which",
        "please",
        "search",
        "latest",
        "current",
    }
    terms: list[str] = []
    for term in raw_terms:
        normalized = term.casefold()
        if normalized in stop_terms or len(normalized) < 2:
            continue
        if normalized not in terms:
            terms.append(normalized)
    return terms[:16]


def _source_kind(domain: str, title: str = "", snippet: str = "") -> str:
    normalized = _strip_www(domain)
    haystack = f"{normalized} {title} {snippet}".casefold()
    if normalized.endswith(".gov") or ".gov." in normalized:
        return "government"
    if normalized.endswith(".edu") or ".edu." in normalized:
        return "academic"
    if any(token in haystack for token in ["docs", "documentation", "developer", "reference"]):
        return "documentation"
    if normalized.endswith(".org"):
        return "organization"
    if any(marker in normalized for marker in LOW_TRUST_DOMAIN_MARKERS):
        return "community"
    if "wikipedia.org" in normalized:
        return "encyclopedia"
    if any(token in haystack for token in ["news", "新聞", "times", "reuters", "bbc"]):
        return "news"
    return "general"


def _source_quality_score(domain: str, title: str, snippet: str) -> int:
    kind = _source_kind(domain, title, snippet)
    if kind == "government":
        return 7
    if kind == "academic":
        return 6
    if kind == "documentation":
        return 5
    if kind == "organization":
        return 3
    if kind == "news":
        return 2
    if kind == "encyclopedia":
        return 1
    if kind == "community":
        return -2
    return 0


def _looks_official(domain: str, title: str, snippet: str) -> bool:
    haystack = f"{domain} {title} {snippet}".casefold()
    if _source_kind(domain, title, snippet) in {"government", "academic", "documentation"}:
        return True
    return any(token in haystack for token in ["official", "官方", "docs", "developer"])


def _confidence_label(item: dict[str, Any], *, fetched: bool = False) -> str:
    score = int(item.get("score", 0))
    kind = str(item.get("source_kind") or "")
    if fetched and score >= 18 and kind in {"government", "academic", "documentation", "organization"}:
        return "high"
    if score >= 12:
        return "medium"
    return "low"


def _merge_results(
    results_by_query: list[tuple[str, list[dict[str, str]]]],
    *,
    question: str,
    intent: SearchIntent | None = None,
    preferred_domains: list[str] | None = None,
    blocked_domains: list[str] | None = None,
    require_official: bool = False,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    intent = intent or _classify_search_intent(question)
    preferred_domains = preferred_domains or []
    blocked_domains = blocked_domains or []
    local_intent = intent.local
    freshness = intent.freshness

    for query, results in results_by_query:
        for item in results:
            url = item.get("url", "").strip()
            title = item.get("title", "").strip()
            domain = _domain(url)
            if blocked_domains and _domain_matches(domain, blocked_domains):
                continue
            key = _canonical_url(url) or title.lower()
            if not key:
                continue

            entry = merged.setdefault(
                key,
                {
                    "title": title,
                    "url": url,
                    "canonical_url": key,
                    "domain": domain,
                    "source_kind": _source_kind(domain, title, item.get("snippet", "")),
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
                    intent=intent,
                    preferred_domains=preferred_domains,
                    require_official=require_official,
                ),
            )
            entry["confidence"] = _confidence_label(entry)

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
    snapshot = await _fetch_snapshot(url, max_chars=max_chars)
    if snapshot.get("error"):
        return f"Fetch failed: {snapshot['error']}"
    title = snapshot.get("title", "")
    content = snapshot.get("content", "")
    if not content:
        return "No readable text content found."
    if title:
        return f"Title: {title}\nContent: {content}"
    return f"Content: {content}"


async def _fetch_snapshot(url: str, max_chars: int = 1400) -> dict[str, str]:
    try:
        html = await _get_text(url, timeout=15.0)
    except Exception as exc:
        return {"url": url, "domain": _domain(url), "error": str(exc)}

    snapshot = _extract_page_snapshot(url, html, max_chars)
    snapshot["error"] = ""
    return snapshot


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


async def _advanced_search_web_impl(
    *,
    question: str,
    depth: str = "normal",
    max_results: int | None = None,
    fetch_top_pages: int | None = None,
    timezone: str = DEFAULT_TIMEZONE,
    require_official: bool = False,
    preferred_domains: Any = "",
    blocked_domains: Any = "",
    recency_days: int = 0,
) -> str:
    question = _normalize_whitespace(question)
    if not question:
        return "Advanced search error: question is empty."

    depth = _normalize_depth(depth)
    profile = SEARCH_DEPTH_PROFILES[depth]
    preferred = _split_domain_list(preferred_domains)
    blocked = _split_domain_list(blocked_domains)
    max_results = _clamp_int(
        max_results,
        default=int(profile["max_results"]),
        minimum=1,
        maximum=12,
    )
    fetch_default = int(profile["fetch_top_pages"])
    fetch_top_pages = _clamp_int(
        fetch_top_pages,
        default=fetch_default,
        minimum=0,
        maximum=5,
    )
    recency_days = _clamp_int(recency_days, default=0, minimum=0, maximum=3650)

    queries, intent = _build_advanced_query_plan(
        question,
        timezone=timezone,
        depth=depth,
        preferred_domains=preferred,
        require_official=require_official,
        recency_days=recency_days,
    )
    if not queries:
        return "Advanced search error: failed to build query plan."

    results_per_query = _clamp_int(
        profile["results_per_query"],
        default=6,
        minimum=3,
        maximum=10,
    )
    search_tasks = [_search_once(query, results_per_query) for query in queries]
    gathered = await asyncio.gather(*search_tasks, return_exceptions=True)

    results_by_query: list[tuple[str, list[dict[str, str]]]] = []
    errors: list[str] = []
    for query, result in zip(queries, gathered):
        if isinstance(result, Exception):
            errors.append(f"{query}: {result}")
            continue
        results_by_query.append((query, result))

    merged = _merge_results(
        results_by_query,
        question=question,
        intent=intent,
        preferred_domains=preferred,
        blocked_domains=blocked,
        require_official=require_official,
    )[:max_results]
    if not merged:
        error_text = f" Search errors: {' | '.join(errors)}" if errors else ""
        return f"Advanced search returned no usable results.{error_text}"

    evidence_chars = int(profile["evidence_chars"])
    top_pages = [item for item in merged if item.get("url")][:fetch_top_pages]
    fetched_snapshots: list[dict[str, str]] = []
    if top_pages:
        fetched = await asyncio.gather(
            *[_fetch_snapshot(item["url"], max_chars=evidence_chars) for item in top_pages],
            return_exceptions=True,
        )
        for item, payload in zip(top_pages, fetched):
            if isinstance(payload, Exception):
                snapshot = {
                    "url": item["url"],
                    "domain": item.get("domain", ""),
                    "error": str(payload),
                }
            else:
                snapshot = payload
            item["fetched"] = snapshot
            if not snapshot.get("error"):
                content = f"{snapshot.get('title', '')} {snapshot.get('description', '')} {snapshot.get('content', '')}".casefold()
                for term in _question_terms(question):
                    if term in content:
                        item["score"] = int(item.get("score", 0)) + 1
                if snapshot.get("published_at") and (intent.freshness or recency_days > 0):
                    item["score"] = int(item.get("score", 0)) + 3
            item["confidence"] = _confidence_label(item, fetched=not snapshot.get("error"))
            fetched_snapshots.append(snapshot)

        merged = sorted(
            merged,
            key=lambda item: (
                int(item.get("score", 0)),
                item.get("confidence") == "high",
                len(item.get("matched_queries", [])),
            ),
            reverse=True,
        )

    return _format_advanced_search_output(
        question=question,
        depth=depth,
        queries=queries,
        intent=intent,
        results=merged,
        fetched_snapshots=fetched_snapshots,
        errors=errors,
        preferred_domains=preferred,
        blocked_domains=blocked,
        require_official=require_official,
        recency_days=recency_days,
        timezone=timezone,
    )


def _format_advanced_search_output(
    *,
    question: str,
    depth: str,
    queries: list[str],
    intent: SearchIntent,
    results: list[dict[str, Any]],
    fetched_snapshots: list[dict[str, str]],
    errors: list[str],
    preferred_domains: list[str],
    blocked_domains: list[str],
    require_official: bool,
    recency_days: int,
    timezone: str,
) -> str:
    now = datetime.now(_safe_zoneinfo(timezone))
    distinct_domains = sorted({item.get("domain", "") for item in results if item.get("domain")})
    high_confidence = [item for item in results if item.get("confidence") == "high"]
    official_like = [
        item
        for item in results
        if _looks_official(item.get("domain", ""), item.get("title", ""), item.get("snippet", ""))
    ]

    lines = [
        f"Advanced search for: {question}",
        f"Depth: {depth}",
        f"Generated at: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "Intent:",
        (
            f"- local={intent.local}, freshness={intent.freshness}, "
            f"official={intent.official or require_official}, "
            f"documentation={intent.documentation}, comparison={intent.comparison}"
        ),
    ]
    if preferred_domains:
        lines.append(f"Preferred domains: {', '.join(preferred_domains)}")
    if blocked_domains:
        lines.append(f"Blocked domains: {', '.join(blocked_domains)}")
    if recency_days:
        lines.append(f"Recency hint: prefer sources updated within {recency_days} days when dates are visible.")

    lines.extend(["", "Search plan:"])
    for idx, query in enumerate(queries, start=1):
        lines.append(f"{idx}. {query}")

    if errors:
        lines.extend(["", "Search warnings:"])
        for err in errors[:4]:
            lines.append(f"- {err}")

    lines.extend(["", "Ranked sources:"])
    for idx, item in enumerate(results, start=1):
        lines.append(f"{idx}. {item.get('title') or item.get('url')}")
        lines.append(f"URL: {item.get('url', '')}")
        lines.append(
            "Source: "
            f"{item.get('domain', '')} | kind={item.get('source_kind', 'general')} | "
            f"confidence={item.get('confidence', 'low')} | score={item.get('score', 0)}"
        )
        if item.get("snippet"):
            lines.append(f"Snippet: {item['snippet']}")
        matched = item.get("matched_queries") or []
        if matched:
            lines.append(f"Matched queries: {', '.join(matched[:3])}")
        lines.append("")

    if fetched_snapshots:
        lines.append("Fetched evidence:")
        for idx, snapshot in enumerate(fetched_snapshots, start=1):
            lines.append(f"{idx}. {snapshot.get('title') or snapshot.get('url')}")
            lines.append(f"URL: {snapshot.get('url', '')}")
            if snapshot.get("published_at"):
                lines.append(f"Published/updated: {snapshot['published_at']}")
            if snapshot.get("description"):
                lines.append(f"Description: {snapshot['description']}")
            if snapshot.get("error"):
                lines.append(f"Fetch warning: {snapshot['error']}")
            elif snapshot.get("content"):
                lines.append(f"Content excerpt: {snapshot['content']}")
            lines.append("")

    lines.append("Research notes:")
    lines.append(f"- Ranked {len(results)} sources across {len(distinct_domains)} domains.")
    if fetched_snapshots:
        ok_fetches = sum(1 for item in fetched_snapshots if not item.get("error"))
        lines.append(f"- Fetched readable evidence from {ok_fetches}/{len(fetched_snapshots)} top sources.")
    if high_confidence:
        lines.append(f"- High-confidence sources found: {len(high_confidence)}.")
    if (require_official or intent.official or intent.documentation) and not official_like:
        lines.append("- Warning: no clearly official/documentation source was found.")
    if len(distinct_domains) < 2 and len(results) > 1:
        lines.append("- Warning: results are concentrated in one domain; verify with another source if stakes are high.")
    lines.append("- Use the URLs above as citations in the final answer when you rely on them.")

    return "\n".join(lines).strip()


@mcp.tool(
    name="advanced_search_web",
    description=(
        "Advanced public web research. Builds a query plan, searches multiple variants, "
        "scores source quality, optionally prefers official domains, fetches top pages, "
        "and returns ranked evidence for citation."
    ),
)
async def advanced_search_web(
    question: str,
    depth: str = "normal",
    max_results: int = 6,
    fetch_top_pages: int = 2,
    timezone: str = DEFAULT_TIMEZONE,
    require_official: bool = False,
    preferred_domains: str = "",
    blocked_domains: str = "",
    recency_days: int = 0,
) -> str:
    return await _advanced_search_web_impl(
        question=question,
        depth=depth,
        max_results=max_results,
        fetch_top_pages=fetch_top_pages,
        timezone=timezone,
        require_official=require_official,
        preferred_domains=preferred_domains,
        blocked_domains=blocked_domains,
        recency_days=recency_days,
    )


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
    return await _advanced_search_web_impl(
        question=question,
        depth="normal",
        max_results=max_results,
        fetch_top_pages=fetch_top_pages,
        timezone=timezone,
    )


@mcp.tool(
    name="fetch_content",
    description="Fetch a public web page and return cleaned main text content for reading or verification.",
)
async def fetch_content(url: str, max_chars: int = 4000) -> str:
    url = (url or "").strip()
    if not url:
        return "Fetch error: url is empty."

    max_chars = max(500, min(int(max_chars or 4000), 12000))
    snapshot = await _fetch_snapshot(url, max_chars=max_chars)
    if snapshot.get("error"):
        return f"Fetch error: {snapshot['error']}"
    if not snapshot.get("content"):
        return f"Fetched: {url}\nNo readable text content found."

    parts = [f"Fetched: {url}"]
    if snapshot.get("title"):
        parts.append(f"Title: {snapshot['title']}")
    if snapshot.get("published_at"):
        parts.append(f"Published/updated: {snapshot['published_at']}")
    if snapshot.get("description"):
        parts.append(f"Description: {snapshot['description']}")
    parts.append(f"Content: {snapshot['content']}")
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
